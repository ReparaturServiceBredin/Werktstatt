"""Phase 9: Kassenbuch (fortlaufend, unveränderlich, Tagesabschluss) und DATEV-Export (EXTF-Buchungsstapel)."""
import csv
import hashlib
import io
import re
import sqlite3
import zipfile
from datetime import date, timedelta
from pathlib import Path

import pytest

from rsb import db as dbm

from conftest import kunde_anlegen, post, rechnung_anlegen

HEUTE = date.today().isoformat()
GESTERN = (date.today() - timedelta(days=1)).isoformat()


def buchen(client, **daten):
    daten.setdefault("datum", HEUTE)
    return post(client, "/kasse/buchen", **daten)


def kb(con):
    return con.execute("SELECT * FROM kassenbuch ORDER BY lfd_nr").fetchall()


def test_kassenbuch_grundregeln(client, con):
    buchen(client, datum=GESTERN, art="anfangsbestand", betrag="100,00", text="Wechselgeld")
    buchen(client, datum=GESTERN, art="ausgabe", betrag="150,00", text="Zu viel")  # → negativ, abgelehnt
    assert len(kb(con)) == 1
    buchen(client, datum=GESTERN, art="ausgabe", betrag="12,50", text="Briefmarken", kostenart="Porto & Versand")
    buchen(client, art="einnahme", betrag="20,00", text="Verkauf Ladekabel", steuersatz="19")
    buchen(client, art="entnahme", betrag="5,00", text="Privat")
    z = kb(con)
    assert [b["lfd_nr"] for b in z] == [1, 2, 3, 4] and [b["betrag"] for b in z] == [10000, -1250, 2000, -500]
    assert z[1]["kostenart"] == "Porto & Versand" and re.search(r"T\d\d:\d\d:\d\d", z[0]["erfasst_am"])
    with pytest.raises(sqlite3.DatabaseError):
        con.execute("UPDATE kassenbuch SET betrag=1 WHERE id=?", (z[0]["id"],))
    with pytest.raises(sqlite3.DatabaseError):
        con.execute("DELETE FROM kassenbuch WHERE id=?", (z[0]["id"],))
    # Gegenbuchung
    post(client, f"/kasse/{z[3]['id']}/gegenbuchung", grund="Falsch erfasst")
    post(client, f"/kasse/{z[3]['id']}/gegenbuchung", grund="nochmal")  # nur einmal möglich
    z = kb(con)
    assert len(z) == 5 and z[4]["betrag"] == 500 and z[4]["gegenbuchung_zu"] == z[3]["id"]
    seite = client.get(f"/kasse?von={GESTERN}").get_data(as_text=True)
    assert "Briefmarken" in seite and "gegengebucht" in seite and "107,50" in seite
    assert "Wechselgeld" in client.get(f"/kasse?von={GESTERN}&druck=1").get_data(as_text=True)


def test_rueckdatierte_buchung_fehlbetrag_und_nachholen(client, con):
    tag = lambda n: (date.today() - timedelta(days=n)).isoformat()  # noqa: E731
    buchen(client, datum=tag(3), art="anfangsbestand", betrag="100,00", text="Wechselgeld")
    buchen(client, datum=tag(1), art="ausgabe", betrag="80,00", text="Ersatzteil bar")
    # rückdatiert: am Buchungstag noch gedeckt, aber am Folgetag negativ
    r = buchen(client, datum=tag(2), art="ausgabe", betrag="50,00", text="Werkzeug bar")
    assert len(kb(con)) == 2 and "#fehlbetrag" in r.headers["Location"]
    tag_de = date.fromisoformat(tag(1)).strftime("%d.%m.%Y")
    seite = client.get(r.headers["Location"]).get_data(as_text=True)
    assert (f"Kassenbestand wäre am {tag_de} um 30,00 € negativ. Wahrscheinlich fehlt eine Einnahme oder eine "
            "Privateinlage.") in seite
    assert "Fehlende Einnahme erfassen" in seite and "Privateinlage buchen" in seite
    assert f'name="datum" value="{tag(1)}"' in seite and 'value="30,00"' in seite
    # zu wenig nachgebucht → bleibt vorgemerkt mit neuem Fehlbetrag
    post(client, "/kasse/buchen", nachholen="1", art="einnahme", datum=tag(1), betrag="10,00", text="Barverkauf Folie")
    with client.session_transaction() as sess:
        assert sess["kasse_offen"]["fehlbetrag"] == 2000 and sess["kasse_offen"]["buchung"]["text"] == "Werkzeug bar"
    # Privateinlage (ohne USt) → ursprüngliche Buchung wird automatisch nachgeholt
    post(client, "/kasse/buchen", nachholen="1", art="einlage", datum=tag(1), betrag="20,00", steuersatz="19",
         text="Wechselgeld aus Privatvermögen")
    z = kb(con)
    assert [(b["art"], b["betrag"], b["datum"]) for b in z[2:]] == [
        ("einnahme", 1000, tag(1)), ("einlage", 2000, tag(1)), ("ausgabe", -5000, tag(2))]
    assert z[3]["steuersatz"] is None and [b["lfd_nr"] for b in z] == [1, 2, 3, 4, 5]
    with client.session_transaction() as sess:
        assert "kasse_offen" not in sess
    assert kb(con) and con.execute("SELECT SUM(betrag) FROM kassenbuch").fetchone()[0] == 0
    # Privatentnahme braucht eine Begründung
    buchen(client, art="entnahme", betrag="1,00", text="")
    assert len(kb(con)) == 5


