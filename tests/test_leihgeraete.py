"""Leihgeräte: Ausgabe, Rückgabe mit/ohne Schaden, Kaution, Abrechnung, Schutz der Protokolle."""
import io
import re
import sqlite3
from datetime import date, timedelta

import pytest
from pypdf import PdfReader

from rsb import db as dbm

from conftest import kunde_anlegen, post
from test_auftrag_detail import bild, foto_hochladen
from test_auftraege import auftrag_anlegen, kva_mit_position


def geraet_anlegen(client, **felder):
    daten = dict(bezeichnung="Lenovo ThinkPad T14 #1", geraetetyp="Laptop", hersteller="Lenovo", modell="T14 Gen 2",
                 seriennummer="PF-12345", inventarnr="LG-001", zubehoer="Netzteil\nTasche\nMaus", zustand="gut",
                 anschaffung_am="2025-01-10", anschaffungswert="900,00", zeitwert="450,00", gebuehr_art="tag",
                 gebuehr_betrag="5,00", frei_tage="3", kaution="50,00")
    daten.update(felder)
    r = post(client, "/leihgeraete/neu", **daten)
    return int(re.search(r"/leihgeraete/(\d+)", r.headers["Location"]).group(1))


def vor_tagen(tage, uhrzeit="10:00:00"):
    return f"{(date.today() - timedelta(days=tage)).isoformat()}T{uhrzeit}"


def ausgeben(client, aid, gid, **felder):
    seite = client.get(f"/auftraege/{aid}/leihgeraet-ausgeben").get_data(as_text=True)
    token = re.search(r'name="upload_token" value="([0-9a-f]+)"', seite).group(1)
    daten = dict(upload_token=token, geraet_id=gid, ausgabe_am=vor_tagen(5),
                 rueckgabe_geplant=(date.today() + timedelta(days=2)).isoformat(),
                 zubehoer=["Netzteil", "Tasche", "Maus"], gebuehr_art="tag", gebuehr_betrag="5,00", frei_tage="3",
                 kaution_erhalten="on", kaution_betrag="50,00", kaution_zahlart="Bar", zustand_ausgabe="Kratzer am Deckel")
    daten.update(felder)
    r = client.post(f"/auftraege/{aid}/leihgeraet-ausgeben", data={"csrf": "test-token", **daten})
    m = re.search(r"/leihen/(\d+)", r.headers.get("Location", ""))
    return (int(m.group(1)) if m else None), token, r


def zuruecknehmen(client, lid, **felder):
    seite = client.get(f"/leihen/{lid}/rueckgabe").get_data(as_text=True)
    token = re.search(r'name="upload_token" value="([0-9a-f]+)"', seite).group(1)
    daten = dict(upload_token=token, rueckgabe_am=f"{date.today().isoformat()}T16:30:15",
                 zubehoer=["Netzteil", "Tasche", "Maus"], zustand="einwandfrei", rueckgabe_notiz="Daten gelöscht",
                 gebuehr="")
    daten.update(felder)
    return client.post(f"/leihen/{lid}/rueckgabe", data={"csrf": "test-token", **daten}), token


def pdf_text(daten):
    return "\n".join(s.extract_text() for s in PdfReader(io.BytesIO(daten)).pages)


@pytest.fixture
def basis(client, con):
    kid = kunde_anlegen(client)
    aid = auftrag_anlegen(client, kid)
    gid = geraet_anlegen(client)
    return kid, aid, gid


def test_geraet_anlegen_liste_katalog(client, con, basis):
    kid, aid, gid = basis
    g = con.execute("SELECT * FROM leihgeraete WHERE id=?", (gid,)).fetchone()
    assert g["status"] == "verfuegbar" and g["zeitwert"] == 45000 and g["frei_tage"] == 3
    assert g["zubehoer"] == '["Netzteil", "Tasche", "Maus"]'
    html = client.get("/leihgeraete").get_data(as_text=True)
    assert "Lenovo ThinkPad T14 #1" in html and "Verfügbar" in html
    assert "ThinkPad" in client.get("/leihgeraete?q=PF-123").get_data(as_text=True)
    assert "ThinkPad" not in client.get("/leihgeraete?status=defekt").get_data(as_text=True)
    namen = {r[0] for r in con.execute("SELECT name FROM artikel")}
    assert {"Leihgebühr pauschal", "Leihgebühr pro Tag", "Schadenersatz Leihgerät"} <= namen
    assert con.execute("SELECT steuersatz FROM artikel WHERE name='Leihgebühr pro Tag'").fetchone()[0] == 19
    # Bearbeiten -> Historie
    post(client, f"/leihgeraete/{gid}", bezeichnung="Lenovo ThinkPad T14 #1", gebuehr_art="pauschal",
         gebuehr_betrag="15,00", zubehoer="Netzteil")
    assert con.execute("SELECT gebuehr_art FROM leihgeraete WHERE id=?", (gid,)).fetchone()[0] == "pauschal"
    assert "Stammdaten geändert" in client.get(f"/leihgeraete/{gid}").get_data(as_text=True)
    # nicht löschbar
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("DELETE FROM leihgeraete WHERE id=?", (gid,))


