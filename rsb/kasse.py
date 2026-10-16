"""Kassenbuch: fortlaufend nummerierte Kassenbuchungen, Tagesabschluss mit Kassensturz, Korrektur nur per Gegenbuchung.

- Jede Buchung bekommt eine lückenlose laufende Nummer. Buchungen sind unveränderlich (Trigger); Fehler werden durch
  eine Gegenbuchung berichtigt.
- Barzahlungen auf Rechnungen (Zahlungen mit Zahlart „bar“) und bar bezahlte Eingangsrechnungen werden automatisch
  übernommen.
- Tagesabschluss: Soll-Bestand laut Kassenbuch gegen gezählten Ist-Bestand; eine Differenz wird mit Begründung als
  eigene Buchung erfasst. Abgeschlossene Tage können nicht mehr bebucht werden.
- Der Kassenbestand darf nie negativ werden – geprüft chronologisch nach Buchungsdatum über die ganze Historie, also
  auch bei rückdatierten Buchungen für jeden Tag ab dem Buchungsdatum.
- Privateinlage und Privatentnahme sind eigene Buchungsarten (Datum, Betrag, Begründung, fortlaufende Nummer, ohne USt).
"""
from datetime import date, timedelta

from . import db as dbm
from .hilfen import EingabeFehler, euro

ARTEN = {"einnahme": "Einnahme", "ausgabe": "Ausgabe", "einlage": "Privateinlage", "entnahme": "Privatentnahme",
         "bank_ein": "Geldtransit von der Bank", "bank_aus": "Einzahlung auf die Bank", "differenz": "Kassendifferenz",
         "gegenbuchung": "Gegenbuchung (Korrektur)", "anfangsbestand": "Anfangsbestand"}
EINGANG = {"einnahme", "einlage", "bank_ein", "anfangsbestand"}
PRIVAT = {"einlage", "entnahme"}  # ohne Umsatzsteuer
SCHEINE = [50000, 20000, 10000, 5000, 2000, 1000, 500, 200, 100, 50, 20, 10, 5, 2, 1]


def bestand(con, bis_datum=None):
    sql, args = "SELECT COALESCE(SUM(betrag), 0) FROM kassenbuch", []
    if bis_datum:
        sql += " WHERE datum <= ?"
        args.append(bis_datum)
    return con.execute(sql, args).fetchone()[0]


class KassenFehlbetrag(EingabeFehler):
    """Buchung würde den Kassenbestand an einem Tag negativ machen (tag: ISO-Datum, fehlbetrag: Cent > 0)."""

    def __init__(self, tag, fehlbetrag):
        self.tag, self.fehlbetrag = tag, fehlbetrag
        super().__init__(f"Kassenbestand wäre am {date.fromisoformat(tag).strftime('%d.%m.%Y')} um "
                         f"{euro(fehlbetrag)} negativ. Wahrscheinlich fehlt eine Einnahme oder eine Privateinlage.")


def erster_fehlbetrag(con, datum, wert):
    """Erster Tag ab datum (chronologisch), an dem der Bestand mit der zusätzlichen Buchung negativ wäre."""
    tage = [datum] + [r[0] for r in con.execute(
        "SELECT DISTINCT datum FROM kassenbuch WHERE datum > ? ORDER BY datum", (datum,))]
    for tag in tage:
        stand = bestand(con, tag) + wert
        if stand < 0:
            return tag, -stand
    return None


def letzter_abschluss(con):
    return con.execute("SELECT * FROM kassen_abschluesse ORDER BY datum DESC, id DESC LIMIT 1").fetchone()


def _naechste_nr(con):
    return (con.execute("SELECT MAX(lfd_nr) FROM kassenbuch").fetchone()[0] or 0) + 1


