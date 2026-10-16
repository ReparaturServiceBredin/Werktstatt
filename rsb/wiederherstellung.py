"""Wiederherstellung aus einer Sicherung – mit Inhaltsvorschau, vorher wird der aktuelle Stand vollständig gesichert.

Ablauf: In den Einstellungen (Backup) wird eine Quelle gewählt und vorgemerkt (Datei „wiederherstellen.json“ im
Datenordner). Beim nächsten Programmstart – bevor die Datenbank geöffnet wird – wird zuerst der komplette aktuelle
Datenordner als ZIP gesichert und dann die gewählte Sicherung eingespielt. Dateien (PDFs, Fotos) werden ergänzt, nie
gelöscht.

Quellen: Sicherungen im Ordner backups (ZIP und vor_update_*.db) sowie andere Datenordner mit einer werkstatt.db an
den üblichen Stellen (Desktop, Downloads, Dokumente, OneDrive).
"""
import json
import re
import shutil
import sqlite3
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

MARKE = "wiederherstellen.json"
DATEI_ORDNER = ["dokumente", "belege", "bilder", "fotos", "exporte"]
ZAEHLEN = [("kunden", "Kunden"), ("auftraege", "Aufträge"), ("artikel", "Artikel"), ("dokumente", "Belege"),
           ("auftrag_fotos", "Fotos")]


def _db_inhalt(db_pfad):
    """Anzahlen und Firmendaten einer Datenbank (nur lesend)."""
    erg = {"anzahl": {}, "firma": "", "strasse": "", "imap": "", "fehler": ""}
    try:
        con = sqlite3.connect(f"file:{Path(db_pfad).as_posix()}?mode=ro", uri=True, timeout=5)
        try:
            tabellen = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            for t, _ in ZAEHLEN:
                if t in tabellen:
                    erg["anzahl"][t] = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            if "einstellungen" in tabellen:
                werte = dict(con.execute("SELECT schluessel, wert FROM einstellungen WHERE schluessel IN "
                                         "('firma_name', 'strasse', 'ort', 'imap_host')").fetchall())
                lesen = lambda k: json.loads(werte[k]) if werte.get(k) else ""  # noqa: E731
                erg["firma"] = lesen("firma_name")
                erg["strasse"] = " ".join(x for x in (lesen("strasse"), lesen("ort")) if x)
                erg["imap"] = lesen("imap_host")
        finally:
            con.close()
    except (sqlite3.Error, ValueError) as e:
        erg["fehler"] = f"nicht lesbar ({e})"
    return erg


def inhalt(quelle):
    """Inhaltsvorschau einer Quelle: {anzahl: {...}, firma, strasse, imap, dateien}."""
    p = Path(quelle)
    if p.suffix.lower() == ".zip":
        with tempfile.TemporaryDirectory() as tmp, zipfile.ZipFile(p) as z:
            namen = z.namelist()
            if "werkstatt.db" not in namen:
                return {"anzahl": {}, "fehler": "keine Datenbank im ZIP", "dateien": 0}
            z.extract("werkstatt.db", tmp)
            erg = _db_inhalt(Path(tmp) / "werkstatt.db")
            erg["dateien"] = sum(1 for n in namen if n.split("/")[0] in DATEI_ORDNER and not n.endswith("/"))
            return erg
    erg = _db_inhalt(p)
    if p.name == "werkstatt.db":  # anderer Datenordner: Dateien daneben zählen
        erg["dateien"] = sum(1 for o in DATEI_ORDNER if (p.parent / o).is_dir()
                             for f in (p.parent / o).rglob("*") if f.is_file())
    else:
        erg["dateien"] = None
    return erg


def _kandidaten_ordner():
    heim = Path.home()
    basis = [heim / n for n in ("Desktop", "Downloads", "Documents", "Dokumente")]
    for od in heim.glob("OneDrive*"):
        basis += [od, od / "Desktop", od / "Dokumente", od / "Documents", od / "Downloads"]
    return [b for b in basis if b.is_dir()]


def andere_datenordner(daten_dir, ordner=None):
    """werkstatt.db in anderen Ordnern (bis zu 3 Ebenen tief unter Desktop/Downloads/Dokumente/OneDrive)."""
    eigene = (Path(daten_dir) / "werkstatt.db").resolve()
    gefunden = []
    for b in ordner if ordner is not None else _kandidaten_ordner():
        for tiefe in ("werkstatt.db", "*/werkstatt.db", "*/*/werkstatt.db", "*/*/*/werkstatt.db"):
            try:
                for f in Path(b).glob(tiefe):
                    if f.is_file() and f.resolve() != eigene and "backups" not in f.parts and f.resolve() not in gefunden:
                        gefunden.append(f.resolve())
            except OSError:
                continue
    return gefunden