def test_ausgabe_protokoll_karte(client, con, basis):
    kid, aid, gid = basis
    seite = client.get(f"/auftraege/{aid}/leihgeraet-ausgeben").get_data(as_text=True)
    token = re.search(r'name="upload_token" value="([0-9a-f]+)"', seite).group(1)
    assert foto_hochladen(client, "/leihen/fotos/vorab", bild(), kategorie="Leihgerät Ausgabe",
                          upload_token=token).get_json()["ok"]
    # Fehlversuch (kein Gerät) -> Foto bleibt
    lid, token2, r = ausgeben(client, aid, "")
    assert lid is None and "NICHT ausgegeben" in r.get_data(as_text=True) and token2 == token
    lid, _, _ = ausgeben(client, aid, gid, zubehoer=["Netzteil", "Tasche"])
    le = con.execute("SELECT * FROM leihen WHERE id=?", (lid,)).fetchone()
    assert le["leihnr"].startswith("LV-") and le["kaution_status"] == "gehalten" and le["kaution_betrag"] == 5000
    assert le["zubehoer_ausgabe"] == '["Netzteil", "Tasche"]'
    assert re.match(r"\d{4}-\d\d-\d\dT10:00:00[+-]\d\d:\d\d", le["ausgabe_am"])
    assert con.execute("SELECT status FROM leihgeraete WHERE id=?", (gid,)).fetchone()[0] == "verliehen"
    f = con.execute("SELECT * FROM auftrag_fotos WHERE leihe_id=?", (lid,)).fetchone()
    assert f["auftrag_id"] == aid and f["leihgeraet_id"] == gid and f["kategorie"] == "Leihgerät Ausgabe"
    # Verlauf Auftrag + Gerät
    assert con.execute("SELECT 1 FROM auftrag_verlauf WHERE auftrag_id=? AND ereignis='Leihgerät ausgegeben'",
                       (aid,)).fetchone()
    assert con.execute("SELECT 1 FROM leihgeraet_verlauf WHERE geraet_id=? AND ereignis='Verliehen'", (gid,)).fetchone()
    # Karte, Auftrag, Kunde, Liste
    assert "🔁 Leihgerät" in client.get("/auftraege").get_data(as_text=True)
    assert "Leihgerät zurücknehmen" in client.get(f"/auftraege/{aid}").get_data(as_text=True)
    assert "Hat aktuell" in client.get(f"/kunden/{kid}").get_data(as_text=True)
    assert "Verliehen" in client.get("/leihgeraete").get_data(as_text=True)
    # Leihvertrag-PDF
    text = pdf_text(client.get(f"/leihen/{lid}/ausgabe.pdf").data)
    for t in ["Leihvertrag", "PF-12345", "Netzteil", "Leihbedingungen", "Unterschrift Kunde", "50,00 €",
              "eigenen Daten", "Kratzer am Deckel"]:
        assert t in text, t
    # Gerät ist nicht mehr auswählbar, zweite Ausgabe scheitert
    aid2 = auftrag_anlegen(client, kid)
    assert "kein Leihgerät verfügbar" in client.get(f"/auftraege/{aid2}/leihgeraet-ausgeben").get_data(as_text=True)
    r = client.post(f"/auftraege/{aid2}/leihgeraet-ausgeben", data={
        "csrf": "test-token", "geraet_id": gid, "gebuehr_art": "kostenlos", "ausgabe_am": ""})
    assert "nicht verfügbar" in r.get_data(as_text=True)
    assert con.execute("SELECT COUNT(*) FROM leihen").fetchone()[0] == 1
    # Ausgabe-Felder geschützt
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("UPDATE leihen SET zustand_ausgabe='anders' WHERE id=?", (lid,))
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("DELETE FROM leihen")


