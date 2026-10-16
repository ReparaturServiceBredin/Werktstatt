"""Wiederherstellung aus Sicherungen: Inhaltsvorschau, vorher vollständige Sicherung, Einspielen beim Start."""
import sqlite3
import zipfile

from rsb import create_app
from rsb import db as dbm
from rsb import wiederherstellung as wh
from rsb.backup import backup_erstellen

from conftest import kunde_anlegen, post


def _zaehlen(db):
    c = sqlite3.connect(db)
    try:
        return {t: c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("kunden", "artikel", "auftraege")}
    finally:
        c.close()


def test_wiederherstellen_aus_zip(tmp_path):
    daten = tmp_path / "Daten"
    app = create_app(daten, testing=True)
    c = app.test_client()
    with c.session_transaction() as s:
        s["csrf"] = "test-token"
    kunde_anlegen(c)
    post(c, "/artikel/neu", name="Akkutausch", preis="89,00", teilekosten="30,00", einheit="pauschal", typ="leistung",
         steuersatz="19", aktiv="1")
    (daten / "fotos" / "2026" / "10").mkdir(parents=True)
    (daten / "fotos" / "2026" / "10" / "abc.jpg").write_bytes(b"jpg")
    with app.app_context():
        dbm.einstellungen_speichern({"strasse": "Hauptstraße 1", "imap_host": "imap.ionos.de"}, dbm.get_db())
        zip_pfad, _ = backup_erstellen(daten, app.config["DB_PFAD"])
    # danach „verloren“: Daten leeren, Foto weg
    con = dbm.verbinden(app.config["DB_PFAD"])
    con.execute("DELETE FROM artikel")
    con.execute("UPDATE einstellungen SET wert='\"\"' WHERE schluessel IN ('strasse', 'imap_host')")
    con.close()
    (daten / "fotos" / "2026" / "10" / "abc.jpg").unlink()
    assert _zaehlen(daten / "werkstatt.db")["artikel"] == 0

    seite = c.get("/einstellungen/backup").get_data(as_text=True)
    assert zip_pfad.name in seite and "Hauptstraße 1" in seite and "imap.ionos.de" in seite
    q = next(x for x in wh.quellen(daten) if x["name"] == zip_pfad.name)
    assert q["inhalt"]["anzahl"]["kunden"] == 1 and q["inhalt"]["anzahl"]["artikel"] >= 1 and q["inhalt"]["dateien"] == 1
    r = post(c, "/einstellungen/backup/wiederherstellen", quelle=q["pfad"])
    assert r.status_code == 302 and wh.vorgemerkt(daten)
    assert post(c, "/einstellungen/backup/wiederherstellen", quelle="/etc/passwd").status_code == 302  # abgelehnt
    assert wh.vorgemerkt(daten)["quelle"] == q["pfad"]

    # Neustart: wird vor dem Öffnen der Datenbank eingespielt
    app2 = create_app(daten, testing=True)
    with app2.app_context():
        e = dbm.einstellungen(dbm.get_db())
        assert e["strasse"] == "Hauptstraße 1" and e["imap_host"] == "imap.ionos.de"
        assert e["wiederherstellung_bericht"]["ok"]
    assert _zaehlen(daten / "werkstatt.db")["artikel"] >= 1
    assert (daten / "fotos" / "2026" / "10" / "abc.jpg").read_bytes() == b"jpg"
    assert not wh.vorgemerkt(daten)
    # vorheriger Stand vollständig gesichert (inkl. Schlüssel)
    sich = list((daten / "backups").glob("vor_wiederherstellung_*.zip"))
    assert len(sich) == 1
    namen = zipfile.ZipFile(sich[0]).namelist()
    assert "werkstatt.db" in namen and any(n.startswith("geheim/") for n in namen)
    assert "Zuletzt eingespielt" in app2.test_client().get("/einstellungen/backup").get_data(as_text=True)


def test_wiederherstellen_aus_vor_update_und_anderem_ordner(tmp_path):
    alt = tmp_path / "Downloads" / "Daten"
    app_alt = create_app(alt, testing=True)
    c = app_alt.test_client()
    with c.session_transaction() as s:
        s["csrf"] = "test-token"
    kunde_anlegen(c, vorname="Bert", nachname="Alt")
    (alt / "dokumente" / "x.pdf").write_bytes(b"%PDF")
    neu = tmp_path / "Desktop" / "Daten"
    create_app(neu, testing=True)
    gefunden = wh.andere_datenordner(neu, [tmp_path])
    assert gefunden == [(alt / "werkstatt.db").resolve()]
    q = [x for x in wh.quellen(neu, [tmp_path]) if x["art"] == "Anderer Datenordner"][0]
    assert q["inhalt"]["anzahl"]["kunden"] == 1 and q["inhalt"]["dateien"] == 1
    # vormerken prüft gegen die Standard-Suchorte – hier direkt eintragen wie vormerken es täte
    import json
    (neu / wh.MARKE).write_text(json.dumps({"quelle": q["pfad"]}), encoding="utf-8")
    create_app(neu, testing=True)
    assert _zaehlen(neu / "werkstatt.db")["kunden"] == 1
    assert (neu / "dokumente" / "x.pdf").is_file() and (neu / "geheim" / "sitzung.key").is_file()
    # vor_update_*.db als Quelle
    vu = neu / "backups" / "vor_update_test.db"
    src = sqlite3.connect(alt / "werkstatt.db")
    dst = sqlite3.connect(vu)
    src.backup(dst)
    src.close()
    dst.close()
    assert any(x["name"] == "vor_update_test.db" and x["inhalt"]["anzahl"]["kunden"] == 1 for x in wh.quellen(neu))
