"""Kopie versendeter E-Mails per IMAP im Ordner „Gesendet“ ablegen.

SMTP verschickt nur – im Postfach (z. B. IONOS-Webmail, Outlook, Handy) erscheint die Mail erst, wenn
eine Kopie per IMAP-APPEND in den Gesendet-Ordner gelegt wird. Genau das macht dieses Modul.

Wichtig: Schlägt die Ablage fehl, gilt die Mail trotzdem als gesendet – sie wird NIE erneut verschickt.
"""
import base64
import imaplib
import re
import time

from .sicherheit import entschluesseln

TIMEOUT = 20


class AblageFehler(Exception):
    pass


# ------------------------------------------------------------------ IMAP-UTF-7 (RFC 3501, Ordnernamen)

def utf7_dekodieren(text: str) -> str:
    """'Gel&APY-schte Elemente' -> 'Gelöschte Elemente'"""
    def teil(m):
        inhalt = m.group(1)
        if inhalt == "":
            return "&"
        roh = inhalt.replace(",", "/")
        roh += "=" * (-len(roh) % 4)
        try:
            return base64.b64decode(roh).decode("utf-16-be")
        except (ValueError, UnicodeDecodeError):
            return m.group(0)
    return re.sub(r"&([^-]*)-", teil, text)


def utf7_kodieren(text: str) -> str:
    """'Gelöschte Elemente' -> 'Gel&APY-schte Elemente'"""
    ergebnis, puffer = [], []

    def leeren():
        if puffer:
            b = base64.b64encode("".join(puffer).encode("utf-16-be")).decode("ascii").rstrip("=").replace("/", ",")
            ergebnis.append(f"&{b}-")
            puffer.clear()

    for z in text:
        if 0x20 <= ord(z) <= 0x7E:
            leeren()
            ergebnis.append("&-" if z == "&" else z)
        else:
            puffer.append(z)
    leeren()
    return "".join(ergebnis)


def _quote(name: str) -> str:
    return '"' + name.replace("\\", "\\\\").replace('"', '\\"') + '"'


# ------------------------------------------------------------------ Einstellungen

def konfiguration(einst, ueberschreiben=None):
    """Liest die IMAP-Einstellungen für die Ablage (optional mit noch nicht gespeicherten Formularwerten)."""
    w = dict(einst)
    w.update({k: v for k, v in (ueberschreiben or {}).items() if v is not None})
    gleich = bool(w.get("gesendet_gleiche_zugangsdaten", True))
    benutzer = (w.get("smtp_benutzer") if gleich else w.get("gesendet_imap_benutzer")) or ""
    if "passwort_klartext" in w and w["passwort_klartext"]:
        passwort = w["passwort_klartext"]
    else:
        passwort = entschluesseln(w.get("smtp_passwort_enc") if gleich else w.get("gesendet_imap_passwort_enc"))
    try:
        port = int(w.get("gesendet_imap_port") or 993)
    except (TypeError, ValueError):
        port = 0
    return {
        "host": (w.get("gesendet_imap_host") or "").strip(),
        "port": port,
        "sicherheit": w.get("gesendet_imap_sicherheit") if w.get("gesendet_imap_sicherheit") in ("ssl", "starttls")
        else "ssl",
        "benutzer": benutzer.strip(),
        "passwort": passwort or "",
        "ordner": (w.get("gesendet_ordner") or "").strip(),
    }


def _pruefen(cfg):
    if not cfg["host"]:
        raise AblageFehler("Es ist kein IMAP-Server eingetragen (Einstellungen → E-Mail → IMAP).")
    if cfg["host"].lower() in ("localhost", "127.0.0.1", "::1"):
        raise AblageFehler(f"Der IMAP-Server „{cfg['host']}“ ist ungültig. Bitte z. B. imap.ionos.de eintragen.")
    if not 1 <= cfg["port"] <= 65535:
        raise AblageFehler("Der IMAP-Port ist ungültig (üblich: 993 für SSL/TLS, 143 für STARTTLS).")
    if not cfg["benutzer"] or not cfg["passwort"]:
        raise AblageFehler("Für IMAP fehlen Benutzername oder Passwort.")