def test_ueberfaellig(client, con, basis):
    kid, aid, gid = basis
    ausgeben(client, aid, gid, rueckgabe_geplant=(date.today() - timedelta(days=1)).isoformat())
    assert "🔁 Leihgerät überfällig" in client.get("/auftraege").get_data(as_text=True)
    html = client.get("/leihgeraete").get_data(as_text=True)
    assert "zeile-rot" in html and "überfällig" in html
    assert 'title="überfällige Rückgaben">1<' in html


def test_rueckgabe_ohne_schaden_und_abrechnung(client, con, basis):
    kid, aid, gid = basis
    kva_mit_position(client, con, aid)
    lid, _, _ = ausgeben(client, aid, gid)
    r, token = zuruecknehmen(client, lid)
    assert r.status_code == 302, r.get_data(as_text=True)
    le = con.execute("SELECT * FROM leihen WHERE id=?", (lid,)).fetchone()
    # 5 Tage, 3 frei -> 2 × 5,00 €
    assert (le["tage"], le["gebuehr_berechnet"], le["zustand_rueckgabe"]) == (5, 1000, "einwandfrei")
    assert le["kaution_status"] == "zurueckzuzahlen"
    assert con.execute("SELECT status FROM leihgeraete WHERE id=?", (gid,)).fetchone()[0] == "verfuegbar"
    assert "Rückgabeprotokoll" in pdf_text(client.get(f"/leihen/{lid}/rueckgabe.pdf").data)
    # Kaution zurückzahlen
    post(client, f"/leihen/{lid}/kaution-zurueck")
    assert con.execute("SELECT kaution_status FROM leihen WHERE id=?", (lid,)).fetchone()[0] == "zurueckgezahlt"
    # Erledigt -> Rechnung mit KVA-Position + Leihgebühr
    r = client.post(f"/auftraege/{aid}/status", data={"csrf": "test-token", "status": "erledigt"},
                    headers={"X-Requested-With": "fetch"})
    rid = int(r.get_json()["rechnung_url"].rsplit("/", 1)[1])
    pos = con.execute("SELECT * FROM positionen WHERE dokument_id=? ORDER BY pos", (rid,)).fetchall()
    assert [p["bezeichnung"] for p in pos] == ["Displaytausch Xiaomi 14T Pro",
                                               "Leihgerät Lenovo ThinkPad T14 #1, 2 Tage à 5,00 €"]
    assert (pos[1]["menge"], pos[1]["einheit"], pos[1]["einzelpreis"]) == (2, "Tag", 500)
    assert pos[1]["artikel_id"] == con.execute("SELECT id FROM artikel WHERE name='Leihgebühr pro Tag'").fetchone()[0]
    d = con.execute("SELECT * FROM dokumente WHERE id=?", (rid,)).fetchone()
    assert d["summe_brutto"] == 14900 + 1000 and "Kaution" in d["hinweise"] and "zurückgezahlt" in d["hinweise"]
    assert con.execute("SELECT rechnung_id FROM leihen WHERE id=?", (lid,)).fetchone()[0] == rid


