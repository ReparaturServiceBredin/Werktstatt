"""Phase 3: Annahmeschein / Abholschein mit digitaler Unterschrift, Gerätezugang, Handy per QR-Code."""
import base64
import hashlib
import io
import json
import re
import sqlite3
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from rsb import db as dbm

from conftest import kunde_anlegen, post
from test_auftraege import kva_mit_position
from test_auftrag_detail import bild, foto_hochladen


def unterschrift(leer=False):
    b = Image.new("RGBA", (600, 200), (0, 0, 0, 0))
    if not leer:
        ImageDraw.Draw(b).line([(40, 150), (200, 60), (320, 140), (560, 50)], fill=(11, 31, 77, 255), width=4)
    puffer = io.BytesIO()
    b.save(puffer, "PNG")
    return "data:image/png;base64," + base64.b64encode(puffer.getvalue()).decode()


def auftrag_mit_annahme(client, kid, **extra):
    daten = {"kunde_id": kid, "geraet": "iPhone 13", "leistungsart": "Smartphone", "seriennummer": "356789012345678",
             "fehler": "Akku hält nicht", "annahme_felder": "1", "zubehoer_check": ["Fahrzeugschlüssel", "Serviceheft"],
             "zubehoer_sonstiges": "rote Tasche", "zustand_eingang": "Kratzer am Rahmen", "kosten_obergrenze": "120,00",
             "kva_gewuenscht": "1", "kva_gebuehr": "19,90", "fertig_bis": "2026-10-20", "zugang_art": "pin",
             "zugang_wert": "4711"}
    daten.update(extra)
    r = post(client, "/auftraege/neu", **daten)
    assert r.status_code == 302, r.data[:500]
    assert r.headers["Location"].endswith("#annahmeschein")
    return int(re.search(r"/auftraege/(\d+)", r.headers["Location"]).group(1))


def unterschreiben(client, aid, art="annahme", **extra):
    daten = {"unterschrift": unterschrift(), "unterzeichner": "Anna Müller", "bestaetigt": "1"}
    daten.update(extra)
    return post(client, f"/auftraege/{aid}/unterschreiben/{art}", **daten)


def test_annahmefelder_und_verschluesselter_zugang(client, con):
    kid = kunde_anlegen(client)
    aid = auftrag_mit_annahme(client, kid)
    a = con.execute("SELECT * FROM auftraege WHERE id=?", (aid,)).fetchone()
    assert a["zubehoer"] == "Fahrzeugschlüssel, Serviceheft, rote Tasche"
    assert a["kosten_obergrenze"] == 12000 and a["kva_gebuehr"] == 1990 and a["kva_gewuenscht"] == 1
    assert a["fertig_bis"] == "2026-10-20" and a["zustand_eingang"] == "Kratzer am Rahmen"
    assert a["zugang_art"] == "pin" and a["zugang_geheim"] and "4711" not in a["zugang_geheim"]
    seite = client.get(f"/auftraege/{aid}").get_data(as_text=True)
    assert "4711" not in seite
    assert 'value="Fahrzeugschlüssel" checked' in seite and 'value="rote Tasche"' in seite

    # Anzeigen wird protokolliert
    r = post(client, f"/auftraege/{aid}/zugang")
    assert r.get_json()["wert"] == "4711"
    assert con.execute("SELECT 1 FROM auftrag_verlauf WHERE auftrag_id=? AND ereignis='Gerätezugang angezeigt'",
                       (aid,)).fetchone()

    # Erledigt → Zugangsdaten automatisch gelöscht
    post(client, f"/auftraege/{aid}/status", status="erledigt", ohne_kva="1")
    a = con.execute("SELECT * FROM auftraege WHERE id=?", (aid,)).fetchone()
    assert a["status"] == "erledigt" and a["zugang_geheim"] is None and a["zugang_geloescht_am"]
    assert con.execute("SELECT details FROM auftrag_verlauf WHERE auftrag_id=? AND ereignis='Gerätezugang gelöscht'",
                       (aid,)).fetchone()["details"].startswith("Auftrag abgeschlossen")


def test_zugang_aendern_und_manuell_loeschen(client, con):
    kid = kunde_anlegen(client)
    aid = auftrag_mit_annahme(client, kid)
    form = {"kunde_id": kid, "status": "offen", "geraet": "iPhone 13", "annahme_felder": "1", "zugang_art": "pin",
            "zugang_wert": ""}
    post(client, f"/auftraege/{aid}", **form)  # leer = bleibt erhalten
    assert con.execute("SELECT zugang_geheim FROM auftraege WHERE id=?", (aid,)).fetchone()[0]
    post(client, f"/auftraege/{aid}", **{**form, "zugang_loeschen": "1"})
    assert con.execute("SELECT zugang_geheim FROM auftraege WHERE id=?", (aid,)).fetchone()[0] is None
    post(client, f"/auftraege/{aid}", **{**form, "zugang_art": "telefonisch"})
    assert con.execute("SELECT zugang_art FROM auftraege WHERE id=?", (aid,)).fetchone()[0] == "telefonisch"


