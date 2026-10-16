"""Bankabgleich: Kontoauszüge (CSV der gängigen Banken oder CAMT.053) einlesen und Zahlungen zuordnen.

- Die Spalten einer CSV-Datei werden anhand der Überschriften erkannt (Sparkasse, Volksbank/Raiffeisen, N26,
  DKB, ING, Postbank, Commerzbank u. a.), Zeichensatz und Trennzeichen automatisch.
- Jeder Umsatz bekommt eine Kennung; überlappende Auszüge erzeugen keine Doppelten.
- Vorschläge: Rechnungs- oder Mahnnummer im Verwendungszweck (sicher), sonst passender Betrag + Name.
  Jede Zuordnung wird vom Inhaber bestätigt.
"""
import csv
import hashlib
import io
import re
import unicodedata
import zipfile
from datetime import date, datetime
from xml.etree import ElementTree

from . import db as dbm
from . import zahlungen as zlg
from .hilfen import EingabeFehler, euro


class ImportFehler(EingabeFehler):
    pass


# ---------------------------------------------------------------- Hilfen

def _normal(text):
    t = unicodedata.normalize("NFC", (text or "").lower())
    t = t.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    t = unicodedata.normalize("NFKD", t)
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", t)


def betrag_cent(text):
    t = (text or "").strip().replace("€", "").replace("EUR", "").replace(" ", "").replace(" ", "")
    if not t:
        return None
    negativ = t.startswith("-") or t.endswith("-")
    t = t.strip("+-")
    if "," in t and "." in t:
        t = t.replace(".", "").replace(",", ".") if t.rfind(",") > t.rfind(".") else t.replace(",", "")
    elif "," in t:
        t = t.replace(",", ".")
    try:
        wert = int(round(float(t) * 100))
    except ValueError:
        return None
    return -wert if negativ else wert


def datum_iso(text):
    t = (text or "").strip()
    for fmt in ("%d.%m.%Y", "%d.%m.%y", "%Y-%m-%d", "%d/%m/%Y", "%Y%m%d"):
        try:
            return datetime.strptime(t[:10] if fmt == "%Y-%m-%d" else t, fmt).date().isoformat()
        except ValueError:
            continue
    return None


# ---------------------------------------------------------------- CSV

SPALTEN = {
    "datum": ["buchungstag", "buchungsdatum", "bookingdate", "buchung", "datum", "date"],
    "valuta": ["valutadatum", "valuta", "wertstellung", "valuedate", "wert"],
    "betrag": ["betrag", "betrageur", "amounteur", "betrag€", "umsatz", "amount", "umsatzineur"],
    "zweck": ["verwendungszweck", "paymentreference", "vorgangverwendungszweck", "beschreibung", "buchungstext"],
    "name": ["beguenstigterzahlungspflichtiger", "namezahlungsbeteiligter", "partnername", "empfaenger",
             "auftraggeberempfaenger", "beguenstigterauftraggeber", "zahlungspflichtiger", "zahlungspflichtiger",
             "zahlungspflichtiger*r", "zahlungspflichtiger", "auftraggeber", "name"],
    "iban": ["kontonummeriban", "ibanzahlungsbeteiligter", "partneriban", "ibankontonummer", "iban", "kontonummer"],
}
IGNORIEREN = ("auftragskonto", "saldo", "ursprungsbetrag", "fremdwaehrung", "originalamount", "auslagenersatz",
              "kontoinhaber", "abweichender")


