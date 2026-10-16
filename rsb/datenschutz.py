"""Datenschutz (DSGVO): Löschfristen, automatische Löschläufe, Auskunft nach Art. 15, Löschprotokolle und das
Verzeichnis der Verarbeitungstätigkeiten (Art. 30) aus den tatsächlich gespeicherten Daten.

Aufbewahrungspflichten (GoBD/HGB/AO, siehe aufbewahrung.py) haben Vorrang: Wer noch aufbewahrungspflichtige Belege
hat, wird anonymisiert statt gelöscht. Jeder Lauf und jede Löschanfrage wird protokolliert (was gelöscht, was
behalten und bis wann).
"""
import io
import json
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path

from . import db as dbm
from .hilfen import EingabeFehler, datum_de, kunde_name

FRISTEN = {  # Einstellung: (Standard, Text)
    "interessent_loeschen_monate": (6, "Interessenten ohne Auftrag: Monate nach Anlage bzw. letztem Kontakt"),
    "ds_kunde_inaktiv_jahre": (3, "Inaktive Kunden: Jahre ab Ende des Kalenderjahres des letzten Kontakts"),
    "ds_fotos_jahre": (3, "Fotos und Annahme-/Abholscheine: Jahre ab Ende des Kalenderjahres der Abholung"),
    "ds_leihe_jahre": (3, "Leihprotokolle und -fotos: Jahre ab Ende des Kalenderjahres der Rückgabe bzw. des "
                          "Abschlusses eines Schadensfalls"),
    "ds_zugang_tage": (90, "Gerätezugangsdaten liegengebliebener Aufträge: Tage nach Eingang (bei Abholung bzw. "
                           "Abschluss werden sie sofort gelöscht)"),
    "ds_email_jahre": (6, "E-Mail-Verlauf ohne Belegbezug (Jahre)"),
}
ARTEN = {"interessent": "Interessent", "kunde": "Inaktiver Kunde", "auftrag": "Fotos und Annahme-/Abholscheine",
         "leihe": "Leihprotokoll und -fotos", "zugang": "Gerätezugangsdaten"}


def einstellungs_standard():
    werte = {k: v[0] for k, v in FRISTEN.items() if k != "interessent_loeschen_monate"}  # gibt es schon
    werte["ds_vorschau_tage"] = 30     # Vorschau „wird in den nächsten … Tagen gelöscht“
    werte["ds_auto"] = False           # Löschlauf automatisch einmal täglich
    werte["ds_letzter_lauf"] = ""
    werte["ds_verantwortlicher"] = ""  # für das Verzeichnis (Name, Anschrift, Kontakt)
    return werte


def _frist(einst, schluessel):
    try:
        return max(0, int(einst.get(schluessel) if einst.get(schluessel) is not None else FRISTEN[schluessel][0]))
    except (TypeError, ValueError):
        return FRISTEN[schluessel][0]


def _tag(iso):
    try:
        return date.fromisoformat((iso or "")[:10])
    except ValueError:
        return None


def ab_jahresende(tag, jahre):
    """Fristbeginn am Ende des Kalenderjahres: Abholung 15.10.2026, 3 Jahre → Löschung ab 01.01.2030."""
    return date(tag.year + jahre + 1, 1, 1)


def _letzte_aktivitaet(con, kid):
    werte = [r[0] for r in con.execute(
        "SELECT MAX(x) FROM (SELECT geaendert_am AS x FROM kunden WHERE id=:k "
        "UNION ALL SELECT MAX(datum) FROM dokumente WHERE kunde_id=:k "
        "UNION ALL SELECT MAX(COALESCE(abgeholt_am, erledigt_am, eingang_am)) FROM auftraege WHERE kunde_id=:k "
        "UNION ALL SELECT MAX(eingang_am) FROM anfragen WHERE kunde_id=:k "
        "UNION ALL SELECT MAX(COALESCE(rueckgabe_am, ausgabe_am)) FROM leihen WHERE kunde_id=:k "
        "UNION ALL SELECT MAX(n.datum) FROM email_nachrichten n JOIN email_kunden e ON e.nachricht_id=n.id "
        "WHERE e.kunde_id=:k)", {"k": kid})]
    return (werte[0] or "")[:10]


def schadensfall_abgeschlossen(con, sf):
    """Abschlussdatum eines Schadensfalls (storniert, Rechnung bezahlt oder mit der Kaution verrechnet) – sonst None."""
    if sf["storniert_am"]:
        return _tag(sf["storniert_am"])
    if sf["rechnung_id"]:
        r = con.execute("SELECT * FROM dokumente WHERE id=?", (sf["rechnung_id"],)).fetchone()
        if r and r["status"] == "festgeschrieben" and r["bezahlt_betrag"] >= r["summe_brutto"]:
            z = con.execute("SELECT MAX(datum) FROM zahlungen WHERE dokument_id=? AND storniert_am IS NULL",
                            (r["id"],)).fetchone()[0]
            return _tag(z or r["datum"])
        return None
    le = con.execute("SELECT * FROM leihen WHERE id=?", (sf["leihe_id"],)).fetchone()
    if le and le["kaution_status"] in ("verrechnet", "zurueckgezahlt") and le["kaution_erledigt_am"]:
        from .leihgeraete import kaution_verrechnung
        if not kaution_verrechnung(con, le)["nachzahlung"]:
            return _tag(le["kaution_erledigt_am"])
    return None


