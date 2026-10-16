"""E-Mail-Historie je Kunde.

Alle Mails, die mit einem Kunden ausgetauscht werden (aus dem Programm, aus Outlook oder vom Handy), erscheinen
beim Kunden. Grundsätze:
- Das Postfach wird nur gelesen: Ordner mit EXAMINE (read-only), Inhalte mit BODY.PEEK[] – nichts wird als
  gelesen markiert, verschoben oder gelöscht.
- Zuerst nur die Kopfzeilen laden und mit den Kunden-Adressen abgleichen. Ohne Treffer wird die Mail komplett
  übersprungen: nichts gespeichert, auch nicht im Protokoll.
- Inkrementell je Ordner (UIDVALIDITY + letzte UID). Duplikate verhindert die Message-ID.
- Mails, die das Programm selbst verschickt, werden beim Versand gespeichert und später über die Message-ID mit
  dem Fund im Postfach zusammengeführt.
"""
import email
import email.policy
import hashlib
import json
import re
import threading
from datetime import datetime, timedelta
from email.utils import getaddresses, parsedate_to_datetime

from . import db as dbm

KOPF_FELDER = "FROM TO CC REPLY-TO DATE MESSAGE-ID SUBJECT"
STAPEL = 200            # UIDs je FETCH der Kopfzeilen
MAX_TEXT = 200_000      # Zeichen Mailtext je Nachricht
ZEITRAUM = {30: "letzte 30 Tage", 182: "letzte 6 Monate", 365: "letztes Jahr", 0: "alles"}
_SPERRE = threading.Lock()  # nie zwei Abgleiche gleichzeitig (Hintergrund, Knopf, nachträglicher Abgleich)


class HistorieFehler(Exception):
    pass


# ---------------------------------------------------------------- Adressen

def adresse_normal(text):
    """'  Anna Müller <Anna@Web.DE> ' → 'anna@web.de' (Anzeigename entfernt, klein, ohne Leerzeichen)."""
    _, adr = email.utils.parseaddr(text or "")
    adr = re.sub(r"\s+", "", adr or "").lower().strip("<>")
    return adr if "@" in adr else ""


def adressen_aus_text(text):
    """Mehrere Adressen aus Freitext (Komma, Semikolon, Zeilen) – Anzeigenamen sind erlaubt."""
    ergebnis = []
    for teil in re.split(r"[,;\n]+", text or ""):
        adr = adresse_normal(teil)
        if adr and adr not in ergebnis:
            ergebnis.append(adr)
    return ergebnis


def adressen_aus_kopf(*werte):
    return [a for a in (adresse_normal(f"{n} <{adr}>" if n else adr)
                        for n, adr in getaddresses([str(w) for w in werte if w])) if a]


def kunden_adressen(con):
    """{adresse: {kunde_id, …}} über E-Mail und weitere Adressen/Ansprechpartner aller Kunden."""
    zuordnung = {}
    for k in con.execute("SELECT id, email, email_weitere FROM kunden"):
        for adr in adressen_aus_text(k["email"]) + adressen_aus_text(k["email_weitere"]):
            zuordnung.setdefault(adr, set()).add(k["id"])
    return zuordnung


def eigene_adressen(einst):
    eigen = set(adressen_aus_text(einst.get("historie_eigene_adressen")))
    for k in ("absender_email", "smtp_benutzer", "imap_benutzer", "gesendet_imap_benutzer"):
        adr = adresse_normal(einst.get(k))
        if adr:
            eigen.add(adr)
    return eigen


def ordner_liste(text):
    return [z.strip() for z in (text or "").splitlines() if z.strip()]


# ---------------------------------------------------------------- Abgleich einer Nachricht

def _kopf(wert):
    from .anfragen import _kopf as dekodieren
    return dekodieren(wert)


def treffer(nachricht, adressbuch, eigen):
    """Welche Kunden betrifft die Mail? {kunde_id: adresse}. Eigene Adressen zählen nie."""
    beteiligte = adressen_aus_kopf(nachricht.get("From"), nachricht.get("To"), nachricht.get("Cc"),
                                   nachricht.get("Reply-To"))
    gefunden = {}
    for adr in beteiligte:
        if adr in eigen:
            continue
        for kid in adressbuch.get(adr, ()):
            gefunden.setdefault(kid, adr)
    return gefunden


