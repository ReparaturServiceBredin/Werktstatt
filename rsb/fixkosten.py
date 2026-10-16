"""Fixkosten: wiederkehrende Ausgaben (Miete, Strom, Versicherungen, Abos …).

- Beträge werden nie überschrieben: jede Änderung ist ein neuer Eintrag mit „gültig ab“. So bleiben vergangene
  Zeiträume korrekt (z. B. Mieterhöhung ab 01.01.2027).
- Fälligkeiten ergeben sich aus Beginn, Rhythmus und Fälligkeitstag (Tag 31 = Monatsende).
- „Anteilig“ verteilt jährliche/vierteljährliche/halbjährliche Kosten gleichmäßig auf die Monate.
- Im Bankabgleich werden Abbuchungen einer Fixkosten-Position zugeordnet (Vorschlag über Empfänger und Betrag,
  bestätigt wird von Hand); fehlende oder abweichende Zahlungen werden markiert.
"""
import calendar
import hashlib
from datetime import date, timedelta
from pathlib import Path

from . import db as dbm
from .hilfen import EingabeFehler, euro, heute_datum

RHYTHMEN = {"monatlich": ("monatlich", 1), "vierteljaehrlich": ("vierteljährlich", 3),
            "halbjaehrlich": ("halbjährlich", 6), "jaehrlich": ("jährlich", 12)}
ZAHLUNGSARTEN = {"lastschrift": "Lastschrift", "dauerauftrag": "Dauerauftrag", "ueberweisung": "Überweisung",
                 "karte": "Karte", "paypal": "PayPal", "bar": "bar"}
UEBER_BANK = {"lastschrift", "dauerauftrag", "ueberweisung", "karte"}
EINHEITEN = {"tage": "Tage", "wochen": "Wochen", "monate": "Monate"}
FELDER = ["bezeichnung", "kategorie", "rhythmus", "faellig_tag", "beginn", "ende", "kuendigung_wert",
          "kuendigung_einheit", "zahlungsart", "empfaenger", "lieferant_id", "bank_suchbegriff", "notiz"]


def kategorien(einst):
    return [k.strip() for k in (einst.get("fixkosten_kategorien") or "").splitlines() if k.strip()] or ["Sonstiges"]


def plus_monate(d, monate):
    m = d.month - 1 + monate
    j, m = d.year + m // 12, m % 12 + 1
    return date(j, m, min(d.day, calendar.monthrange(j, m)[1]))


def _tag(j, m, tag):
    return date(j, m, min(int(tag or 1), calendar.monthrange(j, m)[1]))


def _d(iso):
    return date.fromisoformat(iso[:10]) if iso else None


# ---------------------------------------------------------------------- Anlegen / Ändern

def _pruefen(werte, einst):
    w = dict(werte)
    w["bezeichnung"] = (w.get("bezeichnung") or "").strip()
    if len(w["bezeichnung"]) < 2:
        raise EingabeFehler("Bitte eine Bezeichnung angeben (z. B. Werkstattmiete).")
    if w.get("rhythmus") not in RHYTHMEN:
        raise EingabeFehler("Bitte einen Rhythmus wählen.")
    try:
        w["faellig_tag"] = int(w.get("faellig_tag") or 1)
    except ValueError:
        raise EingabeFehler("Der Fälligkeitstag muss eine Zahl zwischen 1 und 31 sein.")
    if not 1 <= w["faellig_tag"] <= 31:
        raise EingabeFehler("Der Fälligkeitstag muss zwischen 1 und 31 liegen.")
    for k in ("beginn", "ende"):
        if w.get(k):
            try:
                date.fromisoformat(w[k])
            except ValueError:
                raise EingabeFehler("Bitte ein gültiges Datum angeben.")
        else:
            w[k] = None
    if not w["beginn"]:
        raise EingabeFehler("Bitte den Beginn angeben.")
    if w["ende"] and w["ende"] < w["beginn"]:
        raise EingabeFehler("Das Ende liegt vor dem Beginn.")
    if w.get("zahlungsart") not in ZAHLUNGSARTEN:
        w["zahlungsart"] = "lastschrift"
    w["kategorie"] = (w.get("kategorie") or "").strip() or "Sonstiges"
    try:
        w["kuendigung_wert"] = int(w["kuendigung_wert"]) if str(w.get("kuendigung_wert") or "").strip() else None
    except ValueError:
        raise EingabeFehler("Die Kündigungsfrist muss eine Zahl sein.")
    w["kuendigung_einheit"] = w.get("kuendigung_einheit") if w["kuendigung_wert"] and \
        w.get("kuendigung_einheit") in EINHEITEN else None
    if not w["kuendigung_einheit"]:
        w["kuendigung_wert"] = None
    w["lieferant_id"] = int(w["lieferant_id"]) if str(w.get("lieferant_id") or "").isdigit() else None
    for k in ("empfaenger", "bank_suchbegriff", "notiz"):
        w[k] = (w.get(k) or "").strip() or None
    return {k: w.get(k) for k in FELDER}


