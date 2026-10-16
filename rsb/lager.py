"""Lagerverwaltung: Bestand nur über protokollierte Bewegungen, Reservierungen für Aufträge, Mindestbestand, Inventur.

Grundsätze:
- Der Bestand eines Artikels ist die Summe seiner Lagerbewegungen. Die Spalte artikel.bestand ist nur ein
  Zwischenspeicher und wird ausschließlich hier (bewegung_buchen) gesetzt; die Datenprüfung vergleicht beides.
- Lagerbewegungen sind unveränderlich (Trigger). Fehler werden durch eine Korrekturbuchung berichtigt.
- Reservierungen binden Material für einen Auftrag; beim Erledigen werden sie ausgebucht (Abgang),
  beim Storno der Rechnung bzw. des Materials wieder eingebucht.
"""
import hashlib
import io
import math
import secrets
from datetime import date, datetime, timedelta
from pathlib import Path

from . import db as dbm
from .hilfen import EingabeFehler, euro, menge_text

ARTEN = {"zugang": "Zugang", "abgang": "Abgang", "korrektur": "Korrektur", "inventur": "Inventur"}
RES_STATUS = {"reserviert": "reserviert", "ausgebucht": "ausgebucht", "storniert": "storniert",
              "zurueckgebucht": "zurückgebucht"}


def _menge(wert):
    try:
        m = float(str(wert).replace(",", "."))
    except (TypeError, ValueError):
        raise EingabeFehler("Bitte eine gültige Menge angeben.")
    if math.isnan(m) or math.isinf(m):
        raise EingabeFehler("Bitte eine gültige Menge angeben.")
    return round(m, 3)


def artikel_laden(con, artikel_id):
    a = con.execute("SELECT * FROM artikel WHERE id=?", (artikel_id,)).fetchone()
    if not a:
        raise EingabeFehler("Artikel nicht gefunden.")
    return a


def bestand_berechnen(con, artikel_id, bis=None):
    sql, args = "SELECT COALESCE(SUM(menge), 0) FROM lagerbewegungen WHERE artikel_id=?", [artikel_id]
    if bis:
        sql += " AND substr(zeitpunkt, 1, 10) <= ?"
        args.append(bis)
    return round(con.execute(sql, args).fetchone()[0], 3)


def reserviert(con, artikel_id):
    return round(con.execute("SELECT COALESCE(SUM(menge), 0) FROM lager_reservierungen WHERE artikel_id=? "
                             "AND status='reserviert'", (artikel_id,)).fetchone()[0], 3)


def bewegung_buchen(con, artikel_id, art, menge, grund, auftrag_id=None, dokument_id=None, inventur_id=None,
                    ek=None, warnen_negativ=True):
    """Lagerbewegung buchen (menge mit Vorzeichen: + Zugang, − Abgang). Muss in einer Transaktion laufen."""
    if art not in ARTEN:
        raise EingabeFehler("Unbekannte Buchungsart.")
    grund = (grund or "").strip()
    if len(grund) < 3:
        raise EingabeFehler("Bitte einen Grund für die Lagerbuchung angeben.")
    a = artikel_laden(con, artikel_id)
    if not a["lagerfuehrend"]:
        raise EingabeFehler(f"„{a['name']}“ ist nicht lagerführend.")
    menge = _menge(menge)
    if menge == 0:
        raise EingabeFehler("Die Menge darf nicht 0 sein.")
    if art == "zugang" and menge < 0 or art == "abgang" and menge > 0:
        menge = -menge
    neu = round(bestand_berechnen(con, artikel_id) + menge, 3)
    cur = con.execute(
        "INSERT INTO lagerbewegungen (artikel_id, art, menge, bestand_danach, grund, auftrag_id, dokument_id, "
        "inventur_id, ek, zeitpunkt, benutzer) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (artikel_id, art, menge, neu, grund, auftrag_id, dokument_id, inventur_id,
         a["teilekosten"] if ek is None else ek, dbm.jetzt_berlin(), dbm.aktueller_benutzer()))
    con.execute("UPDATE artikel SET bestand=? WHERE id=?", (neu, artikel_id))
    dbm.protokollieren("lagerbewegung", "artikel", artikel_id, {"art": art, "menge": menge, "grund": grund}, con=con)
    return cur.lastrowid, (neu < 0 and warnen_negativ)


