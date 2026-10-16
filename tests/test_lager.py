"""Phase 6: Lager – Bewegungen, Reservierung/Ausbuchung/Rückbuchung, Mindestbestand, Inventur, Lagerwert."""
import hashlib
import re
import sqlite3
from pathlib import Path

import pytest

from conftest import kunde_anlegen, post
from test_annahme import auftrag_mit_annahme


def artikel_anlegen(client, con, name="Akku iPhone 13", ek="30,00", mindest="2", **extra):
    daten = dict(name=name, preis="89,00", teilekosten=ek, einheit="Stk.", typ="material", steuersatz="19",
                 aktiv="1", lagerfuehrend="1", mindestbestand=mindest, lagerort="Regal A2", ean="4006381333931",
                 herstellernr="661-23456", kompatibilitaet="iPhone 13, iPhone 13 Pro")
    daten.update(extra)
    r = post(client, "/artikel/neu", **daten)
    assert r.status_code == 302 and r.headers["Location"].endswith("#lager")
    return con.execute("SELECT id FROM artikel WHERE name=?", (name,)).fetchone()[0]


def bestand(con, aid):
    return con.execute("SELECT bestand FROM artikel WHERE id=?", (aid,)).fetchone()[0]


def test_bewegungen_unveraenderlich(client, con):
    art = artikel_anlegen(client, con)
    post(client, f"/lager/{art}/buchen", art="zugang", menge="5", grund="Erstbestand")
    post(client, f"/lager/{art}/buchen", art="abgang", menge="1", grund="Bruch beim Einbau")
    post(client, f"/lager/{art}/buchen", art="korrektur", menge="-1", grund="Zählfehler")
    post(client, f"/lager/{art}/buchen", art="zugang", menge="2", grund="")  # ohne Grund → abgelehnt
    assert bestand(con, art) == 3
    b = con.execute("SELECT * FROM lagerbewegungen WHERE artikel_id=? ORDER BY id", (art,)).fetchall()
    assert [x["menge"] for x in b] == [5, -1, -1] and [x["bestand_danach"] for x in b] == [5, 4, 3]
    assert b[0]["ek"] == 3000 and b[0]["benutzer"] and re.search(r"T\d\d:\d\d:\d\d", b[0]["zeitpunkt"])
    with pytest.raises(sqlite3.DatabaseError):
        con.execute("UPDATE lagerbewegungen SET menge=10 WHERE id=?", (b[0]["id"],))
    with pytest.raises(sqlite3.DatabaseError):
        con.execute("DELETE FROM lagerbewegungen WHERE id=?", (b[0]["id"],))
    # Bestand kann nicht über das Artikelformular überschrieben werden; lagerführend aus nur bei Bestand 0
    post(client, f"/artikel/{art}", name="Akku iPhone 13", preis="89,00", teilekosten="30,00", einheit="Stk.",
         typ="material", steuersatz="19", aktiv="1", bestand="99")
    assert bestand(con, art) == 3 and con.execute("SELECT lagerfuehrend FROM artikel WHERE id=?", (art,)).fetchone()[0]
    # Suche nach Kompatibilität
    assert "Akku iPhone 13" in client.get("/lager?q=13 Pro").get_data(as_text=True)
    assert "Akku iPhone 13" in client.get("/artikel?q=661-23456").get_data(as_text=True)
    seite = client.get("/pruefung").get_data(as_text=True)
    assert "Lagerbestand" in seite


