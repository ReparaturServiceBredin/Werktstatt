"""E-Mail-Historie je Kunde: nur lesen, nur Kundentreffer speichern, inkrementell, ohne Duplikate."""
import re
import smtplib
from datetime import datetime, timedelta
from email.message import EmailMessage
from email.utils import format_datetime

import pytest

from rsb import db as dbm
from rsb import email_historie as eh
from rsb.mail import senden
from rsb.sicherheit import verschluesseln

from conftest import kunde_anlegen, post


def mail(von, an, betreff="Hallo", cc=None, reply_to=None, mid=None, tage_alt=1, text="Inhalt", anhang=False):
    m = EmailMessage()
    m["From"], m["To"], m["Subject"] = von, an, betreff
    if cc:
        m["Cc"] = cc
    if reply_to:
        m["Reply-To"] = reply_to
    m["Date"] = format_datetime((datetime.now() - timedelta(days=tage_alt)).astimezone())
    if mid != "keine":
        m["Message-ID"] = mid or f"<{abs(hash((von, an, betreff, tage_alt)))}@test>"
    m.set_content(text)
    if anhang:
        m.add_attachment(b"%PDF-1.4 test", maintype="application", subtype="pdf", filename="Rechnung.pdf")
    return m.as_bytes()


class Postfach:
    """Gefälschter IMAP-Server mit Ordnern, protokolliert alle Zugriffe."""
    ordner = {}
    zugriffe = []

    def __init__(self, host, port, ssl_context=None, timeout=None):
        self.aktuell = None

    def login(self, b, p):
        Postfach.zugriffe.append(("login", b))

    def select(self, name, readonly=False):
        name = name.strip('"')
        Postfach.zugriffe.append(("select", name, readonly))
        if name not in Postfach.ordner:
            return "NO", [b"gibt es nicht"]
        self.aktuell = name
        return "OK", [str(len(Postfach.ordner[name]["mails"])).encode()]

    def response(self, code):
        return code, [str(Postfach.ordner[self.aktuell]["uidvalidity"]).encode()]

    def uid(self, befehl, *args):
        mails = Postfach.ordner[self.aktuell]["mails"]
        if befehl == "SEARCH":
            k = [a for a in args if a is not None]
            uids = sorted(mails)
            if "UID" in k:
                von = int(k[k.index("UID") + 1].split(":")[0])
                uids = [u for u in uids if u >= von] or [max(mails)] if mails else []
            if "SINCE" in k:
                grenze = datetime.strptime(k[k.index("SINCE") + 1], "%d-%b-%Y")
                uids = [u for u in uids if self._datum(mails[u]) >= grenze]
            if "FROM" in k:
                adr = k[k.index("FROM") + 1].lower()
                uids = [u for u in uids if adr in self._kopf(mails[u]).lower()]
            Postfach.zugriffe.append(("search", self.aktuell, tuple(k)))
            return "OK", [" ".join(map(str, uids)).encode()]
        if befehl == "FETCH":
            satz, art = args
            assert "PEEK" in art, "Inhalte dürfen nur mit BODY.PEEK geholt werden"
            uids = [int(u) for u in (satz.decode() if isinstance(satz, bytes) else satz).split(",")]
            antwort = []
            for u in uids:
                if u not in mails:
                    continue
                if "HEADER.FIELDS" in art:
                    Postfach.zugriffe.append(("kopf", self.aktuell, u))
                    daten = self._kopf(mails[u]).encode() + b"\r\n"
                else:
                    Postfach.zugriffe.append(("voll", self.aktuell, u))
                    daten = mails[u]
                antwort += [(f"{u} (UID {u} BODY[] {{{len(daten)}}}".encode(), daten), b")"]
            return "OK", antwort
        raise AssertionError(f"Unerlaubter Befehl {befehl} – das Postfach darf nur gelesen werden")

    def _kopf(self, roh):
        return roh.split(b"\n\n", 1)[0].decode("utf-8", "replace")

    def _datum(self, roh):
        from email.utils import parsedate_to_datetime
        m = re.search(r"^Date: (.+)$", self._kopf(roh), re.M)
        return parsedate_to_datetime(m.group(1)).replace(tzinfo=None)

    def logout(self):
        pass

    for verboten in ("store", "copy", "expunge", "create", "append", "delete"):
        locals()[verboten] = lambda self, *a, _n=verboten: (_ for _ in ()).throw(AssertionError(f"{_n} verboten"))


ICH = "kontakt@reparatur-bredin.de"