def _spalten_finden(kopf):
    norm = [_normal(k) for k in kopf]
    ergebnis = {}
    for feld, namen in SPALTEN.items():
        for name in namen:
            for i, n in enumerate(norm):
                if i in ergebnis.values() or any(x in n for x in IGNORIEREN):
                    continue
                if n == _normal(name):
                    ergebnis[feld] = i
                    break
            if feld in ergebnis:
                break
    # DKB: getrennte Spalten für Zahlungspflichtige*r und Zahlungsempfänger*in
    pflichtig = next((i for i, n in enumerate(norm) if n.startswith("zahlungspflichtige")), None)
    empfaenger = next((i for i, n in enumerate(norm) if n.startswith("zahlungsempfaenger")), None)
    if pflichtig is not None and empfaenger is not None:
        ergebnis["name_ein"], ergebnis["name_aus"] = pflichtig, empfaenger
    soll_haben = next((i for i, n in enumerate(norm) if n in ("sollhaben", "sh", "habensoll")), None)
    if soll_haben is not None:
        ergebnis["soll_haben"] = soll_haben
    return ergebnis


def _csv_lesen(roh):
    for kodierung in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            text = roh.decode(kodierung)
            break
        except UnicodeDecodeError:
            continue
    zeilen = text.splitlines()
    # Kopfzeile suchen (manche Banken schreiben vorher Kontoinformationen)
    for start, zeile in enumerate(zeilen[:30]):
        trenner = ";" if zeile.count(";") >= zeile.count(",") else ","
        kopf = next(csv.reader([zeile], delimiter=trenner))
        spalten = _spalten_finden(kopf)
        if "datum" in spalten and "betrag" in spalten:
            break
    else:
        raise ImportFehler("Die CSV-Datei wurde nicht erkannt: Es fehlen Spalten für Buchungstag und Betrag. "
                           "Bitte den Kontoauszug als CSV (bzw. „CSV-CAMT“) oder CAMT.053 exportieren.")
    leser = csv.reader(io.StringIO("\n".join(zeilen[start + 1:])), delimiter=trenner)
    umsaetze = []
    for teile in leser:
        if len(teile) <= max(spalten["datum"], spalten["betrag"]):
            continue
        tag = datum_iso(teile[spalten["datum"]])
        betrag = betrag_cent(teile[spalten["betrag"]])
        if not tag or betrag is None:
            continue
        if "soll_haben" in spalten and teile[spalten["soll_haben"]].strip().upper().startswith("S"):
            betrag = -abs(betrag)

        def wert(feld):
            i = spalten.get(feld)
            return teile[i].strip() if i is not None and i < len(teile) else ""
        name = wert("name")
        if "name_ein" in spalten:
            name = (teile[spalten["name_ein"]] if betrag > 0 else teile[spalten["name_aus"]]).strip()
        umsaetze.append({"buchungstag": tag, "valuta": datum_iso(wert("valuta")), "betrag": betrag, "name": name,
                         "iban": wert("iban").replace(" ", ""), "zweck": wert("zweck")})
    return umsaetze


# ---------------------------------------------------------------- CAMT.053

def _ohne_ns(element):
    for e in element.iter():
        if isinstance(e.tag, str) and "}" in e.tag:
            e.tag = e.tag.split("}", 1)[1]
    return element


def _text(e, pfad):
    x = e.find(pfad)
    return (x.text or "").strip() if x is not None and x.text else ""


def _camt_lesen(roh):
    try:
        wurzel = _ohne_ns(ElementTree.fromstring(roh))
    except ElementTree.ParseError as e:
        raise ImportFehler(f"Die XML-Datei ist nicht lesbar: {e}")
    if wurzel.find(".//BkToCstmrStmt") is None and wurzel.find(".//Stmt") is None:
        raise ImportFehler("Die XML-Datei ist kein CAMT.053-Kontoauszug.")
    umsaetze = []
    for ntry in wurzel.iter("Ntry"):
        betrag = betrag_cent(_text(ntry, "Amt"))
        if betrag is None:
            continue
        if _text(ntry, "CdtDbtInd") == "DBIT":
            betrag = -betrag
        tag = _text(ntry, "BookgDt/Dt") or _text(ntry, "BookgDt/DtTm")[:10]
        valuta = _text(ntry, "ValDt/Dt") or _text(ntry, "ValDt/DtTm")[:10]
        tx = ntry.find("NtryDtls/TxDtls")
        tx = tx if tx is not None else ntry
        zweck = " ".join(x.text.strip() for x in tx.iter("Ustrd") if x.text) or _text(ntry, "AddtlNtryInf")
        partei = "Dbtr" if betrag > 0 else "Cdtr"
        name = _text(tx, f"RltdPties/{partei}/Nm") or _text(tx, f"RltdPties/{partei}/Pty/Nm")
        iban = _text(tx, f"RltdPties/{partei}Acct/Id/IBAN")
        if tag:
            umsaetze.append({"buchungstag": tag[:10], "valuta": valuta[:10] or None, "betrag": betrag, "name": name,
                             "iban": iban, "zweck": zweck})
    return umsaetze