def verbinden(cfg, imap_ssl=None, imap_plain=None):
    """Baut die Verbindung auf und meldet sich an. Fehler werden in verständliche Meldungen übersetzt."""
    from .imap_verbindung import ImapFehler
    from .imap_verbindung import verbinden as imap_verbinden
    _pruefen(cfg)
    try:
        return imap_verbinden(cfg["host"], cfg["port"], cfg["sicherheit"], cfg["benutzer"], cfg["passwort"],
                              imap_ssl=imap_ssl, imap_plain=imap_plain)
    except ImapFehler as e:
        raise AblageFehler(str(e))


def _abmelden(imap):
    try:
        imap.logout()
    except Exception:
        pass


_LIST_RE = re.compile(r'^\((?P<flags>[^)]*)\)\s+(?P<trenner>"(?:[^"\\]|\\.)*"|NIL)\s+(?P<name>.+)$')


def ordner_auflisten(imap):
    """Gibt [{'name': 'Gesendete Objekte', 'roh': '...', 'gesendet': True}, …] zurück."""
    typ, daten = imap.list()
    if typ != "OK":
        raise AblageFehler("Die Ordnerliste konnte nicht abgerufen werden.")
    ordner = []
    i = 0
    while i < len(daten or []):
        eintrag = daten[i]
        if isinstance(eintrag, tuple):  # Name als Literal: (b'(\\Flags) "/" {12}', b'Ordner Name')
            kopf, name_roh = eintrag[0].decode("utf-8", "replace"), eintrag[1].decode("utf-8", "replace")
            m = re.search(r"\(([^)]*)\)", kopf)
            flags = m.group(1) if m else ""
        elif eintrag:
            zeile = eintrag.decode("utf-8", "replace")
            m = _LIST_RE.match(zeile)
            if not m:
                i += 1
                continue
            flags, name_roh = m.group("flags"), m.group("name").strip()
            if name_roh.startswith('"') and name_roh.endswith('"'):
                name_roh = re.sub(r'\\(.)', r'\1', name_roh[1:-1])
        else:
            i += 1
            continue
        if "\\Noselect" not in flags and "\\NonExistent" not in flags:
            ordner.append({"name": utf7_dekodieren(name_roh), "roh": name_roh,
                           "gesendet": "\\Sent" in flags})
        i += 1
    return sorted(ordner, key=lambda o: (not o["gesendet"], o["name"].lower()))


def ordner_vorhanden(imap, name):
    typ, _ = imap.select(_quote(utf7_kodieren(name)), readonly=True)
    return typ == "OK"


def verbindung_testen(cfg, **imap_klassen):
    """Prüft Login und Ordner. Gibt eine Erfolgsmeldung zurück oder wirft AblageFehler."""
    imap = verbinden(cfg, **imap_klassen)
    try:
        if not cfg["ordner"]:
            return "Anmeldung erfolgreich. Bitte noch den Ordner für gesendete Mails auswählen („Ordner abrufen“)."
        if not ordner_vorhanden(imap, cfg["ordner"]):
            namen = ", ".join(o["name"] for o in ordner_auflisten(imap)[:12])
            raise AblageFehler(f"Anmeldung erfolgreich, aber den Ordner „{cfg['ordner']}“ gibt es nicht. "
                               f"Vorhanden sind z. B.: {namen}")
        return f"Verbindung erfolgreich – gesendete Mails werden in „{cfg['ordner']}“ abgelegt."
    finally:
        _abmelden(imap)


def ablegen(cfg, nachricht_bytes, **imap_klassen):
    """Legt die gesendete Nachricht (als Bytes) mit Flag \\Seen im Gesendet-Ordner ab."""
    if not cfg["ordner"]:
        raise AblageFehler("Es ist kein Ordner für gesendete Mails ausgewählt.")
    imap = verbinden(cfg, **imap_klassen)
    try:
        typ, antwort = imap.append(_quote(utf7_kodieren(cfg["ordner"])), r"(\Seen)",
                                   imaplib.Time2Internaldate(time.time()), nachricht_bytes)
        if typ != "OK":
            text = b" ".join(a for a in antwort if isinstance(a, bytes)).decode("utf-8", "replace")
            if "TRYCREATE" in text.upper() or "NONEXISTENT" in text.upper():
                raise AblageFehler(f"Der Ordner „{cfg['ordner']}“ existiert nicht.")
            raise AblageFehler(f"Der Server hat die Ablage abgelehnt: {text or typ}")
    except (OSError, imaplib.IMAP4.error) as e:
        raise AblageFehler(f"Ablage im Ordner „{cfg['ordner']}“ fehlgeschlagen: {e}")
    finally:
        _abmelden(imap)
