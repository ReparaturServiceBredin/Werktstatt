"""DATEV-Export: Buchungsstapel im DATEV-Format (EXTF, Version 700, Kategorie 21) plus Belege als ZIP.

Enthalten sind für den Zeitraum (Belegdatum bzw. Zahlungs-/Buchungsdatum):
- Ausgangsrechnungen, Gutschriften, Stornos (Debitor an Erlöse; bei Regelbesteuerung je Steuersatz)
- Zahlungseingänge (Bank/Kasse an Debitor) und deren Stornos
- Eingangsrechnungen (Aufwand je Kostenart an Kreditor, Vorsteuer per BU-Schlüssel) und deren Stornos
- Zahlungsausgänge (Kreditor an Bank/Kasse)
- Kassenbuchungen, die nicht schon als Zahlung enthalten sind (Einlagen, Entnahmen, Bareinnahmen, Ausgaben, Differenzen)

Exportierte Buchungen werden vermerkt (datev_posten) und beim nächsten Export nicht erneut ausgegeben.
Die Kontenvorschläge sind Standardkonten der Kontenrahmen SKR03/SKR04 – bitte mit dem Steuerberater abstimmen.
"""
import csv
import hashlib
import io
import json
import zipfile
from datetime import date, datetime
from pathlib import Path

from . import db as dbm
from .hilfen import EingabeFehler

KONTEN = {  # Name: (SKR03, SKR04, Bezeichnung)
    "kasse": ("1000", "1600", "Kasse"),
    "bank": ("1200", "1800", "Bank"),
    "geldtransit": ("1360", "1460", "Geldtransit"),
    "erloese_ku": ("8195", "4185", "Erlöse Kleinunternehmer § 19 UStG"),
    "erloese_19": ("8400", "4400", "Erlöse 19 % USt"),
    "erloese_7": ("8300", "4300", "Erlöse 7 % USt"),
    "erloese_0": ("8200", "4200", "Erlöse (ohne USt)"),
    "privateinlage": ("1890", "2180", "Privateinlagen"),
    "privatentnahme": ("1800", "2100", "Privatentnahmen"),
    "sonstige_ertraege": ("2700", "4830", "Sonstige Erträge (Kassenüberschuss)"),
    "sonstige_aufwendungen": ("4900", "6300", "Sonstige Aufwendungen (Kassenfehlbetrag)"),
}
KOSTENARTEN = {  # Kostenart: (SKR03, SKR04) – Konten ohne automatische Vorsteuer
    "Wareneinkauf / Ersatzteile": ("3200", "5200"), "Werkzeug & Geräte": ("4985", "6845"),
    "Miete & Nebenkosten": ("4210", "6310"), "Telefon & Internet": ("4920", "6805"),
    "Software & Lizenzen": ("4964", "6837"), "Porto & Versand": ("4910", "6800"), "Werbung": ("4600", "6600"),
    "Fahrzeugkosten": ("4500", "6500"), "Bürobedarf": ("4930", "6815"), "Fortbildung": ("4945", "6821"),
    "Versicherungen & Beiträge": ("4360", "6400"), "Bankgebühren": ("4970", "6855"), "Sonstiges": ("4900", "6300"),
}
BU_VORSTEUER = {19.0: "9", 7.0: "8"}
SPALTEN = ["Umsatz (ohne Soll/Haben-Kz)", "Soll/Haben-Kennzeichen", "WKZ Umsatz", "Kurs", "Basis-Umsatz",
           "WKZ Basis-Umsatz", "Konto", "Gegenkonto (ohne BU-Schlüssel)", "BU-Schlüssel", "Belegdatum", "Belegfeld 1",
           "Belegfeld 2", "Skonto", "Buchungstext", "Postensperre", "Diverse Adressnummer", "Geschäftspartnerbank",
           "Sachverhalt", "Zinssperre", "Beleglink"]


def _zuordnung(text):
    werte = {}
    for zeile in (text or "").splitlines():
        if "=" in zeile:
            k, v = zeile.split("=", 1)
            if k.strip() and v.strip():
                werte[k.strip()] = v.strip()
    return werte


