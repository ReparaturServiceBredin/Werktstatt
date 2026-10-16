"""Phase 2: Zahlungen, offene Posten, Mahnwesen, Bankabgleich."""
import io
import re
import sqlite3
from datetime import date, timedelta

import pytest
from pypdf import PdfReader

from rsb import bankabgleich as ba
from rsb import db as dbm
from rsb import mahnwesen as mw
from rsb import zahlungen as zlg

from conftest import kunde_anlegen, post, rechnung_anlegen


def tage(n):
    return (date.today() + timedelta(days=n)).isoformat()


def rechnung(client, con, kid, preis="100,00", vor_tagen=0):
    did = rechnung_anlegen(client, kid, positionen=(("Reparatur", preis, "1"),), festschreiben=True,
                           datum=tage(-vor_tagen), leistungsdatum=tage(-vor_tagen))
    d = con.execute("SELECT * FROM dokumente WHERE id=?", (did,)).fetchone()
    assert d["status"] == "festgeschrieben", "Testrechnung konnte nicht festgeschrieben werden"
    return d


def test_zahlungen_status_und_storno(client, con):
    kid = kunde_anlegen(client)
    d = rechnung(client, con, kid)
    assert zlg.stand(con, d)["status"] == "offen"
    post(client, f"/dokumente/{d['id']}/zahlung", datum=tage(0), betrag="40,00", zahlart="bar", notiz="Anzahlung")
    s = zlg.stand(con, d)
    assert (s["status"], s["bezahlt"], s["offen"]) == ("teilweise", 4000, 6000)
    post(client, f"/dokumente/{d['id']}/zahlung", datum=tage(0), betrag="60,00", zahlart="ueberweisung")
    assert zlg.stand(con, d)["status"] == "bezahlt"
    assert con.execute("SELECT bezahlt_betrag FROM dokumente WHERE id=?", (d["id"],)).fetchone()[0] == 10000
    # Zahlung in der Zukunft / ohne Betrag abgelehnt
    post(client, f"/dokumente/{d['id']}/zahlung", datum=tage(3), betrag="1,00", zahlart="bar")
    post(client, f"/dokumente/{d['id']}/zahlung", datum=tage(0), betrag="", zahlart="bar")
    assert con.execute("SELECT COUNT(*) FROM zahlungen").fetchone()[0] == 2
    # Storno nur mit Grund, Datensatz bleibt
    zid = con.execute("SELECT id FROM zahlungen WHERE betrag=6000").fetchone()[0]
    post(client, f"/zahlungen/{zid}/stornieren", grund="")
    assert zlg.stand(con, d)["status"] == "bezahlt"
    post(client, f"/zahlungen/{zid}/stornieren", grund="Fehlbuchung")
    assert zlg.stand(con, d)["offen"] == 6000
    for sql in ["DELETE FROM zahlungen", "UPDATE zahlungen SET betrag=1"]:
        with pytest.raises(sqlite3.IntegrityError):
            con.execute(sql)
    # Anzeige: Rechnung, Kunde, offene Posten, Liste
    assert "Zahlungen" in client.get(f"/dokumente/{d['id']}").get_data(as_text=True)
    seite = client.get(f"/kunden/{kid}").get_data(as_text=True)
    assert "Zahlungshistorie" in seite and "Fehlbuchung" not in seite and "60,00 €" in seite
    seite = client.get("/verkauf/offene-posten").get_data(as_text=True)
    assert d["nummer"] in seite and "60,00 €" in seite
    assert "teilweise bezahlt" in client.get("/verkauf/rechnungen").get_data(as_text=True)
    # Gutschrift mindert den offenen Betrag
    r = post(client, f"/dokumente/{d['id']}/gutschrift")
    gid = int(re.search(r"/dokumente/(\d+)", r.headers["Location"]).group(1))
    client.post(f"/dokumente/{gid}", data={
        "csrf": "test-token", "kunde_id": kid, "datum": "", "leistungsdatum": d["leistungsdatum"], "zahlungsziel_tage": "",
        "betreff": "Gutschrift", "einleitung": "", "schlusstext": "", "hinweise": "", "aktion": "festschreiben",
        "p_bezeichnung": ["Nachlass"], "p_beschreibung": [""], "p_menge": ["1"], "p_einheit": [""], "p_preis": ["10,00"],
        "p_teilekosten": [""], "p_steuersatz": ["19"], "p_leistungsart": [""], "p_artikel_id": [""]})
    assert zlg.stand(con, d)["offen"] == 5000


