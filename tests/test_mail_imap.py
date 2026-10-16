import email
import imaplib
import smtplib

import pytest

from rsb import db as dbm
from rsb import imap_ablage
from rsb.mail import MailFehler, senden, smtp_ziel
from rsb.sicherheit import verschluesseln

from conftest import kunde_anlegen, post, rechnung_anlegen


class FalscherSmtp:
    gesendet = []

    def __init__(self, host, port, timeout=None, **kw):
        FalscherSmtp.verbunden = (host, port, timeout)

    def starttls(self, context=None):
        pass

    def login(self, u, p):
        pass

    def send_message(self, msg):
        FalscherSmtp.gesendet.append(msg)

    def quit(self):
        pass


class FalschesImap:
    """Simuliert einen IMAP-Server (IONOS-ähnlich)."""
    passwort = "geheim"
    ordner = [b'(\\HasNoChildren) "/" "INBOX"', b'(\\HasNoChildren \\Sent) "/" "Gesendete Objekte"',
              b'(\\HasNoChildren \\Trash) "/" "Gel&APY-schte Objekte"', b'(\\Noselect \\HasChildren) "/" "Archiv"',
              (b'(\\HasNoChildren) "/" {10}', b'Rechnungen')]
    abgelegt = []
    fehler_bei_append = False

    def __init__(self, host, port, ssl_context=None, timeout=None):
        if host == "nicht.erreichbar":
            raise ConnectionRefusedError(10061, "Zielcomputer verweigerte die Verbindung")
        FalschesImap.timeout = timeout

    def login(self, u, p):
        if p != self.passwort:
            raise imaplib.IMAP4.error("AUTHENTICATIONFAILED")

    def list(self):
        return "OK", self.ordner

    def select(self, name, readonly=False):
        return ("OK", [b"1"]) if name in ('"Gesendete Objekte"', '"Gel&APY-schte Objekte"') else ("NO", [b"x"])

    def append(self, ordner, flags, datum, daten):
        if FalschesImap.fehler_bei_append:
            return "NO", [b"[TRYCREATE] Mailbox does not exist"]
        FalschesImap.abgelegt.append((ordner, flags, daten))
        return "OK", [b"APPEND completed"]

    def logout(self):
        pass


@pytest.fixture
def mailserver(monkeypatch):
    FalscherSmtp.gesendet = []
    FalschesImap.abgelegt = []
    FalschesImap.fehler_bei_append = False
    monkeypatch.setattr("rsb.mail.smtplib.SMTP", FalscherSmtp)
    monkeypatch.setattr("rsb.imap_ablage.imaplib.IMAP4_SSL", FalschesImap)


def einrichten(con, **mehr):
    with dbm.Transaktion(con):
        dbm.einstellungen_speichern({"smtp_host": "smtp.ionos.de", "smtp_port": 587, "smtp_sicherheit": "starttls",
                                     "smtp_benutzer": "kontakt@reparatur-bredin.de",
                                     "smtp_passwort_enc": verschluesseln("geheim"),
                                     "absender_email": "kontakt@reparatur-bredin.de", "gesendet_aktiv": True,
                                     "gesendet_imap_host": "imap.ionos.de", "gesendet_ordner": "Gesendete Objekte",
                                     **mehr}, con)


def test_utf7_ordnernamen():
    for klar, kodiert in [("Gelöschte Objekte", "Gel&APY-schte Objekte"), ("Entwürfe", "Entw&APw-rfe"),
                          ("A & B", "A &- B"), ("Gesendete Objekte", "Gesendete Objekte")]:
        assert imap_ablage.utf7_kodieren(klar) == kodiert
        assert imap_ablage.utf7_dekodieren(kodiert) == klar


def test_ordner_auflisten():
    ordner = imap_ablage.ordner_auflisten(FalschesImap("imap.ionos.de", 993))
    namen = [o["name"] for o in ordner]
    assert namen[0] == "Gesendete Objekte" and ordner[0]["gesendet"]  # Gesendet-Ordner zuerst
    assert "Gelöschte Objekte" in namen and "Rechnungen" in namen and "Archiv" not in namen


def test_versand_mit_ablage_im_gesendet_ordner(app, con, mailserver):
    with app.app_context():
        einrichten(con)
        hinweis = senden(con, None, "kunde@example.com", "Ihre Rechnung", "Hallo", b"%PDF-1.4 test", "RE-1.pdf")
    assert hinweis is None
    assert len(FalscherSmtp.gesendet) == 1 and FalscherSmtp.verbunden == ("smtp.ionos.de", 587, 20)
    ordner, flags, daten = FalschesImap.abgelegt[0]
    assert ordner == '"Gesendete Objekte"' and flags == r"(\Seen)" and FalschesImap.timeout == 20
    kopie = email.message_from_bytes(daten)
    gesendet = FalscherSmtp.gesendet[0]
    assert kopie["Message-ID"] == gesendet["Message-ID"] and kopie["Date"]
    assert [t.get_filename() for t in kopie.walk() if t.get_filename()] == ["RE-1.pdf"]
    v = con.execute("SELECT * FROM versandprotokoll").fetchone()
    assert v["status"] == "gesendet" and v["ablage"] == "abgelegt"


