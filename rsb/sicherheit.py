"""Verschlüsselung der E-Mail-Zugangsdaten und Hilfen für Passwort/CSRF."""
import os
import secrets
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from flask import abort, current_app, request, session


def _schluessel_datei() -> Path:
    return Path(current_app.config["DATEN"]) / "geheim" / "schluessel.key"


def _fernet():
    pfad = _schluessel_datei()
    if not pfad.exists():
        pfad.parent.mkdir(parents=True, exist_ok=True)
        pfad.write_bytes(Fernet.generate_key())
        try:
            os.chmod(pfad, 0o600)
        except OSError:
            pass
    return Fernet(pfad.read_bytes())


def verschluesseln(klartext: str) -> str:
    if not klartext:
        return ""
    return _fernet().encrypt(klartext.encode("utf-8")).decode("ascii")


def entschluesseln(geheim: str) -> str:
    if not geheim:
        return ""
    try:
        return _fernet().decrypt(geheim.encode("ascii")).decode("utf-8")
    except InvalidToken:
        return ""


def sitzungs_schluessel(daten: Path) -> bytes:
    pfad = Path(daten) / "geheim" / "sitzung.key"
    if not pfad.exists():
        pfad.parent.mkdir(parents=True, exist_ok=True)
        pfad.write_bytes(secrets.token_bytes(32))
    return pfad.read_bytes()


def csrf_token():
    if "csrf" not in session:
        session["csrf"] = secrets.token_hex(16)
    return session["csrf"]


def csrf_pruefen():
    if request.method == "POST":
        token = request.form.get("csrf") or request.headers.get("X-CSRF")
        if not token or token != session.get("csrf"):
            abort(400, "Sicherheitsprüfung fehlgeschlagen. Bitte Seite neu laden und erneut versuchen.")