def message_id(nachricht):
    mid = (nachricht.get("Message-ID") or "").strip()
    if mid:
        return mid
    # ohne Message-ID: stabile Ersatz-ID aus Absender, Datum und Betreff (gleiche Mail in mehreren Ordnern)
    roh = "|".join(str(nachricht.get(k) or "") for k in ("From", "Date", "Subject", "To"))
    return f"<ohne-id-{hashlib.sha256(roh.encode('utf-8', 'replace')).hexdigest()[:32]}@historie>"


def _datum(nachricht):
    try:
        return parsedate_to_datetime(nachricht.get("Date")).astimezone().replace(tzinfo=None).isoformat(
            timespec="seconds")
    except (TypeError, ValueError, IndexError):
        return None


def _anhaenge(nachricht):
    liste = []
    for teil in nachricht.walk() if nachricht.is_multipart() else []:
        name = teil.get_filename()
        if name:
            try:
                groesse = len(teil.get_payload(decode=True) or b"")
            except Exception:
                groesse = 0
            liste.append({"name": _kopf(name), "groesse": groesse})
    return liste


def speichern(con, nachricht, kunden, richtung, quelle="imap", ordner=None, uid=None, dokument_id=None):
    """Legt die Nachricht an (oder ergänzt eine vorhandene) und verknüpft sie mit allen getroffenen Kunden.

    Gibt (nachricht_id, neu) zurück. Muss in einer Transaktion laufen.
    """
    mid = message_id(nachricht)
    vorhanden = con.execute("SELECT * FROM email_nachrichten WHERE message_id=?", (mid,)).fetchone()
    if vorhanden:
        nid, neu = vorhanden["id"], False
        if ordner and not vorhanden["ordner"]:  # vom Programm gesendet, jetzt auch im Postfach gefunden
            con.execute("UPDATE email_nachrichten SET ordner=?, imap_uid=? WHERE id=?", (ordner, uid, nid))
    else:
        from .anfragen import mail_text
        try:
            text = mail_text(nachricht)
        except Exception:
            text = ""
        anfrage = con.execute("SELECT id FROM anfragen WHERE message_id=?", (mid,)).fetchone()
        cur = con.execute(
            "INSERT INTO email_nachrichten (message_id, richtung, datum, von, an, cc, betreff, text, anhaenge, quelle, "
            "ordner, imap_uid, dokument_id, anfrage_id, erfasst_am) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (mid, richtung, _datum(nachricht) or dbm.jetzt(), _kopf(nachricht.get("From")), _kopf(nachricht.get("To")),
             _kopf(nachricht.get("Cc")), _kopf(nachricht.get("Subject")), (text or "")[:MAX_TEXT],
             json.dumps(_anhaenge(nachricht), ensure_ascii=False), quelle, ordner, uid, dokument_id,
             anfrage["id"] if anfrage else None, dbm.jetzt()))
        nid, neu = cur.lastrowid, True
    for kid, adr in kunden.items():
        con.execute("INSERT OR IGNORE INTO email_kunden (nachricht_id, kunde_id, adresse) VALUES (?,?,?)",
                    (nid, kid, adr))
    return nid, neu


def aus_versand(con, nachricht, dokument_id=None):
    """Beim Versand aus dem Programm (KVA, Rechnung, Leihvertrag …) direkt in der Historie speichern."""
    einst = dbm.einstellungen(con)
    if not einst.get("historie_aktiv"):
        return None
    kunden = treffer(nachricht, kunden_adressen(con), eigene_adressen(einst))
    if not kunden:
        return None
    with dbm.Transaktion(con):
        nid, _ = speichern(con, nachricht, kunden, "gesendet", quelle="programm", dokument_id=dokument_id)
    return nid


# ---------------------------------------------------------------- IMAP

def _ordnername(name):
    from .imap_ablage import _quote, utf7_kodieren
    return _quote(utf7_kodieren(name))


def _uid_aus(antwortkopf):
    m = re.search(rb"UID (\d+)", antwortkopf or b"")
    return int(m.group(1)) if m else None


