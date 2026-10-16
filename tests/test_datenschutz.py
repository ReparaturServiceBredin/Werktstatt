"""Phase 10: Datenschutz – Löschfristen und Löschlauf, Auskunft (Art. 15), Löschanfrage mit Protokoll, VVT (Art. 30)."""
import io
import json
import sqlite3
import zipfile
from datetime import date, timedelta
from pathlib import Path

import pytest

from rsb import datenschutz as ds
from rsb import db as dbm

from conftest import kunde_anlegen, post, rechnung_anlegen
from test_annahme import auftrag_mit_annahme, unterschreiben
from test_auftrag_detail import bild, foto_hochladen


def vor(tage):
    return (date.today() - timedelta(days=tage)).isoformat() + "T10:00:00"


def test_auskunft_art15(client, con, app):
    kid = kunde_anlegen(client)
    aid = auftrag_mit_annahme(client, kid)
    foto_hochladen(client, f"/auftraege/{aid}/fotos", bild())
    unterschreiben(client, aid)
    rechnung_anlegen(client, kid, festschreiben=True)
    r = client.get(f"/kunden/{kid}/auskunft")
    assert r.status_code == 200 and r.mimetype == "application/zip"
    z = zipfile.ZipFile(io.BytesIO(r.data))
    namen = z.namelist()
    assert "Auskunft_Art15_DSGVO.pdf" in namen and "gespeicherte_Daten.json" in namen
    assert any(n.startswith("Belege/") for n in namen) and any(n.startswith("Fotos/") for n in namen)
    assert any(n.startswith("Annahme_Abholscheine/") for n in namen)
    daten = json.loads(z.read("gespeicherte_Daten.json"))
    assert daten["kunde"]["nachname"] == "Müller" and daten["auftraege"][0]["zugangsdaten_gespeichert"].startswith("ja")
    assert "4711" not in z.read("gespeicherte_Daten.json").decode()  # Zugangsdaten nie im Klartext
    assert z.read("Auskunft_Art15_DSGVO.pdf").startswith(b"%PDF")
    assert con.execute("SELECT 1 FROM protokoll WHERE aktion='datenschutz_auskunft'").fetchone()


def test_loeschanfrage_mit_protokoll(client, con):
    kid = kunde_anlegen(client)
    rechnung_anlegen(client, kid, festschreiben=True)
    r = post(client, f"/kunden/{kid}/loeschen", anfrage="1")
    assert "#protokolle" in r.headers["Location"]
    p = con.execute("SELECT * FROM loeschprotokolle").fetchone()
    assert p["anlass"].startswith("Löschanfrage") and p["betroffen"].endswith("A. Müller")
    behalten = json.loads(p["behalten"])
    assert behalten and "Dokument" in behalten[0]["was"] and p["bis"]
    assert "Stammdaten" in " ".join(json.loads(p["geloescht"]))
    assert client.get(f"/datenschutz/protokoll/{p['id']}.pdf").data.startswith(b"%PDF")
    with pytest.raises(sqlite3.DatabaseError):
        con.execute("DELETE FROM loeschprotokolle")
    # Kunde ohne Belege: vollständig gelöscht, Protokoll trotzdem da
    kid2 = kunde_anlegen(client, vorname="Bert", nachname="Ohne")
    post(client, f"/kunden/{kid2}/loeschen")
    assert not con.execute("SELECT 1 FROM kunden WHERE id=?", (kid2,)).fetchone()
    assert con.execute("SELECT COUNT(*) FROM loeschprotokolle").fetchone()[0] == 2


def test_kalenderjahr_regel():
    assert ds.ab_jahresende(date(2026, 10, 15), 3) == date(2030, 1, 1)
    assert ds.ab_jahresende(date(2026, 1, 1), 3) == date(2030, 1, 1)
    assert ds.ab_jahresende(date(2026, 12, 31), 3) == date(2030, 1, 1)


def _eintrag(con, art, oid, **kw):
    return next((e for e in ds.kandidaten(con, **kw)["eintraege"] if e["art"] == art and e["id"] == oid), None)