@pytest.fixture
def eingerichtet(app, con, client, monkeypatch):
    app.config["HISTORIE_SYNCHRON"] = True
    monkeypatch.setattr("imaplib.IMAP4_SSL", Postfach)
    Postfach.zugriffe = []
    kontext = app.app_context()
    kontext.push()
    with dbm.Transaktion(con):
        dbm.einstellungen_speichern({"historie_aktiv": False, "imap_host": "imap.ionos.de", "imap_port": 993,
                                     "imap_sicherheit": "ssl", "imap_benutzer": ICH,
                                     "imap_passwort_enc": verschluesseln("geheim"), "absender_email": ICH,
                                     "historie_ordner_eingang": "INBOX\nKunden/Werkstatt",
                                     "historie_ordner_gesendet": "Gesendete Objekte",
                                     "historie_eigene_adressen": "reparatur-bredin@gmail.com"}, con)
    anna = kunde_anlegen(client, email="Anna@Example.com")
    firma = kunde_anlegen(client, typ="firma", firma="Bäckerei Schmid", nachname="Schmid", email="info@schmid.de",
                          email_weitere="Buchhaltung <buchhaltung@schmid.de>\nmax@schmid.de")
    with dbm.Transaktion(con):  # erst jetzt einschalten (sonst sucht schon die Kundenanlage im Postfach)
        dbm.einstellungen_speichern({"historie_aktiv": True}, con)
    Postfach.ordner = {
        "INBOX": {"uidvalidity": 7, "mails": {
            1: mail("Anna Müller <anna@example.com>", ICH, "Display kaputt", mid="<m1@a>", anhang=True),
            2: mail("Newsletter <news@shop.de>", ICH, "Angebote der Woche", mid="<m2@n>"),
            3: mail("Bob <bob@extern.de>", ICH, "Rechnung Bäckerei", cc=" BUCHHALTUNG@schmid.de ", mid="<m3@b>"),
            4: mail("reparatur-bredin@gmail.com", "anna@example.com, max@schmid.de", "Rundmail", mid="<m4@x>"),
            5: mail("Alt <anna@example.com>", ICH, "Uralt", mid="<m5@alt>", tage_alt=400),
        }},
        "Kunden/Werkstatt": {"uidvalidity": 3, "mails": {
            9: mail("Anna Müller <anna@example.com>", ICH, "Display kaputt", mid="<m1@a>"),  # Duplikat
        }},
        "Gesendete Objekte": {"uidvalidity": 11, "mails": {
            20: mail(f"Reparatur Service Bredin <{ICH}>", "Anna Müller < ANNA@example.com >", "Re: Display kaputt",
                     mid="<m20@ich>"),
            21: mail(ICH, "fremder@irgendwo.de", "Privat", mid="<m21@ich>"),
        }},
    }
    yield anna, firma
    kontext.pop()


def links(con, kid):
    return {r[0] for r in con.execute("SELECT n.message_id FROM email_nachrichten n JOIN email_kunden k "
                                      "ON k.nachricht_id=n.id WHERE k.kunde_id=?", (kid,))}


def test_abgleich_nur_kundentreffer_nur_lesen(con, eingerichtet):
    anna, firma = eingerichtet
    e = eh.abgleichen(con)
    assert e["neu"] == 4 and not e["hinweise"]
    assert links(con, anna) == {"<m1@a>", "<m4@x>", "<m20@ich>"}
    assert links(con, firma) == {"<m3@b>", "<m4@x>"}  # weitere Adresse + Mehrfachtreffer
    # Nicht-Kunden-Mails werden nicht gespeichert und nie vollständig geladen
    alle = {r[0] for r in con.execute("SELECT message_id FROM email_nachrichten")}
    assert "<m2@n>" not in alle and "<m21@ich>" not in alle and "<m5@alt>" not in alle  # m5: vor Importzeitraum
    voll = {(z[1], z[2]) for z in Postfach.zugriffe if z[0] == "voll"}
    assert voll == {("INBOX", 1), ("INBOX", 3), ("INBOX", 4), ("Gesendete Objekte", 20)}
    assert all(z[2] is True for z in Postfach.zugriffe if z[0] == "select")  # nur EXAMINE
    # Richtung, Anhänge, Inhalte
    n = {r["message_id"]: r for r in con.execute("SELECT * FROM email_nachrichten")}
    assert n["<m1@a>"]["richtung"] == "empfangen" and "Rechnung.pdf" in n["<m1@a>"]["anhaenge"]
    assert n["<m20@ich>"]["richtung"] == "gesendet" and n["<m4@x>"]["richtung"] == "gesendet"
    assert n["<m1@a>"]["ordner"] == "INBOX" and "Inhalt" in n["<m1@a>"]["text"]
    # Duplikat aus zweitem Ordner nicht doppelt
    assert con.execute("SELECT COUNT(*) FROM email_nachrichten WHERE message_id='<m1@a>'").fetchone()[0] == 1
    stand = {r["ordner"]: r for r in con.execute("SELECT * FROM imap_ordner_status")}
    assert stand["INBOX"]["letzte_uid"] == 5 and stand["INBOX"]["uidvalidity"] == 7  # höchste UID des Ordners