def sperren(con, kid, heute):
    """Was die Löschung eines Kunden (und seiner Fotos/Scheine) derzeit verhindert."""
    gruende = []
    if con.execute("SELECT 1 FROM auftraege WHERE kunde_id=? AND (status<>'erledigt' OR abgeholt_am IS NULL)",
                   (kid,)).fetchone():
        gruende.append("laufender Auftrag")
    if con.execute("SELECT 1 FROM dokumente WHERE kunde_id=? AND typ='rechnung' AND status='festgeschrieben' "
                   "AND summe_brutto > bezahlt_betrag", (kid,)).fetchone():
        gruende.append("offene Rechnung")
    for sf in con.execute("SELECT s.* FROM schadensfaelle s JOIN leihen l ON l.id=s.leihe_id WHERE l.kunde_id=?",
                          (kid,)).fetchall():
        if not schadensfall_abgeschlossen(con, sf):
            gruende.append("offener Schadensfall")
            break
    if con.execute("SELECT 1 FROM auftraege WHERE kunde_id=? AND garantie_ende >= ?", (kid, heute.isoformat())).fetchone():
        gruende.append("laufende Garantie")
    if con.execute("SELECT 1 FROM vertraege WHERE kunde_id=? AND (status='aktiv' OR ende >= ?)",
                   (kid, heute.isoformat())).fetchone():
        gruende.append("laufender Vertrag")
    return gruende


def zurueckgestellt(con, art, objekt_id, heute):
    return con.execute("SELECT * FROM loesch_zurueckstellungen WHERE art=? AND objekt_id=? AND aufgehoben_am IS NULL "
                       "AND (bis IS NULL OR bis >= ?) ORDER BY id DESC LIMIT 1",
                       (art, objekt_id, heute.isoformat())).fetchone()


def kandidaten(con, heute=None, tage=None):
    """Einträge, deren Löschfrist bis heute + tage abläuft (Vorschau) – mit Sperre bzw. Zurückstellung.

    Jeder Eintrag: art, id, titel, faellig (Datum), frist (Text), sperre (Gründe), zurueck (Zurückstellung).
    """
    from .garantie import plus_monate
    from .leihgeraete import ist_intern
    heute = heute or date.today()
    einst = dbm.einstellungen(con)
    tage = int(einst.get("ds_vorschau_tage") or 30) if tage is None else tage
    grenze = heute + timedelta(days=tage)
    eintraege = []
    gesperrt = {}

    def sperre(kid):
        if kid not in gesperrt:
            gesperrt[kid] = sperren(con, kid, heute)
        return gesperrt[kid]

    def neu(art, oid, titel, faellig, frist, kid=None, extra=None):
        if faellig and faellig <= grenze:
            eintraege.append({"art": art, "art_text": ARTEN[art], "id": oid, "titel": titel, "faellig": faellig,
                              "frist": frist, "sperre": (sperre(kid) if kid else []) + (extra or []),
                              "zurueck": zurueckgestellt(con, art, oid, heute)})

    m = _frist(einst, "interessent_loeschen_monate")
    if m:
        for k in con.execute("SELECT * FROM kunden k WHERE interessent=1 AND anonymisiert_am IS NULL "
                             "AND NOT EXISTS (SELECT 1 FROM dokumente d WHERE d.kunde_id=k.id) "
                             "AND NOT EXISTS (SELECT 1 FROM auftraege a WHERE a.kunde_id=k.id) "
                             "AND NOT EXISTS (SELECT 1 FROM vertraege v WHERE v.kunde_id=k.id)").fetchall():
            letzter = max([(x or "")[:10] for x in (k["erstellt_am"], k["geaendert_am"], con.execute(
                "SELECT MAX(eingang_am) FROM anfragen WHERE kunde_id=?", (k["id"],)).fetchone()[0])])
            if not letzter:
                continue
            neu("interessent", k["id"], kurzname(k), plus_monate(_tag(letzter), m),
                f"{m} Monate nach letztem Kontakt ({datum_de(letzter)})", k["id"])
    jahre = _frist(einst, "ds_kunde_inaktiv_jahre")
    if jahre:
        for k in con.execute("SELECT * FROM kunden WHERE anonymisiert_am IS NULL AND interessent=0").fetchall():
            if ist_intern(con, k["id"]):
                continue
            letzte = _letzte_aktivitaet(con, k["id"])
            if letzte:
                neu("kunde", k["id"], kurzname(k), ab_jahresende(_tag(letzte), jahre),
                    f"{jahre} Jahre ab Ende {letzte[:4]} (letzter Kontakt {datum_de(letzte)})", k["id"])
    jahre = _frist(einst, "ds_fotos_jahre")
    if jahre:
        for a in con.execute(
                "SELECT a.*, (SELECT COUNT(*) FROM auftrag_fotos f WHERE f.auftrag_id=a.id AND f.geloescht_am IS NULL "
                "AND f.leihe_id IS NULL AND f.schadensfall_id IS NULL) AS fotos, (SELECT COUNT(*) FROM auftrag_belege b "
                "WHERE b.auftrag_id=a.id) AS belege FROM auftraege a WHERE a.abgeholt_am IS NOT NULL").fetchall():
            if not a["fotos"] and not a["belege"]:
                continue
            extra = ["Garantiefall offen"] if con.execute(
                "SELECT 1 FROM auftraege WHERE garantie_bezug_id=? AND (status<>'erledigt' OR abgeholt_am IS NULL)",
                (a["id"],)).fetchone() else []
            neu("auftrag", a["id"], f"{a['auftragsnr']}: {a['fotos']} Foto(s), {a['belege']} Schein(e)",
                ab_jahresende(_tag(a["abgeholt_am"]), jahre),
                f"{jahre} Jahre ab Ende {a['abgeholt_am'][:4]} (Abholung {datum_de(a['abgeholt_am'][:10])})",
                a["kunde_id"], extra)
    jahre = _frist(einst, "ds_leihe_jahre")
    if jahre:
        for le in con.execute("SELECT l.*, g.bezeichnung FROM leihen l JOIN leihgeraete g ON g.id=l.geraet_id "
                              "WHERE l.rueckgabe_am IS NOT NULL AND l.protokoll_geloescht_am IS NULL").fetchall():
            basis, extra = _tag(le["rueckgabe_am"]), []
            for sf in con.execute("SELECT * FROM schadensfaelle WHERE leihe_id=?", (le["id"],)).fetchall():
                abschluss = schadensfall_abgeschlossen(con, sf)
                if not abschluss:
                    extra = ["offener Schadensfall"]
                elif abschluss > basis:
                    basis = abschluss
            neu("leihe", le["id"], f"{le['leihnr']} ({le['bezeichnung']})", ab_jahresende(basis, jahre),
                f"{jahre} Jahre ab Ende {basis.year} (" + ("Abschluss Schadensfall" if basis != _tag(le["rueckgabe_am"])
                                                           else "Rückgabe") + f" {datum_de(basis.isoformat())})",
                None, extra)
    tage_zugang = _frist(einst, "ds_zugang_tage")
    if tage_zugang:
        for a in con.execute("SELECT id, auftragsnr, eingang_am FROM auftraege WHERE zugang_geheim IS NOT NULL"):
            neu("zugang", a["id"], a["auftragsnr"], _tag(a["eingang_am"]) + timedelta(days=tage_zugang),
                f"{tage_zugang} Tage nach Eingang")
    eintraege.sort(key=lambda e: (e["faellig"], e["art"]))
    emails = 0
    jahre = _frist(einst, "ds_email_jahre")
    if jahre:  # unverändert: E-Mail-Verlauf ohne Belegbezug
        emails = con.execute("SELECT COUNT(*) FROM email_nachrichten WHERE dokument_id IS NULL AND datum < ?",
                             ((heute - timedelta(days=365 * jahre)).isoformat(),)).fetchone()[0]
    return {"eintraege": eintraege, "emails": emails, "heute": heute, "grenze": grenze}