def test_rueckgabe_mit_schaden_kaution_verrechnung(client, con, basis):
    kid, aid, gid = basis
    lid, _, _ = ausgeben(client, aid, gid)
    # Schaden ohne Beschreibung -> Fehler, nichts gespeichert
    r, token = zuruecknehmen(client, lid, zubehoer=["Tasche", "Maus"])
    assert r.status_code == 200 and "NICHT gespeichert" in r.get_data(as_text=True)
    assert con.execute("SELECT rueckgabe_am FROM leihen WHERE id=?", (lid,)).fetchone()[0] is None
    foto_hochladen(client, "/leihen/fotos/vorab", bild("green"), kategorie="Leihgerät Rückgabe", upload_token=token)
    foto_hochladen(client, "/leihen/fotos/vorab", bild("black"), kategorie="Leihgerät Schaden", upload_token=token)
    r, _ = zuruecknehmen(client, lid, zubehoer=["Tasche", "Maus"], zustand="schaden",
                         schaden_beschreibung="Netzteil fehlt, Display-Ecke gesprungen", kostenart="reparatur",
                         schaden_betrag="80,00", interner_auftrag="on")
    assert r.status_code == 302
    s = con.execute("SELECT * FROM schadensfaelle WHERE leihe_id=?", (lid,)).fetchone()
    assert s["betrag"] == 8000 and s["kostenart"] == "reparatur" and s["interner_auftrag_id"]
    assert con.execute("SELECT status FROM leihgeraete WHERE id=?", (gid,)).fetchone()[0] == "defekt"
    le = con.execute("SELECT * FROM leihen WHERE id=?", (lid,)).fetchone()
    assert le["kaution_status"] == "verrechnet" and le["zubehoer_rueckgabe"] == '["Tasche", "Maus"]'
    fotos = {f["kategorie"]: f for f in con.execute("SELECT * FROM auftrag_fotos WHERE leihe_id=?", (lid,))}
    assert fotos["Leihgerät Schaden"]["schadensfall_id"] == s["id"]
    assert fotos["Leihgerät Rückgabe"]["schadensfall_id"] == s["id"]
    html = client.get(f"/leihen/{lid}").get_data(as_text=True)
    assert "noch vom kunden zu zahlen" in html.lower() and "30,00 €" in html and "fehlt" in html
    # Schadens-PDF mit Verrechnung und Fotos
    text = pdf_text(client.get(f"/leihen/{lid}/schaden.pdf").data)
    for t in ["Schadensfall", "Netzteil fehlt", "Noch zu zahlen", "30,00 €", "FEHLT", "Zustand bei Rückgabe"]:
        assert t in text, t
    # Schutz
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("UPDATE schadensfaelle SET betrag=1")
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("DELETE FROM schadensfaelle")
    # interner Auftrag: keine Rechnung, Gerät danach wieder verfügbar
    intern = s["interner_auftrag_id"]
    assert "intern" in client.get("/auftraege").get_data(as_text=True)
    r = client.post(f"/auftraege/{intern}/status", data={"csrf": "test-token", "status": "erledigt"},
                    headers={"X-Requested-With": "fetch"})
    assert r.get_json() == {"ok": True, "rechnung_url": None}
    assert con.execute("SELECT rechnung_id FROM auftraege WHERE id=?", (intern,)).fetchone()[0] is None
    assert con.execute("SELECT status FROM leihgeraete WHERE id=?", (gid,)).fetchone()[0] == "verfuegbar"
    # Kundenauftrag erledigt -> Leihgebühr + Schaden in der Rechnung, Kaution verrechnet
    r = client.post(f"/auftraege/{aid}/status", data={"csrf": "test-token", "status": "erledigt", "ohne_kva": "1"},
                    headers={"X-Requested-With": "fetch"})
    rid = int(r.get_json()["rechnung_url"].rsplit("/", 1)[1])
    pos = con.execute("SELECT * FROM positionen WHERE dokument_id=? ORDER BY pos", (rid,)).fetchall()
    assert [p["bezeichnung"] for p in pos] == ["Leihgerät Lenovo ThinkPad T14 #1, 2 Tage à 5,00 €",
                                               "Schaden Leihgerät: Netzteil fehlt, Display-Ecke gesprungen"]
    hinweis = con.execute("SELECT hinweise FROM dokumente WHERE id=?", (rid,)).fetchone()[0]
    assert "noch zu zahlen 30,00 €" in hinweis and "Kaution" in hinweis
    # Kunde
    html = client.get(f"/kunden/{kid}").get_data(as_text=True)
    assert "Schadensfall" in html and "80,00 €" in html
    post(client, f"/kunden/{kid}/loeschen")
    assert con.execute("SELECT 1 FROM kunden WHERE id=?", (kid,)).fetchone()