def test_inkrementell_und_uidvalidity(con, eingerichtet):
    anna, _ = eingerichtet
    eh.abgleichen(con)
    Postfach.zugriffe = []
    Postfach.ordner["INBOX"]["mails"][6] = mail("anna@example.com", ICH, "Neu", mid="<m6@a>")
    e = eh.abgleichen(con)
    assert e["neu"] == 1 and "<m6@a>" in links(con, anna)
    assert {z[2] for z in Postfach.zugriffe if z[0] == "kopf" and z[1] == "INBOX"} == {6}  # nur die neue Mail
    # UIDVALIDITY ändert sich → Ordner neu abgleichen, keine Duplikate
    Postfach.ordner["INBOX"]["uidvalidity"] = 8
    Postfach.zugriffe = []
    e = eh.abgleichen(con)
    assert e["neu"] == 0 and {z[2] for z in Postfach.zugriffe if z[0] == "kopf" and z[1] == "INBOX"} == {1, 2, 3, 4, 6}
    assert con.execute("SELECT COUNT(*) FROM email_nachrichten").fetchone()[0] == 5


def test_versand_aus_programm_zusammengefuehrt(con, eingerichtet, monkeypatch):
    anna, _ = eingerichtet

    class Smtp:
        def __init__(self, *a, **k):
            pass
        starttls = login = quit = lambda self, *a, **k: None

        def send_message(self, msg):
            Smtp.msg = msg
    monkeypatch.setattr(smtplib, "SMTP", Smtp)
    with dbm.Transaktion(con):
        dbm.einstellungen_speichern({"smtp_host": "smtp.ionos.de", "smtp_port": 587, "smtp_benutzer": ICH,
                                     "smtp_passwort_enc": verschluesseln("x")}, con)
    senden(con, None, "anna@example.com", "Ihr Kostenvoranschlag", "Anbei", b"%PDF", "KV-2026-0001.pdf")
    mid = Smtp.msg["Message-ID"]
    n = con.execute("SELECT * FROM email_nachrichten WHERE message_id=?", (mid,)).fetchone()
    assert n["quelle"] == "programm" and n["richtung"] == "gesendet" and n["ordner"] is None
    assert mid in links(con, anna)
    # Später findet der Abgleich dieselbe Mail im Gesendet-Ordner → zusammengeführt, nicht doppelt
    Postfach.ordner["Gesendete Objekte"]["mails"][22] = Smtp.msg.as_bytes()
    eh.abgleichen(con)
    zeilen = con.execute("SELECT * FROM email_nachrichten WHERE message_id=?", (mid,)).fetchall()
    assert len(zeilen) == 1 and zeilen[0]["ordner"] == "Gesendete Objekte" and zeilen[0]["quelle"] == "programm"
    assert ("voll", "Gesendete Objekte", 22) not in Postfach.zugriffe  # bekannte Mail nicht erneut geladen
    # an Nicht-Kunden: nichts gespeichert
    senden(con, None, "fremder@irgendwo.de", "Privat", "x")
    assert not con.execute("SELECT 1 FROM email_nachrichten WHERE message_id=?", (Smtp.msg["Message-ID"],)).fetchone()


def test_neuer_kunde_wird_nachgeholt(con, client, eingerichtet):
    eh.abgleichen(con)  # carl ist noch kein Kunde → nichts gespeichert, Ordnerstand steht danach am Ende
    Postfach.ordner["INBOX"]["mails"][7] = mail("Carl <carl@neu.de>", ICH, "Termin?", mid="<m7@c>")
    eh.abgleichen(con)
    assert not con.execute("SELECT 1 FROM email_nachrichten WHERE message_id='<m7@c>'").fetchone()
    r = post(client, "/kunden/neu", typ="privat", vorname="Carl", nachname="Neu", email="CARL@neu.de")
    kid = int(re.search(r"/kunden/(\d+)", r.headers["Location"]).group(1))
    assert "<m7@c>" in links(con, kid)
    assert any(z[0] == "search" and "FROM" in z[2] and "carl@neu.de" in z[2] for z in Postfach.zugriffe)
    # weitere Adresse nachträglich ergänzt
    Postfach.ordner["Gesendete Objekte"]["mails"][23] = mail(ICH, "carl.privat@web.de", "Abholung", mid="<m23@ich>")
    eh.abgleichen(con)
    post(client, f"/kunden/{kid}", typ="privat", vorname="Carl", nachname="Neu", email="carl@neu.de",
         email_weitere="carl.privat@web.de")
    assert "<m23@ich>" in links(con, kid)
    seite = client.get(f"/kunden/{kid}").get_data(as_text=True)
    assert "E-Mail-Verlauf" in seite and "Termin?" in seite and "Abholung" in seite


