"""Fixkosten (Rhythmen, Beträge „gültig ab“, Hinweise, Bankabgleich) und Finanzübersicht (nachgerechnete Zahlen)."""
import re
import sqlite3
from datetime import date

import pytest

from rsb import db as dbm
from rsb import finanzen as fin
from rsb import fixkosten as fk

from conftest import kunde_anlegen, post


def fix_anlegen(client, **w):
    daten = dict(bezeichnung="Werkstattmiete", kategorie="Werkstattmiete", netto="1000,00", steuersatz="19",
                 rhythmus="monatlich", faellig_tag="1", beginn="2026-01-01", zahlungsart="lastschrift",
                 empfaenger="Vermieter Huber")
    daten.update(w)
    r = post(client, "/fixkosten/neu", **daten)
    assert r.status_code == 302, r.get_data(as_text=True)[:400]
    return int(re.search(r"/fixkosten/(\d+)", r.headers["Location"]).group(1))


def test_rhythmen_anteilig_faellig_und_mieterhoehung(client, con):
    miete = fix_anlegen(client)
    versicherung = fix_anlegen(client, bezeichnung="Betriebshaftpflicht", kategorie="Versicherungen", netto="",
                               brutto="1200,00", steuersatz="0", rhythmus="jaehrlich", faellig_tag="15",
                               beginn="2026-03-15", empfaenger="Allianz")
    internet = fix_anlegen(client, bezeichnung="Internet", kategorie="Internet", netto="90,00", rhythmus="vierteljaehrlich",
                           beginn="2026-02-01", faellig_tag="31", empfaenger="Telekom")
    # Mieterhöhung ab 01.01.2027 – vergangene Zeiträume bleiben
    r = post(client, f"/fixkosten/{miete}", aktion="betrag", gueltig_ab="2027-01-01", netto="1100,00", steuersatz="19",
             notiz_betrag="Mieterhöhung")
    assert r.status_code == 302
    f = fk.eine(con, miete)
    assert [(b["gueltig_ab"], b["netto"], b["brutto"]) for b in f["betraege"]] == [
        ("2026-01-01", 100000, 119000), ("2027-01-01", 110000, 130900)]
    assert fk.monatsanteil(f, 2026, 12)["netto"] == 100000 and fk.monatsanteil(f, 2027, 1)["netto"] == 110000
    with pytest.raises(sqlite3.DatabaseError):
        con.execute("UPDATE fixkosten_betraege SET netto=1 WHERE fixkosten_id=?", (miete,))
    post(client, f"/fixkosten/{miete}", aktion="betrag", gueltig_ab="2027-01-01", netto="1200,00", steuersatz="19")
    assert len(fk.eine(con, miete)["betraege"]) == 2  # gleiches „gültig ab“ abgelehnt
    seite = client.get(f"/fixkosten/{miete}").get_data(as_text=True)
    assert "Mieterhöhung" in seite and "geplant" in seite and "1.309,00 €" in seite

    v, i = fk.eine(con, versicherung), fk.eine(con, internet)
    assert v["betraege"][0]["netto"] == 120000 and v["betraege"][0]["brutto"] == 120000
    assert [d.isoformat() for d, _ in fk.faelligkeiten(v, date(2026, 1, 1), date(2027, 12, 31))] == [
        "2026-03-15", "2027-03-15"]
    assert [d.isoformat() for d, _ in fk.faelligkeiten(i, date(2026, 1, 1), date(2026, 12, 31))] == [
        "2026-02-28", "2026-05-31", "2026-08-31", "2026-11-30"]  # Tag 31 = Monatsende
    assert fk.monatsanteil(v, 2026, 2) is None and fk.monatsanteil(v, 2026, 3)["netto"] == 10000
    assert fk.monatsanteil(i, 2026, 6)["netto"] == 3000
    ue = fk.uebersicht(con, date(2026, 6, 1))
    assert round(ue["summe"]["monat_netto"]) == 100000 + 10000 + 3000
    assert round(ue["summe"]["monat_brutto"]) == 119000 + 10000 + 3570
    # Finanzen: Quartal summiert korrekt; Monat anteilig vs. im Fälligkeitsmonat
    q2 = fk.kosten(con, date(2026, 4, 1), date(2026, 6, 30), "anteilig")
    assert round(sum(p["netto"] for p in q2)) == 3 * 100000 + 3 * 10000 + 3 * 3000
    maerz_faellig = fk.kosten(con, date(2026, 3, 1), date(2026, 3, 31), "faellig")
    assert sorted(p["f"]["bezeichnung"] for p in maerz_faellig) == ["Betriebshaftpflicht", "Werkstattmiete"]
    assert sum(p["netto"] for p in maerz_faellig) == 100000 + 120000
    jahr_anteilig = fk.kosten(con, date(2026, 1, 1), date(2026, 12, 31), "anteilig")
    jahr_faellig = fk.kosten(con, date(2026, 1, 1), date(2026, 12, 31), "faellig")
    assert round(sum(p["netto"] for p in jahr_anteilig)) == 12 * 100000 + 10 * 10000 + 11 * 3000
    assert sum(p["netto"] for p in jahr_faellig) == 12 * 100000 + 120000 + 4 * 9000
    seite = client.get("/fixkosten").get_data(as_text=True)
    assert "Werkstattmiete" in seite and "Fixkosten pro Monat" in seite and "Versicherungen" in seite


