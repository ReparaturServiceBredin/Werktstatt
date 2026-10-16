"""Einkauf: Lieferanten, Bezugsquellen je Artikel, Bestellungen, Wareneingang, Eingangsrechnungen.

- Bestellnummern (BE-…) und Belegnummern der Eingangsrechnungen (ER-…) laufen über die Nummernkreise.
- Wareneingang erhöht den Lagerbestand (lagerbewegungen), aktualisiert den Einkaufspreis und meldet eingetroffene
  Teile beim zugehörigen Reparaturauftrag.
- Eingangsrechnungen: Originaldatei wird unverändert mit SHA-256 abgelegt; Löschen ist nicht möglich (Storno mit Grund),
  Änderungen an den Angaben stehen im Änderungsprotokoll.
"""
import hashlib
import io
from datetime import date, timedelta
from pathlib import Path

from . import db as dbm
from .hilfen import EingabeFehler, euro, menge_text

BESTELL_STATUS = {"entwurf": "Entwurf", "bestellt": "bestellt", "teilweise": "teilweise geliefert",
                  "geliefert": "geliefert", "storniert": "storniert"}
ER_STATUS = {"offen": "offen", "bezahlt": "bezahlt", "storniert": "storniert"}
ZAHLARTEN = {"ueberweisung": "Überweisung", "lastschrift": "Lastschrift", "bar": "Bar", "karte": "Karte",
             "paypal": "PayPal"}
LIEFERANT_FELDER = ("name", "ansprechpartner", "email", "telefon", "strasse", "plz", "ort", "land", "ust_idnr", "iban",
                    "kundennr_bei", "webshop", "zahlungsbedingungen", "zahlungsziel_tage", "lieferzeit_tage",
                    "kreditornr", "notizen")
LIEFERANT_NAMEN = {"name": "Name", "ansprechpartner": "Ansprechpartner", "email": "E-Mail", "telefon": "Telefon",
                   "strasse": "Straße", "plz": "PLZ", "ort": "Ort", "land": "Land", "ust_idnr": "USt-IdNr.",
                   "iban": "IBAN", "kundennr_bei": "Meine Kundennummer", "webshop": "Webshop",
                   "zahlungsbedingungen": "Zahlungsbedingungen", "zahlungsziel_tage": "Zahlungsziel (Tage)",
                   "lieferzeit_tage": "Lieferzeit (Tage)", "kreditornr": "Kreditorennummer", "notizen": "Notizen",
                   "aktiv": "aktiv"}
ER_NAMEN = {"lieferant_id": "Lieferant", "lieferant_name": "Lieferant (Name)", "nummer": "Rechnungsnummer",
            "datum": "Rechnungsdatum", "faellig_am": "fällig am", "netto": "Netto (Cent)", "steuer": "Steuer (Cent)",
            "brutto": "Brutto (Cent)", "steuersatz": "Steuersatz", "kostenart": "Kostenart",
            "bestellung_id": "Bestellung", "beschreibung": "Beschreibung"}


# ---------------------------------------------------------------------- Lieferanten

def lieferant_speichern(con, daten, lid=None):
    if not (daten.get("name") or "").strip():
        raise EingabeFehler("Bitte den Namen des Lieferanten angeben.")
    werte = {f: (daten.get(f) or None) for f in LIEFERANT_FELDER}
    for f in ("zahlungsziel_tage", "lieferzeit_tage"):
        werte[f] = int(werte[f]) if str(werte[f] or "").strip().isdigit() else None
    if werte["iban"]:
        werte["iban"] = werte["iban"].replace(" ", "").upper()
    werte["aktiv"] = 1 if daten.get("aktiv", "1") else 0
    if lid:
        alt = con.execute("SELECT * FROM lieferanten WHERE id=?", (lid,)).fetchone()
        con.execute(f"UPDATE lieferanten SET {', '.join(f'{k}=?' for k in werte)}, geaendert_am=? WHERE id=?",
                    (*werte.values(), dbm.jetzt(), lid))
        dbm.aenderungen_erfassen(con, "lieferant", lid, alt, werte, namen=LIEFERANT_NAMEN)
        return lid
    cur = con.execute(f"INSERT INTO lieferanten ({', '.join(werte)}, erstellt_am, geaendert_am) "
                      f"VALUES ({', '.join('?' * len(werte))}, ?, ?)", (*werte.values(), dbm.jetzt(), dbm.jetzt()))
    dbm.aenderungen_erfassen(con, "lieferant", cur.lastrowid, None, werte, aktion="angelegt", namen=LIEFERANT_NAMEN)
    dbm.protokollieren("lieferant_angelegt", "lieferant", cur.lastrowid, {"name": werte["name"]}, con=con)
    return cur.lastrowid


def lieferanten(con, nur_aktive=False):
    return con.execute("SELECT l.*, (SELECT COUNT(*) FROM artikel_lieferanten al WHERE al.lieferant_id=l.id) AS artikel, "
                       "(SELECT COUNT(*) FROM bestellungen b WHERE b.lieferant_id=l.id AND b.status IN "
                       "('bestellt', 'teilweise')) AS offene_bestellungen FROM lieferanten l "
                       + ("WHERE l.aktiv=1 " if nur_aktive else "") + "ORDER BY l.name").fetchall()


