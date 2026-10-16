"""Geschäftslogik für Dokumente: Summen, Nummernvergabe, Festschreiben, Storno."""
import hashlib
import json
from datetime import date
from pathlib import Path

from . import db as dbm
from .hilfen import (EingabeFehler, anrede_brief, anschrift_zeilen, datum_de, euro, kunde_name,
                     platzhalter_ersetzen, sicherer_dateiname)

DOKUMENTTYPEN = {
    # typ: (Titel, Präfix-Einstellung)
    "rechnung": ("Rechnung", "praefix_rechnung"),
    "storno": ("Stornorechnung", "praefix_rechnung"),
    "kva": ("Kostenvoranschlag", "praefix_angebot"),
    "gutschrift": ("Gutschrift", "praefix_gutschrift"),  # Rechnungskorrektur zugunsten des Kunden, eigener Nummernkreis
}
RECHNUNGSARTIGE = ("rechnung", "storno", "gutschrift")  # Buchungsbelege mit voller Pflichtangaben-Prüfung

FIRMA_FELDER = ["firma_name", "firma_zusatz", "inhaber", "strasse", "plz", "ort", "land", "telefon", "email",
                "web", "steuernummer", "ust_idnr", "bank_name", "kontoinhaber", "iban", "bic"]
LAYOUT_FELDER = ["farbe_primaer", "farbe_sekundaer", "schrift", "schriftgroesse", "logo_datei", "logo_breite_mm",
                 "logo_position", "kopfzeile_text", "fusszeile_text", "faltmarken", "girocode"]


def titel(typ):
    return DOKUMENTTYPEN.get(typ, (typ.capitalize(), None))[0]


def zahlungsziel(einst, kunde):
    if kunde and kunde["zahlungsziel_tage"] is not None:
        return kunde["zahlungsziel_tage"]
    if kunde and kunde["typ"] == "firma":
        return int(einst["zahlungsziel_firma"])
    return int(einst["zahlungsziel_privat"])


def neuer_entwurf(con, einst, typ, kunde_id=None, betreff="", positionen=(), leistungsdatum=None):
    """Legt einen Dokument-Entwurf (Rechnung oder Kostenvoranschlag) an. Muss in einer Transaktion laufen.

    positionen: Zeilen aus der Tabelle positionen (z. B. vom Kostenvoranschlag), werden kopiert.
    """
    from .hilfen import heute, plus_tage

    kunde = con.execute("SELECT * FROM kunden WHERE id=?", (kunde_id,)).fetchone() if kunde_id else None
    texte = standard_texte(con, typ)
    tage = int(einst.get("kva_gueltig_tage") or 30) if typ == "kva" else zahlungsziel(einst, kunde)
    if typ == "kva":
        leistungsdatum = None
    cur = con.execute(
        "INSERT INTO dokumente (typ, kunde_id, datum, leistungsdatum, zahlungsziel_tage, faellig_am, betreff, "
        "einleitung, schlusstext, hinweise, steuer_modus, erstellt_am, geaendert_am) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (typ, kunde["id"] if kunde else None, heute(), leistungsdatum if typ == "kva" else (leistungsdatum or heute()),
         tage, plus_tage(heute(), tage), betreff, texte.get("einleitung", ""), texte.get("schluss", ""),
         texte.get("hinweis", ""), einst["steuer_modus"], dbm.jetzt(), dbm.jetzt()))
    did = cur.lastrowid
    for i, p in enumerate(positionen, 1):
        con.execute(
            "INSERT INTO positionen (dokument_id, pos, artikel_id, bezeichnung, beschreibung, menge, einheit, "
            "einzelpreis, teilekosten, steuersatz, leistungsart, garantie_monate) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (did, i, p["artikel_id"], p["bezeichnung"], p["beschreibung"], p["menge"], p["einheit"],
             abs(p["einzelpreis"]), abs(p["teilekosten"]), p["steuersatz"], p["leistungsart"],
             p["garantie_monate"] if "garantie_monate" in p.keys() else None))
    summen_speichern(con, did)
    dbm.protokollieren("entwurf_angelegt", "dokument", did, {"typ": typ}, con=con)
    return did


# ---------------------------------------------------------------- Summen / Steuer

def positions_betrag(menge, einzelpreis):
    return int(round(float(menge) * int(einzelpreis)))