def _alt_abgeholt(client, con, kid, jahr=2022, **extra):
    """Auftrag mit Foto, Annahme- und Abholschein, abgeholt im Jahr `jahr`."""
    aid = auftrag_mit_annahme(client, kid, **extra)
    foto_hochladen(client, f"/auftraege/{aid}/fotos", bild())
    unterschreiben(client, aid)
    post(client, f"/auftraege/{aid}/status", status="erledigt", ohne_kva="1")
    unterschreiben(client, aid, art="abholung")
    con.execute("UPDATE auftraege SET abgeholt_am=?, garantie_ende=? WHERE id=?",
                (f"{jahr}-10-15T10:00:00", f"{jahr + 1}-10-15", aid))
    return aid


def test_loeschvorschau_fotos_scheine_sperren_zurueckstellen(client, con, app):
    kid = kunde_anlegen(client)
    aid = _alt_abgeholt(client, con, kid)
    e = _eintrag(con, "auftrag", aid)
    assert e["faellig"] == date(2026, 1, 1) and "3 Jahre ab Ende 2022" in e["frist"] and not e["sperre"]
    # Sperre: offene Rechnung des Kunden
    rid = rechnung_anlegen(client, kid, festschreiben=True)
    assert "offene Rechnung" in _eintrag(con, "auftrag", aid)["sperre"]
    post(client, f"/dokumente/{rid}/zahlung", datum=date.today().isoformat(), betrag="79,00", zahlart="ueberweisung")
    assert not _eintrag(con, "auftrag", aid)["sperre"]
    # Sperre: laufende Garantie
    con.execute("UPDATE auftraege SET garantie_ende=? WHERE id=?", ((date.today() + timedelta(days=30)).isoformat(), aid))
    assert "laufende Garantie" in _eintrag(con, "auftrag", aid)["sperre"]
    con.execute("UPDATE auftraege SET garantie_ende='2023-10-15' WHERE id=?", (aid,))
    # Vorschau
    seite = client.get("/datenschutz").get_data(as_text=True)
    assert "Folgende Daten werden in den nächsten 30 Tagen gelöscht" in seite and "fällig" in seite
    # Zurückstellen mit Begründung
    post(client, "/datenschutz/zurueckstellen", art="auftrag", objekt_id=str(aid), grund="x")  # zu kurz
    assert not ds.zurueckstellungen(con)
    post(client, "/datenschutz/zurueckstellen", art="auftrag", objekt_id=str(aid), grund="Streitfall Display")
    assert _eintrag(con, "auftrag", aid)["zurueck"]["grund"] == "Streitfall Display"
    assert "zurückgestellt" in client.get("/datenschutz").get_data(as_text=True)
    post(client, "/datenschutz")
    assert con.execute("SELECT COUNT(*) FROM auftrag_belege WHERE auftrag_id=?", (aid,)).fetchone()[0] == 2
    # Aufheben → nächster Lauf löscht Fotos und Scheine (Dateien + Einträge)
    z = ds.zurueckstellungen(con)[0]
    post(client, f"/datenschutz/zurueckstellung/{z['id']}/aufheben")
    f = con.execute("SELECT * FROM auftrag_fotos WHERE auftrag_id=?", (aid,)).fetchone()
    belege = [Path(app.config["DATEN"]) / b["pdf_datei"] for b in
              con.execute("SELECT pdf_datei FROM auftrag_belege WHERE auftrag_id=?", (aid,))]
    assert all(p.is_file() for p in belege) and (Path(app.config["DATEN"]) / f["pfad"]).is_file()
    post(client, "/datenschutz")
    assert not con.execute("SELECT 1 FROM auftrag_belege WHERE auftrag_id=?", (aid,)).fetchone()
    assert not any(p.exists() for p in belege) and not (Path(app.config["DATEN"]) / f["pfad"]).exists()
    assert con.execute("SELECT geloescht_am FROM auftrag_fotos WHERE id=?", (f["id"],)).fetchone()[0]
    p = con.execute("SELECT * FROM loeschprotokolle WHERE betroffen LIKE 'Auftrag AU-%' AND frist LIKE '%Ende 2022%'"
                    ).fetchone()
    assert p and "Annahme-/Abholschein" in p["geloescht"] and "Müller" not in p["geloescht"]
    # Schutz der Scheine bleibt außerhalb des Löschlaufs bestehen
    aid2 = auftrag_mit_annahme(client, kid)
    unterschreiben(client, aid2)
    with pytest.raises(sqlite3.DatabaseError):
        con.execute("DELETE FROM auftrag_belege WHERE auftrag_id=?", (aid2,))