# ---------------------------------------------------------------------- Bezugsquellen / Einkaufspreise

def marge_pruefen(einst, artikel):
    """Warntext, wenn die Marge (vom Verkaufspreis) unter der Mindestmarge liegt."""
    if artikel["ek_unbekannt"] or not artikel["preis"]:
        return None
    grenze = float(einst.get("mindest_marge_prozent") or 0)
    marge = (artikel["preis"] - (artikel["teilekosten"] or 0)) / artikel["preis"] * 100
    if marge < grenze:
        return (f"Marge von „{artikel['name']}“ liegt nach der EK-Änderung nur noch bei {marge:.0f} % "
                f"(Grenze {grenze:.0f} %) – Verkaufspreis prüfen.")
    return None


def ek_aktualisieren(con, artikel_id, ek, quelle):
    """Einkaufspreis des Artikels setzen (protokolliert). Gibt eine Margen-Warnung oder None zurück."""
    a = con.execute("SELECT * FROM artikel WHERE id=?", (artikel_id,)).fetchone()
    if not a or ek is None:
        return None
    if a["teilekosten"] == ek and not a["ek_unbekannt"]:
        return None
    from .katalog import aufschlag
    neu = {"teilekosten": ek, "ek_unbekannt": 0, "aufschlag_prozent": aufschlag(a["preis"], ek) if ek else None}
    con.execute("UPDATE artikel SET teilekosten=?, ek_unbekannt=?, aufschlag_prozent=?, geaendert_am=? WHERE id=?",
                (neu["teilekosten"], neu["ek_unbekannt"], neu["aufschlag_prozent"], dbm.jetzt(), artikel_id))
    dbm.aenderungen_erfassen(con, "artikel", artikel_id, a, neu, aktion=f"EK geändert ({quelle})",
                             namen={"teilekosten": "Einkauf (Cent)", "ek_unbekannt": "Einkauf unbekannt",
                                    "aufschlag_prozent": "Aufschlag %"})
    return marge_pruefen(dbm.einstellungen(con), con.execute("SELECT * FROM artikel WHERE id=?",
                                                              (artikel_id,)).fetchone())


def bezugsquelle_speichern(con, artikel_id, lieferant_id, ek, lieferanten_artnr="", garantie_monate=None):
    if not con.execute("SELECT 1 FROM lieferanten WHERE id=?", (lieferant_id,)).fetchone():
        raise EingabeFehler("Bitte einen Lieferanten wählen.")
    con.execute("INSERT INTO artikel_lieferanten (artikel_id, lieferant_id, ek, lieferanten_artnr, garantie_monate, "
                "geaendert_am) VALUES (?,?,?,?,?,?) ON CONFLICT(artikel_id, lieferant_id) DO UPDATE SET ek=excluded.ek, "
                "lieferanten_artnr=excluded.lieferanten_artnr, garantie_monate=excluded.garantie_monate, "
                "geaendert_am=excluded.geaendert_am",
                (artikel_id, lieferant_id, ek, lieferanten_artnr or None, garantie_monate, dbm.jetzt()))
    dbm.ereignis_erfassen(con, "artikel", artikel_id, "Bezugsquelle gespeichert",
                          f"Lieferant #{lieferant_id}: EK {euro(ek) if ek is not None else 'unbekannt'}")


def bezugsquellen(con, artikel_id):
    """Lieferanten eines Artikels, günstigster zuerst (ohne EK am Ende)."""
    return con.execute("SELECT al.*, l.name, l.lieferzeit_tage, l.webshop FROM artikel_lieferanten al "
                       "JOIN lieferanten l ON l.id=al.lieferant_id WHERE al.artikel_id=? AND l.aktiv=1 "
                       "ORDER BY al.ek IS NULL, al.ek, l.name", (artikel_id,)).fetchall()


def guenstigste_quelle(con, artikel_id):
    q = bezugsquellen(con, artikel_id)
    return q[0] if q else None


# ---------------------------------------------------------------------- Bestellungen

def _nummer(con, einst, praefix_schluessel, standard):
    from .logik import naechste_nummer
    return naechste_nummer(con, einst.get(praefix_schluessel) or standard, date.today().year, einst["nummern_format"])


