"""Phase 8: E-Rechnung – ZUGFeRD/Factur-X erzeugen, XRechnung, Stammdatenprüfung, Empfang und lesbare Ansicht."""
import hashlib
import io
import json
import re
import smtplib
from pathlib import Path

import facturx

from rsb import db as dbm
from rsb import erechnung as er

from conftest import kunde_anlegen, post, rechnung_anlegen


def firma_anlegen(client, **extra):
    daten = dict(typ="firma", firma="Muster GmbH", anrede="", vorname="", nachname="", strasse="Weg 2", plz="74072",
                 ort="Heilbronn", email="buchhaltung@muster.de", ust_idnr="DE123456789")
    daten.update(extra)
    return kunde_anlegen(client, **daten)


def dok(con, did):
    return con.execute("SELECT * FROM dokumente WHERE id=?", (did,)).fetchone()


def test_zugferd_fuer_firmenkunden(client, con, app):
    kid = firma_anlegen(client)
    did = rechnung_anlegen(client, kid, positionen=(("Displaytausch", "149,00", "1"), ("Folie", "9,90", "2")),
                           festschreiben=True)
    d = dok(con, did)
    assert d["status"] == "festgeschrieben" and d["e_format"] == "zugferd" and d["xml_pfad"]
    pdf = (Path(app.config["DATEN"]) / d["pdf_pfad"]).read_bytes()
    assert hashlib.sha256(pdf).hexdigest() == d["pdf_sha256"]
    name, xml = facturx.get_xml_from_pdf(pdf, check_xsd=True)
    assert name == "factur-x.xml" and b"urn:cen.eu:en16931:2017" in xml
    assert er.pruefen(xml) == []
    bt = facturx.parse_ubl_cii_xml(xml)
    assert bt["BT-1"] == d["nummer"] and bt["BT-3"] == "380" and bt["BT-112"] == "168.80"
    assert bt["BG-23"][0]["BT-118"] == "E" and "§ 19" in bt["BG-23"][0]["BT-120"]  # Kleinunternehmer
    assert bt["BT-84"] == "DE02120300000000202051" and bt["BG-7"]["name"] == "Muster GmbH"
    assert (Path(app.config["DATEN"]) / d["xml_pfad"]).read_bytes() == xml
    assert b"/OutputIntents" in pdf and b"pdfaid:part>3<" in pdf.replace(b" ", b"")
    seite = client.get(f"/dokumente/{did}").get_data(as_text=True)
    assert "ZUGFeRD / Factur-X" in seite and "XML herunterladen" in seite
    assert client.get(f"/dokumente/{did}/xml").data == xml
    # Privatkunde: normales PDF
    pid = kunde_anlegen(client)
    p = dok(con, rechnung_anlegen(client, pid, festschreiben=True))
    assert p["e_format"] == "pdf" and not p["xml_pfad"]


def test_regelbesteuerung_mehrere_steuersaetze(client, con):
    with dbm.Transaktion(con):
        dbm.einstellungen_speichern({"steuer_modus": "regel", "ust_idnr": "DE999999999"}, con)
    kid = firma_anlegen(client)
    r = client.get(f"/dokumente/neu?kunde_id={kid}")
    did = int(re.search(r"/dokumente/(\d+)", r.headers["Location"]).group(1))
    client.post(f"/dokumente/{did}", data={
        "csrf": "test-token", "kunde_id": kid, "datum": "", "leistungsdatum": "2026-10-01", "leistungsdatum_bis": "",
        "zahlungsziel_tage": "", "betreff": "Reparatur", "einleitung": "", "schlusstext": "", "hinweise": "",
        "aktion": "festschreiben", "p_bezeichnung": ["Arbeit", "Buch"], "p_beschreibung": ["", ""], "p_menge": ["1,5", "1"],
        "p_einheit": ["Std.", "Stk."], "p_preis": ["60,00", "19,99"], "p_teilekosten": ["", ""],
        "p_steuersatz": ["19", "7"], "p_leistungsart": ["", ""], "p_artikel_id": ["", ""]})
    d = dok(con, did)
    assert d["status"] == "festgeschrieben", con.execute("SELECT * FROM protokoll ORDER BY id DESC").fetchone()
    snap = json.loads(d["snapshot_json"])
    xml = er.xml_erzeugen(snap, dbm.einstellungen(con), con.execute("SELECT * FROM kunden WHERE id=?", (kid,)).fetchone(),
                          "zugferd")
    assert er.pruefen(xml) == []
    bt = facturx.parse_ubl_cii_xml(xml)
    saetze = {g["BT-119"]: (g["BT-116"], g["BT-117"]) for g in bt["BG-23"]}
    assert saetze == {"7.00": ("19.99", "1.40"), "19.00": ("90.00", "17.10")}
    assert bt["BT-112"] == "128.49" and bt["BG-25"][0]["BT-130"] == "HUR"


