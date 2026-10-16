import json
import sqlite3
from pathlib import Path

import pytest
from pypdf import PdfReader

from rsb import db as dbm
from rsb import logik
from rsb.hilfen import EingabeFehler

from conftest import kunde_anlegen, post, rechnung_anlegen


def test_rechnung_festschreiben_und_pdf(client, app, con):
    kid = kunde_anlegen(client)
    did = rechnung_anlegen(client, kid, positionen=[("Akkutausch iPhone", "79,00", "1"), ("Folie", "9,90", "2")],
                           festschreiben=True)
    d = con.execute("SELECT * FROM dokumente WHERE id=?", (did,)).fetchone()
    assert d["status"] == "festgeschrieben"
    assert d["nummer"].startswith("RE-") and d["nummer"].endswith("-0001")
    assert d["summe_brutto"] == 7900 + 1980
    pdf = Path(app.config["DATEN"]) / d["pdf_pfad"]
    assert pdf.is_file()
    text = "".join(p.extract_text() for p in PdfReader(pdf).pages)
    for erwartet in ["Rechnung", d["nummer"], "Anna Müller", "Akkutausch iPhone", "98,80", "§ 19 UStG",
                     "Sehr geehrte Frau Müller", "Leistungsdatum"]:
        assert erwartet in text, erwartet
    snap = json.loads(d["snapshot_json"])
    assert d["nummer"] in snap["schlusstext"]  # Platzhalter ersetzt
    # gespeichertes PDF wird unverändert ausgeliefert
    r = client.get(f"/dokumente/{did}/pdf")
    assert r.data == pdf.read_bytes()


def test_nummern_fortlaufend_und_lueckenlos(client, con, app):
    kid = kunde_anlegen(client)
    nummern = []
    for _ in range(3):
        did = rechnung_anlegen(client, kid, festschreiben=True)
        nummern.append(con.execute("SELECT nummer FROM dokumente WHERE id=?", (did,)).fetchone()[0])
    assert [n[-4:] for n in nummern] == ["0001", "0002", "0003"]
    # Entwurf ohne Positionen festschreiben schlägt fehl und verbraucht KEINE Nummer
    leer = rechnung_anlegen(client, kid, positionen=[])
    with pytest.raises(EingabeFehler):
        logik.festschreiben(con, leer, app.config["DATEN"])
    did = rechnung_anlegen(client, kid, festschreiben=True)
    assert con.execute("SELECT nummer FROM dokumente WHERE id=?", (did,)).fetchone()[0].endswith("0004")
    ergebnis = logik.integritaet_pruefen(con, app.config["DATEN"])
    assert ergebnis["nummern"] == [] and ergebnis["pdf"] == [] and ergebnis["protokoll"] == []


def test_festgeschrieben_ist_unveraenderbar(client, con):
    kid = kunde_anlegen(client)
    did = rechnung_anlegen(client, kid, festschreiben=True)
    for sql in ["UPDATE dokumente SET summe_brutto=1 WHERE id=?",
                "UPDATE dokumente SET nummer='RE-X' WHERE id=?",
                "UPDATE dokumente SET status='entwurf' WHERE id=?",
                "DELETE FROM dokumente WHERE id=?",
                "UPDATE positionen SET einzelpreis=1 WHERE dokument_id=?",
                "DELETE FROM positionen WHERE dokument_id=?"]:
        with pytest.raises(sqlite3.DatabaseError):
            con.execute(sql, (did,))
    with pytest.raises(sqlite3.DatabaseError):
        con.execute("UPDATE nummernkreise SET letzte_nummer=0")
    with pytest.raises(sqlite3.DatabaseError):
        con.execute("DELETE FROM nummernkreise")
    # Über die Oberfläche: Bearbeiten und Löschen werden abgewiesen
    post(client, f"/dokumente/{did}", betreff="geändert", aktion="speichern")
    post(client, f"/dokumente/{did}/loeschen")
    d = con.execute("SELECT * FROM dokumente WHERE id=?", (did,)).fetchone()
    assert d["betreff"] == "Reparatur" and d["status"] == "festgeschrieben"


def test_manipuliertes_pdf_wird_erkannt(client, con, app):
    kid = kunde_anlegen(client)
    did = rechnung_anlegen(client, kid, festschreiben=True)
    pfad = Path(app.config["DATEN"]) / con.execute("SELECT pdf_pfad FROM dokumente WHERE id=?", (did,)).fetchone()[0]
    pfad.write_bytes(pfad.read_bytes() + b"x")
    assert logik.integritaet_pruefen(con, app.config["DATEN"])["pdf"]