def bestellung_anlegen(con, lieferant_id, positionen, notiz="", auftrag_id=None):
    """positionen: [{artikel_id, bezeichnung, menge, ek, lieferanten_artnr, auftrag_id}]. Muss in einer Transaktion."""
    l = con.execute("SELECT * FROM lieferanten WHERE id=?", (lieferant_id,)).fetchone()
    if not l:
        raise EingabeFehler("Bitte einen Lieferanten wählen.")
    if not positionen:
        raise EingabeFehler("Die Bestellung hat keine Positionen.")
    einst = dbm.einstellungen(con)
    nummer = _nummer(con, einst, "praefix_bestellung", "BE")
    erwartet = (date.today() + timedelta(days=l["lieferzeit_tage"])).isoformat() if l["lieferzeit_tage"] else None
    cur = con.execute("INSERT INTO bestellungen (nummer, lieferant_id, status, erwartet_am, notiz, erstellt_am, benutzer) "
                      "VALUES (?,?,'entwurf',?,?,?,?)", (nummer, lieferant_id, erwartet, notiz or None,
                                                         dbm.jetzt_berlin(), dbm.aktueller_benutzer()))
    bid = cur.lastrowid
    for p in positionen:
        menge = float(p.get("menge") or 0)
        if menge <= 0 or not (p.get("bezeichnung") or "").strip():
            continue
        con.execute("INSERT INTO bestell_positionen (bestellung_id, artikel_id, bezeichnung, lieferanten_artnr, menge, "
                    "ek, auftrag_id) VALUES (?,?,?,?,?,?,?)",
                    (bid, p.get("artikel_id"), p["bezeichnung"].strip(), p.get("lieferanten_artnr") or None, menge,
                     p.get("ek"), p.get("auftrag_id") or auftrag_id))
    dbm.protokollieren("bestellung_angelegt", "bestellung", bid, {"nummer": nummer}, con=con)
    return bid


def aus_vorschlag(con, auswahl):
    """auswahl: [(artikel_id, menge)] → je Lieferant (günstigster) eine Bestellung. Gibt (ids, ohne_lieferant)."""
    gruppen, ohne = {}, []
    for artikel_id, menge in auswahl:
        a = con.execute("SELECT * FROM artikel WHERE id=?", (artikel_id,)).fetchone()
        q = guenstigste_quelle(con, artikel_id)
        if not a:
            continue
        if not q:
            ohne.append(a["name"])
            continue
        gruppen.setdefault(q["lieferant_id"], []).append(
            {"artikel_id": a["id"], "bezeichnung": a["name"], "menge": menge,
             "ek": q["ek"] if q["ek"] is not None else a["teilekosten"], "lieferanten_artnr": q["lieferanten_artnr"]})
    ids = [bestellung_anlegen(con, lid, pos, "aus Bestellvorschlag") for lid, pos in gruppen.items()]
    return ids, ohne


def bestellung(con, bid):
    b = con.execute("SELECT b.*, l.name AS lieferant, l.email AS lemail, l.kundennr_bei, l.webshop FROM bestellungen b "
                    "JOIN lieferanten l ON l.id=b.lieferant_id WHERE b.id=?", (bid,)).fetchone()
    if not b:
        raise EingabeFehler("Bestellung nicht gefunden.")
    return b


def positionen(con, bid):
    return con.execute("SELECT p.*, a.lagerfuehrend, a.einheit, au.auftragsnr FROM bestell_positionen p "
                       "LEFT JOIN artikel a ON a.id=p.artikel_id LEFT JOIN auftraege au ON au.id=p.auftrag_id "
                       "WHERE p.bestellung_id=? ORDER BY p.id", (bid,)).fetchall()


def bestellt_markieren(con, bid, erwartet_am=None):
    """Status → bestellt. Aufträge mit bestellten Teilen wandern in „Wartet auf Teil“."""
    from .auftraege import status_setzen, verlauf
    b = bestellung(con, bid)
    if b["status"] != "entwurf":
        raise EingabeFehler("Die Bestellung ist bereits bestellt.")
    if erwartet_am:
        try:
            date.fromisoformat(erwartet_am)
        except ValueError:
            raise EingabeFehler("Bitte ein gültiges Lieferdatum angeben.")
    erwartet = erwartet_am or b["erwartet_am"]
    con.execute("UPDATE bestellungen SET status='bestellt', bestellt_am=?, erwartet_am=? WHERE id=?",
                (dbm.jetzt_berlin(), erwartet, bid))
    dbm.protokollieren("bestellung_bestellt", "bestellung", bid, {"nummer": b["nummer"]}, con=con)
    for p in positionen(con, bid):
        if not p["auftrag_id"]:
            continue
        a = con.execute("SELECT * FROM auftraege WHERE id=?", (p["auftrag_id"],)).fetchone()
        con.execute("UPDATE auftraege SET teil_info=?, teil_erwartet=? WHERE id=?",
                    (f"{p['bezeichnung']} ({b['nummer']}, {b['lieferant']})", erwartet, a["id"]))
        verlauf(con, a["id"], "Teil bestellt", f"{menge_text(p['menge'])} × {p['bezeichnung']} bei {b['lieferant']} "
                f"({b['nummer']})" + (f", erwartet {erwartet}" if erwartet else ""))
        if a["status"] != "erledigt" and not a["wartet_teil_seit"]:
            status_setzen(con, a["id"], "wartet_teil")


def bestellung_stornieren(con, bid, grund):
    b = bestellung(con, bid)
    if b["status"] in ("geliefert", "storniert") or con.execute("SELECT 1 FROM wareneingaenge WHERE bestellung_id=?",
                                                                (bid,)).fetchone():
        raise EingabeFehler("Bestellungen mit Wareneingang können nicht storniert werden.")
    if len((grund or "").strip()) < 3:
        raise EingabeFehler("Bitte einen Grund angeben.")
    con.execute("UPDATE bestellungen SET status='storniert', storno_grund=? WHERE id=?", (grund.strip(), bid))
    dbm.protokollieren("bestellung_storniert", "bestellung", bid, {"grund": grund}, con=con)