def bewegungen(con, artikel_id=None, limit=500, auftrag_id=None):
    sql = ("SELECT b.*, a.name, a.einheit, au.auftragsnr FROM lagerbewegungen b JOIN artikel a ON a.id=b.artikel_id "
           "LEFT JOIN auftraege au ON au.id=b.auftrag_id WHERE 1=1 ")
    args = []
    if artikel_id:
        sql += "AND b.artikel_id=? "
        args.append(artikel_id)
    if auftrag_id:
        sql += "AND b.auftrag_id=? "
        args.append(auftrag_id)
    return con.execute(sql + "ORDER BY b.id DESC LIMIT ?", (*args, limit)).fetchall()


def uebersicht(con, suche="", nur_unter_min=False):
    sql = ("SELECT a.*, COALESCE((SELECT SUM(r.menge) FROM lager_reservierungen r WHERE r.artikel_id=a.id "
           "AND r.status='reserviert'), 0) AS reserviert FROM artikel a WHERE a.lagerfuehrend=1 ")
    args = []
    suche = (suche or "").strip()
    if suche:
        sql += ("AND (a.name LIKE ? OR a.artikelnr LIKE ? OR a.ean LIKE ? OR a.herstellernr LIKE ? "
                "OR a.kompatibilitaet LIKE ? OR a.lagerort LIKE ?) ")
        args += [f"%{suche}%"] * 6
    zeilen = []
    for a in con.execute(sql + "ORDER BY a.lagerort, a.name", args).fetchall():
        verfuegbar = round((a["bestand"] or 0) - a["reserviert"], 3)
        unter = a["mindestbestand"] is not None and verfuegbar < a["mindestbestand"]
        if nur_unter_min and not unter:
            continue
        zeilen.append({"a": a, "verfuegbar": verfuegbar, "unter_min": unter,
                       "wert": int(round((a["bestand"] or 0) * (a["teilekosten"] or 0)))})
    return zeilen


def bestellvorschlag(con):
    """Artikel unter Mindestbestand mit Vorschlagsmenge (auffüllen auf das Doppelte des Mindestbestands)."""
    vorschlag = []
    for z in uebersicht(con, nur_unter_min=True):
        a = z["a"]
        ziel = (a["mindestbestand"] or 0) * 2 or 1
        menge = max(1, math.ceil(ziel - z["verfuegbar"]))
        vorschlag.append({**z, "menge": menge, "summe": menge * (a["teilekosten"] or 0)})
    return vorschlag


def unter_mindestbestand_anzahl(con):
    return con.execute(
        "SELECT COUNT(*) FROM artikel a WHERE a.lagerfuehrend=1 AND a.mindestbestand IS NOT NULL AND "
        "COALESCE(a.bestand, 0) - COALESCE((SELECT SUM(r.menge) FROM lager_reservierungen r WHERE r.artikel_id=a.id "
        "AND r.status='reserviert'), 0) < a.mindestbestand").fetchone()[0]


# ---------------------------------------------------------------------- Reservierungen (Material zum Auftrag)

def reservieren(con, auftrag_id, artikel_id, menge, quelle="manuell"):
    """Material für einen Auftrag reservieren. Gibt (id, warnung) zurück; warnung, wenn nicht genug verfügbar ist."""
    from .auftraege import verlauf
    a = artikel_laden(con, artikel_id)
    if not a["lagerfuehrend"]:
        raise EingabeFehler(f"„{a['name']}“ ist nicht lagerführend.")
    au = con.execute("SELECT * FROM auftraege WHERE id=?", (auftrag_id,)).fetchone()
    if not au:
        raise EingabeFehler("Auftrag nicht gefunden.")
    menge = _menge(menge)
    if menge <= 0:
        raise EingabeFehler("Bitte eine Menge größer 0 angeben.")
    verfuegbar = round((a["bestand"] or 0) - reserviert(con, artikel_id), 3)
    cur = con.execute("INSERT INTO lager_reservierungen (artikel_id, auftrag_id, menge, status, quelle, erstellt_am, "
                      "benutzer) VALUES (?,?,?,'reserviert',?,?,?)",
                      (artikel_id, auftrag_id, menge, quelle, dbm.jetzt_berlin(), dbm.aktueller_benutzer()))
    verlauf(con, auftrag_id, "Material reserviert", f"{menge_text(menge)} {a['einheit'] or ''} {a['name']}")
    if au["status"] == "erledigt":  # nachträglich erfasst: sofort ausbuchen
        _ausbuchen(con, con.execute("SELECT * FROM lager_reservierungen WHERE id=?", (cur.lastrowid,)).fetchone(),
                   au)
    warnung = None
    if menge > verfuegbar:
        warnung = (f"Für „{a['name']}“ sind nur {menge_text(max(verfuegbar, 0))} {a['einheit'] or ''} verfügbar – "
                   "bitte nachbestellen.")
    return cur.lastrowid, warnung


