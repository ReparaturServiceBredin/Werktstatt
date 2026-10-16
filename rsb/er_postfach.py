"""Eingangsrechnungen aus dem Postfach übernehmen: Mails mit PDF-/XML-Anhang im eingestellten Ordner anzeigen.

Der Ordner wird nur gelesen (EXAMINE, BODY.PEEK) – es wird nichts verschoben, gelöscht oder als gelesen markiert.
"""
import email
import email.policy
from email.utils import parseaddr, parsedate_to_datetime

from .anfragen import AbrufFehler, imap_anmelden, imap_zugang

ENDUNGEN = (".pdf", ".xml")


def _ordner(einst):
    return (einst.get("er_imap_ordner") or "INBOX").strip() or "INBOX"


def _oeffnen(einst, imap_klasse=None, imap_plain=None):
    imap = imap_anmelden(imap_zugang(einst), imap_klasse, imap_plain)
    ordner = _ordner(einst)
    typ, _ = imap.select(f'"{ordner}"', readonly=True)
    if typ != "OK":
        try:
            imap.logout()
        except Exception:
            pass
        raise AbrufFehler(f"Der Ordner „{ordner}“ wurde im Postfach nicht gefunden.")
    return imap


def _anhaenge(msg):
    liste = []
    for i, teil in enumerate(msg.walk()):
        name = teil.get_filename()
        if not name or teil.is_multipart():
            continue
        if name.lower().endswith(ENDUNGEN) or teil.get_content_type() in ("application/pdf", "application/xml",
                                                                         "text/xml"):
            daten = teil.get_payload(decode=True) or b""
            liste.append({"index": i, "name": name, "groesse": len(daten), "daten": daten})
    return liste


def _kopf(msg):
    try:
        datum = parsedate_to_datetime(msg["Date"]).date().isoformat() if msg["Date"] else ""
    except (TypeError, ValueError):
        datum = ""
    name, adresse = parseaddr(str(msg["From"] or ""))
    return {"message_id": str(msg["Message-ID"] or "").strip(), "von": name or adresse, "von_adresse": adresse,
            "betreff": str(msg["Subject"] or ""), "datum": datum}


def mails(con, einst, anzahl=30, imap_klasse=None, imap_plain=None):
    """Die letzten Mails mit Rechnungsanhang (neueste zuerst)."""
    imap = _oeffnen(einst, imap_klasse, imap_plain)
    try:
        typ, daten = imap.uid("SEARCH", None, "ALL")
        uids = (daten[0] or b"").split()[-anzahl:] if typ == "OK" else []
        ergebnis = []
        for uid in reversed(uids):
            typ, teile = imap.uid("FETCH", uid, "(BODY.PEEK[])")
            roh = next((t[1] for t in teile or [] if isinstance(t, tuple)), None)
            if typ != "OK" or not roh:
                continue
            msg = email.message_from_bytes(roh, policy=email.policy.default)
            anhaenge = _anhaenge(msg)
            if not anhaenge:
                continue
            kopf = _kopf(msg)
            erfasst = {r["datei_name"] for r in con.execute(
                "SELECT datei_name FROM eingangsrechnungen WHERE message_id=? AND status<>'storniert'",
                (kopf["message_id"],))} if kopf["message_id"] else set()
            ergebnis.append({**kopf, "uid": uid.decode(), "anhaenge": [
                {k: v for k, v in a.items() if k != "daten"} | {"erfasst": a["name"] in erfasst} for a in anhaenge]})
        return ergebnis
    finally:
        try:
            imap.logout()
        except Exception:
            pass


def anhang_holen(einst, uid, index, imap_klasse=None, imap_plain=None):
    """Einen Anhang laden. Gibt (daten, dateiname, kopf) zurück."""
    imap = _oeffnen(einst, imap_klasse, imap_plain)
    try:
        typ, teile = imap.uid("FETCH", str(uid).encode(), "(BODY.PEEK[])")
        roh = next((t[1] for t in teile or [] if isinstance(t, tuple)), None)
        if typ != "OK" or not roh:
            raise AbrufFehler("Die E-Mail wurde im Postfach nicht mehr gefunden.")
        msg = email.message_from_bytes(roh, policy=email.policy.default)
        for a in _anhaenge(msg):
            if a["index"] == int(index):
                return a["daten"], a["name"], _kopf(msg)
        raise AbrufFehler("Der Anhang wurde nicht gefunden.")
    finally:
        try:
            imap.logout()
        except Exception:
            pass
