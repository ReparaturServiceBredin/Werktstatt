"""Werkstattkalender: Aufträge per Ziehen auf Tag und Uhrzeit einplanen.

Der Termin gehört zum Auftrag (termin_beginn „JJJJ-MM-TTTHH:MM“, termin_dauer in Minuten). Ohne angegebene Dauer
schlägt das Programm die Summe der Richtzeiten der gewählten Leistungen vor (Einstellungen → Annahme & Abholung).
"""
from datetime import date, datetime, timedelta

from .hilfen import EingabeFehler

RASTER = 15            # Minuten: Termine rasten auf Viertelstunden ein
STANDARD_DAUER = 60
WOCHENTAGE = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]


def richtzeiten(einst):
    """{Leistung: Minuten} aus „Leistung = Minuten“ je Zeile."""
    erg = {}
    for zeile in (einst.get("dauer_je_leistung") or "").splitlines():
        if "=" in zeile:
            name, wert = zeile.rsplit("=", 1)
            if name.strip() and wert.strip().isdigit():
                erg[name.strip()] = int(wert.strip())
    return erg


def dauer_vorschlag(einst, leistungsart):
    from .checkliste import leistungen
    zeiten = richtzeiten(einst)
    summe = sum(zeiten.get(l, 0) for l in leistungen(leistungsart))
    return max(RASTER, summe) if summe else STANDARD_DAUER


def beginn_pruefen(text):
    """„JJJJ-MM-TTTHH:MM“ (auch mit Leerzeichen statt T) → normierter Text, auf das Raster gerundet."""
    try:
        d = datetime.fromisoformat((text or "").strip().replace(" ", "T")[:16])
    except ValueError:
        raise EingabeFehler("Bitte Datum und Uhrzeit des Termins angeben.")
    minuten = round(d.minute / RASTER) * RASTER
    d = d.replace(minute=0, second=0) + timedelta(minutes=minuten)
    return d.strftime("%Y-%m-%dT%H:%M")


def dauer_pruefen(wert, vorschlag):
    if wert in (None, ""):
        return vorschlag
    try:
        m = int(str(wert).strip())
    except ValueError:
        raise EingabeFehler("Bitte die Dauer in Minuten angeben.")
    if not RASTER <= m <= 24 * 60:
        raise EingabeFehler("Die Dauer muss zwischen 15 Minuten und 24 Stunden liegen.")
    return m


def setzen(con, auftrag_id, beginn, dauer, einst):
    """Termin setzen oder verschieben (beginn=None entfernt ihn). Muss in einer Transaktion laufen."""
    from .auftraege import verlauf
    a = con.execute("SELECT termin_beginn, termin_dauer, leistungsart FROM auftraege WHERE id=?",
                    (auftrag_id,)).fetchone()
    if beginn is None:
        if a["termin_beginn"]:
            con.execute("UPDATE auftraege SET termin_beginn=NULL, termin_dauer=NULL WHERE id=?", (auftrag_id,))
            verlauf(con, auftrag_id, "Termin entfernt", text(a["termin_beginn"], a["termin_dauer"]))
        return
    beginn = beginn_pruefen(beginn)
    dauer = dauer_pruefen(dauer, a["termin_dauer"] or dauer_vorschlag(einst, a["leistungsart"]))
    if (beginn, dauer) == (a["termin_beginn"], a["termin_dauer"]):
        return
    con.execute("UPDATE auftraege SET termin_beginn=?, termin_dauer=? WHERE id=?", (beginn, dauer, auftrag_id))
    verlauf(con, auftrag_id, "Termin verschoben" if a["termin_beginn"] else "Termin geplant", text(beginn, dauer))


def text(beginn, dauer):
    """„Mo 20.10.2026, 08:00–08:45 Uhr“"""
    if not beginn:
        return ""
    b = datetime.fromisoformat(beginn)
    e = b + timedelta(minutes=dauer or STANDARD_DAUER)
    return f"{WOCHENTAGE[b.weekday()]} {b:%d.%m.%Y}, {b:%H:%M}–{e:%H:%M} Uhr"


