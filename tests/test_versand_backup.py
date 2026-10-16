import zipfile
from pathlib import Path

from rsb import db as dbm
from rsb.backup import backup_erstellen
from rsb.sicherheit import entschluesseln

from conftest import kunde_anlegen, post, rechnung_anlegen


class FalscherServer:
    gesendet = []

    def __init__(self, host, port, timeout=None, **kw):
        self.host = host

    def starttls(self, context=None):
        pass

    def login(self, user, pw):
        FalscherServer.login_daten = (user, pw)

    def send_message(self, msg):
        FalscherServer.gesendet.append(msg)

    def quit(self):
        pass


def test_email_versand_mit_protokoll(client, con, app, monkeypatch):
    monkeypatch.setattr("rsb.mail.smtplib.SMTP", FalscherServer)
    post(client, "/einstellungen/email", smtp_host="smtp.example.com", smtp_port="587",
         smtp_sicherheit="starttls", smtp_benutzer="kontakt@reparatur-bredin.de", smtp_passwort="SuperGeheim!",
         absender_name="Reparatur Service Bredin", absender_email="kontakt@reparatur-bredin.de", bcc_an_mich="on")
    gespeichert = dbm.einstellungen(con)["smtp_passwort_enc"]
    assert gespeichert and "SuperGeheim" not in gespeichert  # verschlüsselt gespeichert
    with app.app_context():
        assert entschluesseln(gespeichert) == "SuperGeheim!"

    kid = kunde_anlegen(client)
    did = rechnung_anlegen(client, kid, festschreiben=True)
    seite = client.get(f"/dokumente/{did}/email").get_data(as_text=True)
    assert "Ihre Rechnung RE-" in seite
    r = post(client, f"/dokumente/{did}/email", an="anna@example.com", betreff="Ihre Rechnung", text="Hallo")
    assert r.status_code == 302
    msg = FalscherServer.gesendet[-1]
    assert msg["To"] == "anna@example.com" and msg["Bcc"] == "kontakt@reparatur-bredin.de"
    anhang = next(msg.iter_attachments())
    nummer = con.execute("SELECT nummer FROM dokumente WHERE id=?", (did,)).fetchone()[0]
    assert anhang.get_filename() == f"{nummer}.pdf"
    assert FalscherServer.login_daten == ("kontakt@reparatur-bredin.de", "SuperGeheim!")
    v = con.execute("SELECT * FROM versandprotokoll").fetchone()
    assert v["status"] == "gesendet" and v["anhang_sha256"]
    assert con.execute("SELECT versendet_am FROM dokumente WHERE id=?", (did,)).fetchone()[0]


def test_email_fehler_wird_protokolliert(client, con):
    kid = kunde_anlegen(client)
    did = rechnung_anlegen(client, kid, festschreiben=True)
    post(client, f"/dokumente/{did}/email", an="anna@example.com", betreff="x", text="y")
    v = con.execute("SELECT * FROM versandprotokoll").fetchone()
    assert v["status"] == "fehler" and "kein E-Mail-Server" in v["fehlermeldung"]


def test_backup(client, con, app, tmp_path):
    kid = kunde_anlegen(client)
    rechnung_anlegen(client, kid, festschreiben=True)
    nas = tmp_path / "NAS"
    ziel, extern = backup_erstellen(app.config["DATEN"], app.config["DB_PFAD"],
                                    {"backup_ziel": str(nas), "backup_behalten": 5})
    assert Path(extern).is_file()
    namen = zipfile.ZipFile(ziel).namelist()
    assert "werkstatt.db" in namen
    assert any(n.startswith("dokumente/") and n.endswith(".pdf") for n in namen)
    assert not any("schluessel" in n for n in namen)  # Schlüssel nicht im Backup