def _protokoll(con, anlass, betroffen, geloescht, behalten, bis=None, frist=None):
    cur = con.execute("INSERT INTO loeschprotokolle (zeitpunkt, benutzer, anlass, betroffen, geloescht, behalten, bis, "
                      "frist) VALUES (?,?,?,?,?,?,?,?)",
                      (dbm.jetzt_berlin(), dbm.aktueller_benutzer(), anlass, betroffen,
                       json.dumps(geloescht, ensure_ascii=False), json.dumps(behalten, ensure_ascii=False), bis, frist))
    return cur.lastrowid


def kurzname(k):
    """Für das Protokoll: Kundennummer und gekürzter Name (z. B. „A. Müller“)."""
    if k["typ"] == "firma" and k["firma"]:
        return f"{k['kundennr']} {k['firma']}"
    return f"{k['kundennr']} {(k['vorname'] or '')[:1] + '. ' if k['vorname'] else ''}{k['nachname'] or ''}".strip()


def kunde_loeschen(con, kid, anlass="manuell", frist=None):
    """Löschen/Anonymisieren eines Kunden mit Protokoll. Muss in einer Transaktion laufen. Gibt (bericht, prot_id)."""
    from .aufbewahrung import kunde_loeschen as loeschen
    k = con.execute("SELECT * FROM kunden WHERE id=?", (kid,)).fetchone()
    name = kurzname(k)
    bericht = loeschen(con, kid)
    geloescht = list(bericht["loeschen"]) + (["Stammdaten (Name, Anschrift, Kontakt, Notizen)"]
                                             if bericht["anonymisieren"] else ["Kunde mit allen Daten"])
    pid = _protokoll(con, anlass, name, geloescht, bericht["behalten"], bericht["bis"], frist)
    return bericht, pid


def _foto_loeschen(con, daten_dir, f, grund):
    from .fotos import vorschau_pfad
    con.execute("UPDATE auftrag_fotos SET geloescht_am=?, geloescht_von=?, loeschgrund=? WHERE id=?",
                (dbm.jetzt_berlin(), "Löschfrist", grund, f["id"]))
    noch = con.execute("SELECT 1 FROM auftrag_fotos WHERE sha256=? AND geloescht_am IS NULL", (f["sha256"],)).fetchone()
    if not noch:  # Datei nur entfernen, wenn kein anderes (nicht gelöschtes) Foto dieselbe Datei nutzt
        for pfad in (Path(daten_dir) / f["pfad"], vorschau_pfad(daten_dir, f["sha256"])):
            try:
                pfad.unlink()
            except OSError:
                pass


def _mit_freigabe(con, tabelle, zeile_id, aktion):
    """Schutzregel für genau diese Zeile kurz aufheben (nur innerhalb der laufenden Transaktion)."""
    con.execute("INSERT OR IGNORE INTO loeschfreigaben (tabelle, zeile_id) VALUES (?,?)", (tabelle, zeile_id))
    try:
        aktion()
    finally:
        con.execute("DELETE FROM loeschfreigaben WHERE tabelle=? AND zeile_id=?", (tabelle, zeile_id))