def konten(einst):
    """Kontenplan: Standard des gewählten SKR, überschrieben durch die Einstellungen."""
    i = 1 if str(einst.get("datev_skr") or "03") == "04" else 0
    k = {name: werte[i] for name, werte in KONTEN.items()}
    k.update({n: v for n, v in _zuordnung(einst.get("datev_konten")).items() if n in KONTEN})
    kosten = {name: werte[i] for name, werte in KOSTENARTEN.items()}
    kosten.update(_zuordnung(einst.get("datev_kostenarten")))
    return k, kosten


def debitor(einst, kunde_id):
    return str(int(einst.get("datev_debitor_start") or 10000) + int(kunde_id or 0))


def kreditor(einst, lieferant):
    if lieferant and lieferant["kreditornr"]:
        return str(lieferant["kreditornr"]).strip()
    return str(int(einst.get("datev_kreditor_start") or 70000) + int(lieferant["id"] if lieferant else 0))


def _zeile(betrag, konto, gegenkonto, belegdatum, beleg, text, bu="", beleg2="", quelle=None):
    return {"betrag": betrag, "konto": konto, "gegenkonto": gegenkonto, "bu": bu, "datum": belegdatum,
            "beleg": (beleg or "")[:36], "beleg2": (beleg2 or "")[:12], "text": (text or "")[:60], "quelle": quelle}