def wareneingang(con, bid, mengen, eks=None, lieferschein="", auftrag_fortsetzen=True):
    """Wareneingang buchen. mengen/eks: {position_id: Wert}. Gibt (anzahl, warnungen, auftraege) zurück.

    Muss in einer Transaktion laufen.
    """
    from . import lager
    from .auftraege import status_setzen, verlauf
    from .garantie import plus_monate
    b = bestellung(con, bid)
    if b["status"] not in ("bestellt", "teilweise", "entwurf"):
        raise EingabeFehler("Für diese Bestellung ist kein Wareneingang möglich.")
    eks = eks or {}
    anzahl, warnungen, auftraege = 0, [], set()
    for p in positionen(con, bid):
        try:
            menge = float(str(mengen.get(p["id"]) or "0").replace(",", "."))
        except ValueError:
            raise EingabeFehler("Bitte gültige Mengen angeben.")
        if menge <= 0:
            continue
        if menge > p["menge"] - p["geliefert"] + 1e-9:
            raise EingabeFehler(f"„{p['bezeichnung']}“: mehr geliefert als offen ({menge_text(p['menge'] - p['geliefert'])}).")
        ek = eks.get(p["id"], p["ek"])
        bewegung_id = None
        if p["artikel_id"] and p["lagerfuehrend"]:
            bewegung_id, _ = lager.bewegung_buchen(con, p["artikel_id"], "zugang", menge,
                                                   f"Wareneingang {b['nummer']} ({b['lieferant']})"
                                                   + (f", Lieferschein {lieferschein}" if lieferschein else ""), ek=ek)
        if p["artikel_id"] and ek is not None:
            con.execute("UPDATE artikel_lieferanten SET ek=?, geaendert_am=? WHERE artikel_id=? AND lieferant_id=?",
                        (ek, dbm.jetzt(), p["artikel_id"], b["lieferant_id"]))
            w = ek_aktualisieren(con, p["artikel_id"], ek, f"Wareneingang {b['nummer']}")
            if w:
                warnungen.append(w)
        q = con.execute("SELECT garantie_monate FROM artikel_lieferanten WHERE artikel_id=? AND lieferant_id=?",
                        (p["artikel_id"], b["lieferant_id"])).fetchone() if p["artikel_id"] else None
        garantie_bis = plus_monate(date.today(), q["garantie_monate"]).isoformat() \
            if q and q["garantie_monate"] else None
        con.execute("INSERT INTO wareneingaenge (bestellung_id, position_id, artikel_id, lieferant_id, menge, ek, "
                    "lieferschein, garantie_bis, bewegung_id, zeitpunkt, benutzer) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (bid, p["id"], p["artikel_id"], b["lieferant_id"], menge, ek, lieferschein or None, garantie_bis,
                     bewegung_id, dbm.jetzt_berlin(), dbm.aktueller_benutzer()))
        con.execute("UPDATE bestell_positionen SET geliefert=geliefert+? WHERE id=?", (menge, p["id"]))
        anzahl += 1
        if p["auftrag_id"]:
            auftraege.add(p["auftrag_id"])
            verlauf(con, p["auftrag_id"], "Ersatzteil eingetroffen",
                    f"{menge_text(menge)} × {p['bezeichnung']} ({b['nummer']})")
            if p["artikel_id"] and p["lagerfuehrend"]:  # gleich für den Auftrag reservieren
                if not con.execute("SELECT 1 FROM lager_reservierungen WHERE auftrag_id=? AND artikel_id=? "
                                   "AND status IN ('reserviert', 'ausgebucht')",
                                   (p["auftrag_id"], p["artikel_id"])).fetchone():
                    lager.reservieren(con, p["auftrag_id"], p["artikel_id"], menge, quelle=f"Bestellung {b['nummer']}")
    if not anzahl:
        raise EingabeFehler("Bitte bei mindestens einer Position eine gelieferte Menge eintragen.")
    rest = con.execute("SELECT COUNT(*) FROM bestell_positionen WHERE bestellung_id=? AND geliefert < menge - 1e-9",
                       (bid,)).fetchone()[0]
    con.execute("UPDATE bestellungen SET status=?, bestellt_am=COALESCE(bestellt_am, ?) WHERE id=?",
                ("teilweise" if rest else "geliefert", dbm.jetzt_berlin(), bid))
    dbm.protokollieren("wareneingang", "bestellung", bid, {"positionen": anzahl}, con=con)
    if auftrag_fortsetzen:
        for aid in auftraege:
            a = con.execute("SELECT * FROM auftraege WHERE id=?", (aid,)).fetchone()
            offen = con.execute("SELECT 1 FROM bestell_positionen p JOIN bestellungen b ON b.id=p.bestellung_id "
                                "WHERE p.auftrag_id=? AND p.geliefert < p.menge - 1e-9 AND b.status IN "
                                "('bestellt', 'teilweise')", (aid,)).fetchone()
            if a["wartet_teil_seit"] and not offen:
                status_setzen(con, aid, "in_arbeit")
    return anzahl, warnungen, sorted(auftraege)


