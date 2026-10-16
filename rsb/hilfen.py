"""Kleine Hilfsfunktionen: Geldbeträge, Datum, Platzhalter."""
import re
from datetime import date, datetime, timedelta


class EingabeFehler(ValueError):
    """Fehler, der dem Benutzer als verständliche Meldung angezeigt wird."""


def euro(cent, mit_zeichen=True):
    """1234567 -> '12.345,67 €'"""
    cent = int(cent or 0)
    vorzeichen = "-" if cent < 0 else ""
    cent = abs(cent)
    ganz, rest = divmod(cent, 100)
    text = f"{ganz:,}".replace(",", ".") + f",{rest:02d}"
    return f"{vorzeichen}{text}" + (" €" if mit_zeichen else "")


def cent_aus_text(text, leer=0):
    """'1.234,50' / '1234.5' / '89' / '89 €' -> Cent als int."""
    if text is None:
        return leer
    t = str(text).strip().replace("€", "").replace(" ", "")
    if t == "":
        return leer
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    try:
        wert = float(t)
    except ValueError:
        raise EingabeFehler(f"„{text}“ ist kein gültiger Betrag.")
    return int(round(wert * 100))


def zahl_aus_text(text, leer=0.0):
    if text is None or str(text).strip() == "":
        return leer
    t = str(text).strip().replace(" ", "")
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    try:
        return float(t)
    except ValueError:
        raise EingabeFehler(f"„{text}“ ist keine gültige Zahl.")


def menge_text(menge):
    menge = float(menge or 0)
    if menge == int(menge):
        return str(int(menge))
    return f"{menge:.2f}".rstrip("0").replace(".", ",")


def datum_de(iso):
    """'2026-10-14' -> '14.10.2026'"""
    if not iso:
        return ""
    try:
        return datetime.fromisoformat(str(iso)[:19]).strftime("%d.%m.%Y")
    except ValueError:
        return str(iso)


def zeit_de(iso):
    if not iso:
        return ""
    try:
        return datetime.fromisoformat(str(iso)).strftime("%d.%m.%Y %H:%M")
    except ValueError:
        return str(iso)


def heute_datum():
    """Heutiges Datum in Europe/Berlin – unabhängig von der Zeitzone des Rechners (z. B. UTC im Docker-Container)."""
    from datetime import datetime
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo("Europe/Berlin")).date()


def heute():
    return heute_datum().isoformat()


def plus_tage(iso, tage):
    return (date.fromisoformat(iso) + timedelta(days=int(tage))).isoformat()


def platzhalter_ersetzen(text, werte: dict):
    """Ersetzt {name} durch werte['name']; unbekannte Platzhalter bleiben stehen."""
    if not text:
        return ""
    return re.sub(r"\{(\w+)\}", lambda m: str(werte.get(m.group(1), m.group(0))), text)


def kunde_name(k):
    if not k:
        return ""
    k = dict(k)
    person = " ".join(x for x in [k.get("vorname"), k.get("nachname")] if x)
    if k.get("typ") == "firma" and k.get("firma"):
        return k["firma"]
    return person or k.get("firma") or ""


def anrede_brief(k):
    if not k:
        return "Guten Tag,"
    k = dict(k)
    anrede = (k.get("anrede") or "").strip()
    nachname = (k.get("nachname") or "").strip()
    if anrede == "Frau" and nachname:
        return f"Sehr geehrte Frau {nachname},"
    if anrede == "Herr" and nachname:
        return f"Sehr geehrter Herr {nachname},"
    return "Sehr geehrte Damen und Herren," if k.get("typ") == "firma" else "Guten Tag,"


def anschrift_zeilen(k):
    """Empfängeradresse als Zeilenliste (für Anschriftenfeld)."""
    if not k:
        return []
    k = dict(k)
    zeilen = []
    person = " ".join(x for x in [k.get("anrede") if k.get("anrede") in ("Herr", "Frau") else None,
                                  k.get("vorname"), k.get("nachname")] if x)
    if k.get("firma"):
        zeilen.append(k["firma"])
        if person:
            zeilen.append(person)
    elif person:
        zeilen.append(person)
    if k.get("strasse"):
        zeilen.append(k["strasse"])
    ort = " ".join(x for x in [k.get("plz"), k.get("ort")] if x)
    if ort:
        zeilen.append(ort)
    if k.get("land") and k["land"].strip().lower() not in ("deutschland", "de", "germany"):
        zeilen.append(k["land"].upper())
    return zeilen


def iban_format(iban):
    iban = (iban or "").replace(" ", "").upper()
    return " ".join(iban[i:i + 4] for i in range(0, len(iban), 4))


UNERLAUBT_IM_DATEINAMEN = '\\/:*?"<>|'


def sicherer_dateiname(name):
    """Dateiname, der unter Windows und Linux gültig ist: ohne \\ / : * ? " < > |, Steuerzeichen und Punkt/Leerzeichen
    am Ende. Gültige Namen (z. B. „RE-2026-0001“) bleiben unverändert – vorhandene Dateien werden also weiter gefunden."""
    t = "".join("_" if c in UNERLAUBT_IM_DATEINAMEN or ord(c) < 32 else c for c in str(name or ""))
    t = t.rstrip(" .")
    return t or "datei"
