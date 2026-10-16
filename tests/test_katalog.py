import re
import sqlite3
from pathlib import Path

from pypdf import PdfReader

from rsb import db as dbm
from rsb import katalog, logik

from conftest import kunde_anlegen, post


def entwurf(client, kid, typ="rechnung"):
    r = client.get(f"/dokumente/neu?kunde_id={kid}&typ={typ}")
    return int(re.search(r"/dokumente/(\d+)", r.headers["Location"]).group(1))


def speichern(client, did, kid, positionen, aktion="speichern"):
    """positionen: Liste von dicts mit bezeichnung, beschreibung, preis, ek, einheit, katalog, typ, artikel_id"""
    feld = lambda k, std="": [p.get(k, std) for p in positionen]  # noqa: E731
    return client.post(f"/dokumente/{did}", data={
        "csrf": "test-token", "kunde_id": kid, "datum": "", "leistungsdatum": "2026-01-02", "leistungsdatum_bis": "",
        "zahlungsziel_tage": "", "betreff": "Test", "einleitung": "", "schlusstext": "", "hinweise": "",
        "aktion": aktion, "p_bezeichnung": feld("bezeichnung"), "p_beschreibung": feld("beschreibung"),
        "p_menge": feld("menge", "1"), "p_einheit": feld("einheit", "Stk."), "p_preis": feld("preis", "0"),
        "p_teilekosten": feld("ek"), "p_steuersatz": feld("steuersatz", "19"), "p_leistungsart": feld("art", "PC/Laptop"),
        "p_artikel_id": feld("artikel_id"), "p_katalog": feld("katalog", "1"), "p_typ": feld("typ", "material")})


def artikel(con, name):
    return con.execute("SELECT * FROM artikel WHERE name=?", (name,)).fetchone()


def test_manuelle_position_wird_katalogeintrag(client, con):
    kid = kunde_anlegen(client)
    did = entwurf(client, kid, "kva")
    beschreibung = "Anschlüsse:\n  2× HDMI 2.0\n  1× USB-C PD 100 W\nMaße: 120 × 60 × 18 mm"
    speichern(client, did, kid, [
        {"bezeichnung": "USB-C Dock 12-in-1", "beschreibung": beschreibung, "preis": "89,90", "ek": "45,00"},
        {"bezeichnung": "Datenrettung Express", "preis": "120,00", "ek": "", "typ": "leistung", "einheit": "pauschal"},
        {"bezeichnung": "Einmalige Sonderposition", "preis": "5,00", "katalog": "0"},
    ])
    dock = artikel(con, "USB-C Dock 12-in-1")
    assert dock["beschreibung"] == beschreibung  # mehrzeilig, ungekürzt
    assert (dock["preis"], dock["teilekosten"], dock["ek_unbekannt"], dock["typ"]) == (8990, 4500, 0, "material")
    assert dock["aufschlag_prozent"] == round((8990 - 4500) * 100 / 4500, 1)
    assert katalog.marge(dock["preis"], dock["teilekosten"]) == (4490, 49.9)
    daten = artikel(con, "Datenrettung Express")
    assert daten["ek_unbekannt"] == 1 and daten["typ"] == "leistung" and daten["aufschlag_prozent"] is None
    assert katalog.marge(daten["preis"], daten["teilekosten"], daten["ek_unbekannt"]) == (None, None)
    assert artikel(con, "Einmalige Sonderposition") is None
    # Dokumentpositionen sind mit dem Katalog verknüpft (außer der Sonderposition)
    pos = con.execute("SELECT bezeichnung, artikel_id FROM positionen WHERE dokument_id=? ORDER BY pos", (did,)).fetchall()
    assert pos[0]["artikel_id"] == dock["id"] and pos[1]["artikel_id"] == daten["id"] and pos[2]["artikel_id"] is None
    # Artikelliste: Suche in der Beschreibung, nur erste Zeile sichtbar, Marge leer bei unbekanntem EK
    seite = client.get("/artikel?q=HDMI").get_data(as_text=True)
    assert "USB-C Dock 12-in-1" in seite and "Datenrettung" not in seite
    assert "Anschlüsse:" in seite and "Maße" not in seite