def summen_berechnen(positionen, steuer_modus):
    """Berechnet Netto, Steuer je Steuersatz und Brutto (alles in Cent).

    Kleinunternehmer: keine Umsatzsteuer, der Positionsbetrag ist der Endbetrag.
    Regelbesteuerung: Preise sind Nettopreise, Steuer wird je Steuersatz aufaddiert.
    """
    netto = 0
    gruppen = {}
    for p in positionen:
        betrag = positions_betrag(p["menge"], p["einzelpreis"])
        netto += betrag
        if steuer_modus == "regel":
            satz = float(p["steuersatz"] or 0)
            gruppen[satz] = gruppen.get(satz, 0) + betrag
    steuer_gruppen = []
    steuer = 0
    for satz in sorted(gruppen):
        s = int(round(gruppen[satz] * satz / 100))
        steuer += s
        steuer_gruppen.append({"satz": satz, "netto": gruppen[satz], "steuer": s})
    return {"netto": netto, "steuer": steuer, "brutto": netto + steuer, "gruppen": steuer_gruppen}


def summen_speichern(con, dok_id):
    dok = con.execute("SELECT * FROM dokumente WHERE id=?", (dok_id,)).fetchone()
    pos = con.execute("SELECT * FROM positionen WHERE dokument_id=? ORDER BY pos", (dok_id,)).fetchall()
    s = summen_berechnen(pos, dok["steuer_modus"])
    con.execute("UPDATE dokumente SET summe_netto=?, summe_steuer=?, summe_brutto=? WHERE id=?",
                (s["netto"], s["steuer"], s["brutto"], dok_id))
    return s


# ---------------------------------------------------------------- Nummern

def nummer_formatieren(fmt, praefix, jahr, nummer):
    try:
        return fmt.format(praefix=praefix, jahr=jahr, nummer=nummer)
    except (KeyError, ValueError, IndexError):
        return f"{praefix}-{jahr}-{nummer:04d}"


def naechste_nummer(con, praefix, jahr, fmt, nur_vorschau=False):
    """Vergibt die nächste fortlaufende Nummer. Muss innerhalb einer Transaktion aufgerufen werden."""
    r = con.execute("SELECT letzte_nummer, format FROM nummernkreise WHERE praefix=? AND jahr=?",
                    (praefix, jahr)).fetchone()
    neu = (r["letzte_nummer"] if r else 0) + 1
    if r:
        fmt = r["format"]  # innerhalb eines Jahres bleibt das Format gleich
    if not nur_vorschau:
        if r:
            con.execute("UPDATE nummernkreise SET letzte_nummer=? WHERE praefix=? AND jahr=?", (neu, praefix, jahr))
        else:
            con.execute("INSERT INTO nummernkreise (praefix, jahr, letzte_nummer, format) VALUES (?,?,?,?)",
                        (praefix, jahr, neu, fmt))
    return nummer_formatieren(fmt, praefix, jahr, neu)


def naechste_kundennr(con, einst):
    praefix = einst.get("praefix_kunde") or "K"
    nr = 0
    for r in con.execute("SELECT kundennr FROM kunden WHERE kundennr LIKE ?", (praefix + "-%",)):
        try:
            nr = max(nr, int(r["kundennr"].rsplit("-", 1)[1]))
        except (ValueError, IndexError):
            pass
    return f"{praefix}-{nr + 1:04d}"


# ---------------------------------------------------------------- Platzhalter / Snapshot

def platzhalter_werte(dok, kunde, einst, nummer=None, bezug=None):
    dok = dict(dok)
    return {
        "anrede_brief": anrede_brief(kunde),
        "kunde_name": kunde_name(kunde),
        "kundennr": (dict(kunde).get("kundennr") if kunde else "") or "",
        "nummer": nummer or dok.get("nummer") or "(Entwurf)",
        "datum": datum_de(dok.get("datum")),
        "faellig_am": datum_de(dok.get("faellig_am")),
        "gueltig_bis": datum_de(dok.get("faellig_am")),
        "zahlungsziel_tage": dok.get("zahlungsziel_tage") or "",
        "betrag": euro(dok.get("summe_brutto")),
        "bezug_nummer": (bezug["nummer"] if bezug else "") or "",
        "bezug_datum": datum_de(bezug["datum"]) if bezug else "",
        "firma_name": einst.get("firma_name", ""),
        "inhaber": einst.get("inhaber", ""),
        "firma_telefon": einst.get("telefon", ""),
        "firma_web": einst.get("web", ""),
    }