def aus_kva_reservieren(con, auftrag_id):
    """Lagerführende Positionen des verknüpften KVA reservieren (die noch nicht reserviert sind)."""
    au = con.execute("SELECT * FROM auftraege WHERE id=?", (auftrag_id,)).fetchone()
    if not au or not au["kva_id"]:
        raise EingabeFehler("Mit dem Auftrag ist kein Kostenvoranschlag verknüpft.")
    anzahl, warnungen = 0, []
    for p in con.execute("SELECT p.* FROM positionen p JOIN artikel a ON a.id=p.artikel_id WHERE p.dokument_id=? "
                         "AND a.lagerfuehrend=1 ORDER BY p.pos", (au["kva_id"],)).fetchall():
        schon = con.execute("SELECT 1 FROM lager_reservierungen WHERE auftrag_id=? AND artikel_id=? "
                            "AND status IN ('reserviert', 'ausgebucht')", (auftrag_id, p["artikel_id"])).fetchone()
        if schon:
            continue
        _, w = reservieren(con, auftrag_id, p["artikel_id"], p["menge"], quelle="KVA")
        anzahl += 1
        if w:
            warnungen.append(w)
    return anzahl, warnungen


def _ausbuchen(con, r, au):
    bid, _ = bewegung_buchen(con, r["artikel_id"], "abgang", -r["menge"], f"Auftrag {au['auftragsnr']} erledigt",
                             auftrag_id=au["id"])
    con.execute("UPDATE lager_reservierungen SET status='ausgebucht', erledigt_am=?, bewegung_id=? WHERE id=?",
                (dbm.jetzt_berlin(), bid, r["id"]))


def auftrag_erledigt(con, auftrag_id):
    """Beim Erledigen: alle Reservierungen ausbuchen. Muss in einer Transaktion laufen."""
    from .auftraege import verlauf
    au = con.execute("SELECT * FROM auftraege WHERE id=?", (auftrag_id,)).fetchone()
    liste = con.execute("SELECT * FROM lager_reservierungen WHERE auftrag_id=? AND status='reserviert'",
                        (auftrag_id,)).fetchall()
    for r in liste:
        _ausbuchen(con, r, au)
    if liste:
        verlauf(con, auftrag_id, "Material ausgebucht", f"{len(liste)} Position(en)")
    return len(liste)


def reservierung_stornieren(con, res_id, grund):
    """Reserviertes Material freigeben bzw. ausgebuchtes Material wieder einbuchen."""
    from .auftraege import verlauf
    r = con.execute("SELECT r.*, a.name FROM lager_reservierungen r JOIN artikel a ON a.id=r.artikel_id "
                    "WHERE r.id=?", (res_id,)).fetchone()
    if not r or r["status"] not in ("reserviert", "ausgebucht"):
        raise EingabeFehler("Diese Materialposition ist bereits storniert.")
    grund = (grund or "").strip()
    if len(grund) < 3:
        raise EingabeFehler("Bitte einen Grund angeben.")
    au = con.execute("SELECT * FROM auftraege WHERE id=?", (r["auftrag_id"],)).fetchone()
    if r["status"] == "ausgebucht":
        bewegung_buchen(con, r["artikel_id"], "zugang", r["menge"], f"Rückbuchung Auftrag {au['auftragsnr']}: {grund}",
                        auftrag_id=au["id"])
        neu = "zurueckgebucht"
    else:
        neu = "storniert"
    con.execute("UPDATE lager_reservierungen SET status=?, erledigt_am=?, storno_grund=? WHERE id=?",
                (neu, dbm.jetzt_berlin(), grund, res_id))
    verlauf(con, au["id"], "Material storniert" if neu == "storniert" else "Material zurückgebucht",
            f"{menge_text(r['menge'])} {r['name']} – {grund}")


