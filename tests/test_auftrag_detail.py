"""Detailansicht Reparaturauftrag: KVA verknüpfen, Fotos, Verlauf."""
import hashlib
import io
import re
import sqlite3
from pathlib import Path

import pytest
from PIL import Image

from rsb import db as dbm

from conftest import kunde_anlegen, post
from test_auftraege import auftrag_anlegen, kva_mit_position


def bild(farbe="red", exif_zeit="2026:10:01 12:34:56", groesse=(800, 600)):
    b = Image.new("RGB", groesse, farbe)
    exif = Image.Exif()
    if exif_zeit:
        exif[306] = exif_zeit
        exif.get_ifd(0x8769)[36867] = exif_zeit
    puffer = io.BytesIO()
    b.save(puffer, "JPEG", exif=exif)
    return puffer.getvalue()


def foto_hochladen(client, url, daten, name="foto.jpg", kategorie="Fahrzeugeingang", **extra):
    return client.post(url, data={"csrf": "test-token", "kategorie": kategorie, "foto": (io.BytesIO(daten), name),
                                  **extra}, content_type="multipart/form-data")


def freier_kva(client, con, kid):
    """KVA ohne Auftrag anlegen (über Dokumente → Neu)."""
    r = client.get(f"/dokumente/neu?typ=kva&kunde_id={kid}")
    return int(re.search(r"/dokumente/(\d+)", r.headers["Location"]).group(1))


def test_detailseite_reiter_und_karte(client, con):
    kid = kunde_anlegen(client)
    aid = auftrag_anlegen(client, kid)
    html = client.get(f"/auftraege/{aid}").get_data(as_text=True)
    for text in ["Auftragsdaten", "Kostenvoranschlag", "Fotos", "Verlauf", "Bestehenden KVA verknüpfen",
                 "Neuen KVA aus diesem Auftrag erstellen", "Eingang", "Auftrag angelegt"]:
        assert text in html, text
    tafel = client.get("/auftraege").get_data(as_text=True)
    assert "📷 0" in tafel and "kein KVA" in tafel and 'data-kva="0"' in tafel