def test_totalschaden_erstattung_und_storno(client, con, basis):
    kid, aid, gid = basis
    post(client, f"/leihgeraete/{gid}", bezeichnung="Lenovo ThinkPad T14 #1", gebuehr_art="kostenlos",
         zubehoer="Netzteil", zeitwert="40,00", kaution="50,00")
    lid, _, _ = ausgeben(client, aid, gid, gebuehr_art="kulanz", zubehoer=["Netzteil"])
    r, _ = zuruecknehmen(client, lid, zubehoer=[], zustand="schaden", schaden_beschreibung="Gerät verloren",
                         kostenart="totalschaden", schaden_betrag="40,00")
    assert con.execute("SELECT status FROM leihgeraete WHERE id=?", (gid,)).fetchone()[0] == "ausgemustert"
    le = con.execute("SELECT * FROM leihen WHERE id=?", (lid,)).fetchone()
    assert le["gebuehr_berechnet"] == 0
    html = client.get(f"/leihen/{lid}").get_data(as_text=True)
    assert "Erstattung an den Kunden" in html and "10,00 € zurückgezahlt" in html
    post(client, f"/leihen/{lid}/kaution-zurueck")
    assert con.execute("SELECT kaution_status FROM leihen WHERE id=?", (lid,)).fetchone()[0] == "zurueckgezahlt"
    # Schadensfall stornieren nur mit Grund
    sid = con.execute("SELECT id FROM schadensfaelle WHERE leihe_id=?", (lid,)).fetchone()[0]
    post(client, f"/schaeden/{sid}/stornieren", grund="")
    assert con.execute("SELECT storniert_am FROM schadensfaelle WHERE id=?", (sid,)).fetchone()[0] is None
    post(client, f"/schaeden/{sid}/stornieren", grund="Gerät wiedergefunden")
    assert con.execute("SELECT storno_grund FROM schadensfaelle WHERE id=?", (sid,)).fetchone()[0] == \
        "Gerät wiedergefunden"


def test_erledigt_mit_leihgeraet_draussen(client, con, basis):
    kid, aid, gid = basis
    kva_mit_position(client, con, aid)
    lid, _, _ = ausgeben(client, aid, gid)
    r = client.post(f"/auftraege/{aid}/status", data={"csrf": "test-token", "status": "erledigt"},
                    headers={"X-Requested-With": "fetch"})
    assert r.get_json()["leihe_offen"] is True
    r = post(client, f"/auftraege/{aid}/status", status="erledigt")
    assert r.headers["Location"].endswith("#leihgeraet")
    assert con.execute("SELECT status FROM auftraege WHERE id=?", (aid,)).fetchone()[0] == "offen"
    # später separat abrechnen
    r = client.post(f"/auftraege/{aid}/status", data={"csrf": "test-token", "status": "erledigt", "leihe_spaeter": "1"},
                    headers={"X-Requested-With": "fetch"})
    rid = int(r.get_json()["rechnung_url"].rsplit("/", 1)[1])
    assert con.execute("SELECT separat_abrechnen FROM leihen WHERE id=?", (lid,)).fetchone()[0] == 1
    assert con.execute("SELECT COUNT(*) FROM positionen WHERE dokument_id=?", (rid,)).fetchone()[0] == 1
    # Rechnung festschreiben (simuliert), dann Rückgabe -> eigene Rechnung
    con.execute("UPDATE dokumente SET status='festgeschrieben' WHERE id=?", (rid,))
    r, _ = zuruecknehmen(client, lid, abrechnen="on")
    neu = int(r.headers["Location"].rsplit("/", 1)[1])
    assert neu != rid
    d = con.execute("SELECT * FROM dokumente WHERE id=?", (neu,)).fetchone()
    assert d["typ"] == "rechnung" and d["kunde_id"] == kid and d["summe_brutto"] == 1000
    assert "Leihgerät" in d["betreff"]


def test_abrechnung_in_vorhandenen_entwurf_und_entwurf_loeschen(client, con, basis):
    kid, aid, gid = basis
    rid = int(post(client, f"/auftraege/{aid}/rechnung").headers["Location"].rsplit("/", 1)[1])
    lid, _, _ = ausgeben(client, aid, gid, gebuehr_art="pauschal", gebuehr_betrag="15,00")
    zuruecknehmen(client, lid, gebuehr="12,00")  # Betrag vor Übernahme geändert
    le = con.execute("SELECT * FROM leihen WHERE id=?", (lid,)).fetchone()
    assert le["gebuehr_berechnet"] == 1200 and "angepasst" in le["gebuehr_text"]
    r = post(client, f"/leihen/{lid}/abrechnen")
    assert r.headers["Location"].endswith(f"/dokumente/{rid}")
    p = con.execute("SELECT * FROM positionen WHERE dokument_id=?", (rid,)).fetchone()
    assert p["bezeichnung"] == "Leihgerät Lenovo ThinkPad T14 #1, pauschal" and p["einzelpreis"] == 1200
    # Entwurf löschen -> Leihe wieder abrechenbar
    post(client, f"/dokumente/{rid}/loeschen")
    assert con.execute("SELECT rechnung_id FROM leihen WHERE id=?", (lid,)).fetchone()[0] is None