def lesen(dateiname, roh):
    """Gibt (Format, [Umsätze]) zurück."""
    if roh[:2] == b"PK":  # ZIP mit mehreren CAMT-Dateien
        umsaetze = []
        with zipfile.ZipFile(io.BytesIO(roh)) as z:
            for name in sorted(z.namelist()):
                if name.lower().endswith(".xml"):
                    umsaetze += _camt_lesen(z.read(name))
        return "CAMT.053 (ZIP)", umsaetze
    if roh.lstrip()[:1] == b"<":
        return "CAMT.053", _camt_lesen(roh)
    return "CSV", _csv_lesen(roh)


def importieren(con, dateiname, roh):
    """Liest den Auszug ein und speichert neue Umsätze. Muss in einer Transaktion laufen."""
    if not roh:
        raise ImportFehler("Die Datei ist leer.")
    art, umsaetze = lesen(dateiname, roh)
    if not umsaetze:
        raise ImportFehler("In der Datei wurden keine Umsätze gefunden.")
    cur = con.execute("INSERT INTO bank_importe (dateiname, format, sha256, importiert_am, benutzer) VALUES (?,?,?,?,?)",
                      (dateiname, art, hashlib.sha256(roh).hexdigest(), dbm.jetzt_berlin(), dbm.aktueller_benutzer()))
    import_id = cur.lastrowid
    neu = doppelt = 0
    gesehen = {}
    for u in umsaetze:
        basis = "|".join([u["buchungstag"], str(u["betrag"]), _normal(u["zweck"]), _normal(u["name"]), u["iban"]])
        gesehen[basis] = gesehen.get(basis, 0) + 1  # gleiche Buchung mehrfach am selben Tag
        kennung = hashlib.sha256(f"{basis}|{gesehen[basis]}".encode()).hexdigest()
        if con.execute("SELECT 1 FROM bank_umsaetze WHERE kennung=?", (kennung,)).fetchone():
            doppelt += 1
            continue
        con.execute("INSERT INTO bank_umsaetze (import_id, kennung, buchungstag, valuta, betrag, name, iban, "
                    "verwendungszweck) VALUES (?,?,?,?,?,?,?,?)",
                    (import_id, kennung, u["buchungstag"], u["valuta"], u["betrag"], u["name"], u["iban"], u["zweck"]))
        neu += 1
    con.execute("UPDATE bank_importe SET anzahl=?, doppelt=? WHERE id=?", (neu, doppelt, import_id))
    dbm.protokollieren("bank_import", "bank", import_id, {"datei": dateiname, "format": art, "neu": neu,
                                                          "doppelt": doppelt}, con=con)
    return {"format": art, "neu": neu, "doppelt": doppelt}


# ---------------------------------------------------------------- Vorschläge & Zuordnung

def _nummer_muster(nummer):
    teile = [t for t in re.split(r"[^A-Za-z0-9]+", nummer or "") if t]
    if not teile:
        return None
    teile[-1] = teile[-1].lstrip("0") or "0"
    return re.compile(r"(?<![A-Za-z0-9])" + r"[\s\-_/.]*".join(re.escape(t) if i < len(teile) - 1 else r"0*" + re.escape(t)
                                                              for i, t in enumerate(teile)) + r"(?!\d)", re.I)


