import re
from datetime import date

from rsb import db as dbm
from rsb import vertraege as vtr

from conftest import kunde_anlegen, post


def vertrag_anlegen(client, kid, **felder):
    daten = {"kunde_id": kid, "bezeichnung": "MSP Basis", "kategorie": "MSP", "abrechnung": "monatlich",
             "beginn": "2026-01-01", "laufzeit_monate": "", "mindestlaufzeit_monate": "12", "preis": "49,00",
             "einkauf": "10,00", "anzahl": "1", "vertragsnummer": "", "geraet": "", "notizen": ""}
    daten.update(felder)
    r = post(client, "/vertraege/neu", **daten)
    return int(re.search(r"/vertraege/(\d+)", r.headers["Location"]).group(1))


def zeile(con, vid):
    return con.execute("SELECT * FROM vertraege WHERE id=?", (vid,)).fetchone()


def test_monatlich_nachholen_und_keine_doppelten(client, con):
    kid = kunde_anlegen(client)
    vid = vertrag_anlegen(client, kid)
    assert len(vtr.faellige_zeitraeume(con, zeile(con, vid), date(2026, 3, 15))) == 3
    neue = vtr.abrechnen(con, date(2026, 3, 15))
    assert len(neue) == 1  # ein Kunde -> eine Rechnung
    pos = con.execute("SELECT * FROM positionen WHERE dokument_id=? ORDER BY pos", (neue[0],)).fetchall()
    assert len(pos) == 3 and "Zeitraum 01.03.2026 – 31.03.2026" in pos[2]["beschreibung"]
    d = con.execute("SELECT * FROM dokumente WHERE id=?", (neue[0],)).fetchone()
    assert d["summe_brutto"] == 3 * 4900 and d["leistungsdatum"] == "2026-01-01" and d["leistungsdatum_bis"] == "2026-03-31"
    assert vtr.abrechnen(con, date(2026, 3, 15)) == []  # nichts doppelt
    assert len(vtr.abrechnen(con, date(2026, 4, 1))) == 1  # April fällig


def test_kuendigung_stoppt_abrechnung(client, con):
    kid = kunde_anlegen(client)
    vid = vertrag_anlegen(client, kid)
    vtr.abrechnen(con, date(2026, 2, 10))  # Jan + Feb
    post(client, f"/vertraege/{vid}/kuendigen", kuendigung_zum="2026-03-31", kuendigungsgrund="zu teuer",
         gekuendigt_am="2026-02-10")
    v = zeile(con, vid)
    assert v["status"] == "gekuendigt" and v["kuendigung_zum"] == "2026-03-31"
    zeitraeume = vtr.faellige_zeitraeume(con, v, date(2026, 12, 31))
    assert [(a.isoformat(), b.isoformat()) for a, b in zeitraeume] == [("2026-03-01", "2026-03-31")]
    assert vtr.zustand(v, heute=date(2026, 3, 1))[0] == "gekuendigt"
    assert vtr.zustand(v, heute=date(2026, 4, 1))[0] == "beendet"
    # Kündigung zurücknehmen -> läuft weiter
    post(client, f"/vertraege/{vid}/kuendigen", zuruecknehmen="1")
    assert len(vtr.faellige_zeitraeume(con, zeile(con, vid), date(2026, 5, 1))) == 3


def test_lizenz_mit_laufzeit_einmalig_und_verlaengern(client, con):
    kid = kunde_anlegen(client)
    vid = vertrag_anlegen(client, kid, bezeichnung="ESET – 2 Jahre", kategorie="Lizenz", abrechnung="laufzeit",
                          laufzeit_monate="24", mindestlaufzeit_monate="", preis="79,00", vertragsnummer="ABCD-1234",
                          beginn="2026-02-15")
    assert zeile(con, vid)["ende"] == "2028-02-14"
    neue = vtr.abrechnen(con, date(2026, 2, 15))
    pos = con.execute("SELECT * FROM positionen WHERE dokument_id=?", (neue[0],)).fetchone()
    assert pos["einzelpreis"] == 7900 and "ABCD-1234" in pos["beschreibung"]
    assert vtr.abrechnen(con, date(2029, 1, 1)) == []  # ohne Auto-Verlängerung keine weitere Rechnung
    assert vtr.zustand(zeile(con, vid), heute=date(2028, 1, 1))[0] == "laeuft_ab"
    assert vtr.zustand(zeile(con, vid), heute=date(2028, 3, 1))[0] == "abgelaufen"
    # manuell verlängern
    r = post(client, f"/vertraege/{vid}/verlaengern")
    assert "/dokumente/" in r.headers["Location"]
    assert zeile(con, vid)["ende"] == "2030-02-14"


def test_lizenz_automatisch_verlaengern(client, con):
    kid = kunde_anlegen(client)
    vid = vertrag_anlegen(client, kid, abrechnung="laufzeit", laufzeit_monate="12", beginn="2026-01-01",
                          auto_verlaengern="on", mindestlaufzeit_monate="")
    vtr.abrechnen(con, date(2026, 1, 1))
    assert vtr.abrechnen(con, date(2026, 12, 31)) == []
    assert len(vtr.abrechnen(con, date(2027, 1, 1))) == 1
    assert zeile(con, vid)["ende"] == "2027-12-31"


