"""PDF-Erzeugung (A4, DIN 5008 Form B) mit ReportLab.

Das Layout wird vollständig aus den Einstellungen gesteuert (Farben, Schrift, Logo, Kopf-/Fußzeile).
"""
import io
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import (BaseDocTemplate, Frame, KeepTogether, PageTemplate, Paragraph, Spacer, Table,
                                TableStyle)

from .hilfen import datum_de, euro, iban_format, menge_text

STATIC = Path(__file__).parent / "static"
FONTS = STATIC / "fonts"
STANDARD_LOGO = STATIC / "bilder" / "logo_standard.png"

SCHRIFTEN = {
    # Anzeigename: (normal, fett, kursiv)
    "Montserrat": ("Montserrat-Regular.ttf", "Montserrat-SemiBold.ttf", "Montserrat-Italic.ttf"),
    "Open Sans": ("OpenSans-Regular.ttf", "OpenSans-Bold.ttf", "OpenSans-Italic.ttf"),
    "Lato": ("Lato-Regular.ttf", "Lato-Bold.ttf", "Lato-Italic.ttf"),
    "Helvetica": None,
    "Times": None,
}

SEITE_B, SEITE_H = A4
RAND_L = 22 * mm
RAND_R = 18 * mm
INHALT_B = SEITE_B - RAND_L - RAND_R


def _schrift_registrieren(name):
    """Gibt (normal, fett, kursiv) Schriftnamen für ReportLab zurück."""
    if name == "Helvetica" or name not in SCHRIFTEN:
        return "Helvetica", "Helvetica-Bold", "Helvetica-Oblique"
    if name == "Times":
        return "Times-Roman", "Times-Bold", "Times-Italic"
    namen = []
    for stil, datei in zip(("", "-Fett", "-Kursiv"), SCHRIFTEN[name]):
        fname = name.replace(" ", "") + stil
        if fname not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(fname, str(FONTS / datei)))
        namen.append(fname)
    pdfmetrics.registerFontFamily(namen[0], normal=namen[0], bold=namen[1], italic=namen[2], boldItalic=namen[1])
    return tuple(namen)


def _farbe(hexwert, ersatz="#1C54A3"):
    try:
        return colors.HexColor(hexwert or ersatz)
    except (ValueError, TypeError):
        return colors.HexColor(ersatz)


def _absatz(text):
    return escape(text or "").replace("\n", "<br/>")


def girocode_daten(name, iban, bic, betrag_cent, verwendungszweck):
    """EPC-QR-Code (GiroCode) nach EPC069-12, Version 002, UTF-8."""
    betrag = f"EUR{betrag_cent // 100}.{betrag_cent % 100:02d}"
    zeilen = ["BCD", "002", "1", "SCT", (bic or "").replace(" ", ""), (name or "")[:70],
              (iban or "").replace(" ", "").upper(), betrag, "", "", (verwendungszweck or "")[:140]]
    return "\n".join(zeilen)