def test_mahnwesen_ablauf(client, con, monkeypatch):
    kid = kunde_anlegen(client)
    d = rechnung(client, con, kid, "200,00", vor_tagen=30)  # Zahlungsziel 14 Tage → seit 16 Tagen überfällig
    assert zlg.stand(con, d)["status"] == "ueberfaellig"
    v = mw.vorschlaege(con)
    assert [(x["d"]["id"], x["stufe"]) for x in v] == [(d["id"], 0)]
    assert "Zahlungserinnerung" in client.get("/verkauf/mahnwesen").get_data(as_text=True)
    # Stufen können nicht übersprungen werden
    with pytest.raises(Exception):
        mw.erstellen(con, d["id"], 1, client.application.config["DATEN"])
    post(client, "/mahnwesen/erstellen", auswahl=f"{d['id']}:0")
    m0 = con.execute("SELECT * FROM mahnungen WHERE dokument_id=?", (d["id"],)).fetchone()
    assert m0["stufe"] == 0 and m0["gebuehr"] == 0 and m0["gesamt"] == 20000 and m0["nummer"].startswith("MA-")
    text = "\n".join(s.extract_text() for s in PdfReader(io.BytesIO(client.get(f"/mahnungen/{m0['id']}/pdf").data)).pages)
    for t in ["Zahlungserinnerung", d["nummer"], "Offener Betrag aus Rechnung", "200,00"]:
        assert t in text, t
    # 1. Mahnung erst nach Frist + 7 Tagen fällig
    assert not mw.vorschlaege(con)
    spaeter = (date.fromisoformat(m0["frist_bis"]) + timedelta(days=7)).isoformat()
    assert [x["stufe"] for x in mw.vorschlaege(con, heute=spaeter)] == [1]
    with dbm.Transaktion(con):
        dbm.einstellungen_speichern({"zinsen_aktiv": True, "basiszinssatz": "2.27"}, con)
    m1 = con.execute("SELECT * FROM mahnungen WHERE id=?",
                     (mw.erstellen(con, d["id"], 1, client.application.config["DATEN"], heute=spaeter),)).fetchone()
    assert (m1["gebuehr"], m1["zinsen"], m1["gesamt"]) == (395, 0, 20395)  # Zinsen laufen erst ab 1. Mahnung
    noch_spaeter = (date.fromisoformat(m1["frist_bis"]) + timedelta(days=7)).isoformat()
    m2 = con.execute("SELECT * FROM mahnungen WHERE id=?",
                     (mw.erstellen(con, d["id"], 2, client.application.config["DATEN"], heute=noch_spaeter),)).fetchone()
    tage_zins = (date.fromisoformat(noch_spaeter) - date.fromisoformat(m1["datum"])).days
    assert m2["gebuehren_vorher"] == 395 and m2["gebuehr"] == 395
    assert m2["zinsen"] == round(20000 * (2.27 + 5) / 100 * tage_zins / 365)
    assert m2["gesamt"] == 20000 + 790 + m2["zinsen"]
    # keine 3. Mahnung
    assert mw.naechste_stufe(con, d, heute=noch_spaeter) == (None, None)
    # Versand per E-Mail
    from rsb import views
    gesendet = []
    monkeypatch.setattr(views, "senden", lambda con, e, an, b, t, pdf, name, did: gesendet.append((an, name, did)))
    post(client, f"/mahnungen/{m2['id']}/email", an="anna@example.com", betreff="2. Mahnung", text="Bitte zahlen")
    assert gesendet == [("anna@example.com", f"{m2['nummer']}.pdf", d["id"])]
    assert con.execute("SELECT versandart FROM mahnungen WHERE id=?", (m2["id"],)).fetchone()[0] == "email"
    # Archiv unveränderbar
    for sql in ["UPDATE mahnungen SET gesamt=1", "DELETE FROM mahnungen"]:
        with pytest.raises(sqlite3.IntegrityError):
            con.execute(sql)
    # Gebühren erlassen, dann Zahlung des Rechnungsbetrags → bezahlt
    post(client, f"/mahnungen/{m1['id']}/erlassen", grund="Kulanz")
    post(client, f"/mahnungen/{m2['id']}/erlassen", grund="Kulanz")
    post(client, f"/dokumente/{d['id']}/zahlung", datum=tage(0), betrag="200,00", zahlart="ueberweisung")
    s = zlg.stand(con, d)
    assert s["status"] == "bezahlt" and s["gebuehren_offen"] == 0