def test_storno(client, con, app):
    kid = kunde_anlegen(client)
    did = rechnung_anlegen(client, kid, positionen=[("Wartung", "89,00", "1")], festschreiben=True)
    r = post(client, f"/dokumente/{did}/stornieren", grund="Fehler in Adresse")
    assert r.status_code == 302
    orig = con.execute("SELECT * FROM dokumente WHERE id=?", (did,)).fetchone()
    storno = con.execute("SELECT * FROM dokumente WHERE id=?", (orig["storniert_durch"],)).fetchone()
    assert orig["status"] == "storniert"
    assert storno["typ"] == "storno" and storno["status"] == "festgeschrieben"
    assert storno["summe_brutto"] == -8900 and storno["nummer"].endswith("0002")
    text = "".join(p.extract_text() for p in PdfReader(Path(app.config["DATEN"]) / storno["pdf_pfad"]).pages)
    assert "Stornorechnung" in text and orig["nummer"] in text and "-89,00" in text
    # zweites Storno nicht möglich
    with pytest.raises(EingabeFehler):
        logik.stornieren(con, did, app.config["DATEN"])
    # Kopie als neuer Entwurf mit positiven Beträgen
    post(client, f"/dokumente/{storno['id']}/kopieren")
    neu = con.execute("SELECT * FROM dokumente WHERE status='entwurf' ORDER BY id DESC").fetchone()
    assert neu["summe_brutto"] == 8900


def test_zahlungsziel_privat_und_firma(client, con):
    privat = kunde_anlegen(client)
    firma = kunde_anlegen(client, typ="firma", firma="Bäckerei Schön GmbH")
    d1 = rechnung_anlegen(client, privat)
    d2 = rechnung_anlegen(client, firma)
    z = {r["id"]: r["zahlungsziel_tage"] for r in con.execute("SELECT id, zahlungsziel_tage FROM dokumente")}
    assert z[d1] == 14 and z[d2] == 30


def test_umstellung_auf_regelbesteuerung(client, con, app):
    kid = kunde_anlegen(client)
    with dbm.Transaktion(con):
        dbm.einstellungen_speichern({"steuer_modus": "regel"}, con)
    did = rechnung_anlegen(client, kid, positionen=[("Wartung", "100,00", "1")], festschreiben=True)
    d = con.execute("SELECT * FROM dokumente WHERE id=?", (did,)).fetchone()
    assert d["summe_netto"] == 10000 and d["summe_steuer"] == 1900 and d["summe_brutto"] == 11900
    text = "".join(p.extract_text() for p in PdfReader(Path(app.config["DATEN"]) / d["pdf_pfad"]).pages)
    assert "19 % USt" in text and "§ 19 UStG" not in text


def test_datum_reihenfolge(client, con, app):
    kid = kunde_anlegen(client)
    rechnung_anlegen(client, kid, festschreiben=True)
    alt = rechnung_anlegen(client, kid, datum="2020-01-01")
    with pytest.raises(EingabeFehler):
        logik.festschreiben(con, alt, app.config["DATEN"])


def test_kunde_mit_rechnung_nicht_loeschbar(client, con):
    kid = kunde_anlegen(client)
    rechnung_anlegen(client, kid, festschreiben=True)
    post(client, f"/kunden/{kid}/loeschen")
    assert con.execute("SELECT 1 FROM kunden WHERE id=?", (kid,)).fetchone()
    leer = kunde_anlegen(client, nachname="Ohne")
    post(client, f"/kunden/{leer}/loeschen")
    assert not con.execute("SELECT 1 FROM kunden WHERE id=?", (leer,)).fetchone()


def test_seiten_laden(client):
    kid = kunde_anlegen(client)
    did = rechnung_anlegen(client, kid)
    for url in ["/", "/kunden", f"/kunden/{kid}", "/kunden/neu", "/artikel", "/artikel/neu", "/verkauf/rechnungen",
                f"/dokumente/{did}", f"/dokumente/{did}/pdf", f"/dokumente/{did}/drucken", "/textbausteine",
                "/textbausteine/1", "/protokoll", "/pruefung", "/einstellungen/musterrechnung.pdf",
                "/einstellungen/logo.png"] + [f"/einstellungen/{b}" for b in
                                              ["firma", "rechnung", "layout", "email", "backup", "sicherheit"]]:
        assert client.get(url).status_code == 200, url
