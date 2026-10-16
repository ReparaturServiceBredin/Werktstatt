"""PDF für Annahmeschein und Abholschein (aus den eingefrorenen Angaben, optional mit digitaler Unterschrift)."""
import io
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from . import fotos as fot
from .hilfen import datum_de, euro
from .pdf import STANDARD_LOGO, _farbe, _schrift_registrieren

LINIE = colors.HexColor("#D5D9DE")


def _zeit(iso):
    if not iso:
        return "–"
    try:
        return datetime.fromisoformat(iso).strftime("%d.%m.%Y %H:%M:%S")
    except ValueError:
        return iso


def dateiname(snap):
    return f"{snap['titel']}_{snap.get('nummer') or snap['auftragsnr']}.pdf"


def erstellen(snap, daten_dir, einst, unterschrift=None):
    """snap: annahme.snapshot(); unterschrift: PNG-Bytes (sonst Unterschriftslinie zum Ausdrucken)."""
    f_norm, f_fett, _ = _schrift_registrieren(einst.get("schrift") or "Montserrat")
    blau = _farbe(einst.get("farbe_primaer"))
    grau = _farbe(einst.get("farbe_sekundaer"), "#5D6670")
    st = ParagraphStyle("n", fontName=f_norm, fontSize=9, leading=12.5)
    st_f = ParagraphStyle("f", parent=st, fontName=f_fett)
    st_k = ParagraphStyle("k", fontName=f_norm, fontSize=7.5, leading=10, textColor=grau)
    st_t = ParagraphStyle("t", fontName=f_fett, fontSize=15, leading=19, textColor=blau)
    st_h = ParagraphStyle("h", fontName=f_fett, fontSize=10.5, leading=14, textColor=blau, spaceBefore=7, spaceAfter=3,
                          keepWithNext=1)
    st_b = ParagraphStyle("b", parent=st, fontSize=8, leading=11)

    def p(text, stil=st):
        return Paragraph(escape(str(text if text is not None else "")).replace("\n", "<br/>"), stil)

    def tabelle(zeilen, breiten=(52 * mm, 118 * mm)):
        t = Table([[p(x, st_f), y if not isinstance(y, str) else p(y)] for x, y in zeilen], colWidths=list(breiten))
        t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, -1), 0.3, LINIE),
                               ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
        return t

    firma = snap["firma"]
    logo = STANDARD_LOGO
    if einst.get("logo_datei") and (Path(daten_dir) / einst["logo_datei"]).is_file():
        logo = Path(daten_dir) / einst["logo_datei"]
    nummer = snap.get("nummer") or f"{snap['auftragsnr']} (Entwurf, nicht unterschrieben)"

    def seite(c, doc):
        c.saveState()
        try:
            from reportlab.lib.utils import ImageReader
            bild = ImageReader(str(logo))
            iw, ih = bild.getSize()
            b = 45 * mm
            c.drawImage(bild, 190 * mm - b, 297 * mm - 10 * mm - b * ih / iw, width=b, height=b * ih / iw, mask="auto")
        except Exception:
            pass
        c.setFont(f_norm, 7)
        c.setFillColor(grau)
        fuss = " · ".join(x for x in [firma["name"], firma["strasse"], firma["plz_ort"], firma["telefon"],
                                      firma["email"], firma["web"]] if x)
        c.drawString(20 * mm, 10 * mm, fuss[:150])
        c.drawRightString(190 * mm, 10 * mm, f"{snap.get('nummer') or snap['auftragsnr']} · Seite {doc.page}")
        c.restoreState()

    puffer = io.BytesIO()
    doc = SimpleDocTemplate(puffer, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=34 * mm,
                            bottomMargin=18 * mm, title=f"{snap['titel']} {nummer}", author=firma["name"])
    inhalt = [p(snap["titel"], st_t),
              p(f"Nr. {nummer} · Reparaturauftrag {snap['auftragsnr']} · Eingang {_zeit(snap['eingang_am'])}", st_k),
              Spacer(1, 4 * mm)]

    kunde = snap["kunde"]
    parteien = Table([[p("Werkstatt", st_f), p("Kunde", st_f)],
                      [p("\n".join(x for x in [firma["name"], firma["inhaber"], firma["strasse"], firma["plz_ort"],
                                               firma["telefon"], firma["email"]] if x)),
                       p("\n".join(x for x in [kunde["name"], kunde["strasse"], kunde["plz_ort"],
                                               " · ".join(y for y in [kunde["telefon"], kunde["email"]] if y),
                                               f"Kunden-Nr. {kunde['kundennr']}"] if x))]],
                     colWidths=[85 * mm, 85 * mm])
    parteien.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, 0), 0.5, blau)]))
    inhalt += [parteien, Spacer(1, 2 * mm)]

    inhalt.append(p("Gerät", st_h))
    zeilen = [("Gerät", snap["geraet"] or "–"), ("Seriennr. / IMEI", snap["seriennummer"] or "–")]
    if snap["leistungsart"]:
        zeilen.append(("Leistungsart", snap["leistungsart"]))
    zeilen.append(("Fehler laut Kunde", snap["fehler"] or "–"))
    if snap["art"] == "annahme":
        zeilen.append(("Zustand bei Eingang", (snap["zustand_eingang"] or "keine Auffälligkeiten notiert")
                       + (f"\n{len(snap['fotos'])} Eingangsfoto(s) dokumentiert, siehe unten" if snap["fotos"] else "")))
        zeilen.append(("Gerätezugang", snap["zugang"]))
    inhalt.append(tabelle(zeilen))

    # Zubehör als Checkliste
    zubehoer = snap["zubehoer"]
    if zubehoer or snap["zubehoer_sonstiges"]:
        inhalt.append(p("Zubehör" + (" (abgegeben)" if snap["art"] == "annahme" else " (zurückgegeben)"), st_h))
        felder = [f"{'[X]' if z['dabei'] else '[  ]'} {z['name']}" for z in zubehoer]
        if snap["zubehoer_sonstiges"]:
            felder.append(f"[X] {snap['zubehoer_sonstiges']}")
        spalten = 3
        reihen = [felder[i:i + spalten] + [""] * (spalten - len(felder[i:i + spalten]))
                  for i in range(0, len(felder), spalten)]
        t = Table([[p(x) for x in r] for r in reihen], colWidths=[170 * mm / spalten] * spalten)
        t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.3, LINIE)]))
        inhalt.append(t)

    if snap["art"] == "annahme":
        inhalt.append(p("Vereinbarungen", st_h))
        grenze = snap["kosten_obergrenze"]
        inhalt.append(tabelle([
            ("Kosten-Obergrenze", f"Reparatur ohne Rückfrage bis {euro(grenze)} (brutto)" if grenze
             else "keine – vor kostenpflichtigen Arbeiten wird Rücksprache gehalten"),
            ("Kostenvoranschlag", "gewünscht" if snap["kva_gewuenscht"] else "nicht gewünscht"),
            ("KVA-Pauschale", (euro(snap["kva_gebuehr"]) if snap["kva_gebuehr"] else "kostenlos")
             if snap["kva_gebuehr"] is not None else "keine"),
            ("Voraussichtliche Fertigstellung", datum_de(snap["fertig_bis"]) if snap["fertig_bis"] else "offen"),
        ]))
        if snap.get("kva_text"):  # Pauschale deutlich ausweisen
            kasten = Table([[p(snap["kva_text"], st_f)]], colWidths=[170 * mm])
            kasten.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.8, blau), ("BACKGROUND", (0, 0), (-1, -1),
                                                                               colors.HexColor("#EEF3FB")),
                                        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
            inhalt += [Spacer(1, 2 * mm), kasten]
    else:
        r = snap.get("rechnung")
        zeilen = [("Abgeholt am", _zeit(snap.get("unterschrieben_am")) if snap.get("unterschrieben_am") else "–")]
        if r:
            zeilen.append(("Rechnung", f"{r['nummer']} vom {datum_de(r['datum'])} über {euro(r['betrag'])} – {r['status']}"
                           + (f", offen {euro(r['offen'])}" if r["offen"] else "")))
        if snap.get("garantie"):
            zeilen.append(("Freiwillige Garantie", snap["garantie"]))
        inhalt.append(p("Abholung", st_h))
        inhalt.append(tabelle(zeilen))

    if snap["fotos"]:
        inhalt.append(p("Fotos " + ("bei Eingang" if snap["art"] == "annahme" else "bei Ausgabe"), st_h))
        zellen = []
        for f in snap["fotos"][:9]:
            bild = fot.bild_flowable(daten_dir, f, breite_mm=50, max_hoehe_mm=42)
            text = p(f"{f['kategorie']} · SHA-256 {f['sha256'][:12]}…", st_k)
            zellen.append([bild, text] if bild else text)
        reihen = [zellen[i:i + 3] + [""] * (3 - len(zellen[i:i + 3])) for i in range(0, len(zellen), 3)]
        t = Table(reihen, colWidths=[56 * mm] * 3, hAlign="LEFT")
        t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
        inhalt.append(t)
        if len(snap["fotos"]) > 9:
            inhalt.append(p(f"… und {len(snap['fotos']) - 9} weitere Foto(s) in der Auftragsdokumentation.", st_k))

    if snap["art"] == "annahme":
        if snap["datenschutz"]:
            inhalt += [p("Datenschutz und Datensicherung", st_h), p(snap["datenschutz"], st_b)]
        if snap["abholbedingungen"]:
            inhalt += [p("Abholbedingungen", st_h), p(snap["abholbedingungen"], st_b)]
        erklaerung = ("Ich beauftrage die Reparatur zu den oben genannten Bedingungen und bestätige die Richtigkeit der "
                      "Angaben sowie die Kenntnisnahme der Hinweise zu Datenschutz und Abholung.")
    else:
        erklaerung = snap.get("erklaerung") or ""

    block = [Spacer(1, 4 * mm), p(erklaerung)]
    if unterschrift:
        from PIL import Image as PILImage
        with PILImage.open(io.BytesIO(unterschrift)) as b:
            w, h = b.size
        hoehe = min(28 * mm, 80 * mm * h / w)
        bild = Image(io.BytesIO(unterschrift), width=hoehe * w / h, height=hoehe)
        t = Table([[bild], [p(f"{snap.get('unterzeichner') or ''} – digital unterschrieben am "
                              f"{_zeit(snap.get('unterschrieben_am'))} ({snap.get('quelle') or 'Bildschirm'})", st_k)]],
                  colWidths=[110 * mm], hAlign="LEFT")
        t.setStyle(TableStyle([("LINEABOVE", (0, 1), (0, 1), 0.5, colors.black), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
        block += [Spacer(1, 2 * mm), t,
                  p("Zeitpunkt der Unterschrift: Serverzeit (Europe/Berlin). Dieses Dokument wurde nach der Unterschrift "
                    "unverändert archiviert und mit einer SHA-256-Prüfsumme gesichert.", st_k)]
    else:
        t = Table([[p("\n\n\n______________________________\nOrt, Datum, Unterschrift Kunde"),
                    p(f"\n\n\n______________________________\nUnterschrift {firma['name']}")]],
                  colWidths=[85 * mm, 85 * mm])
        block.append(t)
    inhalt.append(KeepTogether(block))
    doc.build(inhalt, onFirstPage=seite, onLaterPages=seite)
    return puffer.getvalue()

