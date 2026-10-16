"""Finanzübersicht: betriebswirtschaftliche Auswertung je Zeitraum (keine steuerliche Gewinnermittlung / EÜR).

Grundidee: Jede Zahl ist die Summe einzelner Posten (Rechnung, Zahlung, Eingangsrechnung, Kassenbuchung, Fixkosten).
Jeder Posten trägt Schlüssel („umsatz“, „ausgabe:Strom“, „monat:2026-03:einnahmen“ …). So lässt sich jede Zahl per
Klick auf genau die Belege zurückführen, aus denen sie besteht.

- Einnahmen nach Rechnungsdatum: festgeschriebene Rechnungen minus Stornos und Gutschriften (netto/brutto), aufgeteilt
  in Reparaturen & Dienstleistungen, Artikelverkauf, Leihgebühren, KVA-Gebühren (anhand der Positionen).
- Einnahmen nach Zahlungseingang: Zahlungen im Zeitraum, anteilig auf die Kategorien der Rechnung verteilt.
- Ausgaben: Fixkosten (anteilig oder im Fälligkeitsmonat), Eingangsrechnungen (Wareneinsatz bzw. sonstige, nach
  Kostenart; Rechnungen, die zu einer Fixkosten-Position gehören, zählen dort), Kassenausgaben (ohne bar bezahlte
  Eingangsrechnungen – die sind schon als Eingangsrechnung erfasst).
- Kleinunternehmer: Ausgaben brutto (keine Vorsteuer), Umsatzsteuer-Block ausgeblendet. Sonst netto.
"""
import calendar
import csv
import io
from datetime import date, timedelta

from . import db as dbm
from . import fixkosten as fk
from .hilfen import heute_datum
from .logik import positions_betrag

KATEGORIEN_EIN = ["Reparaturen & Dienstleistungen", "Artikelverkauf", "Leihgebühren", "KVA-Gebühren"]
ARTEN = {"monat": "Monat", "quartal": "Quartal", "halbjahr": "Halbjahr", "jahr": "Jahr", "frei": "Zeitraum"}
MONATE = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober", "November",
          "Dezember"]


# ---------------------------------------------------------------------- Zeitraum