def test_reservierung_ausbuchen_storno(client, con, app):
    art = artikel_anlegen(client, con, mindest="2")
    post(client, f"/lager/{art}/buchen", art="zugang", menge="3", grund="Lieferung")
    kid = kunde_anlegen(client)
    aid = auftrag_mit_annahme(client, kid)
    post(client, f"/auftraege/{aid}/material", artikel_id=str(art), menge="2")
    r = con.execute("SELECT * FROM lager_reservierungen WHERE auftrag_id=?", (aid,)).fetchone()
    assert r["status"] == "reserviert" and bestand(con, art) == 3
    # verfügbar 1 < Mindestbestand 2 → Warnliste
    assert "unter Mindestbestand" in client.get("/lager?ansicht=mindest").get_data(as_text=True)
    vorschlag = client.get("/lager/bestellvorschlag").get_data(as_text=True)
    assert "Akku iPhone 13" in vorschlag and f'name="menge_{art}" value="3"' in vorschlag  # 4 − 1 = 3
    csv = client.get("/lager/bestellvorschlag?format=csv").data.decode("utf-8-sig")
    assert csv.splitlines()[1].startswith("Akku iPhone 13;")
    # Mehr reservieren als verfügbar → Warnung, aber möglich
    r2 = post(client, f"/auftraege/{aid}/material", artikel_id=str(art), menge="5")
    assert r2.status_code == 302
    rid2 = con.execute("SELECT id FROM lager_reservierungen WHERE auftrag_id=? ORDER BY id DESC", (aid,)).fetchone()[0]
    post(client, f"/material/{rid2}/stornieren", grund="zu viel")
    # Erledigt → ausgebucht
    post(client, f"/auftraege/{aid}/status", status="erledigt", ohne_kva="1")
    assert bestand(con, art) == 1
    r = con.execute("SELECT * FROM lager_reservierungen WHERE id=?", (r["id"],)).fetchone()
    assert r["status"] == "ausgebucht" and r["bewegung_id"]
    # Rechnung festschreiben und stornieren → wieder eingebucht
    re_id = con.execute("SELECT rechnung_id FROM auftraege WHERE id=?", (aid,)).fetchone()[0]
    d = con.execute("SELECT * FROM dokumente WHERE id=?", (re_id,)).fetchone()
    client.post(f"/dokumente/{re_id}", data={
        "csrf": "test-token", "kunde_id": kid, "datum": "", "leistungsdatum": "2026-10-15", "zahlungsziel_tage": "",
        "betreff": d["betreff"], "einleitung": "x", "schlusstext": "y", "hinweise": "", "aktion": "festschreiben",
        "p_bezeichnung": ["Akkutausch"], "p_beschreibung": [""], "p_menge": ["1"], "p_einheit": ["pauschal"],
        "p_preis": ["89,00"], "p_teilekosten": ["30,00"], "p_steuersatz": ["19"], "p_leistungsart": ["Smartphone"],
        "p_artikel_id": [""]})
    assert con.execute("SELECT status FROM dokumente WHERE id=?", (re_id,)).fetchone()[0] == "festgeschrieben"
    post(client, f"/dokumente/{re_id}/stornieren", grund="Falscher Kunde")
    assert con.execute("SELECT status FROM dokumente WHERE id=?", (re_id,)).fetchone()[0] == "storniert"
    assert bestand(con, art) == 3
    assert con.execute("SELECT status FROM lager_reservierungen WHERE id=?", (r["id"],)).fetchone()[0] == \
        "zurueckgebucht"
    # Auftrag mit Lagerbuchungen ist nicht löschbar
    post(client, f"/auftraege/{aid}/loeschen")
    assert con.execute("SELECT 1 FROM auftraege WHERE id=?", (aid,)).fetchone()


def test_kva_reservieren_und_garantiekosten(client, con):
    art = artikel_anlegen(client, con, name="Display iPhone 13", ek="120,00")
    post(client, f"/lager/{art}/buchen", art="zugang", menge="2", grund="Lieferung")
    kid = kunde_anlegen(client)
    aid = auftrag_mit_annahme(client, kid, auftragsart="garantie", seriennummer="")
    r = post(client, f"/auftraege/{aid}/kva")
    kva = int(re.search(r"/dokumente/(\d+)", r.headers["Location"]).group(1))
    client.post(f"/dokumente/{kva}", data={
        "csrf": "test-token", "kunde_id": kid, "datum": "", "zahlungsziel_tage": "", "betreff": "KVA",
        "einleitung": "", "schlusstext": "", "hinweise": "", "aktion": "speichern",
        "p_bezeichnung": ["Display iPhone 13"], "p_beschreibung": [""], "p_menge": ["1"], "p_einheit": ["Stk."],
        "p_preis": ["199,00"], "p_teilekosten": ["120,00"], "p_steuersatz": ["19"], "p_leistungsart": ["Smartphone"],
        "p_artikel_id": [str(art)]})
    post(client, f"/auftraege/{aid}/material", aus_kva="1")
    post(client, f"/auftraege/{aid}/material", aus_kva="1")  # nicht doppelt
    assert con.execute("SELECT COUNT(*) FROM lager_reservierungen WHERE auftrag_id=?", (aid,)).fetchone()[0] == 1
    post(client, f"/auftraege/{aid}/status", status="erledigt")
    seite = client.get(f"/auftraege/{aid}").get_data(as_text=True)
    assert "Interne Kosten: <b>120,00 €</b>" in seite  # Display zum EK aus dem Lager