def test_unterschrift_archiviert_unveraenderlich(client, con, app):
    kid = kunde_anlegen(client)
    aid = auftrag_mit_annahme(client, kid)
    foto_hochladen(client, f"/auftraege/{aid}/fotos", bild())
    # Leere Unterschrift / fehlende Bestätigung werden abgelehnt
    unterschreiben(client, aid, unterschrift=unterschrift(leer=True))
    unterschreiben(client, aid, bestaetigt="")
    assert not con.execute("SELECT 1 FROM auftrag_belege").fetchone()

    r = unterschreiben(client, aid)
    assert r.status_code == 302
    b = con.execute("SELECT * FROM auftrag_belege WHERE auftrag_id=?", (aid,)).fetchone()
    assert b["nummer"].endswith("-AN1") and b["unterzeichner"] == "Anna Müller" and b["quelle"] == "PC/Tablet"
    assert re.match(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d[+-]\d\d:\d\d$", b["unterschrieben_am"])
    pfad = Path(app.config["DATEN"]) / b["pdf_datei"]
    daten = pfad.read_bytes()
    assert daten.startswith(b"%PDF") and hashlib.sha256(daten).hexdigest() == b["pdf_sha256"]
    snap = json.loads(b["snapshot"])
    assert snap["kosten_obergrenze"] == 12000 and len(snap["fotos"]) == 1 and "4711" not in b["snapshot"]
    assert "hinterlegt (verschlüsselt" in snap["zugang"]
    assert client.get(f"/belege/{b['id']}.pdf").data == daten
    assert con.execute("SELECT 1 FROM auftrag_verlauf WHERE auftrag_id=? AND ereignis='Annahmeschein unterschrieben'",
                       (aid,)).fetchone()

    with pytest.raises(sqlite3.DatabaseError):
        con.execute("UPDATE auftrag_belege SET unterzeichner='X' WHERE id=?", (b["id"],))
    with pytest.raises(sqlite3.DatabaseError):
        con.execute("DELETE FROM auftrag_belege WHERE id=?", (b["id"],))
    # Auftrag mit unterschriebenem Schein lässt sich nicht löschen
    post(client, f"/auftraege/{aid}/loeschen")
    assert con.execute("SELECT 1 FROM auftraege WHERE id=?", (aid,)).fetchone()

    # Änderung nach Unterschrift → Hinweis; zweiter Schein bekommt AN2
    post(client, f"/auftraege/{aid}", kunde_id=kid, status="offen", geraet="iPhone 13", annahme_felder="1",
         kosten_obergrenze="200,00", zugang_art="pin")
    assert "nach der letzten Unterschrift geändert" in client.get(f"/auftraege/{aid}").get_data(as_text=True)
    unterschreiben(client, aid)
    assert con.execute("SELECT nummer FROM auftrag_belege ORDER BY id DESC").fetchone()[0].endswith("-AN2")

    # Manipuliertes PDF wird erkannt
    pfad.write_bytes(daten + b"x")
    assert client.get(f"/belege/{b['id']}.pdf").status_code == 409


def test_abholschein_und_vorschau(client, con):
    kid = kunde_anlegen(client)
    aid = auftrag_mit_annahme(client, kid)
    r = client.get(f"/auftraege/{aid}/schein/annahme.pdf")
    assert r.status_code == 200 and r.data.startswith(b"%PDF")
    assert client.get(f"/auftraege/{aid}/schein/abholung.pdf").data.startswith(b"%PDF")
    assert "Auftrag laut Kunde" in client.get(f"/auftraege/{aid}/unterschreiben/annahme").get_data(as_text=True)
    unterschreiben(client, aid, art="abholung")
    a = con.execute("SELECT * FROM auftraege WHERE id=?", (aid,)).fetchone()
    assert a["abgeholt_am"] and a["zugang_geheim"] is None
    b = con.execute("SELECT * FROM auftrag_belege WHERE auftrag_id=?", (aid,)).fetchone()
    assert b["art"] == "abholung" and b["nummer"].endswith("-AB1")
    assert "vollständig und in ordnungsgemäßem Zustand" in json.loads(b["snapshot"])["erklaerung"]
    r = client.get(f"/belege/{b['id']}/email")
    assert r.status_code == 200 and "anna@example.com" in r.get_data(as_text=True)


def test_kva_abgelehnt_gebuehr_in_rechnung(client, con):
    kid = kunde_anlegen(client)
    aid = auftrag_mit_annahme(client, kid, geraet="Xiaomi 14T Pro")
    kva = kva_mit_position(client, con, aid)
    r = post(client, f"/dokumente/{kva}/kva-status", kva_status="abgelehnt")
    assert con.execute("SELECT kva_status FROM dokumente WHERE id=?", (kva,)).fetchone()[0] == "abgelehnt"
    # Bei Ablehnung wird sofort ein Rechnungsentwurf über die Pauschale vorgeschlagen
    re_id = con.execute("SELECT rechnung_id FROM auftraege WHERE id=?", (aid,)).fetchone()[0]
    assert re_id and r.headers["Location"].endswith(f"/dokumente/{re_id}")
    pos = con.execute("SELECT * FROM positionen WHERE dokument_id=?", (re_id,)).fetchall()
    assert len(pos) == 1 and pos[0]["einzelpreis"] == 1990
    assert pos[0]["bezeichnung"] == "Kostenvoranschlag / Fehlerdiagnose – Gerät: Xiaomi 14T Pro"
    art = con.execute("SELECT * FROM artikel WHERE id=?", (pos[0]["artikel_id"],)).fetchone()
    assert art["name"] == "Kostenvoranschlag / Fehlerdiagnose"  # Leistung im Katalog angelegt
    # Abschluss erzeugt keinen zweiten Entwurf
    post(client, f"/auftraege/{aid}/status", status="erledigt")
    assert con.execute("SELECT rechnung_id FROM auftraege WHERE id=?", (aid,)).fetchone()[0] == re_id
    assert con.execute("SELECT COUNT(*) FROM artikel WHERE name='Kostenvoranschlag / Fehlerdiagnose'"
                       ).fetchone()[0] == 1


def test_kva_angenommen_gebuehr_entfaellt(client, con):
    kid = kunde_anlegen(client)
    aid = auftrag_mit_annahme(client, kid, geraet="Xiaomi 14T Pro")
    kva = kva_mit_position(client, con, aid)
    post(client, f"/dokumente/{kva}/kva-status", kva_status="angenommen")
    assert not con.execute("SELECT rechnung_id FROM auftraege WHERE id=?", (aid,)).fetchone()[0]
    assert "KVA-Pauschale entfällt" in client.get(f"/auftraege/{aid}").get_data(as_text=True)


def test_kva_gebuehr_nach_geraetetyp(client, con):
    kid = kunde_anlegen(client)
    # leer → Pauschale laut Gerätetyp
    aid = auftrag_mit_annahme(client, kid, geraetetyp="Motorrad", kva_gebuehr="")
    assert con.execute("SELECT kva_gebuehr FROM auftraege WHERE id=?", (aid,)).fetchone()[0] == 1900
    aid = auftrag_mit_annahme(client, kid, geraetetyp="PKW", kva_gebuehr="")
    assert con.execute("SELECT kva_gebuehr FROM auftraege WHERE id=?", (aid,)).fetchone()[0] == 2900
    # kostenlos überschreibt alles
    aid = auftrag_mit_annahme(client, kid, geraet="Xiaomi 14T Pro", geraetetyp="PKW",
                              kva_kostenlos="1")
    assert con.execute("SELECT kva_gebuehr FROM auftraege WHERE id=?", (aid,)).fetchone()[0] == 0
    kva = kva_mit_position(client, con, aid)
    post(client, f"/dokumente/{kva}/kva-status", kva_status="abgelehnt")
    assert not con.execute("SELECT rechnung_id FROM auftraege WHERE id=?", (aid,)).fetchone()[0]
    # Text mit Pauschale auf dem Annahmeschein (vor der Unterschrift sichtbar)
    aid = auftrag_mit_annahme(client, kid, geraetetyp="Motorrad", kva_gebuehr="")
    seite = client.get(f"/auftraege/{aid}/unterschreiben/annahme").get_data(as_text=True)
    assert "pauschal 19,00 €" in seite and "vollständig verrechnet" in seite
    unterschreiben(client, aid)
    snap = json.loads(con.execute("SELECT snapshot FROM auftrag_belege WHERE auftrag_id=?", (aid,)).fetchone()[0])
    assert "pauschal 19,00 €" in snap["kva_text"]


def test_handy_qr_und_zugriffsschutz(client, con, app):
    kid = kunde_anlegen(client)
    aid = auftrag_mit_annahme(client, kid)
    r = post(client, f"/auftraege/{aid}/handy/annahme")
    seite = r.get_data(as_text=True)
    assert r.status_code == 200 and "<svg" in seite
    token = re.search(r"/m/([A-Za-z0-9_-]+)", seite).group(1)

    with dbm.Transaktion(con):
        dbm.einstellungen_speichern({"login_aktiv": False}, con)
    handy = app.test_client()
    fern = {"REMOTE_ADDR": "192.168.178.50"}
    # Aus dem WLAN ohne Passwortschutz: alles außer den Token-Seiten gesperrt
    assert handy.get("/", environ_base=fern).status_code == 403
    assert handy.get(f"/auftraege/{aid}", environ_base=fern).status_code == 403
    assert handy.get("/m/falsch", environ_base=fern).status_code == 410
    seite = handy.get(f"/m/{token}", environ_base=fern).get_data(as_text=True)
    assert "Unterschrift" in seite and "seitenleiste" not in seite
    csrf = re.search(r'name="csrf" value="([^"]+)"', seite).group(1)
    r = handy.post(f"/m/{token}", environ_base=fern, data={"csrf": csrf, "unterschrift": unterschrift(),
                                                           "unterzeichner": "Anna Müller", "bestaetigt": "1"})
    assert "Vielen Dank" in r.get_data(as_text=True)
    b = con.execute("SELECT * FROM auftrag_belege WHERE auftrag_id=?", (aid,)).fetchone()
    assert b["quelle"] == "Handy (QR-Code)" and b["ip"] == "192.168.178.50"
    # Einmalig gültig
    assert handy.get(f"/m/{token}", environ_base=fern).status_code == 410
    assert client.get(f"/auftraege/{aid}/stand.json").get_json()["belege"] == 1


def test_handy_fotos_und_ablauf(client, con, app):
    kid = kunde_anlegen(client)
    aid = auftrag_mit_annahme(client, kid)
    seite = post(client, f"/auftraege/{aid}/handy/fotos").get_data(as_text=True)
    token = re.search(r"/m/([A-Za-z0-9_-]+)", seite).group(1)
    handy = app.test_client()
    fern = {"REMOTE_ADDR": "192.168.178.51"}
    seite = handy.get(f"/m/{token}", environ_base=fern).get_data(as_text=True)
    csrf = re.search(r'name="csrf" value="([^"]+)"', seite).group(1)
    r = handy.post(f"/m/{token}/fotos", environ_base=fern, content_type="multipart/form-data",
                   data={"csrf": csrf, "kategorie": "Fahrzeugeingang", "foto": (io.BytesIO(bild()), "handy.jpg")})
    assert r.get_json()["ok"]
    f = con.execute("SELECT * FROM auftrag_fotos WHERE auftrag_id=?", (aid,)).fetchone()
    assert f["benutzer"].endswith("(Handy)")
    assert handy.get(f"/m/{token}/foto/{f['id']}", environ_base=fern).status_code == 200
    # Abgelaufen
    con.execute("UPDATE mobil_zugaenge SET gueltig_bis='2020-01-01T00:00:00+01:00' WHERE token=?", (token,))
    assert handy.get(f"/m/{token}", environ_base=fern).status_code == 410
    r = handy.post(f"/m/{token}/fotos", environ_base=fern, content_type="multipart/form-data",
                   data={"csrf": csrf, "kategorie": "Fahrzeugeingang", "foto": (io.BytesIO(bild()), "x.jpg")})
    assert r.status_code == 410


def test_einstellungen_annahme(client, con):
    r = post(client, "/einstellungen/annahme", annahme_zubehoer="Ladekabel\nStift",
             kva_gebuehren="Laptop = 35\nSmartphone / Tablet = 15,00\nKonsole = 25,5", garantie_monate="12",
             annahme_kva_text="Pauschale {KVA-Gebühr}.", garantie_text="Garantie {Garantiedauer}.",
             annahme_datenschutz="DS", annahme_abholbedingungen="AB",
             abholschein_text="erhalten", handy_im_netz="1", handy_adresse="192.168.1.2:5000")
    assert r.status_code == 302
    e = dbm.einstellungen(con)
    assert e["kva_gebuehren"] == "Laptop = 35,00\nSmartphone / Tablet = 15,00\nKonsole = 25,50"
    assert e["handy_im_netz"] is True and e["annahme_kva_text"] == "Pauschale {KVA-Gebühr}."
    assert 'data-cent="2550"' in client.get("/auftraege/neu").get_data(as_text=True)
    # ohne gültigen Gerätetyp wird nicht gespeichert
    post(client, "/einstellungen/annahme", kva_gebuehren="Unsinn", garantie_monate="12")
    assert dbm.einstellungen(con)["kva_gebuehren"].startswith("Laptop = 35,00")
