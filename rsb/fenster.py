"""Programmfenster und Symbol im Infobereich (neben der Uhr) – statt schwarzem Konsolenfenster.

- Die Oberfläche öffnet sich als eigenes Fenster ohne Browser-Leiste (Microsoft Edge im App-Modus,
  ist bei Windows 11 immer dabei). Klappt das nicht, öffnet sich der normale Browser.
- Unten rechts neben der Uhr erscheint das Programmsymbol mit dem Menü
  „Buchhaltung öffnen“, „Daten-Ordner öffnen“, „Beenden“.
"""
import os
import shutil
import subprocess
import webbrowser
from pathlib import Path

SYMBOL = Path(__file__).parent / "static" / "bilder" / "symbol.png"
_symbol_ref = {"icon": None}


def _edge_pfad():
    if os.name != "nt":
        return None
    kandidaten = [shutil.which("msedge")]
    for basis in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles"), os.environ.get("LOCALAPPDATA")):
        if basis:
            kandidaten.append(os.path.join(basis, "Microsoft", "Edge", "Application", "msedge.exe"))
    return next((k for k in kandidaten if k and os.path.isfile(k)), None)


def oeffnen(adresse, modus="app"):
    """Öffnet die Oberfläche als eigenes Fenster (Edge-App-Modus) oder im Standardbrowser."""
    if modus == "app":
        edge = _edge_pfad()
        if edge:
            try:
                subprocess.Popen([edge, f"--app={adresse}", "--window-size=1400,900"],
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), close_fds=True)
                return
            except OSError:
                pass
    webbrowser.open(adresse)


def ordner_oeffnen(pfad):
    try:
        if os.name == "nt":
            os.startfile(pfad)  # noqa: S606 – öffnet den Explorer
        else:
            subprocess.Popen(["xdg-open", str(pfad)])
    except OSError:
        pass


def symbol_anzeigen(titel, adresse, daten_dir, modus_abfrage, beenden):
    """Zeigt das Symbol im Infobereich und blockiert, bis „Beenden“ gewählt wird.

    Gibt False zurück, wenn kein Symbol angezeigt werden kann (z. B. fehlendes Paket) –
    das Programm läuft dann einfach ohne Symbol weiter.
    """
    try:
        import pystray
        from PIL import Image
    except Exception:
        return False

    def menue_oeffnen(icon, item):
        oeffnen(adresse, modus_abfrage())

    def menue_daten(icon, item):
        ordner_oeffnen(daten_dir)

    def menue_beenden(icon, item):
        icon.visible = False
        icon.stop()
        beenden()

    menue = pystray.Menu(
        pystray.MenuItem("Buchhaltung öffnen", menue_oeffnen, default=True),
        pystray.MenuItem("Daten-Ordner öffnen", menue_daten),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Beenden", menue_beenden),
    )
    try:
        icon = pystray.Icon("Werkstatt-Sauter", Image.open(SYMBOL), titel, menue)
        _symbol_ref["icon"] = icon
        icon.run()
        return True
    except Exception:
        return False


def symbol_entfernen():
    icon = _symbol_ref.get("icon")
    if icon is not None:
        try:
            icon.visible = False
            icon.stop()
        except Exception:
            pass