def buchen(con, datum, art, betrag, text, steuersatz=None, dokument_id=None, zahlung_id=None, er_zahlung_id=None,
           beleg=None, gegenbuchung_zu=None, negativ_erlaubt=False, kostenart=None):
    """Kassenbuchung erfassen (betrag positiv in Cent; Richtung ergibt sich aus der Art). Muss in einer Transaktion.

    beleg: (relativer Pfad, sha256, dateiname) oder None. Gibt die ID zurück.
    """
    if art not in ARTEN:
        raise EingabeFehler("Bitte eine Buchungsart wählen.")
    try:
        tag = date.fromisoformat(datum)
    except (TypeError, ValueError):
        raise EingabeFehler("Bitte ein gültiges Datum angeben.")
    if tag > date.today():
        raise EingabeFehler("Kassenbuchungen dürfen nicht in der Zukunft liegen.")
    text = (text or "").strip()
    if len(text) < 3:
        raise EingabeFehler("Bitte eine Begründung angeben (z. B. Wechselgeld aus Privatvermögen)." if art in PRIVAT
                            else "Bitte einen Buchungstext angeben.")
    if art in PRIVAT:
        steuersatz = None  # Privateinlagen/-entnahmen sind keine Umsätze
    if art in ("differenz", "gegenbuchung"):
        wert = int(betrag)  # mit Vorzeichen
        if not wert:
            raise EingabeFehler("Der Betrag darf nicht 0 sein.")
    else:
        if not betrag or int(betrag) <= 0:
            raise EingabeFehler("Bitte einen Betrag größer 0 angeben.")
        wert = int(betrag) if art in EINGANG else -int(betrag)
    abschluss = letzter_abschluss(con)
    if abschluss and datum <= abschluss["datum"]:
        raise EingabeFehler(f"Der {date.fromisoformat(abschluss['datum']).strftime('%d.%m.%Y')} ist bereits "
                            "abgeschlossen – bitte mit heutigem Datum buchen (ggf. als Gegenbuchung).")
    # Bestand darf an keinem Tag ab dem Buchungsdatum negativ werden
    if wert < 0 and not negativ_erlaubt:
        fehl = erster_fehlbetrag(con, datum, wert)
        if fehl:
            raise KassenFehlbetrag(*fehl)
    nr = _naechste_nr(con)
    cur = con.execute(
        "INSERT INTO kassenbuch (lfd_nr, datum, art, betrag, steuersatz, kostenart, text, dokument_id, zahlung_id, "
        "er_zahlung_id, beleg_datei, beleg_sha256, beleg_name, gegenbuchung_zu, erfasst_am, benutzer) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (nr, datum, art, wert, steuersatz, kostenart if art == "ausgabe" else None, text, dokument_id, zahlung_id,
         er_zahlung_id,
         beleg[0] if beleg else None, beleg[1] if beleg else None, beleg[2] if beleg else None, gegenbuchung_zu,
         dbm.jetzt_berlin(), dbm.aktueller_benutzer()))
    dbm.protokollieren("kassenbuchung", "kasse", cur.lastrowid, {"lfd_nr": nr, "betrag": wert, "art": art}, con=con)
    return cur.lastrowid


def gegenbuchen(con, buchung_id, grund, datum=None):
    """Korrektur: hebt eine Buchung durch eine Buchung mit umgekehrtem Vorzeichen auf."""
    b = con.execute("SELECT * FROM kassenbuch WHERE id=?", (buchung_id,)).fetchone()
    if not b:
        raise EingabeFehler("Buchung nicht gefunden.")
    if con.execute("SELECT 1 FROM kassenbuch WHERE gegenbuchung_zu=?", (buchung_id,)).fetchone():
        raise EingabeFehler("Zu dieser Buchung gibt es bereits eine Gegenbuchung.")
    if len((grund or "").strip()) < 3:
        raise EingabeFehler("Bitte einen Grund für die Korrektur angeben.")
    return buchen(con, datum or date.today().isoformat(), "gegenbuchung", -b["betrag"],
                  f"Gegenbuchung zu Nr. {b['lfd_nr']}: {grund.strip()}", steuersatz=b["steuersatz"],
                  dokument_id=b["dokument_id"], gegenbuchung_zu=buchung_id, negativ_erlaubt=b["betrag"] < 0,
                  kostenart=b["kostenart"])


def aus_zahlung(con, zahlung_id):
    """Barzahlung einer Rechnung ins Kassenbuch übernehmen (aufgerufen von zahlungen.erfassen)."""
    z = con.execute("SELECT z.*, d.nummer FROM zahlungen z JOIN dokumente d ON d.id=z.dokument_id WHERE z.id=?",
                    (zahlung_id,)).fetchone()
    return buchen(con, z["datum"], "einnahme", z["betrag"], f"Barzahlung Rechnung {z['nummer']}",
                  dokument_id=z["dokument_id"], zahlung_id=zahlung_id)


def aus_er_zahlung(con, er_zahlung_id):
    z = con.execute("SELECT z.*, e.lfd_nr, e.nummer FROM er_zahlungen z JOIN eingangsrechnungen e "
                    "ON e.id=z.eingangsrechnung_id WHERE z.id=?", (er_zahlung_id,)).fetchone()
    return buchen(con, z["datum"], "ausgabe", z["betrag"],
                  f"Bar bezahlt: Eingangsrechnung {z['lfd_nr']}" + (f" ({z['nummer']})" if z["nummer"] else ""),
                  er_zahlung_id=er_zahlung_id)