def auftrag_dokumentation_loeschen(con, daten_dir, aid, frist):
    """Fotos und Annahme-/Abholscheine eines Auftrags nach Fristablauf löschen (Dateien und Einträge)."""
    from .auftraege import verlauf
    a = con.execute("SELECT * FROM auftraege WHERE id=?", (aid,)).fetchone()
    fotos = con.execute("SELECT * FROM auftrag_fotos WHERE auftrag_id=? AND geloescht_am IS NULL AND leihe_id IS NULL "
                        "AND schadensfall_id IS NULL", (aid,)).fetchall()
    for f in fotos:
        _foto_loeschen(con, daten_dir, f, f"Löschfrist abgelaufen ({frist})")
    belege = con.execute("SELECT * FROM auftrag_belege WHERE auftrag_id=?", (aid,)).fetchall()
    for b in belege:
        pdf = Path(daten_dir) / b["pdf_datei"]
        for pfad in (pdf, pdf.with_suffix(".json"), pdf.with_name(pdf.stem + "_unterschrift.png")):
            try:
                pfad.unlink()
            except OSError:
                pass
        _mit_freigabe(con, "auftrag_belege", b["id"],
                      lambda bid=b["id"]: con.execute("DELETE FROM auftrag_belege WHERE id=?", (bid,)))
    verlauf(con, aid, "Fotos und Scheine gelöscht (Löschfrist)", f"{len(fotos)} Foto(s), {len(belege)} Schein(e) – {frist}")
    _protokoll(con, "Löschfrist", f"Auftrag {a['auftragsnr']}",
               [f"{len(fotos)} Foto(s) (Dateien entfernt)", f"{len(belege)} Annahme-/Abholschein(e) "
                + (f"({', '.join(b['nummer'] for b in belege)})" if belege else "")], [], None, frist)


def leihe_protokoll_loeschen(con, daten_dir, lid, frist):
    """Leihprotokoll (Zustand, Zubehör, Notizen) und Leihfotos nach Fristablauf entfernen; Leihnummer, Daten und
    Beträge bleiben für Rechnungen und Kaution nachvollziehbar."""
    le = con.execute("SELECT * FROM leihen WHERE id=?", (lid,)).fetchone()
    fotos = con.execute("SELECT * FROM auftrag_fotos WHERE (leihe_id=? OR schadensfall_id IN "
                        "(SELECT id FROM schadensfaelle WHERE leihe_id=?)) AND geloescht_am IS NULL", (lid, lid)).fetchall()
    for f in fotos:
        _foto_loeschen(con, daten_dir, f, f"Löschfrist abgelaufen ({frist})")
    _mit_freigabe(con, "leihen", lid, lambda: con.execute(
        "UPDATE leihen SET zustand_ausgabe=NULL, zubehoer_ausgabe='[]', zubehoer_rueckgabe=NULL, rueckgabe_notiz=NULL, "
        "protokoll_geloescht_am=? WHERE id=?", (dbm.jetzt_berlin(), lid)))
    from .leihgeraete import verlauf as lg_verlauf
    lg_verlauf(con, le["geraet_id"], "Leihprotokoll gelöscht (Löschfrist)", f"{le['leihnr']} – {frist}")
    _protokoll(con, "Löschfrist", f"Leihvorgang {le['leihnr']}",
               ["Zustandsbeschreibungen, Zubehörlisten und Notizen des Übergabe-/Rückgabeprotokolls",
                f"{len(fotos)} Foto(s) (Dateien entfernt)"], [], None, frist)


def zurueckstellen(con, art, objekt_id, grund, bis=None):
    if art not in ARTEN:
        raise EingabeFehler("Unbekannte Art.")
    grund = (grund or "").strip()
    if len(grund) < 3:
        raise EingabeFehler("Bitte einen Grund für die Zurückstellung angeben (z. B. laufender Streitfall).")
    if bis:
        try:
            date.fromisoformat(bis)
        except ValueError:
            raise EingabeFehler("Bitte ein gültiges Datum angeben.")
    con.execute("INSERT INTO loesch_zurueckstellungen (art, objekt_id, grund, bis, erstellt_am, benutzer) "
                "VALUES (?,?,?,?,?,?)", (art, objekt_id, grund, bis or None, dbm.jetzt_berlin(), dbm.aktueller_benutzer()))
    dbm.protokollieren("loeschung_zurueckgestellt", "datenschutz", objekt_id, {"art": art, "grund": grund, "bis": bis},
                       con=con)


def zurueckstellung_aufheben(con, zid):
    con.execute("UPDATE loesch_zurueckstellungen SET aufgehoben_am=? WHERE id=? AND aufgehoben_am IS NULL",
                (dbm.jetzt_berlin(), zid))
    dbm.protokollieren("zurueckstellung_aufgehoben", "datenschutz", zid, con=con)


def zurueckstellungen(con):
    return con.execute("SELECT * FROM loesch_zurueckstellungen WHERE aufgehoben_am IS NULL ORDER BY id DESC").fetchall()


def loeschlauf(con, daten_dir, heute=None):
    """Alle heute fälligen, nicht gesperrten und nicht zurückgestellten Löschungen ausführen und protokollieren.

    Muss in einer Transaktion laufen. Gibt eine Zusammenfassung zurück.
    """
    from .annahme import zugang_loeschen
    heute = heute or date.today()
    erg = kandidaten(con, heute, tage=0)
    z = {"interessenten": 0, "kunden_geloescht": 0, "kunden_anonymisiert": 0, "auftraege": 0, "leihen": 0,
         "zugaenge": 0, "emails": 0}
    for e in erg["eintraege"]:
        if e["sperre"] or e["zurueck"] or e["faellig"] > heute:
            continue
        frist = f"{e['art_text']}: {e['frist']}"
        if e["art"] in ("interessent", "kunde"):
            if not con.execute("SELECT 1 FROM kunden WHERE id=? AND anonymisiert_am IS NULL", (e["id"],)).fetchone():
                continue
            bericht, _ = kunde_loeschen(con, e["id"], "Löschfrist", frist)
            if e["art"] == "interessent":
                z["interessenten"] += 1
            else:
                z["kunden_anonymisiert" if bericht["anonymisieren"] else "kunden_geloescht"] += 1
        elif e["art"] == "auftrag":
            auftrag_dokumentation_loeschen(con, daten_dir, e["id"], frist)
            z["auftraege"] += 1
        elif e["art"] == "leihe":
            leihe_protokoll_loeschen(con, daten_dir, e["id"], frist)
            z["leihen"] += 1
        elif e["art"] == "zugang":
            if zugang_loeschen(con, e["id"], "Löschfrist", frist):
                z["zugaenge"] += 1
    if erg["emails"]:  # unverändert: E-Mail-Verlauf ohne Belegbezug
        jahre = _frist(dbm.einstellungen(con), "ds_email_jahre")
        z["emails"] = con.execute("DELETE FROM email_nachrichten WHERE dokument_id IS NULL AND datum < ?",
                                  ((heute - timedelta(days=365 * jahre)).isoformat(),)).rowcount
        if z["emails"]:
            _protokoll(con, "Löschfrist", "E-Mail-Verlauf", [f"{z['emails']} E-Mail(s) ohne Belegbezug"], [], None,
                       f"E-Mail-Verlauf: {jahre} Jahre")
    dbm.einstellungen_speichern({"ds_letzter_lauf": dbm.jetzt_berlin()}, con)
    dbm.protokollieren("datenschutz_loeschlauf", "datenschutz", None, z, con=con)
    return z


