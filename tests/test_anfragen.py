import email
import json
from email.message import EmailMessage

import pytest

from rsb import anfragen as anf
from rsb import db as dbm
from rsb.sicherheit import verschluesseln

from conftest import kunde_anlegen, post, rechnung_anlegen

IONOS_HTML = """<html><head><style>p{{color:#333}}</style></head><body><div class="card">
<p>Hello,</p><p>A new form has been submitted on your website. Details below.</p>
<p><strong>Name</strong></p><p>{name}</p>
<p><strong>Telefon</strong></p><p><a href="tel:{tel}">{tel}</a></p>
<p><strong>Email</strong></p><p><a href="mailto:{mail}">{mail}</a></p>
<p><strong>Geraet</strong></p><p>{geraet}</p>
<p><strong>Nachricht</strong></p><p>{nachricht}</p></div></body></html>"""


def formular_mail(name="Kochendörfer Kai", tel="+491719879253", mail="kai.kochendoerfer@t-online.de",
                  geraet="Smartphone / Tablet", nachricht="Display gesprungen<br>Xiaomi 14T Pro", msgid="<a1@ionos>"):
    m = EmailMessage()
    m["From"] = "IONOS <noreply@website.ionos.example>"
    m["To"] = "kontakt@reparatur-bredin.de"
    m["Subject"] = "Neue Formularanfrage"
    m["Message-ID"] = msgid
    m["Date"] = "Wed, 14 Oct 2026 10:15:00 +0200"
    m.set_content("Bitte HTML-Ansicht verwenden")
    m.add_alternative(IONOS_HTML.format(name=name, tel=tel, mail=mail, geraet=geraet, nachricht=nachricht),
                      subtype="html")
    return m


def text_aus(m):
    return anf.mail_text(email.message_from_bytes(m.as_bytes(), policy=email.policy.default))


def test_ionos_formular_wird_gelesen():
    felder = anf.felder_auslesen(text_aus(formular_mail()))
    assert felder == {"name": "Kochendörfer Kai", "telefon": "+491719879253",
                      "email": "kai.kochendoerfer@t-online.de", "geraet": "Smartphone / Tablet",
                      "nachricht": "Display gesprungen\nXiaomi 14T Pro"}


def test_doppelpunkt_variante():
    felder = anf.felder_auslesen("Name: Max Muster\nE-Mail: max@example.com\nNachricht: Akku leer\nbitte melden")
    assert felder["name"] == "Max Muster" and felder["email"] == "max@example.com"
    assert felder["nachricht"] == "Akku leer\nbitte melden"


@pytest.mark.parametrize("name,erwartet", [
    ("Kochendörfer Kai", ("Kai", "Kochendörfer")),
    ("Kai Kochendörfer", ("Kai", "Kochendörfer")),
    ("Müller, Anna", ("Anna", "Müller")),
    ("Anna Maria Schmidt", ("Anna Maria", "Schmidt")),
    ("Schmidt", ("", "Schmidt")),
])
def test_namen(name, erwartet):
    assert anf.name_aufteilen(name) == erwartet


def bew(**f):
    return anf.bewerten(f)[2]


def test_bewertung():
    assert bew(name="Kochendörfer Kai", telefon="+491719879253", email="kai@t-online.de", geraet="Smartphone / Tablet",
               nachricht="Display gesprungen Xiaomi 14T Pro") == "echt"
    assert bew(name="Erika", email="erika@web.de", geraet="Kaffeemaschine",
               nachricht="Meine Jura E8 zieht kein Wasser mehr, was kostet eine Reparatur?") == "echt"
    # SEO-Spam auf Englisch mit Link
    assert bew(name="John Smith", email="john@seo-agency.com", telefon="12345",
               nachricht="Hello, we can bring your website to the first page of Google. Our SEO services and "
                         "backlinks are the best. Visit https://best-seo.example.com for a free trial.") == "spam"
    # Zeichensalat
    assert bew(name="asdf", email="asdf@asdf", telefon="123", nachricht="sdfghjk qwertz") == "spam"
    # Kyrillisch
    assert bew(name="Иван", email="ivan@mail.ru", nachricht="Здравствуйте, предлагаем услуги продвижения сайта") == "spam"
    # knapp, aber plausibel -> nicht automatisch, sondern prüfen
    assert bew(name="Tom", email="tom@gmx.de", nachricht="Hallo") == "unsicher"


