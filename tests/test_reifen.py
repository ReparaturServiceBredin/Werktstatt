"""Reifen & Teile (Variante „reifen“): Einlagerung, Reifengrößen, Thekenverkauf, ohne Handy-Funktionen."""
import re

import pytest
from flask import url_for

from rsb import create_app, variante
from rsb import db as dbm
from rsb import navigation as nav
from rsb import reifen as rf

from conftest import VOLLSTAENDIGE_FIRMA, kunde_anlegen, post


@pytest.fixture
def app(tmp_path):
    app = create_app(tmp_path / "Daten", testing=True, variante="reifen")
    con = dbm.verbinden(app.config["DB_PFAD"])
    with dbm.Transaktion(con):
        dbm.einstellungen_speichern(VOLLSTAENDIGE_FIRMA, con)
    con.close()
    yield app
    variante.setzen("sauter")  # andere Tests laufen mit der Standard-Variante


def test_variante_eigener_name_ordner_cookie_port(app, client, monkeypatch):
    assert variante.programm() == "Reifen & Teile" and variante.exe_name() == "Reifen-Teile.exe"
    assert app.config["SESSION_COOKIE_NAME"] == "reifen_teile"
    from rsb import datenort
    monkeypatch.setenv("XDG_DATA_HOME", "/tmp/xdg")
    monkeypatch.setenv("LOCALAPPDATA", "/tmp/xdg")
    assert datenort.fester_ort().parent.name == "Reifen-Teile"
    j = client.get("/version").get_json()
    assert j["programm"] == "Reifen & Teile" and j["version"] == variante.wert("version")
    einst = client.get("/einstellungen/annahme").get_data(as_text=True)
    assert "[Räderwechsel]" in einst and "Handy / Tablet im WLAN" not in einst


def test_ohne_handy_funktionen(client, con):
    kid = kunde_anlegen(client)
    r = post(client, "/auftraege/neu", kunde_id=kid, leistung=["Räderwechsel"], geraet="VW Golf",
             kennzeichen="HN-AB 123", fehler="Winterräder montieren")
    aid = int(re.search(r"/auftraege/(\d+)", r.headers["Location"]).group(1))
    html = client.get(f"/auftraege/{aid}").get_data(as_text=True)
    assert "QR-Code" not in html and "Am Handy" not in html and "Räder einlagern" in html
    assert post(client, f"/auftraege/{aid}/handy/annahme").status_code == 404
    assert client.get("/m/irgendwas").status_code == 404
    assert "SMS" not in client.get("/einstellungen/benachrichtigung").get_data(as_text=True)
    # Checkliste der Reifen-Leistung wurde angelegt
    assert con.execute("SELECT COUNT(*) FROM auftrag_checkliste WHERE auftrag_id=? AND leistung='Räderwechsel'",
                       (aid,)).fetchone()[0] >= 5


def test_menue_und_alle_seiten_erreichbar(app, client):
    html = client.get("/").get_data(as_text=True)
    menue = html.split('class="nav"')[1].split("</nav>")[0]
    for punkt in ("Reifeneinlagerung", "Thekenverkauf", "Lager", "Einkauf", "Reifen, Teile"):
        assert punkt in menue, punkt
    with app.test_request_context():
        ziele = [url_for(e.endpoint, **e.args) for _, e in nav.alle_eintraege()]
        ziele += [url_for(ep) for reiter in nav.REITER.values() for _, ep in reiter]
        ziele += [url_for("main.einstellungen", bereich=b) for _, liste in nav.EINSTELLUNGS_GRUPPEN for b, _, _ in liste]
        ziele += [url_for(ep, **args) for _, ep, args, _ in nav.NEU if ep not in ("main.dokument_neu",)]
    for url in ziele:
        assert client.get(url).status_code in (200, 302), url
    assert "einlagerung" in [b for _, liste in nav.EINSTELLUNGS_GRUPPEN for b, _, _ in liste]