def test_duplikat_und_preis_rueckfrage(client, con):
    kid = kunde_anlegen(client)
    d1 = entwurf(client, kid)
    speichern(client, d1, kid, [{"bezeichnung": "Akkutausch Pixel 7", "preis": "79,00", "ek": "25,00"}])
    d2 = entwurf(client, kid)
    # gleiche Bezeichnung mit anderer Schreibweise und anderem Preis
    speichern(client, d2, kid, [{"bezeichnung": "  akkutausch   PIXEL 7 ", "preis": "85,00", "ek": "27,00"}])
    assert con.execute("SELECT COUNT(*) FROM artikel WHERE name LIKE '%Pixel 7%'").fetchone()[0] == 1
    seite = client.get(f"/dokumente/{d2}").get_data(as_text=True)
    assert "Preise im Katalog aktualisieren?" in seite and "85,00" in seite
    a = artikel(con, "Akkutausch Pixel 7")
    assert a["preis"] == 7900  # noch unverändert
    post(client, "/artikel/preise-aktualisieren", antwort="ja", artikel_id=str(a["id"]))
    a = artikel(con, "Akkutausch Pixel 7")
    assert (a["preis"], a["teilekosten"]) == (8500, 2700)
    assert "Preise im Katalog aktualisieren?" not in client.get(f"/dokumente/{d2}").get_data(as_text=True)
    # Nein: Katalog bleibt
    d3 = entwurf(client, kid)
    speichern(client, d3, kid, [{"bezeichnung": "Akkutausch Pixel 7", "preis": "99,00", "ek": ""}])
    post(client, "/artikel/preise-aktualisieren", antwort="nein")
    assert artikel(con, "Akkutausch Pixel 7")["preis"] == 8500


def test_katalogposition_im_dokument_anpassen_aendert_katalog_nicht(client, con, app):
    kid = kunde_anlegen(client)
    did = entwurf(client, kid)
    speichern(client, did, kid, [{"bezeichnung": "SSD 1 TB", "beschreibung": "Lang\nZeile 2\nZeile 3", "preis": "99,00",
                                  "ek": "60,00"}])
    aid = artikel(con, "SSD 1 TB")["id"]
    did2 = entwurf(client, kid)
    speichern(client, did2, kid, [{"bezeichnung": "SSD 1 TB", "beschreibung": "Gekürzt", "preis": "99,00",
                                   "ek": "60,00", "artikel_id": str(aid), "katalog": "0"}], aktion="festschreiben")
    assert artikel(con, "SSD 1 TB")["beschreibung"] == "Lang\nZeile 2\nZeile 3"
    d = con.execute("SELECT * FROM dokumente WHERE id=?", (did2,)).fetchone()
    text = "".join(p.extract_text() for p in PdfReader(Path(app.config["DATEN"]) / d["pdf_pfad"]).pages)
    assert "SSD 1 TB" in text and "Gekürzt" in text and "Zeile 2" not in text


def test_pdf_lange_beschreibung_mit_umbruechen(client, con, app):
    kid = kunde_anlegen(client)
    did = entwurf(client, kid)
    lang = "\n".join(f"Port {i}: USB-C 3.2 Gen 2, 10 Gbit/s" for i in range(1, 120))
    speichern(client, did, kid, [{"bezeichnung": "Dock XXL", "beschreibung": lang, "preis": "10,00", "ek": "1,00"}],
              aktion="festschreiben")
    d = con.execute("SELECT * FROM dokumente WHERE id=?", (did,)).fetchone()
    reader = PdfReader(Path(app.config["DATEN"]) / d["pdf_pfad"])
    text = "".join(p.extract_text() for p in reader.pages)
    assert len(reader.pages) >= 2
    assert "Port 1: USB-C" in text and "Port 119: USB-C" in text  # nichts abgeschnitten
    assert reader.pages[0].extract_text().count("Bezeichnung") == 1  # Tabellenkopf nicht doppelt auf Seite 1