def test_ablage_fehler_mail_gilt_als_gesendet(app, con, mailserver):
    FalschesImap.fehler_bei_append = True
    with app.app_context():
        einrichten(con)
        hinweis = senden(con, None, "kunde@example.com", "Test", "Hallo")
    assert "E-Mail wurde gesendet, konnte aber nicht im Gesendet-Ordner abgelegt werden" in hinweis
    assert len(FalscherSmtp.gesendet) == 1  # NICHT erneut gesendet
    v = con.execute("SELECT * FROM versandprotokoll").fetchone()
    assert v["status"] == "gesendet" and v["ablage"].startswith("fehler")
    assert con.execute("SELECT 1 FROM protokoll WHERE aktion='email_ablage_fehler'").fetchone()


def test_ablage_fehler_in_oberflaeche_gelber_hinweis(client, con, mailserver):
    FalschesImap.passwort = "anders"
    try:
        with client.application.app_context():
            einrichten(con)
        kid = kunde_anlegen(client)
        did = rechnung_anlegen(client, kid, festschreiben=True)
        r = client.post(f"/dokumente/{did}/email", data={"csrf": "test-token", "an": "anna@example.com",
                                                          "betreff": "x", "text": "y"}, follow_redirects=True)
        seite = r.get_data(as_text=True)
        assert "E-Mail an anna@example.com wurde gesendet" in seite
        assert 'meldung warnung' in seite and "Gesendet-Ordner" in seite and "Passwort ist falsch" in seite
    finally:
        FalschesImap.passwort = "geheim"


def test_smtp_einstellungen_werden_geprueft(app, con, monkeypatch):
    with pytest.raises(MailFehler, match="kein E-Mail-Server"):
        smtp_ziel({"smtp_host": "", "smtp_port": 587})
    with pytest.raises(MailFehler, match="ungültig"):
        smtp_ziel({"smtp_host": "localhost", "smtp_port": 587})
    with pytest.raises(MailFehler, match="Port"):
        smtp_ziel({"smtp_host": "smtp.ionos.de", "smtp_port": None})
    # ohne gespeicherte Einstellungen: klare Meldung, kein Verbindungsversuch
    aufgerufen = []
    monkeypatch.setattr("rsb.mail.smtplib.SMTP", lambda *a, **k: aufgerufen.append(a))
    with app.app_context(), pytest.raises(MailFehler, match="kein E-Mail-Server"):
        senden(con, {"smtp_host": "localhost"}, "a@b.de", "x", "y")  # übergebene Werte überschreiben nichts
    assert aufgerufen == []


def test_verbindung_abgelehnt_ein_zweiter_versuch(app, con, monkeypatch):
    versuche = []

    def abgelehnt(host, port, timeout=None):
        versuche.append((host, port, timeout))
        raise ConnectionRefusedError(10061, "Zielcomputer verweigerte die Verbindung")

    monkeypatch.setattr("rsb.mail.smtplib.SMTP", abgelehnt)
    monkeypatch.setattr("rsb.mail.time.sleep", lambda s: None)
    with app.app_context():
        einrichten(con, gesendet_aktiv=False)
        with pytest.raises(MailFehler, match="smtp.ionos.de:587"):
            senden(con, None, "a@b.de", "x", "y")
    assert versuche == [("smtp.ionos.de", 587, 20)] * 2


def test_einstellungen_imap_ordner_und_test(client, con, mailserver):
    basis = {"gesendet_imap_host": "imap.ionos.de", "gesendet_imap_port": "993", "gesendet_imap_sicherheit": "ssl",
             "gesendet_gleiche_zugangsdaten": "on", "smtp_benutzer": "kontakt@reparatur-bredin.de",
             "smtp_passwort": "geheim", "gesendet_ordner": ""}
    j = client.post("/einstellungen/imap-ordner", data={"csrf": "test-token", **basis}).get_json()
    assert j["ok"] and j["ordner"][0]["name"] == "Gesendete Objekte"
    j = client.post("/einstellungen/imap-test", data={"csrf": "test-token", **basis,
                                                       "gesendet_ordner": "Gesendete Objekte"}).get_json()
    assert j["ok"] and "erfolgreich" in j["meldung"]
    j = client.post("/einstellungen/imap-test", data={"csrf": "test-token", **basis, "gesendet_ordner": "Sent"}).get_json()
    assert not j["ok"] and "gibt es nicht" in j["meldung"]
    j = client.post("/einstellungen/imap-test", data={"csrf": "test-token", **basis, "smtp_passwort": "falsch"}).get_json()
    assert not j["ok"] and "Passwort ist falsch" in j["meldung"]
    j = client.post("/einstellungen/imap-test", data={"csrf": "test-token", **basis,
                                                       "gesendet_imap_host": "nicht.erreichbar"}).get_json()
    assert not j["ok"] and "nicht erreichbar" in j["meldung"]
    # Speichern inkl. eigenem, verschlüsseltem IMAP-Passwort
    post(client, "/einstellungen/email", smtp_host="smtp.ionos.de", smtp_port="587", smtp_sicherheit="starttls",
         smtp_benutzer="kontakt@reparatur-bredin.de", absender_name="RSB", absender_email="kontakt@reparatur-bredin.de",
         gesendet_aktiv="on", gesendet_imap_host="imap.ionos.de", gesendet_imap_port="993",
         gesendet_imap_sicherheit="ssl", gesendet_imap_benutzer="ich@ionos.de", gesendet_imap_passwort="PW123",
         gesendet_ordner="Gesendete Objekte")
    e = dbm.einstellungen(con)
    assert e["gesendet_aktiv"] is True and e["gesendet_gleiche_zugangsdaten"] is False
    assert e["gesendet_imap_passwort_enc"] and "PW123" not in e["gesendet_imap_passwort_enc"]
    assert client.get("/einstellungen/email").status_code == 200