def _kopfzeilen_laden(imap, uids):
    """{uid: Message (nur Kopfzeilen)} – lädt nur die benötigten Kopfzeilen, nie den Inhalt."""
    ergebnis = {}
    for i in range(0, len(uids), STAPEL):
        satz = b",".join(str(u).encode() for u in uids[i:i + STAPEL])
        typ, daten = imap.uid("FETCH", satz, f"(UID BODY.PEEK[HEADER.FIELDS ({KOPF_FELDER})])")
        if typ != "OK":
            continue
        daten = list(daten or [])
        for i, teil in enumerate(daten):
            if isinstance(teil, tuple) and len(teil) >= 2:
                uid = _uid_aus(teil[0])
                if uid is None and i + 1 < len(daten) and isinstance(daten[i + 1], bytes):
                    uid = _uid_aus(daten[i + 1])  # manche Server senden „UID n“ erst nach dem Inhalt
                if uid is not None:
                    ergebnis[uid] = email.message_from_bytes(teil[1], policy=email.policy.default)
    return ergebnis


def _voll_laden(imap, uid):
    typ, daten = imap.uid("FETCH", str(uid).encode(), "(BODY.PEEK[])")
    if typ != "OK":
        return None
    for teil in daten or []:
        if isinstance(teil, tuple) and len(teil) >= 2:
            return email.message_from_bytes(teil[1], policy=email.policy.default)
    return None


MONATE = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def imap_datum(d):
    """IMAP-Datum unabhängig vom Gebietsschema (unter deutschem Windows liefert %b sonst „Okt“)."""
    return f"{d.day:02d}-{MONATE[d.month - 1]}-{d.year}"


def _seit(einst):
    tage = int(einst.get("historie_zeitraum_tage") or 0)
    return imap_datum(datetime.now() - timedelta(days=tage)) if tage > 0 else None


def _verarbeiten(con, imap, ordner, uids, gesendet_ordner, adressbuch, eigen, ergebnis):
    """Kopfzeilen prüfen, nur bei Kundentreffer vollständig laden und speichern."""
    kopf = _kopfzeilen_laden(imap, uids)
    for uid in sorted(kopf):
        k = kopf[uid]
        ergebnis["geprueft"] += 1
        kunden = treffer(k, adressbuch, eigen)
        if not kunden:
            continue  # kein Kunde beteiligt → nichts speichern
        mid = message_id(k)
        vorhanden = con.execute("SELECT id, ordner FROM email_nachrichten WHERE message_id=?", (mid,)).fetchone()
        if vorhanden:  # schon bekannt (anderer Ordner / selbst versendet): nur Zuordnungen ergänzen
            with dbm.Transaktion(con):
                speichern(con, k, kunden, "gesendet", ordner=ordner, uid=uid)
            continue
        try:
            voll = _voll_laden(imap, uid)
        except Exception:
            voll = None
        if voll is None:
            ergebnis["fehler"] += 1
            continue
        absender = adressen_aus_kopf(voll.get("From"))
        richtung = "gesendet" if gesendet_ordner or (absender and absender[0] in eigen) else "empfangen"
        with dbm.Transaktion(con):
            _, neu = speichern(con, voll, kunden, richtung, ordner=ordner, uid=uid)
        ergebnis["neu"] += 1 if neu else 0


def _ordner_oeffnen(imap, ordner):
    """EXAMINE (nur lesen). Gibt UIDVALIDITY zurück oder None, wenn es den Ordner nicht gibt."""
    from .imap_verbindung import IMAP_FEHLER
    try:
        typ, _ = imap.select(_ordnername(ordner), readonly=True)
    except IMAP_FEHLER:
        return None
    if typ != "OK":
        return None
    try:
        _, werte = imap.response("UIDVALIDITY")
        return int(werte[0]) if werte and werte[0] else 0
    except (TypeError, ValueError, IndexError):
        return 0


def _suchen(imap, *kriterien):
    typ, daten = imap.uid("SEARCH", None, *kriterien)
    if typ != "OK" or not daten or not daten[0]:
        return []
    return [int(x) for x in daten[0].split() if x.isdigit()]


