"""Phase 1 – GoBD: Gutschrift, Pflichtangaben, Archiv mit Prüfsummen, Änderungsprotokoll, Aufbewahrung."""
import hashlib
import json
import re
import sqlite3
from pathlib import Path

import pytest

from rsb import db as dbm

from conftest import kunde_anlegen, post, rechnung_anlegen


def rechnung_fest(client, kid, **extra):
    return rechnung_anlegen(client, kid, festschreiben=True, **extra)


def test_gutschrift_eigener_nummernkreis(client, con):
    kid = kunde_anlegen(client)
    rid = rechnung_fest(client, kid, positionen=(("Displaytausch", "149,00", "1"),))
    assert con.execute("SELECT nummer FROM dokumente WHERE id=?", (rid,)).fetchone()[0].startswith("RE-")
    r = post(client, f"/dokumente/{rid}/gutschrift")
    gid = int(re.search(r"/dokumente/(\d+)", r.headers["Location"]).group(1))
    g = con.execute("SELECT * FROM dokumente WHERE id=?", (gid,)).fetchone()
    assert g["typ"] == "gutschrift" and g["bezug_id"] == rid and g["status"] == "entwurf" and g["nummer"] is None
    assert con.execute("SELECT einzelpreis FROM positionen WHERE dokument_id=?", (gid,)).fetchone()[0] == -14900
    seite = client.get(f"/dokumente/{gid}").get_data(as_text=True)
    assert "positiv" in seite and "Math.abs" in seite
    # Teil-Gutschrift: 20 € positiv eingegeben -> gespeichert als -20 €
    client.post(f"/dokumente/{gid}", data={
        "csrf": "test-token", "kunde_id": kid, "datum": "", "leistungsdatum": g["leistungsdatum"], "zahlungsziel_tage": "",
        "betreff": g["betreff"], "einleitung": "", "schlusstext": "", "hinweise": "", "aktion": "festschreiben",
        "p_bezeichnung": ["Preisnachlass Displaytausch"], "p_beschreibung": [""], "p_menge": ["1"], "p_einheit": ["pauschal"],
        "p_preis": ["20,00"], "p_teilekosten": [""], "p_steuersatz": ["19"], "p_leistungsart": ["Smartphone"],
        "p_artikel_id": [""], "p_katalog": ["1"]})
    g = con.execute("SELECT * FROM dokumente WHERE id=?", (gid,)).fetchone()
    assert g["status"] == "festgeschrieben" and g["nummer"].startswith("GS-") and g["summe_brutto"] == -2000
    assert not con.execute("SELECT 1 FROM artikel WHERE name='Preisnachlass Displaytausch'").fetchone()
    # Rechnungs-Nummernkreis bleibt lückenlos
    rid2 = rechnung_fest(client, kid)
    nr1 = con.execute("SELECT nummer FROM dokumente WHERE id=?", (rid,)).fetchone()[0]
    nr2 = con.execute("SELECT nummer FROM dokumente WHERE id=?", (rid2,)).fetchone()[0]
    assert int(nr2[-4:]) == int(nr1[-4:]) + 1
    assert "Gutschriften" in client.get(f"/dokumente/{rid}").get_data(as_text=True)


