"""E-Rechnung: ZUGFeRD/Factur-X (EN 16931, PDF/A-3 mit eingebetteter XML) und XRechnung (CII-XML).

Erzeugen: drafthorse baut die CII-XML aus den eingefrorenen Rechnungsdaten (Snapshot), factur-x prüft gegen XSD und
die EN-16931-Schematron-Regeln und bettet die XML ins PDF ein.
Empfangen: factur-x liest ZUGFeRD-PDFs, CII- und UBL-XML (XRechnung) und liefert die Business-Terms (BT-…).
"""
import io
import re
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from .hilfen import EingabeFehler, euro

FORMATE = {"auto": "automatisch (Firmen: ZUGFeRD, Privat: PDF)", "pdf": "PDF",
           "zugferd": "ZUGFeRD / Factur-X (PDF mit XML)", "xrechnung": "XRechnung (XML, z. B. für Behörden)"}
E_TYPEN = ("rechnung", "gutschrift", "storno")
PROFIL_EN16931 = "urn:cen.eu:en16931:2017"
PROFIL_XRECHNUNG = "urn:cen.eu:en16931:2017#compliant#urn:xeinkauf.de:kosit:xrechnung_3.0"
LAENDER = {"deutschland": "DE", "germany": "DE", "de": "DE", "österreich": "AT", "oesterreich": "AT", "austria": "AT",
           "schweiz": "CH", "switzerland": "CH", "frankreich": "FR", "france": "FR", "niederlande": "NL",
           "italien": "IT", "spanien": "ES", "polen": "PL", "belgien": "BE", "luxemburg": "LU", "dänemark": "DK",
           "tschechien": "CZ"}
EINHEITEN = {"stk": "C62", "stk.": "C62", "stück": "C62", "st": "C62", "pauschal": "LS", "psch": "LS", "std": "HUR",
             "std.": "HUR", "h": "HUR", "stunde": "HUR", "stunden": "HUR", "min": "MIN", "km": "KMT", "tag": "DAY",
             "tage": "DAY", "monat": "MON", "monate": "MON", "jahr": "ANN", "m": "MTR", "kg": "KGM", "l": "LTR"}