def test_hinweise_kuendigungsfrist_und_glocke(client, con):
    fid = fix_anlegen(client, bezeichnung="Leasing Transporter", kategorie="Leasing", beginn="2024-01-01",
                      ende="2026-12-31", kuendigung_wert="3", kuendigung_einheit="monate")
    f = fk.eine(con, fid)
    assert fk.kuendigung_bis(f) == date(2026, 9, 30)
    h = fk.hinweise(con, date(2026, 9, 10))
    assert [x["text"] for x in h] == ["Kündigungsfrist für „Leasing Transporter“ endet am 30.09.2026"]
    assert [x["text"] for x in fk.hinweise(con, date(2026, 12, 15))] == ["Vertrag „Leasing Transporter“ endet am 31.12.2026"]
    assert fk.hinweise(con, date(2026, 6, 1)) == []
    # Glocke (heute = Systemdatum): Hinweis anlegen, der jetzt fällig ist
    heute = fk.heute_datum()
    fid2 = fix_anlegen(client, bezeichnung="Software-Abo", kategorie="Software-Abos", beginn="2025-01-01",
                       ende=(heute.replace(day=1) if heute.day > 20 else heute).isoformat()[:8] + "28",
                       kuendigung_wert="1", kuendigung_einheit="tage")
    assert any(x["f"]["id"] == fid2 for x in fk.hinweise(con, nur_ungelesen=True))
    html = client.get("/").get_data(as_text=True)
    assert "Software-Abo" in html and 'class="glocke-zahl"' in html
    r = client.get(f"/fixkosten/hinweis?s={fk.hinweise(con)[0]['schluessel']}&fid={fid2}")
    assert r.status_code == 302
    post(client, "/benachrichtigungen/gelesen")
    assert fk.hinweise(con, nur_ungelesen=True) == []


def _umsatz(con, tag, betrag, name, zweck=""):
    imp = con.execute("INSERT INTO bank_importe (dateiname, format, sha256, importiert_am, anzahl) VALUES "
                      "('a.csv', 'CSV', ?, ?, 1)", (f"x{tag}{betrag}", dbm.jetzt_berlin())).lastrowid
    return con.execute("INSERT INTO bank_umsaetze (import_id, kennung, buchungstag, betrag, name, verwendungszweck) "
                       "VALUES (?,?,?,?,?,?)", (imp, f"k{tag}{betrag}{name}", tag, betrag, name, zweck)).lastrowid


