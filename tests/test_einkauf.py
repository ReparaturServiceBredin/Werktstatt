"""Phase 7: Lieferanten, Bezugsquellen, Bestellungen, Wareneingang, Eingangsrechnungen, Bankabgleich (Ausgänge)."""
import email.message
import hashlib
import io
import re
import sqlite3
from pathlib import Path

import pytest

from rsb import db as dbm

from conftest import kunde_anlegen, post
from test_annahme import auftrag_mit_annahme
from test_lager import artikel_anlegen, bestand


def lieferant_anlegen(client, con, name="iParts GmbH", **extra):
    daten = dict(name=name, email="bestellung@iparts.de", kundennr_bei="KD-4711", lieferzeit_tage="3",
                 zahlungsziel_tage="14", webshop="https://iparts.example", kreditornr="70001")
    daten.update(extra)
    r = post(client, "/lieferanten/neu", **daten)
    return int(re.search(r"/lieferanten/(\d+)", r.headers["Location"]).group(1))


def test_bezugsquellen_guenstigster_und_marge(client, con):
    art = artikel_anlegen(client, con, ek="30,00")  # VK 89,00
    l1 = lieferant_anlegen(client, con)
    l2 = lieferant_anlegen(client, con, name="Teilehandel Süd")
    post(client, f"/artikel/{art}/bezugsquelle", lieferant_id=str(l1), ek="32,00", lieferanten_artnr="IP-1",
         garantie_monate="6")
    post(client, f"/artikel/{art}/bezugsquelle", lieferant_id=str(l2), ek="28,50", lieferanten_artnr="TS-9")
    seite = client.get(f"/artikel/{art}").get_data(as_text=True)
    assert seite.index("Teilehandel Süd") < seite.index("iParts GmbH") and "günstigster" in seite
    # EK übernehmen → Marge unter 30 % → Warnung
    r = client.post(f"/artikel/{art}/bezugsquelle", data={"csrf": "test-token", "lieferant_id": str(l2), "ek": "70,00",
                                                          "als_ek": "1"}, follow_redirects=True)
    assert "Marge" in r.get_data(as_text=True) and "Grenze 30 %" in r.get_data(as_text=True)
    assert con.execute("SELECT teilekosten FROM artikel WHERE id=?", (art,)).fetchone()[0] == 7000
    assert "EK geändert" in client.get(f"/artikel/{art}").get_data(as_text=True)