def test_pflichtangaben(client, con):
    kid = kunde_anlegen(client)
    with dbm.Transaktion(con):
        dbm.einstellungen_speichern({"steuernummer": "", "ust_idnr": ""}, con)
    did = rechnung_anlegen(client, kid)
    seite = client.get(f"/dokumente/{did}").get_data(as_text=True)
    assert "Pflichtangaben" in seite and "Steuernummer oder USt-IdNr." in seite
    # Festschreiben scheitert, keine Nummer verbraucht
    did2 = rechnung_anlegen(client, kid, festschreiben=True)
    assert con.execute("SELECT status, nummer FROM dokumente WHERE id=?", (did2,)).fetchone()[:] == ("entwurf", None)
    assert not con.execute("SELECT 1 FROM nummernkreise WHERE letzte_nummer>0").fetchone()
    with dbm.Transaktion(con):
        dbm.einstellungen_speichern({"ust_idnr": "DE123456789"}, con)
    # Kunde ohne Anschrift: Kleinbetrag bis 250 € nur Hinweis, darüber Fehler
    ohne = kunde_anlegen(client, strasse="", plz="", ort="")
    klein = rechnung_anlegen(client, ohne, festschreiben=True)
    assert con.execute("SELECT status FROM dokumente WHERE id=?", (klein,)).fetchone()[0] == "festgeschrieben"
    gross = rechnung_anlegen(client, ohne, positionen=(("Mainboard", "300,00", "1"),), festschreiben=True)
    assert con.execute("SELECT status FROM dokumente WHERE id=?", (gross,)).fetchone()[0] == "entwurf"
    assert "Anschrift des Kunden" in client.get(f"/dokumente/{gross}").get_data(as_text=True)
    # Kleinunternehmer-Hinweis fehlt
    with dbm.Transaktion(con):
        dbm.einstellungen_speichern({"kleinunternehmer_hinweis": ""}, con)
    d3 = rechnung_anlegen(client, kid, festschreiben=True)
    assert con.execute("SELECT status FROM dokumente WHERE id=?", (d3,)).fetchone()[0] == "entwurf"