def speichern(con, werte, einst, fid=None, betrag=None):
    """Anlegen (mit erstem Betrag ab Beginn) oder Stammdaten ändern. Beträge ändern nur über betrag_neu()."""
    w = _pruefen(werte, einst)
    jetzt = dbm.jetzt_berlin()
    if fid:
        alt = con.execute("SELECT * FROM fixkosten WHERE id=?", (fid,)).fetchone()
        con.execute(f"UPDATE fixkosten SET {', '.join(f'{k}=?' for k in FELDER)}, geaendert_am=? WHERE id=?",
                    (*w.values(), jetzt, fid))
        dbm.aenderungen_erfassen(con, "fixkosten", fid, dict(alt), w)
        return fid
    if not betrag:
        raise EingabeFehler("Bitte den Betrag angeben.")
    cur = con.execute(f"INSERT INTO fixkosten ({', '.join(FELDER)}, erstellt_am, geaendert_am) "
                      f"VALUES ({', '.join('?' * len(FELDER))}, ?, ?)", (*w.values(), jetzt, jetzt))
    fid = cur.lastrowid
    betrag_neu(con, fid, w["beginn"], *betrag, notiz="Anfangsbetrag")
    dbm.protokollieren("fixkosten_angelegt", "fixkosten", fid, {"bezeichnung": w["bezeichnung"]}, con=con)
    return fid


def betrag_rechnen(netto=None, brutto=None, steuersatz=0.0):
    """Netto ↔ Brutto (Cent). Angegeben wird eines von beiden."""
    satz = float(steuersatz or 0)
    if netto is not None:
        return netto, int(round(netto * (100 + satz) / 100))
    return int(round(brutto * 100 / (100 + satz))), brutto


def betrag_neu(con, fid, gueltig_ab, netto, steuersatz, notiz=None):
    """Neuer Betrag ab einem Datum. Vorhandene Beträge bleiben unverändert (Verlauf)."""
    try:
        date.fromisoformat(gueltig_ab or "")
    except ValueError:
        raise EingabeFehler("Bitte angeben, ab wann der Betrag gilt.")
    if netto is None or netto < 0:
        raise EingabeFehler("Bitte einen Betrag angeben.")
    netto, brutto = betrag_rechnen(netto=netto, steuersatz=steuersatz)
    if con.execute("SELECT 1 FROM fixkosten_betraege WHERE fixkosten_id=? AND gueltig_ab=?",
                   (fid, gueltig_ab)).fetchone():
        raise EingabeFehler("Für dieses Datum gibt es schon einen Betrag. Bitte ein anderes „gültig ab“ wählen.")
    con.execute("INSERT INTO fixkosten_betraege (fixkosten_id, gueltig_ab, netto, steuersatz, brutto, notiz, erfasst_am, "
                "benutzer) VALUES (?,?,?,?,?,?,?,?)", (fid, gueltig_ab, netto, float(steuersatz or 0), brutto,
                                                       (notiz or "").strip() or None, dbm.jetzt_berlin(),
                                                       dbm.aktueller_benutzer()))
    dbm.ereignis_erfassen(con, "fixkosten", fid, "Betrag ab " + gueltig_ab, f"{euro(netto)} netto / {euro(brutto)} brutto")