def protokolle(con, limit=200):
    return con.execute("SELECT * FROM loeschprotokolle ORDER BY id DESC LIMIT ?", (limit,)).fetchall()


# ---------------------------------------------------------------------- Auskunft nach Art. 15 DSGVO

def _zeilen(con, sql, args):
    return [dict(r) for r in con.execute(sql, args).fetchall()]


def auskunft_daten(con, kid):
    k = dict(con.execute("SELECT * FROM kunden WHERE id=?", (kid,)).fetchone())
    return {
        "kunde": k,
        "auftraege": _zeilen(con, "SELECT auftragsnr, eingang_am, status, geraet, seriennummer, zubehoer, fehler, "
                                  "zustand_eingang, fertig_bis, erledigt_am, abgeholt_am, zugang_art, "
                                  "CASE WHEN zugang_geheim IS NULL THEN 'nein' ELSE 'ja (verschlüsselt)' END AS "
                                  "zugangsdaten_gespeichert FROM auftraege WHERE kunde_id=? ORDER BY eingang_am", (kid,)),
        "dokumente": _zeilen(con, "SELECT typ, nummer, datum, betreff, summe_brutto, status FROM dokumente "
                                  "WHERE kunde_id=? AND status<>'entwurf' ORDER BY datum", (kid,)),
        "zahlungen": _zeilen(con, "SELECT z.datum, z.betrag, z.zahlart, d.nummer FROM zahlungen z JOIN dokumente d "
                                  "ON d.id=z.dokument_id WHERE d.kunde_id=? AND z.storniert_am IS NULL", (kid,)),
        "anfragen": _zeilen(con, "SELECT eingang_am, name, email, telefon, nachricht FROM anfragen WHERE kunde_id=?",
                            (kid,)),
        "vertraege": _zeilen(con, "SELECT v.bezeichnung, a.name AS art, v.beginn, v.ende, v.status FROM vertraege v "
                                  "LEFT JOIN vertragsarten a ON a.id=v.vertragsart_id WHERE v.kunde_id=?", (kid,)),
        "leihen": _zeilen(con, "SELECT l.leihnr, g.bezeichnung, l.ausgabe_am, l.rueckgabe_am FROM leihen l "
                               "JOIN leihgeraete g ON g.id=l.geraet_id WHERE l.kunde_id=?", (kid,)),
        "belege": _zeilen(con, "SELECT b.nummer, b.art, b.unterschrieben_am, b.unterzeichner FROM auftrag_belege b "
                               "JOIN auftraege a ON a.id=b.auftrag_id WHERE a.kunde_id=?", (kid,)),
        "fotos": _zeilen(con, "SELECT a.auftragsnr, f.kategorie, f.dateiname, f.hochgeladen_am FROM auftrag_fotos f "
                              "JOIN auftraege a ON a.id=f.auftrag_id WHERE a.kunde_id=? AND f.geloescht_am IS NULL",
                         (kid,)),
        "emails": _zeilen(con, "SELECT n.datum, n.richtung, n.von, n.an, n.betreff, n.text FROM email_nachrichten n "
                               "JOIN email_kunden e ON e.nachricht_id=n.id WHERE e.kunde_id=? ORDER BY n.datum", (kid,)),
        "benachrichtigungen": _zeilen(con, "SELECT erstellt_am, anlass, kanal, an, betreff, status FROM "
                                           "benachrichtigungen WHERE kunde_id=?", (kid,)),
    }


def auskunft_zip(con, kid, daten_dir):
    """ZIP mit Auskunftsschreiben (PDF), allen Daten (JSON), Belegen, Annahmescheinen und Fotos."""
    d = auskunft_daten(con, kid)
    d["kunde"].pop("zugang_geheim", None)
    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("Auskunft_Art15_DSGVO.pdf", auskunft_pdf(con, d))
        z.writestr("gespeicherte_Daten.json", json.dumps(d, ensure_ascii=False, indent=1, default=str))
        for r in con.execute("SELECT nummer, pdf_pfad FROM dokumente WHERE kunde_id=? AND status<>'entwurf'", (kid,)):
            if r["pdf_pfad"] and (Path(daten_dir) / r["pdf_pfad"]).is_file():
                z.write(Path(daten_dir) / r["pdf_pfad"], f"Belege/{r['nummer']}.pdf")
        for r in con.execute("SELECT b.nummer, b.pdf_datei FROM auftrag_belege b JOIN auftraege a ON a.id=b.auftrag_id "
                             "WHERE a.kunde_id=?", (kid,)):
            if (Path(daten_dir) / r["pdf_datei"]).is_file():
                z.write(Path(daten_dir) / r["pdf_datei"], f"Annahme_Abholscheine/{r['nummer']}.pdf")
        for r in con.execute("SELECT f.id, f.pfad, f.dateiname, a.auftragsnr FROM auftrag_fotos f JOIN auftraege a "
                             "ON a.id=f.auftrag_id WHERE a.kunde_id=? AND f.geloescht_am IS NULL", (kid,)):
            if (Path(daten_dir) / r["pfad"]).is_file():
                z.write(Path(daten_dir) / r["pfad"], f"Fotos/{r['auftragsnr']}_{r['id']}_{r['dateiname']}")
    return puffer.getvalue()


