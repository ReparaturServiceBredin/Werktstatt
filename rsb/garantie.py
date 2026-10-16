"""Garantie auf Reparaturen, Wiedererkennung von Geräten (SN/IMEI) und Garantiefälle.

Die hier verwaltete Garantie ist eine freiwillige Zusage der Werkstatt. Sie beginnt mit der Abholung; das Ende wird im
Auftrag gespeichert. Die gesetzlichen Mängelrechte des Kunden (§§ 634 ff. BGB) bleiben davon unberührt – das steht
auch so auf Rechnung und Abholschein (Text in den Einstellungen).
"""
import calendar
import re
from datetime import date, datetime

from . import db as dbm
from .hilfen import datum_de

AUFTRAGSARTEN = {"reparatur": "Reparatur", "garantie": "Garantiefall"}


def standard_monate(einst):
    try:
        return max(0, int(einst.get("garantie_monate") or 0))
    except (TypeError, ValueError):
        return 12


def plus_monate(d, monate):
    m = d.month - 1 + monate
    jahr, monat = d.year + m // 12, m % 12 + 1
    return date(jahr, monat, min(d.day, calendar.monthrange(jahr, monat)[1]))


def _datum(iso):
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso).date()
    except ValueError:
        return None


def monate(a, einst):
    if a["garantie_monate"] is not None:
        return int(a["garantie_monate"])
    return standard_monate(einst)


def ende_berechnen(a, einst, beginn):
    """Garantieende = Abholdatum + Garantiedauer (None bei „keine Garantie“ oder Garantiefall)."""
    m = monate(a, einst)
    if not beginn or not m or a["auftragsart"] == "garantie":
        return None
    return plus_monate(beginn, m)


def ende_speichern(con, auftrag_id):
    """Garantieende im Auftrag speichern (bei Abholung und wenn sich die Garantiedauer danach ändert)."""
    a = con.execute("SELECT * FROM auftraege WHERE id=?", (auftrag_id,)).fetchone()
    ende = ende_berechnen(a, dbm.einstellungen(con), _datum(a["abgeholt_am"]))
    wert = ende.isoformat() if ende else None
    if wert != a["garantie_ende"]:
        con.execute("UPDATE auftraege SET garantie_ende=? WHERE id=?", (wert, auftrag_id))
    return wert


def status(a, einst, heute=None):
    """Freiwillige Garantie eines Auftrags: Beginn = Abholung, Ende wie im Auftrag gespeichert."""
    heute = heute or date.today()
    m = monate(a, einst)
    beginn = _datum(a["abgeholt_am"])
    if a["auftragsart"] == "garantie":
        return {"monate": m, "beginn": beginn, "ende": None, "laeuft": False, "text": "Garantiefall (kostenlos)"}
    if not m:
        return {"monate": 0, "beginn": beginn, "ende": None, "laeuft": False,
                "text": "keine freiwillige Garantie vereinbart"}
    if not beginn:
        return {"monate": m, "beginn": None, "ende": None, "laeuft": False,
                "text": f"{m} Monate ab Abholung (noch nicht abgeholt)"}
    ende = _datum(a["garantie_ende"]) or plus_monate(beginn, m)
    laeuft = ende >= heute
    return {"monate": m, "beginn": beginn, "ende": ende, "laeuft": laeuft,
            "text": f"{m} Monate bis {datum_de(ende.isoformat())}" + (" – läuft" if laeuft else " – abgelaufen")}


HINWEIS_GESETZ = "Ihre gesetzlichen Gewährleistungsrechte bleiben von dieser Garantie unberührt."


def _dauer(m):
    return "einem Monat" if m == 1 else f"{m} Monaten"