def rechnung_storniert(con, dokument_id):
    """Storno einer Auftragsrechnung: ausgebuchtes Material wieder einbuchen."""
    anzahl = 0
    for au in con.execute("SELECT * FROM auftraege WHERE rechnung_id=?", (dokument_id,)).fetchall():
        for r in con.execute("SELECT id FROM lager_reservierungen WHERE auftrag_id=? AND status='ausgebucht'",
                             (au["id"],)).fetchall():
            reservierung_stornieren(con, r["id"], "Rechnung storniert")
            anzahl += 1
    return anzahl


def auftrag_material(con, auftrag_id):
    return con.execute("SELECT r.*, a.name, a.einheit, a.lagerort, a.teilekosten, a.bestand, b.ek AS ek_buchung "
                       "FROM lager_reservierungen r JOIN artikel a ON a.id=r.artikel_id "
                       "LEFT JOIN lagerbewegungen b ON b.id=r.bewegung_id WHERE r.auftrag_id=? ORDER BY r.id",
                       (auftrag_id,)).fetchall()


def auftrag_materialkosten(con, auftrag_id):
    """Summe der ausgebuchten Teile zum Einkaufspreis der Buchung (für Garantiefälle)."""
    return int(round(con.execute(
        "SELECT COALESCE(SUM(-b.menge * COALESCE(b.ek, 0)), 0) FROM lagerbewegungen b WHERE b.auftrag_id=?",
        (auftrag_id,)).fetchone()[0]))


# ---------------------------------------------------------------------- Lagerwert und Inventur

def lagerwert(con, stichtag=None):
    """Lagerwert zum Stichtag (Bestand laut Bewegungen bis einschließlich Stichtag × aktueller Einkaufspreis)."""
    stichtag = stichtag or date.today().isoformat()
    zeilen, summe = [], 0
    for a in con.execute("SELECT * FROM artikel WHERE lagerfuehrend=1 OR id IN (SELECT artikel_id FROM lagerbewegungen) "
                         "ORDER BY lagerort, name").fetchall():
        b = bestand_berechnen(con, a["id"], stichtag)
        if not b:
            continue
        wert = int(round(b * (a["teilekosten"] or 0)))
        summe += wert
        zeilen.append({"a": a, "bestand": b, "ek": a["teilekosten"] or 0, "wert": wert,
                       "ek_unbekannt": bool(a["ek_unbekannt"])})
    return zeilen, summe


def inventur_anlegen(con, stichtag, bezeichnung=""):
    if con.execute("SELECT 1 FROM inventuren WHERE status='offen'").fetchone():
        raise EingabeFehler("Es läuft bereits eine Inventur. Bitte erst abschließen.")
    try:
        date.fromisoformat(stichtag)
    except (TypeError, ValueError):
        raise EingabeFehler("Bitte einen gültigen Stichtag angeben.")
    cur = con.execute("INSERT INTO inventuren (stichtag, bezeichnung, status, erstellt_am, benutzer) "
                      "VALUES (?,?,'offen',?,?)", (stichtag, bezeichnung or f"Inventur {stichtag}", dbm.jetzt_berlin(),
                                                    dbm.aktueller_benutzer()))
    iid = cur.lastrowid
    for a in con.execute("SELECT * FROM artikel WHERE lagerfuehrend=1 ORDER BY lagerort, name").fetchall():
        con.execute("INSERT INTO inventur_positionen (inventur_id, artikel_id, soll, ek) VALUES (?,?,?,?)",
                    (iid, a["id"], a["bestand"] or 0, a["teilekosten"] or 0))
    dbm.protokollieren("inventur_angelegt", "inventur", iid, {"stichtag": stichtag}, con=con)
    return iid


def inventur_positionen(con, iid):
    return con.execute("SELECT p.*, a.name, a.einheit, a.lagerort, a.artikelnr, a.ean, a.bestand AS bestand_jetzt "
                       "FROM inventur_positionen p JOIN artikel a ON a.id=p.artikel_id WHERE p.inventur_id=? "
                       "ORDER BY a.lagerort, a.name", (iid,)).fetchall()