def test_nur_dokumentation_und_mehrere_vertraege(client, con):
    kid = kunde_anlegen(client)
    vertrag_anlegen(client, kid, bezeichnung="Wertgarantie", kategorie="Garantie/Versicherung", abrechnung="keine",
                    laufzeit_monate="24", geraet="iPhone 15, IMEI 3567", preis="0")
    vertrag_anlegen(client, kid, bezeichnung="MSP", beginn="2026-05-01")
    vertrag_anlegen(client, kid, bezeichnung="Backup", beginn="2026-05-01", preis="9,90", anzahl="2")
    neue = vtr.abrechnen(con, date(2026, 5, 2))
    assert len(neue) == 1
    assert con.execute("SELECT summe_brutto FROM dokumente WHERE id=?", (neue[0],)).fetchone()[0] == 4900 + 1980
    assert con.execute("SELECT COUNT(*) FROM positionen WHERE dokument_id=?", (neue[0],)).fetchone()[0] == 2


def test_geloeschter_entwurf_gibt_zeitraum_frei(client, con):
    kid = kunde_anlegen(client)
    vid = vertrag_anlegen(client, kid, beginn="2026-01-01")
    neue = vtr.abrechnen(con, date(2026, 1, 5))
    post(client, f"/dokumente/{neue[0]}/loeschen")
    assert len(vtr.faellige_zeitraeume(con, zeile(con, vid), date(2026, 1, 5))) == 1


def test_automatisch_festschreiben(client, con, app, monkeypatch):
    kid = kunde_anlegen(client)
    vertrag_anlegen(client, kid, beginn=date.today().replace(day=1).isoformat())
    with dbm.Transaktion(con):
        dbm.einstellungen_speichern({"abo_modus": "automatisch"}, con)
    e = vtr.abrechnungslauf(con, app.config["DATEN"])
    assert e["rechnungen"] == 1 and e["festgeschrieben"] == 1
    assert e["versendet"] == 0 and e["fehler"]  # kein E-Mail-Zugang eingerichtet -> Hinweis
    d = con.execute("SELECT * FROM dokumente WHERE typ='rechnung'").fetchone()
    assert d["status"] == "festgeschrieben" and d["nummer"].startswith("RE-")


def test_seiten(client, con):
    kid = kunde_anlegen(client)
    vid = vertrag_anlegen(client, kid)
    for url in ["/vertraege", "/vertraege?filter=alle", "/vertraege?filter=gekuendigt", f"/vertraege/{vid}",
                f"/vertraege/neu?kunde_id={kid}", "/vertragsarten", "/vertragsarten?neu=1", "/vertragsarten/1",
                f"/kunden/{kid}", "/", "/einstellungen/vertraege"]:
        assert client.get(url).status_code == 200, url
    post(client, "/vertragsarten", name="ESET Internet Security 3 Geräte", kategorie="Lizenz", abrechnung="laufzeit",
         laufzeit_monate="12", preis="59,90", einkauf="35,00", aktiv="on", beschreibung="")
    assert con.execute("SELECT preis FROM vertragsarten WHERE name LIKE 'ESET Internet%'").fetchone()[0] == 5990
    with dbm.Transaktion(con):
        dbm.einstellungen_speichern({"abo_modus": "entwurf"}, con)
    r = post(client, "/vertraege/abrechnen")
    assert r.status_code == 302
    # Vertrag mit festgeschriebener Rechnung lässt sich nicht löschen
    from rsb import logik
    did = con.execute("SELECT dokument_id FROM vertrag_abrechnungen WHERE vertrag_id=?", (vid,)).fetchone()[0]
    con.execute("UPDATE dokumente SET datum=? WHERE id=?", (date.today().isoformat(), did))
    logik.festschreiben(con, did, client.application.config["DATEN"])
    post(client, f"/vertraege/{vid}/loeschen")
    assert zeile(con, vid) is not None


def test_bestehenden_vertrag_uebernehmen(client, con):
    kid = kunde_anlegen(client)
    vid = vertrag_anlegen(client, kid, beginn="2025-01-01", abgerechnet_bis="2026-09-30")
    z = vtr.faellige_zeitraeume(con, zeile(con, vid), date(2026, 10, 15))
    assert [(a.isoformat(), b.isoformat()) for a, b in z] == [("2026-10-01", "2026-10-31")]
    lz = vertrag_anlegen(client, kid, abrechnung="laufzeit", laufzeit_monate="36", beginn="2025-03-01",
                         abgerechnet_bis="2028-02-29", mindestlaufzeit_monate="")
    assert vtr.faellige_zeitraeume(con, zeile(con, lz), date(2026, 10, 15)) == []


def test_standard_vollautomatisch(app, con):
    assert dbm.einstellungen(con)["abo_modus"] == "automatisch"
    # bestehende Installation mit "entwurf" wird einmalig umgestellt, danach bleibt die eigene Wahl erhalten
    con.execute("UPDATE einstellungen SET wert='\"entwurf\"' WHERE schluessel='abo_modus'")
    con.execute("DELETE FROM einstellungen WHERE schluessel='umstellung_abo_automatisch'")
    dbm.initialisieren(app.config["DB_PFAD"])
    assert dbm.einstellungen(con)["abo_modus"] == "automatisch"
    con.execute("UPDATE einstellungen SET wert='\"entwurf\"' WHERE schluessel='abo_modus'")
    dbm.initialisieren(app.config["DB_PFAD"])
    assert dbm.einstellungen(con)["abo_modus"] == "entwurf"