SPARKASSE = ('"Auftragskonto";"Buchungstag";"Valutadatum";"Buchungstext";"Verwendungszweck";"Glaeubiger ID";'
             '"Mandatsreferenz";"Kundenreferenz (End-to-End)";"Sammlerreferenz";"Lastschrift Ursprungsbetrag";'
             '"Auslagenersatz Ruecklastschrift";"Beguenstigter/Zahlungspflichtiger";"Kontonummer/IBAN";'
             '"BIC (SWIFT-Code)";"Betrag";"Waehrung";"Info"\n'
             '"DE111";"{tag}";"{tag}";"GUTSCHR. UEBERWEISUNG";"Rechnung {nr} Danke";"";"";"";"";"";"";"Anna Mueller";'
             '"DE02120300000000202051";"BYLADEM1001";"100,00";"EUR";"Umsatz gebucht"\n'
             '"DE111";"{tag}";"{tag}";"FOLGELASTSCHRIFT";"Strom";"";"";"";"";"";"";"Stadtwerke";"DE999";"";"-58,40";'
             '"EUR";"Umsatz gebucht"\n')


def test_bank_csv_camt_vorschlag_zuordnung(client, con):
    kid = kunde_anlegen(client)
    d = rechnung(client, con, kid)
    d2 = rechnung(client, con, kid, "49,90")
    tag = date.today().strftime("%d.%m.%y")
    datei = SPARKASSE.format(tag=tag, nr=d["nummer"].replace("-", " ")).encode("cp1252")
    r = client.post("/bank", data={"csrf": "test-token", "datei": (io.BytesIO(datei), "umsaetze.csv")},
                    content_type="multipart/form-data")
    assert r.status_code == 302
    u = con.execute("SELECT * FROM bank_umsaetze WHERE betrag > 0").fetchone()
    assert u["name"] == "Anna Mueller" and u["buchungstag"] == date.today().isoformat()
    assert con.execute("SELECT betrag FROM bank_umsaetze WHERE betrag < 0").fetchone()[0] == -5840
    # erneuter Import: nichts doppelt
    with dbm.Transaktion(con):
        e = ba.importieren(con, "umsaetze.csv", datei)
    assert (e["neu"], e["doppelt"]) == (0, 2)
    v = ba.vorschlag(con, u)
    assert v["p"]["d"]["id"] == d["id"] and v["sicher"]
    assert "Vorschlag" in client.get("/bank").get_data(as_text=True)
    post(client, f"/bank/{u['id']}/zuordnen", dokument_id=d["id"])
    assert zlg.stand(con, d)["status"] == "bezahlt"
    z = con.execute("SELECT * FROM zahlungen WHERE bank_umsatz_id=?", (u["id"],)).fetchone()
    assert z["zahlart"] == "ueberweisung" and z["betrag"] == 10000
    assert con.execute("SELECT status FROM bank_umsaetze WHERE id=?", (u["id"],)).fetchone()[0] == "zugeordnet"
    # Zahlung stornieren gibt den Umsatz wieder frei
    post(client, f"/zahlungen/{z['id']}/stornieren", grund="falsch zugeordnet")
    assert con.execute("SELECT status FROM bank_umsaetze WHERE id=?", (u["id"],)).fetchone()[0] == "offen"
    # Ausgang ignorieren / wieder öffnen
    aus = con.execute("SELECT id FROM bank_umsaetze WHERE betrag < 0").fetchone()[0]
    post(client, f"/bank/{aus}/ignorieren")
    assert con.execute("SELECT status FROM bank_umsaetze WHERE id=?", (aus,)).fetchone()[0] == "ignoriert"
    post(client, f"/bank/{aus}/ignorieren", oeffnen="1")
    assert con.execute("SELECT status FROM bank_umsaetze WHERE id=?", (aus,)).fetchone()[0] == "offen"
    # CAMT.053: Betrag passt nur zu d2, ohne Nummer → Vorschlag „Betrag und Name“
    camt = f"""<?xml version="1.0" encoding="UTF-8"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.02"><BkToCstmrStmt><Stmt>
<Ntry><Amt Ccy="EUR">49.90</Amt><CdtDbtInd>CRDT</CdtDbtInd><BookgDt><Dt>{date.today().isoformat()}</Dt></BookgDt>
<ValDt><Dt>{date.today().isoformat()}</Dt></ValDt><NtryDtls><TxDtls><RltdPties><Dbtr><Nm>Anna Müller</Nm></Dbtr>
<DbtrAcct><Id><IBAN>DE02120300000000202051</IBAN></Id></DbtrAcct></RltdPties><RmtInf><Ustrd>Reparatur Handy</Ustrd>
</RmtInf></TxDtls></NtryDtls></Ntry></Stmt></BkToCstmrStmt></Document>""".encode()
    with dbm.Transaktion(con):
        e = ba.importieren(con, "auszug.xml", camt)
    assert e["format"] == "CAMT.053" and e["neu"] == 1
    u2 = con.execute("SELECT * FROM bank_umsaetze WHERE betrag=4990").fetchone()
    v = ba.vorschlag(con, u2)
    assert v["p"]["d"]["id"] == d2["id"] and not v["sicher"] and "Name" in v["grund"]