def quellen(daten_dir, ordner=None):
    """Alle Quellen, neueste zuerst: [{pfad, art, name, zeit, groesse, inhalt}]."""
    liste = []
    bk = Path(daten_dir) / "backups"
    for f in list(bk.glob("backup_*.zip")) + list(bk.glob("vor_update_*.db")) + list(bk.glob("vor_wiederherstellung_*.zip")):
        liste.append({"pfad": str(f), "art": "Sicherung", "name": f.name})
    for f in andere_datenordner(daten_dir, ordner):
        liste.append({"pfad": str(f), "art": "Anderer Datenordner", "name": str(f.parent)})
    for q in liste:
        st = Path(q["pfad"]).stat()
        m = re.search(r"(\d{4}-\d{2}-\d{2})_(\d{2})(\d{2})(\d{2})", Path(q["pfad"]).name)
        q["zeit"] = (f"{m.group(1)}T{m.group(2)}:{m.group(3)}:{m.group(4)}" if m
                     else datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"))
        q["groesse"] = st.st_size
        q["inhalt"] = inhalt(q["pfad"])
    return sorted(liste, key=lambda q: q["zeit"], reverse=True)


def vormerken(daten_dir, quelle):
    gueltig = {q["pfad"] for q in quellen(daten_dir)}
    if str(quelle) not in gueltig:
        raise ValueError("Diese Sicherung wurde nicht gefunden.")
    (Path(daten_dir) / MARKE).write_text(json.dumps({"quelle": str(quelle), "vorgemerkt": datetime.now().isoformat(
        timespec="seconds")}, ensure_ascii=False), encoding="utf-8")


def vorgemerkt(daten_dir):
    p = Path(daten_dir) / MARKE
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None
    except (OSError, ValueError):
        return None


def _sichern(daten):
    """Kompletten aktuellen Datenordner sichern (inkl. Schlüssel – bleibt lokal), ohne den Ordner backups."""
    ziel = daten / "backups" / f"vor_wiederherstellung_{datetime.now():%Y-%m-%d_%H%M%S}.zip"
    ziel.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(ziel, "w", zipfile.ZIP_DEFLATED) as z:
        for f in daten.rglob("*"):
            if f.is_file() and "backups" not in f.relative_to(daten).parts and f.name != MARKE:
                z.write(f, f.relative_to(daten).as_posix())
    return ziel


def _datei_ergaenzen(quelle, ziel):
    """Datei übernehmen, ohne vorhandene andere Dateien zu überschreiben (bei Namensgleichheit: ersetzen)."""
    ziel.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(quelle, ziel)


def ausfuehren(daten_dir):
    """Beim Programmstart aufrufen, bevor die Datenbank geöffnet wird. Gibt einen Bericht zurück oder None."""
    daten = Path(daten_dir)
    marke = vorgemerkt(daten)
    if not marke:
        return None
    quelle = Path(marke["quelle"])
    (daten / MARKE).unlink(missing_ok=True)  # nie zweimal einspielen
    if not quelle.is_file():
        return {"ok": False, "meldung": f"Sicherung {quelle} nicht mehr vorhanden – nichts geändert."}
    sicherung = _sichern(daten)
    db = daten / "werkstatt.db"
    with tempfile.TemporaryDirectory() as tmp:
        if quelle.suffix.lower() == ".zip":
            with zipfile.ZipFile(quelle) as z:
                for n in z.namelist():
                    teile = Path(n).parts
                    if n.endswith("/") or ".." in teile or Path(n).is_absolute():
                        continue
                    if n == "werkstatt.db":
                        z.extract(n, tmp)
                    elif teile[0] in DATEI_ORDNER + (["geheim"] if quelle.name.startswith("vor_wiederherstellung_")
                                                    else []):
                        z.extract(n, tmp)
                        _datei_ergaenzen(Path(tmp) / n, daten / n)
            neue_db = Path(tmp) / "werkstatt.db"
        else:
            neue_db = Path(tmp) / "werkstatt.db"
            q = sqlite3.connect(f"file:{quelle.as_posix()}?mode=ro", uri=True)
            z = sqlite3.connect(neue_db)
            with z:
                q.backup(z)  # konsistent, inkl. Inhalt einer evtl. vorhandenen WAL-Datei
            q.close()
            z.close()
            if quelle.name == "werkstatt.db":  # anderer Datenordner: Dateien und Schlüssel mitnehmen
                for o in DATEI_ORDNER + ["geheim"]:
                    for f in (quelle.parent / o).rglob("*") if (quelle.parent / o).is_dir() else []:
                        if f.is_file():
                            _datei_ergaenzen(f, daten / f.relative_to(quelle.parent))
        if not neue_db.is_file():
            return {"ok": False, "meldung": "In der Sicherung ist keine Datenbank – nichts geändert.",
                    "sicherung": str(sicherung)}
        for rest in (db.with_name(db.name + "-wal"), db.with_name(db.name + "-shm")):
            rest.unlink(missing_ok=True)
        shutil.copy2(neue_db, db)
    bericht = {"ok": True, "quelle": str(quelle), "sicherung": str(sicherung), "inhalt": _db_inhalt(db)}
    (daten / "backups" / "letzte_wiederherstellung.json").write_text(json.dumps(bericht, ensure_ascii=False, indent=1),
                                                                    encoding="utf-8")
    return bericht
