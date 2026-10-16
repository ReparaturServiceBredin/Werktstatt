"""Fester Datenordner: unabhängig vom Startort, bisherige Daten werden einmalig geprüft übernommen."""
import json

from rsb import create_app
from rsb import datenort
from rsb import db as dbm

from conftest import kunde_anlegen


def _ordner_mit_daten(pfad, kunden=1):
    app = create_app(pfad, testing=True)
    c = app.test_client()
    with c.session_transaction() as s:
        s["csrf"] = "test-token"
    for i in range(kunden):
        kunde_anlegen(c, vorname=f"K{i}", nachname="Test")
    (pfad / "fotos" / "2026").mkdir(parents=True, exist_ok=True)
    (pfad / "fotos" / "2026" / f"f{kunden}.jpg").write_bytes(b"jpg")
    return app


def _umgebung(monkeypatch, tmp_path, programm):
    monkeypatch.delenv("RSB_DATEN", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "AppData"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "AppData"))
    monkeypatch.setattr(datenort, "_programm_ordner", lambda: programm)


def test_uebernahme_des_ordners_mit_den_meisten_daten(tmp_path, monkeypatch):
    desktop, downloads = tmp_path / "Desktop", tmp_path / "Downloads"
    _ordner_mit_daten(desktop / "Daten", kunden=1)       # neben der gestarteten EXE: wenig
    _ordner_mit_daten(downloads / "Daten", kunden=3)     # alter Ort mit den eigentlichen Daten
    _umgebung(monkeypatch, tmp_path, desktop)
    ziel = datenort.ermitteln(suchorte=[tmp_path], ausgabe=lambda m: None)
    assert ziel == datenort.fester_ort() and "AppData" in str(ziel)
    bericht = json.loads((ziel / "umzug.json").read_text(encoding="utf-8"))
    assert bericht["von"] == str((downloads / "Daten").resolve()) and bericht["datensaetze"]["kunden"] == 3
    assert bericht["weitere_ordner"] == [str((desktop / "Daten").resolve())]
    assert (ziel / "fotos" / "2026" / "f3.jpg").is_file() and (ziel / "geheim" / "schluessel.key").exists() is \
        (downloads / "Daten" / "geheim" / "schluessel.key").exists()
    assert (downloads / "Daten" / datenort.NOTIZ).is_file() and (downloads / "Daten" / "werkstatt.db").is_file()
    # Programm öffnet den festen Ort – auch von einem anderen Startordner aus, ohne erneute Übernahme
    monkeypatch.setattr(datenort, "_programm_ordner", lambda: tmp_path / "Woanders")
    assert datenort.ermitteln(suchorte=[tmp_path]) == ziel
    app = create_app(testing=True)
    assert app.config["DATEN"] == str(ziel)
    with app.app_context():
        assert dbm.get_db().execute("SELECT COUNT(*) FROM kunden").fetchone()[0] == 3
    c = app.test_client()
    seite = c.get("/").get_data(as_text=True)
    assert "Ihre Daten liegen jetzt fest an einem Ort" in seite and "Weitere ältere Datenordner" in seite
    assert "Ihre Daten liegen jetzt fest" not in c.get("/").get_data(as_text=True)  # nur einmal


def test_erster_start_ohne_alte_daten_und_rsb_daten(tmp_path, monkeypatch):
    _umgebung(monkeypatch, tmp_path, tmp_path / "Programm")
    assert datenort.ermitteln(suchorte=[tmp_path / "leer"]) == datenort.fester_ort()
    monkeypatch.setenv("RSB_DATEN", str(tmp_path / "Docker"))
    assert datenort.ermitteln() == (tmp_path / "Docker").resolve()


def test_pruefung_schlaegt_fehl_dann_bleibt_alter_ordner(tmp_path, monkeypatch):
    alt = tmp_path / "Programm" / "Daten"
    _ordner_mit_daten(alt, kunden=2)
    _umgebung(monkeypatch, tmp_path, tmp_path / "Programm")
    echt = datenort._tabellen_zaehlen
    aufrufe = []

    def falsch(db):
        aufrufe.append(db)
        z = echt(db)
        if len(aufrufe) > 1 and "AppData" in str(db):
            z["kunden"] -= 1  # simulierte unvollständige Kopie
        return z
    monkeypatch.setattr(datenort, "_tabellen_zaehlen", falsch)
    meldungen = []
    assert datenort.ermitteln(suchorte=[], ausgabe=meldungen.append) == alt
    assert not datenort.fester_ort().exists() and "fehlgeschlagen" in meldungen[0]
    assert not (alt / datenort.NOTIZ).exists()