def test_bankabgleich_fixkosten(client, con):
    miete = fix_anlegen(client, beginn="2026-07-01")
    strom = fix_anlegen(client, bezeichnung="Strom", kategorie="Strom", netto="", brutto="85,00",
                        beginn="2026-07-01", faellig_tag="5", empfaenger="Stadtwerke Möckmühl",
                        bank_suchbegriff="STADTWERKE MOECKMUEHL")
    u1 = _umsatz(con, "2026-07-01", -119000, "Vermieter Huber", "Miete Juli")
    u2 = _umsatz(con, "2026-08-03", -125000, "Vermieter Huber", "Miete August")   # Betrag weicht ab
    u3 = _umsatz(con, "2026-07-05", -8500, "STADTWERKE MOECKMUEHL GMBH", "Abschlag")
    _umsatz(con, "2026-09-30", -100, "Bank", "Kontoführung")  # Ende des Auszugszeitraums
    liste = fk.alle(con)
    vor = {u: fk.bank_vorschlag(con, con.execute("SELECT * FROM bank_umsaetze WHERE id=?", (u,)).fetchone(), liste)
           for u in (u1, u2, u3)}
    assert vor[u1]["f"]["id"] == miete and vor[u1]["sicher"]
    assert vor[u2]["f"]["id"] == miete and not vor[u2]["sicher"] and "weicht ab" in vor[u2]["grund"]
    assert vor[u3]["f"]["id"] == strom and vor[u3]["sicher"]
    seite = client.get("/bank").get_data(as_text=True)
    assert "Fixkosten-Vorschlag: Werkstattmiete – Empfänger und Betrag passen" in seite
    for u, f in ((u1, miete), (u2, miete), (u3, strom)):
        post(client, f"/bank/{u}/fixkosten", fixkosten_id=str(f))
    assert con.execute("SELECT status, fixkosten_monat FROM bank_umsaetze WHERE id=?", (u2,)).fetchone()[:] == (
        "zugeordnet", "2026-08")
    stand = fk.zahlungsstand(con, heute=date(2026, 10, 16))
    assert [(s["monat"], s["status"]) for s in stand[miete]] == [("2026-07", "bezahlt"), ("2026-08", "abweichend"),
                                                                ("2026-09", "fehlt")]
    assert [(s["monat"], s["status"]) for s in stand[strom]] == [("2026-07", "bezahlt"), ("2026-08", "fehlt"),
                                                                ("2026-09", "fehlt")]
    assert "Fixkosten ohne passende Abbuchung" in client.get("/bank").get_data(as_text=True)
    assert "fehlt" in client.get("/fixkosten").get_data(as_text=True)
    post(client, f"/bank/{u2}/fixkosten", loesen="1")
    assert con.execute("SELECT status, fixkosten_id FROM bank_umsaetze WHERE id=?", (u2,)).fetchone()[:] == ("offen", None)
    # Löschen nur ohne Zuordnungen
    post(client, f"/fixkosten/{miete}", aktion="loeschen")
    assert fk.eine(con, miete)


def _rechnung(client, con, kid, datum, positionen):
    """positionen: (Bezeichnung, Preis, Menge, Artikel-ID, Teilekosten)."""
    r = client.get(f"/dokumente/neu?kunde_id={kid}")
    did = int(re.search(r"/dokumente/(\d+)", r.headers["Location"]).group(1))
    client.post(f"/dokumente/{did}", data={
        "csrf": "test-token", "kunde_id": kid, "datum": datum, "leistungsdatum": datum, "leistungsdatum_bis": "",
        "zahlungsziel_tage": "14", "betreff": "Reparatur", "einleitung": "x", "schlusstext": "y", "hinweise": "",
        "aktion": "festschreiben", "p_bezeichnung": [p[0] for p in positionen],
        "p_beschreibung": ["" for _ in positionen], "p_menge": [p[2] for p in positionen],
        "p_einheit": ["Stk." for _ in positionen], "p_preis": [p[1] for p in positionen],
        "p_teilekosten": [p[4] for p in positionen], "p_steuersatz": ["19" for _ in positionen],
        "p_leistungsart": ["Smartphone" for _ in positionen], "p_artikel_id": [p[3] for p in positionen]})
    d = con.execute("SELECT * FROM dokumente WHERE id=?", (did,)).fetchone()
    assert d["status"] == "festgeschrieben", d["status"]
    return did