def test_kontaktformular_verknuepft(con, eingerichtet):
    anna, _ = eingerichtet
    con.execute("INSERT INTO anfragen (eingang_am, quelle, message_id, status, einstufung, spam_punkte, kunde_id) "
                "VALUES (?, 'email', '<form1@web>', 'kunde_angelegt', 'echt', 0, ?)", (dbm.jetzt(), anna))
    Postfach.ordner["INBOX"]["mails"][8] = mail("Website <noreply@reparatur-bredin.de>", ICH, "A new form",
                                               reply_to="anna@example.com", mid="<form1@web>")
    eh.abgleichen(con)
    n = con.execute("SELECT * FROM email_nachrichten WHERE message_id='<form1@web>'").fetchone()
    assert n["anfrage_id"] and "<form1@web>" in links(con, anna)


def test_seite_einstellungen_loeschen_datenschutz(con, client, eingerichtet):
    anna, firma = eingerichtet
    post(client, "/einstellungen/historie/abrufen")
    assert con.execute("SELECT COUNT(*) FROM email_nachrichten").fetchone()[0] == 4
    einst = dbm.einstellungen(con)
    assert einst["historie_letzter_abruf"] and not einst["historie_letzter_fehler"]
    # Protokoll enthält nur Anzahlen, keine Betreffs oder Adressen
    texte = " ".join(r[0] or "" for r in con.execute("SELECT details FROM protokoll WHERE aktion LIKE 'email_hist%'"))
    assert "Display" not in texte and "anna@" not in texte and "news@" not in texte
    seite = client.get(f"/kunden/{anna}").get_data(as_text=True)
    assert "Display kaputt" in seite and "Rechnung.pdf" in seite
    seite = client.get("/einstellungen/anfragen").get_data(as_text=True)
    assert "E-Mail-Historie aktivieren" in seite and "Ordner abrufen" in seite and "letzte 6 Monate" in seite
    # Speichern
    post(client, "/einstellungen/anfragen", historie_aktiv="on", historie_ordner_eingang=" INBOX \n\nArchiv",
         historie_ordner_gesendet="Gesendete Objekte", historie_zeitraum_tage="365", anfragen_intervall_min="5",
         imap_host="imap.ionos.de", imap_port="143", imap_sicherheit="starttls", imap_ordner="INBOX",
         imap_zielordner="Anfragen erledigt", anfrage_schwelle_unsicher="2", anfrage_schwelle_spam="5",
         anfrage_namensreihenfolge="auto", interessent_loeschen_monate="6")
    e = dbm.einstellungen(con)
    assert e["historie_ordner_eingang"] == "INBOX\nArchiv" and e["historie_zeitraum_tage"] == 365
    # Kunde löschen → seine Mails weg, geteilte Mail bleibt beim anderen Kunden
    post(client, f"/kunden/{anna}/loeschen")
    assert not links(con, anna) and links(con, firma) == {"<m3@b>", "<m4@x>"}
    assert not con.execute("SELECT 1 FROM email_nachrichten WHERE message_id='<m1@a>'").fetchone()


def test_fehler_als_hinweis(con, eingerichtet, monkeypatch):
    class Kaputt(Postfach):
        def login(self, b, p):
            import imaplib
            raise imaplib.IMAP4.error("AUTHENTICATIONFAILED")
    monkeypatch.setattr("imaplib.IMAP4_SSL", Kaputt)
    e, fehler = eh.abgleich_mit_protokoll(con)
    assert e is None and "Anmeldung" in fehler
    assert "Anmeldung" in dbm.einstellungen(con)["historie_letzter_fehler"]
    # fehlender Ordner bricht nicht ab
    monkeypatch.setattr("imaplib.IMAP4_SSL", Postfach)
    with dbm.Transaktion(con):
        dbm.einstellungen_speichern({"historie_ordner_eingang": "Gibtsnicht\nINBOX"}, con)
    e, fehler = eh.abgleich_mit_protokoll(con)
    assert e["neu"] == 4 and "Gibtsnicht" in fehler


def test_adressen_normalisieren():
    assert eh.adresse_normal("  Anna Müller <Anna@Web.DE> ") == "anna@web.de"
    assert eh.adressen_aus_text("a@b.de; Max <MAX@b.de>\nc@d.de, a@b.de") == ["a@b.de", "max@b.de", "c@d.de"]
    assert eh.adresse_normal("kein-name") == ""


def test_uid_nach_inhalt_und_datum():
    class Server:
        def uid(self, *a):
            return "OK", [(b"1 (BODY[HEADER.FIELDS (FROM)] {20}", b"From: a@b.de\r\n\r\n"), b" UID 42)"]
    k = eh._kopfzeilen_laden(Server(), [42])
    assert list(k) == [42] and k[42]["From"] == "a@b.de"
    assert eh.imap_datum(datetime(2026, 10, 5)) == "05-Oct-2026"