def test_xrechnung_leitweg_pflicht_und_versand(client, con, app, monkeypatch):
    kid = firma_anlegen(client, e_rechnung="xrechnung")
    did = rechnung_anlegen(client, kid, festschreiben=True)
    d = dok(con, did)
    assert d["status"] == "entwurf"  # ohne Leitweg-ID nicht festgeschrieben
    r = client.get(f"/dokumente/{did}")
    assert "Leitweg-ID" in r.get_data(as_text=True)
    post(client, f"/kunden/{kid}", typ="firma", firma="Stadt Möckmühl", strasse="Hauptstr. 23", plz="74219",
         ort="Möckmühl", email="rechnung@moeckmuehl.de", e_rechnung="xrechnung", leitweg_id="08125067-0001-25",
         land="Deutschland")
    client.post(f"/dokumente/{did}", data={"csrf": "test-token", "kunde_id": kid, "datum": "", "leistungsdatum": "2026-10-02",
                                           "leistungsdatum_bis": "", "zahlungsziel_tage": "", "betreff": "Reparatur",
                                           "einleitung": "", "schlusstext": "", "hinweise": "", "aktion": "festschreiben",
                                           "p_bezeichnung": ["Akkutausch"], "p_beschreibung": [""], "p_menge": ["1"],
                                           "p_einheit": ["pauschal"], "p_preis": ["79,00"], "p_teilekosten": [""],
                                           "p_steuersatz": ["19"], "p_leistungsart": [""], "p_artikel_id": [""]})
    d = dok(con, did)
    assert d["status"] == "festgeschrieben" and d["e_format"] == "xrechnung"
    xml = (Path(app.config["DATEN"]) / d["xml_pfad"]).read_bytes()
    assert b"xrechnung_3.0" in xml and b"08125067-0001-25" in xml and er.pruefen(xml) == []
    pdf = (Path(app.config["DATEN"]) / d["pdf_pfad"]).read_bytes()
    assert b"factur-x.xml" not in pdf  # XRechnung: XML separat
    gesendet = []

    class Smtp:
        def __init__(self, *a, **k):
            pass
        starttls = login = quit = lambda self, *a, **k: None

        def send_message(self, msg):
            gesendet.append(msg)
    monkeypatch.setattr(smtplib, "SMTP", Smtp)
    from rsb.sicherheit import verschluesseln
    with app.app_context(), dbm.Transaktion(con):
        dbm.einstellungen_speichern({"smtp_host": "smtp.x", "smtp_benutzer": "a@b.de",
                                     "smtp_passwort_enc": verschluesseln("x")}, con)
    post(client, f"/dokumente/{did}/email", an="rechnung@moeckmuehl.de", betreff="Rechnung", text="Anbei")
    namen = [t.get_filename() for t in gesendet[0].iter_attachments()]
    assert namen == [f"{d['nummer']}.pdf", f"{d['nummer']}_xrechnung.xml"]


