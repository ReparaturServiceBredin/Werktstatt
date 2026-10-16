"""PDF-Protokolle für Leihgeräte: Leihvertrag/Übergabeprotokoll, Rückgabeprotokoll, Schadensfall-Dokumentation."""
import io
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from . import db as dbm
from . import fotos as fot
from . import leihgeraete as lg
from .hilfen import datum_de, euro, kunde_name
from .pdf import STANDARD_LOGO, _farbe, _schrift_registrieren

TITEL = {"ausgabe": "Leihvertrag / Übergabeprotokoll", "rueckgabe": "Rückgabeprotokoll Leihgerät",
         "schaden": "Schadensfall Leihgerät – Dokumentation"}
LINIE = colors.HexColor("#D5D9DE")


def _zeit(iso):
    if not iso:
        return "–"
    try:
        return datetime.fromisoformat(iso).strftime("%d.%m.%Y %H:%M:%S")
    except ValueError:
        return iso


def dateiname(leihe, art):
    return {"ausgabe": "Leihvertrag", "rueckgabe": "Rueckgabeprotokoll", "schaden": "Schadensfall"}[art] + \
        f"_{leihe['leihnr']}.pdf"


def protokoll_pdf(con, leihe_id, art, daten_dir):
    le = con.execute("SELECT * FROM leihen WHERE id=?", (leihe_id,)).fetchone()
    g = con.execute("SELECT * FROM leihgeraete WHERE id=?", (le["geraet_id"],)).fetchone()
    k = con.execute("SELECT * FROM kunden WHERE id=?", (le["kunde_id"],)).fetchone()
    a = con.execute("SELECT * FROM auftraege WHERE id=?", (le["auftrag_id"],)).fetchone() if le["auftrag_id"] else None
    einst = dbm.einstellungen(con)
    f_norm, f_fett, _ = _schrift_registrieren(einst.get("schrift") or "Montserrat")
    blau = _farbe(einst.get("farbe_primaer"))
    grau = _farbe(einst.get("farbe_sekundaer"), "#5D6670")
    st = ParagraphStyle("n", fontName=f_norm, fontSize=9, leading=12.5)
    st_f = ParagraphStyle("f", parent=st, fontName=f_fett)
    st_k = ParagraphStyle("k", fontName=f_norm, fontSize=7.5, leading=10, textColor=grau)
    st_t = ParagraphStyle("t", fontName=f_fett, fontSize=15, leading=19, textColor=blau)
    st_h = ParagraphStyle("h", fontName=f_fett, fontSize=10.5, leading=14, textColor=blau, spaceBefore=8, spaceAfter=3,
                          keepWithNext=1)
    rot = ParagraphStyle("r", parent=st, textColor=colors.HexColor("#B3261E"))

    def p(text, stil=st):
        return Paragraph(escape(str(text if text is not None else "")).replace("\n", "<br/>"), stil)

    def tabelle(zeilen, breiten=(45 * mm, 125 * mm)):
        t = Table([[p(x, st_f), y if not isinstance(y, str) else p(y)] for x, y in zeilen], colWidths=list(breiten))
        t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, -1), 0.3, LINIE),
                               ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
        return t

    firma = einst.get("firma_name") or ""
    adresse = ", ".join(x for x in [einst.get("strasse"), " ".join(x for x in [einst.get("plz"), einst.get("ort")] if x)]
                        if x)
    logo = STANDARD_LOGO
    if einst.get("logo_datei") and (Path(daten_dir) / einst["logo_datei"]).is_file():
        logo = Path(daten_dir) / einst["logo_datei"]

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
        fuss = " · ".join(x for x in [firma, adresse, einst.get("telefon"), einst.get("email"), einst.get("web")] if x)
        c.drawString(20 * mm, 10 * mm, fuss[:150])
        c.drawRightString(190 * mm, 10 * mm, f"{le['leihnr']} · Seite {doc.page}")
        c.restoreState()

    puffer = io.BytesIO()
    doc = SimpleDocTemplate(puffer, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=34 * mm,
                            bottomMargin=18 * mm, title=f"{TITEL[art]} {le['leihnr']}", author=firma)
    inhalt = [p(TITEL[art], st_t), p(f"Nr. {le['leihnr']} · erstellt {_zeit(dbm.jetzt_berlin())}", st_k),
              Spacer(1, 4 * mm)]
    if le["storniert_am"]:
        inhalt.append(p(f"STORNIERT am {_zeit(le['storniert_am'])} – Grund: {le['storno_grund']}", rot))

    # Vertragsparteien
    kunde_txt = "\n".join(x for x in [kunde_name(k), k["strasse"], " ".join(x for x in [k["plz"], k["ort"]] if x),
                                      " · ".join(x for x in [k["telefon"], k["email"]] if x)] if x)
    parteien = Table([[p("Verleiher", st_f), p("Entleiher (Kunde)", st_f)],
                      [p("\n".join(x for x in [firma, einst.get("inhaber"), adresse, einst.get("telefon"),
                                               einst.get("email")] if x)),
                       p(f"{kunde_txt}\nKunden-Nr. {k['kundennr']}")]], colWidths=[85 * mm, 85 * mm])
    parteien.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, 0), 0.5, blau)]))
    inhalt += [parteien, Spacer(1, 3 * mm)]

    # Gerät
    inhalt.append(p("Leihgerät", st_h))
    geraet = " · ".join(x for x in [g["geraetetyp"], g["hersteller"], g["modell"]] if x)
    inhalt.append(tabelle([
        ("Bezeichnung", g["bezeichnung"]), ("Typ / Hersteller / Modell", geraet or "–"),
        ("Seriennummer", g["seriennummer"] or "–"), ("Inventarnummer", g["inventarnr"] or "–"),
        ("Zeitwert (bei Verlust)", euro(g["zeitwert"]) if g["zeitwert"] else "–"),
        ("Zum Reparaturauftrag", f"{le['auftragsnr'] or '–'}" + (f" ({a['geraet']})" if a and a["geraet"] else "")),
    ]))

    # Zubehör
    ausgabe = lg.liste_aus_json(le["zubehoer_ausgabe"])
    zurueck = lg.liste_aus_json(le["zubehoer_rueckgabe"]) if le["rueckgabe_am"] else None
    standard = lg.liste_aus_json(g["zubehoer"])
    alle = ausgabe + [z for z in standard if z not in ausgabe]
    if alle:
        inhalt.append(p("Zubehör", st_h))
        kopf = ["Zubehör", "mitgegeben"] + (["zurück"] if zurueck is not None and art != "ausgabe" else [])
        zeilen = [[p(x, st_f) for x in kopf]]
        for z in alle:
            zeile = [p(z), p("ja" if z in ausgabe else "nein")]
            if len(kopf) == 3:
                zeile.append(p("ja", st) if z in zurueck else (p("FEHLT", rot) if z in ausgabe else p("–")))
            zeilen.append(zeile)
        t = Table(zeilen, colWidths=[110 * mm, 30 * mm, 30 * mm][:len(kopf)] if len(kopf) == 3 else [110 * mm, 60 * mm])
        t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.3, LINIE), ("LINEBELOW", (0, 0), (-1, 0), 0.6, blau)]))
        inhalt.append(t)

    # Ausgabe
    inhalt.append(p("Ausgabe", st_h))
    kaution = (f"{euro(le['kaution_betrag'])} erhalten ({le['kaution_zahlart'] or '–'})" if le["kaution_erhalten"]
               else "keine")
    inhalt.append(tabelle([
        ("Ausgabe am", _zeit(le["ausgabe_am"]) + f" (durch {le['ausgegeben_von'] or ''})"),
        ("Rückgabe bis", datum_de(le["rueckgabe_geplant"]) if le["rueckgabe_geplant"] else "nach Abschluss der Reparatur"),
        ("Zustand bei Ausgabe", f"Protokoll gelöscht (Löschfrist) am {_zeit(le['protokoll_geloescht_am'])}"
         if le["protokoll_geloescht_am"] else le["zustand_ausgabe"] or "–"),
        ("Leihgebühr", lg.gebuehr_beschreibung(le["gebuehr_art"], le["gebuehr_betrag"], le["frei_tage"])),
        ("Kaution", kaution),
    ]))

    # Rückgabe
    if art in ("rueckgabe", "schaden") and le["rueckgabe_am"]:
        inhalt.append(p("Rückgabe", st_h))
        fehlt = [z for z in ausgabe if z not in (zurueck or [])]
        inhalt.append(tabelle([
            ("Rückgabe am", _zeit(le["rueckgabe_am"]) + f" (durch {le['zurueckgenommen_von'] or ''})"),
            ("Zustand", "einwandfrei" if le["zustand_rueckgabe"] == "einwandfrei" else "Schaden festgestellt"),
            ("Notiz", le["rueckgabe_notiz"] or "–"),
            ("Fehlendes Zubehör", ", ".join(fehlt) if fehlt else "nichts"),
            ("Leihtage / Leihgebühr", f"{le['tage']} Tag(e) · {euro(le['gebuehr_berechnet'] or 0)}\n{le['gebuehr_text'] or ''}"),
            ("Kaution", lg.KAUTION_STATUS.get(le["kaution_status"], le["kaution_status"])
             + (f" am {_zeit(le['kaution_erledigt_am'])}" if le["kaution_erledigt_am"] else "")),
        ]))

    # Schadensfälle + Verrechnung
    alle_schaeden = lg.schaeden(con, le["id"], mit_stornierten=True)
    if art in ("rueckgabe", "schaden") and alle_schaeden:
        inhalt.append(p("Schadensfälle", st_h))
        zeilen = [[p("Erfasst", st_f), p("Beschreibung", st_f), p("Kostenart", st_f), p("Betrag", st_f)]]
        for s in alle_schaeden:
            stil = st_k if s["storniert_am"] else st
            beschr = s["beschreibung"] + (f"\nSTORNIERT {_zeit(s['storniert_am'])}: {s['storno_grund']}"
                                          if s["storniert_am"] else "")
            zeilen.append([p(f"{_zeit(s['erstellt_am'])}\n{s['benutzer'] or ''}", st_k), p(beschr, stil),
                           p(lg.KOSTENARTEN[s["kostenart"]], stil), p(euro(s["betrag"]), stil)])
        t = Table(zeilen, colWidths=[32 * mm, 78 * mm, 38 * mm, 22 * mm], repeatRows=1)
        t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, -1), 0.3, LINIE),
                               ("LINEBELOW", (0, 0), (-1, 0), 0.6, blau)]))
        inhalt.append(t)
        v = lg.kaution_verrechnung(con, le)
        if v["kaution"]:
            inhalt.append(Spacer(1, 2 * mm))
            inhalt.append(tabelle([("Schadenersatz gesamt", euro(v["schaden"])),
                                   ("Erhaltene Kaution", euro(v["kaution"])),
                                   ("Durch Kaution verrechnet", euro(v["angerechnet"])),
                                   ("Noch zu zahlen", euro(v["nachzahlung"])),
                                   ("Erstattung an Kunden", euro(v["erstattung"]))], (60 * mm, 110 * mm)))

    # Fotos: Ausgabe und Rückgabe nebeneinander
    fotos = fot.liste(con, leihe_id=le["id"])
    gruppen = [("Leihgerät Ausgabe", "Zustand bei Ausgabe")]
    if art != "ausgabe":
        gruppen.append(("Leihgerät Rückgabe", "Zustand bei Rückgabe"))
    if art == "schaden":
        gruppen.append(("Leihgerät Schaden", "Schadensfotos"))
    spalten = [[f for f in fotos if f["kategorie"] == kat] for kat, _ in gruppen]
    if len(gruppen) == 1 and len(spalten[0]) > 1:  # nur Ausgabe: Fotos zweispaltig
        gruppen = [gruppen[0], ("", "")]
        spalten = [spalten[0][0::2], spalten[0][1::2]]
    if any(spalten):
        inhalt.append(p("Fotos" + (" – Vergleich Ausgabe / Rückgabe" if len(gruppen) > 1 else ""), st_h))
        breite = 170 / max(len(gruppen), 2)
        zeilen = [[p(titel, st_f) for _, titel in gruppen]]
        for i in range(max(len(sp) for sp in spalten)):
            zeile = []
            for sp in spalten:
                if i < len(sp):
                    f = sp[i]
                    bild = fot.bild_flowable(daten_dir, f, breite_mm=breite - 6, max_hoehe_mm=60)
                    text = (f"{f['dateiname']}\nHochgeladen {_zeit(f['hochgeladen_am'])}\n"
                            f"Aufnahme (EXIF) {_zeit(f['exif_zeit']) if f['exif_zeit'] else '–'}\n"
                            f"SHA-256 {f['sha256'][:16]}…")
                    if f["geloescht_am"]:
                        text += f"\nALS GELÖSCHT MARKIERT: {f['loeschgrund']}"
                    zeile.append([bild, p(text, st_k)] if bild else p(text, st_k))
                else:
                    zeile.append("")
            zeilen.append(zeile)
        t = Table(zeilen, colWidths=[breite * mm] * len(gruppen), repeatRows=1, hAlign="LEFT")
        t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, -1), 0.3, LINIE)]))
        inhalt.append(t)

    # Leihbedingungen + Unterschriften
    if art == "ausgabe":
        bedingungen = (einst.get("leihbedingungen") or "").replace("{firma}", firma)
        inhalt += [p("Leihbedingungen", st_h), p(bedingungen, ParagraphStyle("b", parent=st, fontSize=8, leading=11))]
    if art == "schaden":
        verlauf = con.execute("SELECT * FROM leihgeraet_verlauf WHERE geraet_id=? AND zeitpunkt>=? ORDER BY id",
                              (g["id"], le["ausgabe_am"][:19])).fetchall()
        inhalt.append(p("Verlauf", st_h))
        zeilen = [[p(_zeit(v["zeitpunkt"]), st_k), p(v["benutzer"] or "", st_k),
                   p(f"{v['ereignis']}: {v['details'] or ''}", st_k)] for v in verlauf]
        if zeilen:
            t = Table(zeilen, colWidths=[32 * mm, 22 * mm, 116 * mm])
            t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, -1), 0.3, LINIE)]))
            inhalt.append(t)
        inhalt.append(p("Die Fotos werden als unveränderte Originale mit SHA-256-Prüfsumme gespeichert. Protokolle und "
                        "Schadensfälle lassen sich nicht ändern oder löschen, nur mit Begründung stornieren.", st_k))
    else:
        bestaetigung = ("Der Kunde bestätigt den Erhalt des Leihgeräts mit dem oben genannten Zubehör im beschriebenen "
                        "Zustand und erkennt die Leihbedingungen an." if art == "ausgabe" else
                        "Die Rückgabe des Leihgeräts im oben beschriebenen Zustand wird bestätigt.")
        unterschrift = Table([[p("\n\n\n______________________________\nOrt, Datum, Unterschrift Kunde"),
                               p(f"\n\n\n______________________________\nOrt, Datum, Unterschrift {firma}")]],
                             colWidths=[85 * mm, 85 * mm])
        inhalt.append(KeepTogether([Spacer(1, 5 * mm), p(bestaetigung), unterschrift]))
    doc.build(inhalt, onFirstPage=seite, onLaterPages=seite)
    return puffer.getvalue()