@pytest.mark.parametrize("name, inhalt, erwartet", [
    ("n26.csv", '"Booking Date","Value Date","Partner Name","Partner Iban",Type,"Payment Reference","Account Name",'
                '"Amount (EUR)","Original Amount","Original Currency","Exchange Rate"\n'
                '2026-10-01,2026-10-01,"Max Muster",DE123,Credit Transfer,"RE-2026-0007",Hauptkonto,25.5,,,\n',
     ("2026-10-01", 2550, "Max Muster", "RE-2026-0007")),
    ("n26alt.csv", '"Datum","Empfänger","Kontonummer","Transaktionstyp","Verwendungszweck","Kategorie",'
                   '"Betrag (EUR)","Betrag (Fremdwährung)","Fremdwährung","Wechselkurs"\n'
                   '"2026-10-02","Bäckerei Schmid","DE55","Gutschrift","RE 2026 8","Einkommen","120.00","","",""\n',
     ("2026-10-02", 12000, "Bäckerei Schmid", "RE 2026 8")),
    ("volksbank.csv", 'Bezeichnung Auftragskonto;IBAN Auftragskonto;BIC Auftragskonto;Bankname Auftragskonto;'
                      'Buchungstag;Valutadatum;Name Zahlungsbeteiligter;IBAN Zahlungsbeteiligter;'
                      'BIC (SWIFT-Code) Zahlungsbeteiligter;Buchungstext;Verwendungszweck;Betrag;Waehrung;'
                      'Saldo nach Buchung;Bemerkung;Kategorie;Steuerrelevant;Glaeubiger ID;Mandatsreferenz\n'
                      'Konto;DE77;GENO;VR;03.10.2026;03.10.2026;Peter Klein;DE88;BIC;Gutschrift;RE-2026-0009;1.234,56;EUR;'
                      '9.999,00;;;;;\n',
     ("2026-10-03", 123456, "Peter Klein", "RE-2026-0009")),
    ("dkb.csv", '"Girokonto";"DE12345"\n"Zeitraum:";"01.10.2026 - 15.10.2026"\n\n'
                '"Buchungsdatum";"Wertstellung";"Status";"Zahlungspflichtige*r";"Zahlungsempfänger*in";'
                '"Verwendungszweck";"Umsatztyp";"IBAN";"Betrag (€)";"Gläubiger-ID";"Mandatsreferenz";"Kundenreferenz"\n'
                '"04.10.26";"04.10.26";"Gebucht";"Lisa Lang";"Reparatur Service Bredin";"Rechnung RE-2026-0010";'
                '"Eingang";"DE66";"89,00 €";"";"";""\n',
     ("2026-10-04", 8900, "Lisa Lang", "Rechnung RE-2026-0010")),
])
def test_csv_formate(name, inhalt, erwartet):
    fmt, umsaetze = ba.lesen(name, inhalt.encode("utf-8"))
    u = umsaetze[0]
    assert (u["buchungstag"], u["betrag"], u["name"], u["zweck"]) == erwartet


