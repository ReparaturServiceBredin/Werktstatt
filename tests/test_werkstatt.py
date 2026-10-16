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


def test_kalender_einplanen_verschieben_entfernen(client, con):
    from rsb import kalender as kal
    aid = auftrag(client, kunde_anlegen(client))
    seite = client.get("/kalender?datum=2026-10-21").get_data(as_text=True)
    assert "Nicht eingeplant" in seite and 'data-dauer="75"' in seite  # Ölwechsel 45 + Reifenwechsel 30
    r = client.post(f"/auftraege/{aid}/termin", headers={"X-Requested-With": "fetch"},
                    data={"csrf": "test-token", "beginn": "2026-10-21T08:07"})
    assert r.get_json()["ok"]
    a = con.execute("SELECT termin_beginn, termin_dauer FROM auftraege WHERE id=?", (aid,)).fetchone()
    assert (a["termin_beginn"], a["termin_dauer"]) == ("2026-10-21T08:00", 75)  # auf Viertelstunde gerundet
    seite = client.get("/kalender?datum=2026-10-23").get_data(as_text=True)  # gleiche Woche
    assert "08:00–09:15" in seite and "HN-AB 123" in seite and "KW 43" in seite
    assert "📅 Mi 21.10.2026, 08:00–09:15 Uhr" in client.get("/auftraege").get_data(as_text=True)
    post(client, f"/auftraege/{aid}/termin", aendern="15")
    assert con.execute("SELECT termin_dauer FROM auftraege WHERE id=?", (aid,)).fetchone()[0] == 90
    post(client, f"/auftraege/{aid}/termin", beginn="2026-10-22T13:30")
    post(client, f"/auftraege/{aid}/termin", entfernen="1")
    assert con.execute("SELECT termin_beginn FROM auftraege WHERE id=?", (aid,)).fetchone()[0] is None
    verlauf = [v["ereignis"] for v in con.execute("SELECT ereignis FROM auftrag_verlauf WHERE auftrag_id=?", (aid,))]
    assert {"Termin geplant", "Termin verschoben", "Termin entfernt"} <= set(verlauf)
    # ungültige Eingaben
    r = client.post(f"/auftraege/{aid}/termin", headers={"X-Requested-With": "fetch"},
                    data={"csrf": "test-token", "beginn": "morgen"})
    assert r.status_code == 400 and not r.get_json()["ok"]
    assert kal.text("2026-10-21T08:00", 75) == "Mi 21.10.2026, 08:00–09:15 Uhr"


def test_ueberschneidende_termine_nebeneinander(client, con):
    kid = kunde_anlegen(client)
    ids = [auftrag(client, kid) for _ in range(3)]
    for aid, beginn in zip(ids, ["2026-10-21T08:00", "2026-10-21T08:30", "2026-10-21T10:00"]):
        post(client, f"/auftraege/{aid}/termin", beginn=beginn)
    from rsb import kalender as kal, db as dbm
    from rsb.views import AUFTRAG_SQL
    from datetime import date
    w = kal.woche(con, date(2026, 10, 19), dbm.einstellungen(con), AUFTRAG_SQL)
    mi = next(t for t in w["tage"] if t["datum"] == date(2026, 10, 21))
    assert [(t["bahn"], t["bahnen"]) for t in mi["termine"]] == [(0, 2), (1, 2), (0, 1)]


def test_termin_im_auftragsformular(client, con):
    aid = auftrag(client, kunde_anlegen(client), termin_beginn="2026-10-24T09:00", termin_dauer="")
    a = con.execute("SELECT termin_beginn, termin_dauer FROM auftraege WHERE id=?", (aid,)).fetchone()
    assert (a["termin_beginn"], a["termin_dauer"]) == ("2026-10-24T09:00", 75)
    assert "Kalender" in client.get("/einstellungen/annahme").get_data(as_text=True)


def test_heute_auf_der_uebersicht_und_kalender_skript(client, con):
    from rsb.hilfen import heute_datum
    aid = auftrag(client, kunde_anlegen(client))
    post(client, f"/auftraege/{aid}/termin", beginn=f"{heute_datum().isoformat()}T09:00")
    seite = client.get("/").get_data(as_text=True)
    assert "Heute in der Werkstatt" in seite and "09:00–10:15 Uhr" in seite and "HN-AB 123" in seite
    k = client.get("/kalender").get_data(as_text=True)
    assert "const PX = ," not in k and "kal-jetzt" in k


def test_getrennt_von_der_rsb_buchhaltung(app, client, monkeypatch):
    """Eigenes Cookie, eigener Port, eigener Datenordner: beide Programme laufen auf einem PC nebeneinander."""
    import socket
    from rsb import __main__ as start, datenort
    assert app.config["SESSION_COOKIE_NAME"] == "werkstatt_sauter"
    assert client.get("/version").get_json()["programm"] == "Werkstatt Sauter"
    assert start.STANDARD_PORT != 5000
    assert datenort.fester_ort().parts[-2] == "Werkstatt-Sauter"
    # Port belegt durch ein fremdes Programm → nächster freier Port
    s = socket.socket(); s.bind(("127.0.0.1", 0)); s.listen(1)
    belegt = s.getsockname()[1]
    try:
        assert start.freier_port("127.0.0.1", belegt) != belegt
    finally:
        s.close()