def betrag_entfernen(con, bid, heute=None):
    """Nur ein noch nicht gültiger (zukünftiger) Betrag darf wieder entfernt werden."""
    b = con.execute("SELECT * FROM fixkosten_betraege WHERE id=?", (bid,)).fetchone()
    if not b:
        raise EingabeFehler("Betrag nicht gefunden.")
    if b["gueltig_ab"] <= (heute or heute_datum()).isoformat():
        raise EingabeFehler("Bereits gültige Beträge bleiben erhalten – bitte einen neuen Betrag „gültig ab“ erfassen.")
    if con.execute("SELECT COUNT(*) FROM fixkosten_betraege WHERE fixkosten_id=?", (b["fixkosten_id"],)).fetchone()[0] < 2:
        raise EingabeFehler("Der einzige Betrag kann nicht entfernt werden.")
    con.execute("DELETE FROM fixkosten_betraege WHERE id=?", (bid,))
    dbm.ereignis_erfassen(con, "fixkosten", b["fixkosten_id"], "geplanten Betrag entfernt", f"ab {b['gueltig_ab']}")
    return b["fixkosten_id"]


def loeschen(con, fid):
    if con.execute("SELECT 1 FROM bank_umsaetze WHERE fixkosten_id=?", (fid,)).fetchone() or \
            con.execute("SELECT 1 FROM eingangsrechnungen WHERE fixkosten_id=?", (fid,)).fetchone():
        raise EingabeFehler("Zu dieser Position gibt es zugeordnete Zahlungen oder Rechnungen. Bitte stattdessen ein "
                            "Vertragsende eintragen – dann bleiben vergangene Zeiträume korrekt.")
    f = con.execute("SELECT * FROM fixkosten WHERE id=?", (fid,)).fetchone()
    con.execute("DELETE FROM fixkosten_betraege WHERE fixkosten_id=?", (fid,))
    con.execute("DELETE FROM fixkosten WHERE id=?", (fid,))
    dbm.protokollieren("fixkosten_geloescht", "fixkosten", fid, {"bezeichnung": f["bezeichnung"]}, con=con)


def vertrag_ablegen(daten_dir, daten, name):
    if not daten:
        raise EingabeFehler("Die Datei ist leer.")
    endung = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if endung not in ("pdf", "jpg", "jpeg", "png"):
        raise EingabeFehler("Bitte eine PDF- oder Bilddatei hochladen.")
    sha = hashlib.sha256(daten).hexdigest()
    ordner = Path(daten_dir) / "belege" / "fixkosten"
    ordner.mkdir(parents=True, exist_ok=True)
    pfad = ordner / f"{sha}.{endung}"
    if not pfad.exists():
        pfad.write_bytes(daten)
    return pfad.relative_to(Path(daten_dir)).as_posix(), sha


# ---------------------------------------------------------------------- Lesen und rechnen

def alle(con):
    """Alle Positionen mit Beträgen (Verlauf, aufsteigend) – als Liste von dicts."""
    betraege = {}
    for b in con.execute("SELECT * FROM fixkosten_betraege ORDER BY gueltig_ab"):
        betraege.setdefault(b["fixkosten_id"], []).append(dict(b))
    liste = []
    for f in con.execute("SELECT f.*, l.name AS lieferant FROM fixkosten f LEFT JOIN lieferanten l "
                         "ON l.id=f.lieferant_id ORDER BY f.kategorie, f.bezeichnung"):
        d = dict(f)
        d["betraege"] = betraege.get(f["id"], [])
        liste.append(d)
    return liste


def eine(con, fid):
    return next((f for f in alle(con) if f["id"] == fid), None)


def betrag_am(f, tag):
    """Betrag, der an diesem Tag gilt (vor dem ersten „gültig ab“: der erste Betrag)."""
    if not f["betraege"]:
        return None
    gueltig = [b for b in f["betraege"] if b["gueltig_ab"] <= tag.isoformat()]
    return gueltig[-1] if gueltig else f["betraege"][0]


def aktiv_am(f, tag):
    return _d(f["beginn"]) <= tag and (not f["ende"] or tag <= _d(f["ende"]))


