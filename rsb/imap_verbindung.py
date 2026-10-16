"""Gemeinsamer IMAP-Verbindungsaufbau für Kontaktformular-Abruf und Gesendet-Ablage.

- „ssl“: direkt verschlüsselt (IMAP4_SSL, meist Port 993)
- „starttls“: zuerst unverschlüsselt verbinden (meist Port 143), sofort STARTTLS – erst danach Anmeldung.
  Schlägt STARTTLS fehl, wird abgebrochen. Es gibt keine Anmeldung ohne Verschlüsselung.
Fehler werden in verständliche deutsche Meldungen übersetzt.
"""
import imaplib
import socket
import ssl

TIMEOUT = 20
# Ausnahmeklassen einmal merken (unabhängig davon, ob imaplib.IMAP4 später ersetzt wird, z. B. in Tests)
IMAP_FEHLER = imaplib.IMAP4.error
IMAP_ABBRUCH = imaplib.IMAP4.abort
SICHERHEIT = {"ssl": "SSL/TLS (meist Port 993)", "starttls": "STARTTLS (meist Port 143)"}
STANDARD_PORT = {"ssl": 993, "starttls": 143}
HINWEIS_PORT = "Port und Verschlüsselung passen nicht zusammen (993 = SSL, 143 = STARTTLS)."


class ImapFehler(Exception):
    pass


def sicherheit_aus_port(port):
    """Für die Umstellung älterer Einstellungen: Port 993 → SSL/TLS, sonst STARTTLS."""
    try:
        return "ssl" if int(port) == 993 else "starttls"
    except (TypeError, ValueError):
        return "ssl"


def _passt_nicht(port, sicherheit):
    return (sicherheit == "ssl" and port == 143) or (sicherheit == "starttls" and port == 993)


def fehler_uebersetzen(e, host, port, sicherheit):
    """Technischen Fehler beim Verbindungsaufbau in eine verständliche Meldung übersetzen."""
    ziel = f"{host}:{port} ({SICHERHEIT.get(sicherheit, sicherheit)})"
    zusatz = f" {HINWEIS_PORT}" if _passt_nicht(port, sicherheit) else ""
    tipp = zusatz or (" Ist Port 993 gesperrt, STARTTLS mit Port 143 versuchen." if sicherheit == "ssl" else
                      " Bitte prüfen, ob der Port in Ihrem Netzwerk freigegeben ist.")
    text = str(e)
    if isinstance(e, socket.gaierror):
        return f"Der IMAP-Server „{host}“ wurde nicht gefunden. Bitte den Servernamen prüfen (z. B. imap.ionos.de)."
    if isinstance(e, ssl.SSLError) or "SSL" in text:
        if "WRONG_VERSION_NUMBER" in text or "wrong version number" in text.lower() or "UNKNOWN_PROTOCOL" in text:
            return f"{HINWEIS_PORT} Aktuell: {ziel}."
        if "CERTIFICATE_VERIFY_FAILED" in text:
            return (f"Das Sicherheitszertifikat von {host} konnte nicht geprüft werden. Bitte den Servernamen genau so "
                    "eintragen, wie ihn der Anbieter angibt. Manche Virenscanner mit E-Mail-Prüfung verursachen das "
                    "ebenfalls.")
        return f"Verschlüsselte Verbindung zu {ziel} fehlgeschlagen ({getattr(e, 'reason', None) or text}).{zusatz}"
    if isinstance(e, ConnectionRefusedError):
        return (f"IMAP-Server {ziel} ist nicht erreichbar: Verbindung abgelehnt – der Port ist geschlossen oder durch "
                f"eine Firewall gesperrt.{tipp}")
    if isinstance(e, (TimeoutError, socket.timeout)):
        return (f"IMAP-Server {ziel} ist nicht erreichbar: keine Antwort innerhalb von {TIMEOUT} Sekunden "
                f"(Zeitüberschreitung). Vermutlich ist der Port gesperrt.{tipp}")
    if isinstance(e, ConnectionResetError):
        return f"Der Server {ziel} hat die Verbindung getrennt.{zusatz}"
    return f"Verbindung zum IMAP-Server {ziel} fehlgeschlagen: {text}{zusatz}"