def test_bestellung_fuer_auftrag_und_wareneingang(client, con, app):
    art = artikel_anlegen(client, con, name="Display iPhone 13", ek="120,00")
    lid = lieferant_anlegen(client, con)
    post(client, f"/artikel/{art}/bezugsquelle", lieferant_id=str(lid), ek="115,00", lieferanten_artnr="IP-D13",
         garantie_monate="12")
    kid = kunde_anlegen(client)
    aid = auftrag_mit_annahme(client, kid)
    assert "Teil für diesen Auftrag bestellen" in client.get(f"/auftraege/{aid}").get_data(as_text=True)
    r = post(client, "/bestellungen/neu", lieferant_id=str(lid), auftrag_id=str(aid), notiz="eilt",
             p_artikel_id=[str(art)], p_bezeichnung=["Display iPhone 13"], p_artnr=["IP-D13"], p_menge=["1"],
             p_ek=["115,00"])
    bid = int(re.search(r"/bestellungen/(\d+)", r.headers["Location"]).group(1))
    b = con.execute("SELECT * FROM bestellungen WHERE id=?", (bid,)).fetchone()
    assert re.match(r"BE-\d{4}-0001", b["nummer"]) and b["status"] == "entwurf" and b["erwartet_am"]
    assert client.get(f"/bestellungen/{bid}/pdf").data.startswith(b"%PDF")
    post(client, f"/bestellungen/{bid}", aktion="bestellt", erwartet_am="2026-10-30")
    a = con.execute("SELECT * FROM auftraege WHERE id=?", (aid,)).fetchone()
    assert a["wartet_teil_seit"] and a["teil_erwartet"] == "2026-10-30" and b["nummer"] in a["teil_info"]
    tafel = client.get("/auftraege").get_data(as_text=True)
    assert "30.10.2026" in tafel and "Display iPhone 13" in tafel
    # Wareneingang mit neuem EK
    pos = con.execute("SELECT id FROM bestell_positionen WHERE bestellung_id=?", (bid,)).fetchone()[0]
    post(client, f"/bestellungen/{bid}", aktion="wareneingang", lieferschein="LS-1", auftrag_fortsetzen="1",
         **{f"menge_{pos}": "1", f"ek_{pos}": "118,00"})
    assert bestand(con, art) == 1
    assert con.execute("SELECT teilekosten FROM artikel WHERE id=?", (art,)).fetchone()[0] == 11800
    assert con.execute("SELECT status FROM bestellungen WHERE id=?", (bid,)).fetchone()[0] == "geliefert"
    a = con.execute("SELECT * FROM auftraege WHERE id=?", (aid,)).fetchone()
    assert a["status"] == "in_arbeit" and a["wartet_teil_seit"] is None
    assert con.execute("SELECT 1 FROM auftrag_verlauf WHERE auftrag_id=? AND ereignis='Ersatzteil eingetroffen'",
                       (aid,)).fetchone()
    r = con.execute("SELECT * FROM lager_reservierungen WHERE auftrag_id=?", (aid,)).fetchone()
    assert r and r["status"] == "reserviert"
    w = con.execute("SELECT * FROM wareneingaenge WHERE bestellung_id=?", (bid,)).fetchone()
    assert w["garantie_bis"] and w["lieferschein"] == "LS-1"
    with pytest.raises(sqlite3.DatabaseError):
        con.execute("DELETE FROM wareneingaenge")
    # Material nach Erledigen: Lieferant und Lieferantengarantie sichtbar
    post(client, f"/auftraege/{aid}/status", status="erledigt", ohne_kva="1")
    seite = client.get(f"/auftraege/{aid}").get_data(as_text=True)
    assert "Lieferantengarantie bis" in seite and "iParts GmbH" in seite
    # zu viel liefern → Fehler, Bestellung bleibt
    post(client, f"/bestellungen/{bid}", aktion="wareneingang", **{f"menge_{pos}": "1"})
    assert bestand(con, art) == 0


def test_bestellvorschlag_zu_bestellungen(client, con):
    a1 = artikel_anlegen(client, con, name="Akku A", mindest="2")
    a2 = artikel_anlegen(client, con, name="Akku B", mindest="1")
    l1 = lieferant_anlegen(client, con)
    post(client, f"/artikel/{a1}/bezugsquelle", lieferant_id=str(l1), ek="10,00")
    r = post(client, "/bestellungen/aus-vorschlag", artikel_id=[str(a1), str(a2)], **{f"menge_{a1}": "4",
                                                                                      f"menge_{a2}": "2"})
    assert r.status_code == 302
    b = con.execute("SELECT * FROM bestellungen").fetchall()
    assert len(b) == 1 and b[0]["lieferant_id"] == l1
    p = con.execute("SELECT * FROM bestell_positionen").fetchall()
    assert len(p) == 1 and p[0]["menge"] == 4 and p[0]["ek"] == 1000