def faelligkeiten(f, von, bis):
    """Alle Fälligkeiten im Zeitraum: [(Datum, Betrag-dict)]."""
    abstand = RHYTHMEN[f["rhythmus"]][1]
    beginn, ende = _d(f["beginn"]), _d(f["ende"]) if f["ende"] else None
    j, m = beginn.year, beginn.month
    ergebnis = []
    while True:
        d = _tag(j, m, f["faellig_tag"])
        if d > bis or (ende and d > ende):
            break
        if d >= beginn and d >= von:
            ergebnis.append((d, betrag_am(f, d)))
        m += abstand
        j, m = j + (m - 1) // 12, (m - 1) % 12 + 1
    return ergebnis


def monatsanteil(f, jahr, monat):
    """Anteiliger Betrag für einen Monat (Jahresbetrag / 12 usw.), wenn die Position in dem Monat läuft."""
    erster = date(jahr, monat, 1)
    letzter = date(jahr, monat, calendar.monthrange(jahr, monat)[1])
    beginn, ende = _d(f["beginn"]), _d(f["ende"]) if f["ende"] else None
    if beginn > letzter or (ende and ende < erster):
        return None
    b = betrag_am(f, max(erster, beginn))
    if not b:
        return None
    teiler = RHYTHMEN[f["rhythmus"]][1]
    return {"netto": b["netto"] / teiler, "brutto": b["brutto"] / teiler, "steuer": (b["brutto"] - b["netto"]) / teiler,
            "steuersatz": b["steuersatz"]}


def monate(von, bis):
    j, m = von.year, von.month
    while date(j, m, 1) <= bis:
        yield j, m
        m += 1
        j, m = (j + 1, 1) if m > 12 else (j, m)


def kosten(con, von, bis, modus="anteilig", liste=None):
    """Fixkosten im Zeitraum als Einzelposten: [{datum, monat, f, netto, steuer, brutto}].

    modus „anteilig“: je Monat der anteilige Betrag; „faellig“: im Monat der tatsächlichen Fälligkeit.
    """
    posten = []
    for f in liste if liste is not None else alle(con):
        if modus == "faellig":
            for d, b in faelligkeiten(f, von, bis):
                if b:
                    posten.append({"datum": d, "monat": d.strftime("%Y-%m"), "f": f, "netto": b["netto"],
                                   "steuer": b["brutto"] - b["netto"], "brutto": b["brutto"]})
        else:
            for j, m in monate(von, bis):
                a = monatsanteil(f, j, m)
                if a:
                    posten.append({"datum": date(j, m, 1), "monat": f"{j}-{m:02d}", "f": f, "netto": a["netto"],
                                   "steuer": a["steuer"], "brutto": a["brutto"]})
    return posten


def uebersicht(con, stichtag=None, liste=None):
    """Summen je Monat (anteilig) und je Jahr nach Kategorie – mit den am Stichtag gültigen Beträgen."""
    stichtag = stichtag or heute_datum()
    kat = {}
    for f in liste if liste is not None else alle(con):
        if not aktiv_am(f, stichtag):
            continue
        b = betrag_am(f, stichtag)
        if not b:
            continue
        teiler = RHYTHMEN[f["rhythmus"]][1]
        k = kat.setdefault(f["kategorie"] or "Sonstiges", {"monat_netto": 0, "monat_brutto": 0, "anzahl": 0})
        k["monat_netto"] += b["netto"] / teiler
        k["monat_brutto"] += b["brutto"] / teiler
        k["anzahl"] += 1
    summe = {"monat_netto": sum(k["monat_netto"] for k in kat.values()),
             "monat_brutto": sum(k["monat_brutto"] for k in kat.values())}
    return {"kategorien": dict(sorted(kat.items(), key=lambda x: -x[1]["monat_brutto"])), "summe": summe}


def naechste_faelligkeit(f, heute=None):
    heute = heute or heute_datum()
    f_ = faelligkeiten(f, heute, plus_monate(heute, 13))
    return f_[0] if f_ else None