def buchungen(con, von, bis, auch_exportierte=False):
    """Alle Buchungszeilen des Zeitraums. Jede Zeile trägt ihre Quelle (für das Vermerken als exportiert)."""
    einst = dbm.einstellungen(con)
    k, kosten = konten(einst)
    regel = einst["steuer_modus"] == "regel"
    erledigt = set() if auch_exportierte else {(r["quelle"], r["quelle_id"]) for r in
                                               con.execute("SELECT quelle, quelle_id FROM datev_posten")}
    zeilen = []

    def neu(quelle, qid):
        return (quelle, qid) not in erledigt

    # 1. Ausgangsrechnungen, Gutschriften, Stornos
    for d in con.execute("SELECT d.*, k.firma, k.vorname, k.nachname, k.typ AS ktyp FROM dokumente d "
                         "JOIN kunden k ON k.id=d.kunde_id WHERE d.typ IN ('rechnung', 'gutschrift', 'storno') "
                         "AND d.status<>'entwurf' AND d.datum BETWEEN ? AND ? ORDER BY d.datum, d.nummer", (von, bis)):
        if not neu("dokument", d["id"]):
            continue
        snap = json.loads(d["snapshot_json"])
        name = snap["kunde"]["name"]
        deb = debitor(einst, d["kunde_id"])
        gruppen = snap["summen"]["gruppen"] if d["steuer_modus"] == "regel" else []
        if gruppen:
            for g in gruppen:
                konto = k["erloese_19"] if g["satz"] == 19 else (k["erloese_7"] if g["satz"] == 7 else k["erloese_0"])
                zeilen.append(_zeile(g["netto"] + g["steuer"], deb, konto, d["datum"], d["nummer"],
                                     f"{name} {snap['titel']}", quelle=("dokument", d["id"])))
        else:
            zeilen.append(_zeile(d["summe_brutto"], deb, k["erloese_ku"] if d["steuer_modus"] != "regel"
                                 else k["erloese_0"], d["datum"], d["nummer"], f"{name} {snap['titel']}",
                                 quelle=("dokument", d["id"])))
    # 2. Zahlungseingänge (und Stornos bereits exportierter Zahlungen)
    for z in con.execute("SELECT z.*, d.nummer, d.kunde_id FROM zahlungen z JOIN dokumente d ON d.id=z.dokument_id "
                         "ORDER BY z.datum, z.id"):
        gegen = k["kasse"] if z["zahlart"] == "bar" else k["bank"]
        if von <= z["datum"] <= bis and neu("zahlung", z["id"]) and not (
                z["storniert_am"] and ("zahlung", z["id"]) not in erledigt and not auch_exportierte
                and z["storniert_am"][:10] <= bis):
            zeilen.append(_zeile(z["betrag"], gegen, debitor(einst, z["kunde_id"]), z["datum"], z["nummer"],
                                 f"Zahlung {z['nummer']}", quelle=("zahlung", z["id"])))
        if z["storniert_am"] and von <= z["storniert_am"][:10] <= bis and neu("zahlung_storno", z["id"]) and (
                ("zahlung", z["id"]) in erledigt or auch_exportierte):
            zeilen.append(_zeile(-z["betrag"], gegen, debitor(einst, z["kunde_id"]), z["storniert_am"][:10],
                                 z["nummer"], f"Storno Zahlung {z['nummer']}", quelle=("zahlung_storno", z["id"])))
    # 3. Eingangsrechnungen
    for e in con.execute("SELECT e.*, l.kreditornr, l.name AS lname FROM eingangsrechnungen e LEFT JOIN lieferanten l "
                         "ON l.id=e.lieferant_id ORDER BY e.datum, e.id"):
        lief = {"id": e["lieferant_id"] or 0, "kreditornr": e["kreditornr"]}
        kred = kreditor(einst, lief)
        konto = kosten.get(e["kostenart"] or "", kosten.get("Sonstiges", k["sonstige_aufwendungen"]))
        bu = BU_VORSTEUER.get(float(e["steuersatz"] or 0), "") if regel and e["steuer"] else ""
        text = f"{e['lname'] or e['lieferant_name'] or ''} {e['nummer'] or ''}".strip()
        storniert_vor_export = e["status"] == "storniert" and ("eingangsrechnung", e["id"]) not in erledigt
        if von <= e["datum"] <= bis and neu("eingangsrechnung", e["id"]) and not (storniert_vor_export and
                                                                                  not auch_exportierte):
            zeilen.append(_zeile(e["brutto"], konto, kred, e["datum"], e["nummer"] or e["lfd_nr"], text, bu,
                                 e["lfd_nr"], quelle=("eingangsrechnung", e["id"])))
        if e["status"] == "storniert" and e["storniert_am"] and von <= e["storniert_am"][:10] <= bis and \
                neu("eingangsrechnung_storno", e["id"]) and (("eingangsrechnung", e["id"]) in erledigt or auch_exportierte):
            zeilen.append(_zeile(-e["brutto"], konto, kred, e["storniert_am"][:10], e["nummer"] or e["lfd_nr"],
                                 f"Storno {text}", bu, e["lfd_nr"], quelle=("eingangsrechnung_storno", e["id"])))
    # 4. Zahlungsausgänge
    for z in con.execute("SELECT z.*, e.nummer, e.lfd_nr, e.lieferant_id, l.kreditornr FROM er_zahlungen z "
                         "JOIN eingangsrechnungen e ON e.id=z.eingangsrechnung_id LEFT JOIN lieferanten l "
                         "ON l.id=e.lieferant_id ORDER BY z.datum, z.id"):
        kred = kreditor(einst, {"id": z["lieferant_id"] or 0, "kreditornr": z["kreditornr"]})
        gegen = k["kasse"] if z["zahlart"] == "bar" else k["bank"]
        if von <= z["datum"] <= bis and neu("er_zahlung", z["id"]) and not (
                z["storniert_am"] and ("er_zahlung", z["id"]) not in erledigt and not auch_exportierte):
            zeilen.append(_zeile(z["betrag"], kred, gegen, z["datum"], z["nummer"] or z["lfd_nr"],
                                 f"Zahlung {z['nummer'] or z['lfd_nr']}", beleg2=z["lfd_nr"], quelle=("er_zahlung", z["id"])))
        if z["storniert_am"] and von <= z["storniert_am"][:10] <= bis and neu("er_zahlung_storno", z["id"]) and (
                ("er_zahlung", z["id"]) in erledigt or auch_exportierte):
            zeilen.append(_zeile(-z["betrag"], kred, gegen, z["storniert_am"][:10], z["nummer"] or z["lfd_nr"],
                                 "Storno Zahlung", beleg2=z["lfd_nr"], quelle=("er_zahlung_storno", z["id"])))
    # 5. Kassenbuch (ohne Barzahlungen, die schon als Zahlung enthalten sind)
    for b in con.execute("SELECT * FROM kassenbuch WHERE datum BETWEEN ? AND ? ORDER BY lfd_nr", (von, bis)):
        if not neu("kasse", b["id"]) or b["art"] == "anfangsbestand":
            continue
        art, betrag, basis = b["art"], b["betrag"], b
        if art == "gegenbuchung":
            orig = con.execute("SELECT * FROM kassenbuch WHERE id=?", (b["gegenbuchung_zu"],)).fetchone()
            if not orig or orig["zahlung_id"] or orig["er_zahlung_id"] or orig["art"] == "anfangsbestand":
                continue  # Storno einer Zahlung steht schon bei den Zahlungen
            art, basis = orig["art"], orig
        elif b["zahlung_id"] or b["er_zahlung_id"]:
            continue
        satz = float(basis["steuersatz"] or 0)
        gegen = {"einnahme": (k["erloese_19"] if satz == 19 else k["erloese_7"] if satz == 7 else k["erloese_0"])
                 if regel else k["erloese_ku"],
                 "ausgabe": kosten.get(basis["kostenart"] or "Sonstiges", k["sonstige_aufwendungen"]),
                 "einlage": k["privateinlage"], "entnahme": k["privatentnahme"], "bank_ein": k["geldtransit"],
                 "bank_aus": k["geldtransit"],
                 "differenz": k["sonstige_ertraege"] if basis["betrag"] > 0 else k["sonstige_aufwendungen"]}.get(art)
        if not gegen:
            continue
        bu = BU_VORSTEUER.get(satz, "") if regel and art == "ausgabe" else ""
        zeilen.append(_zeile(betrag, k["kasse"], gegen, b["datum"], f"KB{b['lfd_nr']}", b["text"], bu,
                             quelle=("kasse", b["id"])))
    return zeilen