def test_finanzen_nachgerechnet(client, con):
    with dbm.Transaktion(con):
        dbm.einstellungen_speichern({"steuer_modus": "regel"}, con)
    kid = kunde_anlegen(client)
    post(client, "/artikel/neu", name="Panzerglas", preis="20,00", teilekosten="4,00", einheit="Stk.", typ="material",
         steuersatz="19", aktiv="1")
    panzerglas = con.execute("SELECT id FROM artikel WHERE name='Panzerglas'").fetchone()[0]
    heute = fk.heute_datum()
    tag = heute.replace(day=2).isoformat()
    # Rechnung 1: Reparatur 100 (Teile 30), Artikel 2 × 20 (Teile 4), KVA 29, Leihgebühr 15
    r1 = _rechnung(client, con, kid, tag, [("Displaytausch", "100,00", "1", "", "30,00"),
                                          ("Panzerglas", "20,00", "2", str(panzerglas), "4,00"),
                                          ("Kostenvoranschlag / Fehlerdiagnose – Gerät: iPhone", "29,00", "1", "", "0"),
                                          ("Leihgerät Lenovo, 3 Tage à 5,00 €", "5,00", "3", "", "0")])
    # Rechnung 2 wird storniert → zählt netto 0
    r2 = _rechnung(client, con, kid, tag, [("Akkutausch", "80,00", "1", "", "25,00")])
    post(client, f"/dokumente/{r2}/stornieren", grund="Fehler")
    # Zahlung auf Rechnung 1 (Teilzahlung 100 €)
    post(client, f"/dokumente/{r1}/zahlung", datum=tag, betrag="100,00", zahlart="ueberweisung")
    # Eingangsrechnungen: Wareneinsatz 20 netto, Sonstiges 10 netto, eine gehört zu Fixkosten (zählt nicht doppelt)
    miete = fix_anlegen(client, beginn="2026-01-01")
    for nr, netto, kostenart in (("W1", "20,00", "Wareneinkauf / Ersatzteile"), ("B1", "10,00", "Bürobedarf"),
                                 ("M1", "1000,00", "Miete & Nebenkosten")):
        client.post("/eingangsrechnungen/neu", data={"csrf": "test-token", "lieferant_name": "Lieferant", "nummer": nr,
                                                     "datum": tag, "netto": netto, "steuersatz": "19",
                                                     "kostenart": kostenart})
    m1 = con.execute("SELECT id FROM eingangsrechnungen WHERE nummer='M1'").fetchone()[0]
    post(client, f"/eingangsrechnungen/{m1}/fixkosten", fixkosten_id=str(miete))
    # Kasse: Anfangsbestand, Ausgabe 11,90 brutto (19 %) Bürobedarf → 10,00 netto
    post(client, "/kasse/buchen", datum=tag, art="anfangsbestand", betrag="100,00", text="Wechselgeld")
    post(client, "/kasse/buchen", datum=tag, art="ausgabe", betrag="11,90", text="Druckerpapier", steuersatz="19",
         kostenart="Bürobedarf")

    a = fin.auswertung(con, "monat", heute.year, heute.month)
    k = a["k"]
    assert k["umsatz_kat"] == {"Reparaturen & Dienstleistungen": 10000, "Artikelverkauf": 4000, "Leihgebühren": 1500,
                               "KVA-Gebühren": 2900}
    assert k["umsatz_netto"] == 18400 and k["umsatz_brutto"] == 21896   # 184,00 + 19 % (Storno hebt R2 auf)
    assert k["wareneinsatz"] == 2000 and k["sonstige"] == 1000 + 1000 and k["fixkosten"] == 100000
    assert k["rohertrag"] == 16400 and k["ergebnis"] == 16400 - 100000 - 2000
    assert k["ust"] == 3496 and k["vorsteuer"] == 380 + 190 + 190 + 19000
    assert a["zufluss"] == 10000
    assert sum(x["offen"] for x in a["forderungen"]) == 21896 - 10000
    assert sum(x["offen"] for x in a["verbindlichkeiten"]) == 2380 + 1190 + 119000
    assert a["auftraege"]["marge"] == pytest.approx((18400 - (3000 + 800)) / 18400 * 100)
    # nach Zahlungseingang: 100 € brutto → 84,03 netto, anteilig auf die Kategorien
    z = fin.auswertung(con, "monat", heute.year, heute.month, basis="zahlung")
    assert z["k"]["umsatz_netto"] == round(10000 * 18400 / 21896)
    # Seite, Belege hinter einer Zahl, Export
    seite = client.get(f"/finanzen?art=monat&jahr={heute.year}&nr={heute.month}").get_data(as_text=True)
    assert "nicht die steuerliche Gewinnermittlung bzw. EÜR" in seite and "184,00 €" in seite
    assert "<svg" in seite and "Break-even" in seite and "Vorschau nächste 3 Monate" in seite
    belege = client.get(f"/finanzen/belege?s=wareneinsatz&art=monat&jahr={heute.year}&nr={heute.month}")
    text = belege.get_data(as_text=True)
    assert "W1" in text and "B1" not in text and "20,00 €" in text
    text = client.get(f"/finanzen/belege?s=ausgabe:Bürobedarf&art=monat&jahr={heute.year}&nr={heute.month}"
                      ).get_data(as_text=True)
    assert "B1" in text and "Druckerpapier" in text and "20,00 €" in text  # Summe 10 + 10
    text = client.get(f"/finanzen/belege?s=umsatz&art=monat&jahr={heute.year}&nr={heute.month}").get_data(as_text=True)
    assert "Storno" in text and "184,00 €" in text
    csv = client.get(f"/finanzen?art=monat&jahr={heute.year}&nr={heute.month}&export=csv")
    assert csv.data.startswith("﻿".encode()) and "Umsatz netto;184,00".encode() in csv.data
    pdf = client.get(f"/finanzen?art=quartal&jahr={heute.year}&export=pdf")
    assert pdf.data.startswith(b"%PDF")
    for art in ("quartal", "halbjahr", "jahr"):
        a = fin.auswertung(con, art, heute.year)
        assert a["k"]["umsatz_netto"] == 18400
        assert a["k"]["fixkosten"] == 100000 * len(a["monate"])
        assert client.get(f"/finanzen?art={art}&jahr={heute.year}").status_code == 200
    assert client.get("/finanzen?art=frei&von=2026-01-01&bis=2026-12-31").status_code == 200


