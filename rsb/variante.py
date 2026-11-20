"""Programm-Varianten aus demselben Code.

- „sauter“: Werkstatt Sauter (Kfz-Werkstatt) – Standard.
- „reifen“: Reifen & Teile (Reifenwerkstatt mit Autoteile-Verkauf): Reifeneinlagerung, Reifengrößen-Suche,
  Thekenverkauf, Lager & Einkauf; ohne Handy-/QR-Code-Funktionen und ohne SMS.

Gewählt wird die Variante über die Umgebungsvariable RSB_VARIANTE (die EXE „Reifen-Teile.exe“ setzt sie selbst,
siehe start_exe_reifen.py) bzw. in Tests über create_app(variante=…). Jede Variante hat eigenen Namen, eigenen
Datenordner, eigenen Port, eigenes Sitzungs-Cookie und einen eigenen Update-Kanal – mehrere Varianten können auf
demselben PC laufen, ohne sich zu stören.
"""
import os

VARIANTEN = {
    "sauter": {
        "programm": "Werkstatt Sauter",
        "kurz": "Werkstatt-Sauter",         # EXE-, Ordner- und Symbolname
        "zusatz": "Kfz-Service",
        "version": None,                    # wird aus rsb/__init__.py (VERSION_NUMMER) gesetzt
        "port": 5100,
        "cookie": "werkstatt_sauter",
        "tag_praefix": "v",                 # GitHub-Releases v1.2.1 …
        "aenderungen": "AENDERUNGEN.md",
        "handy": True,                      # QR-Code/Handy-Seiten, SMS, Programm im WLAN
        "reifen": False,                    # Reifeneinlagerung, Reifengrößen, Thekenverkauf, Lager & Einkauf
        "taetigkeit": "Kfz-Reparatur und -Wartung, Verkauf von Ersatzteilen.",
    },
    "reifen": {
        "programm": "Reifen & Teile",
        "kurz": "Reifen-Teile",
        "zusatz": "Reifenservice & Autoteile",
        "version": "1.0.0",
        "port": 5150,
        "cookie": "reifen_teile",
        "tag_praefix": "reifen-v",          # GitHub-Releases reifen-v1.0.0 … (eigener Update-Kanal)
        "aenderungen": "AENDERUNGEN_REIFEN.md",
        "handy": False,
        "reifen": True,
        "bilder": {"logo_standard.png": "logo_reifen.png", "symbol.png": "symbol_reifen.png",
                   "favicon.png": "favicon_reifen.png"},
        "taetigkeit": "Reifenservice (Montage, Wuchten, Einlagerung), Kfz-Service und Verkauf von Reifen, "
                      "Felgen und Autoteilen.",
    },
}

_aktiv = {"name": None}


def setzen(name):
    """Variante für diesen Prozess festlegen (create_app ruft das auf)."""
    name = (name or "sauter").strip().lower()
    if name not in VARIANTEN:
        raise ValueError(f"Unbekannte Programm-Variante: {name}")
    _aktiv["name"] = name
    return name


def name():
    return name_()


def name_():
    if _aktiv["name"] is None:
        setzen(os.environ.get("RSB_VARIANTE") or "sauter")
    return _aktiv["name"]


def wert(schluessel):
    return VARIANTEN[name()][schluessel]


def programm():
    return wert("programm")


def kurz():
    return wert("kurz")


def exe_name():
    return kurz() + ".exe"


def hat(funktion):
    """hat("handy"), hat("reifen") …"""
    return bool(VARIANTEN[name()].get(funktion))


def bild(name):
    """Dateiname eines Bildes in static/bilder für diese Variante (eigenes Logo/Symbol)."""
    return (VARIANTEN[name_()].get("bilder") or {}).get(name, name)


def version(standard=None):
    return wert("version") or standard or VARIANTEN["sauter"]["version"]
