"""SMS-Versand: vorbereitete Schnittstelle, noch ohne konkreten Anbieter.

Ein Anbieter wird als Unterklasse von SmsAnbieter angelegt und in ANBIETER eingetragen, z. B.:

    class MeinAnbieter(SmsAnbieter):
        name = "Mein Anbieter"
        def senden(self, nummer, text):
            ...  # HTTP-Aufruf der Anbieter-API; bei Fehlern SmsFehler werfen

    ANBIETER["mein_anbieter"] = MeinAnbieter

Zugangsdaten (API-Schlüssel) gehören verschlüsselt in die Einstellungen (sicherheit.verschluesseln).
"""
import re

from .hilfen import EingabeFehler


class SmsFehler(EingabeFehler):
    pass


class SmsAnbieter:
    name = "Basis"

    def __init__(self, einst):
        self.einst = einst

    def senden(self, nummer, text):  # pragma: no cover - Schnittstelle
        raise NotImplementedError


ANBIETER = {}


def nummer_normal(nummer):
    """0151 234 567 → +49151234567 (deutsche Nummern)."""
    n = re.sub(r"[^\d+]", "", nummer or "")
    if n.startswith("00"):
        n = "+" + n[2:]
    elif n.startswith("0"):
        n = "+49" + n[1:]
    if not re.fullmatch(r"\+\d{8,15}", n):
        raise SmsFehler(f"„{nummer}“ ist keine gültige Handynummer.")
    return n


def verfuegbar(einst):
    return (einst.get("sms_anbieter") or "") in ANBIETER


def senden(einst, nummer, text):
    schluessel = einst.get("sms_anbieter") or ""
    if schluessel not in ANBIETER:
        raise SmsFehler("Es ist noch kein SMS-Anbieter eingerichtet. Bitte E-Mail verwenden.")
    ANBIETER[schluessel](einst).senden(nummer_normal(nummer), text)