def test_eingangsrechnung_upload_zahlung_storno(client, con, app):
    lid = lieferant_anlegen(client, con)
    pdf = b"%PDF-1.4 Rechnung 123"
    r = client.post("/eingangsrechnungen/neu", content_type="multipart/form-data", data={
        "csrf": "test-token", "datei": (io.BytesIO(pdf), "RE-123.pdf"), "lieferant_id": str(lid), "nummer": "RE-123",
        "datum": "2026-10-10", "netto": "100,00", "steuersatz": "19", "steuer": "", "brutto": "",
        "kostenart": "Wareneinkauf / Ersatzteile", "aktion": "speichern"})
    eid = int(re.search(r"/eingangsrechnungen/(\d+)", r.headers["Location"]).group(1))
    e = con.execute("SELECT * FROM eingangsrechnungen WHERE id=?", (eid,)).fetchone()
    assert e["brutto"] == 11900 and e["steuer"] == 1900 and e["faellig_am"] == "2026-10-24"
    assert re.match(r"ER-\d{4}-0001", e["lfd_nr"]) and e["datei_sha256"] == hashlib.sha256(pdf).hexdigest()
    assert client.get(f"/eingangsrechnungen/datei/{e['datei_sha256']}").data == pdf
    # Doppelt (gleiche Nummer) → abgelehnt
    client.post("/eingangsrechnungen/neu", data={"csrf": "test-token", "lieferant_id": str(lid), "nummer": "RE-123",
                                                 "datum": "2026-10-10", "brutto": "119,00"})
    assert con.execute("SELECT COUNT(*) FROM eingangsrechnungen").fetchone()[0] == 1
    # Ändern wird protokolliert, Datei bleibt geschützt
    post(client, f"/eingangsrechnungen/{eid}", aktion="speichern", lieferant_id=str(lid), nummer="RE-123",
         datum="2026-10-10", netto="100,00", steuer="19,00", brutto="119,00", steuersatz="19", kostenart="Werkzeug & Geräte")
    assert "Werkzeug" in client.get(f"/eingangsrechnungen/{eid}").get_data(as_text=True)
    with pytest.raises(sqlite3.DatabaseError):
        con.execute("UPDATE eingangsrechnungen SET datei_sha256='x' WHERE id=?", (eid,))
    with pytest.raises(sqlite3.DatabaseError):
        con.execute("DELETE FROM eingangsrechnungen WHERE id=?", (eid,))
    # Zahlung → bezahlt; Storno nur ohne Zahlung
    post(client, f"/eingangsrechnungen/{eid}", aktion="zahlung", datum="2026-10-12", betrag="119,00",
         zahlart="ueberweisung")
    assert con.execute("SELECT status FROM eingangsrechnungen WHERE id=?", (eid,)).fetchone()[0] == "bezahlt"
    post(client, f"/eingangsrechnungen/{eid}", aktion="stornieren", grund="doppelt")
    assert con.execute("SELECT status FROM eingangsrechnungen WHERE id=?", (eid,)).fetchone()[0] == "bezahlt"
    z = con.execute("SELECT id FROM er_zahlungen").fetchone()[0]
    post(client, f"/eingangsrechnungen/{eid}", aktion="zahlung_storno", zahlung_id=str(z), grund="falsch")
    post(client, f"/eingangsrechnungen/{eid}", aktion="stornieren", grund="doppelt erfasst")
    assert con.execute("SELECT status FROM eingangsrechnungen WHERE id=?", (eid,)).fetchone()[0] == "storniert"
    seite = client.get("/pruefung").get_data(as_text=True)
    assert "ER-" not in seite.split("Lückenlose Nummernfolge")[1].split("</div>")[0]
    # Originaldatei manipuliert → Datenprüfung meldet es
    (Path(app.config["DATEN"]) / e["datei"]).write_bytes(b"manipuliert")
    assert "Originaldatei wurde verändert" in client.get("/pruefung").get_data(as_text=True)


