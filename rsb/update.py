"""Automatische Updates der EXE-Version über GitHub-Releases (kostenlos, ohne eigenen Server).

Ablauf:
  1. Beim Start und danach alle paar Stunden wird
     https://api.github.com/repos/<REPO>/releases/latest abgefragt.
  2. Ist dort eine neuere Version, wird Werkstatt-Sauter.exe heruntergeladen und mit der
     veröffentlichten SHA-256-Prüfsumme verglichen.
  3. Vor dem Austausch wird ein Backup der Daten erstellt.
  4. Die laufende EXE wird umbenannt (Windows erlaubt das, löschen nicht), die neue an ihre
     Stelle gelegt und das Programm neu gestartet. Die alte Datei wird beim nächsten Start gelöscht.

Die Daten (Ordner „Daten“) werden dabei nie angefasst; Datenbank-Änderungen neuer Versionen
werden beim Start automatisch nachgezogen.
"""
import hashlib
import json
import os
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

REPO = os.environ.get("RSB_UPDATE_REPO", "ReparaturServiceBredin/Werktstatt")
API_URL = os.environ.get("RSB_UPDATE_API") or f"https://api.github.com/repos/{REPO}/releases/latest"
EXE_NAME = "Werkstatt-Sauter.exe"
TIMEOUT = 15


class UpdateFehler(Exception):
    pass


def ist_exe():
    """True, wenn das Programm als gebaute EXE (PyInstaller) läuft."""
    return bool(getattr(sys, "frozen", False))


def versions_tupel(text):
    """'v0.4.1' / '0.4.1 (Name)' -> (0, 4, 1)"""
    text = (text or "").strip().lstrip("vV").split(" ")[0]
    teile = []
    for t in text.split("."):
        ziffern = "".join(c for c in t if c.isdigit())
        teile.append(int(ziffern) if ziffern else 0)
    return tuple(teile + [0] * (3 - len(teile)))[:3]


def ist_neuer(kandidat, aktuell):
    return versions_tupel(kandidat) > versions_tupel(aktuell)


def _abrufen(url, timeout=TIMEOUT):
    anfrage = urllib.request.Request(url, headers={"User-Agent": "Werkstatt-Sauter-Updater",
                                                   "Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(anfrage, timeout=timeout) as antwort:
            return antwort.read()
    except OSError as e:
        raise UpdateFehler(f"Update-Server nicht erreichbar: {e}")


def neueste_version():
    """Liest die neueste Veröffentlichung. Gibt dict mit version, exe_url, sha_url, hinweise zurück."""
    try:
        daten = json.loads(_abrufen(API_URL))
    except ValueError:
        raise UpdateFehler("Antwort des Update-Servers ist ungültig.")
    assets = {a.get("name"): a.get("browser_download_url") for a in daten.get("assets", [])}
    if EXE_NAME not in assets:
        raise UpdateFehler("In der neuesten Version ist keine EXE-Datei enthalten.")
    return {
        "version": (daten.get("tag_name") or "").lstrip("vV"),
        "exe_url": assets[EXE_NAME],
        "sha_url": assets.get(EXE_NAME + ".sha256"),
        "hinweise": (daten.get("body") or "").strip(),
        "datum": daten.get("published_at") or "",
    }


def herunterladen(info, ziel: Path):
    """Lädt die neue EXE nach ziel und prüft die SHA-256-Prüfsumme."""
    if not info.get("sha_url"):
        raise UpdateFehler("Zur neuen Version fehlt die Prüfsumme – Update wird aus Sicherheitsgründen nicht installiert.")
    erwartet = _abrufen(info["sha_url"]).decode("ascii", "replace").split()[0].strip().lower()
    temp = ziel.with_suffix(ziel.suffix + ".download")
    anfrage = urllib.request.Request(info["exe_url"], headers={"User-Agent": "Werkstatt-Sauter-Updater"})
    h = hashlib.sha256()
    try:
        with urllib.request.urlopen(anfrage, timeout=120) as antwort, open(temp, "wb") as datei:
            while True:
                block = antwort.read(1024 * 256)
                if not block:
                    break
                h.update(block)
                datei.write(block)
    except OSError as e:
        temp.unlink(missing_ok=True)
        raise UpdateFehler(f"Download fehlgeschlagen: {e}")
    if h.hexdigest() != erwartet:
        temp.unlink(missing_ok=True)
        raise UpdateFehler("Die heruntergeladene Datei ist beschädigt (Prüfsumme stimmt nicht). Update abgebrochen.")
    temp.replace(ziel)
    return ziel


def exe_pfad():
    return Path(sys.executable).resolve()


def alte_versionen_aufraeumen():
    """Löscht die beim letzten Update umbenannte alte EXE (gelingt, sobald sie nicht mehr läuft)."""
    if not ist_exe():
        return
    exe = exe_pfad()
    for alt in exe.parent.glob(exe.stem + ".alt*"):
        for _ in range(10):
            try:
                alt.unlink()
                break
            except OSError:
                time.sleep(0.5)
    for rest in exe.parent.glob(exe.stem + ".neu*"):
        try:
            rest.unlink()
        except OSError:
            pass


def installieren(info, vor_austausch=None):
    """Lädt die neue Version herunter und tauscht die EXE aus. Startet NICHT neu."""
    if not ist_exe():
        raise UpdateFehler("Automatische Updates funktionieren nur in der EXE-Version des Programms.")
    exe = exe_pfad()
    neu = exe.with_name(exe.stem + ".neu" + exe.suffix)
    herunterladen(info, neu)
    try:
        os.chmod(neu, exe.stat().st_mode)  # ausführbar wie die bisherige Datei (wichtig außerhalb von Windows)
    except OSError:
        pass
    if vor_austausch:
        vor_austausch()
    alt = exe.with_name(exe.stem + ".alt" + exe.suffix)
    if alt.exists():
        try:
            alt.unlink()
        except OSError:
            alt = exe.with_name(f"{exe.stem}.alt{int(time.time())}{exe.suffix}")
    exe.rename(alt)  # die laufende Datei darf unter Windows umbenannt werden
    try:
        neu.rename(exe)
    except OSError:
        alt.rename(exe)  # zurückrollen
        raise UpdateFehler("Die neue Version konnte nicht an ihren Platz gelegt werden. Es bleibt bei der alten.")
    return exe


def neu_starten(verzoegerung=1.0):
    """Startet die (neue) EXE und beendet dieses Programm."""
    def _los():
        time.sleep(verzoegerung)
        umgebung = dict(os.environ, RSB_KEIN_BROWSER="1", RSB_WARTE_AUF_PORT="1")
        umgebung.pop("_MEIPASS2", None)
        umgebung.pop("_PYI_APPLICATION_HOME_DIR", None)
        umgebung["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
        try:
            subprocess.Popen([str(exe_pfad())], env=umgebung, cwd=str(exe_pfad().parent), close_fds=True)
        except OSError as e:
            print(f"Neustart fehlgeschlagen ({e}). Bitte Werkstatt-Sauter.exe von Hand neu starten.")
        from .fenster import symbol_entfernen
        symbol_entfernen()  # altes Symbol neben der Uhr ausblenden
        os._exit(0)

    threading.Thread(target=_los, daemon=True).start()