def test_tagesabschluss_kassensturz(client, con):
    buchen(client, datum=GESTERN, art="anfangsbestand", betrag="200,00", text="Anfang")
    post(client, "/kasse/abschluss", datum=GESTERN, ist="195,00")  # Differenz ohne Begründung → abgelehnt
    assert not con.execute("SELECT 1 FROM kassen_abschluesse").fetchone()
    post(client, "/kasse/abschluss", datum=GESTERN, ist="", anzahl_10000="1", anzahl_5000="1", anzahl_2000="2",
         anzahl_500="1", begruendung="Wechselgeld falsch herausgegeben")
    a = con.execute("SELECT * FROM kassen_abschluesse").fetchone()
    assert a["soll"] == 20000 and a["ist"] == 19500 and a["differenz"] == -500 and '"10000": 1' in a["zaehlung"]
    d = kb(con)[-1]
    assert d["art"] == "differenz" and d["betrag"] == -500
    # abgeschlossener Tag nicht mehr bebuchbar, nicht doppelt abschließbar
    buchen(client, datum=GESTERN, art="einnahme", betrag="1,00", text="zu spät")
    assert len(kb(con)) == 2
    post(client, "/kasse/abschluss", datum=GESTERN, ist="195,00")
    assert con.execute("SELECT COUNT(*) FROM kassen_abschluesse").fetchone()[0] == 1
    with pytest.raises(sqlite3.DatabaseError):
        con.execute("DELETE FROM kassen_abschluesse")
    seite = client.get("/pruefung").get_data(as_text=True)
    assert "Kassenbuch:" not in seite


def test_barzahlung_rechnung_und_storno(client, con):
    kid = kunde_anlegen(client)
    did = rechnung_anlegen(client, kid, festschreiben=True)
    buchen(client, art="einnahme", betrag="79,00", text="bar", dokument_id=str(did))
    z = con.execute("SELECT * FROM zahlungen").fetchone()
    assert z["zahlart"] == "bar"
    b = kb(con)[0]
    assert b["zahlung_id"] == z["id"] and b["betrag"] == 7900 and b["dokument_id"] == did
    post(client, f"/zahlungen/{z['id']}/stornieren", grund="Irrtum")
    b2 = kb(con)[-1]
    assert b2["gegenbuchung_zu"] == b["id"] and b2["betrag"] == -7900