def snapshot_bauen(con, dok_id, nummer=None):
    """Stellt alle Daten zusammen, die auf dem Dokument erscheinen. Wird beim Festschreiben eingefroren."""
    einst = dbm.einstellungen(con)
    dok = con.execute("SELECT * FROM dokumente WHERE id=?", (dok_id,)).fetchone()
    kunde = con.execute("SELECT * FROM kunden WHERE id=?", (dok["kunde_id"],)).fetchone() if dok["kunde_id"] else None
    bezug = con.execute("SELECT * FROM dokumente WHERE id=?", (dok["bezug_id"],)).fetchone() if dok["bezug_id"] else None
    pos = con.execute("SELECT * FROM positionen WHERE dokument_id=? ORDER BY pos", (dok_id,)).fetchall()
    s = summen_berechnen(pos, dok["steuer_modus"])
    werte = platzhalter_werte({**dict(dok), "summe_brutto": s["brutto"]}, kunde, einst, nummer, bezug)
    return {
        "version": 1,
        "typ": dok["typ"],
        "titel": titel(dok["typ"]),
        "nummer": nummer or dok["nummer"],
        "datum": dok["datum"],
        "leistungsdatum": dok["leistungsdatum"],
        "leistungsdatum_bis": dok["leistungsdatum_bis"],
        "faellig_am": dok["faellig_am"],
        "zahlungsziel_tage": dok["zahlungsziel_tage"],
        "betreff": platzhalter_ersetzen(dok["betreff"], werte),
        "einleitung": platzhalter_ersetzen(dok["einleitung"], werte),
        "schlusstext": platzhalter_ersetzen(dok["schlusstext"], werte),
        "hinweise": platzhalter_ersetzen(dok["hinweise"], werte),
        "steuer_modus": dok["steuer_modus"],
        "kleinunternehmer_hinweis": einst["kleinunternehmer_hinweis"] if dok["steuer_modus"] == "kleinunternehmer" else "",
        "zahlungsarten_text": einst["zahlungsarten_text"],
        "bezug": {"nummer": bezug["nummer"], "datum": bezug["datum"]} if bezug else None,
        "kunde": {
            "kundennr": kunde["kundennr"] if kunde else "",
            "name": kunde_name(kunde),
            "anschrift": anschrift_zeilen(kunde),
            "ust_idnr": (kunde["ust_idnr"] or "") if kunde else "",
            "typ": kunde["typ"] if kunde else "",
        },
        "firma": {k: einst.get(k, "") for k in FIRMA_FELDER},
        "layout": {k: einst.get(k) for k in LAYOUT_FELDER},
        "positionen": [
            {
                "pos": p["pos"], "bezeichnung": p["bezeichnung"], "beschreibung": p["beschreibung"] or "",
                "menge": p["menge"], "einheit": p["einheit"] or "", "einzelpreis": p["einzelpreis"],
                "steuersatz": p["steuersatz"], "betrag": positions_betrag(p["menge"], p["einzelpreis"]),
                "garantie_monate": p["garantie_monate"],
            }
            for p in pos
        ],
        "summen": s,
        "garantie_text": _garantie_text(con, dok),
    }


def _garantie_text(con, dok):
    if dok["typ"] != "rechnung":
        return ""
    from .garantie import rechnungstext
    return rechnungstext(con, dok)


# ---------------------------------------------------------------- Festschreiben

KLEINBETRAG_GRENZE = 25000  # § 33 UStDV: Rechnungen bis 250 € brutto (Kleinbetragsrechnung)