def zahlung_storniert(con, zahlung_id=None, er_zahlung_id=None, grund="Zahlung storniert"):
    spalte, wert = ("zahlung_id", zahlung_id) if zahlung_id else ("er_zahlung_id", er_zahlung_id)
    b = con.execute(f"SELECT id FROM kassenbuch WHERE {spalte}=? AND gegenbuchung_zu IS NULL", (wert,)).fetchone()
    if b and not con.execute("SELECT 1 FROM kassenbuch WHERE gegenbuchung_zu=?", (b["id"],)).fetchone():
        gegenbuchen(con, b["id"], grund)


def buchungen(con, von=None, bis=None):
    sql, args = ("SELECT k.*, d.nummer AS dok_nummer FROM kassenbuch k LEFT JOIN dokumente d ON d.id=k.dokument_id "
                 "WHERE 1=1 "), []
    if von:
        sql += "AND k.datum >= ? "
        args.append(von)
    if bis:
        sql += "AND k.datum <= ? "
        args.append(bis)
    zeilen = con.execute(sql + "ORDER BY k.datum, k.lfd_nr", args).fetchall()
    laufend = bestand(con, (date.fromisoformat(von) - timedelta(days=1)).isoformat()) if von else 0
    ergebnis = []
    for z in zeilen:
        laufend += z["betrag"]
        ergebnis.append({"b": z, "saldo": laufend})
    return ergebnis


def tagesabschluss(con, datum, ist, begruendung="", zaehlung=None):
    """Kassensturz: Soll (Kassenbuch) gegen Ist (gezählt). Differenz wird gebucht. Muss in einer Transaktion laufen."""
    try:
        tag = date.fromisoformat(datum)
    except (TypeError, ValueError):
        raise EingabeFehler("Bitte ein gültiges Datum angeben.")
    if tag > date.today():
        raise EingabeFehler("Ein Tag in der Zukunft kann nicht abgeschlossen werden.")
    letzter = letzter_abschluss(con)
    if letzter and datum <= letzter["datum"]:
        raise EingabeFehler("Dieser Tag ist bereits abgeschlossen.")
    if ist is None or ist < 0:
        raise EingabeFehler("Bitte den gezählten Kassenbestand angeben.")
    soll = bestand(con, datum)
    if con.execute("SELECT 1 FROM kassenbuch WHERE datum > ?", (datum,)).fetchone():
        raise EingabeFehler("Es gibt schon Buchungen nach diesem Tag – bitte die Tage der Reihe nach abschließen.")
    differenz = ist - soll
    begruendung = (begruendung or "").strip()
    if differenz and len(begruendung) < 3:
        raise EingabeFehler(f"Soll {euro(soll)}, gezählt {euro(ist)}: Differenz {euro(differenz)} – bitte begründen.")
    if differenz:
        buchen(con, datum, "differenz", differenz, f"Kassendifferenz Tagesabschluss: {begruendung}",
               negativ_erlaubt=True)
    import json
    cur = con.execute("INSERT INTO kassen_abschluesse (datum, soll, ist, differenz, begruendung, zaehlung, erstellt_am, "
                      "benutzer) VALUES (?,?,?,?,?,?,?,?)",
                      (datum, soll, ist, differenz, begruendung or None, json.dumps(zaehlung) if zaehlung else None,
                       dbm.jetzt_berlin(), dbm.aktueller_benutzer()))
    dbm.protokollieren("tagesabschluss", "kasse", cur.lastrowid, {"datum": datum, "soll": soll, "ist": ist}, con=con)
    return cur.lastrowid, differenz


def beleg_ablegen(daten_dir, daten, name):
    from .einkauf import datei_ablegen
    rel, sha = datei_ablegen(daten_dir, daten, name)
    return rel, sha, name


def integritaet(con):
    """Lückenlose Nummerierung und Abschlüsse = Kassenbuch (für die Datenprüfung)."""
    fehler = []
    nrn = [r[0] for r in con.execute("SELECT lfd_nr FROM kassenbuch ORDER BY lfd_nr")]
    if nrn and nrn != list(range(1, len(nrn) + 1)):
        fehler.append("Kassenbuch: Die laufenden Nummern sind nicht lückenlos.")
    for a in con.execute("SELECT * FROM kassen_abschluesse"):
        if bestand(con, a["datum"]) != a["ist"]:
            fehler.append(f"Kassenbuch: Bestand am {a['datum']} weicht vom Tagesabschluss ab.")
    if any(bestand(con, d[0]) < 0 for d in con.execute("SELECT DISTINCT datum FROM kassenbuch")):
        fehler.append("Kassenbuch: Der Bestand war an mindestens einem Tag negativ.")
    return fehler