def _ordner_abgleichen(con, imap, ordner, gesendet_ordner, einst, adressbuch, eigen, ergebnis):
    uidvalidity = _ordner_oeffnen(imap, ordner)
    if uidvalidity is None:
        ergebnis["hinweise"].append(f"Ordner „{ordner}“ wurde nicht gefunden.")
        return
    stand = con.execute("SELECT * FROM imap_ordner_status WHERE ordner=?", (ordner,)).fetchone()
    if stand and stand["uidvalidity"] == uidvalidity:
        letzte = stand["letzte_uid"]
        uids = [u for u in _suchen(imap, "UID", f"{letzte + 1}:*") if u > letzte]
    else:  # erster Abgleich oder UIDVALIDITY geändert → Ordner im Importzeitraum neu abgleichen
        seit = _seit(einst)
        alle = _suchen(imap, "ALL")
        uids = _suchen(imap, "SINCE", seit) if seit else alle
        # Stand = höchste UID des ganzen Ordners, damit ältere Mails außerhalb des Zeitraums später nicht nachrutschen
        letzte = max(alle, default=0)
        uids = [u for u in uids if u <= letzte] if alle else uids
    if uids:
        _verarbeiten(con, imap, ordner, uids, gesendet_ordner, adressbuch, eigen, ergebnis)
    with dbm.Transaktion(con):
        con.execute("INSERT INTO imap_ordner_status (ordner, uidvalidity, letzte_uid, aktualisiert_am) VALUES (?,?,?,?) "
                    "ON CONFLICT(ordner) DO UPDATE SET uidvalidity=excluded.uidvalidity, letzte_uid=excluded.letzte_uid, "
                    "aktualisiert_am=excluded.aktualisiert_am",
                    (ordner, uidvalidity, max([letzte, *uids]), dbm.jetzt()))


def _ordner_aus_einst(einst):
    eingang = ordner_liste(einst.get("historie_ordner_eingang")) or ["INBOX"]
    gesendet = ordner_liste(einst.get("historie_ordner_gesendet"))
    return [(o, False) for o in eingang] + [(o, True) for o in gesendet if o not in eingang]


def _anmelden(einst, imap_klasse=None, imap_plain=None):
    from .anfragen import AbrufFehler, imap_anmelden, imap_zugang
    try:
        return imap_anmelden(imap_zugang(einst), imap_klasse, imap_plain)
    except AbrufFehler as e:
        raise HistorieFehler(str(e))


def abgleichen(con, einst=None, imap_klasse=None, imap_plain=None):
    """Regelmäßiger, inkrementeller Abgleich aller eingestellten Ordner. Gibt eine Zusammenfassung zurück."""
    einst = einst or dbm.einstellungen(con)
    ergebnis = {"geprueft": 0, "neu": 0, "fehler": 0, "hinweise": []}
    adressbuch = kunden_adressen(con)
    if not adressbuch:
        return ergebnis
    with _SPERRE:
        imap = _anmelden(einst, imap_klasse, imap_plain)
        try:
            for ordner, gesendet in _ordner_aus_einst(einst):
                try:
                    _ordner_abgleichen(con, imap, ordner, gesendet, einst, adressbuch, eigene_adressen(einst),
                                       ergebnis)
                except Exception as e:  # ein Ordner darf den Rest nicht verhindern
                    ergebnis["hinweise"].append(f"Ordner „{ordner}“: {e}")
        finally:
            _abmelden(imap)
    return ergebnis