def pflichtangaben_pruefen(con, dok, einst=None):
    """Prüft die Pflichtangaben (§ 14 Abs. 4 UStG, § 33 UStDV). Gibt (fehler, hinweise) als Listen zurück.

    Fehler verhindern das Festschreiben, Hinweise nicht.
    """
    einst = einst or dbm.einstellungen(con)
    fehler, hinweise = [], []
    ist_beleg = dok["typ"] in RECHNUNGSARTIGE
    # Eigene Angaben
    if not (einst.get("inhaber") or "").strip():
        fehler.append("Ihr vollständiger Name (Inhaber) fehlt – Einstellungen → Firmendaten.")
    if not (einst.get("firma_name") or "").strip():
        hinweise.append("Kein Firmenname eingetragen (Einstellungen → Firmendaten).")
    if not all((einst.get(f) or "").strip() for f in ("strasse", "plz", "ort")):
        fehler.append("Ihre vollständige Anschrift (Straße, PLZ, Ort) fehlt – Einstellungen → Firmendaten.")
    if ist_beleg and not ((einst.get("steuernummer") or "").strip() or (einst.get("ust_idnr") or "").strip()):
        fehler.append("Steuernummer oder USt-IdNr. fehlt – Einstellungen → Firmendaten.")
    # Kunde
    kunde = con.execute("SELECT * FROM kunden WHERE id=?", (dok["kunde_id"],)).fetchone() if dok["kunde_id"] else None
    if not kunde:
        fehler.append("Kein Kunde ausgewählt.")
    else:
        if not kunde_name(kunde).strip():
            fehler.append("Name des Kunden fehlt.")
        if not all((kunde[f] or "").strip() for f in ("strasse", "plz", "ort")):
            brutto = abs(summen_berechnen(con.execute("SELECT * FROM positionen WHERE dokument_id=?",
                                                      (dok["id"],)).fetchall(), dok["steuer_modus"])["brutto"])
            if ist_beleg and brutto > KLEINBETRAG_GRENZE:
                fehler.append("Vollständige Anschrift des Kunden (Straße, PLZ, Ort) fehlt.")
            elif ist_beleg:
                hinweise.append("Anschrift des Kunden fehlt – bei Rechnungen bis 250 € brutto (Kleinbetragsrechnung, "
                                "§ 33 UStDV) nicht vorgeschrieben.")
    # Datum, Leistungszeitpunkt
    if not dok["datum"]:
        fehler.append("Rechnungsdatum fehlt.")
    if dok["typ"] in ("rechnung", "gutschrift") and not dok["leistungsdatum"]:
        fehler.append("Leistungsdatum bzw. Leistungszeitraum (Datum der Reparatur) fehlt.")
    # Positionen
    positionen = con.execute("SELECT * FROM positionen WHERE dokument_id=? ORDER BY pos", (dok["id"],)).fetchall()
    if not positionen:
        fehler.append("Das Dokument hat keine Positionen.")
    for p in positionen:
        if not (p["bezeichnung"] or "").strip():
            fehler.append(f"Position {p['pos']}: Bezeichnung fehlt.")
        if not p["menge"]:
            fehler.append(f"Position {p['pos']}: Menge fehlt.")
    # Steuer
    if dok["steuer_modus"] == "kleinunternehmer":
        if ist_beleg and not (einst.get("kleinunternehmer_hinweis") or "").strip():
            fehler.append("Hinweis auf die Kleinunternehmerregelung (§ 19 UStG) fehlt – Einstellungen → Rechnung & "
                          "Steuer.")
    elif ist_beleg:
        if any(p["steuersatz"] is None for p in positionen):
            fehler.append("Bei mindestens einer Position fehlt der Steuersatz.")
        if any(p["steuersatz"] == 0 for p in positionen):
            hinweise.append("Position mit 0 % Steuer: Bitte im Hinweistext den Grund der Steuerbefreiung angeben.")
    if dok["typ"] in ("rechnung", "gutschrift", "storno") and kunde:
        from .erechnung import format_fuer, stammdaten_pruefen
        fehler += stammdaten_pruefen(einst, kunde, format_fuer(kunde, dok["typ"]))
    return fehler, hinweise


def _pruefen_vor_festschreiben(con, dok, einst):
    if dok["status"] != "entwurf":
        raise EingabeFehler("Das Dokument ist bereits festgeschrieben.")
    if not dok["kunde_id"]:
        raise EingabeFehler("Bitte zuerst einen Kunden auswählen.")
    fehler, _ = pflichtangaben_pruefen(con, dok, einst)
    if fehler:
        raise EingabeFehler("Festschreiben nicht möglich – Pflichtangaben fehlen: " + " · ".join(fehler))
    if date.fromisoformat(dok["datum"]) > date.today():
        raise EingabeFehler("Das Rechnungsdatum darf nicht in der Zukunft liegen.")
    praefix = einst[DOKUMENTTYPEN[dok["typ"]][1]]
    letzte = con.execute(
        "SELECT MAX(datum) FROM dokumente WHERE status<>'entwurf' AND typ IN "
        f"({','.join('?' * len(_typen_mit_praefix(einst, praefix)))})",
        _typen_mit_praefix(einst, praefix),
    ).fetchone()[0]
    if letzte and dok["datum"] < letzte:
        raise EingabeFehler(
            f"Das Datum liegt vor dem letzten festgeschriebenen Dokument dieses Nummernkreises ({datum_de(letzte)}). "
            "Nummern und Datum müssen in derselben Reihenfolge laufen.")
    return praefix


def _typen_mit_praefix(einst, praefix):
    return [t for t, (_, key) in DOKUMENTTYPEN.items() if einst.get(key) == praefix]