def wochenanfang(tag):
    return tag - timedelta(days=tag.weekday())


def woche(con, montag, einst, auftrag_sql):
    """Tage der Woche mit Terminen und Bahnen für Überschneidungen, dazu Kopfdaten."""
    tage_anzahl = 6 if einst.get("kalender_samstag", True) else 5
    von_h, bis_h = int(einst.get("kalender_von") or 7), int(einst.get("kalender_bis") or 18)
    von_h, bis_h = max(0, min(von_h, 23)), max(1, min(bis_h, 24))
    if bis_h <= von_h:
        von_h, bis_h = 7, 18
    ende = montag + timedelta(days=7)
    zeilen = con.execute(auftrag_sql + "WHERE a.termin_beginn >= ? AND a.termin_beginn < ? ORDER BY a.termin_beginn",
                         (montag.isoformat(), ende.isoformat())).fetchall()
    tage = []
    for i in range(7):
        tag = montag + timedelta(days=i)
        termine = [_termin(a) for a in zeilen if a["termin_beginn"][:10] == tag.isoformat()]
        if i >= tage_anzahl and not termine:
            continue
        _bahnen(termine)
        tage.append({"datum": tag, "name": WOCHENTAGE[i], "termine": termine,
                     "minuten": sum(t["dauer"] for t in termine)})
    # Termine außerhalb des sichtbaren Zeitraums: Zeitraum erweitern statt sie zu verstecken
    for t in (x for tg in tage for x in tg["termine"]):
        von_h = min(von_h, t["start"] // 60)
        bis_h = max(bis_h, min(24, -(-t["ende"] // 60)))
    return {"tage": tage, "von": von_h, "bis": bis_h, "montag": montag, "sonntag": montag + timedelta(days=6)}


def _termin(a):
    b = datetime.fromisoformat(a["termin_beginn"])
    dauer = a["termin_dauer"] or STANDARD_DAUER
    start = b.hour * 60 + b.minute
    return {"a": a, "start": start, "ende": min(start + dauer, 24 * 60), "dauer": dauer,
            "von": f"{b:%H:%M}", "bis": (b + timedelta(minutes=dauer)).strftime("%H:%M"), "bahn": 0, "bahnen": 1}


def _bahnen(termine):
    """Überschneidende Termine nebeneinander: jede Gruppe überlappender Termine teilt sich die Breite."""
    gruppe, gruppen_ende = [], -1
    for t in sorted(termine, key=lambda x: (x["start"], -x["dauer"])):
        if gruppe and t["start"] >= gruppen_ende:
            _gruppe_abschliessen(gruppe)
            gruppe, gruppen_ende = [], -1
        belegt = {x["bahn"] for x in gruppe if x["ende"] > t["start"]}
        t["bahn"] = next(i for i in range(len(gruppe) + 1) if i not in belegt)
        gruppe.append(t)
        gruppen_ende = max(gruppen_ende, t["ende"])
    if gruppe:
        _gruppe_abschliessen(gruppe)


def _gruppe_abschliessen(gruppe):
    n = max(x["bahn"] for x in gruppe) + 1
    for x in gruppe:
        x["bahnen"] = n


def heute_offen(con, tag, auftrag_sql):
    return con.execute(auftrag_sql + "WHERE substr(a.termin_beginn, 1, 10)=? ORDER BY a.termin_beginn",
                       (tag.isoformat(),)).fetchall()


def ungeplant(con, auftrag_sql):
    """Offene Aufträge ohne Termin (älteste zuerst)."""
    return con.execute(auftrag_sql + "WHERE a.termin_beginn IS NULL AND a.status<>'erledigt' "
                       "ORDER BY a.fertig_bis IS NULL, a.fertig_bis, a.eingang_am").fetchall()


def montag_aus(text, heute):
    try:
        return wochenanfang(date.fromisoformat(text)) if text else wochenanfang(heute)
    except ValueError:
        return wochenanfang(heute)
