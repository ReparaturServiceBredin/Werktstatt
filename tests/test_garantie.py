"""Phase 5: Garantie je Reparatur/Position, Wiedererkennung per SN/IMEI, Garantiefall."""
import json
from datetime import date

from rsb import db as dbm
from rsb import garantie as gar

from conftest import kunde_anlegen, post
from test_annahme import auftrag_mit_annahme, unterschreiben
from test_auftraege import kva_mit_position


def test_plus_monate():
    assert gar.plus_monate(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert gar.plus_monate(date(2026, 10, 15), 12) == date(2027, 10, 15)
    assert gar.sn_normal(" 3567-8901 2345/678 ") == "356789012345678"


def test_garantie_auf_abholschein_und_rechnung(client, con, app):
    kid = kunde_anlegen(client)
    aid = auftrag_mit_annahme(client, kid, geraet="Xiaomi 14T Pro", garantie_monate="6")
    kva_mit_position(client, con, aid)
    post(client, f"/auftraege/{aid}/status", status="erledigt")
    a = con.execute("SELECT * FROM auftraege WHERE id=?", (aid,)).fetchone()
    assert a["garantie_monate"] == 6
    # Rechnung festschreiben → Garantietext im Snapshot
    re_id = a["rechnung_id"]
    d = con.execute("SELECT * FROM dokumente WHERE id=?", (re_id,)).fetchone()
    client.post(f"/dokumente/{re_id}", data={
        "csrf": "test-token", "kunde_id": kid, "datum": "", "leistungsdatum": "2026-10-15", "zahlungsziel_tage": "",
        "betreff": d["betreff"], "einleitung": "x", "schlusstext": "y", "hinweise": "", "aktion": "festschreiben",
        "p_bezeichnung": ["Displaytausch", "Schutzfolie"], "p_beschreibung": ["", ""], "p_menge": ["1", "1"],
        "p_einheit": ["pauschal", "Stk."], "p_preis": ["149,00", "9,90"], "p_teilekosten": ["70,00", "1,00"],
        "p_steuersatz": ["19", "19"], "p_leistungsart": ["Smartphone", "Smartphone"], "p_artikel_id": ["", ""],
        "p_garantie": ["", "0"]})
    d = con.execute("SELECT * FROM dokumente WHERE id=?", (re_id,)).fetchone()
    assert d["status"] == "festgeschrieben"
    snap = json.loads(d["snapshot_json"])
    t = snap["garantie_text"]
    # noch nicht abgeholt: Beginn = Abholung, nicht Rechnungsdatum
    assert "freiwillige Garantie von 6 Monaten ab Abholung (bis Ablauf von 6 Monaten nach Abholung)" in t
    assert "bei Reparatur Service Bredin, Hauptstraße 1, 74219 Möckmühl vorstellen" in t
    assert "gesetzlichen Gewährleistungsrechte bleiben von dieser Garantie unberührt" in t
    assert [p["garantie_monate"] for p in snap["positionen"]] == [None, 0]
    assert client.get(f"/dokumente/{re_id}/pdf").status_code == 200
    assert not con.execute("SELECT garantie_ende FROM auftraege WHERE id=?", (aid,)).fetchone()[0]
    unterschreiben(client, aid, art="abholung")
    ende = gar.plus_monate(date.today(), 6)
    assert con.execute("SELECT garantie_ende FROM auftraege WHERE id=?", (aid,)).fetchone()[0] == ende.isoformat()
    b = con.execute("SELECT snapshot FROM auftrag_belege WHERE auftrag_id=? AND art='abholung'", (aid,)).fetchone()
    assert f"6 Monaten ab Abholung (bis {ende.strftime('%d.%m.%Y')})" in json.loads(b["snapshot"])["garantie"]
    seite = client.get(f"/auftraege/{aid}").get_data(as_text=True)
    assert "6 Monate bis" in seite and "läuft" in seite
    # spätere Rechnung zum Auftrag nennt das gespeicherte Ende
    assert ende.strftime("%d.%m.%Y") in gar.rechnungstext(con, d)


def test_garantiepruefung_nutzt_gespeichertes_ende(client, con):
    kid = kunde_anlegen(client)
    alt = auftrag_mit_annahme(client, kid, seriennummer="356789012345678")
    post(client, f"/auftraege/{alt}/status", status="erledigt", ohne_kva="1")
    post(client, f"/auftraege/{alt}/abgeholt")
    assert client.get("/auftraege/geraet-pruefen?sn=356789012345678").get_json()[0]["laeuft"]
    # gespeichertes Garantieende zählt (nicht neu berechnet aus heutigen Einstellungen)
    con.execute("UPDATE auftraege SET garantie_ende=? WHERE id=?", ("2026-01-31", alt))
    v = client.get("/auftraege/geraet-pruefen?sn=356789012345678").get_json()[0]
    assert not v["laeuft"] and "31.01.2026" in v["garantie"] and "abgelaufen" in v["garantie"]
    # keine Garantie vereinbart
    ohne = auftrag_mit_annahme(client, kid, seriennummer="IMEI99887766", garantie_monate="0")
    post(client, f"/auftraege/{ohne}/status", status="erledigt", ohne_kva="1")
    post(client, f"/auftraege/{ohne}/abgeholt")
    assert con.execute("SELECT garantie_ende FROM auftraege WHERE id=?", (ohne,)).fetchone()[0] is None
    assert "keine freiwillige Garantie" in client.get("/auftraege/geraet-pruefen?sn=IMEI99887766").get_json()[0]["garantie"]


def test_wiedererkennung_und_garantiefall(client, con):
    kid = kunde_anlegen(client)
    alt = auftrag_mit_annahme(client, kid, seriennummer="356789012345678")
    post(client, f"/auftraege/{alt}/status", status="erledigt", ohne_kva="1")
    post(client, f"/auftraege/{alt}/abgeholt")
    # Suche ignoriert Leerzeichen/Bindestriche
    liste = client.get("/auftraege/geraet-pruefen?sn=3567 8901-2345 678").get_json()
    assert len(liste) == 1 and liste[0]["laeuft"] and "12 Monate bis" in liste[0]["garantie"]
    assert client.get(f"/auftraege/geraet-pruefen?sn=356789012345678&ohne={alt}").get_json() == []
    # Garantiefall anlegen
    neu = auftrag_mit_annahme(client, kid, seriennummer="356789012345678", auftragsart="garantie",
                              garantie_bezug_id=str(alt), interne_kosten="35,00", interne_kosten_notiz="Akku")
    a = con.execute("SELECT * FROM auftraege WHERE id=?", (neu,)).fetchone()
    assert a["auftragsart"] == "garantie" and a["garantie_bezug_id"] == alt and a["interne_kosten"] == 3500
    seite = client.get(f"/auftraege/{neu}").get_data(as_text=True)
    assert "war schon 1× hier" in seite and "Garantiefall" in seite and "35,00" in seite
    # Erledigt ohne KVA-Rückfrage und ohne Rechnung
    post(client, f"/auftraege/{neu}/status", status="erledigt")
    a = con.execute("SELECT * FROM auftraege WHERE id=?", (neu,)).fetchone()
    assert a["status"] == "erledigt" and a["rechnung_id"] is None
    assert "Garantiefälle zu diesem Auftrag" in client.get(f"/auftraege/{alt}").get_data(as_text=True)


def test_artikel_garantie_und_einstellung(client, con):
    post(client, "/einstellungen/annahme", garantie_monate="6", annahme_zubehoer="Ladekabel",
         kva_gebuehren="Sonstige Geräte = 29,00", annahme_datenschutz="", annahme_abholbedingungen="", abholschein_text="")
    assert dbm.einstellungen(con)["garantie_monate"] == 6
    r = post(client, "/artikel/neu", name="Akkutausch iPhone", preis="89,00", teilekosten="30,00", einheit="pauschal",
             typ="leistung", steuersatz="19", aktiv="1", garantie_monate="3")
    assert r.status_code == 302
    assert con.execute("SELECT garantie_monate FROM artikel WHERE name='Akkutausch iPhone'").fetchone()[0] == 3
    kid = kunde_anlegen(client)
    aid = auftrag_mit_annahme(client, kid)
    assert "Standard: 6" in client.get(f"/auftraege/{aid}").get_data(as_text=True)
    a = con.execute("SELECT * FROM auftraege WHERE id=?", (aid,)).fetchone()
    assert gar.monate(a, dbm.einstellungen(con)) == 6