def festschreiben(con, dok_id, daten_dir):
    """Vergibt die Nummer, friert den Inhalt ein, erzeugt und archiviert das PDF.

    Alles geschieht in einer Transaktion: Schlägt ein Schritt fehl, wird nichts gespeichert
    und auch keine Nummer verbraucht (lückenlose Nummernfolge).
    """
    from .pdf import pdf_erzeugen

    einst = dbm.einstellungen(con)
    with dbm.Transaktion(con):
        dok = con.execute("SELECT * FROM dokumente WHERE id=?", (dok_id,)).fetchone()
        if dok is None:
            raise EingabeFehler("Dokument nicht gefunden.")
        praefix = _pruefen_vor_festschreiben(con, dok, einst)
        jahr = int(dok["datum"][:4])
        nummer = naechste_nummer(con, praefix, jahr, einst["nummern_format"])
        summen_speichern(con, dok_id)
        snap = snapshot_bauen(con, dok_id, nummer)
        from . import erechnung
        kunde = con.execute("SELECT * FROM kunden WHERE id=?", (dok["kunde_id"],)).fetchone()
        e_format = erechnung.format_fuer(kunde, dok["typ"])
        snap["e_format"] = e_format
        pdf = pdf_erzeugen(snap, daten_dir=daten_dir, entwurf=False)
        pdf, xml = erechnung.erzeugen(snap, einst, kunde, e_format, pdf)
        sha = hashlib.sha256(pdf).hexdigest()
        rel = Path("dokumente") / str(jahr) / f"{sicherer_dateiname(nummer)}.pdf"
        ziel = Path(daten_dir) / rel
        ziel.parent.mkdir(parents=True, exist_ok=True)
        ziel.write_bytes(pdf)
        xml_rel = xml_sha = None
        if xml:
            xml_rel = rel.with_name(f"{sicherer_dateiname(nummer)}_{e_format}.xml")
            (Path(daten_dir) / xml_rel).write_bytes(xml)
            xml_sha = hashlib.sha256(xml).hexdigest()
            xml_rel = xml_rel.as_posix()
        # Rechnungsdaten (alle Inhalte, wie sie im PDF stehen) unverändert neben dem PDF archivieren
        daten = json.dumps(snap, ensure_ascii=False, sort_keys=True, indent=1).encode("utf-8")
        snap_sha = hashlib.sha256(daten).hexdigest()
        ziel.with_suffix(".json").write_bytes(daten)
        con.execute(
            "UPDATE dokumente SET status='festgeschrieben', nummer=?, snapshot_json=?, pdf_pfad=?, pdf_sha256=?, "
            "snapshot_sha256=?, festgeschrieben_am=?, geaendert_am=?, e_format=?, xml_pfad=?, xml_sha256=? WHERE id=?",
            (nummer, json.dumps(snap, ensure_ascii=False), rel.as_posix(), sha, snap_sha, dbm.jetzt_berlin(),
             dbm.jetzt(), e_format, xml_rel, xml_sha, dok_id),
        )
        dbm.ereignis_erfassen(con, "dokument", dok_id, "festgeschrieben",
                              f"Nummer {nummer}, Betrag {euro(snap['summen']['brutto'])}, PDF SHA-256 {sha}"
                              + (f", {erechnung.FORMATE[e_format]} (XML SHA-256 {xml_sha})" if xml else ""))
        con.execute("UPDATE kunden SET interessent=0 WHERE id=?", (dok["kunde_id"],))  # jetzt echter Kunde
        dbm.protokollieren("festgeschrieben", "dokument", dok_id,
                           {"nummer": nummer, "betrag": snap["summen"]["brutto"], "pdf_sha256": sha}, con=con)
    return nummer