def kuendigung_bis(f):
    """Letzter Tag, an dem gekündigt werden kann (Vertragsende minus Kündigungsfrist) – oder None."""
    if not f["ende"] or not f["kuendigung_wert"]:
        return None
    ende = _d(f["ende"])
    if f["kuendigung_einheit"] == "monate":
        return plus_monate(ende, -int(f["kuendigung_wert"]))
    tage = int(f["kuendigung_wert"]) * (7 if f["kuendigung_einheit"] == "wochen" else 1)
    return ende - timedelta(days=tage)


def hinweise(con, heute=None, liste=None, nur_ungelesen=False):
    """Bald endende Verträge und nahende Kündigungsfristen: [{schluessel, text, datum, f}]."""
    heute = heute or heute_datum()
    tage = int(dbm.einstellungen(con).get("fixkosten_hinweis_tage") or 30)
    grenze = heute + timedelta(days=tage)
    gelesen = {r[0] for r in con.execute("SELECT schluessel FROM hinweise_gelesen")} if nur_ungelesen else set()
    ergebnis = []
    for f in liste if liste is not None else alle(con):
        frist = kuendigung_bis(f)
        if frist and heute <= frist <= grenze:
            ergebnis.append({"schluessel": f"fixkosten:{f['id']}:kuendigung:{frist}", "datum": frist, "f": f,
                             "text": f"Kündigungsfrist für „{f['bezeichnung']}“ endet am {frist:%d.%m.%Y}"})
        if f["ende"] and heute <= _d(f["ende"]) <= grenze:
            ergebnis.append({"schluessel": f"fixkosten:{f['id']}:ende:{f['ende']}", "datum": _d(f["ende"]), "f": f,
                             "text": f"Vertrag „{f['bezeichnung']}“ endet am {_d(f['ende']):%d.%m.%Y}"})
    return sorted([h for h in ergebnis if h["schluessel"] not in gelesen], key=lambda h: h["datum"])


def hinweis_gelesen(con, schluessel=None, heute=None):
    """Einen (oder alle aktuellen) Hinweise als gelesen markieren."""
    keys = [schluessel] if schluessel else [h["schluessel"] for h in hinweise(con, heute)]
    for k in keys:
        con.execute("INSERT OR IGNORE INTO hinweise_gelesen (schluessel, gelesen_am) VALUES (?,?)",
                    (k, dbm.jetzt_berlin()))


# ---------------------------------------------------------------------- Bankabgleich

def _woerter(f):
    from .bankabgleich import _normal
    texte = [f["bank_suchbegriff"], f["empfaenger"], f.get("lieferant")]
    return [w for t in texte if t for w in [_normal(t)] if len(w) >= 3]


def bank_vorschlag(con, umsatz, liste=None):
    """Passende Fixkosten-Position für eine Abbuchung: Empfänger/Suchbegriff im Auszug und Betrag."""
    if umsatz["betrag"] >= 0:
        return None
    from .bankabgleich import _normal
    tag = date.fromisoformat(umsatz["buchungstag"][:10])
    text = _normal(" ".join(x for x in (umsatz["name"], umsatz["iban"], umsatz["verwendungszweck"]) if x))
    betrag = -umsatz["betrag"]
    treffer = []
    for f in liste if liste is not None else alle(con):
        if not f["betraege"] or not aktiv_am(f, tag) and not (f["ende"] and tag <= _d(f["ende"]) + timedelta(days=40)):
            continue
        b = betrag_am(f, tag)
        name = any(w in text or w.split(" ")[0] in text for w in _woerter(f))
        gleich = b and b["brutto"] == betrag
        nah = b and abs(b["brutto"] - betrag) <= max(100, b["brutto"] * 0.15)
        if name and gleich:
            treffer.append((0, f, "Empfänger und Betrag passen", True))
        elif name and nah:
            treffer.append((1, f, f"Empfänger passt, Betrag weicht ab (erwartet {euro(b['brutto'])})", False))
        elif gleich and not _woerter(f):
            treffer.append((2, f, "nur der Betrag passt – bitte prüfen", False))
    if not treffer:
        return None
    treffer.sort(key=lambda t: t[0])
    rang, f, grund, sicher = treffer[0]
    return {"f": f, "grund": grund, "sicher": sicher}