def test_storno_email_einstellungen(client, con, basis, monkeypatch):
    kid, aid, gid = basis
    post(client, "/einstellungen/leihgeraete", leihbedingungen="Eigene Bedingung für {firma}.")
    lid, _, _ = ausgeben(client, aid, gid)
    assert "Eigene Bedingung für Reparatur Service Bredin." in pdf_text(client.get(f"/leihen/{lid}/ausgabe.pdf").data)
    from rsb import views
    gesendet = []
    monkeypatch.setattr(views, "senden", lambda con, e, an, betreff, text, pdf, name, *a: gesendet.append((an, name)))
    post(client, f"/leihen/{lid}/email", art="ausgabe", an="anna@example.com", betreff="Leihvertrag", text="Hallo")
    assert gesendet and gesendet[0][1].startswith("Leihvertrag_LV-")
    assert con.execute("SELECT 1 FROM auftrag_verlauf WHERE auftrag_id=? AND ereignis LIKE '%E-Mail%'",
                       (aid,)).fetchone()
    post(client, f"/leihen/{lid}/stornieren", grund="")
    assert con.execute("SELECT storniert_am FROM leihen WHERE id=?", (lid,)).fetchone()[0] is None
    post(client, f"/leihen/{lid}/stornieren", grund="Falsches Gerät erfasst")
    assert con.execute("SELECT status FROM leihgeraete WHERE id=?", (gid,)).fetchone()[0] == "verfuegbar"
    assert "storniert" in client.get(f"/leihen/{lid}").get_data(as_text=True)
    # Auftrag mit Leihe nicht löschbar
    post(client, f"/auftraege/{aid}/loeschen")
    assert con.execute("SELECT 1 FROM auftraege WHERE id=?", (aid,)).fetchone()


def test_seiten_laden(client, con, basis):
    kid, aid, gid = basis
    lid, _, _ = ausgeben(client, aid, gid)
    for url in ["/leihgeraete", "/leihgeraete?status=alle", "/leihgeraete/neu", f"/leihgeraete/{gid}",
                f"/leihen/{lid}", f"/leihen/{lid}/rueckgabe", f"/leihen/{lid}/email?art=ausgabe",
                f"/auftraege/{aid}", "/einstellungen/leihgeraete", f"/kunden/{kid}"]:
        assert client.get(url).status_code == 200, url


def test_migration_mit_sicherung(tmp_path):
    pfad = tmp_path / "werkstatt.db"
    dbm.initialisieren(str(pfad))
    con = dbm.verbinden(str(pfad))
    for t in ["leihgeraet_verlauf", "schadensfaelle", "leihen", "leihgeraete"]:
        con.execute(f"DROP TABLE {t}")
    con.close()
    dbm.initialisieren(str(pfad))
    assert list((tmp_path / "backups").glob("vor_update_*.db"))
    con = dbm.verbinden(str(pfad))
    assert con.execute("SELECT COUNT(*) FROM leihgeraete").fetchone()[0] == 0
    con.close()


def test_abrechnen_wartet_auf_erledigt(client, con, basis):
    kid, aid, gid = basis
    lid, _, _ = ausgeben(client, aid, gid)
    r, _ = zuruecknehmen(client, lid, abrechnen="on")  # Auftrag läuft noch, keine Rechnung -> nichts anlegen
    assert r.headers["Location"].endswith(f"/leihen/{lid}")
    assert con.execute("SELECT COUNT(*) FROM dokumente WHERE typ='rechnung'").fetchone()[0] == 0
    assert "automatisch in die Rechnung des Auftrags" in client.get(f"/leihen/{lid}").get_data(as_text=True)
    r = client.post(f"/auftraege/{aid}/status", data={"csrf": "test-token", "status": "erledigt", "ohne_kva": "1"},
                    headers={"X-Requested-With": "fetch"})
    rid = int(r.get_json()["rechnung_url"].rsplit("/", 1)[1])
    assert con.execute("SELECT rechnung_id FROM leihen WHERE id=?", (lid,)).fetchone()[0] == rid
    # ausdrücklich separat abrechnen geht auch bei laufendem Auftrag
    aid2 = auftrag_anlegen(client, kid)
    lid2, _, _ = ausgeben(client, aid2, gid)
    zuruecknehmen(client, lid2)
    r = post(client, f"/leihen/{lid2}/abrechnen")
    neu = int(r.headers["Location"].rsplit("/", 1)[1])
    assert con.execute("SELECT separat_abrechnen, rechnung_id FROM leihen WHERE id=?", (lid2,)).fetchone()[:] == (1, neu)