def zaehlen(con, iid, werte):
    """werte: {artikel_id: ist-Menge-Text}; leere Felder bleiben ungezählt. Muss in einer Transaktion laufen."""
    inv = con.execute("SELECT * FROM inventuren WHERE id=?", (iid,)).fetchone()
    if not inv or inv["status"] != "offen":
        raise EingabeFehler("Die Inventur ist bereits abgeschlossen.")
    anzahl = 0
    for artikel_id, text in werte.items():
        text = (text or "").strip()
        if text == "":
            continue
        ist = _menge(text)
        if ist < 0:
            raise EingabeFehler("Gezählte Mengen dürfen nicht negativ sein.")
        cur = con.execute("UPDATE inventur_positionen SET ist=?, gezaehlt_am=?, gezaehlt_von=? WHERE inventur_id=? "
                          "AND artikel_id=? AND (ist IS NULL OR ist<>?)",
                          (ist, dbm.jetzt_berlin(), dbm.aktueller_benutzer(), iid, artikel_id, ist))
        anzahl += cur.rowcount
    return anzahl


def inventur_abschliessen(con, iid, daten_dir, ungezaehlt_wie_soll=False):
    """Differenzen buchen, Protokoll-PDF archivieren. Muss in einer Transaktion laufen."""
    inv = con.execute("SELECT * FROM inventuren WHERE id=?", (iid,)).fetchone()
    if not inv or inv["status"] != "offen":
        raise EingabeFehler("Die Inventur ist bereits abgeschlossen.")
    positionen = inventur_positionen(con, iid)
    offen = [p for p in positionen if p["ist"] is None]
    if offen and not ungezaehlt_wie_soll:
        raise EingabeFehler(f"{len(offen)} Artikel sind noch nicht gezählt. Bitte zählen oder bestätigen, dass "
                            "ungezählte Artikel unverändert bleiben.")
    differenzen = 0
    for p in positionen:
        ist = p["ist"]
        if ist is None:
            continue
        diff = round(ist - bestand_berechnen(con, p["artikel_id"]), 3)
        if diff:
            bewegung_buchen(con, p["artikel_id"], "inventur", diff, f"{inv['bezeichnung']}: gezählt "
                            f"{menge_text(ist)}", inventur_id=iid, warnen_negativ=False)
            differenzen += 1
    positionen = inventur_positionen(con, iid)
    wert = sum(int(round((p["ist"] if p["ist"] is not None else p["soll"]) * (p["ek"] or 0))) for p in positionen)
    jetzt = dbm.jetzt_berlin()
    pdf = inventur_pdf(con, inv, positionen, wert, jetzt, daten_dir)
    ordner = Path(daten_dir) / "dokumente" / "inventur"
    ordner.mkdir(parents=True, exist_ok=True)
    datei = ordner / f"Inventur_{inv['stichtag']}_{iid}.pdf"
    datei.write_bytes(pdf)
    rel = datei.relative_to(Path(daten_dir)).as_posix()
    con.execute("UPDATE inventuren SET status='abgeschlossen', abgeschlossen_am=?, abgeschlossen_von=?, lagerwert=?, "
                "differenzen=?, pdf_datei=?, pdf_sha256=? WHERE id=?",
                (jetzt, dbm.aktueller_benutzer(), wert, differenzen, rel, hashlib.sha256(pdf).hexdigest(), iid))
    dbm.protokollieren("inventur_abgeschlossen", "inventur", iid,
                       {"lagerwert": wert, "differenzen": differenzen, "pdf_sha256": hashlib.sha256(pdf).hexdigest()},
                       con=con)
    return differenzen, wert


