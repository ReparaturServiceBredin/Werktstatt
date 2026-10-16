"""Katalog „Leistungen und Artikel“: manuell eingegebene Positionen automatisch übernehmen.

- Gleiche Bezeichnung (ohne Unterschied bei Groß-/Kleinschreibung und Leerzeichen) = derselbe Eintrag.
- Fehlt der Einkaufspreis, bleibt die Marge leer (statt 0 % oder 100 % anzunehmen).
"""
from . import db as dbm

EINHEITEN_LEISTUNG = {"std.", "std", "stunde", "stunden", "pauschal", "psch.", "km", "monat", "monatlich"}


def schluessel(name):
    """Vergleichsschlüssel: Leerzeichen zusammenfassen, Groß-/Kleinschreibung ignorieren."""
    return " ".join((name or "").split()).casefold()


def finden(con, name):
    k = schluessel(name)
    if not k:
        return None
    for a in con.execute("SELECT * FROM artikel"):
        if schluessel(a["name"]) == k:
            return a
    return None


def typ_raten(einheit, teilekosten):
    if (einheit or "").strip().lower() in EINHEITEN_LEISTUNG:
        return "leistung"
    return "material" if teilekosten else "leistung"


def marge(preis, einkauf, ek_unbekannt=False):
    """(Marge in Cent, Marge in % vom Verkaufspreis) – (None, None), wenn der Einkaufspreis unbekannt ist."""
    if ek_unbekannt or einkauf is None:
        return None, None
    m = int(preis or 0) - int(einkauf or 0)
    return m, (round(m * 100 / preis, 1) if preis else None)


def aufschlag(preis, einkauf):
    if not einkauf:
        return None
    return round((preis - einkauf) * 100 / einkauf, 1)


def anlegen(con, daten):
    """Neuen Katalogeintrag aus Positionsdaten anlegen. Muss in einer Transaktion laufen. Gibt die ID zurück."""
    ek_bekannt = daten.get("teilekosten") is not None
    ek = int(daten.get("teilekosten") or 0)
    cur = con.execute(
        "INSERT INTO artikel (name, beschreibung, leistungsart, typ, einheit, preis, teilekosten, aufschlag_prozent, "
        "steuersatz, ek_unbekannt, aktiv, erstellt_am, geaendert_am) VALUES (?,?,?,?,?,?,?,?,?,?,1,?,?)",
        (" ".join(daten["bezeichnung"].split()), daten.get("beschreibung") or "", daten.get("leistungsart") or "",
         daten.get("typ") if daten.get("typ") in ("leistung", "material") else typ_raten(daten.get("einheit"), ek),
         daten.get("einheit") or "Stk.", int(daten.get("preis") or 0), ek,
         aufschlag(int(daten.get("preis") or 0), ek) if ek_bekannt else None,
         float(daten.get("steuersatz") if daten.get("steuersatz") is not None else 19),
         0 if ek_bekannt else 1, dbm.jetzt(), dbm.jetzt()))
    dbm.protokollieren("artikel_aus_position", "artikel", cur.lastrowid, {"name": daten["bezeichnung"]}, con=con)
    neu = con.execute("SELECT * FROM artikel WHERE id=?", (cur.lastrowid,)).fetchone()
    dbm.aenderungen_erfassen(con, "artikel", cur.lastrowid, None, dict(neu), aktion="angelegt (aus Position)")
    return cur.lastrowid


def uebernehmen(con, daten):
    """Position in den Katalog übernehmen.

    Gibt (artikel_id, konflikt) zurück. konflikt ist ein dict, wenn es den Eintrag schon gibt und sich die
    Preise unterscheiden – der Katalog wird dann NICHT automatisch geändert (Rückfrage in der Oberfläche).
    """
    vorhanden = finden(con, daten["bezeichnung"])
    if not vorhanden:
        return anlegen(con, daten), None
    neu_ek = daten.get("teilekosten")
    preis_anders = int(daten.get("preis") or 0) != vorhanden["preis"]
    ek_anders = neu_ek is not None and (vorhanden["ek_unbekannt"] or int(neu_ek) != vorhanden["teilekosten"])
    if preis_anders or ek_anders:
        return vorhanden["id"], {
            "artikel_id": vorhanden["id"], "name": vorhanden["name"],
            "alt_preis": vorhanden["preis"], "neu_preis": int(daten.get("preis") or 0),
            "alt_ek": None if vorhanden["ek_unbekannt"] else vorhanden["teilekosten"],
            "neu_ek": None if neu_ek is None else int(neu_ek),
        }
    return vorhanden["id"], None