def auskunft_pdf(con, d):
    from .verfahrensdoku import pdf
    einst = dbm.einstellungen(con)
    k = d["kunde"]
    zahl = {name: len(d[name]) for name in ("auftraege", "dokumente", "zahlungen", "anfragen", "vertraege", "leihen",
                                             "belege", "fotos", "emails", "benachrichtigungen")}
    abschnitte = [
        ("Ihre Anfrage nach Art. 15 DSGVO", [
            f"Auskunft für {kunde_name(k)} (Kunden-Nr. {k['kundennr']}), erstellt am {date.today().strftime('%d.%m.%Y')}.",
            f"Verantwortlicher: {einst.get('firma_name') or ''}, {einst.get('inhaber') or ''}, "
            f"{einst.get('strasse') or ''}, {einst.get('plz') or ''} {einst.get('ort') or ''}, "
            f"{einst.get('email') or ''}.",
            "Alle zu Ihrer Person gespeicherten Daten finden Sie vollständig in der beigefügten Datei "
            "„gespeicherte_Daten.json“ sowie als Kopien der Belege, Annahme-/Abholscheine und Fotos."]),
        ("Gespeicherte Daten (Übersicht)", [("tabelle", [["Kategorie", "Anzahl"],
                                                         ["Stammdaten (Name, Anschrift, Kontakt)", "1"],
                                                         ["Reparaturaufträge", str(zahl["auftraege"])],
                                                         ["Rechnungen/Kostenvoranschläge/Gutschriften", str(zahl["dokumente"])],
                                                         ["Zahlungen", str(zahl["zahlungen"])],
                                                         ["Kontaktanfragen", str(zahl["anfragen"])],
                                                         ["Verträge", str(zahl["vertraege"])],
                                                         ["Leihgeräte-Verträge", str(zahl["leihen"])],
                                                         ["Unterschriebene Annahme-/Abholscheine", str(zahl["belege"])],
                                                         ["Fotos", str(zahl["fotos"])],
                                                         ["E-Mails", str(zahl["emails"])],
                                                         ["Benachrichtigungen", str(zahl["benachrichtigungen"])]])]),
        ("Zwecke und Rechtsgrundlagen", [("liste", [
            "Durchführung von Reparaturaufträgen, Kostenvoranschlägen, Leihgeräten und Verträgen "
            "(Art. 6 Abs. 1 lit. b DSGVO)",
            "Rechnungsstellung, Buchhaltung und gesetzliche Aufbewahrung (Art. 6 Abs. 1 lit. c DSGVO i. V. m. "
            "§ 147 AO, § 257 HGB)",
            "Dokumentation des Gerätezustands und Gewährleistung (Art. 6 Abs. 1 lit. b und f DSGVO)"])]),
        ("Empfänger", [("liste", ["Steuerberater (Buchhaltungsdaten)", "E-Mail-Anbieter beim Versand von Nachrichten",
                                  "Kreditinstitut bei Zahlungen", "Finanzbehörden im Rahmen gesetzlicher Pflichten",
                                  "Keine Übermittlung in Drittländer, keine automatisierte Entscheidungsfindung."])]),
        ("Speicherdauer", [("liste", [
            f"Rechnungen und Buchungsbelege: {einst.get('aufbewahrung_belege_jahre') or 8} Jahre, Geschäftsbriefe "
            f"(z. B. Kostenvoranschläge): {einst.get('aufbewahrung_briefe_jahre') or 6} Jahre ab Jahresende",
            f"Fotos und Annahme-/Abholscheine: {_frist(einst, 'ds_fotos_jahre')} Jahre ab Ende des Jahres der Abholung",
            "Gerätezugangsdaten: verschlüsselt, gelöscht bei Abschluss des Auftrags",
            f"Kundendaten ohne Aufbewahrungspflicht: Löschung nach {_frist(einst, 'ds_kunde_inaktiv_jahre')} Jahren "
            "ohne Kontakt"])]),
        ("Herkunft der Daten", ["Die Daten stammen von Ihnen (Auftrag, Kontaktformular, E-Mail, Telefon)."]),
        ("Ihre Rechte", ["Sie haben das Recht auf Berichtigung (Art. 16), Löschung (Art. 17), Einschränkung (Art. 18), "
                         "Datenübertragbarkeit (Art. 20) und Widerspruch (Art. 21) sowie auf Beschwerde bei einer "
                         "Datenschutz-Aufsichtsbehörde (für Baden-Württemberg: Landesbeauftragter für den Datenschutz "
                         "und die Informationsfreiheit)."]),
    ]
    return pdf(abschnitte, einst.get("firma_name") or "", titel="Auskunft nach Art. 15 DSGVO")