def test_archiv_und_pruefsummen(client, con, app):
    kid = kunde_anlegen(client)
    did = rechnung_fest(client, kid)
    d = con.execute("SELECT * FROM dokumente WHERE id=?", (did,)).fetchone()
    pdf = Path(app.config["DATEN"]) / d["pdf_pfad"]
    daten = pdf.with_suffix(".json")
    assert hashlib.sha256(daten.read_bytes()).hexdigest() == d["snapshot_sha256"]
    assert json.loads(daten.read_text(encoding="utf-8"))["nummer"] == d["nummer"]
    assert re.match(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d[+-]", d["festgeschrieben_am"])
    # Öffnen liefert exakt das archivierte PDF
    assert client.get(f"/dokumente/{did}/pdf").data == pdf.read_bytes()
    seite = client.get(f"/dokumente/{did}").get_data(as_text=True)
    assert "Aufbewahren bis" in seite and f"{int(d['datum'][:4]) + 8}" in seite
    # Manipulation wird erkannt
    pdf.write_bytes(pdf.read_bytes() + b"%manipuliert")
    r = client.get(f"/dokumente/{did}/pdf")
    assert r.status_code == 409 and "verändert" in r.get_data(as_text=True)
    daten.write_text("{}", encoding="utf-8")
    seite = client.get("/pruefung").get_data(as_text=True)
    assert "PDF-Datei wurde verändert" in seite and "Rechnungsdaten wurden verändert" in seite


def test_unveraenderbar_auch_direkt(client, con):
    kid = kunde_anlegen(client)
    did = rechnung_fest(client, kid)
    for sql in ["UPDATE dokumente SET zahlungsziel_tage=99 WHERE id=?", "UPDATE dokumente SET kunde_id=NULL WHERE id=?",
                "UPDATE dokumente SET snapshot_sha256='x' WHERE id=?", "DELETE FROM dokumente WHERE id=?",
                "UPDATE positionen SET einzelpreis=1 WHERE dokument_id=?", "DELETE FROM positionen WHERE dokument_id=?"]:
        with pytest.raises(sqlite3.IntegrityError):
            con.execute(sql, (did,))
    post(client, f"/dokumente/{did}/loeschen")
    assert con.execute("SELECT 1 FROM dokumente WHERE id=?", (did,)).fetchone()


def test_aenderungsprotokoll(client, con):
    kid = kunde_anlegen(client)
    post(client, f"/kunden/{kid}", typ="privat", vorname="Anna", nachname="Schmidt", strasse="Hauptstraße 5",
         plz="74219", ort="Möckmühl", land="Deutschland", email="anna@example.com")
    z = con.execute("SELECT * FROM feldaenderungen WHERE objekt='kunde' AND objekt_id=? AND feld='Nachname' "
                    "AND aktion='geaendert'",
                    (kid,)).fetchone()
    assert (z["alt"], z["neu"], z["benutzer"]) == ("Müller", "Schmidt", "inhaber")
    assert re.match(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d[+-]", z["zeitpunkt"])
    assert "Änderungsprotokoll" in client.get(f"/kunden/{kid}").get_data(as_text=True)
    # Artikel
    post(client, "/artikel/neu", name="Akkutausch", preis="79,00", teilekosten="20,00", einheit="Stk.", steuersatz="19",
         typ="leistung", aktiv="on")
    aid = con.execute("SELECT id FROM artikel WHERE name='Akkutausch'").fetchone()[0]
    post(client, f"/artikel/{aid}", name="Akkutausch", preis="89,00", teilekosten="20,00", einheit="Stk.",
         steuersatz="19", typ="leistung", aktiv="on")
    z = con.execute("SELECT * FROM feldaenderungen WHERE objekt='artikel' AND objekt_id=? AND aktion='geaendert'",
                    (aid,)).fetchall()
    assert any(r["feld"] == "Preis (Cent)" and r["alt"] == "7900" and r["neu"] == "8900" for r in z)
    # Dokument-Entwurf: Positionen und Kopf, danach Festschreiben als Ereignis
    did = rechnung_anlegen(client, kid)
    # zweites Speichern mit anderem Betreff und Preis, dabei festschreiben
    client.post(f"/dokumente/{did}", data={
        "csrf": "test-token", "kunde_id": kid, "datum": "", "leistungsdatum": "2026-01-02", "zahlungsziel_tage": "",
        "betreff": "Reparatur iPhone", "einleitung": "", "schlusstext": "", "hinweise": "", "aktion": "festschreiben",
        "p_bezeichnung": ["Akkutausch"], "p_beschreibung": [""], "p_menge": ["1"], "p_einheit": ["Stk."],
        "p_preis": ["89,00"], "p_teilekosten": ["10,00"], "p_steuersatz": ["19"], "p_leistungsart": ["Smartphone"],
        "p_artikel_id": [""]})
    z = {r["feld"]: r for r in con.execute("SELECT * FROM feldaenderungen WHERE objekt='dokument' AND objekt_id=?",
                                           (did,))}
    assert z["Betreff"]["alt"] == "Reparatur" and z["Betreff"]["neu"] == "Reparatur iPhone"
    assert "79,00 €" in z["Positionen"]["alt"] and "89,00 €" in z["Positionen"]["neu"]
    assert con.execute("SELECT 1 FROM feldaenderungen WHERE objekt='dokument' AND objekt_id=? "
                       "AND aktion='festgeschrieben'", (did,)).fetchone()
    for sql in ["UPDATE feldaenderungen SET neu='x'", "DELETE FROM feldaenderungen"]:
        with pytest.raises(sqlite3.IntegrityError):
            con.execute(sql)


def test_kunde_loeschen_anonymisiert_bei_aufbewahrung(client, con):
    kid = kunde_anlegen(client)
    rid = rechnung_fest(client, kid)
    entwurf = rechnung_anlegen(client, kid)
    con.execute("INSERT INTO anfragen (eingang_am, quelle, status, einstufung, kunde_id, nachricht) "
                "VALUES (?, 'manuell', 'kunde_angelegt', 'echt', ?, 'Hallo')", (dbm.jetzt(), kid))
    seite = client.get(f"/kunden/{kid}/loeschen").get_data(as_text=True)
    assert "wird anonymisiert" in seite and "festgeschriebene" in seite and "Kontaktformular-Anfragen" in seite
    post(client, f"/kunden/{kid}/loeschen")
    k = con.execute("SELECT * FROM kunden WHERE id=?", (kid,)).fetchone()
    assert k["nachname"] == "Gelöschter Kunde" and k["vorname"] is None and k["email"] is None and k["strasse"] is None
    assert k["anonymisiert_am"] and k["archiviert"] == 1
    # Beleg bleibt unverändert mit Kundendaten
    snap = json.loads(con.execute("SELECT snapshot_json FROM dokumente WHERE id=?", (rid,)).fetchone()[0])
    assert "Müller" in snap["kunde"]["name"]
    assert not con.execute("SELECT 1 FROM dokumente WHERE id=?", (entwurf,)).fetchone()
    assert not con.execute("SELECT 1 FROM anfragen WHERE kunde_id=?", (kid,)).fetchone()
    assert "anonymisiert" in client.get(f"/kunden/{kid}").get_data(as_text=True)
    # Bearbeiten nicht mehr möglich
    post(client, f"/kunden/{kid}", typ="privat", nachname="Müller")
    assert con.execute("SELECT nachname FROM kunden WHERE id=?", (kid,)).fetchone()[0] == "Gelöschter Kunde"
    assert con.execute("SELECT 1 FROM protokoll WHERE aktion='kunde_anonymisiert'").fetchone()
    # ohne Aufbewahrungspflicht: vollständig gelöscht
    kid2 = kunde_anlegen(client, vorname="Bert")
    rechnung_anlegen(client, kid2)
    assert "vollständig gelöscht" in client.get(f"/kunden/{kid2}/loeschen").get_data(as_text=True)
    post(client, f"/kunden/{kid2}/loeschen")
    assert not con.execute("SELECT 1 FROM kunden WHERE id=?", (kid2,)).fetchone()


def test_einstellungen_und_verfahrensdoku(client, con):
    basis = dict(steuer_modus="kleinunternehmer", regel_steuersatz="19", kleinunternehmer_hinweis="§ 19",
                 zahlungsziel_privat="14", zahlungsziel_firma="30", zahlungsarten_text="", kva_gueltig_tage="30",
                 anzahlung_prozent="50", mahngebuehr_cent="3,95", mahnstufen="2",
                 nummern_format="{praefix}-{jahr}-{nummer:04d}", praefix_rechnung="RE", praefix_gutschrift="GS",
                 praefix_angebot="KV", praefix_kunde="K", leistungsarten="Smartphone",
                 aufbewahrung_belege_jahre="8", aufbewahrung_briefe_jahre="6")
    post(client, "/einstellungen/rechnung", **{**basis, "aufbewahrung_belege_jahre": "5"})
    assert dbm.einstellungen(con)["aufbewahrung_belege_jahre"] == 8
    post(client, "/einstellungen/rechnung", **{**basis, "praefix_gutschrift": "re"})
    assert dbm.einstellungen(con)["praefix_gutschrift"] == "GS"
    post(client, "/einstellungen/rechnung", **{**basis, "aufbewahrung_belege_jahre": "10"})
    assert dbm.einstellungen(con)["aufbewahrung_belege_jahre"] == 10
    seite = client.get("/verfahrensdokumentation").get_data(as_text=True)
    for t in ["Verfahrensdokumentation", "Festschreiben", "SHA-256", "10 Jahre", "bitte ergänzen", "65001/12345"]:
        assert t in seite, t
    assert "&lt;mark&gt;" not in seite and "<mark>[bitte ergänzen]</mark>" in seite
    r = client.get("/verfahrensdokumentation?pdf=1")
    assert r.data.startswith(b"%PDF")


def test_migration_mit_sicherung(tmp_path):
    pfad = tmp_path / "werkstatt.db"
    dbm.initialisieren(str(pfad))
    con = dbm.verbinden(str(pfad))
    con.execute("DROP TABLE feldaenderungen")
    con.execute("DROP TRIGGER dok_schutz_update")
    con.execute("ALTER TABLE dokumente DROP COLUMN snapshot_sha256")
    con.close()
    dbm.initialisieren(str(pfad))
    assert list((tmp_path / "backups").glob("vor_update_*.db"))
    con = dbm.verbinden(str(pfad))
    assert "snapshot_sha256" in {r["name"] for r in con.execute("PRAGMA table_info(dokumente)")}
    assert con.execute("SELECT 1 FROM sqlite_master WHERE name='dok_schutz_update'").fetchone()
    con.close()