def preise_aktualisieren(con, artikel_id, preis, einkauf):
    """Katalogpreise nach Rückfrage übernehmen. einkauf=None lässt den Einkaufspreis unverändert."""
    a = con.execute("SELECT * FROM artikel WHERE id=?", (artikel_id,)).fetchone()
    if not a:
        return
    ek = a["teilekosten"] if einkauf is None else int(einkauf)
    ek_unbekannt = a["ek_unbekannt"] if einkauf is None else 0
    neu = {"preis": int(preis), "teilekosten": ek, "ek_unbekannt": ek_unbekannt,
           "aufschlag_prozent": None if ek_unbekannt else aufschlag(int(preis), ek)}
    con.execute("UPDATE artikel SET preis=?, teilekosten=?, ek_unbekannt=?, aufschlag_prozent=?, geaendert_am=? "
                "WHERE id=?", (*neu.values(), dbm.jetzt(), artikel_id))
    dbm.aenderungen_erfassen(con, "artikel", artikel_id, a, neu, aktion="Preise aktualisiert")
    dbm.protokollieren("artikel_preise_aktualisiert", "artikel", artikel_id,
                       {"preis": preis, "einkauf": einkauf}, con=con)


def aus_dokumenten_sammeln(con):
    """Alle manuellen Positionen (ohne Katalog-Verknüpfung) aus Rechnungen und KVA, Duplikate zusammengefasst.

    Gibt eine Liste von Vorschlägen zurück (neueste Angaben zuerst), bereits im Katalog vorhandene werden markiert.
    """
    zeilen = con.execute(
        "SELECT p.*, d.datum, d.nummer, d.typ AS dtyp FROM positionen p JOIN dokumente d ON d.id=p.dokument_id "
        "WHERE p.artikel_id IS NULL AND d.typ IN ('rechnung', 'kva') AND TRIM(p.bezeichnung)<>'' "
        "ORDER BY d.datum DESC, d.id DESC, p.pos").fetchall()
    katalog = {schluessel(a["name"]): a for a in con.execute("SELECT * FROM artikel")}
    gruppen = {}
    for p in zeilen:
        k = schluessel(p["bezeichnung"])
        g = gruppen.get(k)
        if g is None:
            g = gruppen[k] = {
                "schluessel": k, "bezeichnung": " ".join(p["bezeichnung"].split()),
                "beschreibung": p["beschreibung"] or "", "einheit": p["einheit"] or "Stk.",
                "preis": p["einzelpreis"], "teilekosten": None, "steuersatz": p["steuersatz"],
                "leistungsart": p["leistungsart"] or "", "anzahl": 0, "preise": set(),
                "zuletzt": p["datum"], "beleg": p["nummer"] or "Entwurf", "im_katalog": k in katalog,
            }
        g["anzahl"] += 1
        g["preise"].add(p["einzelpreis"])
        if g["teilekosten"] is None and p["teilekosten"]:
            g["teilekosten"] = p["teilekosten"]  # neuester bekannter Einkaufspreis
        if not g["beschreibung"] and p["beschreibung"]:
            g["beschreibung"] = p["beschreibung"]
    ergebnis = []
    for g in gruppen.values():
        g["typ"] = typ_raten(g["einheit"], g["teilekosten"])
        g["marge"], g["marge_prozent"] = marge(g["preis"], g["teilekosten"], g["teilekosten"] is None)
        g["preise"] = sorted(g["preise"])
        ergebnis.append(g)
    return sorted(ergebnis, key=lambda g: (g["im_katalog"], g["bezeichnung"].casefold()))


def aus_dokumenten_importieren(con, schluessel_liste):
    """Ausgewählte Vorschläge anlegen und offene Entwürfe mit den neuen Einträgen verknüpfen."""
    gewaehlt = set(schluessel_liste)
    angelegt = 0
    for g in aus_dokumenten_sammeln(con):
        if g["schluessel"] not in gewaehlt or g["im_katalog"]:
            continue
        aid = anlegen(con, g)
        angelegt += 1
        for p in con.execute("SELECT p.id, p.bezeichnung FROM positionen p JOIN dokumente d ON d.id=p.dokument_id "
                             "WHERE p.artikel_id IS NULL AND d.status='entwurf'").fetchall():
            if schluessel(p["bezeichnung"]) == g["schluessel"]:
                con.execute("UPDATE positionen SET artikel_id=? WHERE id=?", (aid, p["id"]))
    return angelegt