def test_inaktive_kunden_und_interessenten(client, con):
    alt = kunde_anlegen(client, vorname="Alt", nachname="Kunde")
    rechnung_anlegen(client, alt, festschreiben=True)
    con.execute("UPDATE dokumente SET bezahlt_betrag=summe_brutto WHERE kunde_id=?", (alt,))
    ohne = kunde_anlegen(client, vorname="Leer", nachname="Kunde")
    aktiv = kunde_anlegen(client, vorname="Neu", nachname="Kunde")
    auftrag_mit_annahme(client, aktiv)  # laufender Auftrag → gesperrt
    con.execute("UPDATE kunden SET geaendert_am=?, erstellt_am=? WHERE id=?", ("2022-06-01T10:00:00", "2022-06-01T10:00:00", ohne))
    e = _eintrag(con, "kunde", ohne)
    assert e["faellig"] == date(2026, 1, 1) and "letzter Kontakt 01.06.2022" in e["frist"]
    assert _eintrag(con, "kunde", alt) is None  # Rechnung von heute = letzter Kontakt
    zukunft = date(date.today().year + 4, 1, 1)
    assert _eintrag(con, "kunde", alt, heute=zukunft, tage=0)["faellig"] == zukunft
    assert "laufender Auftrag" in _eintrag(con, "kunde", aktiv, heute=zukunft, tage=0)["sperre"]
    # Interessent: 6 Monate nach letztem Kontakt
    inter = kunde_anlegen(client, vorname="Inter", nachname="Essent")
    con.execute("UPDATE kunden SET interessent=1, geaendert_am=?, erstellt_am=? WHERE id=?",
                (vor(200), vor(200), inter))
    assert _eintrag(con, "interessent", inter)["faellig"] <= date.today()
    with dbm.Transaktion(con):
        z = ds.loeschlauf(con, str(Path(client.application.config["DATEN"])), heute=zukunft)
    assert z["kunden_geloescht"] == 1 and z["kunden_anonymisiert"] == 1 and z["interessenten"] == 1
    assert not con.execute("SELECT 1 FROM kunden WHERE id IN (?, ?)", (ohne, inter)).fetchone()
    assert con.execute("SELECT anonymisiert_am FROM kunden WHERE id=?", (alt,)).fetchone()[0]
    assert con.execute("SELECT anonymisiert_am FROM kunden WHERE id=?", (aktiv,)).fetchone()[0] is None
    assert con.execute("SELECT COUNT(*) FROM loeschprotokolle WHERE frist LIKE 'Inaktiver Kunde%'").fetchone()[0] == 2


def test_zugangsdaten_bei_abholung_und_storno(client, con):
    kid = kunde_anlegen(client)
    aid = auftrag_mit_annahme(client, kid)
    unterschreiben(client, aid)
    post(client, f"/auftraege/{aid}/status", status="erledigt", ohne_kva="1")
    # Abschluss löscht bereits; zweiter Auftrag: erst bei Abholung
    aid2 = auftrag_mit_annahme(client, kid)
    assert con.execute("SELECT zugang_geheim FROM auftraege WHERE id=?", (aid2,)).fetchone()[0]
    unterschreiben(client, aid2, art="abholung")
    a = con.execute("SELECT * FROM auftraege WHERE id=?", (aid2,)).fetchone()
    assert a["zugang_geheim"] is None and a["zugang_geloescht_am"]
    p = con.execute("SELECT * FROM loeschprotokolle WHERE anlass='Gerät abgeholt'").fetchone()
    assert p and "Gerätezugangsdaten" in p["geloescht"] and "4711" not in json.dumps(dict(p))
    # Stornierung (Auftrag löschen)
    aid3 = auftrag_mit_annahme(client, kid)
    post(client, f"/auftraege/{aid3}/loeschen")
    assert not con.execute("SELECT 1 FROM auftraege WHERE id=?", (aid3,)).fetchone()
    assert con.execute("SELECT 1 FROM loeschprotokolle WHERE anlass='Auftrag storniert/gelöscht'").fetchone()
    # Restlaufzeit bei liegengebliebenen Aufträgen
    aid4 = auftrag_mit_annahme(client, kid)
    con.execute("UPDATE auftraege SET eingang_am=? WHERE id=?", (vor(100), aid4))
    post(client, "/datenschutz")
    assert con.execute("SELECT zugang_geheim FROM auftraege WHERE id=?", (aid4,)).fetchone()[0] is None