def loeschbestaetigung_pdf(con, prot):
    from .verfahrensdoku import pdf
    einst = dbm.einstellungen(con)
    geloescht, behalten = json.loads(prot["geloescht"]), json.loads(prot["behalten"])
    abschnitte = [
        ("Bestätigung", [f"Betroffen: {prot['betroffen']}. Bearbeitet am "
                         f"{datetime.fromisoformat(prot['zeitpunkt']).strftime('%d.%m.%Y %H:%M:%S')} "
                         f"(Anlass: {prot['anlass']})."]),
        ("Gelöscht", [("liste", geloescht or ["–"])]),
        ("Weiter aufbewahrt (gesetzliche Pflicht, Art. 17 Abs. 3 lit. b DSGVO)",
         [("liste", [f"{b['was']} – bis {datum_de(b['bis'])}" for b in behalten] or ["nichts"]),
          "Diese Unterlagen sind gesperrt und werden nur zur Erfüllung der Aufbewahrungspflichten verwendet. "
          "Nach Ablauf der Frist werden sie gelöscht."]),
    ]
    return pdf(abschnitte, einst.get("firma_name") or "", titel="Bestätigung Ihrer Löschanfrage (Art. 17 DSGVO)")


# ---------------------------------------------------------------------- Verzeichnis der Verarbeitungstätigkeiten