def stornieren(con, dok_id, daten_dir, grund=""):
    """Erstellt eine Stornorechnung mit negativen Beträgen und schreibt sie sofort fest."""
    einst = dbm.einstellungen(con)
    orig = con.execute("SELECT * FROM dokumente WHERE id=?", (dok_id,)).fetchone()
    if orig is None or orig["status"] != "festgeschrieben" or orig["typ"] != "rechnung":
        raise EingabeFehler("Nur festgeschriebene, nicht stornierte Rechnungen können storniert werden.")
    texte = standard_texte(con, "storno")
    heute = date.today().isoformat()
    with dbm.Transaktion(con):
        cur = con.execute(
            "INSERT INTO dokumente (typ, kunde_id, datum, leistungsdatum, leistungsdatum_bis, betreff, einleitung, "
            "schlusstext, hinweise, steuer_modus, bezug_id, erstellt_am, geaendert_am) "
            "VALUES ('storno',?,?,?,?,?,?,?,?,?,?,?,?)",
            (orig["kunde_id"], heute, orig["leistungsdatum"], orig["leistungsdatum_bis"],
             f"Storno zu Rechnung {orig['nummer']}" + (f" – {grund}" if grund else ""),
             texte.get("einleitung", ""), texte.get("schluss", ""), "", orig["steuer_modus"], orig["id"],
             dbm.jetzt(), dbm.jetzt()),
        )
        neu_id = cur.lastrowid
        for p in con.execute("SELECT * FROM positionen WHERE dokument_id=? ORDER BY pos", (dok_id,)).fetchall():
            con.execute(
                "INSERT INTO positionen (dokument_id, pos, artikel_id, bezeichnung, beschreibung, menge, einheit, "
                "einzelpreis, teilekosten, steuersatz, leistungsart) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (neu_id, p["pos"], p["artikel_id"], p["bezeichnung"], p["beschreibung"], p["menge"], p["einheit"],
                 -p["einzelpreis"], -p["teilekosten"], p["steuersatz"], p["leistungsart"]),
            )
        summen_speichern(con, neu_id)
        dbm.protokollieren("storno_angelegt", "dokument", neu_id, {"zu": orig["nummer"], "grund": grund}, con=con)
    try:
        nummer = festschreiben(con, neu_id, daten_dir)
    except Exception:
        # Entwurf wieder entfernen, damit nichts Halbfertiges liegen bleibt
        with dbm.Transaktion(con):
            con.execute("DELETE FROM positionen WHERE dokument_id=?", (neu_id,))
            con.execute("DELETE FROM dokumente WHERE id=?", (neu_id,))
        raise
    with dbm.Transaktion(con):
        con.execute("UPDATE dokumente SET status='storniert', storniert_durch=?, geaendert_am=? WHERE id=?",
                    (neu_id, dbm.jetzt(), dok_id))
        dbm.protokollieren("storniert", "dokument", dok_id, {"durch": nummer}, con=con)
        dbm.ereignis_erfassen(con, "dokument", dok_id, "storniert", f"durch Stornorechnung {nummer}"
                              + (f" – Grund: {grund}" if grund else ""))
        from .lager import rechnung_storniert
        rechnung_storniert(con, dok_id)  # ausgebuchtes Material des Auftrags wieder einbuchen
    return neu_id, nummer


def gutschrift_entwurf(con, dok_id):
    """Gutschrift-Entwurf (eigener Nummernkreis) zu einer festgeschriebenen Rechnung, Positionen vorbelegt."""
    orig = con.execute("SELECT * FROM dokumente WHERE id=?", (dok_id,)).fetchone()
    if orig is None or orig["typ"] != "rechnung" or orig["status"] == "entwurf":
        raise EingabeFehler("Eine Gutschrift kann nur zu einer festgeschriebenen Rechnung erstellt werden.")
    einst = dbm.einstellungen(con)
    positionen = [dict(p, einzelpreis=-abs(p["einzelpreis"]), teilekosten=0)
                  for p in con.execute("SELECT * FROM positionen WHERE dokument_id=? ORDER BY pos", (dok_id,))]
    did = neuer_entwurf(con, einst, "gutschrift", orig["kunde_id"], f"Gutschrift zu Rechnung {orig['nummer']}",
                        leistungsdatum=orig["leistungsdatum"])
    for i, p in enumerate(positionen, 1):  # negative Beträge (neuer_entwurf übernimmt nur Beträge > 0)
        con.execute("INSERT INTO positionen (dokument_id, pos, artikel_id, bezeichnung, beschreibung, menge, einheit, "
                    "einzelpreis, teilekosten, steuersatz, leistungsart) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (did, i, p["artikel_id"], p["bezeichnung"], p["beschreibung"], p["menge"], p["einheit"],
                     p["einzelpreis"], 0, p["steuersatz"], p["leistungsart"]))
    con.execute("UPDATE dokumente SET bezug_id=?, leistungsdatum_bis=? WHERE id=?",
                (dok_id, orig["leistungsdatum_bis"], did))
    summen_speichern(con, did)
    dbm.protokollieren("gutschrift_angelegt", "dokument", did, {"zu": orig["nummer"]}, con=con)
    return did


# ---------------------------------------------------------------- Aufbewahrung

