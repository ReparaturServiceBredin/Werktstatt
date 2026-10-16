"""Zahlungseingänge, Zahlungsstatus und offene Posten.

Zahlungen werden je Rechnung erfasst (auch Teilzahlungen), sind nicht löschbar und nur mit Begründung stornierbar.
Der offene Betrag einer Rechnung = Rechnungsbetrag + festgeschriebene Gutschriften (negativ) − Zahlungen.
"""
from datetime import date

from . import db as dbm
from .hilfen import EingabeFehler, euro

ZAHLARTEN = {"ueberweisung": "Überweisung", "bar": "Bar", "karte": "EC/Karte", "paypal": "PayPal",
             "verrechnung": "Verrechnung"}
STATUS = {"offen": "offen", "teilweise": "teilweise bezahlt", "bezahlt": "bezahlt", "ueberfaellig": "überfällig",
          "storniert": "storniert", "erstattung": "Guthaben/Erstattung offen"}


def stand(con, dok, heute=None):
    """Zahlungsstand einer (festgeschriebenen) Rechnung als dict."""
    heute = heute or date.today().isoformat()
    gutschriften = con.execute("SELECT COALESCE(SUM(summe_brutto), 0) FROM dokumente WHERE bezug_id=? "
                               "AND typ='gutschrift' AND status<>'entwurf'", (dok["id"],)).fetchone()[0]
    bezahlt = con.execute("SELECT COALESCE(SUM(betrag), 0) FROM zahlungen WHERE dokument_id=? AND storniert_am IS NULL",
                          (dok["id"],)).fetchone()[0]
    mahnungen = con.execute("SELECT * FROM mahnungen WHERE dokument_id=? ORDER BY stufe, id", (dok["id"],)).fetchall()
    forderung = dok["summe_brutto"] + gutschriften
    offen = forderung - bezahlt
    gebuehren = sum(m["gebuehr"] for m in mahnungen if not m["erledigt_am"])
    zinsen = mahnungen[-1]["zinsen"] if mahnungen and not mahnungen[-1]["erledigt_am"] else 0
    ueberzahlt = max(0, -offen)
    gebuehren_offen = max(0, gebuehren + zinsen - ueberzahlt)
    if dok["status"] == "storniert":
        status = "storniert"
    elif offen < 0 and gebuehren_offen == 0 and ueberzahlt > gebuehren + zinsen:
        status = "erstattung"
    elif offen <= 0:
        status = "bezahlt"
    elif dok["faellig_am"] and dok["faellig_am"] < heute:
        status = "ueberfaellig"
    elif bezahlt:
        status = "teilweise"
    else:
        status = "offen"
    return {"brutto": dok["summe_brutto"], "gutschriften": gutschriften, "forderung": forderung, "bezahlt": bezahlt,
            "offen": max(offen, 0), "ueberzahlt": ueberzahlt, "gebuehren_offen": gebuehren_offen, "status": status,
            "status_text": STATUS[status], "mahnstufe": mahnungen[-1]["stufe"] if mahnungen else None,
            "letzte_mahnung": mahnungen[-1] if mahnungen else None,
            "tage_ueberfaellig": (date.fromisoformat(heute) - date.fromisoformat(dok["faellig_am"])).days
            if status in ("ueberfaellig",) else 0}


def _cache_aktualisieren(con, dok_id):
    bezahlt = con.execute("SELECT COALESCE(SUM(betrag), 0) FROM zahlungen WHERE dokument_id=? AND storniert_am IS NULL",
                          (dok_id,)).fetchone()[0]
    con.execute("UPDATE dokumente SET bezahlt_betrag=? WHERE id=?", (bezahlt, dok_id))


