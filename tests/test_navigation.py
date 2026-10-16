"""Navigation: Seitenleiste, alte Adressen, Schnellsuche (Strg+K), Glocke, Oberflächen-Zustand, Einstellungs-Suche."""
import re

from rsb import db as dbm
from rsb import navigation as nav

from conftest import kunde_anlegen, post, rechnung_anlegen
from test_annahme import auftrag_mit_annahme


def test_alle_menuepunkte_reiter_und_einstellungen_erreichbar(client, app):
    with app.test_request_context():
        from flask import url_for
        ziele = [url_for(e.endpoint, **e.args) for _, e in nav.alle_eintraege()]
        ziele += [url_for(ep) for reiter in nav.REITER.values() for _, ep in reiter]
        ziele += [url_for("main.einstellungen", bereich=b) for _, l in nav.EINSTELLUNGS_GRUPPEN for b, _, _ in l]
        ziele += [url_for(ep) for ep, *_ in nav.VERWALTUNG]
        ziele += [url_for("main.benachrichtigungen"), url_for("main.leihe_ausgabe_waehlen"),
                  url_for("main.dokumente", typ="alle")]
    for url in ziele:
        r = client.get(url)
        assert r.status_code == 200, url
        assert 'class="seitenleiste"' in r.get_data(as_text=True), url
    # „+ Neu“-Menü: alle Ziele funktionieren (Rechnung/KVA legen einen Entwurf an und leiten weiter)
    with app.test_request_context():
        neu = [url_for(ep, **args) for _, ep, args, _ in nav.NEU]
    for url in neu:
        assert client.get(url).status_code in (200, 302), url


def test_jede_seite_hat_einen_menuepunkt(app):
    """Keine Funktion geht verloren: jede aufrufbare Seite gehört zu einem Menüpunkt (oder ist bewusst ohne)."""
    ohne = {"main.login", "main.einrichten", "main.version_info", "main.mobil", "main.mobil_foto_vorschau",
            "main.mobil_inventur", "main.benachrichtigungen", "main.benachrichtigung_oeffnen", "main.schnellsuche"}
    fehlt = [r.endpoint for r in app.url_map.iter_rules()
             if "GET" in r.methods and r.endpoint != "static" and not r.endpoint.startswith("main.alt_")
             and r.endpoint not in ohne and not nav.aktiver_schluessel(r.endpoint)]
    assert fehlt == []
    namen = {e.titel for _, e in nav.alle_eintraege()}
    # Werkstatt Sauter: bewusst schlank (Leihgeräte, Lager, Einkauf, Verträge, Bank, Fixkosten, DATEV ausgeblendet)
    assert {"Übersicht", "Aufträge", "Kunden", "Rechnungen", "Leistungen & Artikel", "Belege & Ausgaben", "Kassenbuch",
            "Finanzen", "Einstellungen"} == namen
    assert len([b for _, l in nav.EINSTELLUNGS_GRUPPEN for b in l]) == 12


def test_alte_adressen_leiten_weiter(client):
    erwartet = {
        "/dokumente": "/verkauf/rechnungen?typ=alle", "/dokumente?typ=kva": "/verkauf/kostenvoranschlaege",
        "/dokumente?typ=rechnung&status=entwurf": "/verkauf/rechnungen?status=entwurf",
        "/offene-posten?filter=ueberfaellig": "/verkauf/offene-posten?filter=ueberfaellig",
        "/mahnwesen": "/verkauf/mahnwesen", "/bestellungen?status=alle": "/einkauf/bestellungen?status=alle",
        "/lieferanten": "/einkauf/lieferanten", "/eingangsrechnungen?status=bezahlt&q=x":
            "/einkauf/eingangsrechnungen?status=bezahlt&q=x",
        "/einstellungen": "/einstellungen/firma", "/einstellungen?bereich=email": "/einstellungen/email",
        "/einstellungen?bereich=gibtsnicht": "/einstellungen/firma",
    }
    for alt, neu in erwartet.items():
        r = client.get(alt)
        assert r.status_code in (301, 302), alt
        assert r.headers["Location"].endswith(neu), (alt, r.headers["Location"])
        assert client.get(alt, follow_redirects=True).status_code == 200, alt
    # Speichern über die alte Adresse funktioniert weiterhin
    r = post(client, "/einstellungen?bereich=vertraege", abo_modus="entwurf", vertrag_erinnerung_tage="21")
    assert r.headers["Location"].endswith("/einstellungen/vertraege")
    # Unterseiten behalten ihre Adresse
    assert client.get("/mahnwesen/erstellen").status_code in (404, 405)
    assert client.get("/lieferanten/neu").status_code == 200


