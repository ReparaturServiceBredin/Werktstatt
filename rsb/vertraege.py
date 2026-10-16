"""Verträge, Lizenzen und Garantien beim Kunden – mit automatischer wiederkehrender Abrechnung.

Abrechnungsarten:
  keine            nur Dokumentation (z. B. Wertgarantie: Kunde zahlt direkt an den Versicherer)
  monatlich / vierteljaehrlich / halbjaehrlich / jaehrlich
                   wiederkehrend im Voraus, bis gekündigt (z. B. MSP-Paket)
  laufzeit         einmal für die ganze Laufzeit (z. B. ESET 1/2/3 Jahre); bei „automatisch verlängern“
                   wird nach Ablauf die nächste Laufzeit berechnet

Gekündigte Verträge werden bis zum Kündigungsdatum abgerechnet, danach nicht mehr.
Jeder abgerechnete Zeitraum wird gespeichert – so entsteht nie eine doppelte Rechnung.
Wird ein Rechnungsentwurf gelöscht, gilt der Zeitraum wieder als offen.
"""
import calendar
from datetime import date, timedelta

from . import db as dbm
from . import logik
from .hilfen import EingabeFehler, datum_de

ABRECHNUNG = {
    "keine": ("nur Dokumentation (keine Rechnung)", 0),
    "monatlich": ("monatlich", 1),
    "vierteljaehrlich": ("vierteljährlich", 3),
    "halbjaehrlich": ("halbjährlich", 6),
    "jaehrlich": ("jährlich", 12),
    "laufzeit": ("einmal je Laufzeit (z. B. 1/2/3 Jahre)", None),
}
KATEGORIEN = ["Garantie/Versicherung", "Lizenz", "MSP", "Wartung", "Sonstiges"]


def plus_monate(d: date, monate: int) -> date:
    m = d.month - 1 + monate
    jahr, monat = d.year + m // 12, m % 12 + 1
    return date(jahr, monat, min(d.day, calendar.monthrange(jahr, monat)[1]))


def _d(text):
    return date.fromisoformat(text) if text else None


def intervall_monate(v):
    if v["abrechnung"] == "laufzeit":
        return int(v["laufzeit_monate"] or 12)
    return ABRECHNUNG.get(v["abrechnung"], ("", 0))[1]


def laufzeit_ende(beginn: date, monate):
    return plus_monate(beginn, int(monate)) - timedelta(days=1) if monate else None


def fruehestes_kuendigungsdatum(v, heute=None):
    """Vorschlag: Ende der laufenden Abrechnungsperiode, frühestens Ende der Mindestlaufzeit."""
    heute = heute or date.today()
    beginn = _d(v["beginn"])
    kandidaten = [heute]
    if v["mindestlaufzeit_monate"]:
        kandidaten.append(laufzeit_ende(beginn, v["mindestlaufzeit_monate"]))
    n = intervall_monate(v)
    if v["abrechnung"] == "laufzeit" and v["ende"]:
        kandidaten.append(_d(v["ende"]))
    elif n:
        start = beginn
        while plus_monate(start, n) <= heute:
            start = plus_monate(start, n)
        kandidaten.append(plus_monate(start, n) - timedelta(days=1))
    return max(k for k in kandidaten if k)


def zustand(v, heute=None, erinnerung_tage=60):
    """Lesbarer Zustand: aktiv / gekündigt / beendet / läuft bald ab."""
    heute = heute or date.today()
    ende = _d(v["ende"])
    if v["status"] == "gekuendigt":
        zum = _d(v["kuendigung_zum"])
        if zum and zum < heute:
            return "beendet", f"beendet seit {datum_de(v['kuendigung_zum'])}"
        return "gekuendigt", f"gekündigt zum {datum_de(v['kuendigung_zum'])}"
    if ende and not v["auto_verlaengern"]:
        if ende < heute:
            return "abgelaufen", f"abgelaufen am {datum_de(v['ende'])}"
        if (ende - heute).days <= erinnerung_tage:
            return "laeuft_ab", f"läuft ab am {datum_de(v['ende'])}"
    return "aktiv", "aktiv"


def monatswert(v):
    """Umgerechneter Monatsbetrag (für die Übersicht „regelmäßige Einnahmen“)."""
    n = intervall_monate(v)
    if not n or v["abrechnung"] == "keine":
        return 0
    return int(round(v["preis"] * float(v["anzahl"] or 1) / n))