def bestellungen(con, status=None, auftrag_id=None):
    sql = ("SELECT b.*, l.name AS lieferant, (SELECT COUNT(*) FROM bestell_positionen p WHERE p.bestellung_id=b.id) "
           "AS positionen, (SELECT SUM(p.menge * COALESCE(p.ek, 0)) FROM bestell_positionen p WHERE "
           "p.bestellung_id=b.id) AS summe FROM bestellungen b JOIN lieferanten l ON l.id=b.lieferant_id WHERE 1=1 ")
    args = []
    if status == "offen":
        sql += "AND b.status IN ('entwurf', 'bestellt', 'teilweise') "
    elif status:
        sql += "AND b.status=? "
        args.append(status)
    if auftrag_id:
        sql += "AND b.id IN (SELECT bestellung_id FROM bestell_positionen WHERE auftrag_id=?) "
        args.append(auftrag_id)
    return con.execute(sql + "ORDER BY b.id DESC LIMIT 300", args).fetchall()


def bestellung_pdf(con, bid, daten_dir):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    from .pdf import _farbe, _schrift_registrieren
    b = bestellung(con, bid)
    l = con.execute("SELECT * FROM lieferanten WHERE id=?", (b["lieferant_id"],)).fetchone()
    einst = dbm.einstellungen(con)
    f_norm, f_fett, _ = _schrift_registrieren(einst.get("schrift") or "Montserrat")
    st = ParagraphStyle("n", fontName=f_norm, fontSize=9.5, leading=13)
    st_f = ParagraphStyle("f", parent=st, fontName=f_fett)
    st_t = ParagraphStyle("t", fontName=f_fett, fontSize=15, leading=19, textColor=_farbe(einst.get("farbe_primaer")))
    puffer = io.BytesIO()
    doc = SimpleDocTemplate(puffer, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=20 * mm,
                            bottomMargin=18 * mm, title=f"Bestellung {b['nummer']}")
    absender = " · ".join(x for x in [einst.get("firma_name"), einst.get("strasse"),
                                      " ".join(x for x in [einst.get("plz"), einst.get("ort")] if x)] if x)
    an = "<br/>".join(x for x in [l["name"], l["ansprechpartner"], l["strasse"],
                                  " ".join(x for x in [l["plz"], l["ort"]] if x)] if x)
    inhalt = [Paragraph(absender, ParagraphStyle("k", parent=st, fontSize=7.5)), Spacer(1, 3 * mm), Paragraph(an, st),
              Spacer(1, 10 * mm), Paragraph(f"Bestellung {b['nummer']}", st_t),
              Paragraph(f"Datum: {date.today().strftime('%d.%m.%Y')}"
                        + (f" · Unsere Kundennummer bei Ihnen: {l['kundennr_bei']}" if l["kundennr_bei"] else ""), st),
              Spacer(1, 6 * mm), Paragraph("Wir bestellen hiermit:", st), Spacer(1, 3 * mm)]
    zeilen = [[Paragraph(x, st_f) for x in ["Pos.", "Ihre Art.-Nr.", "Bezeichnung", "Menge", "EK netto", "Summe"]]]
    summe = 0
    for i, p in enumerate(positionen(con, bid), 1):
        betrag = int(round(p["menge"] * (p["ek"] or 0)))
        summe += betrag
        zeilen.append([Paragraph(str(i), st), Paragraph(p["lieferanten_artnr"] or "", st), Paragraph(p["bezeichnung"], st),
                       Paragraph(menge_text(p["menge"]), st), Paragraph(euro(p["ek"]) if p["ek"] is not None else "", st),
                       Paragraph(euro(betrag) if p["ek"] is not None else "", st)])
    zeilen.append(["", "", Paragraph("Summe netto (laut Ihrer Preisliste)", st_f), "", "", Paragraph(euro(summe), st_f)])
    t = Table(zeilen, colWidths=[12 * mm, 30 * mm, 70 * mm, 16 * mm, 21 * mm, 21 * mm], repeatRows=1)
    t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.3, colors.HexColor("#D5D9DE")),
                           ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    inhalt += [t, Spacer(1, 6 * mm)]
    if b["notiz"]:
        inhalt.append(Paragraph(b["notiz"], st))
    inhalt += [Spacer(1, 6 * mm), Paragraph("Bitte bestätigen Sie die Bestellung und den Liefertermin.", st),
               Spacer(1, 4 * mm), Paragraph(f"Mit freundlichen Grüßen<br/>{einst.get('inhaber') or ''}<br/>"
                                            f"{einst.get('firma_name') or ''}", st)]
    doc.build(inhalt)
    return puffer.getvalue()


def lieferantengarantie(con, artikel_id, bis_datum=None):
    """Letzter Wareneingang eines Artikels (bis zum Datum) mit Lieferant und Garantie-Ende."""
    sql = ("SELECT w.*, l.name AS lieferant, b.nummer FROM wareneingaenge w JOIN lieferanten l ON l.id=w.lieferant_id "
           "JOIN bestellungen b ON b.id=w.bestellung_id WHERE w.artikel_id=? ")
    args = [artikel_id]
    if bis_datum:
        sql += "AND substr(w.zeitpunkt, 1, 10) <= ? "
        args.append(bis_datum[:10])
    return con.execute(sql + "ORDER BY w.id DESC LIMIT 1", args).fetchone()


