"""Fester Ablageort für alle Daten – unabhängig davon, von wo das Programm gestartet wird.

Bis Version 0.22 lag der Ordner „Daten“ neben der EXE bzw. dem Programmordner. Wurde das Programm von einer anderen
Stelle gestartet (Downloads, Desktop, start.bat), entstand dort ein zweiter, leerer Datenbestand. Jetzt gilt:

- Windows: %LOCALAPPDATA%\\Werkstatt-Sauter\\Daten   (wird nicht von OneDrive synchronisiert)
- Linux/macOS: $XDG_DATA_HOME bzw. ~/.local/share/Werkstatt-Sauter/Daten
- Umgebungsvariable RSB_DATEN überschreibt das (z. B. für Docker oder Tests).

Beim ersten Start mit dem festen Ort werden die bisherigen Datenordner gesucht (neben dem Programm, Desktop, Downloads,
Dokumente, OneDrive). Der Ordner mit den meisten Daten wird übernommen – kopiert, nicht verschoben – und danach geprüft:
gleiche Anzahl Datensätze in jeder Tabelle und gleiche Anzahl Dateien. Stimmt etwas nicht, wird die Kopie verworfen
und es bleibt beim bisherigen Ordner. Der alte Ordner bleibt unverändert liegen und bekommt eine Notiz.
"""
import json
import os
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ORDNER = ["dokumente", "belege", "bilder", "fotos", "exporte", "geheim", "backups"]
NOTIZ = "UMGEZOGEN – bitte nicht mehr verwenden.txt"


def fester_ort():
    if os.name == "nt":
        basis = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    else:
        basis = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return basis / "Werkstatt-Sauter" / "Daten"


def _programm_ordner():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _tabellen_zaehlen(db):
    con = sqlite3.connect(str(db), timeout=10)  # nicht nur lesend: eine evtl. WAL-Datei wird so mitgelesen
    try:
        namen = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' "
                                           "AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        return {n: con.execute(f'SELECT COUNT(*) FROM "{n}"').fetchone()[0] for n in namen}
    finally:
        con.close()


def _dateien_zaehlen(ordner):
    return {o: sum(1 for f in (ordner / o).rglob("*") if f.is_file()) if (ordner / o).is_dir() else 0
            for o in ORDNER}


def _gewicht(db):
    """Wie viel Arbeit steckt in einer Datenbank? (Kunden/Aufträge/Belege/Fotos/Artikel, dann Änderungsdatum)"""
    try:
        z = _tabellen_zaehlen(db)
    except sqlite3.Error:
        return (-1, -1, 0)
    inhalt = sum(z.get(t, 0) for t in ("kunden", "auftraege", "dokumente", "auftrag_fotos", "kassenbuch", "leihen"))
    letzte = max((p.stat().st_mtime for p in (Path(db), Path(str(db) + "-wal")) if p.exists()), default=0)
    return (inhalt, z.get("artikel", 0), letzte)


def kandidaten(ziel, suchorte=None):
    """Bisherige Datenordner (mit werkstatt.db), ohne den festen Ort selbst."""
    from .wiederherstellung import andere_datenordner
    liste = []
    neben = _programm_ordner() / "Daten" / "werkstatt.db"
    if neben.is_file():
        liste.append(neben.resolve())
    for f in andere_datenordner(ziel, suchorte):
        if f not in liste and NOTIZ not in {p.name for p in f.parent.iterdir()}:
            liste.append(f)
    return [f for f in liste if f.parent.resolve() != Path(ziel).resolve()]


def _kopieren(quelle_ordner, ziel):
    ziel.mkdir(parents=True, exist_ok=True)
    q = sqlite3.connect(str(quelle_ordner / "werkstatt.db"), timeout=15)
    z = sqlite3.connect(ziel / "werkstatt.db")
    with z:
        q.backup(z)  # konsistente Kopie inkl. Inhalt der WAL-Datei
    q.close()
    z.close()
    for o in ORDNER:
        if (quelle_ordner / o).is_dir():
            shutil.copytree(quelle_ordner / o, ziel / o, dirs_exist_ok=True)


def ermitteln(suchorte=None, ausgabe=print):
    """Datenordner bestimmen; beim ersten Mal bisherige Daten an den festen Ort übernehmen. Gibt den Pfad zurück."""
    if os.environ.get("RSB_DATEN"):
        return Path(os.environ["RSB_DATEN"]).resolve()
    ziel = fester_ort()
    if (ziel / "werkstatt.db").is_file():
        return ziel
    gefunden = sorted(kandidaten(ziel, suchorte), key=_gewicht, reverse=True)
    if not gefunden:
        return ziel  # erster Start überhaupt: neuer, leerer Datenbestand am festen Ort
    quelle = gefunden[0].parent
    try:
        _kopieren(quelle, ziel)
        vorher, nachher = _tabellen_zaehlen(quelle / "werkstatt.db"), _tabellen_zaehlen(ziel / "werkstatt.db")
        dateien_vorher, dateien_nachher = _dateien_zaehlen(quelle), _dateien_zaehlen(ziel)
        if vorher != nachher or any(dateien_nachher[o] < dateien_vorher[o] for o in ORDNER):
            raise RuntimeError(f"Prüfung fehlgeschlagen: Datensätze {vorher} ≠ {nachher} oder Dateien "
                               f"{dateien_vorher} ≠ {dateien_nachher}")
    except Exception as e:  # nie mit einer halben Kopie weiterarbeiten
        shutil.rmtree(ziel, ignore_errors=True)
        ausgabe(f"WARNUNG: Übernahme nach {ziel} fehlgeschlagen ({e}) – es bleibt beim bisherigen Ordner {quelle}.")
        return quelle
    bericht = {"zeitpunkt": datetime.now().isoformat(timespec="seconds"), "von": str(quelle), "nach": str(ziel),
               "datensaetze": nachher, "dateien": dateien_nachher,
               "weitere_ordner": [str(f.parent) for f in gefunden[1:]]}
    (ziel / "umzug.json").write_text(json.dumps(bericht, ensure_ascii=False, indent=1), encoding="utf-8")
    try:
        (quelle / NOTIZ).write_text(
            "Die Daten der Buchhaltung liegen seit "
            f"{datetime.now():%d.%m.%Y %H:%M} fest an diesem Ort:\n\n    {ziel}\n\n"
            "Dieser Ordner ist nur noch eine alte Kopie und wird vom Programm nicht mehr benutzt.\n"
            "Er kann gelöscht werden, sobald im Programm alles stimmt.\n", encoding="utf-8")
    except OSError:
        pass
    ausgabe(f"Daten übernommen: {quelle} → {ziel} ({sum(nachher.values())} Datensätze, "
            f"{sum(dateien_nachher.values())} Dateien, geprüft)")
    return ziel