def _d(cent):
    return (Decimal(int(cent)) / 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def land(text):
    t = (text or "").strip().lower()
    if len(t) == 2 and t.isalpha():
        return t.upper()
    return LAENDER.get(t, "DE")


def einheit(text):
    return EINHEITEN.get((text or "").strip().lower(), "C62")


def format_fuer(kunde, typ="rechnung"):
    """Gewünschtes Format für ein Dokument dieses Kunden: pdf / zugferd / xrechnung."""
    if typ not in E_TYPEN or not kunde:
        return "pdf"
    wahl = (kunde["e_rechnung"] if "e_rechnung" in kunde.keys() else None) or "auto"
    if wahl == "auto":
        return "zugferd" if kunde["typ"] == "firma" else "pdf"
    return wahl


def stammdaten_pruefen(einst, kunde, fmt):
    """Fehlende Stammdaten für die E-Rechnung (deutsche Texte). Leere Liste = alles da."""
    if fmt == "pdf":
        return []
    fehler = []
    if not (einst.get("iban") or "").strip():
        fehler.append("E-Rechnung: Ihre IBAN fehlt (Einstellungen → Firmendaten).")
    if not all((einst.get(f) or "").strip() for f in ("strasse", "plz", "ort")):
        fehler.append("E-Rechnung: Ihre Anschrift ist unvollständig (Einstellungen → Firmendaten).")
    if not ((einst.get("steuernummer") or "").strip() or (einst.get("ust_idnr") or "").strip()):
        fehler.append("E-Rechnung: Steuernummer oder USt-IdNr. fehlt (Einstellungen → Firmendaten).")
    if not kunde:
        return fehler + ["E-Rechnung: Kein Kunde ausgewählt."]
    if not ((kunde["plz"] or "").strip() and (kunde["ort"] or "").strip()):
        fehler.append("E-Rechnung: Beim Kunden fehlen PLZ oder Ort.")
    if fmt == "xrechnung":
        if not (kunde["leitweg_id"] or "").strip():
            fehler.append("XRechnung: Beim Kunden fehlt die Leitweg-ID (Käuferreferenz).")
        if not (kunde["email"] or "").strip():
            fehler.append("XRechnung: Beim Kunden fehlt die E-Mail-Adresse (elektronische Adresse des Käufers).")
        for feld, text in (("email", "E-Mail"), ("telefon", "Telefon"), ("inhaber", "Inhaber/Ansprechpartner")):
            if not (einst.get(feld) or "").strip():
                fehler.append(f"XRechnung: Ihre {text} fehlt (Einstellungen → Firmendaten).")
    elif kunde["ust_idnr"] and not re.fullmatch(r"[A-Z]{2}[0-9A-Z+*.]{2,12}", (kunde["ust_idnr"] or "").replace(" ", "")):
        fehler.append("E-Rechnung: Die USt-IdNr. des Kunden hat kein gültiges Format (z. B. DE123456789).")
    return fehler


# ---------------------------------------------------------------------- Erzeugen

def xml_erzeugen(snap, einst, kunde, fmt):
    """CII-XML (EN 16931) aus den Rechnungsdaten. fmt: zugferd oder xrechnung."""
    from drafthorse.models.accounting import ApplicableTradeTax, BillingSpecifiedPeriod
    from drafthorse.models.document import Document
    from drafthorse.models.note import IncludedNote
    from drafthorse.models.party import TaxRegistration
    from drafthorse.models.payment import PaymentMeans, PaymentTerms
    from drafthorse.models.tradelines import LineItem

    gutschrift = snap["typ"] in ("gutschrift", "storno")
    vorzeichen = -1 if gutschrift else 1
    regel = snap["steuer_modus"] == "regel"
    doc = Document()
    doc.context.guideline_parameter.id = PROFIL_XRECHNUNG if fmt == "xrechnung" else PROFIL_EN16931
    doc.header.id = snap["nummer"]
    doc.header.type_code = "381" if gutschrift else "380"
    doc.header.issue_date_time = date.fromisoformat(snap["datum"])
    hinweise = [snap.get("kleinunternehmer_hinweis") or "", snap.get("hinweise") or ""]
    for h in hinweise:
        if h.strip():
            doc.header.notes.add(IncludedNote(content=h.strip()))

    f = snap["firma"]
    s = doc.trade.agreement.seller
    s.name = f.get("firma_name") or f.get("inhaber") or ""
    s.address.line_one = f.get("strasse") or ""
    s.address.postcode = f.get("plz") or ""
    s.address.city_name = f.get("ort") or ""
    s.address.country_id = land(f.get("land"))
    if f.get("email"):
        s.electronic_address.uri_ID = ("EM", f["email"])
    if f.get("ust_idnr"):
        s.tax_registrations.add(TaxRegistration(id=("VA", f["ust_idnr"].replace(" ", ""))))
    if f.get("steuernummer"):
        s.tax_registrations.add(TaxRegistration(id=("FC", f["steuernummer"])))
    if fmt == "xrechnung" or f.get("telefon"):
        s.contact.person_name = f.get("inhaber") or s.name
        if f.get("telefon"):
            s.contact.telephone.number = f["telefon"]
        if f.get("email"):
            s.contact.email.address = f["email"]

    b = doc.trade.agreement.buyer
    k = snap["kunde"]
    b.name = k["name"]
    b.address.line_one = kunde["strasse"] or "" if kunde else ""
    b.address.postcode = kunde["plz"] or "" if kunde else ""
    b.address.city_name = kunde["ort"] or "" if kunde else ""
    b.address.country_id = land(kunde["land"] if kunde else "")
    if kunde and kunde["email"]:
        b.electronic_address.uri_ID = ("EM", kunde["email"])
    if k.get("ust_idnr"):
        b.tax_registrations.add(TaxRegistration(id=("VA", k["ust_idnr"].replace(" ", ""))))
    leitweg = (kunde["leitweg_id"] or "").strip() if kunde and "leitweg_id" in kunde.keys() else ""
    if leitweg:
        doc.trade.agreement.buyer_reference = leitweg
    elif fmt == "xrechnung":
        doc.trade.agreement.buyer_reference = k.get("kundennr") or "-"

    if snap.get("leistungsdatum_bis") and snap.get("leistungsdatum"):
        p = BillingSpecifiedPeriod()
        p.start = date.fromisoformat(snap["leistungsdatum"])
        p.end = date.fromisoformat(snap["leistungsdatum_bis"])
        doc.trade.settlement.period = p
    elif snap.get("leistungsdatum"):
        doc.trade.delivery.event.occurrence = date.fromisoformat(snap["leistungsdatum"])
    if snap.get("bezug"):
        doc.trade.settlement.invoice_referenced_document.issuer_assigned_id = snap["bezug"]["nummer"]
        doc.trade.settlement.invoice_referenced_document.issue_date_time = date.fromisoformat(snap["bezug"]["datum"])

    st = doc.trade.settlement
    st.currency_code = "EUR"
    st.payment_reference = snap["nummer"]
    if f.get("iban"):
        pm = PaymentMeans()
        pm.type_code = "58"
        pm.payee_account.iban = f["iban"].replace(" ", "")
        pm.payee_account.account_name = f.get("kontoinhaber") or f.get("inhaber") or s.name
        if f.get("bic"):
            pm.payee_institution.bic = f["bic"]
        st.payment_means.add(pm)
    t = PaymentTerms()
    if gutschrift:
        t.description = "Der Betrag wird erstattet bzw. verrechnet."
    else:
        t.description = (snap.get("zahlungsarten_text") or "").strip()[:500] or "Zahlbar ohne Abzug."
        if snap.get("faellig_am"):
            t.due = date.fromisoformat(snap["faellig_am"])
    st.terms.add(t)

    # Positionen
    kategorien = {}
    for p in snap["positionen"]:
        li = LineItem()
        li.document.line_id = str(p["pos"])
        li.product.name = p["bezeichnung"]
        if (p.get("beschreibung") or "").strip():
            li.product.description = p["beschreibung"].strip()
        li.agreement.net.amount = _d(abs(p["einzelpreis"]))
        li.delivery.billed_quantity = (Decimal(str(p["menge"])).quantize(Decimal("0.0001")), einheit(p.get("einheit")))
        satz = float(p["steuersatz"] or 0) if regel else 0.0
        kat = "S" if regel and satz > 0 else ("Z" if regel else "E")
        li.settlement.trade_tax.type_code = "VAT"
        li.settlement.trade_tax.category_code = kat
        li.settlement.trade_tax.rate_applicable_percent = Decimal(str(satz)).quantize(Decimal("0.01"))
        betrag = vorzeichen * p["betrag"]
        li.settlement.monetary_summation.total_amount = _d(betrag)
        doc.trade.items.add(li)
        kategorien.setdefault((kat, satz), 0)
        kategorien[(kat, satz)] += betrag

    summen = snap["summen"]
    steuer_summe = 0
    for (kat, satz), basis in sorted(kategorien.items()):
        tt = ApplicableTradeTax()
        steuer = int(round(basis * satz / 100)) if kat == "S" else 0
        steuer_summe += steuer
        tt.calculated_amount = _d(steuer)
        tt.basis_amount = _d(basis)
        tt.type_code = "VAT"
        tt.category_code = kat
        if kat == "E":
            tt.exemption_reason = "Umsatzsteuerbefreit – Kleinunternehmer gemäß § 19 UStG"
        tt.rate_applicable_percent = Decimal(str(satz)).quantize(Decimal("0.01"))
        st.trade_tax.add(tt)
    netto = vorzeichen * summen["netto"]
    if steuer_summe != vorzeichen * summen["steuer"]:  # sollte nie passieren – dann lieber gar keine E-Rechnung
        raise EingabeFehler("E-Rechnung: Die Steuerbeträge je Steuersatz stimmen nicht mit der Rechnung überein.")
    ms = st.monetary_summation
    ms.line_total = _d(netto)
    ms.charge_total = _d(0)
    ms.allowance_total = _d(0)
    ms.tax_basis_total = (_d(netto), "EUR")
    ms.tax_total = (_d(steuer_summe), "EUR")
    ms.grand_total = (_d(netto + steuer_summe), "EUR")
    ms.due_amount = _d(netto + steuer_summe)
    try:
        return doc.serialize(schema="FACTUR-X_EN16931")
    except Exception as e:
        raise EingabeFehler("E-Rechnung konnte nicht erzeugt werden (Schemafehler): " + _deutsch(str(e)))


REGELN_DE = {
    "BR-CO-10": "Die Summe der Positionsbeträge stimmt nicht mit der Rechnungssumme überein.",
    "BR-CO-15": "Gesamtbetrag ≠ Nettobetrag + Umsatzsteuer.",
    "BR-CO-25": "Bei offenem Betrag muss ein Fälligkeitsdatum oder eine Zahlungsbedingung angegeben sein.",
    "BR-06": "Der Name des Verkäufers fehlt.",
    "BR-07": "Der Name des Käufers fehlt.",
    "BR-08": "Die Anschrift des Verkäufers fehlt.",
    "BR-09": "Das Land des Verkäufers fehlt.",
    "BR-10": "Die Anschrift des Käufers fehlt.",
    "BR-11": "Das Land des Käufers fehlt.",
    "BR-16": "Die Rechnung hat keine Positionen.",
    "BR-50": "Die IBAN fehlt.",
    "BR-E-02": "Bei steuerbefreiten Positionen (Kleinunternehmer) fehlt die Steuernummer oder USt-IdNr. des Verkäufers.",
    "BR-S-02": "Bei steuerpflichtigen Positionen fehlt die USt-IdNr. bzw. Steuernummer des Verkäufers.",
    "BR-DE-1": "XRechnung: Zahlungsanweisungen fehlen.",
    "BR-DE-2": "XRechnung: Kontaktangaben des Verkäufers (Name, Telefon, E-Mail) fehlen.",
    "BR-DE-15": "XRechnung: Die Leitweg-ID/Käuferreferenz fehlt.",
}


def _deutsch(text):
    regeln = sorted(set(re.findall(r"\b(BR-[A-Z0-9]+(?:-[0-9]+)?)\b", text)))
    if regeln:
        return " ".join(REGELN_DE.get(r, f"Regel {r} ist verletzt.") for r in regeln)
    text = text.replace("This element is not expected", "Dieses Element ist hier nicht erlaubt").replace(
        "Expected is", "erwartet wird").replace("is not a valid value", "ist kein gültiger Wert").replace(
        "Missing child element(s)", "Es fehlen Unterelemente")
    return text[:400]


def _summenregeln(bt):
    """Wichtigste Rechenregeln der EN 16931 (die vollständige Schematron-Prüfung braucht einen externen Validator)."""
    fehler = []

    def c(wert):
        return _cent(wert) or 0
    zeilen = bt.get("BG-25") or []
    if not zeilen:
        fehler.append("BR-16")
    if sum(c(z.get("BT-131")) for z in zeilen) != c(bt.get("BT-106")):
        fehler.append("BR-CO-10")
    if c(bt.get("BT-109")) + c(bt.get("BT-110")) != c(bt.get("BT-112")):
        fehler.append("BR-CO-15")
    if sum(c(g.get("BT-117")) for g in bt.get("BG-23") or []) != c(bt.get("BT-110")):
        fehler.append("BR-CO-14")
    for nr, feld in (("BR-06", (bt.get("BG-4") or {}).get("name")), ("BR-07", (bt.get("BG-7") or {}).get("name")),
                     ("BR-09", (bt.get("BG-4") or {}).get("country_code")),
                     ("BR-11", (bt.get("BG-7") or {}).get("country_code"))):
        if not feld:
            fehler.append(nr)
    if bt.get("BT-81") == "58" and not bt.get("BT-84"):
        fehler.append("BR-50")
    if c(bt.get("BT-115")) > 0 and not (bt.get("BT-9") or bt.get("BT-20")):
        fehler.append("BR-CO-25")
    if "xrechnung" in str(bt.get("BT-24") or "") and not bt.get("BT-10"):
        fehler.append("BR-DE-15")
    return fehler


REGELN_DE["BR-CO-14"] = "Die Summe der Steuerbeträge je Steuersatz stimmt nicht mit der Gesamtsteuer überein."


def pruefen(xml):
    """XSD-Prüfung (EN 16931) und die zentralen Rechenregeln. Gibt deutsche Fehlermeldungen zurück (leer = gültig).

    Hinweis: factur-x würde die Schematron-Regeln nur über einen externen Saxon-Server prüfen – das wird bewusst
    nicht genutzt (keine Daten nach außen). Für eine vollständige Prüfung: KoSIT-Validator bzw. ein Online-Prüfdienst.
    """
    import facturx
    try:
        facturx.xml_check_xsd(xml, flavor="factur-x", level="en16931")
    except Exception as e:
        return ["Schema (XSD): " + _deutsch(str(e))]
    try:
        bt = facturx.parse_ubl_cii_xml(xml, check_xsd=False)
    except Exception as e:
        return ["Die E-Rechnung konnte nicht gelesen werden: " + _deutsch(str(e))]
    regeln = _summenregeln(bt)
    return [_deutsch(" ".join(regeln))] if regeln else []


def _output_intent(pdf):
    """sRGB-OutputIntent ergänzen (Voraussetzung für PDF/A)."""
    from PIL import ImageCms
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import ArrayObject, DictionaryObject, NameObject, NumberObject, StreamObject, TextStringObject
    w = PdfWriter(clone_from=PdfReader(io.BytesIO(pdf)))
    icc = StreamObject()
    icc.set_data(ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes())
    icc[NameObject("/N")] = NumberObject(3)
    intent = DictionaryObject({NameObject("/Type"): NameObject("/OutputIntent"), NameObject("/S"): NameObject("/GTS_PDFA1"),
                               NameObject("/OutputConditionIdentifier"): TextStringObject("sRGB"),
                               NameObject("/Info"): TextStringObject("sRGB IEC61966-2.1"),
                               NameObject("/DestOutputProfile"): w._add_object(icc)})
    w._root_object[NameObject("/OutputIntents")] = ArrayObject([w._add_object(intent)])
    puffer = io.BytesIO()
    w.write(puffer)
    return puffer.getvalue()


def einbetten(pdf, xml, snap):
    """ZUGFeRD/Factur-X: XML als factur-x.xml ins PDF einbetten (PDF/A-3, Profil EN 16931)."""
    import facturx
    try:
        basis = _output_intent(pdf)
        return facturx.generate_from_binary(
            basis, xml, flavor="factur-x", level="en16931", check_xsd=True, check_schematron=False, lang="de-DE",
            xmp_compression=False,
            pdf_metadata={"author": snap["firma"].get("firma_name") or "", "keywords": "Factur-X, ZUGFeRD, Rechnung",
                          "title": f"{snap['titel']} {snap['nummer']}", "subject": snap.get("betreff") or ""})
    except Exception as e:
        raise EingabeFehler("ZUGFeRD-PDF konnte nicht erzeugt werden: " + _deutsch(str(e)))


def erzeugen(snap, einst, kunde, fmt, pdf):
    """Gibt (pdf, xml) zurück: bei ZUGFeRD das PDF mit eingebetteter XML, bei XRechnung die separate XML."""
    if fmt not in ("zugferd", "xrechnung"):
        return pdf, None
    xml = xml_erzeugen(snap, einst, kunde, fmt)
    fehler = pruefen(xml)
    if fehler:
        raise EingabeFehler("Die E-Rechnung ist nicht gültig und wurde nicht festgeschrieben: " + " ".join(fehler))
    if fmt == "zugferd":
        return einbetten(pdf, xml, snap), xml
    return pdf, xml


# ---------------------------------------------------------------------- Empfangen

def einlesen(daten, dateiname=""):
    """ZUGFeRD-PDF oder XML (CII/UBL, z. B. XRechnung) lesen. Gibt (bt_dict, xml) oder (None, None) zurück."""
    import facturx
    name = (dateiname or "").lower()
    xml = None
    try:
        if daten[:5] == b"%PDF-" or name.endswith(".pdf"):
            try:
                _, xml = facturx.get_xml_from_pdf(daten, check_xsd=False)
            except Exception:
                return None, None
            if not xml:
                return None, None
        else:
            xml = daten
        return facturx.parse_ubl_cii_xml(xml, check_xsd=False), xml
    except Exception:
        return None, None


def _cent(wert):
    if wert in (None, ""):
        return None
    return int((Decimal(str(wert)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def eingangswerte(bt):
    """Business-Terms → Felder für das Eingangsrechnungs-Formular."""
    verkaeufer = bt.get("BG-4") or {}
    steuer = bt.get("BG-23") or []
    saetze = {float(x.get("BT-119") or 0) for x in steuer}
    netto, ust, brutto = _cent(bt.get("BT-109")), _cent(bt.get("BT-110")), _cent(bt.get("BT-112"))
    gutschrift = str(bt.get("BT-3") or "") in ("381", "261", "262", "296", "308", "396", "420", "458", "532")
    if gutschrift:
        netto, ust, brutto = [(-x if x else x) for x in (netto, ust, brutto)]
    return {"lieferant_name": verkaeufer.get("name") or "", "nummer": bt.get("BT-1") or "",
            "datum": str(bt.get("BT-2") or "")[:10], "faellig_am": str(bt.get("BT-9") or "")[:10],
            "netto": netto, "steuer": ust, "brutto": brutto,
            "steuersatz": saetze.pop() if len(saetze) == 1 else None,
            "beschreibung": ("Gutschrift – " if gutschrift else "") + ", ".join(
                (z.get("BT-153") or "") for z in (bt.get("BG-25") or [])[:3]),
            "iban": bt.get("BT-84") or "", "ust_idnr": verkaeufer.get("vat_id") or "",
            "email": verkaeufer.get("einvoicing_addr") or ""}


def lesbar(bt):
    """Aufbereitete Darstellung einer E-Rechnung (für Ansicht und PDF)."""
    v, k = bt.get("BG-4") or {}, bt.get("BG-7") or {}

    def partei(p):
        return [x for x in [p.get("name"), p.get("addr_l1"), p.get("addr_l2"),
                            " ".join(y for y in [p.get("postcode"), p.get("city")] if y), p.get("country_code"),
                            ("USt-IdNr. " + p["vat_id"]) if p.get("vat_id") else "",
                            ("Steuernr. " + p["tax_identifier"]) if p.get("tax_identifier") else "",
                            p.get("einvoicing_addr")] if x]
    positionen = [{"nr": z.get("BT-126"), "bezeichnung": z.get("BT-153") or "", "beschreibung": z.get("BT-154") or "",
                   "menge": z.get("BT-129"), "einheit": z.get("BT-130"), "preis": _cent(z.get("BT-146")),
                   "betrag": _cent(z.get("BT-131")), "satz": z.get("BT-152"), "kategorie": z.get("BT-151")}
                  for z in bt.get("BG-25") or []]
    steuern = [{"basis": _cent(s.get("BT-116")), "steuer": _cent(s.get("BT-117")), "kategorie": s.get("BT-118"),
                "satz": s.get("BT-119"), "grund": s.get("BT-120") or ""} for s in bt.get("BG-23") or []]
    return {"nummer": bt.get("BT-1"), "datum": str(bt.get("BT-2") or "")[:10], "art": bt.get("BT-3"),
            "waehrung": bt.get("BT-5") or "EUR", "faellig": str(bt.get("BT-9") or "")[:10],
            "leitweg": bt.get("BT-10"), "profil": bt.get("BT-24"), "leistungsdatum": str(bt.get("BT-72") or "")[:10],
            "verkaeufer": partei(v), "kaeufer": partei(k), "positionen": positionen, "steuern": steuern,
            "netto": _cent(bt.get("BT-109")), "steuer": _cent(bt.get("BT-110")), "brutto": _cent(bt.get("BT-112")),
            "zahlbetrag": _cent(bt.get("BT-115")), "iban": bt.get("BT-84"), "bic": bt.get("BT-86"),
            "zahlungsbedingungen": bt.get("BT-20"), "verwendungszweck": bt.get("BT-83"),
            "hinweise": [n.get("BT-22") for n in bt.get("BG-1") or [] if n.get("BT-22")]}


def ansicht_pdf(r, titel="E-Rechnung (Sichtprüfung)"):
    """Lesbare PDF-Darstellung einer empfangenen E-Rechnung."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    from xml.sax.saxutils import escape

    from .pdf import _schrift_registrieren
    f_norm, f_fett, _ = _schrift_registrieren("Montserrat")
    st = ParagraphStyle("n", fontName=f_norm, fontSize=9, leading=12)
    st_f = ParagraphStyle("f", parent=st, fontName=f_fett)
    st_t = ParagraphStyle("t", fontName=f_fett, fontSize=14, leading=18)

    def p(t, s=st):
        return Paragraph(escape(str(t if t is not None else "")).replace("\n", "<br/>"), s)
    puffer = io.BytesIO()
    doc = SimpleDocTemplate(puffer, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm,
                            bottomMargin=16 * mm, title=f"{titel} {r['nummer'] or ''}")
    inhalt = [p(f"{titel}: {r['nummer'] or ''}", st_t),
              p(f"Datum {r['datum']} · Art {r['art']} · Währung {r['waehrung']}"
                + (f" · fällig {r['faellig']}" if r["faellig"] else "") + (f" · Leitweg-ID {r['leitweg']}"
                                                                            if r["leitweg"] else "")),
              Spacer(1, 4 * mm)]
    t = Table([[p("Verkäufer", st_f), p("Käufer", st_f)], [p("\n".join(r["verkaeufer"])), p("\n".join(r["kaeufer"]))]],
              colWidths=[87 * mm, 87 * mm])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    inhalt += [t, Spacer(1, 4 * mm)]
    zeilen = [[p(x, st_f) for x in ["Nr.", "Bezeichnung", "Menge", "Preis", "USt", "Betrag"]]]
    for z in r["positionen"]:
        zeilen.append([p(z["nr"]), p(z["bezeichnung"] + (("\n" + z["beschreibung"]) if z["beschreibung"] else "")),
                       p(f"{z['menge']} {z['einheit'] or ''}"), p(euro(z["preis"]) if z["preis"] is not None else ""),
                       p(f"{z['kategorie']} {z['satz']} %"), p(euro(z["betrag"]) if z["betrag"] is not None else "")])
    t = Table(zeilen, colWidths=[10 * mm, 80 * mm, 22 * mm, 22 * mm, 18 * mm, 22 * mm], repeatRows=1)
    t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.3, colors.HexColor("#D5D9DE")),
                           ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    inhalt += [t, Spacer(1, 4 * mm)]
    for s in r["steuern"]:
        inhalt.append(p(f"USt {s['kategorie']} {s['satz']} %: Basis {euro(s['basis'] or 0)}, Steuer {euro(s['steuer'] or 0)}"
                        + (f" – {s['grund']}" if s["grund"] else "")))
    inhalt += [p(f"Netto {euro(r['netto'] or 0)} · USt {euro(r['steuer'] or 0)} · Brutto {euro(r['brutto'] or 0)} · "
                 f"zu zahlen {euro(r['zahlbetrag'] or 0)}", st_f)]
    if r["iban"]:
        inhalt.append(p(f"Zahlung an IBAN {r['iban']}" + (f", BIC {r['bic']}" if r["bic"] else "")
                        + (f", Verwendungszweck {r['verwendungszweck']}" if r["verwendungszweck"] else "")))
    if r["zahlungsbedingungen"]:
        inhalt.append(p(f"Zahlungsbedingungen: {r['zahlungsbedingungen']}"))
    for h in r["hinweise"]:
        inhalt.append(p(h))
    inhalt += [Spacer(1, 4 * mm), p("Diese Darstellung wurde aus der elektronischen Rechnung (XML) erzeugt. Maßgeblich "
                                    "ist die archivierte Originaldatei.", ParagraphStyle("k", parent=st, fontSize=7.5))]
    doc.build(inhalt)
    return puffer.getvalue()