# ---------------------------------------------------------------------- Eingangsrechnungen

ER_ENDUNGEN = {"pdf": "application/pdf", "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
               "xml": "application/xml"}


def datei_ablegen(daten_dir, daten, dateiname):
    """Originaldatei unverändert ablegen (Name = SHA-256). Gibt (relativer Pfad, sha256) zurück."""
    endung = (dateiname or "").rsplit(".", 1)[-1].lower() if "." in (dateiname or "") else ""
    if endung not in ER_ENDUNGEN:
        raise EingabeFehler("Bitte eine PDF-, Bild- oder XML-Datei hochladen.")
    if not daten:
        raise EingabeFehler("Die Datei ist leer.")
    sha = hashlib.sha256(daten).hexdigest()
    ordner = Path(daten_dir) / "belege" / "eingang" / sha[:2]
    ordner.mkdir(parents=True, exist_ok=True)
    pfad = ordner / f"{sha}.{endung}"
    if not pfad.exists():
        pfad.write_bytes(daten)
    return pfad.relative_to(Path(daten_dir)).as_posix(), sha


def _betraege(daten):
    from .hilfen import cent_aus_text
    netto = cent_aus_text(daten.get("netto"), None)
    steuer = cent_aus_text(daten.get("steuer"), None)
    brutto = cent_aus_text(daten.get("brutto"), None)
    satz = str(daten.get("steuersatz") or "").strip().replace(",", ".")
    satz = float(satz) if satz.replace(".", "", 1).isdigit() else None
    if steuer is None and satz is not None:  # Steuer aus dem Steuersatz berechnen
        if netto is not None and brutto is None:
            steuer = int(round(netto * satz / 100))
        elif brutto is not None and netto is None:
            netto = int(round(brutto * 100 / (100 + satz)))
            steuer = brutto - netto
    if brutto is None and netto is not None:
        brutto = netto + (steuer or 0)
    if netto is None and brutto is not None:
        netto = brutto - (steuer or 0)
    if steuer is None and brutto is not None and netto is not None:
        steuer = brutto - netto
    if brutto is None:
        raise EingabeFehler("Bitte mindestens den Bruttobetrag angeben.")
    if netto + steuer != brutto:
        raise EingabeFehler(f"Netto ({euro(netto)}) + Steuer ({euro(steuer)}) ergibt nicht Brutto ({euro(brutto)}).")
    return netto, steuer, brutto


def er_felder(daten):
    try:
        datum = date.fromisoformat(daten.get("datum") or "").isoformat()
    except ValueError:
        raise EingabeFehler("Bitte das Rechnungsdatum angeben.")
    faellig = daten.get("faellig_am") or None
    if faellig:
        try:
            date.fromisoformat(faellig)
        except ValueError:
            raise EingabeFehler("Bitte ein gültiges Fälligkeitsdatum angeben.")
    netto, steuer, brutto = _betraege(daten)
    satz = daten.get("steuersatz")
    lid = int(daten["lieferant_id"]) if str(daten.get("lieferant_id") or "").isdigit() else None
    if not lid and not (daten.get("lieferant_name") or "").strip():
        raise EingabeFehler("Bitte einen Lieferanten wählen oder den Namen eintragen.")
    return {"lieferant_id": lid, "lieferant_name": (daten.get("lieferant_name") or "").strip() or None,
            "nummer": (daten.get("nummer") or "").strip() or None, "datum": datum, "faellig_am": faellig,
            "netto": netto, "steuer": steuer, "brutto": brutto,
            "steuersatz": float(str(satz).replace(",", ".")) if str(satz or "").strip() else
            (round(steuer / netto * 100, 1) if netto else None),
            "kostenart": (daten.get("kostenart") or "").strip() or None,
            "bestellung_id": int(daten["bestellung_id"]) if str(daten.get("bestellung_id") or "").isdigit() else None,
            "beschreibung": (daten.get("beschreibung") or "").strip() or None}


def er_anlegen(con, felder, datei_rel=None, sha=None, datei_name=None, quelle="Upload", message_id=None,
               e_daten=None):
    """Eingangsrechnung erfassen. Muss in einer Transaktion laufen."""
    if felder["lieferant_id"] and felder["nummer"] and con.execute(
            "SELECT 1 FROM eingangsrechnungen WHERE lieferant_id=? AND nummer=? AND status<>'storniert'",
            (felder["lieferant_id"], felder["nummer"])).fetchone():
        raise EingabeFehler(f"Die Rechnung {felder['nummer']} dieses Lieferanten ist bereits erfasst.")
    if sha and con.execute("SELECT 1 FROM eingangsrechnungen WHERE datei_sha256=? AND status<>'storniert'",
                           (sha,)).fetchone():
        raise EingabeFehler("Diese Datei wurde bereits als Eingangsrechnung erfasst.")
    einst = dbm.einstellungen(con)
    lfd = _nummer(con, einst, "praefix_eingangsrechnung", "ER")
    if not felder["faellig_am"] and felder["lieferant_id"]:
        l = con.execute("SELECT zahlungsziel_tage FROM lieferanten WHERE id=?", (felder["lieferant_id"],)).fetchone()
        if l and l["zahlungsziel_tage"]:
            felder["faellig_am"] = (date.fromisoformat(felder["datum"]) +
                                    timedelta(days=l["zahlungsziel_tage"])).isoformat()
    cur = con.execute(
        f"INSERT INTO eingangsrechnungen ({', '.join(felder)}, lfd_nr, status, datei, datei_name, datei_sha256, quelle, "
        f"message_id, e_daten, erfasst_am, benutzer) VALUES ({', '.join('?' * len(felder))}, ?, 'offen', ?, ?, ?, ?, ?, "
        f"?, ?, ?)",
        (*felder.values(), lfd, datei_rel, datei_name, sha, quelle, message_id, e_daten, dbm.jetzt_berlin(),
         dbm.aktueller_benutzer()))
    dbm.protokollieren("eingangsrechnung_erfasst", "eingangsrechnung", cur.lastrowid,
                       {"lfd_nr": lfd, "brutto": felder["brutto"], "datei_sha256": sha}, con=con)
    dbm.aenderungen_erfassen(con, "eingangsrechnung", cur.lastrowid, None, felder, aktion="erfasst", namen=ER_NAMEN)
    return cur.lastrowid