def erfassen(con, dok_id, datum, betrag, zahlart, notiz="", bank_umsatz_id=None):
    """Zahlung zu einer festgeschriebenen Rechnung erfassen. Muss in einer Transaktion laufen. Gibt die ID zurück."""
    dok = con.execute("SELECT * FROM dokumente WHERE id=?", (dok_id,)).fetchone()
    if not dok or dok["typ"] != "rechnung" or dok["status"] == "entwurf":
        raise EingabeFehler("Zahlungen können nur zu festgeschriebenen Rechnungen erfasst werden.")
    if zahlart not in ZAHLARTEN:
        raise EingabeFehler("Bitte eine Zahlungsart wählen.")
    if not betrag:
        raise EingabeFehler("Bitte einen Betrag angeben.")
    try:
        if date.fromisoformat(datum) > date.today():
            raise EingabeFehler("Das Zahlungsdatum darf nicht in der Zukunft liegen.")
    except (TypeError, ValueError):
        raise EingabeFehler("Bitte ein gültiges Zahlungsdatum angeben.")
    cur = con.execute("INSERT INTO zahlungen (dokument_id, datum, betrag, zahlart, notiz, bank_umsatz_id, erfasst_am, "
                      "benutzer) VALUES (?,?,?,?,?,?,?,?)",
                      (dok_id, datum, betrag, zahlart, notiz or None, bank_umsatz_id, dbm.jetzt_berlin(),
                       dbm.aktueller_benutzer()))
    _cache_aktualisieren(con, dok_id)
    text = f"{euro(betrag)} am {datum} ({ZAHLARTEN[zahlart]})" + (f" – {notiz}" if notiz else "")
    dbm.ereignis_erfassen(con, "dokument", dok_id, "Zahlung erfasst", text)
    dbm.protokollieren("zahlung_erfasst", "dokument", dok_id, {"zahlung": cur.lastrowid, "betrag": betrag,
                                                               "datum": datum, "zahlart": zahlart}, con=con)
    _auftrag_verlauf(con, dok_id, "Zahlung erfasst", f"{dok['nummer']}: {text}")
    if zahlart == "bar":  # Barzahlung → Kassenbuch
        from .kasse import aus_zahlung
        aus_zahlung(con, cur.lastrowid)
    return cur.lastrowid


def stornieren(con, zahlung_id, grund):
    grund = (grund or "").strip()
    if len(grund) < 3:
        raise EingabeFehler("Bitte einen Grund für die Stornierung der Zahlung angeben.")
    z = con.execute("SELECT * FROM zahlungen WHERE id=?", (zahlung_id,)).fetchone()
    if not z or z["storniert_am"]:
        raise EingabeFehler("Zahlung nicht gefunden oder bereits storniert.")
    con.execute("UPDATE zahlungen SET storniert_am=?, storniert_von=?, storno_grund=? WHERE id=?",
                (dbm.jetzt_berlin(), dbm.aktueller_benutzer(), grund, zahlung_id))
    if z["bank_umsatz_id"]:  # Bankumsatz wieder zur Zuordnung freigeben
        con.execute("UPDATE bank_umsaetze SET status='offen', zahlung_id=NULL, bearbeitet_am=?, bearbeitet_von=? "
                    "WHERE id=?", (dbm.jetzt_berlin(), dbm.aktueller_benutzer(), z["bank_umsatz_id"]))
    _cache_aktualisieren(con, z["dokument_id"])
    if z["zahlart"] == "bar":
        from .kasse import zahlung_storniert
        zahlung_storniert(con, zahlung_id=zahlung_id, grund=f"Zahlung storniert: {grund}")
    dbm.ereignis_erfassen(con, "dokument", z["dokument_id"], "Zahlung storniert",
                          f"{euro(z['betrag'])} vom {z['datum']} – Grund: {grund}")
    dbm.protokollieren("zahlung_storniert", "dokument", z["dokument_id"], {"zahlung": zahlung_id, "grund": grund},
                       con=con)


def _auftrag_verlauf(con, dok_id, ereignis, details):
    from .auftraege import verlauf
    for a in con.execute("SELECT id FROM auftraege WHERE rechnung_id=?", (dok_id,)).fetchall():
        verlauf(con, a["id"], ereignis, details)


def liste(con, dok_id):
    return con.execute("SELECT * FROM zahlungen WHERE dokument_id=? ORDER BY datum, id", (dok_id,)).fetchall()


RECHNUNG_SQL = ("SELECT d.*, k.kundennr, k.firma, k.vorname, k.nachname, k.typ AS ktyp, k.email AS kemail "
                "FROM dokumente d LEFT JOIN kunden k ON k.id=d.kunde_id ")


def offene_posten(con, kunde_id=None, nur_ueberfaellig=False, heute=None):
    """Alle festgeschriebenen Rechnungen mit offenem Betrag oder offenen Mahngebühren (inkl. Guthaben)."""
    sql = RECHNUNG_SQL + "WHERE d.typ='rechnung' AND d.status='festgeschrieben' "
    args = []
    if kunde_id:
        sql += "AND d.kunde_id=? "
        args.append(kunde_id)
    ergebnis = []
    for d in con.execute(sql + "ORDER BY d.faellig_am, d.nummer", args).fetchall():
        s = stand(con, d, heute)
        if s["status"] == "bezahlt" and not s["gebuehren_offen"]:
            continue
        if nur_ueberfaellig and s["status"] != "ueberfaellig":
            continue
        ergebnis.append({"d": d, "s": s})
    return ergebnis


def summe_offen(con):
    return sum(p["s"]["offen"] for p in offene_posten(con))