def test_reifengroesse():
    assert rf.groesse_text("205 55 16") == "205/55 R16"
    assert rf.groesse_text("225/45zr17 94W") == "225/45 R17 94W"
    assert rf.groesse_schluessel("205/55 R16 91V") == "2055516"
    assert rf.ist_groessen_suche("2055516") and rf.ist_groessen_suche("205/55 R16") and rf.ist_groessen_suche("205/55")
    assert not rf.ist_groessen_suche("Ölfilter") and not rf.ist_groessen_suche("4006633123456")
    assert rf.groesse_passt("205/55 R16 91V", "205/55") and not rf.groesse_passt("195/65 R15", "2055516")


def test_dot_und_warnungen():
    from datetime import date
    assert rf.dot_datum("2321") == date.fromisocalendar(2021, 23, 1)
    assert rf.dot_datum("9921") is None and rf.dot_datum("12") is None
    assert rf.dot_alter_jahre("0121", date(2026, 1, 1)) == 5.0
    e = {"saison": "winter", **{f"profil_{p}": 6.0 for p in ("vl", "vr", "hl", "hr")},
         **{f"dot_{p}": "" for p in ("vl", "vr", "hl", "hr")}}
    e["profil_hr"] = 3.5
    w = rf.warnungen(e, {"einlagerung_profil_warnung_winter": 4.0, "einlagerung_dot_warnung_jahre": 6})
    assert any("HR" in x for x in w) and w[-1] == "→ Neue Reifen anbieten"


def _einlagern(client, kid, **felder):
    daten = dict(kunde_id=kid, kennzeichen="hn-ab 123", fahrzeug="VW Golf VII", saison="winter", art="raeder",
                 felge="Alu", anzahl="4", hersteller="Continental TS 870", groesse="205 55 16 91h", lagerplatz="a-01",
                 profil_vl="6,5", profil_vr="6,5", profil_hl="7", profil_hr="7", dot_vl="2321", dot_vr="2321",
                 dot_hl="2421", dot_hr="2421", gebuehr="25,00")
    daten.update(felder)
    r = post(client, "/einlagerung/neu", **daten)
    assert r.status_code == 302, r.get_data(as_text=True)[:500]
    return int(re.search(r"/einlagerung/(\d+)", r.headers["Location"]).group(1))


def test_einlagerung_tausch_suche_pdf_und_rechnung(client, con):
    kid = kunde_anlegen(client, telefon="0170 123")
    eid = _einlagern(client, kid)
    e = con.execute("SELECT * FROM einlagerungen WHERE id=?", (eid,)).fetchone()
    assert e["nummer"].startswith("EL-") and e["kennzeichen"] == "HN-AB 123" and e["lagerplatz"] == "A-01"
    assert e["groesse"] == "205/55 R16 91H" and e["profil_hl"] == 7.0 and e["gebuehr"] == 2500
    # Suche: Kennzeichen ohne Leerzeichen/Bindestrich, Größe, Lagerplatz
    for q in ("HNAB123", "2055516", "A-01", "Müller"):
        assert "HN-AB 123" in client.get(f"/einlagerung?q={q}").get_data(as_text=True), q
    # Platz eines anderen Kunden ist belegt
    k2 = kunde_anlegen(client, vorname="Bert", nachname="Schmidt", email="bert@example.com")
    r = post(client, "/einlagerung/neu", kunde_id=k2, saison="sommer", lagerplatz="A-01")
    assert r.status_code == 302 and con.execute("SELECT COUNT(*) FROM einlagerungen").fetchone()[0] == 1
    # PDF: Schein und Etiketten
    for url in (f"/einlagerung/{eid}.pdf", f"/einlagerung/{eid}.pdf?etiketten=1"):
        r = client.get(url)
        assert r.status_code == 200 and r.data[:4] == b"%PDF"
    # Saisontausch: Sommerräder kommen an denselben Platz, Winterräder werden ausgelagert
    html = client.get(f"/einlagerung/neu?tausch={eid}").get_data(as_text=True)
    assert 'value="A-01"' in html and "automatisch ausgelagert" in html
    neu = _einlagern(client, kid, saison="sommer", vorgaenger_id=str(eid), groesse="205/55 R16 91V")
    assert con.execute("SELECT ausgelagert_am FROM einlagerungen WHERE id=?", (eid,)).fetchone()[0]
    assert con.execute("SELECT lagerplatz FROM einlagerungen WHERE id=?", (neu,)).fetchone()[0] == "A-01"
    assert "HN-AB 123" in client.get("/einlagerung/ausgelagert").get_data(as_text=True)
    assert "EL-" in client.get(f"/kunden/{kid}").get_data(as_text=True)
    # Gebühr abrechnen -> Rechnungsentwurf mit 25,00 brutto
    r = post(client, f"/einlagerung/{neu}/rechnung")
    did = int(re.search(r"/dokumente/(\d+)", r.headers["Location"]).group(1))
    d = con.execute("SELECT * FROM dokumente WHERE id=?", (did,)).fetchone()
    assert d["status"] == "entwurf" and abs(d["summe_brutto"] - 2500) <= 1
    # Kunde mit eingelagerten Rädern darf nicht gelöscht werden
    from rsb.datenschutz import sperren
    from datetime import date
    assert "eingelagerte Räder" in sperren(con, kid, date.today())