def test_verarbeitung_legt_interessent_an_und_keine_dubletten(app, con):
    einst = dbm.einstellungen(con)
    aid = anf.verarbeiten(con, text_aus(formular_mail()), einst, message_id="<a1>")
    a = con.execute("SELECT * FROM anfragen WHERE id=?", (aid,)).fetchone()
    assert a["einstufung"] == "echt" and a["status"] == "kunde_angelegt"
    k = con.execute("SELECT * FROM kunden WHERE id=?", (a["kunde_id"],)).fetchone()
    assert (k["vorname"], k["nachname"], k["interessent"], k["quelle"]) == ("Kai", "Kochendörfer", 1, "Kontaktformular")
    assert "Display gesprungen" in k["notizen"]
    # gleiche E-Mail nochmal -> nichts doppelt
    assert anf.verarbeiten(con, text_aus(formular_mail()), einst, message_id="<a1>") is None
    # neue Anfrage desselben Kunden (andere Schreibweise der Nummer) -> zugeordnet, kein neuer Kunde
    aid2 = anf.verarbeiten(con, text_aus(formular_mail(tel="0171 9879253", mail="anders@example.com",
                                                       nachricht="Akku hält nicht mehr")), einst, message_id="<a2>")
    assert con.execute("SELECT status FROM anfragen WHERE id=?", (aid2,)).fetchone()[0] == "zugeordnet"
    assert con.execute("SELECT COUNT(*) FROM kunden").fetchone()[0] == 1


def test_spam_legt_keinen_kunden_an(app, con):
    text = text_aus(formular_mail(name="Best SEO", mail="x@mailinator.com", tel="1",
                                  nachricht="We offer SEO and backlinks, visit www.seo.example.com"))
    aid = anf.verarbeiten(con, text, dbm.einstellungen(con), message_id="<s1>")
    a = con.execute("SELECT * FROM anfragen WHERE id=?", (aid,)).fetchone()
    assert a["einstufung"] == "spam" and a["kunde_id"] is None
    assert con.execute("SELECT COUNT(*) FROM kunden").fetchone()[0] == 0


def test_rechnung_macht_aus_interessent_kunden(client, con, app):
    aid = anf.verarbeiten(con, text_aus(formular_mail()), dbm.einstellungen(con), message_id="<a1>")
    kid = con.execute("SELECT kunde_id FROM anfragen WHERE id=?", (aid,)).fetchone()[0]
    rechnung_anlegen(client, kid, festschreiben=True)
    assert con.execute("SELECT interessent FROM kunden WHERE id=?", (kid,)).fetchone()[0] == 0


class FalschesImap:
    postfach = {}
    verschoben = []
    angemeldet = None

    def __init__(self, host, port, ssl_context=None, timeout=None):
        self.host = host

    def login(self, user, pw):
        FalschesImap.angemeldet = (user, pw)

    def select(self, ordner):
        return "OK", [b"1"]

    def uid(self, befehl, *args):
        if befehl == "SEARCH":
            return "OK", [b" ".join(self.postfach)]
        if befehl == "FETCH":
            return "OK", [(b"1 (BODY[] {123}", self.postfach[args[0]]), b")"]
        if befehl == "COPY":
            FalschesImap.verschoben.append((args[0], args[1]))
            return "OK", []
        return "OK", []

    def create(self, ordner):
        return "NO", []

    def expunge(self):
        pass

    def logout(self):
        pass