def er_aendern(con, eid, felder):
    e = con.execute("SELECT * FROM eingangsrechnungen WHERE id=?", (eid,)).fetchone()
    if not e or e["status"] == "storniert":
        raise EingabeFehler("Stornierte Eingangsrechnungen können nicht geändert werden.")
    if e["exportiert_am"]:
        raise EingabeFehler("Die Rechnung wurde bereits an die Buchhaltung exportiert – bitte stornieren und neu erfassen.")
    con.execute(f"UPDATE eingangsrechnungen SET {', '.join(f'{k}=?' for k in felder)} WHERE id=?",
                (*felder.values(), eid))
    dbm.aenderungen_erfassen(con, "eingangsrechnung", eid, e, felder, namen=ER_NAMEN)
    _er_status(con, eid)


def er_stornieren(con, eid, grund):
    e = con.execute("SELECT * FROM eingangsrechnungen WHERE id=?", (eid,)).fetchone()
    if not e or e["status"] == "storniert":
        raise EingabeFehler("Die Eingangsrechnung ist bereits storniert.")
    if len((grund or "").strip()) < 3:
        raise EingabeFehler("Bitte einen Grund angeben.")
    if con.execute("SELECT 1 FROM er_zahlungen WHERE eingangsrechnung_id=? AND storniert_am IS NULL", (eid,)).fetchone():
        raise EingabeFehler("Bitte zuerst die Zahlungen zu dieser Rechnung stornieren.")
    con.execute("UPDATE eingangsrechnungen SET status='storniert', storniert_am=?, storno_grund=? WHERE id=?",
                (dbm.jetzt_berlin(), grund.strip(), eid))
    dbm.ereignis_erfassen(con, "eingangsrechnung", eid, "storniert", grund.strip())
    dbm.protokollieren("eingangsrechnung_storniert", "eingangsrechnung", eid, {"grund": grund}, con=con)


def er_bezahlt(con, eid):
    return con.execute("SELECT COALESCE(SUM(betrag), 0) FROM er_zahlungen WHERE eingangsrechnung_id=? "
                       "AND storniert_am IS NULL", (eid,)).fetchone()[0]


def _er_status(con, eid):
    e = con.execute("SELECT * FROM eingangsrechnungen WHERE id=?", (eid,)).fetchone()
    if e["status"] == "storniert":
        return
    neu = "bezahlt" if er_bezahlt(con, eid) >= e["brutto"] else "offen"
    if neu != e["status"]:
        con.execute("UPDATE eingangsrechnungen SET status=? WHERE id=?", (neu, eid))


def er_zahlung(con, eid, datum, betrag, zahlart, notiz="", bank_umsatz_id=None):
    e = con.execute("SELECT * FROM eingangsrechnungen WHERE id=?", (eid,)).fetchone()
    if not e or e["status"] == "storniert":
        raise EingabeFehler("Zu stornierten Rechnungen können keine Zahlungen erfasst werden.")
    if zahlart not in ZAHLARTEN:
        raise EingabeFehler("Bitte eine Zahlungsart wählen.")
    if not betrag or betrag <= 0:
        raise EingabeFehler("Bitte einen Betrag angeben.")
    try:
        date.fromisoformat(datum)
    except (TypeError, ValueError):
        raise EingabeFehler("Bitte ein gültiges Zahlungsdatum angeben.")
    cur = con.execute("INSERT INTO er_zahlungen (eingangsrechnung_id, datum, betrag, zahlart, notiz, bank_umsatz_id, "
                      "erfasst_am, benutzer) VALUES (?,?,?,?,?,?,?,?)",
                      (eid, datum, betrag, zahlart, notiz or None, bank_umsatz_id, dbm.jetzt_berlin(),
                       dbm.aktueller_benutzer()))
    _er_status(con, eid)
    dbm.ereignis_erfassen(con, "eingangsrechnung", eid, "Zahlung erfasst",
                          f"{euro(betrag)} am {datum} ({ZAHLARTEN[zahlart]})")
    if zahlart == "bar":  # bar bezahlt → Kassenbuch (Ausgabe)
        from .kasse import aus_er_zahlung
        aus_er_zahlung(con, cur.lastrowid)
    return cur.lastrowid


