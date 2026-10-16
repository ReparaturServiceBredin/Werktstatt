"""Datensicherung: ZIP-Archiv mit Datenbank, Dokumenten und Belegen.

Der Schlüssel für das E-Mail-Passwort wird bewusst NICHT mitgesichert. Nach einer Wiederherstellung
muss das E-Mail-Passwort einmal neu eingegeben werden; dafür ist ein Backup auf dem NAS allein wertlos
für jemanden, der an Ihr E-Mail-Passwort will.
"""
import shutil
import sqlite3
import tempfile
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

from . import db as dbm

ORDNER_IM_BACKUP = ["dokumente", "belege", "bilder", "fotos", "exporte"]


def backup_erstellen(daten_dir, db_pfad, einst=None):
    daten = Path(daten_dir)
    ziel_ordner = daten / "backups"
    ziel_ordner.mkdir(parents=True, exist_ok=True)
    name = f"backup_{datetime.now():%Y-%m-%d_%H%M%S}.zip"
    ziel = ziel_ordner / name
    with tempfile.TemporaryDirectory() as tmp:
        kopie = Path(tmp) / "werkstatt.db"
        quelle = sqlite3.connect(db_pfad)
        ziel_db = sqlite3.connect(kopie)
        with ziel_db:
            quelle.backup(ziel_db)  # konsistente Kopie auch während das Programm läuft
        quelle.close()
        ziel_db.close()
        with zipfile.ZipFile(ziel, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(kopie, "werkstatt.db")
            for ordner in ORDNER_IM_BACKUP:
                for datei in (daten / ordner).rglob("*") if (daten / ordner).exists() else []:
                    if datei.is_file():
                        z.write(datei, datei.relative_to(daten).as_posix())
            z.writestr("LIESMICH.txt",
                       "Backup Werkstatt Sauter\n"
                       f"Erstellt: {datetime.now():%d.%m.%Y %H:%M}\n\n"
                       "Wiederherstellen: Programm beenden, Inhalt dieses ZIP in den Ordner 'Daten' entpacken\n"
                       "(vorhandene Dateien ersetzen), Programm starten, E-Mail-Passwort neu eingeben.\n")
    kopiert_nach = None
    if einst and einst.get("backup_ziel"):
        extern = Path(einst["backup_ziel"])
        try:
            extern.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ziel, extern / name)
            kopiert_nach = str(extern / name)
        except OSError as e:
            kopiert_nach = f"FEHLER: {e}"
    if einst:
        _aufraeumen(ziel_ordner, int(einst.get("backup_behalten") or 30))
    return ziel, kopiert_nach


def _aufraeumen(ordner, behalten):
    dateien = sorted(ordner.glob("backup_*.zip"))
    for alt in dateien[:-behalten] if behalten > 0 else []:
        alt.unlink(missing_ok=True)


def auto_backup(daten_dir, db_pfad):
    """Einmal täglich beim Start bzw. beim ersten Aufruf ein Backup anlegen."""
    con = dbm.verbinden(db_pfad)
    try:
        einst = dbm.einstellungen(con)
        if not einst.get("backup_auto"):
            return None
        letztes = einst.get("letztes_backup")
        if letztes and datetime.fromisoformat(letztes) > datetime.now() - timedelta(hours=20):
            return None
        ziel, extern = backup_erstellen(daten_dir, db_pfad, einst)
        dbm.einstellungen_speichern({"letztes_backup": dbm.jetzt()}, con)
        dbm.protokollieren("backup_automatisch", "system", None, {"datei": ziel.name, "extern": extern}, con=con)
        return ziel
    finally:
        con.close()