def faellige_zeitraeume(con, v, heute=None):
    """Alle bis heute fälligen, noch nicht abgerechneten Zeiträume eines Vertrags."""
    heute = heute or date.today()
    n = intervall_monate(v)
    if v["abrechnung"] == "keine" or not n:
        return []
    letzte = con.execute("SELECT MAX(bis) FROM vertrag_abrechnungen WHERE vertrag_id=?", (v["id"],)).fetchone()[0]
    start = _d(letzte) + timedelta(days=1) if letzte else _d(v["beginn"])
    if v["abgerechnet_bis"]:
        # bei Übernahme bestehender Verträge: bereits (z. B. in Lexware) berechnete Zeit überspringen
        frueher = _d(v["abgerechnet_bis"])
        while start <= frueher:
            start = plus_monate(start, n)
    zum = _d(v["kuendigung_zum"]) if v["status"] == "gekuendigt" else None
    bezahlt_bis = _d(v["ende"]) if v["abrechnung"] == "laufzeit" else None
    zeitraeume = []
    while start <= heute and len(zeitraeume) < 60:
        if zum and start > zum:
            break
        if v["abrechnung"] == "laufzeit" and bezahlt_bis and start > bezahlt_bis and not v["auto_verlaengern"]:
            break  # befristete Lizenz ohne automatische Verlängerung: nur die vereinbarte Laufzeit
        bis = plus_monate(start, n) - timedelta(days=1)
        if zum and bis > zum and v["abrechnung"] != "laufzeit":
            bis = zum
        zeitraeume.append((start, bis))
        start = bis + timedelta(days=1)
    return zeitraeume


def abrechnen(con, heute=None):
    """Erstellt für alle fälligen Verträge Rechnungsentwürfe (je Kunde eine Rechnung).

    Gibt eine Liste der erstellten Dokument-IDs zurück. Muss außerhalb einer Transaktion aufgerufen werden.
    """
    heute = heute or date.today()
    einst = dbm.einstellungen(con)
    vertraege = con.execute("SELECT v.* FROM vertraege v JOIN kunden k ON k.id=v.kunde_id "
                            "WHERE v.abrechnung<>'keine' ORDER BY v.kunde_id, v.id").fetchall()
    je_kunde = {}
    for v in vertraege:
        for von, bis in faellige_zeitraeume(con, v, heute):
            je_kunde.setdefault(v["kunde_id"], []).append((v, von, bis))
    neue = []
    for kunde_id, eintraege in je_kunde.items():
        with dbm.Transaktion(con):
            neue.append(_rechnung_erstellen(con, einst, kunde_id, eintraege))
    return neue


def _rechnung_erstellen(con, einst, kunde_id, eintraege):
    """Ein Rechnungsentwurf für einen Kunden mit allen übergebenen (vertrag, von, bis)-Zeiträumen."""
    von_min = min(e[1] for e in eintraege)
    bis_max = max(e[2] for e in eintraege)
    did = logik.neuer_entwurf(con, einst, "rechnung", kunde_id,
                              f"Wiederkehrende Leistungen {datum_de(von_min.isoformat())} – "
                              f"{datum_de(bis_max.isoformat())}",
                              leistungsdatum=von_min.isoformat())
    con.execute("UPDATE dokumente SET leistungsdatum_bis=? WHERE id=?", (bis_max.isoformat(), did))
    for pos, (v, von, bis) in enumerate(eintraege, 1):
        details = [f"Zeitraum {datum_de(von.isoformat())} – {datum_de(bis.isoformat())}"]
        if v["vertragsnummer"]:
            details.append(f"Vertrag/Lizenz: {v['vertragsnummer']}")
        if v["geraet"]:
            details.append(f"Gerät: {v['geraet']}")
        con.execute(
            "INSERT INTO positionen (dokument_id, pos, bezeichnung, beschreibung, menge, einheit, einzelpreis, "
            "teilekosten, steuersatz, leistungsart) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (did, pos, v["bezeichnung"], "\n".join(details), v["anzahl"] or 1,
             "Lizenz" if v["abrechnung"] == "laufzeit" else ABRECHNUNG[v["abrechnung"]][0].capitalize(),
             v["preis"], v["einkauf"], einst.get("regel_steuersatz", 19), v["kategorie"]))
        con.execute("INSERT INTO vertrag_abrechnungen (vertrag_id, dokument_id, von, bis, betrag) "
                    "VALUES (?,?,?,?,?)", (v["id"], did, von.isoformat(), bis.isoformat(),
                                           int(round(v["preis"] * float(v["anzahl"] or 1)))))
        if v["abrechnung"] == "laufzeit" and (not v["ende"] or bis.isoformat() > v["ende"]):
            con.execute("UPDATE vertraege SET ende=?, geaendert_am=? WHERE id=?",
                        (bis.isoformat(), dbm.jetzt(), v["id"]))
    logik.summen_speichern(con, did)
    dbm.protokollieren("vertraege_abgerechnet", "dokument", did, {"kunde": kunde_id, "positionen": len(eintraege)},
                       con=con)
    return did