def abmelden(imap):
    try:
        imap.logout()
    except Exception:
        pass


def verbinden(host, port, sicherheit, benutzer, passwort, imap_ssl=None, imap_plain=None):
    """Baut die verschlüsselte Verbindung auf und meldet sich an. Gibt das IMAP-Objekt zurück.

    imap_ssl/imap_plain: nur für Tests (Ersatzklassen).
    """
    host = (host or "").strip()
    try:
        port = int(port)
    except (TypeError, ValueError):
        port = 0
    if sicherheit not in SICHERHEIT:
        raise ImapFehler("Bitte bei „Verschlüsselung“ SSL/TLS oder STARTTLS auswählen.")
    if not host:
        raise ImapFehler("Es ist kein IMAP-Server eingetragen.")
    if host.lower() in ("localhost", "127.0.0.1", "::1"):
        raise ImapFehler(f"Der IMAP-Server „{host}“ ist ungültig. Bitte z. B. imap.ionos.de eintragen.")
    if not 1 <= port <= 65535:
        raise ImapFehler("Der IMAP-Port ist ungültig (üblich: 993 für SSL/TLS, 143 für STARTTLS).")
    if not benutzer or not passwort:
        raise ImapFehler("Für IMAP fehlen Benutzername oder Passwort.")
    imap_ssl = imap_ssl or imaplib.IMAP4_SSL  # erst hier auflösen (Tests ersetzen imaplib.IMAP4_SSL)
    imap_plain = imap_plain or imaplib.IMAP4
    try:
        if sicherheit == "ssl":
            imap = imap_ssl(host, port, ssl_context=ssl.create_default_context(), timeout=TIMEOUT)
        else:
            imap = imap_plain(host, port, timeout=TIMEOUT)
    except (OSError, IMAP_FEHLER) as e:
        raise ImapFehler(fehler_uebersetzen(e, host, port, sicherheit))
    if sicherheit == "starttls":
        try:
            imap.starttls(ssl_context=ssl.create_default_context())
        except IMAP_FEHLER as e:  # auch IMAP4.abort („TLS not supported by server“)
            abmelden(imap)
            if "not supported" in str(e).lower() or "starttls" in str(e).lower():
                raise ImapFehler(f"Der Server {host}:{port} bietet kein STARTTLS an. Aus Sicherheitsgründen wurde "
                                 "nicht unverschlüsselt angemeldet. Bitte SSL/TLS mit Port 993 verwenden oder beim "
                                 "Anbieter nachfragen.")
            raise ImapFehler(f"STARTTLS fehlgeschlagen ({e}) – aus Sicherheitsgründen wurde nicht angemeldet."
                             + (f" {HINWEIS_PORT}" if _passt_nicht(port, sicherheit) else ""))
        except OSError as e:
            abmelden(imap)
            raise ImapFehler("STARTTLS fehlgeschlagen – es wurde nicht angemeldet. "
                             + fehler_uebersetzen(e, host, port, sicherheit))
    try:
        imap.login(benutzer, passwort)
    except IMAP_ABBRUCH as e:
        abmelden(imap)
        raise ImapFehler(f"Verbindung während der Anmeldung abgebrochen: {e}")
    except IMAP_FEHLER:
        abmelden(imap)
        raise ImapFehler("Anmeldung am IMAP-Server fehlgeschlagen – Benutzername oder Passwort ist falsch. "
                         "(Gmail: nur mit App-Passwort.)")
    except OSError as e:
        abmelden(imap)
        raise ImapFehler(f"Verbindung während der Anmeldung abgebrochen: {fehler_uebersetzen(e, host, port, sicherheit)}")
    return imap