def test_aus_bisherigen_dokumenten_uebernehmen(client, con, app):
    kid = kunde_anlegen(client)
    # alte Rechnung mit manuellen Positionen (ohne Katalog-Haken, wie vor diesem Update)
    did = entwurf(client, kid)
    speichern(client, did, kid, [
        {"bezeichnung": "Display iPhone 12", "beschreibung": "Original-Qualität", "preis": "149,00", "ek": "80,00",
         "katalog": "0"},
        {"bezeichnung": "Reinigung", "preis": "29,00", "ek": "", "katalog": "0", "einheit": "pauschal"},
    ], aktion="festschreiben")
    did2 = entwurf(client, kid, "kva")
    speichern(client, did2, kid, [{"bezeichnung": "display IPHONE 12", "preis": "139,00", "ek": "", "katalog": "0"}])
    vorschlaege = {v["bezeichnung"]: v for v in katalog.aus_dokumenten_sammeln(con)}
    assert len(vorschlaege) == 2  # Duplikate zusammengefasst
    disp = next(v for k, v in vorschlaege.items() if "iphone 12" in k.lower())
    assert disp["anzahl"] == 2 and disp["teilekosten"] == 8000 and set(disp["preise"]) == {13900, 14900}
    seite = client.get("/artikel/aus-dokumenten").get_data(as_text=True)
    assert "Reinigung" in seite and "früher auch" in seite
    post(client, "/artikel/aus-dokumenten", schluessel=[v["schluessel"] for v in vorschlaege.values()])
    assert con.execute("SELECT COUNT(*) FROM artikel WHERE name IN ('Reinigung') OR name LIKE '%iPhone 12%' "
                       "COLLATE NOCASE").fetchone()[0] == 2
    assert artikel(con, "Reinigung")["ek_unbekannt"] == 1
    # offener Entwurf wurde verknüpft, festgeschriebene Rechnung bleibt unverändert
    assert con.execute("SELECT artikel_id FROM positionen WHERE dokument_id=?", (did2,)).fetchone()[0]
    assert con.execute("SELECT artikel_id FROM positionen WHERE dokument_id=? AND pos=1", (did,)).fetchone()[0] is None
    assert all(v["im_katalog"] for v in katalog.aus_dokumenten_sammeln(con))


def test_migration_mit_sicherung(tmp_path):
    pfad = tmp_path / "Daten" / "werkstatt.db"
    pfad.parent.mkdir()
    con = sqlite3.connect(pfad)  # Datenbank im Stand einer älteren Version
    con.executescript("""
        CREATE TABLE artikel (id INTEGER PRIMARY KEY, artikelnr TEXT, name TEXT NOT NULL, beschreibung TEXT,
            leistungsart TEXT, typ TEXT NOT NULL DEFAULT 'leistung', einheit TEXT, preis INTEGER NOT NULL DEFAULT 0,
            teilekosten INTEGER NOT NULL DEFAULT 0, aufschlag_prozent REAL, steuersatz REAL NOT NULL DEFAULT 19,
            aktiv INTEGER NOT NULL DEFAULT 1, erstellt_am TEXT NOT NULL, geaendert_am TEXT NOT NULL);
        INSERT INTO artikel (name, preis, erstellt_am, geaendert_am) VALUES ('Altartikel', 1000, 'x', 'x');
        CREATE TABLE versandprotokoll (id INTEGER PRIMARY KEY, dokument_id INTEGER, zeitpunkt TEXT NOT NULL,
            empfaenger TEXT NOT NULL, bcc TEXT, betreff TEXT, text TEXT, anhang_name TEXT, anhang_sha256 TEXT,
            status TEXT NOT NULL, fehlermeldung TEXT);
    """)
    con.commit()
    con.close()
    dbm.initialisieren(str(pfad))
    sicherungen = list((pfad.parent / "backups").glob("vor_update_*.db"))
    assert len(sicherungen) == 1
    alt = sqlite3.connect(sicherungen[0])
    assert "ek_unbekannt" not in [r[1] for r in alt.execute("PRAGMA table_info(artikel)")]
    neu = dbm.verbinden(str(pfad))
    assert neu.execute("SELECT name, ek_unbekannt FROM artikel").fetchone()[:] == ("Altartikel", 0)
    assert "ablage" in [r[1] for r in neu.execute("PRAGMA table_info(versandprotokoll)")]
    dbm.initialisieren(str(pfad))  # zweiter Start: keine weitere Sicherung nötig
    assert len(list((pfad.parent / "backups").glob("vor_update_*.db"))) == 1