def inventur_pdf(con, inv, positionen, wert, zeitpunkt, daten_dir):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    from .pdf import _schrift_registrieren
    einst = dbm.einstellungen(con)
    f_norm, f_fett, _ = _schrift_registrieren(einst.get("schrift") or "Montserrat")
    st = ParagraphStyle("n", fontName=f_norm, fontSize=8, leading=10)
    st_f = ParagraphStyle("f", parent=st, fontName=f_fett)
    st_t = ParagraphStyle("t", fontName=f_fett, fontSize=14, leading=18)
    puffer = io.BytesIO()
    doc = SimpleDocTemplate(puffer, pagesize=landscape(A4), leftMargin=14 * mm, rightMargin=14 * mm, topMargin=14 * mm,
                            bottomMargin=14 * mm, title=f"Inventurprotokoll {inv['stichtag']}")
    kopf = ["Lagerort", "Artikel", "Art.-Nr./EAN", "Soll", "Ist", "Differenz", "Einheit", "EK", "Wert (Ist)",
            "gezählt"]
    zeilen = [[Paragraph(k, st_f) for k in kopf]]
    for p in positionen:
        ist = p["ist"]
        diff = (ist - p["soll"]) if ist is not None else None
        zeilen.append([Paragraph(x, st) for x in [
            p["lagerort"] or "", p["name"], " / ".join(x for x in [p["artikelnr"], p["ean"]] if x),
            menge_text(p["soll"]), menge_text(ist) if ist is not None else "nicht gezählt (= Soll)",
            (("+" if diff > 0 else "") + menge_text(diff)) if diff else "", p["einheit"] or "", euro(p["ek"] or 0),
            euro(int(round((ist if ist is not None else p["soll"]) * (p["ek"] or 0)))),
            f"{p['gezaehlt_von'] or ''} {datetime.fromisoformat(p['gezaehlt_am']).strftime('%d.%m.%Y %H:%M:%S')}"
            if p["gezaehlt_am"] else ""]])
    t = Table(zeilen, colWidths=[25 * mm, 65 * mm, 35 * mm, 16 * mm, 30 * mm, 18 * mm, 15 * mm, 20 * mm, 22 * mm,
                                 23 * mm], repeatRows=1)
    t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.3, colors.HexColor("#D5D9DE")),
                           ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    inhalt = [Paragraph(f"Inventurprotokoll – Stichtag {datetime.fromisoformat(inv['stichtag']).strftime('%d.%m.%Y')}",
                        st_t),
              Paragraph(f"{einst.get('firma_name') or ''} · {inv['bezeichnung']} · angelegt "
                        f"{datetime.fromisoformat(inv['erstellt_am']).strftime('%d.%m.%Y %H:%M:%S')} von "
                        f"{inv['benutzer']} · abgeschlossen {datetime.fromisoformat(zeitpunkt).strftime('%d.%m.%Y %H:%M:%S')}"
                        f" von {dbm.aktueller_benutzer()}", st), Spacer(1, 4 * mm), t, Spacer(1, 4 * mm),
              Paragraph(f"Lagerwert zum Einkaufspreis: <b>{euro(wert)}</b>. Differenzen wurden als Inventurbuchung in "
                        "die Lagerbewegungen übernommen. Dieses Protokoll wurde unverändert archiviert (SHA-256).", st)]
    doc.build(inhalt)
    return puffer.getvalue()


# ---------------------------------------------------------------------- Zählen am Handy

def zaehl_token(con, iid, minuten=240):
    token = secrets.token_urlsafe(24)
    jetzt = datetime.fromisoformat(dbm.jetzt_berlin())
    con.execute("INSERT INTO inventur_zugaenge (token, inventur_id, gueltig_bis, erstellt_am) VALUES (?,?,?,?)",
                (token, iid, (jetzt + timedelta(minutes=minuten)).isoformat(timespec="seconds"),
                 jetzt.isoformat(timespec="seconds")))
    return token


def zaehl_token_pruefen(con, token):
    if not token or len(token) > 64:
        return None
    z = con.execute("SELECT z.*, i.status FROM inventur_zugaenge z JOIN inventuren i ON i.id=z.inventur_id "
                    "WHERE token=?", (token,)).fetchone()
    if not z or z["status"] != "offen" or datetime.fromisoformat(z["gueltig_bis"]) < \
            datetime.fromisoformat(dbm.jetzt_berlin()):
        return None
    return z


def integritaet(con):
    """Abweichungen zwischen artikel.bestand und der Summe der Bewegungen (für die Datenprüfung)."""
    fehler = []
    for a in con.execute("SELECT id, name, bestand FROM artikel WHERE lagerfuehrend=1 OR id IN "
                         "(SELECT artikel_id FROM lagerbewegungen)").fetchall():
        summe = bestand_berechnen(con, a["id"])
        if round(a["bestand"] or 0, 3) != summe:
            fehler.append(f"Lagerbestand „{a['name']}“: gespeichert {menge_text(a['bestand'] or 0)}, laut Bewegungen "
                          f"{menge_text(summe)}")
    return fehler

