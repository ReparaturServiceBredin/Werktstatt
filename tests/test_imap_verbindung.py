"""IMAP-Verbindung: SSL/TLS oder STARTTLS, nie Anmeldung ohne Verschlüsselung, verständliche Fehler."""
import imaplib
import socket
import ssl
import threading

import pytest

from rsb import anfragen as anf
from rsb import db as dbm
from rsb.imap_verbindung import IMAP_FEHLER, ImapFehler, verbinden
from rsb.sicherheit import verschluesseln

from conftest import post


class Protokoll:
    schritte = []


class FalschesSsl:
    def __init__(self, host, port, ssl_context=None, timeout=None):
        assert isinstance(ssl_context, ssl.SSLContext) and timeout == 20
        Protokoll.schritte.append(("ssl", host, port))

    def login(self, b, p):
        Protokoll.schritte.append(("login", b))

    def select(self, ordner, readonly=False):
        Protokoll.schritte.append(("select", ordner))
        return ("OK", [b"1"]) if ordner in ('"INBOX"', '"Anfragen erledigt"') else ("NO", [b"nicht da"])

    def logout(self):
        Protokoll.schritte.append(("logout",))


class FalschesPlain(FalschesSsl):
    starttls_fehler = None

    def __init__(self, host, port, timeout=None):
        assert timeout == 20
        Protokoll.schritte.append(("plain", host, port))

    def starttls(self, ssl_context=None):
        assert isinstance(ssl_context, ssl.SSLContext)
        if FalschesPlain.starttls_fehler:
            raise FalschesPlain.starttls_fehler
        Protokoll.schritte.append(("starttls",))


@pytest.fixture(autouse=True)
def zuruecksetzen():
    Protokoll.schritte = []
    FalschesPlain.starttls_fehler = None


def test_ssl_und_starttls_reihenfolge():
    verbinden("imap.ionos.de", 993, "ssl", "u", "p", imap_ssl=FalschesSsl, imap_plain=FalschesPlain)
    assert Protokoll.schritte == [("ssl", "imap.ionos.de", 993), ("login", "u")]
    Protokoll.schritte = []
    verbinden("imap.ionos.de", 143, "starttls", "u", "p", imap_ssl=FalschesSsl, imap_plain=FalschesPlain)
    assert Protokoll.schritte == [("plain", "imap.ionos.de", 143), ("starttls",), ("login", "u")]


def test_starttls_fehler_keine_anmeldung():
    FalschesPlain.starttls_fehler = imaplib.IMAP4.error("STARTTLS extension not supported by server.")
    with pytest.raises(ImapFehler) as e:
        verbinden("imap.ionos.de", 143, "starttls", "u", "p", imap_ssl=FalschesSsl, imap_plain=FalschesPlain)
    assert "nicht unverschlüsselt angemeldet" in str(e.value)
    assert ("login", "u") not in Protokoll.schritte and ("logout",) in Protokoll.schritte
    FalschesPlain.starttls_fehler = ssl.SSLError(1, "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed")
    with pytest.raises(ImapFehler) as e:
        verbinden("imap.ionos.de", 143, "starttls", "u", "p", imap_ssl=FalschesSsl, imap_plain=FalschesPlain)
    assert "STARTTLS fehlgeschlagen" in str(e.value) and "Sicherheitszertifikat" in str(e.value)
    assert ("login", "u") not in Protokoll.schritte


def test_fehler_uebersetzt():
    def wirft(fehler):
        class K:
            def __init__(self, *a, **k):
                raise fehler
        return K
    with pytest.raises(ImapFehler, match=r"Port und Verschlüsselung passen nicht zusammen \(993 = SSL, 143 = STARTTLS\)"):
        verbinden("imap.ionos.de", 143, "ssl", "u", "p",
                  imap_ssl=wirft(ssl.SSLError(1, "[SSL: WRONG_VERSION_NUMBER] wrong version number (_ssl.c:1000)")))
    with pytest.raises(ImapFehler, match="nicht gefunden"):
        verbinden("imap.gibtsnicht.de", 993, "ssl", "u", "p", imap_ssl=wirft(socket.gaierror(11001, "getaddrinfo")))
    with pytest.raises(ImapFehler, match="Zeitüberschreitung.*STARTTLS mit Port 143"):
        verbinden("imap.ionos.de", 993, "ssl", "u", "p", imap_ssl=wirft(TimeoutError("timed out")))
    with pytest.raises(ImapFehler, match="Port und Verschlüsselung passen nicht"):
        verbinden("imap.ionos.de", 993, "starttls", "u", "p", imap_plain=wirft(TimeoutError("timed out")))
    with pytest.raises(ImapFehler, match="Verschlüsselung"):
        verbinden("imap.ionos.de", 993, "keine", "u", "p")


# ------------------------------------------------------------- echter Netzwerk-Test mit Mini-IMAP-Server