def test_stammdaten_pruefen_deutsch():
    einst = {"iban": "", "strasse": "", "plz": "", "ort": "", "steuernummer": ""}
    kunde = {"plz": "", "ort": "", "leitweg_id": "", "email": "", "ust_idnr": "DE12"}
    fehler = er.stammdaten_pruefen(einst, kunde, "xrechnung")
    text = " ".join(fehler)
    for wort in ("IBAN", "Anschrift", "Steuernummer", "PLZ", "Leitweg-ID", "E-Mail", "Telefon"):
        assert wort in text
    assert er.stammdaten_pruefen(einst, kunde, "pdf") == []
    kaputt = b'<?xml version="1.0"?><rsm:CrossIndustryInvoice xmlns:rsm="urn:un:unece:uncefact:data:standard:' \
             b'CrossIndustryInvoice:100"><rsm:Falsch/></rsm:CrossIndustryInvoice>'
    meldung = " ".join(er.pruefen(kaputt))
    assert meldung.startswith("Schema (XSD)") and "nicht erlaubt" in meldung


def test_gutschrift_als_381(client, con, app):
    kid = firma_anlegen(client)
    did = rechnung_anlegen(client, kid, festschreiben=True)
    post(client, f"/dokumente/{did}/stornieren", grund="Fehler")
    s = con.execute("SELECT * FROM dokumente WHERE typ='storno'").fetchone()
    assert s["e_format"] == "zugferd"
    _, xml = facturx.get_xml_from_pdf((Path(app.config["DATEN"]) / s["pdf_pfad"]).read_bytes())
    bt = facturx.parse_ubl_cii_xml(xml)
    assert bt["BT-3"] == "381" and bt["BT-112"] == "79.00" and bt["BG-3"][0]["BT-25"] == dok(con, did)["nummer"]


def test_e_rechnung_empfangen(client, con, app):
    # Eine echte XRechnung (aus dem eigenen Programm) als Lieferantenrechnung hochladen
    kid = firma_anlegen(client)
    did = rechnung_anlegen(client, kid, positionen=(("Ersatzteil", "50,00", "2"),), festschreiben=True)
    d = dok(con, did)
    pdf = (Path(app.config["DATEN"]) / d["pdf_pfad"]).read_bytes()
    post(client, "/lieferanten/neu", name="Reparatur Service Bredin", email="kontakt@reparatur-bredin.de")
    r = client.post("/eingangsrechnungen/neu", content_type="multipart/form-data", data={
        "csrf": "test-token", "datei": (io.BytesIO(pdf), "lieferant.pdf"), "datum": "", "brutto": "", "netto": ""})
    assert r.headers["Location"].endswith("/eingangsrechnungen/neu")
    seite = client.get("/eingangsrechnungen/neu").get_data(as_text=True)
    assert d["nummer"] in seite and 'value="100,00"' in seite and "E-Rechnung" in seite
    lid = con.execute("SELECT id FROM lieferanten").fetchone()[0]
    assert f'value="{lid}" selected' in seite  # über die E-Mail-Adresse zugeordnet
    r = post(client, "/eingangsrechnungen/neu", lieferant_id=str(lid), nummer=d["nummer"], datum=d["datum"],
             netto="100,00", steuer="0,00", brutto="100,00", steuersatz="0")
    eid = int(re.search(r"/eingangsrechnungen/(\d+)", r.headers["Location"]).group(1))
    e = con.execute("SELECT * FROM eingangsrechnungen WHERE id=?", (eid,)).fetchone()
    assert e["quelle"] == "Upload (E-Rechnung)" and json.loads(e["e_daten"])["BT-1"] == d["nummer"]
    ansicht = client.get(f"/eingangsrechnungen/{eid}/e-rechnung").get_data(as_text=True)
    assert "Ersatzteil" in ansicht and "DE02120300000000202051" in ansicht and "Muster GmbH" in ansicht
    assert client.get(f"/eingangsrechnungen/{eid}/e-rechnung?pdf=1").data.startswith(b"%PDF")
    # Reine XML (CII) wird ebenso erkannt; normales PDF nicht
    bt, _ = er.einlesen((Path(app.config["DATEN"]) / d["xml_pfad"]).read_bytes(), "x.xml")
    assert bt["BT-1"] == d["nummer"]
    assert er.einlesen(b"%PDF-1.4 kein xml", "a.pdf") == (None, None)