class _SeitenCanvas(rl_canvas.Canvas):
    """Canvas, der am Ende 'Seite x von y' schreibt."""

    def __init__(self, *args, fusszeile=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._seiten = []
        self._fusszeile = fusszeile

    def showPage(self):
        self._seiten.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        gesamt = len(self._seiten)
        for zustand in self._seiten:
            self.__dict__.update(zustand)
            if self._fusszeile:
                self._fusszeile(self, self._pageNumber, gesamt)
            super().showPage()
        super().save()


def pdf_erzeugen(snap, daten_dir=None, entwurf=False):
    """Erzeugt das PDF aus einem Snapshot (siehe logik.snapshot_bauen) und gibt die Bytes zurück."""
    lay = snap["layout"]
    firma = snap["firma"]
    f_norm, f_fett, f_kursiv = _schrift_registrieren(lay.get("schrift") or "Montserrat")
    groesse = float(lay.get("schriftgroesse") or 9.5)
    primaer = _farbe(lay.get("farbe_primaer"))
    sekundaer = _farbe(lay.get("farbe_sekundaer"), "#5D6670")

    logo_pfad = STANDARD_LOGO
    if lay.get("logo_datei") and daten_dir:
        eigen = Path(daten_dir) / lay["logo_datei"]
        if eigen.is_file():
            logo_pfad = eigen

    st = {
        "normal": ParagraphStyle("n", fontName=f_norm, fontSize=groesse, leading=groesse * 1.4),
        "klein": ParagraphStyle("k", fontName=f_norm, fontSize=groesse - 1.5, leading=(groesse - 1.5) * 1.35,
                                textColor=sekundaer),
        "titel": ParagraphStyle("t", fontName=f_fett, fontSize=groesse + 7, leading=groesse + 11, textColor=primaer),
        "betreff": ParagraphStyle("b", fontName=f_fett, fontSize=groesse + 0.5, leading=groesse * 1.5),
        "kopf": ParagraphStyle("h", fontName=f_fett, fontSize=groesse - 0.5, leading=groesse * 1.25,
                               textColor=colors.white),
        "kopf_r": ParagraphStyle("hr", fontName=f_fett, fontSize=groesse - 0.5, leading=groesse * 1.25,
                                 textColor=colors.white, alignment=TA_RIGHT),
        "zelle": ParagraphStyle("z", fontName=f_norm, fontSize=groesse - 0.5, leading=(groesse - 0.5) * 1.35),
        "zelle_r": ParagraphStyle("zr", fontName=f_norm, fontSize=groesse - 0.5, leading=(groesse - 0.5) * 1.35,
                                  alignment=TA_RIGHT),
        "beschreibung": ParagraphStyle("pb", fontName=f_norm, fontSize=groesse - 1.5, leading=(groesse - 1.5) * 1.35,
                                       textColor=sekundaer),
        "zelle_fett": ParagraphStyle("zf", fontName=f_fett, fontSize=groesse - 0.5, leading=(groesse - 0.5) * 1.35),
        "summe": ParagraphStyle("s", fontName=f_norm, fontSize=groesse, leading=groesse * 1.4, alignment=TA_RIGHT),
        "summe_fett": ParagraphStyle("sf", fontName=f_fett, fontSize=groesse + 1.5, leading=groesse * 1.7,
                                     alignment=TA_RIGHT, textColor=primaer),
        "hinweis": ParagraphStyle("hi", fontName=f_kursiv, fontSize=groesse - 0.5, leading=(groesse - 0.5) * 1.4),
    }

    # ---------------------------------------------------------- feste Seitenelemente
    logo_b = float(lay.get("logo_breite_mm") or 62) * mm
    try:
        logo_img = ImageReader(str(logo_pfad))
        iw, ih = logo_img.getSize()
        logo_h = logo_b * ih / iw
    except Exception:
        logo_img, logo_h = None, 0

    def logo_zeichnen(c, breite, oben):
        if not logo_img:
            return 0
        h = breite * logo_h / logo_b
        pos = lay.get("logo_position") or "rechts"
        x = {"links": RAND_L, "mitte": (SEITE_B - breite) / 2}.get(pos, SEITE_B - RAND_R - breite)
        c.drawImage(logo_img, x, SEITE_H - oben - h, width=breite, height=h, mask="auto")
        return h

    def erste_seite(c, _doc):
        c.saveState()
        logo_zeichnen(c, logo_b, 10 * mm)
        if lay.get("kopfzeile_text"):
            c.setFont(f_norm, groesse - 2)
            c.setFillColor(sekundaer)
            c.drawRightString(SEITE_B - RAND_R, SEITE_H - 10 * mm - logo_h - 4 * mm, lay["kopfzeile_text"])
        # Rücksendeangabe (Absenderzeile über dem Anschriftfeld)
        absender = " · ".join(x for x in [firma.get("firma_name"), firma.get("strasse"),
                                          " ".join(y for y in [firma.get("plz"), firma.get("ort")] if y)] if x)
        c.setFont(f_norm, 6.5)
        c.setFillColor(sekundaer)
        c.drawString(RAND_L, SEITE_H - 59 * mm, absender)
        c.setStrokeColor(sekundaer)
        c.setLineWidth(0.3)
        c.line(RAND_L, SEITE_H - 60 * mm, RAND_L + 85 * mm, SEITE_H - 60 * mm)
        # Anschrift des Kunden
        c.setFillColor(colors.black)
        c.setFont(f_norm, groesse + 0.5)
        y = SEITE_H - 66 * mm
        for zeile in snap["kunde"]["anschrift"][:6]:
            c.drawString(RAND_L, y, zeile)
            y -= (groesse + 3.5)
        # Informationsblock rechts
        info = _infoblock(snap)
        x_l, x_r = 128 * mm, SEITE_B - RAND_R
        y = SEITE_H - 54 * mm
        for i, (label, wert) in enumerate(info):
            c.setFont(f_norm, groesse - 1)
            c.setFillColor(sekundaer)
            c.drawString(x_l, y, label)
            c.setFont(f_fett if i == 0 else f_norm, groesse - 0.5)
            c.setFillColor(colors.black)
            c.drawRightString(x_r, y, wert)
            y -= (groesse + 4.5)
        _faltmarken(c)
        _wasserzeichen(c)
        c.restoreState()

    def folgeseite(c, _doc):
        c.saveState()
        h = logo_zeichnen(c, logo_b * 0.55, 8 * mm)
        c.setFont(f_norm, groesse - 1)
        c.setFillColor(sekundaer)
        c.drawString(RAND_L, SEITE_H - 8 * mm - h + 2 * mm,
                     f"{snap['titel']} {snap.get('nummer') or '(Entwurf)'} vom {datum_de(snap['datum'])}")
        _faltmarken(c)
        _wasserzeichen(c)
        c.restoreState()

    def _faltmarken(c):
        if not lay.get("faltmarken"):
            return
        c.setStrokeColor(colors.HexColor("#999999"))
        c.setLineWidth(0.3)
        for y_mm, laenge in ((105, 5), (148.5, 7), (210, 5)):
            c.line(4 * mm, SEITE_H - y_mm * mm, (4 + laenge) * mm, SEITE_H - y_mm * mm)

    def _wasserzeichen(c):
        if not entwurf:
            return
        c.saveState()
        c.setFont(f_fett, 80)
        c.setFillColor(colors.Color(0.85, 0.1, 0.1, alpha=0.12))
        c.translate(SEITE_B / 2, SEITE_H / 2)
        c.rotate(45)
        c.drawCentredString(0, 0, "ENTWURF")
        c.restoreState()

    def fusszeile(c, seite, gesamt):
        c.saveState()
        y0 = 24 * mm
        c.setStrokeColor(primaer)
        c.setLineWidth(0.8)
        c.line(RAND_L, y0, SEITE_B - RAND_R, y0)
        spalten = _fussspalten(firma)
        # Spaltenbreiten nach Textlänge, Abstand gleichmäßig verteilen; notfalls Schrift verkleinern
        fg = 6.8
        while True:
            breiten = [max(pdfmetrics.stringWidth(z, f_fett if j == 0 else f_norm, fg) for j, z in enumerate(sp))
                       for sp in spalten]
            luecke = (INHALT_B - sum(breiten)) / max(len(spalten) - 1, 1)
            if luecke >= 3 * mm or fg <= 5:
                break
            fg -= 0.3
        x = RAND_L
        for zeilen, b in zip(spalten, breiten):
            y = y0 - 4 * mm
            for j, z in enumerate(zeilen):
                c.setFont(f_fett if j == 0 else f_norm, fg)
                c.setFillColor(colors.black if j == 0 else sekundaer)
                c.drawString(x, y, z)
                y -= fg * 1.25
            x += b + luecke
        if lay.get("fusszeile_text"):
            c.setFont(f_norm, 6.5)
            c.setFillColor(sekundaer)
            c.drawCentredString(SEITE_B / 2, 6 * mm, lay["fusszeile_text"])
        c.setFont(f_norm, 7)
        c.setFillColor(sekundaer)
        c.drawRightString(SEITE_B - RAND_R, 6 * mm, f"Seite {seite} von {gesamt}")
        c.restoreState()

    # ---------------------------------------------------------- Inhalt
    puffer = io.BytesIO()
    unten = 28 * mm
    erster_rahmen = Frame(RAND_L, unten, INHALT_B, SEITE_H - 98 * mm - unten, id="erste",
                          leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    folge_oben = 8 * mm + logo_h * 0.55 + 8 * mm
    folge_rahmen = Frame(RAND_L, unten, INHALT_B, SEITE_H - folge_oben - unten, id="folge",
                         leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc = BaseDocTemplate(
        puffer, pagesize=A4, title=f"{snap['titel']} {snap.get('nummer') or 'Entwurf'}",
        author=firma.get("firma_name", ""), subject=snap.get("betreff") or snap["titel"],
        creator="Werkstatt Sauter",
    )
    doc.addPageTemplates([
        PageTemplate(id="Erste", frames=[erster_rahmen], onPage=erste_seite, autoNextPageTemplate="Folge"),
        PageTemplate(id="Folge", frames=[folge_rahmen], onPage=folgeseite),
    ])

    inhalt = [Paragraph(escape(snap["titel"]), st["titel"])]
    if snap.get("betreff"):
        inhalt += [Spacer(1, 1 * mm), Paragraph(_absatz(snap["betreff"]), st["betreff"])]
    inhalt.append(Spacer(1, 5 * mm))
    if snap.get("einleitung"):
        inhalt += [Paragraph(_absatz(snap["einleitung"]), st["normal"]), Spacer(1, 5 * mm)]

    inhalt.append(_positionstabelle(snap, st, primaer, sekundaer))
    inhalt.append(Spacer(1, 2 * mm))
    inhalt.append(_summentabelle(snap, st, primaer))
    inhalt.append(Spacer(1, 5 * mm))

    if snap.get("kleinunternehmer_hinweis"):
        inhalt += [Paragraph(_absatz(snap["kleinunternehmer_hinweis"]), st["hinweis"]), Spacer(1, 4 * mm)]
    if snap.get("hinweise"):
        inhalt += [Paragraph(_absatz(snap["hinweise"]), st["klein"]), Spacer(1, 4 * mm)]
    if snap.get("garantie_text"):
        inhalt += [Paragraph(_absatz(snap["garantie_text"]), st["klein"]), Spacer(1, 4 * mm)]
    zahlblock = _zahlungsblock(snap, st, primaer)
    if zahlblock:
        inhalt += [zahlblock, Spacer(1, 5 * mm)]
    if snap.get("schlusstext"):
        inhalt.append(Paragraph(_absatz(snap["schlusstext"]), st["normal"]))

    doc.build(inhalt, canvasmaker=lambda *a, **k: _SeitenCanvas(*a, fusszeile=fusszeile, **k))
    return puffer.getvalue()


def _infoblock(snap):
    nr_label = {"rechnung": "Rechnungsnummer", "storno": "Stornonummer", "gutschrift": "Gutschriftnummer",
                "kva": "Angebotsnummer", "mahnung": "Mahnnummer"}.get(snap["typ"], "Dokumentnummer")
    info = [(nr_label, snap.get("nummer") or "(Entwurf)"),
            ("Datum", datum_de(snap["datum"]))]
    if snap.get("kunde", {}).get("kundennr"):
        info.append(("Kundennummer", snap["kunde"]["kundennr"]))
    if snap.get("leistungsdatum"):
        if snap.get("leistungsdatum_bis") and snap["leistungsdatum_bis"] != snap["leistungsdatum"]:
            info.append(("Leistungszeitraum",
                         f"{datum_de(snap['leistungsdatum'])} – {datum_de(snap['leistungsdatum_bis'])}"))
        else:
            info.append(("Leistungsdatum", datum_de(snap["leistungsdatum"])))
    if snap.get("bezug"):
        info.append(("Zu Rechnung", snap["bezug"]["nummer"] or ""))
    if snap["typ"] in ("rechnung", "mahnung") and snap.get("faellig_am"):
        info.append(("Zahlbar bis", datum_de(snap["faellig_am"])))
    if snap["typ"] == "kva" and snap.get("faellig_am"):
        info.append(("Gültig bis", datum_de(snap["faellig_am"])))
    if snap.get("kunde", {}).get("ust_idnr"):
        info.append(("Ihre USt-IdNr.", snap["kunde"]["ust_idnr"]))
    return info


def _fussspalten(firma):
    sp1 = [firma.get("firma_name", ""), f"Inh. {firma['inhaber']}" if firma.get("inhaber") else "",
           firma.get("strasse", ""), " ".join(x for x in [firma.get("plz"), firma.get("ort")] if x)]
    sp2 = ["Kontakt", f"Tel. {firma['telefon']}" if firma.get("telefon") else "", firma.get("email", ""),
           firma.get("web", "")]
    sp3 = ["Bankverbindung", firma.get("bank_name", ""),
           f"IBAN {iban_format(firma['iban'])}" if firma.get("iban") else "",
           f"BIC {firma['bic']}" if firma.get("bic") else ""]
    sp4 = ["Steuerangaben", f"Steuernummer {firma['steuernummer']}" if firma.get("steuernummer") else "",
           f"USt-IdNr. {firma['ust_idnr']}" if firma.get("ust_idnr") else ""]
    return [[z for z in sp if z] for sp in (sp1, sp2, sp3, sp4) if len([z for z in sp if z]) > 1]


def _positionstabelle(snap, st, primaer, sekundaer):
    mit_ust = snap["steuer_modus"] == "regel"
    kopf = ["Pos.", "Bezeichnung", "Menge", "Einheit"] + (["USt."] if mit_ust else []) + ["Einzelpreis", "Gesamt"]
    zeilen = [[Paragraph(k, st["kopf_r"] if i >= 2 and k != "Einheit" else st["kopf"]) for i, k in enumerate(kopf)]]
    leer = ""
    positions_zeilen = []  # (erste Zeilennummer, letzte Zeilennummer) je Position – für Linien und Hintergrund
    for p in snap["positionen"]:
        # Bezeichnung fett, darunter die Beschreibung kleiner (Zeilenumbrüche bleiben erhalten).
        # Lange Beschreibungen werden auf Fortsetzungszeilen verteilt, damit die Tabelle sauber
        # zwischen den Seiten umbricht.
        teile = []
        for zeile_text in (p.get("beschreibung") or "").replace("\r\n", "\n").split("\n"):
            if zeile_text.strip():
                einrueckung = len(zeile_text) - len(zeile_text.lstrip(" "))
                teile.append(Paragraph("&nbsp;" * einrueckung + escape(zeile_text.strip()), st["beschreibung"]))
            elif teile:
                teile.append(Spacer(1, st["beschreibung"].leading * 0.6))
        while teile and isinstance(teile[-1], Spacer):
            teile.pop()
        if p.get("garantie_monate") is not None:
            teile.append(Paragraph(f"Freiwillige Garantie: {p['garantie_monate']} Monate ab Abholung"
                                   if p["garantie_monate"] else "ohne freiwillige Garantie", st["beschreibung"]))
        erste = [Paragraph(f"<b>{escape(p['bezeichnung'])}</b>", st["zelle"])] + teile[:4]
        zeile = [Paragraph(str(p["pos"]), st["zelle"]), erste,
                 Paragraph(menge_text(p["menge"]), st["zelle_r"]), Paragraph(escape(p["einheit"]), st["zelle"])]
        if mit_ust:
            zeile.append(Paragraph(f"{menge_text(p['steuersatz'])} %", st["zelle_r"]))
        zeile += [Paragraph(euro(p["einzelpreis"]), st["zelle_r"]), Paragraph(euro(p["betrag"]), st["zelle_r"])]
        start = len(zeilen)
        zeilen.append(zeile)
        for i in range(4, len(teile), 3):
            fortsetzung = [leer] * len(zeile)
            fortsetzung[1] = teile[i:i + 3]
            zeilen.append(fortsetzung)
        positions_zeilen.append((start, len(zeilen) - 1))
    feste = [10 * mm, None, 15 * mm, 18 * mm] + ([13 * mm] if mit_ust else []) + [25 * mm, 25 * mm]
    rest = INHALT_B - sum(b for b in feste if b)
    breiten = [b if b else rest for b in feste]
    t = Table(zeilen, colWidths=breiten, repeatRows=1)
    stil = [
        ("BACKGROUND", (0, 0), (-1, 0), primaer),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]
    for nr, (von, bis) in enumerate(positions_zeilen):
        stil.append(("LINEBELOW", (0, bis), (-1, bis), 0.3, colors.HexColor("#D5D9DE")))
        if bis > von:  # Fortsetzungszeilen ohne Abstand dazwischen
            stil.append(("BOTTOMPADDING", (0, von), (-1, bis - 1), 0))
            stil.append(("TOPPADDING", (0, von + 1), (-1, bis), 0))
        if nr % 2 == 1:
            stil.append(("BACKGROUND", (0, von), (-1, bis), colors.HexColor("#F5F7FA")))
    t.setStyle(TableStyle(stil))
    return t


def _summentabelle(snap, st, primaer):
    s = snap["summen"]
    zeilen = []
    if snap["steuer_modus"] == "regel":
        zeilen.append([Paragraph("Nettobetrag", st["summe"]), Paragraph(euro(s["netto"]), st["summe"])])
        for g in s["gruppen"]:
            zeilen.append([Paragraph(f"zzgl. {menge_text(g['satz'])} % USt. auf {euro(g['netto'])}", st["summe"]),
                           Paragraph(euro(g["steuer"]), st["summe"])])
    zeilen.append([Paragraph("Gesamtbetrag", st["summe_fett"]), Paragraph(euro(s["brutto"]), st["summe_fett"])])
    t = Table(zeilen, colWidths=[75 * mm, 30 * mm], hAlign="RIGHT")
    t.setStyle(TableStyle([
        ("LINEABOVE", (0, -1), (-1, -1), 1, primaer),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))
    return KeepTogether([t])


def _zahlungsblock(snap, st, primaer):
    """Bankverbindung und GiroCode (QR-Code zum Bezahlen)."""
    firma = snap["firma"]
    betrag = snap["summen"]["brutto"]
    if snap["typ"] not in ("rechnung", "mahnung") or betrag <= 0 or not firma.get("iban"):
        return None
    zweck = snap.get("verwendungszweck") or snap.get("nummer") or ""
    links = (f"<b>Zahlungsinformationen</b><br/>{_absatz(snap.get('zahlungsarten_text'))}<br/>"
             f"Betrag: <b>{euro(betrag)}</b> · Verwendungszweck: <b>{escape(zweck)}</b>")
    rechts = (f"Empfänger: {escape(firma.get('kontoinhaber') or firma.get('firma_name', ''))}<br/>"
              f"IBAN: {escape(iban_format(firma['iban']))}<br/>"
              + (f"BIC: {escape(firma['bic'])}" if firma.get("bic") else "")
              + (f" · {escape(firma['bank_name'])}" if firma.get("bank_name") else ""))
    mit_qr = bool(snap["layout"].get("girocode"))
    qr_b = 24 * mm
    rest = INHALT_B - (qr_b + 4 * mm if mit_qr else 0)
    zellen = [Paragraph(links, st["zelle"]), Paragraph(rechts, st["zelle"])]
    breiten = [rest * 0.52, rest * 0.48]
    if mit_qr:
        daten = girocode_daten(firma.get("kontoinhaber") or firma.get("firma_name"), firma["iban"], firma.get("bic"),
                               betrag, zweck)
        qr = QrCodeWidget(daten, barLevel="M")
        b = qr.getBounds()
        groesse = qr_b - 4 * mm
        d = Drawing(groesse, groesse, transform=[groesse / (b[2] - b[0]), 0, 0, groesse / (b[3] - b[1]), 0, 0])
        d.add(qr)
        zellen.append([d, Paragraph("GiroCode", st["klein"])])
        breiten.append(qr_b + 4 * mm)
    t = Table([zellen], colWidths=breiten)
    t.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.6, primaer),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
    ]))
    return KeepTogether([t])