def test_bank_ausgang_zuordnen(client, con):
    lid = lieferant_anlegen(client, con)
    client.post("/eingangsrechnungen/neu", data={"csrf": "test-token", "lieferant_id": str(lid), "nummer": "R-2026-77",
                                                 "datum": "2026-10-01", "brutto": "59,50", "steuersatz": "19"})
    eid = con.execute("SELECT id FROM eingangsrechnungen").fetchone()[0]
    csv = ("Buchungstag;Valutadatum;Name Zahlungsbeteiligter;IBAN Zahlungsbeteiligter;Verwendungszweck;Betrag\n"
           "05.10.2026;05.10.2026;iParts GmbH;DE02120300000000202051;Rechnung R-2026-77;-59,50\n").encode("utf-8")
    client.post("/bank", data={"csrf": "test-token", "datei": (io.BytesIO(csv), "umsaetze.csv")},
                content_type="multipart/form-data")
    seite = client.get("/bank").get_data(as_text=True)
    assert "Rechnungsnummer R-2026-77 im Verwendungszweck" in seite
    uid = con.execute("SELECT id FROM bank_umsaetze").fetchone()[0]
    post(client, f"/bank/{uid}/eingangsrechnung", eingangsrechnung_id=str(eid))
    assert con.execute("SELECT status FROM eingangsrechnungen WHERE id=?", (eid,)).fetchone()[0] == "bezahlt"
    u = con.execute("SELECT * FROM bank_umsaetze WHERE id=?", (uid,)).fetchone()
    assert u["status"] == "zugeordnet" and u["er_zahlung_id"]
    # Zahlung stornieren → Umsatz wieder offen
    post(client, f"/eingangsrechnungen/{eid}", aktion="zahlung_storno", zahlung_id=str(u["er_zahlung_id"]), grund="x falsch")
    assert con.execute("SELECT status FROM bank_umsaetze WHERE id=?", (uid,)).fetchone()[0] == "offen"


class FalschesPostfach:
    mails = {}

    def __init__(self, *a, **k):
        pass

    def login(self, *a):
        return "OK", []

    def select(self, name, readonly=False):
        assert readonly
        return ("OK", [b"1"]) if name.strip('"') == "Rechnungen" else ("NO", [])

    def uid(self, befehl, *args):
        if befehl == "SEARCH":
            return "OK", [b" ".join(str(u).encode() for u in self.mails)]
        uid = int(args[0])
        assert b"PEEK" in args[1].encode() if isinstance(args[1], str) else True
        return "OK", [(b"1 (BODY[] {1}", self.mails[uid]), b")"]

    def logout(self):
        pass


def test_postfach_uebernehmen(client, con, monkeypatch):
    import imaplib
    msg = email.message.EmailMessage()
    msg["From"] = "iParts Buchhaltung <rechnung@iparts.de>"
    msg["Subject"] = "Ihre Rechnung R-99"
    msg["Date"] = "Mon, 12 Oct 2026 10:00:00 +0200"
    msg["Message-ID"] = "<r99@iparts.de>"
    msg.set_content("Anbei Ihre Rechnung.")
    msg.add_attachment(b"%PDF-1.4 R-99", maintype="application", subtype="pdf", filename="R-99.pdf")
    FalschesPostfach.mails = {5: msg.as_bytes()}
    monkeypatch.setattr(imaplib, "IMAP4_SSL", FalschesPostfach)
    from rsb.sicherheit import verschluesseln
    with dbm.Transaktion(con):
        dbm.einstellungen_speichern({"imap_host": "imap.example", "imap_benutzer": "ich@x.de", "imap_port": 993,
                                     "imap_sicherheit": "ssl", "er_imap_ordner": "Rechnungen"}, con)
    with client.application.app_context():
        with dbm.Transaktion(con):
            dbm.einstellungen_speichern({"imap_passwort_enc": verschluesseln("geheim")}, con)
    lid = lieferant_anlegen(client, con, email="rechnung@iparts.de")
    seite = client.get("/eingangsrechnungen/postfach").get_data(as_text=True)
    assert "R-99.pdf" in seite and "Ihre Rechnung R-99" in seite
    r = post(client, "/eingangsrechnungen/postfach", uid="5", index=re.search(r'name="index" value="(\d+)"', seite).group(1))
    assert r.headers["Location"].endswith("/eingangsrechnungen/neu")
    neu = client.get("/eingangsrechnungen/neu").get_data(as_text=True)
    assert "R-99.pdf" in neu and "2026-10-12" in neu and f'value="{lid}" selected' in neu
    post(client, "/eingangsrechnungen/neu", lieferant_id=str(lid), nummer="R-99", datum="2026-10-12", brutto="10,00")
    e = con.execute("SELECT * FROM eingangsrechnungen").fetchone()
    assert e["quelle"] == "Postfach" and e["message_id"] == "<r99@iparts.de>" and e["datei_name"] == "R-99.pdf"
    assert "bereits erfasst" in client.get("/eingangsrechnungen/postfach").get_data(as_text=True)