def test_csv_unbekannt_verstaendlich():
    with pytest.raises(ba.ImportFehler, match="nicht erkannt"):
        ba.lesen("x.csv", b"a;b;c\n1;2;3\n")


def test_nummer_im_verwendungszweck():
    m = ba._nummer_muster("RE-2026-0007")
    for text in ["RE-2026-0007", "re 2026 7", "Rechnung RE20260007 vielen Dank", "RE/2026/007"]:
        assert m.search(text), text
    for text in ["RE-2026-00071", "XRE-2026-0007", "RE-2026-0017"]:
        assert not m.search(text), text


def test_seiten_und_einstellungen(client, con):
    for url in ["/verkauf/offene-posten", "/verkauf/offene-posten?filter=ueberfaellig", "/verkauf/mahnwesen", "/bank", "/bank?ansicht=ignoriert",
                "/einstellungen/mahnwesen", "/"]:
        assert client.get(url).status_code == 200, url
    basis = dict(mahn_erinnerung_tage="7", mahn_stufe1_tage="7", mahn_stufe2_tage="7", mahn_frist_tage="10",
                 mahngebuehr_cent="2,50", mahngebuehr_2_cent="5,00", mahn_text_0="a", mahn_text_1="b", mahn_text_2="c",
                 mahn_email_betreff="x", mahn_email_text="y", basiszinssatz="", zinsen_aufschlag_privat="5",
                 zinsen_aufschlag_firma="9", zinsen_ab="mahnung1")
    post(client, "/einstellungen/mahnwesen", **{**basis, "zinsen_aktiv": "on"})
    assert not dbm.einstellungen(con)["zinsen_aktiv"]  # ohne Basiszinssatz abgelehnt
    post(client, "/einstellungen/mahnwesen", **{**basis, "zinsen_aktiv": "on", "basiszinssatz": "2,27"})
    e = dbm.einstellungen(con)
    assert e["zinsen_aktiv"] and e["basiszinssatz"] == "2.27" and e["mahngebuehr_cent"] == 250


def test_datenpruefung_mahnung(client, con, app):
    from pathlib import Path
    kid = kunde_anlegen(client)
    d = rechnung(client, con, kid, vor_tagen=30)
    mid = mw.erstellen(con, d["id"], 0, app.config["DATEN"])
    m = con.execute("SELECT * FROM mahnungen WHERE id=?", (mid,)).fetchone()
    assert "PDF der Mahnung" not in client.get("/pruefung").get_data(as_text=True)
    pfad = Path(app.config["DATEN"]) / m["pdf_pfad"]
    pfad.write_bytes(pfad.read_bytes() + b"x")
    assert "PDF der Mahnung wurde verändert" in client.get("/pruefung").get_data(as_text=True)
    assert client.get(f"/mahnungen/{mid}/pdf").status_code == 409