def garantietext(einst, m, ende=None):
    """Text der freiwilligen Garantie aus den Einstellungen mit Firmendaten (leer bei „keine Garantie“)."""
    if not m:
        return ""
    vorlage = einst.get("garantie_text") or ""
    anschrift = ", ".join(x for x in [einst.get("strasse"), " ".join(x for x in [einst.get("plz"), einst.get("ort")]
                                                                     if x)] if x)
    werte = {"{Garantiedauer}": _dauer(m),
             "{Garantieende}": datum_de(ende.isoformat()) if ende else f"Ablauf von {_dauer(m)} nach Abholung",
             "{Firmenname}": einst.get("firma_name") or einst.get("inhaber") or "",
             "{Firmenanschrift}": anschrift}
    for k, v in werte.items():
        vorlage = vorlage.replace(k, v)
    return vorlage


def text_fuer_auftrag(con, a, ab=None):
    """Garantietext für den Abholschein. ab: Beginn (Standard: Abholung bzw. heute = Tag der Unterschrift)."""
    einst = dbm.einstellungen(con)
    if a["auftragsart"] == "garantie":
        return "Garantiefall – kostenlose Nachbesserung." + (f" Bezug: Auftrag {bezug_nr(con, a)}."
                                                              if a["garantie_bezug_id"] else "")
    beginn = ab or _datum(a["abgeholt_am"]) or date.today()
    return garantietext(einst, monate(a, einst), ende_berechnen(a, einst, beginn))


def bezug_nr(con, a):
    r = con.execute("SELECT auftragsnr FROM auftraege WHERE id=?", (a["garantie_bezug_id"],)).fetchone()
    return r["auftragsnr"] if r else ""


def rechnungstext(con, dok):
    """Garantietext für eine Rechnung, die zu einem Auftrag gehört (sonst leer).

    Ist das Gerät noch nicht abgeholt, steht statt des Enddatums „Ablauf von … nach Abholung“ – die Garantie
    beginnt mit der Abholung, nicht mit dem Rechnungsdatum.
    """
    a = con.execute("SELECT * FROM auftraege WHERE rechnung_id=?", (dok["id"],)).fetchone()
    if not a or a["auftragsart"] == "garantie":
        return ""
    einst = dbm.einstellungen(con)
    return garantietext(einst, monate(a, einst), _datum(a["garantie_ende"]))


# ---------------------------------------------------------------------- Geräte wiedererkennen

def sn_normal(sn):
    return re.sub(r"[\s\-/.]", "", (sn or "")).upper()


SN_SQL = "upper(replace(replace(replace(replace(COALESCE(a.seriennummer,''),' ',''),'-',''),'/',''),'.',''))"


def vorbesuche(con, sn, ohne_id=None, heute=None):
    """Frühere Aufträge mit derselben Seriennummer/IMEI (neueste zuerst), mit Garantiestand."""
    n = sn_normal(sn)
    if len(n) < 4:
        return []
    einst = dbm.einstellungen(con)
    zeilen = con.execute(
        "SELECT a.*, k.kundennr, k.firma, k.vorname, k.nachname, k.typ AS ktyp, re.nummer AS re_nummer, "
        "re.status AS re_status, re.summe_brutto AS re_betrag, "
        "(SELECT COUNT(*) FROM auftrag_fotos f WHERE f.auftrag_id=a.id AND f.geloescht_am IS NULL) AS foto_anzahl "
        f"FROM auftraege a JOIN kunden k ON k.id=a.kunde_id LEFT JOIN dokumente re ON re.id=a.rechnung_id "
        f"WHERE {SN_SQL}=? AND a.id<>? ORDER BY a.eingang_am DESC", (n, ohne_id or 0)).fetchall()
    return [{"a": z, "garantie": status(z, einst, heute)} for z in zeilen]


def interne_kosten(con, a):
    """Interne Kosten eines Garantiefalls: manuell erfasste Kosten (+ später Lagerabgänge zum EK)."""
    summe = a["interne_kosten"] or 0
    try:
        from .lager import auftrag_materialkosten
        summe += auftrag_materialkosten(con, a["id"])
    except ImportError:
        pass
    return summe


def garantiefaelle_zu(con, auftrag_id):
    return con.execute("SELECT * FROM auftraege WHERE garantie_bezug_id=? ORDER BY eingang_am", (auftrag_id,)).fetchall()