def vorschlag(con, umsatz, offene=None):
    """Bester Zuordnungsvorschlag für einen Zahlungseingang: dict(dokument, grund, sicher) oder None."""
    if umsatz["betrag"] <= 0:
        return None
    offene = offene if offene is not None else zlg.offene_posten(con)
    zweck = f"{umsatz['verwendungszweck'] or ''} {umsatz['name'] or ''}"
    for p in offene:  # Rechnungsnummer oder Mahnnummer im Verwendungszweck
        nummern = [p["d"]["nummer"]] + [m["nummer"] for m in con.execute(
            "SELECT nummer FROM mahnungen WHERE dokument_id=?", (p["d"]["id"],))]
        for nr in nummern:
            muster = _nummer_muster(nr)
            if muster and muster.search(zweck):
                ganz = umsatz["betrag"] in (p["s"]["offen"], p["s"]["offen"] + p["s"]["gebuehren_offen"])
                return {"p": p, "sicher": ganz, "grund": f"Nummer {nr} im Verwendungszweck"
                        + ("" if ganz else f" – Betrag weicht ab (offen {euro(p['s']['offen'])})")}
    passend = [p for p in offene if p["s"]["offen"] == umsatz["betrag"]]
    name = _normal(umsatz["name"])
    mit_name = [p for p in passend if name and (_normal(p["d"]["nachname"]) and _normal(p["d"]["nachname"]) in name
                                                or _normal(p["d"]["firma"]) and _normal(p["d"]["firma"]) in name)]
    if len(mit_name) == 1:
        return {"p": mit_name[0], "sicher": False, "grund": "Betrag und Name passen"}
    if len(passend) == 1:
        return {"p": passend[0], "sicher": False, "grund": "nur der Betrag passt – bitte prüfen"}
    return None


def zuordnen(con, umsatz_id, dokument_id, betrag=None):
    """Bestätigte Zuordnung: erzeugt die Zahlung (Überweisung) zur Rechnung. Muss in einer Transaktion laufen."""
    u = con.execute("SELECT * FROM bank_umsaetze WHERE id=?", (umsatz_id,)).fetchone()
    if not u or u["status"] != "offen":
        raise EingabeFehler("Der Umsatz ist bereits bearbeitet.")
    if u["betrag"] <= 0:
        raise EingabeFehler("Ausgänge können erst mit den Eingangsrechnungen (Ausbaustufe 7) zugeordnet werden.")
    zid = zlg.erfassen(con, dokument_id, min(u["buchungstag"], date.today().isoformat()), betrag or u["betrag"],
                       "ueberweisung", f"Bank: {u['name'] or ''} – {(u['verwendungszweck'] or '')[:120]}".strip(),
                       bank_umsatz_id=umsatz_id)
    con.execute("UPDATE bank_umsaetze SET status='zugeordnet', zahlung_id=?, bearbeitet_am=?, bearbeitet_von=? "
                "WHERE id=?", (zid, dbm.jetzt_berlin(), dbm.aktueller_benutzer(), umsatz_id))
    return zid


def ignorieren(con, umsatz_id, wieder_oeffnen=False):
    u = con.execute("SELECT * FROM bank_umsaetze WHERE id=?", (umsatz_id,)).fetchone()
    if not u or u["status"] == "zugeordnet":
        raise EingabeFehler("Zugeordnete Umsätze können nur über das Stornieren der Zahlung gelöst werden.")
    con.execute("UPDATE bank_umsaetze SET status=?, bearbeitet_am=?, bearbeitet_von=? WHERE id=?",
                ("offen" if wieder_oeffnen else "ignoriert", dbm.jetzt_berlin(), dbm.aktueller_benutzer(), umsatz_id))