def zeitraum(art, jahr=None, nr=None, von=None, bis=None, heute=None):
    """(von, bis, titel) für Monat/Quartal/Halbjahr/Jahr bzw. frei gewählten Zeitraum."""
    heute = heute or heute_datum()
    jahr = int(jahr or heute.year)
    if art == "frei":
        try:
            v, b = date.fromisoformat(von), date.fromisoformat(bis)
        except (TypeError, ValueError):
            v, b = date(heute.year, heute.month, 1), heute
        v, b = min(v, b), max(v, b)
        return v, b, f"{v:%d.%m.%Y} – {b:%d.%m.%Y}"
    if art == "jahr":
        return date(jahr, 1, 1), date(jahr, 12, 31), str(jahr)
    laenge = {"monat": 1, "quartal": 3, "halbjahr": 6}.get(art, 1)
    standard = {"monat": heute.month, "quartal": (heute.month - 1) // 3 + 1, "halbjahr": (heute.month - 1) // 6 + 1}
    nr = int(nr or standard.get(art, heute.month))
    erster = (nr - 1) * laenge + 1
    v = date(jahr, erster, 1)
    letzter = erster + laenge - 1
    b = date(jahr, letzter, calendar.monthrange(jahr, letzter)[1])
    titel = {"monat": f"{MONATE[erster - 1]} {jahr}", "quartal": f"{nr}. Quartal {jahr}",
             "halbjahr": f"{nr}. Halbjahr {jahr}"}.get(art, f"{MONATE[erster - 1]} {jahr}")
    return v, b, titel


def blaettern(art, jahr, nr, schritt):
    """Nachbar-Zeitraum (schritt = −1 / +1): (jahr, nr)."""
    anzahl = {"monat": 12, "quartal": 4, "halbjahr": 2, "jahr": 1}.get(art, 12)
    if art == "jahr":
        return jahr + schritt, 1
    n = (jahr * anzahl + (nr - 1)) + schritt
    return n // anzahl, n % anzahl + 1


def schnellauswahl(heute=None):
    heute = heute or heute_datum()
    q = (heute.month - 1) // 3 + 1
    lm = fk.plus_monate(date(heute.year, heute.month, 1), -1)
    lq_j, lq = (heute.year, q - 1) if q > 1 else (heute.year - 1, 4)
    return [("aktueller Monat", {"art": "monat", "jahr": heute.year, "nr": heute.month}),
            ("letzter Monat", {"art": "monat", "jahr": lm.year, "nr": lm.month}),
            ("aktuelles Quartal", {"art": "quartal", "jahr": heute.year, "nr": q}),
            ("letztes Quartal", {"art": "quartal", "jahr": lq_j, "nr": lq}),
            ("dieses Jahr", {"art": "jahr", "jahr": heute.year}),
            ("letztes Jahr", {"art": "jahr", "jahr": heute.year - 1})]


def _verschieben(von, bis, art):
    """Vorperiode (gleich lang, direkt davor)."""
    if art in ("monat", "quartal", "halbjahr", "jahr"):
        monate_ = (bis.year - von.year) * 12 + bis.month - von.month + 1
        v = fk.plus_monate(von, -monate_)
        b = fk.plus_monate(date(bis.year, bis.month, 1), -monate_)
        return v, date(b.year, b.month, calendar.monthrange(b.year, b.month)[1])
    tage = (bis - von).days + 1
    return von - timedelta(days=tage), von - timedelta(days=1)


def _vorjahr(von, bis):
    def zurueck(d):
        return date(d.year - 1, d.month, min(d.day, calendar.monthrange(d.year - 1, d.month)[1]))
    return zurueck(von), zurueck(bis)


# ---------------------------------------------------------------------- Einzelposten

def _kat_position(p, artikel):
    from .auftraege import KVA_ARTIKEL
    from .leihgeraete import KATALOG
    a = artikel.get(p["artikel_id"]) if p["artikel_id"] else None
    name = (a["name"] if a else "") or ""
    bez = p["bezeichnung"] or ""
    if name == KVA_ARTIKEL or bez.startswith(KVA_ARTIKEL) or bez.startswith("Gebühr Kostenvoranschlag"):
        return "KVA-Gebühren"
    if name in KATALOG.values() or bez.startswith("Leihgerät") or bez.startswith("Schaden Leihgerät"):
        return "Leihgebühren"
    if a and a["typ"] == "material":
        return "Artikelverkauf"
    return "Reparaturen & Dienstleistungen"


def _aufteilung(con, dok_ids):
    """Anteil je Einnahmen-Kategorie pro Beleg (aus den Positionen) und Wareneinsatz laut Positionen."""
    if not dok_ids:
        return {}
    artikel = {a["id"]: a for a in con.execute("SELECT id, name, typ FROM artikel")}
    teile = {}
    platz = ",".join("?" * len(dok_ids))
    for p in con.execute(f"SELECT * FROM positionen WHERE dokument_id IN ({platz})", list(dok_ids)):
        t = teile.setdefault(p["dokument_id"], {"kat": {}, "teilekosten": 0})
        k = _kat_position(p, artikel)
        t["kat"][k] = t["kat"].get(k, 0) + positions_betrag(p["menge"], p["einzelpreis"])
        t["teilekosten"] += int(round((p["teilekosten"] or 0) * (p["menge"] or 0)))
    return teile


def _verteilen(gesamt, kat):
    """Betrag nach Anteilen aufteilen (Rundungsrest auf die größte Kategorie)."""
    summe = sum(kat.values())
    if not kat or not summe:
        return {"Reparaturen & Dienstleistungen": gesamt}
    teile = {k: int(round(gesamt * v / summe)) for k, v in kat.items()}
    rest = gesamt - sum(teile.values())
    if rest:
        groesste = max(teile, key=lambda k: abs(teile[k]))
        teile[groesste] += rest
    return teile


DOK_SQL = ("SELECT d.*, k.firma, k.vorname, k.nachname, k.typ AS ktyp FROM dokumente d "
           "LEFT JOIN kunden k ON k.id=d.kunde_id ")


def _dokname(d):
    from .hilfen import kunde_name
    return kunde_name({**dict(d), "typ": d["ktyp"]}) if d["kunde_id"] else ""


def posten(con, von, bis, basis="rechnung", fix_modus="anteilig", ku=False):
    """Alle Einzelposten im Zeitraum. Jeder Posten: datum, monat, art, text, kategorie, gruppe, netto, steuer,
    brutto, wert (netto bzw. bei Kleinunternehmer brutto für Ausgaben), url-Teile, schluessel (set)."""
    v, b = von.isoformat(), bis.isoformat()
    liste = []

    def neu(datum, art, text, kategorie, gruppe, netto, steuer, brutto, ziel, *zusatz):
        datum = datum if isinstance(datum, date) else date.fromisoformat(datum[:10])
        wert = brutto if (ku and gruppe != "einnahme") else netto
        monat = datum.strftime("%Y-%m")
        s = {gruppe, f"{gruppe}:{kategorie}", f"monat:{monat}:{gruppe}", *zusatz}
        if gruppe in ("fixkosten", "wareneinsatz", "sonstige"):
            s |= {"ausgaben", f"ausgabe:{kategorie}", f"monat:{monat}:ausgaben"}
        liste.append({"datum": datum, "monat": monat, "art": art, "text": text, "kategorie": kategorie,
                      "gruppe": gruppe, "netto": netto, "steuer": steuer, "brutto": brutto, "wert": wert,
                      "ziel": ziel, "schluessel": s})

    # Einnahmen
    if basis == "zahlung":
        zahlungen = con.execute(
            "SELECT z.*, d.nummer, d.typ AS dtyp, d.summe_netto, d.summe_steuer, d.summe_brutto, d.kunde_id, "
            "k.firma, k.vorname, k.nachname, k.typ AS ktyp FROM zahlungen z JOIN dokumente d ON d.id=z.dokument_id "
            "LEFT JOIN kunden k ON k.id=d.kunde_id WHERE z.storniert_am IS NULL AND z.datum BETWEEN ? AND ?",
            (v, b)).fetchall()
        aufteilung = _aufteilung(con, {z["dokument_id"] for z in zahlungen})
        for z in zahlungen:
            faktor = z["summe_netto"] / z["summe_brutto"] if z["summe_brutto"] else 1
            netto = int(round(z["betrag"] * faktor))
            kat = aufteilung.get(z["dokument_id"], {}).get("kat", {})
            for k, teil in _verteilen(netto, kat).items():
                anteil = teil / netto if netto else 0
                neu(z["datum"], "Zahlungseingang", f"{z['nummer']} · {_dokname(z)}", k, "einnahme", teil,
                    int(round((z["betrag"] - netto) * anteil)), int(round(z["betrag"] * anteil)),
                    ("dokument", z["dokument_id"]), "umsatz", f"umsatz:{k}", "zufluss")
    else:
        doks = con.execute(DOK_SQL + "WHERE d.typ IN ('rechnung', 'storno', 'gutschrift') AND d.status<>'entwurf' "
                           "AND d.datum BETWEEN ? AND ?", (v, b)).fetchall()
        aufteilung = _aufteilung(con, {d["id"] for d in doks})
        for d in doks:
            kat = aufteilung.get(d["id"], {}).get("kat", {})
            netto_teile = _verteilen(d["summe_netto"], kat)
            for k, teil in netto_teile.items():
                anteil = teil / d["summe_netto"] if d["summe_netto"] else 1
                art = {"rechnung": "Rechnung", "storno": "Storno", "gutschrift": "Gutschrift"}[d["typ"]]
                neu(d["datum"], art, f"{d['nummer']} · {_dokname(d)}", k, "einnahme", teil,
                    int(round(d["summe_steuer"] * anteil)), int(round(d["summe_brutto"] * anteil)),
                    ("dokument", d["id"]), "umsatz", f"umsatz:{k}")

    # Eingangsrechnungen (Wareneinsatz / sonstige; Rechnungen zu Fixkosten zählen bei den Fixkosten)
    einst = dbm.einstellungen(con)
    waren = {k.strip() for k in (einst.get("wareneinsatz_kostenarten") or "").splitlines() if k.strip()}
    if basis == "zahlung":
        ers = con.execute(
            "SELECT z.datum AS datum, z.betrag AS betrag, e.id, e.lfd_nr, e.nummer, e.netto, e.steuer, e.brutto, "
            "e.kostenart, e.fixkosten_id, COALESCE(l.name, e.lieferant_name) AS lieferant FROM er_zahlungen z "
            "JOIN eingangsrechnungen e ON e.id=z.eingangsrechnung_id LEFT JOIN lieferanten l ON l.id=e.lieferant_id "
            "WHERE z.storniert_am IS NULL AND z.datum BETWEEN ? AND ?", (v, b)).fetchall()
    else:
        ers = con.execute(
            "SELECT e.datum AS datum, e.brutto AS betrag, e.id, e.lfd_nr, e.nummer, e.netto, e.steuer, e.brutto, "
            "e.kostenart, e.fixkosten_id, COALESCE(l.name, e.lieferant_name) AS lieferant FROM eingangsrechnungen e "
            "LEFT JOIN lieferanten l ON l.id=e.lieferant_id WHERE e.status<>'storniert' AND e.datum BETWEEN ? AND ?",
            (v, b)).fetchall()
    for e in ers:
        if e["fixkosten_id"]:
            continue
        faktor = e["betrag"] / e["brutto"] if e["brutto"] else 1
        kat = e["kostenart"] or "Sonstiges"
        neu(e["datum"], "Eingangsrechnung", f"{e['lfd_nr']} · {e['lieferant'] or ''} {e['nummer'] or ''}".strip(), kat,
            "wareneinsatz" if kat in waren else "sonstige", int(round(e["netto"] * faktor)),
            int(round(e["steuer"] * faktor)), e["betrag"], ("eingangsrechnung", e["id"]), "er")

    # Kassenausgaben (ohne bar bezahlte Eingangsrechnungen) inkl. ihrer Gegenbuchungen
    for k in con.execute(
            "SELECT k.*, COALESCE(o.kostenart, k.kostenart) AS kart, COALESCE(o.steuersatz, k.steuersatz) AS satz "
            "FROM kassenbuch k LEFT JOIN kassenbuch o ON o.id=k.gegenbuchung_zu WHERE k.datum BETWEEN ? AND ? AND ("
            "(k.art='ausgabe' AND k.er_zahlung_id IS NULL) OR (k.art='gegenbuchung' AND o.art='ausgabe' "
            "AND o.er_zahlung_id IS NULL))", (v, b)):
        brutto = -k["betrag"]
        satz = float(k["satz"] or 0)
        netto = int(round(brutto * 100 / (100 + satz))) if satz else brutto
        kat = k["kart"] or "Sonstiges"
        neu(k["datum"], "Kassenbuchung", f"Nr. {k['lfd_nr']} · {k['text']}", kat,
            "wareneinsatz" if kat in waren else "sonstige", netto, brutto - netto, brutto, ("kasse", k["id"]), "kasse")

    # Fixkosten
    for p in fk.kosten(con, von, bis, fix_modus):
        f = p["f"]
        neu(p["datum"], "Fixkosten", f"{f['bezeichnung']} ({fk.RHYTHMEN[f['rhythmus']][0]}"
            + (", anteilig)" if fix_modus == "anteilig" else ")"), f["kategorie"] or "Sonstiges", "fixkosten",
            int(round(p["netto"])), int(round(p["steuer"])), int(round(p["brutto"])), ("fixkosten", f["id"]))
    return liste


# ---------------------------------------------------------------------- Auswertung

def _summe(liste, schluessel, feld="wert"):
    return sum(p[feld] for p in liste if schluessel in p["schluessel"])


def kennzahlen(con, von, bis, basis="rechnung", fix_modus="anteilig", ku=None, liste=None):
    if ku is None:
        ku = dbm.einstellungen(con).get("steuer_modus") != "regel"
    liste = posten(con, von, bis, basis, fix_modus, ku) if liste is None else liste
    umsatz = _summe(liste, "einnahme", "netto")
    waren = _summe(liste, "wareneinsatz")
    fix = _summe(liste, "fixkosten")
    sonst = _summe(liste, "sonstige")
    rohertrag = umsatz - waren
    return {
        "umsatz_netto": umsatz, "umsatz_brutto": _summe(liste, "einnahme", "brutto"),
        "umsatz_kat": {k: _summe(liste, f"einnahme:{k}", "netto") for k in KATEGORIEN_EIN},
        "fixkosten": fix, "wareneinsatz": waren, "sonstige": sonst,
        "kasse": _summe(liste, "kasse"), "er": _summe(liste, "er"),
        "ausgaben": fix + waren + sonst, "rohertrag": rohertrag, "ergebnis": rohertrag - fix - sonst,
        "ust": _summe(liste, "einnahme", "steuer"),
        "vorsteuer": sum(p["steuer"] for p in liste if "ausgaben" in p["schluessel"]),
    }


def _zufluss(con, von, bis):
    zeilen = con.execute(
        "SELECT z.*, d.nummer, d.kunde_id, k.firma, k.vorname, k.nachname, k.typ AS ktyp FROM zahlungen z "
        "JOIN dokumente d ON d.id=z.dokument_id LEFT JOIN kunden k ON k.id=d.kunde_id "
        "WHERE z.storniert_am IS NULL AND z.datum BETWEEN ? AND ? ORDER BY z.datum", (von.isoformat(),
                                                                                   bis.isoformat())).fetchall()
    return sum(z["betrag"] for z in zeilen), zeilen


def offene_posten_stichtag(con, stichtag):
    """Offene Forderungen und Verbindlichkeiten zum Stichtag (Zahlungen bis einschließlich Stichtag)."""
    s = stichtag.isoformat()
    ford = []
    for d in con.execute(
            DOK_SQL + "WHERE d.typ='rechnung' AND d.status='festgeschrieben' AND d.datum<=?", (s,)).fetchall():
        bezahlt = con.execute("SELECT COALESCE(SUM(betrag), 0) FROM zahlungen WHERE dokument_id=? AND datum<=? "
                              "AND storniert_am IS NULL", (d["id"], s)).fetchone()[0]
        gut = con.execute("SELECT COALESCE(SUM(summe_brutto), 0) FROM dokumente WHERE bezug_id=? AND typ='gutschrift' "
                          "AND status<>'entwurf' AND datum<=?", (d["id"], s)).fetchone()[0]
        offen = d["summe_brutto"] + gut - bezahlt
        if offen > 0:
            ford.append({"d": d, "offen": offen})
    verb = []
    for e in con.execute(
            "SELECT e.*, COALESCE(l.name, e.lieferant_name) AS lieferant FROM eingangsrechnungen e LEFT JOIN "
            "lieferanten l ON l.id=e.lieferant_id WHERE e.status<>'storniert' AND e.datum<=?", (s,)).fetchall():
        bezahlt = con.execute("SELECT COALESCE(SUM(betrag), 0) FROM er_zahlungen WHERE eingangsrechnung_id=? AND "
                              "datum<=? AND storniert_am IS NULL", (e["id"], s)).fetchone()[0]
        if e["brutto"] - bezahlt > 0:
            verb.append({"e": e, "offen": e["brutto"] - bezahlt})
    return ford, verb


def auftraege(con, von, bis):
    """Abgeschlossene Aufträge im Zeitraum, Ø Auftragswert (netto, laut Rechnung) und Ø Marge der Rechnungen."""
    a = con.execute(
        "SELECT a.*, d.summe_netto AS re_netto, d.nummer AS re_nummer FROM auftraege a LEFT JOIN dokumente d "
        "ON d.id=a.rechnung_id AND d.status='festgeschrieben' WHERE a.status='erledigt' AND "
        "substr(a.erledigt_am, 1, 10) BETWEEN ? AND ?", (von.isoformat(), bis.isoformat())).fetchall()
    mit_wert = [x["re_netto"] for x in a if x["re_netto"]]
    doks = [d["id"] for d in con.execute("SELECT id FROM dokumente WHERE typ IN ('rechnung', 'storno', 'gutschrift') "
                                         "AND status<>'entwurf' AND "
                                         "datum BETWEEN ? AND ?", (von.isoformat(), bis.isoformat()))]
    teile = _aufteilung(con, set(doks))
    netto = sum(sum(t["kat"].values()) for t in teile.values())
    kosten = sum(t["teilekosten"] for t in teile.values())
    return {"anzahl": len(a), "liste": a, "durchschnitt": int(sum(mit_wert) / len(mit_wert)) if mit_wert else 0,
            "marge": (netto - kosten) / netto * 100 if netto else None, "marge_euro": netto - kosten}


def monatstabelle(liste, von, bis):
    zeilen = []
    for j, m in fk.monate(von, bis):
        key = f"{j}-{m:02d}"
        ein = sum(p["netto"] for p in liste if p["monat"] == key and p["gruppe"] == "einnahme")
        fix = sum(p["wert"] for p in liste if p["monat"] == key and p["gruppe"] == "fixkosten")
        waren = sum(p["wert"] for p in liste if p["monat"] == key and p["gruppe"] == "wareneinsatz")
        sonst = sum(p["wert"] for p in liste if p["monat"] == key and p["gruppe"] == "sonstige")
        zeilen.append({"monat": key, "titel": f"{MONATE[m - 1]} {j}", "kurz": MONATE[m - 1][:3], "einnahmen": ein,
                       "fixkosten": fix, "wareneinsatz": waren, "sonstige": sonst, "ausgaben": fix + waren + sonst,
                       "ergebnis": ein - fix - waren - sonst})
    return zeilen


def kategorien_ausgaben(liste):
    kat = {}
    for p in liste:
        if "ausgaben" in p["schluessel"]:
            k = kat.setdefault(p["kategorie"], {"wert": 0, "gruppen": set()})
            k["wert"] += p["wert"]
            k["gruppen"].add(p["gruppe"])
    return sorted(([k, v["wert"], v["gruppen"]] for k, v in kat.items()), key=lambda x: -x[1])


def break_even(con, heute=None, ku=False):
    """Fixkosten je Monat, nötiger Umsatz (über die Rohertragsquote der letzten 12 Monate) und Stand im Monat."""
    heute = heute or heute_datum()
    monat_von = date(heute.year, heute.month, 1)
    monat_bis = date(heute.year, heute.month, calendar.monthrange(heute.year, heute.month)[1])
    fix = sum(p["brutto" if ku else "netto"] for p in fk.kosten(con, monat_von, monat_bis, "anteilig"))
    j_von = fk.plus_monate(monat_von, -12)
    k12 = kennzahlen(con, j_von, monat_von - timedelta(days=1), ku=ku)
    quote = k12["rohertrag"] / k12["umsatz_netto"] if k12["umsatz_netto"] > 0 and k12["rohertrag"] > 0 else 1.0
    jetzt = kennzahlen(con, monat_von, monat_bis, ku=ku)
    return {"fixkosten": fix, "quote": quote, "noetiger_umsatz": int(fix / quote) if quote else fix,
            "umsatz": jetzt["umsatz_netto"], "rohertrag": jetzt["rohertrag"],
            "prozent": min(100.0, jetzt["rohertrag"] / fix * 100) if fix else 100.0,
            "fehlt": max(0, fix - jetzt["rohertrag"]), "monat": f"{MONATE[heute.month - 1]} {heute.year}"}


def vorschau(con, heute=None, ku=False):
    """Nächste 3 Monate: anstehende Fixkosten (fällig) und erwartete Eingänge aus offenen Rechnungen."""
    heute = heute or heute_datum()
    from .zahlungen import offene_posten
    offene = offene_posten(con)
    ergebnis = []
    for i in range(3):
        start = fk.plus_monate(date(heute.year, heute.month, 1), i)
        ende = date(start.year, start.month, calendar.monthrange(start.year, start.month)[1])
        fix = [(d, f, b) for f in fk.alle(con) for d, b in fk.faelligkeiten(f, max(start, heute), ende) if b]
        ein = [p for p in offene if (i == 0 and (p["d"]["faellig_am"] or "") <= ende.isoformat())
               or (i > 0 and start.isoformat() <= (p["d"]["faellig_am"] or "") <= ende.isoformat())]
        ergebnis.append({"titel": f"{MONATE[start.month - 1]} {start.year}",
                         "fixkosten": sorted(fix, key=lambda x: x[0]),
                         "fix_summe": sum(b["brutto"] for _, _, b in fix),
                         "eingaenge": ein, "ein_summe": sum(p["s"]["offen"] for p in ein)})
    return ergebnis


def vergleich(aktuell, vorher):
    """Veränderung je Kennzahl: (Differenz, Prozent oder None)."""
    ergebnis = {}
    for k in ("umsatz_netto", "ausgaben", "rohertrag", "ergebnis", "fixkosten", "wareneinsatz", "sonstige"):
        d = aktuell[k] - vorher[k]
        ergebnis[k] = (d, d / abs(vorher[k]) * 100 if vorher[k] else None)
    return ergebnis


def auswertung(con, art="monat", jahr=None, nr=None, von=None, bis=None, basis="rechnung", fix_modus="anteilig",
               vergleich_mit="vorjahr", heute=None):
    heute = heute or heute_datum()
    v, b, titel = zeitraum(art, jahr, nr, von, bis, heute)
    ku = dbm.einstellungen(con).get("steuer_modus") != "regel"
    liste = posten(con, v, b, basis, fix_modus, ku)
    k = kennzahlen(con, v, b, basis, fix_modus, ku, liste)
    vv, vb = _vorjahr(v, b) if vergleich_mit == "vorjahr" else _verschieben(v, b, art)
    k_vor = kennzahlen(con, vv, vb, basis, fix_modus, ku)
    stichtag = min(b, heute)
    ford, verb = offene_posten_stichtag(con, stichtag)
    zufluss, _ = _zufluss(con, v, b)
    return {"von": v, "bis": b, "titel": titel, "art": art, "basis": basis, "fix_modus": fix_modus, "ku": ku,
            "liste": liste, "k": k, "k_vor": k_vor, "vor_von": vv, "vor_bis": vb, "vergleich_mit": vergleich_mit,
            "diff": vergleich(k, k_vor), "monate": monatstabelle(liste, v, b),
            "kategorien": kategorien_ausgaben(liste), "stichtag": stichtag,
            "forderungen": ford, "verbindlichkeiten": verb, "zufluss": zufluss,
            "auftraege": auftraege(con, v, b)}


# ---------------------------------------------------------------------- Belege zu einer Zahl

def belege(con, schluessel, art="monat", jahr=None, nr=None, von=None, bis=None, basis="rechnung",
           fix_modus="anteilig", heute=None):
    """Einzelposten hinter einer Zahl. Sonderfälle: Zufluss, Forderungen, Verbindlichkeiten, Aufträge."""
    heute = heute or heute_datum()
    v, b, titel = zeitraum(art, jahr, nr, von, bis, heute)
    ku = dbm.einstellungen(con).get("steuer_modus") != "regel"
    if schluessel == "zufluss":
        _, zeilen = _zufluss(con, v, b)
        return titel, [{"datum": date.fromisoformat(z["datum"]), "art": "Zahlungseingang",
                        "text": f"{z['nummer']} · {_dokname(z)}", "kategorie": z["zahlart"], "wert": z["betrag"],
                        "ziel": ("dokument", z["dokument_id"])} for z in zeilen]
    if schluessel in ("forderungen", "verbindlichkeiten"):
        ford, verb = offene_posten_stichtag(con, min(b, heute))
        if schluessel == "forderungen":
            return titel, [{"datum": date.fromisoformat(x["d"]["datum"]), "art": "Rechnung",
                            "text": f"{x['d']['nummer']} · {_dokname(x['d'])}", "kategorie": "offen",
                            "wert": x["offen"], "ziel": ("dokument", x["d"]["id"])} for x in ford]
        return titel, [{"datum": date.fromisoformat(x["e"]["datum"]), "art": "Eingangsrechnung",
                        "text": f"{x['e']['lfd_nr']} · {x['e']['lieferant'] or ''}", "kategorie": "offen",
                        "wert": x["offen"], "ziel": ("eingangsrechnung", x["e"]["id"])} for x in verb]
    if schluessel == "auftraege":
        a = auftraege(con, v, b)
        return titel, [{"datum": date.fromisoformat(x["erledigt_am"][:10]), "art": "Auftrag",
                        "text": f"{x['auftragsnr']} · {x['geraet'] or ''}"
                        + (f" · Rechnung {x['re_nummer']}" if x["re_nummer"] else ""), "kategorie": "erledigt",
                        "wert": x["re_netto"] or 0, "ziel": ("auftrag", x["id"])} for x in a["liste"]]
    liste = posten(con, v, b, basis, fix_modus, ku)
    feld = "steuer" if schluessel in ("ust", "vorsteuer") else None
    if schluessel == "ust":
        schluessel = "einnahme"
    elif schluessel == "vorsteuer":
        schluessel = "ausgaben"
    treffer = [dict(p, wert=p[feld] if feld else (p["netto"] if p["gruppe"] == "einnahme" else p["wert"]))
               for p in liste if schluessel in p["schluessel"]]
    return titel, sorted(treffer, key=lambda p: (p["datum"], p["art"]))


# ---------------------------------------------------------------------- Diagramme (SVG, ohne Fremdbibliothek)

def _achse(maximum):
    """Obergrenze der Achse: 4 Gitterlinien mit „runden“ Schritten (1, 2, 2,5, 3, 4, 5, 6, 8 × 10ⁿ)."""
    import math
    if maximum <= 0:
        return 100_00
    roh = maximum / 4
    groesse = 10 ** math.floor(math.log10(roh))
    schritt = next(f * groesse for f in (1, 2, 2.5, 3, 4, 5, 6, 8, 10) if f * groesse >= roh)
    return int(schritt * 4)


def _euro_kurz(cent):
    w = cent / 100
    if abs(w) >= 10000:
        return f"{w / 1000:,.0f} T€".replace(",", ".")
    return f"{w:,.0f} €".replace(",", ".")


def svg_balken(monate_):
    """Einnahmen vs. Ausgaben je Monat (gruppierte Balken)."""
    from markupsafe import Markup, escape
    if not monate_:
        return Markup("")
    breite, hoehe, links, unten, oben = 720, 240, 56, 26, 10
    maximum = _achse(max([m["einnahmen"] for m in monate_] + [m["ausgaben"] for m in monate_] + [1]))
    min_wert = min([0] + [m["einnahmen"] for m in monate_])
    unten_wert = -_achse(-min_wert) if min_wert < 0 else 0
    spanne = maximum - unten_wert
    y = lambda w: oben + (maximum - w) / spanne * (hoehe - oben - unten)  # noqa: E731
    feld = (breite - links - 10) / len(monate_)
    bw = min(26, feld * 0.32)
    teile = [f'<svg class="diagramm" viewBox="0 0 {breite} {hoehe}" role="img" aria-label="Einnahmen und Ausgaben je '
             f'Monat">']
    for i in range(5):
        w = unten_wert + spanne * i / 4
        teile.append(f'<line class="gitter" x1="{links}" x2="{breite - 10}" y1="{y(w):.1f}" y2="{y(w):.1f}"/>'
                     f'<text class="achse" x="{links - 6}" y="{y(w) + 4:.1f}" text-anchor="end">{_euro_kurz(w)}</text>')
    null = y(0)
    for i, m in enumerate(monate_):
        x0 = links + feld * i + feld / 2
        for wert, klasse, dx, name in ((m["einnahmen"], "ein", -bw - 1, "Einnahmen"),
                                       (m["ausgaben"], "aus", 1, "Ausgaben")):
            top, h = (y(wert), null - y(wert)) if wert >= 0 else (null, y(wert) - null)
            r = min(4, bw / 2, max(h, 0))
            teile.append(f'<g class="marke"><title>{escape(m["titel"])} – {name}: {_euro_kurz(wert)}</title>'
                         f'<rect class="treffer" x="{x0 + dx - 2:.1f}" y="{oben}" width="{bw + 4:.1f}" '
                         f'height="{hoehe - oben - unten}"/>'
                         f'<rect class="{klasse}" x="{x0 + dx:.1f}" y="{top:.1f}" width="{bw:.1f}" height="{max(h, 0.5):.1f}" '
                         f'rx="{r:.1f}"/></g>')
        teile.append(f'<text class="achse" x="{x0:.1f}" y="{hoehe - 8}" text-anchor="middle">{m["kurz"]}</text>')
    teile.append(f'<line class="null" x1="{links}" x2="{breite - 10}" y1="{null:.1f}" y2="{null:.1f}"/></svg>')
    return Markup("".join(teile))


def svg_linie(monate_):
    """Ergebnisverlauf (Linie mit Punkten, Nulllinie)."""
    from markupsafe import Markup, escape
    if not monate_:
        return Markup("")
    breite, hoehe, links, unten, oben = 720, 200, 56, 26, 12
    werte = [m["ergebnis"] for m in monate_]
    maximum, minimum = _achse(max(werte + [1])), -_achse(-min(werte + [0])) if min(werte) < 0 else 0
    spanne = maximum - minimum or 1
    y = lambda w: oben + (maximum - w) / spanne * (hoehe - oben - unten)  # noqa: E731
    feld = (breite - links - 10) / len(monate_)
    xs = [links + feld * i + feld / 2 for i in range(len(monate_))]
    teile = [f'<svg class="diagramm" viewBox="0 0 {breite} {hoehe}" role="img" aria-label="Ergebnis je Monat">']
    for i in range(5):
        w = minimum + spanne * i / 4
        teile.append(f'<line class="gitter" x1="{links}" x2="{breite - 10}" y1="{y(w):.1f}" y2="{y(w):.1f}"/>'
                     f'<text class="achse" x="{links - 6}" y="{y(w) + 4:.1f}" text-anchor="end">{_euro_kurz(w)}</text>')
    teile.append(f'<line class="null" x1="{links}" x2="{breite - 10}" y1="{y(0):.1f}" y2="{y(0):.1f}"/>')
    if len(xs) > 1:
        teile.append('<polyline class="linie" points="' + " ".join(f"{x:.1f},{y(w):.1f}" for x, w in zip(xs, werte))
                     + '"/>')
    for x, w, m in zip(xs, werte, monate_):
        teile.append(f'<g class="marke"><title>{escape(m["titel"])} – Ergebnis: {_euro_kurz(w)}</title>'
                     f'<circle class="treffer" cx="{x:.1f}" cy="{y(w):.1f}" r="14"/>'
                     f'<circle class="punkt{" neg" if w < 0 else ""}" cx="{x:.1f}" cy="{y(w):.1f}" r="4.5"/></g>'
                     f'<text class="achse" x="{x:.1f}" y="{hoehe - 8}" text-anchor="middle">{m["kurz"]}</text>')
    teile.append("</svg>")
    return Markup("".join(teile))


# ---------------------------------------------------------------------- Export

def csv_export(a):
    puffer = io.StringIO()
    w = csv.writer(puffer, delimiter=";", lineterminator="\r\n")
    euro_ = lambda c: f"{c / 100:.2f}".replace(".", ",")  # noqa: E731
    w.writerow(["Finanzübersicht", a["titel"], f"{a['von']:%d.%m.%Y}", f"{a['bis']:%d.%m.%Y}"])
    w.writerow(["Hinweis", "Betriebswirtschaftliche Übersicht – nicht die steuerliche Gewinnermittlung bzw. EÜR"])
    w.writerow([])
    w.writerow(["Kennzahl", "Betrag (€)", "Vergleich (€)", "Veränderung (€)"])
    k, kv = a["k"], a["k_vor"]
    for name, key in (("Umsatz netto", "umsatz_netto"), ("Wareneinsatz", "wareneinsatz"), ("Rohertrag", "rohertrag"),
                      ("Fixkosten", "fixkosten"), ("Sonstige Ausgaben", "sonstige"), ("Ergebnis", "ergebnis")):
        w.writerow([name, euro_(k[key]), euro_(kv[key]), euro_(k[key] - kv[key])])
    w.writerow(["Umsatz brutto", euro_(k["umsatz_brutto"])])
    w.writerow(["Zahlungseingänge", euro_(a["zufluss"])])
    for kat, wert in k["umsatz_kat"].items():
        w.writerow([f"Umsatz: {kat}", euro_(wert)])
    if not a["ku"]:
        w.writerow(["Umsatzsteuer", euro_(k["ust"])])
        w.writerow(["Vorsteuer", euro_(k["vorsteuer"])])
        w.writerow(["Zahllast (Orientierung)", euro_(k["ust"] - k["vorsteuer"])])
    w.writerow([])
    w.writerow(["Monat", "Einnahmen", "Fixkosten", "Wareneinsatz", "Sonstige Ausgaben", "Ergebnis"])
    for m in a["monate"]:
        w.writerow([m["titel"], euro_(m["einnahmen"]), euro_(m["fixkosten"]), euro_(m["wareneinsatz"]),
                    euro_(m["sonstige"]), euro_(m["ergebnis"])])
    w.writerow(["Summe", euro_(sum(m["einnahmen"] for m in a["monate"])),
                euro_(sum(m["fixkosten"] for m in a["monate"])), euro_(sum(m["wareneinsatz"] for m in a["monate"])),
                euro_(sum(m["sonstige"] for m in a["monate"])), euro_(sum(m["ergebnis"] for m in a["monate"]))])
    w.writerow([])
    w.writerow(["Ausgaben nach Kategorie", "Betrag (€)"])
    for kat, wert, _ in a["kategorien"]:
        w.writerow([kat, euro_(wert)])
    w.writerow([])
    w.writerow(["Datum", "Art", "Beleg", "Kategorie", "Gruppe", "Netto", "Steuer", "Brutto"])
    for p in sorted(a["liste"], key=lambda p: p["datum"]):
        w.writerow([f"{p['datum']:%d.%m.%Y}", p["art"], p["text"], p["kategorie"], p["gruppe"], euro_(p["netto"]),
                    euro_(p["steuer"]), euro_(p["brutto"])])
    return ("﻿" + puffer.getvalue()).encode("utf-8")  # BOM: Excel erkennt Umlaute


def pdf_export(a, firma=""):
    from . import verfahrensdoku as vd
    from .hilfen import euro
    k, kv = a["k"], a["k_vor"]
    vgl = "Vorjahr" if a["vergleich_mit"] == "vorjahr" else "Vorperiode"
    kennz = [["Kennzahl", "Betrag", vgl, "Veränderung"]]
    for name, key in (("Umsatz netto", "umsatz_netto"), ("Wareneinsatz", "wareneinsatz"), ("Rohertrag", "rohertrag"),
                      ("Fixkosten", "fixkosten"), ("Sonstige Ausgaben", "sonstige"), ("Ergebnis", "ergebnis")):
        d, p = a["diff"].get(key, (k[key] - kv[key], None))
        kennz.append([name, euro(k[key]), euro(kv[key]), euro(d) + (f" ({p:+.1f} %)" if p is not None else "")])
    monate_ = [["Monat", "Einnahmen", "Fixkosten", "Wareneinsatz", "Sonstige", "Ergebnis"]] + [
        [m["titel"], euro(m["einnahmen"]), euro(m["fixkosten"]), euro(m["wareneinsatz"]), euro(m["sonstige"]),
         euro(m["ergebnis"])] for m in a["monate"]]
    monate_.append(["Summe"] + [euro(sum(m[x] for m in a["monate"])) for x in ("einnahmen", "fixkosten",
                                                                                "wareneinsatz", "sonstige", "ergebnis")])
    abschnitte = [
        ("Hinweis", [f"Zeitraum {a['von']:%d.%m.%Y} bis {a['bis']:%d.%m.%Y}. Einnahmen "
                     + ("nach Zahlungseingang" if a["basis"] == "zahlung" else "nach Rechnungsdatum")
                     + ", Fixkosten " + ("anteilig verteilt" if a["fix_modus"] == "anteilig" else "im Fälligkeitsmonat")
                     + ". Betriebswirtschaftliche Übersicht – nicht die steuerliche Gewinnermittlung bzw. EÜR."
                     + (" Ausgaben brutto (Kleinunternehmer, keine Vorsteuer)." if a["ku"] else " Beträge netto.")]),
        ("Kennzahlen", [("tabelle", kennz)]),
        ("Umsatz nach Bereich", [("tabelle", [["Bereich", "netto"]] + [[kat, euro(w)] for kat, w in
                                                                       k["umsatz_kat"].items()])]),
        ("Monate", [("tabelle", monate_)]),
        ("Ausgaben nach Kategorie", [("tabelle", [["Kategorie", "Betrag"]] + [[kat, euro(w)] for kat, w, _ in
                                                                             a["kategorien"]])]),
        ("Offene Posten zum " + f"{a['stichtag']:%d.%m.%Y}",
         [("tabelle", [["", "Betrag"], ["Offene Forderungen", euro(sum(x["offen"] for x in a["forderungen"]))],
                       ["Offene Verbindlichkeiten", euro(sum(x["offen"] for x in a["verbindlichkeiten"]))]])]),
    ]
    if not a["ku"]:
        abschnitte.append(("Umsatzsteuer (Orientierung)", [("tabelle", [
            ["", "Betrag"], ["Umsatzsteuer", euro(k["ust"])], ["Vorsteuer", euro(k["vorsteuer"])],
            ["Voraussichtliche Zahllast", euro(k["ust"] - k["vorsteuer"])]])]))
    return vd.pdf(abschnitte, firma, titel=f"Finanzübersicht – {a['titel']}")