def test_leihprotokoll_frist(client, con, app):
    from test_leihgeraete import ausgeben, geraet_anlegen, zuruecknehmen
    from test_auftraege import auftrag_anlegen
    kid = kunde_anlegen(client)
    aid = auftrag_anlegen(client, kid)
    gid = geraet_anlegen(client)
    lid, token, _ = ausgeben(client, aid, gid)
    zuruecknehmen(client, lid)
    gid2 = geraet_anlegen(client, bezeichnung="Laptop #2", inventarnr="LG-002", seriennummer="PF-2")
    lid2, _, _ = ausgeben(client, aid, gid2)
    zuruecknehmen(client, lid2, zustand="schaden", schaden_beschreibung="Display gesprungen", kostenart="reparatur",
                  schaden_betrag="120,00")
    zukunft = date(date.today().year + 4, 1, 1)
    e = _eintrag(con, "leihe", lid, heute=zukunft, tage=0)
    assert e["faellig"] == zukunft and not e["sperre"]
    assert _eintrag(con, "leihe", lid, heute=zukunft - timedelta(days=40), tage=30) is None
    assert "offener Schadensfall" in _eintrag(con, "leihe", lid2, heute=zukunft, tage=0)["sperre"]
    with dbm.Transaktion(con):
        z = ds.loeschlauf(con, app.config["DATEN"], heute=zukunft)
    assert z["leihen"] == 1
    le = con.execute("SELECT * FROM leihen WHERE id=?", (lid,)).fetchone()
    assert le["protokoll_geloescht_am"] and le["zustand_ausgabe"] is None and le["rueckgabe_notiz"] is None
    assert le["leihnr"] and le["gebuehr_berechnet"] is not None  # Abrechnung bleibt nachvollziehbar
    assert con.execute("SELECT zustand_ausgabe FROM leihen WHERE id=?", (lid2,)).fetchone()[0] == "Kratzer am Deckel"
    assert "Protokoll gelöscht (Löschfrist)" in client.get(f"/leihen/{lid}").get_data(as_text=True)
    assert client.get(f"/leihen/{lid}/ausgabe.pdf").status_code == 200
    with pytest.raises(sqlite3.DatabaseError):  # Schutz außerhalb des Löschlaufs unverändert
        con.execute("UPDATE leihen SET zustand_ausgabe='x' WHERE id=?", (lid2,))


def test_verzeichnis_und_einstellungen(client, con):
    kunde_anlegen(client)
    seite = client.get("/datenschutz/verzeichnis").get_data(as_text=True)
    assert "Verarbeitungstätigkeiten" in seite and "Gerätezugangsdaten" in seite and "1 Kunden" in seite
    assert "Ende des Kalenderjahres der Abholung" in seite
    assert client.get("/datenschutz/verzeichnis?pdf=1").data.startswith(b"%PDF")
    post(client, "/einstellungen/datenschutz", ds_auto="1", interessent_loeschen_monate="6",
         ds_kunde_inaktiv_jahre="0", ds_fotos_jahre="4", ds_leihe_jahre="5", ds_vorschau_tage="14", ds_zugang_tage="60",
         ds_email_jahre="0", ds_verantwortlicher="")
    e = dbm.einstellungen(con)
    assert e["ds_auto"] is True and e["ds_fotos_jahre"] == 4 and e["ds_leihe_jahre"] == 5
    assert e["ds_kunde_inaktiv_jahre"] == 0 and e["ds_vorschau_tage"] == 14
    assert not [x for x in ds.kandidaten(con)["eintraege"] if x["art"] == "kunde"]  # 0 = aus
    assert "nächsten 14 Tagen" in client.get("/datenschutz").get_data(as_text=True)