def _betrag(cent):
    return f"{abs(cent) // 100},{abs(cent) % 100:02d}"


def csv_erzeugen(einst, zeilen, von, bis, jetzt=None):
    """EXTF-Buchungsstapel als Bytes (Windows-1252, Semikolon, wie von DATEV erwartet)."""
    jetzt = jetzt or datetime.now()
    wj = (einst.get("datev_wj_beginn") or "01-01").split("-")
    wj_beginn = f"{von[:4]}{wj[0].zfill(2)}{wj[1].zfill(2)}" if len(wj) == 2 else f"{von[:4]}0101"
    kopf = ["EXTF", 700, 21, "Buchungsstapel", 13, jetzt.strftime("%Y%m%d%H%M%S") + f"{jetzt.microsecond // 1000:03d}",
            "", "RE", "", "", einst.get("datev_beraternr") or "", einst.get("datev_mandantennr") or "", wj_beginn,
            int(einst.get("datev_kontenlaenge") or 4), von.replace("-", ""), bis.replace("-", ""),
            f"Buchhaltung {von[:7]}", "", 1, 0, 0, "EUR", "", "", "", "", str(einst.get("datev_skr") or "03"), "", "", "",
            "Werkstatt-Sauter"]
    puffer = io.StringIO()
    w = csv.writer(puffer, delimiter=";", quotechar='"', quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")
    w.writerow(kopf)
    w.writerow(SPALTEN)
    for z in zeilen:
        w.writerow([_betrag(z["betrag"]), "S" if z["betrag"] >= 0 else "H", "EUR", "", "", "", z["konto"],
                    z["gegenkonto"], z["bu"], date.fromisoformat(z["datum"]).strftime("%d%m"), z["beleg"], z["beleg2"],
                    "", z["text"], "", "", "", "", "", ""])
    return puffer.getvalue().encode("cp1252", errors="replace")


def exportieren(con, von, bis, daten_dir, auch_exportierte=False):
    """ZIP mit Buchungsstapel und Belegen erzeugen, protokollieren, Buchungen als exportiert vermerken.

    Muss in einer Transaktion laufen. Gibt die Export-ID zurück.
    """
    try:
        if date.fromisoformat(von) > date.fromisoformat(bis):
            raise EingabeFehler("Das Startdatum liegt nach dem Enddatum.")
    except (TypeError, ValueError):
        raise EingabeFehler("Bitte einen gültigen Zeitraum angeben.")
    if von[:4] != bis[:4]:
        raise EingabeFehler("Ein Buchungsstapel darf nur ein Wirtschaftsjahr umfassen – bitte je Jahr exportieren.")
    einst = dbm.einstellungen(con)
    zeilen = buchungen(con, von, bis, auch_exportierte)
    if not zeilen:
        raise EingabeFehler("Im Zeitraum gibt es keine (noch nicht exportierten) Buchungen.")
    csv_daten = csv_erzeugen(einst, zeilen, von, bis)
    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(f"EXTF_Buchungsstapel_{von}_{bis}.csv", csv_daten)
        for pfad, name in _belege(con, zeilen, daten_dir):
            z.write(pfad, f"Belege/{name}")
        z.writestr("LIESMICH.txt", (f"DATEV-Export {von} bis {bis}, erstellt {dbm.jetzt_berlin()}\r\n"
                                    f"{len(zeilen)} Buchungen. Kontenrahmen SKR{einst.get('datev_skr') or '03'}.\r\n"
                                    "Die Belege liegen im Ordner Belege (Dateiname = Belegnummer).\r\n").encode("utf-8"))
    daten = puffer.getvalue()
    ordner = Path(daten_dir) / "exporte" / "datev"
    ordner.mkdir(parents=True, exist_ok=True)
    datei = ordner / f"DATEV_{von}_{bis}_{datetime.now().strftime('%Y%m%d%H%M%S')}.zip"
    datei.write_bytes(daten)
    sha = hashlib.sha256(daten).hexdigest()
    cur = con.execute("INSERT INTO datev_exporte (von, bis, anzahl, summe, datei, sha256, erneut, erstellt_am, benutzer) "
                      "VALUES (?,?,?,?,?,?,?,?,?)", (von, bis, len(zeilen), sum(abs(z["betrag"]) for z in zeilen),
                                                     datei.relative_to(Path(daten_dir)).as_posix(), sha,
                                                     1 if auch_exportierte else 0, dbm.jetzt_berlin(),
                                                     dbm.aktueller_benutzer()))
    eid = cur.lastrowid
    if not auch_exportierte:
        for quelle in {z["quelle"] for z in zeilen}:
            con.execute("INSERT OR IGNORE INTO datev_posten (quelle, quelle_id, export_id) VALUES (?,?,?)",
                        (*quelle, eid))
        for q, qid in {z["quelle"] for z in zeilen}:
            if q == "eingangsrechnung":
                con.execute("UPDATE eingangsrechnungen SET exportiert_am=? WHERE id=? AND exportiert_am IS NULL",
                            (dbm.jetzt_berlin(), qid))
    dbm.protokollieren("datev_export", "datev", eid, {"von": von, "bis": bis, "anzahl": len(zeilen), "sha256": sha},
                       con=con)
    return eid


def _belege(con, zeilen, daten_dir):
    gesehen = set()
    for z in zeilen:
        q, qid = z["quelle"]
        if (q, qid) in gesehen:
            continue
        gesehen.add((q, qid))
        if q == "dokument":
            d = con.execute("SELECT nummer, pdf_pfad, xml_pfad FROM dokumente WHERE id=?", (qid,)).fetchone()
            for rel in (d["pdf_pfad"], d["xml_pfad"]):
                if rel and (Path(daten_dir) / rel).is_file():
                    yield Path(daten_dir) / rel, Path(rel).name
        elif q == "eingangsrechnung":
            e = con.execute("SELECT lfd_nr, datei FROM eingangsrechnungen WHERE id=?", (qid,)).fetchone()
            if e["datei"] and (Path(daten_dir) / e["datei"]).is_file():
                yield Path(daten_dir) / e["datei"], f"{e['lfd_nr']}.{e['datei'].rsplit('.', 1)[-1]}"
        elif q == "kasse":
            b = con.execute("SELECT lfd_nr, beleg_datei FROM kassenbuch WHERE id=?", (qid,)).fetchone()
            if b["beleg_datei"] and (Path(daten_dir) / b["beleg_datei"]).is_file():
                yield Path(daten_dir) / b["beleg_datei"], f"KB{b['lfd_nr']}.{b['beleg_datei'].rsplit('.', 1)[-1]}"