def aufbewahren_bis(dok, einst):
    """Ende der Aufbewahrungsfrist: Schluss des Kalenderjahres des Belegs + Frist (§ 147 Abs. 4 AO)."""
    if not dok["datum"] or dok["status"] == "entwurf":
        return None
    jahre = int(einst.get("aufbewahrung_belege_jahre") or 8) if dok["typ"] in RECHNUNGSARTIGE \
        else int(einst.get("aufbewahrung_briefe_jahre") or 6)
    return f"{int(dok['datum'][:4]) + jahre}-12-31"


def standard_texte(con, dokumenttyp):
    """Liefert die als Standard markierten Textbausteine je Kategorie für einen Dokumenttyp."""
    texte = {}
    for r in con.execute(
            "SELECT * FROM textbausteine WHERE standard=1 AND dokumenttyp IN (?, 'alle') "
            "ORDER BY CASE dokumenttyp WHEN 'alle' THEN 1 ELSE 0 END, id", (dokumenttyp,)):
        texte.setdefault(r["kategorie"], r["text"])
    return texte


# ---------------------------------------------------------------- Prüfung

DATEIPFADE = [  # (Tabelle, Spalte, Bezeichnung, Bedingung, Datei hier prüfen – sonst schon oben mit Prüfsumme)
    ("dokumente", "pdf_pfad", "Beleg-PDF", "pdf_pfad IS NOT NULL", False),
    ("dokumente", "xml_pfad", "E-Rechnungs-XML", "xml_pfad IS NOT NULL", False),
    ("mahnungen", "pdf_pfad", "Mahnungs-PDF", "1=1", False),
    ("auftrag_fotos", "pfad", "Foto", "geloescht_am IS NULL", True),
    ("auftrag_belege", "pdf_datei", "Annahme-/Abholschein", "1=1", False),
    ("inventuren", "pdf_datei", "Inventurprotokoll", "pdf_datei IS NOT NULL", False),
    ("eingangsrechnungen", "datei", "Eingangsrechnung", "datei IS NOT NULL", False),
    ("kassenbuch", "beleg_datei", "Kassenbeleg", "beleg_datei IS NOT NULL", True),
    ("datev_exporte", "datei", "DATEV-Export", "datei IS NOT NULL", True),
    ("fixkosten", "datei", "Fixkosten-Vertrag", "datei IS NOT NULL", True),
]


def pfad_problem(rel):
    """Warum ein gespeicherter Pfad nicht plattformunabhängig ist (sonst None)."""
    if not rel:
        return None
    if "\\" in rel:
        return "enthält Backslashes (nur unter Windows lesbar)"
    if rel.startswith("/") or (len(rel) > 1 and rel[1] == ":"):
        return "ist absolut statt relativ zum Datenordner"
    if ".." in rel.split("/"):
        return "verweist aus dem Datenordner heraus"
    return None


def dateipfade_pruefen(con, daten_dir):
    """Alle gespeicherten Dateipfade: relativ zum Datenordner, mit „/“, und die Datei ist vorhanden."""
    fehler = []
    tabellen = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    for tabelle, spalte, text, bedingung, vorhanden in DATEIPFADE:
        if tabelle not in tabellen:
            continue
        for (rel,) in con.execute(f"SELECT {spalte} FROM {tabelle} WHERE {bedingung}"):
            problem = pfad_problem(rel)
            if problem:
                fehler.append(f"{text} {rel}: Pfad {problem}.")
            elif rel and vorhanden and not (Path(daten_dir) / rel).is_file():
                fehler.append(f"{text} {rel}: Datei fehlt im Datenordner.")
    logo = dbm.einstellungen(con).get("logo_datei")
    if logo and pfad_problem(logo):
        fehler.append(f"Logo {logo}: Pfad {pfad_problem(logo)}.")
    return fehler