def test_auftrag_bearbeiten_kunde_status_und_verlauf(client, con):
    kid = kunde_anlegen(client)
    kid2 = kunde_anlegen(client, vorname="Bernd", nachname="Maier")
    aid = auftrag_anlegen(client, kid)
    daten = dict(kunde_id=kid2, status="in_arbeit", geraet="iPhone 13", leistungsart="Smartphone", seriennummer="1",
                 zubehoer="", fehler="Akku", notizen="Teil bestellt")
    post(client, f"/auftraege/{aid}", **daten)
    a = con.execute("SELECT * FROM auftraege WHERE id=?", (aid,)).fetchone()
    assert (a["kunde_id"], a["status"], a["geraet"], a["notizen"]) == (kid2, "in_arbeit", "iPhone 13", "Teil bestellt")
    # Erledigt ohne KVA: erst nachfragen, nichts speichern
    r = post(client, f"/auftraege/{aid}", **{**daten, "status": "erledigt", "geraet": "geändert"})
    assert r.headers["Location"].endswith("#kostenvoranschlag")
    assert con.execute("SELECT status, geraet FROM auftraege WHERE id=?", (aid,)).fetchone()[:] == \
        ("in_arbeit", "iPhone 13")
    r = post(client, f"/auftraege/{aid}", **{**daten, "status": "erledigt", "ohne_kva": "1"})
    assert "/dokumente/" in r.headers["Location"]
    ereignisse = [v["ereignis"] for v in con.execute("SELECT * FROM auftrag_verlauf WHERE auftrag_id=? ORDER BY id",
                                                     (aid,))]
    assert ereignisse == ["Auftrag angelegt", "Auftragsdaten geändert", "Status geändert", "Status geändert",
                          "Rechnung erstellt"]
    v = con.execute("SELECT * FROM auftrag_verlauf WHERE auftrag_id=? ORDER BY id LIMIT 1", (aid,)).fetchone()
    assert v["benutzer"] == "inhaber" and re.match(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d[+-]\d\d:\d\d", v["zeitpunkt"])
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("DELETE FROM auftrag_verlauf WHERE auftrag_id=?", (aid,))
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("UPDATE auftrag_verlauf SET ereignis='x' WHERE auftrag_id=?", (aid,))


def test_kva_verknuepfen_auswahl_loesen(client, con):
    kid = kunde_anlegen(client)
    kid2 = kunde_anlegen(client, vorname="Bernd", nachname="Maier")
    aid = auftrag_anlegen(client, kid)
    eigener, fremder = freier_kva(client, con, kid), freier_kva(client, con, kid2)
    # Auswahl: standardmäßig nur gleicher Kunde, optional alle
    ids = [d["id"] for d in client.get(f"/auftraege/kva-auswahl?kunde_id={kid}").get_json()]
    assert ids == [eigener]
    ids = {d["id"] for d in client.get(f"/auftraege/kva-auswahl?kunde_id={kid}&alle=1").get_json()}
    assert ids == {eigener, fremder}
    # Verknüpfen
    r = post(client, f"/auftraege/{aid}/kva-verknuepfen", kva_id=eigener)
    assert r.headers["Location"].endswith("#kostenvoranschlag")
    assert con.execute("SELECT kva_id FROM auftraege WHERE id=?", (aid,)).fetchone()[0] == eigener
    # Verknüpfte KVAs tauchen nicht mehr in der Auswahl auf
    assert client.get(f"/auftraege/kva-auswahl?kunde_id={kid}").get_json() == []
    html = client.get(f"/auftraege/{aid}").get_data(as_text=True)
    assert "Verknüpfung lösen" in html and "Bearbeiten" in html
    assert "KVA ✓" in client.get("/auftraege").get_data(as_text=True)
    # KVA-Seite zeigt den Auftrag
    assert "← Auftrag AU-" in client.get(f"/dokumente/{eigener}").get_data(as_text=True)
    # zweiter Auftrag kann denselben KVA nicht verknüpfen
    aid2 = auftrag_anlegen(client, kid)
    post(client, f"/auftraege/{aid2}/kva-verknuepfen", kva_id=eigener)
    assert con.execute("SELECT kva_id FROM auftraege WHERE id=?", (aid2,)).fetchone()[0] is None
    # anderer Kunde: verknüpfen mit Warnung
    client.get("/")  # Meldungen leeren
    post(client, f"/auftraege/{aid2}/kva-verknuepfen", kva_id=fremder)
    html = client.get(f"/auftraege/{aid2}").get_data(as_text=True)
    assert "anderen Kunden" in html
    # lösen: KVA bleibt erhalten
    post(client, f"/auftraege/{aid}/kva-loesen")
    assert con.execute("SELECT kva_id FROM auftraege WHERE id=?", (aid,)).fetchone()[0] is None
    assert con.execute("SELECT 1 FROM dokumente WHERE id=?", (eigener,)).fetchone()
    ereignisse = [v[0] for v in con.execute("SELECT ereignis FROM auftrag_verlauf WHERE auftrag_id=?", (aid,))]
    assert "KVA verknüpft" in ereignisse and "KVA-Verknüpfung gelöst" in ereignisse


def test_kva_status_und_erledigt_mit_verknuepftem_kva(client, con):
    kid = kunde_anlegen(client)
    aid = auftrag_anlegen(client, kid)
    kva = kva_mit_position(client, con, aid)
    assert con.execute("SELECT kva_status FROM dokumente WHERE id=?", (kva,)).fetchone()[0] == "offen"
    post(client, f"/dokumente/{kva}/kva-status", kva_status="angenommen")
    assert con.execute("SELECT kva_status FROM dokumente WHERE id=?", (kva,)).fetchone()[0] == "angenommen"
    assert "angenommen" in client.get(f"/auftraege/{aid}").get_data(as_text=True)
    r = client.post(f"/auftraege/{aid}/status", data={"csrf": "test-token", "status": "erledigt"},
                    headers={"X-Requested-With": "fetch"})
    rid = int(r.get_json()["rechnung_url"].rsplit("/", 1)[1])
    assert con.execute("SELECT summe_brutto FROM dokumente WHERE id=?", (rid,)).fetchone()[0] == 14900
    ereignisse = [v[0] for v in con.execute("SELECT ereignis FROM auftrag_verlauf WHERE auftrag_id=?", (aid,))]
    for e in ["KVA erstellt und verknüpft", "KVA festgeschrieben", "KVA angenommen", "Rechnung erstellt"]:
        assert e in ereignisse, e


def test_kva_versand_im_verlauf(client, con, monkeypatch):
    from rsb import views
    kid = kunde_anlegen(client)
    aid = auftrag_anlegen(client, kid)
    kva = kva_mit_position(client, con, aid)
    monkeypatch.setattr(views, "senden", lambda *a, **k: None)
    post(client, f"/dokumente/{kva}/email", an="anna@example.com", betreff="KVA", text="Hallo")
    assert con.execute("SELECT 1 FROM auftrag_verlauf WHERE auftrag_id=? AND ereignis='KVA per E-Mail versendet'",
                       (aid,)).fetchone()


def test_fotos_hochladen_metadaten_und_schutz(client, con, app):
    kid = kunde_anlegen(client)
    aid = auftrag_anlegen(client, kid)
    daten = bild()
    r = foto_hochladen(client, f"/auftraege/{aid}/fotos", daten, name="IMG_0001.JPG", kategorie="Vorschaden")
    j = r.get_json()
    assert j["ok"], j
    fid = j["dateien"][0]["id"]
    f = con.execute("SELECT * FROM auftrag_fotos WHERE id=?", (fid,)).fetchone()
    assert f["auftrag_id"] == aid and f["kategorie"] == "Vorschaden" and f["benutzer"] == "inhaber"
    assert f["sha256"] == hashlib.sha256(daten).hexdigest()
    assert f["exif_zeit"] == "2026-10-01T12:34:56"
    assert re.match(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d[+-]\d\d:\d\d", f["hochgeladen_am"])
    # Original unverändert, Vorschau vorhanden
    assert (Path(app.config["DATEN"]) / f["pfad"]).read_bytes() == daten
    assert client.get(f"/fotos/{fid}").data == daten
    assert client.get(f"/fotos/{fid}/vorschau").mimetype == "image/jpeg"
    # Karte zeigt Anzahl
    assert "📷 1" in client.get("/auftraege").get_data(as_text=True)
    # keine Bilder / falsche Kategorie
    assert not foto_hochladen(client, f"/auftraege/{aid}/fotos", b"kein bild", name="x.txt").get_json()["ok"]
    assert not foto_hochladen(client, f"/auftraege/{aid}/fotos", daten, kategorie="Quatsch").get_json()["ok"]
    # Löschen nur mit Grund und nur als Markierung
    post(client, f"/fotos/{fid}/loeschen", grund="")
    assert con.execute("SELECT geloescht_am FROM auftrag_fotos WHERE id=?", (fid,)).fetchone()[0] is None
    post(client, f"/fotos/{fid}/loeschen", grund="Falscher Auftrag")
    f = con.execute("SELECT * FROM auftrag_fotos WHERE id=?", (fid,)).fetchone()
    assert f["geloescht_am"] and f["loeschgrund"] == "Falscher Auftrag" and f["geloescht_von"] == "inhaber"
    assert "📷 0" in client.get("/auftraege").get_data(as_text=True)
    assert "Als gelöscht markiert" in client.get(f"/auftraege/{aid}").get_data(as_text=True)
    for sql in ["DELETE FROM auftrag_fotos", "UPDATE auftrag_fotos SET sha256='x'",
                "UPDATE auftrag_fotos SET loeschgrund='anders'", "UPDATE auftrag_fotos SET auftrag_id=99"]:
        with pytest.raises(sqlite3.IntegrityError):
            con.execute(sql)
    # Verlauf + Auftrag mit Fotos nicht löschbar
    ereignisse = [v[0] for v in con.execute("SELECT ereignis FROM auftrag_verlauf WHERE auftrag_id=?", (aid,))]
    assert "Foto hochgeladen" in ereignisse and "Foto als gelöscht markiert" in ereignisse
    post(client, f"/auftraege/{aid}/loeschen")
    assert con.execute("SELECT 1 FROM auftraege WHERE id=?", (aid,)).fetchone()
    # PDF
    r = client.get(f"/auftraege/{aid}/fotodokumentation.pdf")
    assert r.status_code == 200 and r.data.startswith(b"%PDF")


def test_neuer_auftrag_mit_kva_und_fotos_ueberlebt_fehler(client, con):
    kid = kunde_anlegen(client)
    kva = freier_kva(client, con, kid)
    seite = client.get("/auftraege/neu").get_data(as_text=True)
    token = re.search(r'name="upload_token" value="([0-9a-f]+)"', seite).group(1)
    r = foto_hochladen(client, "/auftraege/neu/fotos", bild("blue"), upload_token=token)
    assert r.get_json()["ok"]
    assert foto_hochladen(client, "/auftraege/neu/fotos", bild(), upload_token="falsch").status_code == 400
    # Speichern schlägt fehl (kein Kunde) -> Foto bleibt, Eingaben bleiben
    r = post(client, "/auftraege/neu", upload_token=token, kunde_id="", status="offen", geraet="Pixel 8",
             leistungsart="Smartphone", kva_id=kva)
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and "NICHT gespeichert" in html and "Pixel 8" in html
    assert html.count('class="foto"') == 1
    assert con.execute("SELECT COUNT(*) FROM auftraege").fetchone()[0] == 0
    # Erledigt ohne KVA -> Nachfrage, nicht gespeichert
    r = post(client, "/auftraege/neu", upload_token=token, kunde_id=kid, status="erledigt", geraet="Pixel 8")
    assert r.status_code == 200 and "Kein KVA verknüpft" in r.get_data(as_text=True)
    # jetzt richtig
    r = post(client, "/auftraege/neu", upload_token=token, kunde_id=kid, status="in_arbeit", geraet="Pixel 8",
             leistungsart="Smartphone", seriennummer="", zubehoer="", fehler="Akku", notizen="", kva_id=kva)
    aid = int(re.search(r"/auftraege/(\d+)", r.headers["Location"]).group(1))
    a = con.execute("SELECT * FROM auftraege WHERE id=?", (aid,)).fetchone()
    assert a["kva_id"] == kva and a["status"] == "in_arbeit"
    assert con.execute("SELECT COUNT(*) FROM auftrag_fotos WHERE auftrag_id=?", (aid,)).fetchone()[0] == 1
    ereignisse = [v[0] for v in con.execute("SELECT ereignis FROM auftrag_verlauf WHERE auftrag_id=? ORDER BY id",
                                            (aid,))]
    assert ereignisse == ["Auftrag angelegt", "KVA verknüpft", "Fotos hochgeladen", "Status geändert"]
    # neues Formular hat eine neue Kennung, alte Fotos sind nicht mehr dort
    seite = client.get("/auftraege/neu").get_data(as_text=True)
    assert token not in seite and 'class="foto"' not in seite


def test_kunde_mit_fotos_nicht_loeschbar(client, con):
    kid = kunde_anlegen(client)
    aid = auftrag_anlegen(client, kid)
    foto_hochladen(client, f"/auftraege/{aid}/fotos", bild())
    post(client, f"/kunden/{kid}/loeschen")
    assert con.execute("SELECT 1 FROM kunden WHERE id=?", (kid,)).fetchone()


def test_migration_alte_datenbank(tmp_path):
    """Datenbank aus 0.7.0 ohne neue Tabellen: Aufträge bleiben erhalten, Verlauf wird nachgetragen."""
    pfad = tmp_path / "werkstatt.db"
    dbm.initialisieren(str(pfad))
    con = dbm.verbinden(str(pfad))
    con.execute("INSERT INTO kunden (kundennr, typ, nachname, erstellt_am, geaendert_am) "
                "VALUES ('K1','privat','Alt','2026-01-01','2026-01-01')")
    con.execute("INSERT INTO auftraege (auftragsnr, kunde_id, status, eingang_am, erstellt_am, geaendert_am) "
                "VALUES ('AU-2026-0001', 1, 'offen', '2026-01-01T10:00:00', '2026-01-01', '2026-01-01')")
    for t in ["auftrag_fotos", "auftrag_verlauf"]:
        con.execute(f"DROP TABLE {t}")
    con.execute("DELETE FROM einstellungen WHERE schluessel='verlauf_nachgetragen'")
    con.close()
    dbm.initialisieren(str(pfad))
    con = dbm.verbinden(str(pfad))
    assert con.execute("SELECT auftragsnr FROM auftraege").fetchone()[0] == "AU-2026-0001"
    assert con.execute("SELECT ereignis FROM auftrag_verlauf WHERE auftrag_id=1").fetchone()[0] == "Auftrag angelegt"
    con.close()