def test_backup_formulare_getrennt(client, con, app):
    r = post(client, "/einstellungen/backup", backup_auto="1", backup_ziel="", backup_behalten="9")
    assert dbm.einstellungen(con)["backup_behalten"] == 9 and r.headers["Location"].endswith("/einstellungen/backup")
    post(client, "/einstellungen/backup/erstellen")
    assert dbm.einstellungen(con)["letztes_backup"]
    # „Backup jetzt erstellen“ aus einer alten, noch offenen Seite (POST /einstellungen/backup ohne Felder):
    # erstellt ein Backup und überschreibt die Backup-Einstellungen nicht
    con.execute("DELETE FROM einstellungen WHERE schluessel='letztes_backup'")
    post(client, "/einstellungen/backup")
    e = dbm.einstellungen(con)
    assert e["letztes_backup"] and e["backup_behalten"] == 9 and e["backup_auto"] is True


def test_seitenleiste_aktiv_zaehler_brotkrumen(client, con):
    kid = kunde_anlegen(client)
    auftrag_mit_annahme(client, kid)
    html = client.get("/verkauf/offene-posten").get_data(as_text=True)
    aktiv = re.search(r'class="nav-punkt aktiv"[^>]*data-titel="([^"]+)"', html).group(1)
    assert aktiv == "Rechnungen" and 'aria-current="page"' in html
    assert re.search(r"<span>Rechnungen</span>.*?>Rechnungen</a>.*?<b>Offene Posten</b>", html, re.S)
    assert 'class="bereichsreiter"' in html and "Kostenvoranschläge" in html and "Mahnwesen" in html
    assert re.search(r'data-titel="Aufträge".*?<span class="zaehler" title="offene Aufträge">1</span>', html,
                     re.S)
    assert "Benachrichtigungen</span>" not in html.split('class="nav"')[1].split("</nav>")[0]  # nicht mehr im Menü
    html = client.get("/einkauf/lieferanten").get_data(as_text=True)
    assert re.search(r'class="nav-punkt aktiv"[^>]*data-titel="Belege &amp; Ausgaben"', html)
    html = client.get("/protokoll").get_data(as_text=True)
    assert re.search(r'class="nav-punkt aktiv"[^>]*data-titel="Einstellungen"', html)


def test_oberflaeche_zustand_je_benutzer(client, con):
    r = client.post("/oberflaeche", json={"zu": ["werkstatt", "verkauf", "unsinn"], "schmal": True, "design": "dunkel"},
                    headers={"X-CSRF": "test-token"})
    assert r.get_json()["ok"]
    z = dbm.einstellungen(con)["oberflaeche:inhaber"]
    assert z == {"zu": ["werkstatt", "verkauf"], "schmal": True, "design": "dunkel"}
    html = client.get("/finanzen").get_data(as_text=True)
    assert '<body class="nav-schmal">' in html and 'data-design="dunkel"' in html
    assert 'class="nav-gruppe zu" data-gruppe="werkstatt"' in html
    # Gruppe der geöffneten Seite ist immer aufgeklappt
    html = client.get("/verkauf/rechnungen").get_data(as_text=True)
    assert 'class="nav-gruppe" data-gruppe="verkauf"' in html
    assert client.post("/oberflaeche", json={"schmal": False}).status_code == 400  # ohne CSRF-Token


def test_glocke_gelesen(client, con):
    kid = kunde_anlegen(client)
    aid = auftrag_mit_annahme(client, kid)
    ids = [r[0] for r in con.execute("SELECT id FROM benachrichtigungen WHERE status='offen'")]
    assert ids, "Annahme erzeugt einen Benachrichtigungs-Vorschlag"
    html = client.get("/").get_data(as_text=True)
    assert f'<span class="glocke-zahl">{len(ids)}</span>' in html and "Alle als gelesen" in html
    r = client.get(f"/benachrichtigungen/{ids[0]}/oeffnen")
    assert f"/auftraege/{aid}" in r.headers["Location"]
    assert con.execute("SELECT gelesen_am FROM benachrichtigungen WHERE id=?", (ids[0],)).fetchone()[0]
    post(client, "/benachrichtigungen/gelesen")
    assert not con.execute("SELECT 1 FROM benachrichtigungen WHERE gelesen_am IS NULL").fetchone()
    html = client.get("/").get_data(as_text=True)
    assert "glocke-zahl" not in html
    # Vorschlag wartet trotzdem weiter auf Freigabe
    assert con.execute("SELECT status FROM benachrichtigungen WHERE id=?", (ids[0],)).fetchone()[0] == "offen"