def faelliger_monat(f, tag):
    """Zu welcher Fälligkeit gehört eine Abbuchung? Die nächstgelegene (± ein Rhythmus)."""
    abstand = RHYTHMEN[f["rhythmus"]][1]
    kand = faelligkeiten(f, plus_monate(tag, -abstand), plus_monate(tag, abstand))
    if not kand:
        return tag.strftime("%Y-%m")
    return min(kand, key=lambda x: abs((x[0] - tag).days))[0].strftime("%Y-%m")


def bank_zuordnen(con, umsatz_id, fid):
    u = con.execute("SELECT * FROM bank_umsaetze WHERE id=?", (umsatz_id,)).fetchone()
    if not u or u["status"] != "offen" or u["betrag"] >= 0:
        raise EingabeFehler("Der Umsatz ist bereits bearbeitet oder keine Abbuchung.")
    f = eine(con, fid)
    if not f:
        raise EingabeFehler("Bitte eine Fixkosten-Position wählen.")
    monat = faelliger_monat(f, date.fromisoformat(u["buchungstag"][:10]))
    con.execute("UPDATE bank_umsaetze SET status='zugeordnet', fixkosten_id=?, fixkosten_monat=?, bearbeitet_am=?, "
                "bearbeitet_von=? WHERE id=?", (fid, monat, dbm.jetzt_berlin(), dbm.aktueller_benutzer(), umsatz_id))
    dbm.ereignis_erfassen(con, "fixkosten", fid, "Abbuchung zugeordnet",
                          f"{euro(-u['betrag'])} am {u['buchungstag']} (Fälligkeit {monat})")


def bank_loesen(con, umsatz_id):
    u = con.execute("SELECT * FROM bank_umsaetze WHERE id=?", (umsatz_id,)).fetchone()
    if not u or not u["fixkosten_id"]:
        raise EingabeFehler("Diese Buchung ist keiner Fixkosten-Position zugeordnet.")
    con.execute("UPDATE bank_umsaetze SET status='offen', fixkosten_id=NULL, fixkosten_monat=NULL, bearbeitet_am=?, "
                "bearbeitet_von=? WHERE id=?", (dbm.jetzt_berlin(), dbm.aktueller_benutzer(), umsatz_id))
    dbm.ereignis_erfassen(con, "fixkosten", u["fixkosten_id"], "Zuordnung gelöst", f"Bankumsatz vom {u['buchungstag']}")


def zahlungsstand(con, liste=None, heute=None):
    """Erwartete Zahlungen im Zeitraum der eingelesenen Kontoauszüge: bezahlt / abweichend / fehlt.

    Geprüft werden nur Positionen, die über die Bank laufen, und nur Fälligkeiten, für die schon Kontoauszüge
    vorliegen (mit 5 Tagen Spielraum für Lastschriften). Rückgabe: {fixkosten_id: [{datum, monat, erwartet,
    gezahlt, status}]}.
    """
    heute = heute or heute_datum()
    r = con.execute("SELECT MIN(buchungstag), MAX(buchungstag) FROM bank_umsaetze").fetchone()
    if not r[0]:
        return {}
    von, bis = date.fromisoformat(r[0][:10]), date.fromisoformat(r[1][:10]) - timedelta(days=5)
    gezahlt = {}
    for u in con.execute("SELECT fixkosten_id, fixkosten_monat, SUM(-betrag) FROM bank_umsaetze "
                         "WHERE fixkosten_id IS NOT NULL GROUP BY fixkosten_id, fixkosten_monat"):
        gezahlt[(u[0], u[1])] = u[2]
    ergebnis = {}
    for f in liste if liste is not None else alle(con):
        if f["zahlungsart"] not in UEBER_BANK:
            continue
        for d, b in faelligkeiten(f, von, min(bis, heute)):
            monat = d.strftime("%Y-%m")
            g = gezahlt.get((f["id"], monat))
            status = "fehlt" if g is None else "bezahlt" if g == b["brutto"] else "abweichend"
            ergebnis.setdefault(f["id"], []).append({"datum": d, "monat": monat, "erwartet": b["brutto"],
                                                     "gezahlt": g, "status": status})
    return ergebnis