def test_saisonwechsel_erinnern(client, con, monkeypatch):
    kid = kunde_anlegen(client)
    eid = _einlagern(client, kid)
    einst = dbm.einstellungen(con)
    from datetime import date
    assert rf.saison_ziel(einst, date(2026, 10, 15)) == "winter"
    assert rf.saison_ziel(einst, date(2026, 4, 1)) == "sommer"
    assert rf.saison_ziel(einst, date(2026, 7, 1)) is None
    html = client.get("/einlagerung/saisonwechsel?saison=winter").get_data(as_text=True)
    assert "Müller" in html and "noch nicht" in html
    gesendet = []
    monkeypatch.setattr("rsb.mail.senden", lambda con, **k: gesendet.append(k))
    post(client, f"/einlagerung/{eid}/erinnern", wie="email")
    assert gesendet and "Winterräder" in gesendet[0]["betreff"] and "A-01" in gesendet[0]["text"]
    e = con.execute("SELECT * FROM einlagerungen WHERE id=?", (eid,)).fetchone()
    assert e["erinnert_wie"] == "E-Mail" and rf.frisch_erinnert(e)


def test_artikel_reifengroesse_suche(client, con):
    post(client, "/artikel/neu", aktiv="1", name="Michelin Primacy 4", typ="material", preis="80,00", teilekosten="55,00",
         steuersatz="19", reifen_groesse="205/55r16 91v", reifen_saison="sommer", lagerfuehrend="1",
         herstellernr="MI-123")
    post(client, "/artikel/neu", aktiv="1", name="Bremsscheibe vorne", typ="material", preis="40,00", teilekosten="20,00",
         steuersatz="19", herstellernr="1K0615301AA", kompatibilitaet="VW Golf VII")
    a = con.execute("SELECT * FROM artikel WHERE name LIKE 'Michelin%'").fetchone()
    assert a["reifen_groesse"] == "205/55 R16 91V" and a["reifen_saison"] == "sommer"
    for q, erwartet, nicht in (("2055516", "Michelin", "Bremsscheibe"), ("205/55", "Michelin", "Bremsscheibe"),
                               ("1K0615301", "Bremsscheibe", "Michelin"), ("Golf", "Bremsscheibe", "Michelin")):
        html = client.get(f"/artikel?q={q}").get_data(as_text=True)
        assert erwartet in html and nicht not in html, q
    j = client.get("/theke/suche.json?q=2055516").get_json()
    assert j[0]["name"] == "Michelin Primacy 4" and j[0]["brutto"] == 8000  # Kleinunternehmer: ohne USt