def _suche(client, q):
    return {g["art"]: g["eintraege"] for g in client.get("/suche.json", query_string={"q": q}).get_json()}


def test_schnellsuche(client, con):
    kid = kunde_anlegen(client, telefon="07298 123456")
    aid = auftrag_mit_annahme(client, kid, geraet="Xiaomi 14T Pro", seriennummer="IMEI4455667788")
    did = rechnung_anlegen(client, kid, festschreiben=True)
    nummer = con.execute("SELECT nummer FROM dokumente WHERE id=?", (did,)).fetchone()[0]
    leer = _suche(client, "")
    assert [e["titel"] for e in leer["Schnellaktionen"]] == ["Neuer Auftrag", "Neuer Kunde", "Neuer KVA",
                                                              "Neue Rechnung", "Neuer Beleg", "Kassenbuchung"]
    assert "/verkauf/mahnwesen" in [e["url"] for e in _suche(client, "Mahnwesen")["Seiten"]]
    assert _suche(client, "SMTP")["Einstellungen"][0]["url"].startswith("/einstellungen/email#feld-smtp_")
    assert any(e["url"].startswith("/einstellungen/backup") for e in _suche(client, "Backup")["Einstellungen"])
    assert _suche(client, "Müller")["Kunden"][0]["url"] == f"/kunden/{kid}"
    assert _suche(client, "anna@example")["Kunden"][0]["url"] == f"/kunden/{kid}"
    assert _suche(client, "07298/123456")["Kunden"][0]["url"] == f"/kunden/{kid}"
    for q in ("Xiaomi", "IMEI4455", "AU-2026"):
        assert _suche(client, q)["Aufträge"][0]["url"] == f"/auftraege/{aid}", q
    assert _suche(client, nummer)["Rechnungen & KVA"][0]["url"] == f"/dokumente/{did}"
    post(client, "/artikel/neu", name="Akkutausch iPhone", preis="89,00", teilekosten="30,00", einheit="pauschal",
         typ="leistung", steuersatz="19", aktiv="1")
    assert _suche(client, "akkutausch")["Leistungen & Artikel"]
    assert [e["titel"] for e in _suche(client, "neu")["Schnellaktionen"]][:2] == ["Neuer Auftrag", "Neuer Kunde"]
    assert _suche(client, "loeschfrist")["Einstellungen"]  # Umlaute egal


def test_einstellungs_suche_und_anker(client):
    treffer = client.get("/einstellungen/suche.json?q=IMAP").get_json()
    bereiche = {t["bereich"] for t in treffer}
    assert "email" in bereiche and "anfragen" not in bereiche  # Anfragen sind ausgeblendet
    t = client.get("/einstellungen/suche.json?q=Verzugszinsen").get_json()
    assert t[0]["bereich"] == "mahnwesen" and t[0]["url"].startswith("/einstellungen/mahnwesen#abschnitt-")
    html = client.get("/einstellungen/email").get_data(as_text=True)
    assert 'id="einst-suche"' in html and 'class="einst-nav"' in html and "Verwaltung &amp; Prüfung" in html
    assert 'name="smtp_host"' in html


def test_zaehlerfehler_leert_nie_die_einstellungen(client, con, monkeypatch):
    """Fällt ein Zähler aus (z. B. fehlende Spalte), bleiben Firmendaten und IMAP sichtbar – nie leere Formulare."""
    with dbm.Transaktion(con):
        dbm.einstellungen_speichern({"imap_host": "imap.ionos.de"}, con)
    con.execute("ALTER TABLE benachrichtigungen DROP COLUMN gelesen_am")
    import rsb.lager
    monkeypatch.setattr(rsb.lager, "unter_mindestbestand_anzahl", lambda c: 1 / 0)
    firma = dbm.einstellungen(con)["firma_name"]
    assert firma and firma in client.get("/einstellungen/firma").get_data(as_text=True)
    assert 'value="imap.ionos.de"' in client.get("/einstellungen/anfragen").get_data(as_text=True)