def test_inventur(client, con, app):
    a1 = artikel_anlegen(client, con, name="Akku A", ek="10,00", lagerort="A")
    a2 = artikel_anlegen(client, con, name="Akku B", ek="20,00", lagerort="B")
    post(client, f"/lager/{a1}/buchen", art="zugang", menge="5", grund="Erstbestand")
    post(client, f"/lager/{a2}/buchen", art="zugang", menge="2", grund="Erstbestand")
    r = post(client, "/lager/inventur/neu", stichtag="2026-12-31", bezeichnung="Jahresinventur")
    iid = int(re.search(r"/inventur/(\d+)", r.headers["Location"]).group(1))
    post(client, "/lager/inventur/neu", stichtag="2026-12-31")  # zweite offene Inventur → abgelehnt
    assert con.execute("SELECT COUNT(*) FROM inventuren").fetchone()[0] == 1
    assert "______" in client.get(f"/lager/inventur/{iid}?druck=1").get_data(as_text=True)
    post(client, f"/lager/inventur/{iid}", **{f"ist_{a1}": "4"})
    post(client, f"/lager/inventur/{iid}/abschliessen")  # Akku B ungezählt → abgelehnt
    assert con.execute("SELECT status FROM inventuren WHERE id=?", (iid,)).fetchone()[0] == "offen"
    # Handy-Zählung per QR-Code (ohne Anmeldung aus dem WLAN)
    seite = post(client, f"/lager/inventur/{iid}/handy").get_data(as_text=True)
    token = re.search(r"/m/inventur/([A-Za-z0-9_-]+)", seite).group(1)
    handy = app.test_client()
    fern = {"REMOTE_ADDR": "192.168.178.60"}
    s = handy.get(f"/m/inventur/{token}", environ_base=fern).get_data(as_text=True)
    csrf = re.search(r'name="csrf" value="([^"]+)"', s).group(1)
    handy.post(f"/m/inventur/{token}", environ_base=fern, data={"csrf": csrf, f"ist_{a2}": "3"})
    post(client, f"/lager/inventur/{iid}/abschliessen")
    inv = con.execute("SELECT * FROM inventuren WHERE id=?", (iid,)).fetchone()
    assert inv["status"] == "abgeschlossen" and inv["differenzen"] == 2 and inv["lagerwert"] == 4 * 1000 + 3 * 2000
    assert bestand(con, a1) == 4 and bestand(con, a2) == 3
    pfad = Path(app.config["DATEN"]) / inv["pdf_datei"]
    assert hashlib.sha256(pfad.read_bytes()).hexdigest() == inv["pdf_sha256"]
    assert client.get(f"/lager/inventur/{iid}/protokoll.pdf").data.startswith(b"%PDF")
    assert handy.get(f"/m/inventur/{token}", environ_base=fern).status_code == 410  # abgeschlossen
    with pytest.raises(sqlite3.DatabaseError):
        con.execute("UPDATE inventur_positionen SET ist=99 WHERE inventur_id=?", (iid,))
    # Lagerwert zum Stichtag
    assert "100,00 €" in client.get("/lager?ansicht=wert").get_data(as_text=True)
    assert "Kein Bestand zum Stichtag" in client.get("/lager?ansicht=wert&stichtag=2020-01-01").get_data(as_text=True)
