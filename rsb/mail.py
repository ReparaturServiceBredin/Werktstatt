"""E-Mail-Versand über den eigenen SMTP-Zugang – optional mit Kopie im IMAP-Ordner „Gesendet“."""
import hashlib
import smtplib
import socket
import ssl
import time
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid

from . import db as dbm
from .sicherheit import entschluesseln

TIMEOUT = 20


class MailFehler(Exception):
    pass


def smtp_ziel(einst):
    """Prüft die gespeicherten SMTP-Einstellungen – nie stillschweigend auf localhost oder Standardwerte ausweichen."""
    host = (einst.get("smtp_host") or "").strip()
    if not host:
        raise MailFehler("Es ist noch kein E-Mail-Server (SMTP) eingerichtet – Einstellungen → E-Mail.")
    if host.lower() in ("localhost", "127.0.0.1", "::1"):
        raise MailFehler(f"Der SMTP-Server „{host}“ ist ungültig. Bitte z. B. smtp.ionos.de eintragen.")
    try:
        port = int(einst.get("smtp_port"))
    except (TypeError, ValueError):
        raise MailFehler("Der SMTP-Port fehlt oder ist ungültig (üblich: 587 mit STARTTLS, 465 mit SSL/TLS).")
    if not 1 <= port <= 65535:
        raise MailFehler("Der SMTP-Port ist ungültig (üblich: 587 mit STARTTLS, 465 mit SSL/TLS).")
    art = einst.get("smtp_sicherheit") or "starttls"
    if art not in ("starttls", "ssl", "keine"):
        raise MailFehler("Die SMTP-Verschlüsselung ist ungültig – bitte in den Einstellungen neu auswählen.")
    return host, port, art


def _verbindung(einst):
    host, port, art = smtp_ziel(einst)
    ziel = f"{host}:{port}"
    kontext = ssl.create_default_context()
    letzter_fehler = None
    for versuch in range(2):  # ein zweiter Versuch nur beim Verbindungsaufbau – dabei wird noch nichts gesendet
        try:
            if art == "ssl":
                server = smtplib.SMTP_SSL(host, port, timeout=TIMEOUT, context=kontext)
            else:
                server = smtplib.SMTP(host, port, timeout=TIMEOUT)
                if art == "starttls":
                    server.starttls(context=kontext)
            break
        except (ConnectionRefusedError, TimeoutError, socket.timeout) as e:
            letzter_fehler = e
            if versuch == 0:
                time.sleep(2)
                continue
            raise MailFehler(f"E-Mail-Server {ziel} hat die Verbindung abgelehnt bzw. nicht geantwortet ({e}). "
                             "Häufige Ursache: Virenschutz/Firewall blockiert den Versand aus Programmen "
                             "(z. B. E-Mail-Schutz von ESET/Avast) oder Port/Verschlüsselung passen nicht zusammen.")
        except socket.gaierror:
            raise MailFehler(f"E-Mail-Server „{host}“ wurde nicht gefunden. Bitte Servernamen und Internetverbindung prüfen.")
        except ssl.SSLError as e:
            raise MailFehler(f"Verschlüsselte Verbindung zu {ziel} fehlgeschlagen ({e.reason or e}). "
                             "Passen Port und Verschlüsselung? (587 = STARTTLS, 465 = SSL/TLS)")
        except (OSError, smtplib.SMTPException) as e:
            raise MailFehler(f"Verbindung zum E-Mail-Server {ziel} fehlgeschlagen: {e}")
    else:  # pragma: no cover
        raise MailFehler(f"Verbindung zum E-Mail-Server {ziel} fehlgeschlagen: {letzter_fehler}")
    try:
        if einst.get("smtp_benutzer"):
            server.login(einst["smtp_benutzer"], entschluesseln(einst.get("smtp_passwort_enc")))
        return server
    except smtplib.SMTPAuthenticationError:
        _beenden(server)
        raise MailFehler("Anmeldung am E-Mail-Server fehlgeschlagen. Bitte Benutzername und Passwort prüfen.")
    except (OSError, smtplib.SMTPException) as e:
        _beenden(server)
        raise MailFehler(f"Anmeldung am E-Mail-Server {ziel} fehlgeschlagen: {e}")


def _beenden(server):
    try:
        server.quit()
    except Exception:
        pass


