import hashlib
import http.server
import json
import sys
import threading

import pytest

from rsb import update

from conftest import post


@pytest.fixture
def server(tmp_path):
    """Kleiner lokaler Webserver, der wie die GitHub-Releases-API antwortet."""
    inhalt = {"exe": b"NEUE-EXE-VERSION-9.9.0" * 1000}
    inhalt["sha"] = (hashlib.sha256(inhalt["exe"]).hexdigest() + "  Werkstatt-Sauter.exe\n").encode()

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            port = self.server.server_address[1]
            if self.path == "/latest":
                body = json.dumps({"tag_name": "v9.9.0", "body": "- Neu: Test", "assets": [
                    {"name": "Werkstatt-Sauter.exe", "browser_download_url": f"http://127.0.0.1:{port}/exe"},
                    {"name": "Werkstatt-Sauter.exe.sha256", "browser_download_url": f"http://127.0.0.1:{port}/sha"},
                ]}).encode()
            elif self.path == "/exe":
                body = inhalt["exe"]
            elif self.path == "/sha":
                body = inhalt["sha"]
            else:
                self.send_response(404)
                self.end_headers()
                return
            self.send_response(200)
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    httpd = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{httpd.server_address[1]}"
    yield url, inhalt
    httpd.shutdown()


def test_versionsvergleich():
    assert update.ist_neuer("v0.4.1", "0.4.0")
    assert update.ist_neuer("1.0.0", "0.9.9")
    assert update.ist_neuer("0.10.0", "0.9.0")
    assert not update.ist_neuer("0.4.0", "0.4.0 (Auto-Update)")
    assert not update.ist_neuer("0.3.9", "0.4.0")
    assert not update.ist_neuer("", "0.4.0")


def test_installieren_tauscht_exe(server, tmp_path, monkeypatch):
    url, inhalt = server
    monkeypatch.setattr(update, "API_URL", url + "/latest")
    exe = tmp_path / "Werkstatt-Sauter.exe"
    exe.write_bytes(b"ALTE-EXE")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe))
    info = update.neueste_version()
    assert info["version"] == "9.9.0" and info["hinweise"] == "- Neu: Test"
    backup = []
    update.installieren(info, vor_austausch=lambda: backup.append(True))
    assert exe.read_bytes() == inhalt["exe"]
    assert (tmp_path / "Werkstatt-Sauter.alt.exe").read_bytes() == b"ALTE-EXE"
    assert backup == [True]
    update.alte_versionen_aufraeumen()
    assert not (tmp_path / "Werkstatt-Sauter.alt.exe").exists()


def test_falsche_pruefsumme_bricht_ab(server, tmp_path, monkeypatch):
    url, inhalt = server
    inhalt["sha"] = b"0" * 64
    monkeypatch.setattr(update, "API_URL", url + "/latest")
    exe = tmp_path / "Werkstatt-Sauter.exe"
    exe.write_bytes(b"ALTE-EXE")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe))
    with pytest.raises(update.UpdateFehler, match="Prüfsumme"):
        update.installieren(update.neueste_version())
    assert exe.read_bytes() == b"ALTE-EXE"
    assert list(tmp_path.iterdir()) == [exe]


def test_nicht_als_exe_kein_update(server, monkeypatch):
    url, _ = server
    monkeypatch.setattr(update, "API_URL", url + "/latest")
    with pytest.raises(update.UpdateFehler, match="EXE"):
        update.installieren(update.neueste_version())


def test_oberflaeche_update_pruefen(client, server, monkeypatch):
    url, _ = server
    monkeypatch.setattr(update, "API_URL", url + "/latest")
    post(client, "/update/pruefen")
    seite = client.get("/einstellungen/programm").get_data(as_text=True)
    assert "Neue Version 9.9.0" in seite
    assert "Neue Programmversion 9.9.0" in client.get("/kunden").get_data(as_text=True)
    assert client.get("/version").get_json()["version"]
    # ohne EXE: Installieren wird freundlich abgelehnt
    r = post(client, "/update/installieren")
    assert r.status_code == 302


def test_offline(client, monkeypatch):
    monkeypatch.setattr(update, "API_URL", "http://127.0.0.1:9/gibtsnicht")
    post(client, "/update/pruefen")
    assert "nicht erreichbar" in client.get("/einstellungen/programm").get_data(as_text=True)


def test_versionsprotokoll(client):
    from rsb import VERSION_NUMMER
    from rsb.versionen import protokoll_datei
    text = protokoll_datei().read_text(encoding="utf-8")
    assert f"## {VERSION_NUMMER} " in text, "Für die aktuelle Version fehlt ein Eintrag im Versionsprotokoll"
    seite = client.get("/versionen").get_data(as_text=True)
    assert f'id="v{VERSION_NUMMER}"' in seite and "<table" in seite and "<ul>" in seite