def test_kleinunternehmer_ausgaben_brutto_ohne_ust(client, con):
    fix_anlegen(client)
    heute = fk.heute_datum()
    a = fin.auswertung(con, "monat", heute.year, heute.month)
    assert a["ku"] and a["k"]["fixkosten"] == 119000  # keine Vorsteuer → brutto
    seite = client.get("/finanzen").get_data(as_text=True)
    assert "Umsatzsteuer (Orientierung)" not in seite and "Ausgaben brutto (Kleinunternehmer" in seite


def test_zeitraum_und_blaettern():
    assert fin.zeitraum("quartal", 2026, 4)[:2] == (date(2026, 10, 1), date(2026, 12, 31))
    assert fin.zeitraum("halbjahr", 2026, 1)[:2] == (date(2026, 1, 1), date(2026, 6, 30))
    assert fin.blaettern("monat", 2026, 1, -1) == (2025, 12)
    assert fin.blaettern("quartal", 2026, 4, 1) == (2027, 1)
    assert fin._vorjahr(date(2024, 2, 1), date(2024, 2, 29)) == (date(2023, 2, 1), date(2023, 2, 28))
    assert fin._verschieben(date(2026, 4, 1), date(2026, 6, 30), "quartal") == (date(2026, 1, 1), date(2026, 3, 31))