def nachricht_bauen(einst, an, betreff, text, anhang=None, anhang_name=None, bcc=None, weitere=None):
    msg = EmailMessage()
    absender = einst.get("absender_email") or einst.get("smtp_benutzer")
    msg["From"] = formataddr((einst.get("absender_name") or "", absender))
    msg["To"] = an
    if bcc:
        msg["Bcc"] = bcc
    msg["Subject"] = betreff
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=(absender or "localhost").split("@")[-1])
    msg.set_content(text)
    if anhang:
        msg.add_attachment(anhang, maintype="application", subtype="pdf", filename=anhang_name)
    for daten, name in weitere or []:  # z. B. XRechnung-XML
        typ = ("application", "xml") if name.lower().endswith(".xml") else ("application", "octet-stream")
        msg.add_attachment(daten, maintype=typ[0], subtype=typ[1], filename=name)
    return msg


def senden(con, einst=None, an=None, betreff="", text="", anhang=None, anhang_name=None, dokument_id=None,
           weitere=None):
    """Sendet eine E-Mail und schreibt das Ergebnis ins Versandprotokoll (auch bei Fehlern).

    Die Einstellungen werden immer frisch aus der Datenbank gelesen; `einst` darf nur einzelne Werte
    überschreiben (z. B. bcc_an_mich beim Test).
    Rückgabe: Hinweistext, falls die Ablage im Gesendet-Ordner fehlschlug, sonst None.
    Wirft MailFehler, wenn der Versand selbst fehlschlug.
    """
    gespeichert = dbm.einstellungen(con)
    ueberschreiben = {k: v for k, v in (einst or {}).items() if k in ("bcc_an_mich",)}
    einst = {**gespeichert, **ueberschreiben}
    bcc = einst.get("absender_email") if einst.get("bcc_an_mich") else None
    sha = hashlib.sha256(anhang).hexdigest() if anhang else None
    status, fehler, msg = "gesendet", None, None
    try:
        msg = nachricht_bauen(einst, an, betreff, text, anhang, anhang_name, bcc, weitere)
        server = _verbindung(einst)
        try:
            server.send_message(msg)
        finally:
            _beenden(server)
    except MailFehler as e:
        status, fehler = "fehler", str(e)
    except (OSError, smtplib.SMTPException, ValueError) as e:
        status, fehler = "fehler", f"Versand fehlgeschlagen: {e}"

    ablage, hinweis = None, None
    if status == "gesendet" and einst.get("gesendet_aktiv"):
        from .imap_ablage import AblageFehler, ablegen, konfiguration
        try:
            ablegen(konfiguration(einst), msg.as_bytes())
            ablage = "abgelegt"
        except (AblageFehler, OSError, ValueError) as e:
            ablage = f"fehler: {e}"
            hinweis = f"E-Mail wurde gesendet, konnte aber nicht im Gesendet-Ordner abgelegt werden: {e}"

    with dbm.Transaktion(con):
        con.execute(
            "INSERT INTO versandprotokoll (dokument_id, zeitpunkt, empfaenger, bcc, betreff, text, anhang_name, "
            "anhang_sha256, status, fehlermeldung, ablage) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (dokument_id, dbm.jetzt(), an, bcc, betreff, text, anhang_name, sha, status, fehler, ablage),
        )
        if status == "gesendet" and dokument_id:
            con.execute("UPDATE dokumente SET versendet_am=? WHERE id=?", (dbm.jetzt(), dokument_id))
        dbm.protokollieren("email_" + status, "dokument" if dokument_id else "einstellungen", dokument_id,
                           {"an": an, "betreff": betreff, "fehler": fehler, "ablage": ablage}, con=con)
        if hinweis:
            dbm.protokollieren("email_ablage_fehler", "dokument" if dokument_id else "einstellungen", dokument_id,
                               hinweis, con=con)
    if status == "gesendet":
        try:
            from .email_historie import aus_versand
            aus_versand(con, msg, dokument_id)  # beim Kunden in der E-Mail-Historie
        except Exception as e:  # die Historie darf den Versand nie scheitern lassen
            print(f"E-Mail-Historie: {e}")
    if hinweis:
        print(hinweis)
    if fehler:
        raise MailFehler(fehler)
    return hinweis