def adressen_nachholen(con, adressen, einst=None, imap_klasse=None, imap_plain=None):
    """Nach neuem Kunden / neuer Adresse: gezielt im Importzeitraum suchen (SEARCH FROM/TO/CC)."""
    einst = einst or dbm.einstellungen(con)
    eigen = eigene_adressen(einst)
    adressen = [a for a in (adresse_normal(x) for x in adressen) if a and a not in eigen]
    ergebnis = {"geprueft": 0, "neu": 0, "fehler": 0, "hinweise": []}
    if not adressen:
        return ergebnis
    adressbuch = kunden_adressen(con)
    seit = _seit(einst)
    with _SPERRE:
        imap = _anmelden(einst, imap_klasse, imap_plain)
        try:
            for ordner, gesendet in _ordner_aus_einst(einst):
                if _ordner_oeffnen(imap, ordner) is None:
                    continue
                uids = set()
                for adr in adressen:
                    kriterien = (["SINCE", seit] if seit else []) + ["OR", "OR", "FROM", adr, "TO", adr, "CC", adr]
                    uids.update(_suchen(imap, *kriterien))
                if uids:
                    _verarbeiten(con, imap, ordner, sorted(uids), gesendet, adressbuch, eigen, ergebnis)
        finally:
            _abmelden(imap)
    return ergebnis


def _abmelden(imap):
    from .imap_verbindung import abmelden
    abmelden(imap)


# ---------------------------------------------------------------- Ablauf mit Protokoll / Hintergrund

def abgleich_mit_protokoll(con, **imap_klassen):
    """Abgleich inkl. Zeitpunkt/Hinweis in den Einstellungen. Wirft keine Fehler – sie stehen als Hinweis da."""
    try:
        e = abgleichen(con, **imap_klassen)
        fehler = "; ".join(e["hinweise"])
    except HistorieFehler as ex:
        e, fehler = None, str(ex)
    except Exception as ex:
        e, fehler = None, f"E-Mail-Historie: {ex}"
    with dbm.Transaktion(con):
        dbm.einstellungen_speichern({"historie_letzter_abruf": dbm.jetzt(), "historie_letzter_fehler": fehler}, con)
        if e and e["neu"]:  # nur Anzahlen ins Protokoll, nie Inhalte oder Adressen
            dbm.protokollieren("email_historie_abruf", "einstellungen", None, {"neu": e["neu"],
                                                                               "geprueft": e["geprueft"]}, con=con)
    return e, fehler


def im_hintergrund(app, funktion, *args, synchron=False):
    """Führt einen Abgleich mit eigener Datenbankverbindung aus – im Hintergrund, damit die Oberfläche nicht wartet."""
    def los():
        with app.app_context():
            _ausfuehren(app.config["DB_PFAD"], funktion, *args)
    if synchron:
        los()
    else:
        threading.Thread(target=los, daemon=True).start()


def _ausfuehren(db_pfad, funktion, *args):
    con = dbm.verbinden(db_pfad)
    try:
        funktion(con, *args)
    except Exception as e:
        try:
            with dbm.Transaktion(con):
                dbm.einstellungen_speichern({"historie_letzter_fehler": str(e)}, con)
        except Exception:
            pass
    finally:
        con.close()


def faellig(einst):
    if not einst.get("historie_aktiv"):
        return False
    letzter = einst.get("historie_letzter_abruf")
    intervall = max(int(einst.get("anfragen_intervall_min") or 5), 1)
    return not letzter or datetime.fromisoformat(letzter) <= datetime.now() - timedelta(minutes=intervall)


def zuruecksetzen(con):
    """Alle Ordner beim nächsten Abgleich neu (im Importzeitraum) prüfen – vorhandene Mails bleiben, keine Duplikate."""
    with dbm.Transaktion(con):
        con.execute("DELETE FROM imap_ordner_status")


def fuer_kunde(con, kunde_id, grenze=None):
    sql = ("SELECT n.*, ek.adresse FROM email_nachrichten n JOIN email_kunden ek ON ek.nachricht_id=n.id "
           "WHERE ek.kunde_id=? ORDER BY n.datum DESC, n.id DESC")
    zeilen = con.execute(sql + (f" LIMIT {int(grenze)}" if grenze else ""), (kunde_id,)).fetchall()
    return [dict(z, anhaenge=json.loads(z["anhaenge"] or "[]")) for z in zeilen]


def kunde_entfernen(con, kunde_id):
    """Beim Löschen eines Kunden (Datenschutz): Zuordnungen und nur noch verwaiste Mails löschen."""
    con.execute("DELETE FROM email_kunden WHERE kunde_id=?", (kunde_id,))
    con.execute("DELETE FROM email_nachrichten WHERE id NOT IN (SELECT nachricht_id FROM email_kunden)")