def er_zahlung_stornieren(con, zid, grund):
    z = con.execute("SELECT * FROM er_zahlungen WHERE id=?", (zid,)).fetchone()
    if not z or z["storniert_am"]:
        raise EingabeFehler("Zahlung nicht gefunden oder bereits storniert.")
    if len((grund or "").strip()) < 3:
        raise EingabeFehler("Bitte einen Grund angeben.")
    con.execute("UPDATE er_zahlungen SET storniert_am=?, storno_grund=? WHERE id=?",
                (dbm.jetzt_berlin(), grund.strip(), zid))
    if z["bank_umsatz_id"]:
        con.execute("UPDATE bank_umsaetze SET status='offen', er_zahlung_id=NULL, bearbeitet_am=?, bearbeitet_von=? "
                    "WHERE id=?", (dbm.jetzt_berlin(), dbm.aktueller_benutzer(), z["bank_umsatz_id"]))
    _er_status(con, z["eingangsrechnung_id"])
    if z["zahlart"] == "bar":
        from .kasse import zahlung_storniert
        zahlung_storniert(con, er_zahlung_id=zid, grund=f"Zahlung storniert: {grund.strip()}")
    dbm.ereignis_erfassen(con, "eingangsrechnung", z["eingangsrechnung_id"], "Zahlung storniert",
                          f"{euro(z['betrag'])} – {grund.strip()}")


ER_SQL = ("SELECT e.*, COALESCE(l.name, e.lieferant_name) AS lieferant, "
          "(SELECT COALESCE(SUM(z.betrag), 0) FROM er_zahlungen z WHERE z.eingangsrechnung_id=e.id "
          "AND z.storniert_am IS NULL) AS bezahlt FROM eingangsrechnungen e LEFT JOIN lieferanten l ON l.id=e.lieferant_id ")


def eingangsrechnungen(con, status=None, suche=""):
    sql, args = ER_SQL + "WHERE 1=1 ", []
    if status in ER_STATUS:
        sql += "AND e.status=? "
        args.append(status)
    if suche:
        sql += "AND (e.nummer LIKE ? OR e.lfd_nr LIKE ? OR COALESCE(l.name, e.lieferant_name) LIKE ? OR e.beschreibung LIKE ?) "
        args += [f"%{suche}%"] * 4
    return con.execute(sql + "ORDER BY e.datum DESC, e.id DESC LIMIT 500", args).fetchall()


def offene_er(con):
    return con.execute(ER_SQL + "WHERE e.status='offen' ORDER BY e.faellig_am, e.datum").fetchall()


# ---------------------------------------------------------------------- Bankabgleich (Ausgänge)

def bank_vorschlag(con, umsatz, offene=None):
    """Vorschlag für einen Ausgang: passende offene Eingangsrechnung (Nummer im Zweck, sonst Betrag + Name)."""
    if umsatz["betrag"] >= 0:
        return None
    from .bankabgleich import _normal, _nummer_muster
    offene = offene if offene is not None else offene_er(con)
    betrag = -umsatz["betrag"]
    zweck = f"{umsatz['verwendungszweck'] or ''}"
    for e in offene:
        muster = _nummer_muster(e["nummer"]) if e["nummer"] else None
        if muster and muster.search(zweck):
            return {"e": e, "sicher": betrag == e["brutto"] - e["bezahlt"], "grund": f"Rechnungsnummer {e['nummer']} "
                    "im Verwendungszweck"}
    name = _normal(umsatz["name"])
    passend = [e for e in offene if e["brutto"] - e["bezahlt"] == betrag]
    mit_name = [e for e in passend if name and e["lieferant"] and _normal(e["lieferant"]).split(" ")[0] in name]
    if len(mit_name) == 1:
        return {"e": mit_name[0], "sicher": False, "grund": "Betrag und Lieferant passen"}
    if len(passend) == 1:
        return {"e": passend[0], "sicher": False, "grund": "nur der Betrag passt – bitte prüfen"}
    return None


def bank_zuordnen(con, umsatz_id, eid):
    u = con.execute("SELECT * FROM bank_umsaetze WHERE id=?", (umsatz_id,)).fetchone()
    if not u or u["status"] != "offen" or u["betrag"] >= 0:
        raise EingabeFehler("Der Umsatz ist bereits bearbeitet oder kein Ausgang.")
    zid = er_zahlung(con, eid, min(u["buchungstag"], date.today().isoformat()), -u["betrag"], "ueberweisung",
                     f"Bank: {u['name'] or ''} – {(u['verwendungszweck'] or '')[:120]}".strip(), bank_umsatz_id=umsatz_id)
    con.execute("UPDATE bank_umsaetze SET status='zugeordnet', er_zahlung_id=?, bearbeitet_am=?, bearbeitet_von=? "
                "WHERE id=?", (zid, dbm.jetzt_berlin(), dbm.aktueller_benutzer(), umsatz_id))
    return zid


def summe_offen(con):
    return sum(e["brutto"] - e["bezahlt"] for e in offene_er(con))