def verlaengern(con, vertrag_id):
    """Befristete Lizenz um eine Laufzeit verlängern und die Verlängerung sofort berechnen (Entwurf)."""
    v = con.execute("SELECT * FROM vertraege WHERE id=?", (vertrag_id,)).fetchone()
    if not v or v["abrechnung"] != "laufzeit" or not v["laufzeit_monate"]:
        raise EingabeFehler("Nur befristete Lizenzen mit Laufzeit können verlängert werden.")
    if v["status"] == "gekuendigt":
        raise EingabeFehler("Der Vertrag ist gekündigt. Bitte zuerst die Kündigung zurücknehmen.")
    bisher = _d(v["ende"]) or laufzeit_ende(_d(v["beginn"]), v["laufzeit_monate"])
    von = bisher + timedelta(days=1)
    bis = laufzeit_ende(von, v["laufzeit_monate"])
    with dbm.Transaktion(con):
        did = _rechnung_erstellen(con, dbm.einstellungen(con), v["kunde_id"], [(v, von, bis)])
        dbm.protokollieren("vertrag_verlaengert", "vertrag", vertrag_id, {"bis": bis.isoformat()}, con=con)
    return did


def abrechnungslauf(con, daten_dir, heute=None):
    """Täglicher Lauf: Entwürfe anlegen und – im Modus „automatisch“ – festschreiben und per E-Mail senden."""
    from pathlib import Path

    from .hilfen import platzhalter_ersetzen
    from .mail import MailFehler, senden

    einst = dbm.einstellungen(con)
    neue = abrechnen(con, heute)
    ergebnis = {"rechnungen": len(neue), "festgeschrieben": 0, "versendet": 0, "fehler": []}
    if einst.get("abo_modus") == "automatisch":
        for did in neue:
            try:
                nummer = logik.festschreiben(con, did, daten_dir)
                ergebnis["festgeschrieben"] += 1
            except EingabeFehler as e:
                ergebnis["fehler"].append(f"Rechnungsentwurf {did}: {e}")
                continue
            d = con.execute("SELECT * FROM dokumente WHERE id=?", (did,)).fetchone()
            kunde = con.execute("SELECT * FROM kunden WHERE id=?", (d["kunde_id"],)).fetchone()
            if not (kunde["email"] and einst.get("smtp_host")):
                ergebnis["fehler"].append(f"{nummer}: nicht versendet (keine E-Mail-Adresse oder kein E-Mail-Zugang)")
                continue
            werte = logik.platzhalter_werte(d, kunde, einst)
            texte = logik.standard_texte(con, "rechnung")
            try:
                hinweis = senden(con, None, kunde["email"], platzhalter_ersetzen(texte.get("email_betreff", "{nummer}"), werte),
                       platzhalter_ersetzen(texte.get("email_text", ""), werte),
                       (Path(daten_dir) / d["pdf_pfad"]).read_bytes(), f"{nummer}.pdf", did)
                ergebnis["versendet"] += 1
                if hinweis:
                    ergebnis["fehler"].append(f"{nummer}: {hinweis}")
            except MailFehler as e:
                ergebnis["fehler"].append(f"{nummer}: {e}")
    with dbm.Transaktion(con):
        dbm.einstellungen_speichern({"abo_letzter_lauf": dbm.jetzt()}, con)
        if neue or ergebnis["fehler"]:
            dbm.protokollieren("abrechnungslauf", "vertrag", None, ergebnis, con=con)
    return ergebnis