def verzeichnis(con):
    """Art. 30 DSGVO – aus den tatsächlich gespeicherten Daten. Gleiche Struktur wie die Verfahrensdokumentation."""
    from .verfahrensdoku import ERGAENZEN
    e = dbm.einstellungen(con)

    def n(sql):
        return con.execute(sql).fetchone()[0]
    zahlen = {
        "kunden": n("SELECT COUNT(*) FROM kunden WHERE anonymisiert_am IS NULL AND interessent=0"),
        "interessenten": n("SELECT COUNT(*) FROM kunden WHERE interessent=1"),
        "auftraege": n("SELECT COUNT(*) FROM auftraege"), "fotos": n("SELECT COUNT(*) FROM auftrag_fotos WHERE geloescht_am IS NULL"),
        "zugaenge": n("SELECT COUNT(*) FROM auftraege WHERE zugang_geheim IS NOT NULL"),
        "emails": n("SELECT COUNT(*) FROM email_nachrichten"), "leihen": n("SELECT COUNT(*) FROM leihen"),
        "anfragen": n("SELECT COUNT(*) FROM anfragen"), "lieferanten": n("SELECT COUNT(*) FROM lieferanten"),
        "belege": n("SELECT COUNT(*) FROM auftrag_belege"), "bank": n("SELECT COUNT(*) FROM bank_umsaetze"),
        "vertraege": n("SELECT COUNT(*) FROM vertraege"), "kasse": n("SELECT COUNT(*) FROM kassenbuch"),
    }
    verantwortlich = e.get("ds_verantwortlicher") or (
        f"{e.get('firma_name') or ERGAENZEN}, Inhaber {e.get('inhaber') or ERGAENZEN}, {e.get('strasse') or ''}, "
        f"{e.get('plz') or ''} {e.get('ort') or ''}, {e.get('email') or ''}, {e.get('telefon') or ''}")
    loesch = (f"Löschfristen im Programm: Interessenten {_frist(e, 'interessent_loeschen_monate')} Monate, inaktive Kunden "
              f"{_frist(e, 'ds_kunde_inaktiv_jahre')} Jahre ab Ende des Jahres des letzten Kontakts, Fotos und "
              f"Annahme-/Abholscheine {_frist(e, 'ds_fotos_jahre')} Jahre ab Ende des Abholjahres, Leihprotokolle "
              f"{_frist(e, 'ds_leihe_jahre')} Jahre ab Ende des Rückgabejahres, "
              f"Gerätezugangsdaten bei Abholung/Abschluss bzw. spätestens {_frist(e, 'ds_zugang_tage')} Tage nach Eingang, "
              f"E-Mails ohne Belegbezug {_frist(e, 'ds_email_jahre')} Jahre (0 = aus). Belege: "
              f"{e.get('aufbewahrung_belege_jahre') or 8} bzw. {e.get('aufbewahrung_briefe_jahre') or 6} Jahre "
              f"(GoBD) – danach Anonymisierung/Löschung. Automatischer Löschlauf: "
              f"{'eingeschaltet' if e.get('ds_auto') else 'ausgeschaltet (manuell unter Datenschutz, Löschlauf)'}.")

    def taetigkeit(titel, zweck, rechtsgrundlage, betroffene, daten, empfaenger, frist, anzahl):
        return (titel, [("tabelle", [["Merkmal", "Angabe"], ["Zweck", zweck], ["Rechtsgrundlage", rechtsgrundlage],
                                     ["Betroffene", betroffene], ["Datenkategorien", daten], ["Empfänger", empfaenger],
                                     ["Löschfrist", frist], ["Bestand (aktuell)", anzahl]])])
    abschnitte = [
        ("1. Verantwortlicher", [verantwortlich, f"Datenschutzbeauftragter: nicht benannt (unter 20 Personen ständig mit "
                                                 f"Datenverarbeitung beschäftigt, § 38 BDSG) – {ERGAENZEN} prüfen.",
                                 f"Stand: {date.today().strftime('%d.%m.%Y')}. Dieses Verzeichnis wurde aus den "
                                 "tatsächlich im Programm gespeicherten Daten erzeugt und ist eine Vorlage."]),
        taetigkeit("2. Kunden- und Auftragsverwaltung (Reparaturen)", "Annahme, Durchführung und Abrechnung von Reparaturen",
                   "Art. 6 Abs. 1 lit. b DSGVO", "Kunden (Privat- und Firmenkunden)",
                   "Name, Anschrift, Telefon, E-Mail, Gerät, Seriennummer/IMEI, Fehlerbeschreibung, Zustand, Zubehör, "
                   "Unterschrift (Annahme-/Abholschein)", "Steuerberater; E-Mail-Anbieter beim Versand",
                   loesch, f"{zahlen['kunden']} Kunden, {zahlen['auftraege']} Aufträge, {zahlen['belege']} unterschriebene Scheine"),
        taetigkeit("3. Fotodokumentation", "Nachweis des Gerätezustands bei Eingang/Ausgabe, Gewährleistung",
                   "Art. 6 Abs. 1 lit. b und f DSGVO", "Kunden (ggf. persönliche Inhalte auf Gerätefotos vermeiden)",
                   "Fotos mit Zeitstempel und Prüfsumme", "keine",
                   f"{_frist(e, 'ds_fotos_jahre')} Jahre ab Ende des Kalenderjahres der Abholung",
                   f"{zahlen['fotos']} Fotos"),
        taetigkeit("4. Gerätezugangsdaten", "Funktionstest des reparierten Geräts", "Art. 6 Abs. 1 lit. b DSGVO (freiwillig)",
                   "Kunden", "PIN, Passwort oder Entsperrmuster (verschlüsselt gespeichert, Anzeige protokolliert)", "keine",
                   f"bei Abschluss des Auftrags, spätestens {_frist(e, 'ds_zugang_tage')} Tage nach Eingang",
                   f"{zahlen['zugaenge']} derzeit gespeichert"),
        taetigkeit("5. Kontaktanfragen und E-Mail-Verlauf", "Beantwortung von Anfragen, Kommunikation zum Auftrag",
                   "Art. 6 Abs. 1 lit. b und f DSGVO", "Interessenten, Kunden", "Name, Kontaktdaten, Nachrichteninhalt",
                   f"E-Mail-Anbieter ({e.get('imap_host') or e.get('smtp_host') or ERGAENZEN})",
                   f"Interessenten {_frist(e, 'interessent_loeschen_monate')} Monate; E-Mails {_frist(e, 'ds_email_jahre')} Jahre",
                   f"{zahlen['anfragen']} Anfragen, {zahlen['interessenten']} Interessenten, {zahlen['emails']} E-Mails"),
        taetigkeit("6. Leihgeräte", "Überlassung von Leihgeräten während der Reparatur", "Art. 6 Abs. 1 lit. b DSGVO",
                   "Kunden", "Leihvertrag, Übergabe-/Rückgabeprotokoll, Fotos, Kaution", "keine",
                   f"{e.get('aufbewahrung_briefe_jahre') or 6} Jahre", f"{zahlen['leihen']} Leihvorgänge"),
        taetigkeit("7. Buchhaltung, Zahlungen, Mahnwesen, Kasse", "Rechnungsstellung, Zahlungsüberwachung, Buchführung",
                   "Art. 6 Abs. 1 lit. b und c DSGVO (§ 147 AO, § 257 HGB)", "Kunden, Lieferanten",
                   "Rechnungsdaten, Zahlungen, Bankumsätze (Name, IBAN, Verwendungszweck), Kassenbuch",
                   "Steuerberater (DATEV-Export), Finanzamt, Kreditinstitut",
                   f"{e.get('aufbewahrung_belege_jahre') or 8} Jahre ab Jahresende",
                   f"{zahlen['bank']} Bankumsätze, {zahlen['kasse']} Kassenbuchungen"),
        taetigkeit("8. Verträge und Lizenzen", "Verwaltung wiederkehrender Leistungen (z. B. Virenschutz, IT-Betreuung)",
                   "Art. 6 Abs. 1 lit. b DSGVO", "Kunden", "Vertragsdaten, Laufzeiten, Abrechnungen",
                   "ggf. Hersteller/Partner (z. B. Wertgarantie) " + ERGAENZEN, "Vertragsende + Aufbewahrungsfrist",
                   f"{zahlen['vertraege']} Verträge"),
        taetigkeit("9. Lieferanten und Einkauf", "Bestellung von Ersatzteilen, Eingangsrechnungen",
                   "Art. 6 Abs. 1 lit. b und c DSGVO", "Ansprechpartner bei Lieferanten", "Name, Kontaktdaten, Bankverbindung",
                   "Steuerberater", f"{e.get('aufbewahrung_belege_jahre') or 8} Jahre", f"{zahlen['lieferanten']} Lieferanten"),
        ("10. Technische und organisatorische Maßnahmen (Art. 32 DSGVO)", [("liste", [
            "Datenhaltung lokal auf dem eigenen PC, keine Cloud-Datenbank",
            "Zugangsdaten (E-Mail, Gerätezugang) verschlüsselt (Fernet/AES)",
            "Programm-Passwort: " + ("eingeschaltet" if e.get("login_aktiv") else "aus – Schutz über die Windows-Anmeldung"),
            "Zugriff aus dem WLAN nur über zeitlich begrenzte QR-Code-Links bzw. mit Passwort",
            f"Automatische Datensicherung: {'eingeschaltet' if e.get('backup_auto') else 'aus'}"
            f"{(', Ziel ' + e['backup_ziel']) if e.get('backup_ziel') else ''}",
            "Unveränderbare Protokolle (Hash-Kette), Belege mit SHA-256-Prüfsummen",
            f"Festplattenverschlüsselung (BitLocker) des PCs: {ERGAENZEN}",
            f"Virenschutz / Updates des Betriebssystems: {ERGAENZEN}"])]),
        ("11. Auftragsverarbeiter (Art. 28 DSGVO)", [("liste", [
            f"E-Mail-Anbieter: {e.get('smtp_host') or ERGAENZEN} – AV-Vertrag {ERGAENZEN}",
            f"Steuerberater: {ERGAENZEN} (eigene Verantwortlichkeit bzw. AV-Vertrag)",
            f"Website/Kontaktformular-Anbieter: {ERGAENZEN}"])]),
    ]
    return abschnitte

