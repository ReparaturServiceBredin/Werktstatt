import sys
import types

from rsb import fenster


def test_symbol_menue_und_beenden(monkeypatch, tmp_path):
    """Simuliert pystray: prüft Menüeinträge und dass „Beenden“ das Programm beendet."""
    aufrufe = {"geoeffnet": [], "beendet": False}

    class MenuItem:
        def __init__(self, text, aktion, default=False):
            self.text, self.aktion, self.default = text, aktion, default

    class Menu:
        SEPARATOR = object()

        def __init__(self, *eintraege):
            self.eintraege = [e for e in eintraege if isinstance(e, MenuItem)]

    class Icon:
        def __init__(self, name, bild, titel, menue):
            self.menue, self.titel, self.visible = menue, titel, True

        def run(self):
            texte = {e.text: e for e in self.menue.eintraege}
            assert list(texte) == ["Buchhaltung öffnen", "Daten-Ordner öffnen", "Beenden"]
            assert texte["Buchhaltung öffnen"].default
            texte["Buchhaltung öffnen"].aktion(self, None)
            texte["Beenden"].aktion(self, None)

        def stop(self):
            self.gestoppt = True

    monkeypatch.setitem(sys.modules, "pystray", types.SimpleNamespace(MenuItem=MenuItem, Menu=Menu, Icon=Icon))
    monkeypatch.setattr(fenster, "oeffnen", lambda adresse, modus: aufrufe["geoeffnet"].append((adresse, modus)))
    ok = fenster.symbol_anzeigen("Titel", "http://localhost:5000", tmp_path, lambda: "app",
                                 lambda: aufrufe.__setitem__("beendet", True))
    assert ok and aufrufe["beendet"] and aufrufe["geoeffnet"] == [("http://localhost:5000", "app")]


def test_ohne_edge_normaler_browser(monkeypatch):
    geoeffnet = []
    monkeypatch.setattr(fenster, "_edge_pfad", lambda: None)
    monkeypatch.setattr(fenster.webbrowser, "open", lambda url: geoeffnet.append(url))
    fenster.oeffnen("http://localhost:5000", "app")
    assert geoeffnet == ["http://localhost:5000"]