def test_thekenverkauf_bar_lager_kasse_und_storno(client, con, app):
    post(client, "/artikel/neu", aktiv="1", name="Scheibenwischer 600 mm", typ="material", preis="10,00", teilekosten="4,00",
         steuersatz="19", lagerfuehrend="1")
    a = con.execute("SELECT * FROM artikel WHERE name LIKE 'Scheibenwischer%'").fetchone()
    post(client, f"/lager/{a['id']}/buchen", art="zugang", menge="10", grund="Erstbestand")
    r = post(client, "/theke", t_artikel_id=[str(a["id"]), ""], t_bezeichnung=[a["name"], "Altreifenentsorgung"],
             t_menge=["2", "4"], t_preis=["11,90", "2,50"], zahlart="bar", kunde_id="")
    assert r.status_code == 302, r.get_data(as_text=True)[:300]
    d = con.execute("SELECT * FROM dokumente WHERE betreff='Verkauf'").fetchone()
    assert d["status"] == "festgeschrieben" and d["summe_brutto"] == 2380 + 1000
    k = con.execute("SELECT * FROM kunden WHERE id=?", (d["kunde_id"],)).fetchone()
    assert k["nachname"] == rf.LAUFKUNDE_NAME
    assert con.execute("SELECT bezahlt_betrag FROM dokumente WHERE id=?", (d["id"],)).fetchone()[0] == d["summe_brutto"]
    assert con.execute("SELECT COUNT(*) FROM kassenbuch WHERE dokument_id=?", (d["id"],)).fetchone()[0] == 1
    assert con.execute("SELECT bestand FROM artikel WHERE id=?", (a["id"],)).fetchone()[0] == 8
    assert d["nummer"] in client.get("/theke").get_data(as_text=True)
    # zweiter Verkauf nutzt denselben Laufkunden
    post(client, "/theke", t_artikel_id=[str(a["id"])], t_bezeichnung=[a["name"]], t_menge=["1"], t_preis=["11,90"],
         zahlart="karte", kunde_id="")
    assert con.execute(f"SELECT COUNT(*) FROM kunden WHERE nachname=?", (rf.LAUFKUNDE_NAME,)).fetchone()[0] == 1
    # Storno bucht das Lager zurück
    from rsb import logik
    logik.stornieren(con, d["id"], app.config["DATEN"], "Test")
    assert con.execute("SELECT bestand FROM artikel WHERE id=?", (a["id"],)).fetchone()[0] == 9
    # Überweisung ohne Kunde geht nicht
    r = post(client, "/theke", t_artikel_id=[""], t_bezeichnung=["Ventil"], t_menge=["1"], t_preis=["3,00"],
             zahlart="ueberweisung", kunde_id="")
    assert con.execute("SELECT COUNT(*) FROM dokumente WHERE betreff='Verkauf' AND status<>'entwurf'"
                       ).fetchone()[0] == 2  # nur die 2 Verkäufe, kein dritter


def test_update_eigener_kanal(monkeypatch):
    from rsb import update
    variante.setzen("reifen")
    try:
        liste = [
            {"tag_name": "v9.9.9", "assets": [{"name": "Werkstatt-Sauter.exe", "browser_download_url": "x"}]},
            {"tag_name": "reifen-v1.0.0", "assets": [{"name": "Reifen-Teile.exe", "browser_download_url": "a"},
                                                     {"name": "Reifen-Teile.exe.sha256", "browser_download_url": "b"}]},
            {"tag_name": "reifen-v1.2.0", "assets": [{"name": "Reifen-Teile.exe", "browser_download_url": "c"},
                                                     {"name": "Reifen-Teile.exe.sha256", "browser_download_url": "d"}]},
            {"tag_name": "reifen-v1.3.0", "prerelease": True, "assets": []},
        ]
        import json
        monkeypatch.setattr(update, "_abrufen", lambda url, timeout=15: json.dumps(liste).encode())
        info = update.neueste_version()
        assert info["version"] == "1.2.0" and info["exe_url"] == "c" and info["sha_url"] == "d"
    finally:
        variante.setzen("sauter")