def test_datev_export(client, con, app):
    with dbm.Transaktion(con):
        dbm.einstellungen_speichern({"datev_beraternr": "1234567", "datev_mandantennr": "54321"}, con)
    kid = kunde_anlegen(client)
    did = rechnung_anlegen(client, kid, positionen=(("Akkutausch", "79,00", "1"),), festschreiben=True,
                           datum=GESTERN)
    nummer = con.execute("SELECT nummer FROM dokumente WHERE id=?", (did,)).fetchone()[0]
    post(client, f"/dokumente/{did}/zahlung", datum=HEUTE, betrag="79,00", zahlart="ueberweisung")
    post(client, "/lieferanten/neu", name="iParts GmbH", kreditornr="70005")
    lid = con.execute("SELECT id FROM lieferanten").fetchone()[0]
    client.post("/eingangsrechnungen/neu", data={"csrf": "test-token", "lieferant_id": str(lid), "nummer": "R-9",
                                                 "datum": GESTERN, "brutto": "59,50", "steuersatz": "19",
                                                 "kostenart": "Wareneinkauf / Ersatzteile"})
    buchen(client, art="einlage", betrag="50,00", text="Einlage")
    von, bis = HEUTE[:4] + "-01-01", HEUTE
    seite = client.get(f"/datev?von={von}&bis={bis}").get_data(as_text=True)
    assert "4 Buchung(en)" in seite and "8195" in seite
    r = post(client, "/datev", von=von, bis=bis)
    eid = int(re.search(r"neu=(\d+)", r.headers["Location"]).group(1))
    e = con.execute("SELECT * FROM datev_exporte WHERE id=?", (eid,)).fetchone()
    daten = client.get(f"/datev/{eid}/download").data
    assert hashlib.sha256(daten).hexdigest() == e["sha256"] and e["anzahl"] == 4
    z = zipfile.ZipFile(io.BytesIO(daten))
    namen = z.namelist()
    csv_name = [n for n in namen if n.startswith("EXTF_")][0]
    assert f"Belege/{nummer}.pdf" in namen
    zeilen = list(csv.reader(io.StringIO(z.read(csv_name).decode("cp1252")), delimiter=";"))
    kopf = zeilen[0]
    assert kopf[:5] == ["EXTF", "700", "21", "Buchungsstapel", "13"] and kopf[10:12] == ["1234567", "54321"]
    assert kopf[14] == von.replace("-", "") and kopf[26] == "03"
    assert zeilen[1][0] == "Umsatz (ohne Soll/Haben-Kz)"
    daten_zeilen = {(r[6], r[7]): r for r in zeilen[2:]}
    deb = str(10000 + kid)
    assert daten_zeilen[(deb, "8195")][0] == "79,00" and daten_zeilen[(deb, "8195")][10] == nummer
    assert daten_zeilen[("1200", deb)][1] == "S"           # Zahlungseingang Bank an Debitor
    assert daten_zeilen[("3200", "70005")][0] == "59,50"  # Wareneingang an Kreditor (KU: ohne Vorsteuer)
    assert ("1000", "1890") in daten_zeilen               # Einlage
    # zweiter Export: nichts Neues
    assert "Keine noch nicht exportierten" in client.get(f"/datev?von={von}&bis={bis}").get_data(as_text=True)
    # exportierte Eingangsrechnung ist gesperrt
    er = con.execute("SELECT * FROM eingangsrechnungen").fetchone()
    assert er["exportiert_am"]
    # erneuter Export möglich, ohne neue Vermerke
    post(client, "/datev", von=von, bis=bis, erneut="1")
    assert con.execute("SELECT COUNT(*) FROM datev_exporte").fetchone()[0] == 2
    assert con.execute("SELECT COUNT(*) FROM datev_posten").fetchone()[0] == 4
    assert Path(app.config["DATEN"], e["datei"]).is_file()


def test_datev_regelbesteuerung_und_storno(client, con):
    with dbm.Transaktion(con):
        dbm.einstellungen_speichern({"steuer_modus": "regel", "datev_skr": "04"}, con)
    kid = kunde_anlegen(client)
    did = rechnung_anlegen(client, kid, positionen=(("Arbeit", "100,00", "1"),), festschreiben=True)
    from rsb import datev
    z = datev.buchungen(con, HEUTE[:4] + "-01-01", HEUTE)
    assert [(x["konto"], x["gegenkonto"], x["betrag"]) for x in z] == [(str(10000 + kid), "4400", 11900)]
    post(client, f"/dokumente/{did}/stornieren", grund="Fehler")
    z = datev.buchungen(con, HEUTE[:4] + "-01-01", HEUTE)
    assert sorted(x["betrag"] for x in z) == [-11900, 11900]
    # Einstellungen
    r = post(client, "/einstellungen/datev", datev_beraternr="12a", datev_mandantennr="1", datev_skr="03",
             datev_wj_beginn="01-01", datev_kontenlaenge="4", datev_debitor_start="10000", datev_kreditor_start="70000",
             datev_konten="", datev_kostenarten="")
    assert dbm.einstellungen(con)["datev_beraternr"] == ""  # Buchstaben abgelehnt
    post(client, "/einstellungen/datev", datev_beraternr="1234567", datev_mandantennr="1", datev_skr="03",
         datev_wj_beginn="01-01", datev_kontenlaenge="4", datev_debitor_start="10000", datev_kreditor_start="70000",
         datev_konten="bank=1210", datev_kostenarten="")
    assert datev.konten(dbm.einstellungen(con))[0]["bank"] == "1210"
    assert r.status_code == 302