class MiniImap:
    """Unverschlüsselter IMAP-Server ohne STARTTLS – merkt sich, ob ein LOGIN ankam."""

    def __init__(self):
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.2", 0))  # 127.0.0.1 lehnt die Einstellungsprüfung bewusst ab
        self.sock.listen(5)
        self.port = self.sock.getsockname()[1]
        self.login_empfangen = False
        threading.Thread(target=self._laufen, daemon=True).start()

    def _laufen(self):
        while True:
            try:
                verb, _ = self.sock.accept()
            except OSError:
                return
            threading.Thread(target=self._sitzung, args=(verb,), daemon=True).start()

    def _sitzung(self, verb):
        try:
            verb.sendall(b"* OK Mini IMAP bereit\r\n")
            datei = verb.makefile("rb")
            for zeile in datei:
                teile = zeile.decode("latin-1").strip().split(" ", 2)
                if len(teile) < 2:
                    break
                tag, befehl = teile[0], teile[1].upper()
                if befehl == "CAPABILITY":
                    verb.sendall(b"* CAPABILITY IMAP4rev1 AUTH=PLAIN\r\n" + tag.encode() + b" OK fertig\r\n")
                elif befehl == "LOGIN":
                    self.login_empfangen = True
                    verb.sendall(tag.encode() + b" OK angemeldet\r\n")
                elif befehl == "LOGOUT":
                    verb.sendall(b"* BYE\r\n" + tag.encode() + b" OK\r\n")
                    break
                else:
                    verb.sendall(tag.encode() + b" BAD unbekannt\r\n")
        except OSError:
            pass
        finally:
            verb.close()

    def schliessen(self):
        self.sock.close()


@pytest.fixture
def mini():
    s = MiniImap()
    yield s
    s.schliessen()


def test_echt_ssl_auf_klartext_port(mini):
    """Genau der gemeldete Fehler: SSL auf einen Port, der kein SSL spricht (wie 143)."""
    with pytest.raises(ImapFehler) as e:
        verbinden("127.0.0.2", mini.port, "ssl", "u", "p")
    assert "Port und Verschlüsselung passen nicht zusammen" in str(e.value), str(e.value)
    assert not mini.login_empfangen


def test_echt_server_ohne_starttls_keine_anmeldung(mini):
    with pytest.raises(ImapFehler) as e:
        verbinden("127.0.0.2", mini.port, "starttls", "u", "p")
    assert "kein STARTTLS" in str(e.value)
    assert not mini.login_empfangen  # Passwort wurde nie unverschlüsselt gesendet


# ------------------------------------------------------------- Einstellungen, Abruf, Test-Knopf

def test_migration_imap_sicherheit(tmp_path):
    for port, erwartet in [(143, "starttls"), (993, "ssl"), (1143, "starttls")]:
        pfad = tmp_path / f"db{port}.db"
        dbm.initialisieren(str(pfad))
        con = dbm.verbinden(str(pfad))
        con.execute("DELETE FROM einstellungen WHERE schluessel='imap_sicherheit'")
        con.execute("UPDATE einstellungen SET wert=? WHERE schluessel='imap_port'", (str(port),))
        con.close()
        dbm.initialisieren(str(pfad))
        con = dbm.verbinden(str(pfad))
        assert dbm.einstellungen(con)["imap_sicherheit"] == erwartet, port
        con.close()


def test_abruf_nutzt_starttls(app, con):
    with app.app_context():
        with dbm.Transaktion(con):
            dbm.einstellungen_speichern({"imap_port": 143, "imap_sicherheit": "starttls", "imap_benutzer": "k@r.de",
                                         "imap_passwort_enc": verschluesseln("geheim"), "imap_verschieben": False},
                                        con)

        class Abruf(FalschesPlain):
            def uid(self, *a):
                return "OK", [b""]
        anf.abrufen(con, dbm.einstellungen(con), imap_klasse=FalschesSsl, imap_plain=Abruf)
    assert Protokoll.schritte[:3] == [("plain", "imap.ionos.de", 143), ("starttls",), ("login", "k@r.de")]


def test_knopf_verbindung_testen(client, con, monkeypatch):
    monkeypatch.setattr(imaplib, "IMAP4", FalschesPlain)
    monkeypatch.setattr(imaplib, "IMAP4_SSL", FalschesSsl)
    basis = {"csrf": "test-token", "imap_host": "imap.ionos.de", "imap_port": "143", "imap_sicherheit": "starttls",
             "imap_benutzer": "k@r.de", "imap_passwort": "pw", "imap_ordner": "INBOX",
             "imap_zielordner": "Anfragen erledigt"}
    j = client.post("/einstellungen/anfragen/imap-test", data=basis).get_json()
    assert j["ok"] and "STARTTLS" in j["meldung"] and "„INBOX“ ist vorhanden" in j["meldung"]
    assert "„Anfragen erledigt“ ist vorhanden" in j["meldung"]
    assert ("starttls",) in Protokoll.schritte
    j = client.post("/einstellungen/anfragen/imap-test", data={**basis, "imap_zielordner": "Gibtsnicht"}).get_json()
    assert not j["ok"] and "„Gibtsnicht“ wurde nicht gefunden" in j["meldung"]
    FalschesPlain.starttls_fehler = IMAP_FEHLER("STARTTLS extension not supported by server.")
    j = client.post("/einstellungen/anfragen/imap-test", data=basis).get_json()
    assert not j["ok"] and "kein STARTTLS" in j["meldung"]
    # Speichern der Auswahl
    post(client, "/einstellungen/anfragen", anfragen_intervall_min="5", imap_host="imap.ionos.de",
         imap_port="143", imap_sicherheit="starttls", imap_ordner="INBOX", imap_zielordner="Anfragen erledigt",
         anfrage_schwelle_unsicher="2", anfrage_schwelle_spam="5", anfrage_namensreihenfolge="auto",
         interessent_loeschen_monate="6")
    assert dbm.einstellungen(con)["imap_sicherheit"] == "starttls"
    seite = client.get("/einstellungen/anfragen").get_data(as_text=True)
    assert "STARTTLS (meist Port 143)" in seite and "Verbindung testen" in seite