def test_imap_abruf(app, con):
    andere = EmailMessage()
    andere["Subject"] = "Newsletter"
    andere["Message-ID"] = "<n1>"
    andere.set_content("Ganz normale E-Mail")
    FalschesImap.postfach = {b"1": formular_mail().as_bytes(), b"2": andere.as_bytes(),
                             b"3": formular_mail(name="qwertz", mail="a@b", tel="1", nachricht="asdfgh",
                                                 msgid="<x9>").as_bytes()}
    FalschesImap.verschoben = []
    with app.app_context():
        with dbm.Transaktion(con):
            dbm.einstellungen_speichern({"imap_benutzer": "kontakt@reparatur-bredin.de",
                                         "imap_passwort_enc": verschluesseln("geheim")}, con)
        ergebnis = anf.abrufen(con, dbm.einstellungen(con), imap_klasse=FalschesImap)
        assert ergebnis["neu"] == 2 and ergebnis["echt"] == 1 and ergebnis["spam"] == 1
        assert [u for u, _ in FalschesImap.verschoben] == [b"1", b"3"]  # Newsletter bleibt unberührt
        assert FalschesImap.angemeldet == ("kontakt@reparatur-bredin.de", "geheim")
        # zweiter Abruf: nichts doppelt
        assert anf.abrufen(con, dbm.einstellungen(con), imap_klasse=FalschesImap)["neu"] == 0


def test_imap_ohne_zugangsdaten(app, con):
    with app.app_context(), pytest.raises(anf.AbrufFehler):
        anf.abrufen(con, dbm.einstellungen(con))


def test_oberflaeche(client, con):
    r = post(client, "/anfragen/einfuegen", text="Name\nMüller Anna\nTelefon\n0171 1234567\nEmail\nanna@web.de\n"
                                                  "Geraet\nKaffeemaschine\nNachricht\nJura entkalken bitte")
    assert r.status_code == 302
    aid = int(r.headers["Location"].rsplit("/", 1)[1])
    a = con.execute("SELECT * FROM anfragen WHERE id=?", (aid,)).fetchone()
    assert a["einstufung"] == "echt" and a["kunde_id"]
    for url in ["/anfragen", "/anfragen?filter=spam", f"/anfragen/{aid}", "/anfragen/einfuegen",
                "/einstellungen/anfragen", f"/kunden/{a['kunde_id']}", "/kunden?interessenten=1", "/"]:
        assert client.get(url).status_code == 200, url
    # unsichere Anfrage manuell übernehmen mit korrigiertem Namen
    r = post(client, "/anfragen/einfuegen", text="Name\nTom\nEmail\ntom@gmx.de\nNachricht\nHallo")
    aid2 = int(r.headers["Location"].rsplit("/", 1)[1])
    assert con.execute("SELECT einstufung FROM anfragen WHERE id=?", (aid2,)).fetchone()[0] == "unsicher"
    post(client, f"/anfragen/{aid2}/aktion", aktion="kunde", vorname="Tom", nachname="Becker")
    k = con.execute("SELECT k.* FROM kunden k JOIN anfragen a ON a.kunde_id=k.id WHERE a.id=?", (aid2,)).fetchone()
    assert (k["vorname"], k["nachname"]) == ("Tom", "Becker")
    # Speichern in Einstellungen
    r = post(client, "/einstellungen/anfragen", anfragen_aktiv="on", anfragen_intervall_min="5",
             imap_host="imap.ionos.de", imap_port="993", imap_benutzer="", imap_ordner="INBOX",
             imap_zielordner="Anfragen erledigt", imap_verschieben="on", anfrage_erkennung="A new form",
             anfrage_auto_kunde="on", anfrage_schwelle_unsicher="2", anfrage_schwelle_spam="5",
             anfrage_namensreihenfolge="auto", interessent_loeschen_monate="6", imap_passwort="pw")
    assert dbm.einstellungen(con)["anfragen_aktiv"] is True
    assert dbm.einstellungen(con)["imap_passwort_enc"]
