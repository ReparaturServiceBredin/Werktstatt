"""Werkstatt Sauter: Fahrzeugdaten am Auftrag und Checkliste je Leistung."""
import re

from rsb import checkliste as ckl

from conftest import kunde_anlegen, post


def auftrag(client, kid, **extra):
    daten = {"kunde_id": kid, "geraet": "VW Golf VII 1.6 TDI", "kennzeichen": "hn-ab 123", "km_stand": "123.456",
             "seriennummer": "wvwzzz1kzaw000001", "erstzulassung": "2015-03-20", "hu_bis": "2027-05",
             "leistung": ["Ölwechsel", "Reifenwechsel"], "fehler": "Ölwechsel mit Filter, Sommerräder drauf",
             "annahme_felder": "1"}
    daten.update(extra)
    r = post(client, "/auftraege/neu", **daten)
    assert r.status_code == 302, r.data[:500]
    return int(re.search(r"/auftraege/(\d+)", r.headers["Location"]).group(1))


def test_fahrzeugdaten_und_checkliste_aus_vorlagen(client, con):
    aid = auftrag(client, kunde_anlegen(client))
    a = con.execute("SELECT * FROM auftraege WHERE id=?", (aid,)).fetchone()
    assert a["auftragsnr"].startswith("AU-")
    assert (a["kennzeichen"], a["km_stand"], a["seriennummer"]) == ("HN-AB 123", 123456, "WVWZZZ1KZAW000001")
    assert a["leistungsart"] == "Ölwechsel, Reifenwechsel" and a["hu_bis"] == "2027-05"
    schritte = ckl.liste(con, aid)
    vorlagen = ckl.vorlagen({"checklisten": con.execute(
        "SELECT json_extract(wert, '$') FROM einstellungen WHERE schluessel='checklisten'").fetchone()[0]})
    assert len(schritte) == len(vorlagen["Ölwechsel"]) + len(vorlagen["Reifenwechsel"])
    assert {s["leistung"] for s in schritte} == {"Ölwechsel", "Reifenwechsel"}
    seite = client.get(f"/auftraege/{aid}").get_data(as_text=True)
    assert "Ölfilter gewechselt" in seite and f"0/{len(schritte)}" in seite
    tafel = client.get("/auftraege").get_data(as_text=True)
    assert "HN-AB 123" in tafel and f"0/{len(schritte)} erledigt" in tafel
    # Suche findet das Kennzeichen
    assert "VW Golf" in client.get("/suche.json?q=HN-AB").get_data(as_text=True)


def test_abhaken_eigene_schritte_und_leistung_abwaehlen(client, con):
    aid = auftrag(client, kunde_anlegen(client))
    s = ckl.liste(con, aid)
    oel = [x for x in s if x["leistung"] == "Ölwechsel"]
    reifen = [x for x in s if x["leistung"] == "Reifenwechsel"]
    r = client.post(f"/auftraege/{aid}/checkliste", headers={"X-Requested-With": "fetch"},
                    data={"csrf": "test-token", "aktion": "abhaken", "cid": oel[0]["id"], "erledigt": "1"})
    d = r.get_json()
    assert d["ok"] and d["erledigt"] == 1 and d["wann"]
    post(client, f"/auftraege/{aid}/checkliste", aktion="abhaken", cid=reifen[0]["id"], erledigt="1")
    post(client, f"/auftraege/{aid}/checkliste", aktion="hinzufuegen", text="  Scheibenwischer   tauschen ")
    assert ckl.liste(con, aid)[-1]["text"] == "Scheibenwischer tauschen"
    assert ckl.stand(con, aid) == (2, len(s) + 1)
    # Abgehakte Schritte lassen sich nicht entfernen
    r = post(client, f"/auftraege/{aid}/checkliste", aktion="entfernen", cid=oel[0]["id"])
    assert con.execute("SELECT 1 FROM auftrag_checkliste WHERE id=?", (oel[0]["id"],)).fetchone()
    # Reifenwechsel abwählen: offene Schritte weg, der abgehakte bleibt als Nachweis
    post(client, f"/auftraege/{aid}", kunde_id=con.execute("SELECT kunde_id FROM auftraege").fetchone()[0],
         leistung=["Ölwechsel"], annahme_felder="1", geraet="VW Golf", kennzeichen="HN-AB 123")
    rest = [x for x in ckl.liste(con, aid) if x["leistung"] == "Reifenwechsel"]
    assert [x["id"] for x in rest] == [reifen[0]["id"]]
    verlauf = [v["ereignis"] for v in con.execute("SELECT ereignis FROM auftrag_verlauf WHERE auftrag_id=?", (aid,))]
    assert "Checkliste: erledigt" in verlauf


def test_falscher_kilometerstand_wird_abgelehnt(client, con):
    r = post(client, "/auftraege/neu", kunde_id=kunde_anlegen(client), km_stand="viel", annahme_felder="1")
    assert r.status_code == 200 and "Kilometerstand" in r.get_data(as_text=True)
    assert not con.execute("SELECT 1 FROM auftraege").fetchone()


def test_annahmeschein_zeigt_fahrzeug(client, con):
    aid = auftrag(client, kunde_anlegen(client))
    seite = client.get(f"/auftraege/{aid}/unterschreiben/annahme").get_data(as_text=True)
    assert "HN-AB 123" in seite and "WVWZZZ1KZAW000001" in seite and "123.456 km" in seite
    assert "Ölwechsel, Reifenwechsel" in seite