def integritaet_pruefen(con, daten_dir):
    """Prüft PDF-Prüfsummen, Lückenlosigkeit der Nummern und die Protokollkette."""
    ergebnisse = {"pdf": [], "nummern": [], "protokoll": dbm.protokoll_pruefen(con), "anzahl_dokumente": 0}
    for d in con.execute("SELECT id, nummer, pdf_pfad, pdf_sha256, snapshot_sha256, xml_pfad, xml_sha256 "
                         "FROM dokumente WHERE status<>'entwurf'"):
        if d["xml_pfad"]:
            x = Path(daten_dir) / d["xml_pfad"]
            if not x.is_file() or hashlib.sha256(x.read_bytes()).hexdigest() != d["xml_sha256"]:
                ergebnisse["pdf"].append(f"{d['nummer']}: E-Rechnungs-XML fehlt oder wurde verändert.")
        ergebnisse["anzahl_dokumente"] += 1
        pfad = Path(daten_dir) / (d["pdf_pfad"] or "")
        if not d["pdf_pfad"] or not pfad.is_file():
            ergebnisse["pdf"].append(f"{d['nummer']}: PDF-Datei fehlt.")
        elif hashlib.sha256(pfad.read_bytes()).hexdigest() != d["pdf_sha256"]:
            ergebnisse["pdf"].append(f"{d['nummer']}: PDF-Datei wurde verändert (Prüfsumme stimmt nicht).")
        if d["snapshot_sha256"]:  # archivierte Rechnungsdaten (ab Version 0.11)
            json_pfad = pfad.with_suffix(".json")
            if not json_pfad.is_file():
                ergebnisse["pdf"].append(f"{d['nummer']}: archivierte Rechnungsdaten (JSON) fehlen.")
            elif hashlib.sha256(json_pfad.read_bytes()).hexdigest() != d["snapshot_sha256"]:
                ergebnisse["pdf"].append(f"{d['nummer']}: archivierte Rechnungsdaten wurden verändert.")
    for m in con.execute("SELECT nummer, pdf_pfad, pdf_sha256, snapshot_sha256 FROM mahnungen"):
        pfad = Path(daten_dir) / m["pdf_pfad"]
        if not pfad.is_file():
            ergebnisse["pdf"].append(f"{m['nummer']}: PDF der Mahnung fehlt.")
        elif hashlib.sha256(pfad.read_bytes()).hexdigest() != m["pdf_sha256"]:
            ergebnisse["pdf"].append(f"{m['nummer']}: PDF der Mahnung wurde verändert.")
        elif not pfad.with_suffix(".json").is_file() or \
                hashlib.sha256(pfad.with_suffix(".json").read_bytes()).hexdigest() != m["snapshot_sha256"]:
            ergebnisse["pdf"].append(f"{m['nummer']}: archivierte Daten der Mahnung fehlen oder wurden verändert.")
    for tabelle, spalte, text in (("auftrag_belege", "nummer", "Annahme-/Abholschein"),
                                  ("inventuren", "stichtag", "Inventurprotokoll")):
        for b in con.execute(f"SELECT {spalte} AS nummer, pdf_datei, pdf_sha256 FROM {tabelle} "
                             "WHERE pdf_datei IS NOT NULL"):
            pfad = Path(daten_dir) / b["pdf_datei"]
            if not pfad.is_file():
                ergebnisse["pdf"].append(f"{text} {b['nummer']}: PDF fehlt.")
            elif hashlib.sha256(pfad.read_bytes()).hexdigest() != b["pdf_sha256"]:
                ergebnisse["pdf"].append(f"{text} {b['nummer']}: PDF wurde verändert.")
    for e in con.execute("SELECT lfd_nr, datei, datei_sha256 FROM eingangsrechnungen WHERE datei IS NOT NULL"):
        pfad = Path(daten_dir) / e["datei"]
        if not pfad.is_file():
            ergebnisse["pdf"].append(f"Eingangsrechnung {e['lfd_nr']}: Originaldatei fehlt.")
        elif hashlib.sha256(pfad.read_bytes()).hexdigest() != e["datei_sha256"]:
            ergebnisse["pdf"].append(f"Eingangsrechnung {e['lfd_nr']}: Originaldatei wurde verändert.")
    ergebnisse["pfade"] = dateipfade_pruefen(con, daten_dir)
    from .lager import integritaet as lager_integritaet
    ergebnisse["lager"] = lager_integritaet(con)
    from .kasse import integritaet as kasse_integritaet
    ergebnisse["lager"] += kasse_integritaet(con)
    vergeben = {r["nummer"] for r in con.execute("SELECT nummer FROM dokumente WHERE nummer IS NOT NULL")}
    vergeben |= {r["nummer"] for r in con.execute("SELECT nummer FROM mahnungen")}
    vergeben |= {r["nummer"] for r in con.execute("SELECT nummer FROM bestellungen")}
    vergeben |= {r["nummer"] for r in con.execute("SELECT lfd_nr AS nummer FROM eingangsrechnungen")}
    for k in con.execute("SELECT * FROM nummernkreise ORDER BY praefix, jahr"):
        for n in range(1, k["letzte_nummer"] + 1):
            nr = nummer_formatieren(k["format"], k["praefix"], k["jahr"], n)
            if nr not in vergeben:
                ergebnisse["nummern"].append(f"Nummer {nr} wurde vergeben, das Dokument fehlt.")
    return ergebnisse
