"""Anfragen aus dem Kontaktformular: E-Mails abholen, Felder auslesen, Spam erkennen, Kunden anlegen.

Ablauf:
  Website-Formular -> E-Mail an kontakt@... -> dieses Modul holt sie per IMAP ab
  -> liest die Felder (Name, Telefon, Email, Geraet, Nachricht) -> vergibt Spam-Punkte
  -> echt: Kunde als Interessent anlegen / unsicher: zur Prüfung / spam: nur ablegen.
Alles läuft lokal; es werden keine Daten an Dritte geschickt.
"""
import email
import email.policy
import imaplib
import json
import re
import unicodedata
from datetime import datetime, timedelta
from email.header import decode_header, make_header
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser

from . import db as dbm
from .hilfen import kunde_name
from .namen import VORNAMEN
from .sicherheit import entschluesseln

# Feldnamen im Formular -> interne Namen (Kleinschreibung, ohne Doppelpunkt)
FELDER = {
    "name": "name", "vollständiger name": "name", "ihr name": "name",
    "vorname": "vorname", "nachname": "nachname",
    "telefon": "telefon", "telefonnummer": "telefon", "tel": "telefon", "handy": "telefon", "mobil": "telefon",
    "email": "email", "e-mail": "email", "e-mail-adresse": "email", "mail": "email",
    "geraet": "geraet", "gerät": "geraet", "geräteart": "geraet", "geraeteart": "geraet",
    "nachricht": "nachricht", "ihre nachricht": "nachricht", "anliegen": "nachricht", "beschreibung": "nachricht",
    "firma": "firma", "unternehmen": "firma",
    "straße": "strasse", "strasse": "strasse", "adresse": "strasse", "anschrift": "strasse",
    "plz": "plz", "postleitzahl": "plz", "ort": "ort", "wohnort": "ort", "stadt": "ort",
}

# Formular-Auswahl "Gerät" -> Leistungsart im Tool
GERAET_ZU_LEISTUNGSART = [
    (("smartphone", "handy", "tablet", "iphone", "ipad", "telefon"), "Smartphone"),
    (("kaffee", "espresso", "vollautomat", "siebträger"), "Kaffeemaschine"),
    (("pc", "laptop", "notebook", "computer", "rechner", "macbook"), "PC/Laptop"),
]

# ------------------------------------------------------------------ Spam-Regeln

THEMENWOERTER = [
    "display", "akku", "batterie", "handy", "smartphone", "iphone", "ipad", "tablet", "samsung", "galaxy", "xiaomi",
    "huawei", "pixel", "oppo", "oneplus", "motorola", "nokia", "redmi", "honor", "realme",
    "kaffee", "maschine", "vollautomat", "jura", "delonghi", "de'longhi", "siemens", "philips", "saeco", "melitta",
    "krups", "nivona", "bosch", "brühgruppe", "bruehgruppe", "entkalk", "mahlwerk", "pumpe", "dichtung", "milchschaum",
    "pc", "laptop", "notebook", "computer", "rechner", "macbook", "windows", "festplatte", "ssd", "lüfter", "luefter",
    "tastatur", "bildschirm", "grafikkarte", "mainboard", "netzteil",
    "reparatur", "reparieren", "defekt", "kaputt", "gesprungen", "gebrochen", "riss", "lädt", "laedt", "ladebuchse",
    "geht nicht", "funktioniert", "startet", "wasserschaden", "tausch", "wechsel", "kostenvoranschlag", "preis",
    "kosten", "termin", "abholung", "garantie", "kamera", "lautsprecher", "mikrofon", "glas", "rückseite",
]

SPAMWOERTER = [
    "seo", "backlink", "ranking", "google ranking", "first page", "erste seite", "website design", "web design",
    "webdesign", "marketing", "lead generation", "leads", "traffic", "crypto", "krypto", "bitcoin", "btc", "forex",
    "investment", "invest", "casino", "lottery", "loan", "kredit", "darlehen", "viagra", "cialis", "porn", "sex",
    "dating", "guest post", "gastbeitrag", "sponsored", "outsourcing", "virtual assistant", "app development",
    "dear sir", "dear madam", "business proposal", "partnership", "kooperation anfrage", "unsubscribe",
    "click here", "hier klicken", "free trial", "telegram", "whatsapp me", "earn money", "geld verdienen",
    "social media", "instagram followers", "youtube views", "ai tool", "chatgpt", "rabattcode",
]

ENGLISCHE_WOERTER = {"the", "and", "you", "your", "our", "we", "for", "with", "this", "that", "website", "business",
                     "hello", "hi", "please", "would", "like", "offer", "services", "company", "best", "regards"}

WEGWERF_DOMAINS = {"mailinator.com", "guerrillamail.com", "10minutemail.com", "tempmail.com", "temp-mail.org",
                   "yopmail.com", "trashmail.com", "sharklasers.com", "getnada.com", "dispostable.com",
                   "maildrop.cc", "fakeinbox.com"}

TASTATUR_FOLGEN = ["asdf", "qwer", "wert", "sdfg", "dfgh", "fghj", "ghjk", "hjkl", "yxcv", "xcvb", "cvbn", "vbnm",
                   "qwertz", "1234", "jklö"]

EMAIL_RE = re.compile(r"^[^@\s<>]+@[^@\s<>]+\.[a-zA-Z]{2,}$")
URL_RE = re.compile(r"(https?://|www\.|\b[a-z0-9-]+\.(com|net|org|ru|cn|info|biz|xyz|top|io)\b)", re.I)


def _woerter(text):
    return re.findall(r"[a-zäöüß']+", (text or "").lower())


def _ist_kauderwelsch(wort):
    w = wort.lower()
    if len(w) < 4:
        return False
    if any(f in w for f in TASTATUR_FOLGEN):
        return True
    if re.search(r"(.)\1{3,}", w):           # aaaa
        return True
    if len(w) >= 5 and not re.search(r"[aeiouyäöü]", w):  # keine Vokale
        return True
    if re.search(r"[bcdfghjklmnpqrstvwxzß]{6,}", w):     # 6+ Konsonanten am Stück
        return True
    return False


def _anteil_fremdschrift(text):
    buchstaben = [c for c in text if c.isalpha()]
    if not buchstaben:
        return 0.0
    fremd = 0
    for c in buchstaben:
        try:
            if "LATIN" not in unicodedata.name(c):
                fremd += 1
        except ValueError:
            fremd += 1
    return fremd / len(buchstaben)


def telefon_normalisieren(tel):
    """'+49 171 9879253' / '0171-9879253' -> '491719879253' (zum Vergleichen)."""
    ziffern = re.sub(r"\D", "", tel or "")
    if (tel or "").strip().startswith("+"):
        return ziffern
    if ziffern.startswith("00"):
        return ziffern[2:]
    if ziffern.startswith("0"):
        return "49" + ziffern[1:]
    return ziffern


def bewerten(felder, schwelle_unsicher=2, schwelle_spam=5):
    """Vergibt Spam-Punkte. Gibt (punkte, gründe, einstufung) zurück.

    Positive Punkte sprechen für Spam/Unsinn, negative für eine echte Anfrage.
    """
    gruende = []
    punkte = 0

    def regel(p, text):
        nonlocal punkte
        punkte += p
        gruende.append(f"{'+' if p > 0 else ''}{p}: {text}")

    name = (felder.get("name") or " ".join(x for x in [felder.get("vorname"), felder.get("nachname")] if x)).strip()
    mail = (felder.get("email") or "").strip()
    tel = (felder.get("telefon") or "").strip()
    nachricht = (felder.get("nachricht") or "").strip()
    geraet = (felder.get("geraet") or "").strip()
    alles = " ".join([name, nachricht, geraet])
    kleintext = alles.lower()

    # --- Inhalt der Nachricht
    links = len(URL_RE.findall(nachricht))
    if links:
        regel(min(3 * links, 6), f"{links} Link(s) in der Nachricht")
    treffer = sorted({w for w in SPAMWOERTER if re.search(r"(?<![a-zäöü])" + re.escape(w) + r"(?![a-zäöü])", kleintext)})
    if treffer:
        regel(min(3 * len(treffer), 6), "typische Spam-Wörter: " + ", ".join(treffer[:5]))
    if _anteil_fremdschrift(alles) > 0.2:
        regel(4, "überwiegend fremde Schriftzeichen (z. B. Kyrillisch)")
    woerter = _woerter(nachricht)
    if woerter:
        englisch = sum(1 for w in woerter if w in ENGLISCHE_WOERTER)
        if len(woerter) >= 6 and englisch / len(woerter) > 0.2:
            regel(2, "Nachricht ist auf Englisch")
        kauder = [w for w in _woerter(alles) if _ist_kauderwelsch(w)]
        if kauder and len(kauder) / max(len(_woerter(alles)), 1) >= 0.3:
            regel(4, "Zeichensalat: " + ", ".join(kauder[:3]))
        elif kauder:
            regel(2, "teilweise Zeichensalat: " + ", ".join(kauder[:3]))
    if len(nachricht) < 4:
        regel(2, "keine oder fast keine Nachricht")
    if len(nachricht) > 2500:
        regel(2, "ungewöhnlich lange Nachricht")

    # --- Kontaktdaten
    if not mail and not tel:
        regel(3, "weder E-Mail noch Telefon angegeben")
    if mail:
        if not EMAIL_RE.match(mail):
            regel(2, "E-Mail-Adresse ungültig")
        elif mail.split("@")[-1].lower() in WEGWERF_DOMAINS:
            regel(2, "Wegwerf-E-Mail-Adresse")
    if tel:
        ziffern = re.sub(r"\D", "", tel)
        if not 6 <= len(ziffern) <= 15:
            regel(1, "Telefonnummer unplausibel")
        elif telefon_normalisieren(tel).startswith("49"):
            regel(-1, "deutsche Telefonnummer")
    if not name or len(name) < 2:
        regel(1, "kein Name")
    elif re.search(r"\d|https?://|www\.", name):
        regel(3, "Name enthält Ziffern oder Links")

    # --- Passt das Thema?
    # nur Name und Nachricht zählen – die Geräteauswahl im Formular kann auch ein Bot anklicken
    inhalt = (name + " " + nachricht).lower()
    themen = sorted({w for w in THEMENWOERTER if re.search(r"(?<![a-zäöü])" + re.escape(w), inhalt)})
    if themen:
        regel(-3, "passt zum Angebot: " + ", ".join(themen[:4]))
    elif len(nachricht) >= 4:
        regel(2 if len(nachricht) < 40 else 1, "kein erkennbarer Bezug zu Reparaturen")
    if geraet and geraet_zu_leistungsart(geraet):
        regel(-1, f"Gerät ausgewählt: {geraet}")

    if punkte >= schwelle_spam:
        stufe = "spam"
    elif punkte >= schwelle_unsicher:
        stufe = "unsicher"
    else:
        stufe = "echt"
    return punkte, gruende, stufe


# ------------------------------------------------------------------ Auslesen

class _TextAusHtml(HTMLParser):
    BLOCK = {"p", "div", "br", "tr", "td", "th", "li", "h1", "h2", "h3", "h4", "h5", "h6", "table", "section"}

    def __init__(self):
        super().__init__()
        self.teile = []
        self._ignorieren = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("style", "script", "head"):
            self._ignorieren += 1
        if tag in self.BLOCK:
            self.teile.append("\n")

    def handle_endtag(self, tag):
        if tag in ("style", "script", "head"):
            self._ignorieren = max(0, self._ignorieren - 1)
        if tag in self.BLOCK:
            self.teile.append("\n")

    def handle_data(self, data):
        if not self._ignorieren:
            self.teile.append(data)


def html_zu_text(html):
    p = _TextAusHtml()
    p.feed(html)
    text = "".join(p.teile).replace("\xa0", " ")
    zeilen = [re.sub(r"[ \t]+", " ", z).strip() for z in text.splitlines()]
    return "\n".join(z for z in zeilen if z)


def _kopf(wert):
    try:
        return str(make_header(decode_header(wert or "")))
    except Exception:
        return wert or ""


def mail_text(nachricht):
    """Liefert den lesbaren Text einer E-Mail (bevorzugt HTML-Teil, sonst Text-Teil)."""
    html = text = None
    for teil in nachricht.walk() if nachricht.is_multipart() else [nachricht]:
        if teil.get_content_maintype() == "multipart" or teil.get_filename():
            continue
        try:
            inhalt = teil.get_content()
        except (LookupError, KeyError):
            inhalt = teil.get_payload(decode=True).decode("utf-8", "replace")
        if teil.get_content_type() == "text/html" and html is None:
            html = inhalt
        elif teil.get_content_type() == "text/plain" and text is None:
            text = inhalt
    if html:
        return html_zu_text(html)
    return "\n".join(z.strip() for z in (text or "").splitlines() if z.strip())


def felder_auslesen(text):
    """Liest 'Feldname' / 'Wert'-Paare aus dem Text der Formular-E-Mail.

    Unterstützt beide Varianten:
      Name                    Name: Kai Muster
      Kai Muster
    """
    felder = {}
    aktuell = None
    for zeile in text.splitlines():
        z = zeile.strip()
        if not z:
            continue
        schluessel, _, rest = z.partition(":")
        label = z.rstrip(":").strip().lower()
        if label in FELDER:
            aktuell = FELDER[label]
            felder.setdefault(aktuell, [])
            continue
        if rest and schluessel.strip().lower() in FELDER and len(schluessel) < 30:
            aktuell = FELDER[schluessel.strip().lower()]
            felder.setdefault(aktuell, []).append(rest.strip())
            continue
        if aktuell:
            # Ende des Formulars erkennen (Fußzeilen von Website-Baukästen)
            if re.match(r"^(this (e-)?mail|diese e-mail|sent from|gesendet von|powered by|you received|"
                        r"unsubscribe|--\s*$)", z, re.I):
                aktuell = None
                continue
            felder[aktuell].append(z)
    return {k: "\n".join(v).strip() for k, v in felder.items() if "\n".join(v).strip()}


def name_aufteilen(name, reihenfolge="auto"):
    """'Kochendörfer Kai' -> ('Kai', 'Kochendörfer'). Erkennt Vornamen anhand einer Namensliste."""
    teile = (name or "").replace(",", " ").split()
    if not teile:
        return "", ""
    if len(teile) == 1:
        return "", teile[0]
    # "Nachname, Vorname" mit Komma
    if "," in (name or ""):
        nach, _, vor = name.partition(",")
        return vor.strip(), nach.strip()
    erster, letzter = teile[0], teile[-1]
    if reihenfolge == "nachname_vorname":
        return " ".join(teile[1:]), erster
    if reihenfolge == "vorname_nachname":
        return " ".join(teile[:-1]), letzter
    erster_ist_vorname = erster.lower() in VORNAMEN
    letzter_ist_vorname = letzter.lower() in VORNAMEN
    if letzter_ist_vorname and not erster_ist_vorname:
        return " ".join(teile[1:]), erster
    return " ".join(teile[:-1]), letzter


def geraet_zu_leistungsart(geraet):
    g = (geraet or "").lower()
    for woerter, art in GERAET_ZU_LEISTUNGSART:
        if any(w in g for w in woerter):
            return art
    return None


def schoen(text):
    """Großschreibung reparieren, wenn jemand alles klein oder alles groß schreibt."""
    if text and (text.islower() or text.isupper()):
        return " ".join(t[:1].upper() + t[1:].lower() for t in text.split())
    return text


# ------------------------------------------------------------------ Verarbeiten

def verarbeiten(con, text, einst, quelle="email", message_id=None, absender=None, betreff=None, eingang=None):
    """Legt eine Anfrage an, bewertet sie und legt bei echten Anfragen den Kunden an.

    Gibt die ID der Anfrage zurück, oder None, wenn sie schon vorhanden war.
    """
    if message_id and con.execute("SELECT 1 FROM anfragen WHERE message_id=?", (message_id,)).fetchone():
        return None
    felder = felder_auslesen(text)
    punkte, gruende, stufe = bewerten(felder, int(einst["anfrage_schwelle_unsicher"]),
                                      int(einst["anfrage_schwelle_spam"]))
    vorname, nachname = felder.get("vorname", ""), felder.get("nachname", "")
    if felder.get("name") and not (vorname or nachname):
        vorname, nachname = name_aufteilen(felder["name"], einst.get("anfrage_namensreihenfolge", "auto"))
    vorname, nachname = schoen(vorname), schoen(nachname)
    with dbm.Transaktion(con):
        cur = con.execute(
            "INSERT INTO anfragen (eingang_am, quelle, message_id, absender, betreff, name, vorname, nachname, telefon, "
            "email, geraet, nachricht, felder_json, rohtext, spam_punkte, gruende_json, einstufung) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (eingang or dbm.jetzt(), quelle, message_id, absender, betreff, felder.get("name", ""), vorname, nachname,
             felder.get("telefon", ""), (felder.get("email") or "").strip().lower(), felder.get("geraet", ""),
             felder.get("nachricht", ""), json.dumps(felder, ensure_ascii=False), text[:20000], punkte,
             json.dumps(gruende, ensure_ascii=False), stufe))
        aid = cur.lastrowid
        dbm.protokollieren("anfrage_eingegangen", "anfrage", aid, {"einstufung": stufe, "punkte": punkte}, con=con)
        if stufe == "echt" and einst.get("anfrage_auto_kunde"):
            kunde_aus_anfrage(con, aid, einst)
    return aid


def passender_kunde(con, email_adresse, telefon):
    if email_adresse:
        k = con.execute("SELECT * FROM kunden WHERE lower(email)=? ORDER BY id LIMIT 1",
                        (email_adresse.strip().lower(),)).fetchone()
        if k:
            return k
    norm = telefon_normalisieren(telefon)
    if len(norm) >= 8:
        for k in con.execute("SELECT * FROM kunden WHERE telefon IS NOT NULL AND telefon<>''"):
            if telefon_normalisieren(k["telefon"]) == norm:
                return k
    return None


def kunde_aus_anfrage(con, anfrage_id, einst, vorname=None, nachname=None):
    """Legt aus der Anfrage einen Interessenten an oder ordnet sie einem vorhandenen Kunden zu.

    Muss innerhalb einer Transaktion aufgerufen werden. Gibt (kunde_id, neu_angelegt) zurück.
    """
    from .logik import naechste_kundennr

    a = con.execute("SELECT * FROM anfragen WHERE id=?", (anfrage_id,)).fetchone()
    felder = json.loads(a["felder_json"] or "{}")
    notiz = (f"Anfrage vom {datetime.fromisoformat(a['eingang_am']).strftime('%d.%m.%Y')}"
             + (f" – Gerät: {a['geraet']}" if a["geraet"] else "") + f"\n{a['nachricht'] or ''}").strip()
    vorhanden = passender_kunde(con, a["email"], a["telefon"])
    if vorhanden:
        alte = vorhanden["notizen"] or ""
        con.execute("UPDATE kunden SET notizen=?, geaendert_am=? WHERE id=?",
                    ((alte + "\n\n" + notiz).strip(), dbm.jetzt(), vorhanden["id"]))
        con.execute("UPDATE anfragen SET status='zugeordnet', kunde_id=?, bearbeitet_am=? WHERE id=?",
                    (vorhanden["id"], dbm.jetzt(), anfrage_id))
        dbm.protokollieren("anfrage_zugeordnet", "anfrage", anfrage_id, {"kunde": vorhanden["kundennr"]}, con=con)
        return vorhanden["id"], False
    nr = naechste_kundennr(con, einst)
    firma = schoen(felder.get("firma", ""))
    cur = con.execute(
        "INSERT INTO kunden (kundennr, typ, firma, vorname, nachname, strasse, plz, ort, land, email, telefon, notizen, "
        "interessent, quelle, erstellt_am, geaendert_am) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,1,'Kontaktformular',?,?)",
        (nr, "firma" if firma else "privat", firma, vorname if vorname is not None else a["vorname"],
         nachname if nachname is not None else a["nachname"], felder.get("strasse", ""), felder.get("plz", ""),
         schoen(felder.get("ort", "")), "Deutschland", a["email"], a["telefon"], notiz, dbm.jetzt(), dbm.jetzt()))
    kid = cur.lastrowid
    con.execute("UPDATE anfragen SET status='kunde_angelegt', kunde_id=?, bearbeitet_am=? WHERE id=?",
                (kid, dbm.jetzt(), anfrage_id))
    dbm.protokollieren("kunde_aus_anfrage", "kunde", kid, {"kundennr": nr, "anfrage": anfrage_id}, con=con)
    return kid, True


def aufraeumen(con, einst):
    """Löscht Spam und verworfene Anfragen nach 30 Tagen (Datensparsamkeit)."""
    grenze = (datetime.now() - timedelta(days=30)).isoformat(timespec="seconds")
    with dbm.Transaktion(con):
        n = con.execute("DELETE FROM anfragen WHERE (status='verworfen' OR (einstufung='spam' AND status='neu')) "
                        "AND eingang_am < ?", (grenze,)).rowcount
        if n:
            dbm.protokollieren("anfragen_bereinigt", "anfrage", None, {"geloescht": n}, con=con)
    return n


def interessenten_zum_loeschen(con, einst):
    """Interessenten ohne Dokumente, die älter als die eingestellte Frist sind."""
    monate = int(einst.get("interessent_loeschen_monate") or 6)
    grenze = (datetime.now() - timedelta(days=30 * monate)).isoformat(timespec="seconds")
    return con.execute(
        "SELECT * FROM kunden k WHERE interessent=1 AND geaendert_am < ? "
        "AND NOT EXISTS (SELECT 1 FROM dokumente d WHERE d.kunde_id=k.id) "
        "AND NOT EXISTS (SELECT 1 FROM auftraege a WHERE a.kunde_id=k.id) "
        "AND NOT EXISTS (SELECT 1 FROM vertraege v WHERE v.kunde_id=k.id) ORDER BY geaendert_am", (grenze,)).fetchall()


# ------------------------------------------------------------------ IMAP

class AbrufFehler(Exception):
    pass


def _imap_ordnername(name):
    from .imap_ablage import _quote, utf7_kodieren
    return _quote(utf7_kodieren(name))


def imap_zugang(einst, ueberschreiben=None):
    """IMAP-Zugang für den Abruf (Formularwerte dürfen gespeicherte Werte überschreiben, z. B. beim Test)."""
    w = {**einst, **{k: v for k, v in (ueberschreiben or {}).items() if v not in (None, "")}}
    passwort = w.get("imap_passwort_klartext") or entschluesseln(w.get("imap_passwort_enc")) \
        or entschluesseln(w.get("smtp_passwort_enc"))
    sicherheit = w.get("imap_sicherheit")
    if sicherheit not in ("ssl", "starttls"):
        from .imap_verbindung import sicherheit_aus_port
        sicherheit = sicherheit_aus_port(w.get("imap_port"))
    return {"host": (w.get("imap_host") or "").strip(), "port": w.get("imap_port") or 993, "sicherheit": sicherheit,
            "benutzer": (w.get("imap_benutzer") or w.get("smtp_benutzer") or "").strip(), "passwort": passwort or ""}


def imap_anmelden(zugang, imap_klasse=None, imap_plain=None):
    from .imap_verbindung import ImapFehler, verbinden
    if not zugang["host"] or not zugang["benutzer"] or not zugang["passwort"]:
        raise AbrufFehler("Bitte unter Einstellungen → Anfragen den Posteingang (IMAP) einrichten.")
    try:
        return verbinden(zugang["host"], zugang["port"], zugang["sicherheit"], zugang["benutzer"], zugang["passwort"],
                         imap_ssl=imap_klasse, imap_plain=imap_plain)
    except ImapFehler as e:
        raise AbrufFehler(str(e))


def verbindung_testen(einst, ueberschreiben=None, imap_klasse=None, imap_plain=None):
    """Prüft Verbindung, Anmeldung und die Ordner. Gibt (ok, [Zeilen]) zurück."""
    zugang = imap_zugang(einst, ueberschreiben)
    w = {**einst, **(ueberschreiben or {})}
    from .imap_verbindung import IMAP_FEHLER, SICHERHEIT
    imap = imap_anmelden(zugang, imap_klasse, imap_plain)
    zeilen = [f"✓ Verbindung zu {zugang['host']}:{zugang['port']} mit {SICHERHEIT[zugang['sicherheit']]} "
              f"und Anmeldung als {zugang['benutzer']} erfolgreich."]
    ok = True
    try:
        for name, zweck in [((w.get("imap_ordner") or "INBOX").strip(), "Anfragen-Ordner"),
                            ((w.get("imap_zielordner") or "Anfragen erledigt").strip(), "Ordner für erledigte")]:
            try:
                typ, _ = imap.select(_imap_ordnername(name), readonly=True)
            except IMAP_FEHLER:
                typ = "NO"
            if typ == "OK":
                zeilen.append(f"✓ {zweck} „{name}“ ist vorhanden.")
            elif zweck == "Ordner für erledigte" and w.get("imap_verschieben"):
                zeilen.append(f"• {zweck} „{name}“ gibt es noch nicht – er wird beim ersten Verschieben "
                              "automatisch angelegt.")
            else:
                ok = False
                zeilen.append(f"✗ {zweck} „{name}“ wurde nicht gefunden. Bitte den Namen prüfen.")
    finally:
        try:
            imap.logout()
        except Exception:
            pass
    return ok, zeilen


def abrufen(con, einst, imap_klasse=None, imap_plain=None):
    """Holt Formular-E-Mails aus dem Postfach. Gibt eine Zusammenfassung zurück."""
    zugang = imap_zugang(einst)
    host = zugang["host"]
    erkennung = (einst.get("anfrage_erkennung") or "").strip().lower()
    ergebnis = {"gelesen": 0, "neu": 0, "echt": 0, "unsicher": 0, "spam": 0, "verschoben": 0}
    imap = imap_anmelden(zugang, imap_klasse, imap_plain)
    try:
        typ, _ = imap.select(_imap_ordnername(einst.get("imap_ordner") or "INBOX"))
        if typ != "OK":
            raise AbrufFehler(f"Ordner „{einst.get('imap_ordner')}“ nicht gefunden.")
        seit = (datetime.now() - timedelta(days=60)).strftime("%d-%b-%Y")
        typ, daten = imap.uid("SEARCH", None, f"SINCE {seit}")
        uids = daten[0].split() if typ == "OK" and daten and daten[0] else []
        zum_verschieben = []
        for uid in uids:
            typ, teile = imap.uid("FETCH", uid, "(BODY.PEEK[])")
            if typ != "OK" or not teile or not isinstance(teile[0], tuple):
                continue
            ergebnis["gelesen"] += 1
            nachricht = email.message_from_bytes(teile[0][1], policy=email.policy.default)
            text = mail_text(nachricht)
            if erkennung and erkennung not in text.lower():
                continue  # keine Formular-E-Mail -> nicht anfassen
            message_id = (nachricht.get("Message-ID") or "").strip() or f"uid-{uid.decode()}-{host}"
            try:
                eingang = parsedate_to_datetime(nachricht.get("Date")).astimezone().replace(tzinfo=None)
                eingang = eingang.isoformat(timespec="seconds")
            except (TypeError, ValueError):
                eingang = None
            aid = verarbeiten(con, text, einst, "email", message_id, _kopf(nachricht.get("From")),
                              _kopf(nachricht.get("Subject")), eingang)
            if aid:
                ergebnis["neu"] += 1
                stufe = con.execute("SELECT einstufung FROM anfragen WHERE id=?", (aid,)).fetchone()[0]
                ergebnis[stufe] += 1
            zum_verschieben.append(uid)
        if einst.get("imap_verschieben") and zum_verschieben:
            ziel = _imap_ordnername(einst.get("imap_zielordner") or "Anfragen erledigt")
            imap.create(ziel)  # Fehler, falls vorhanden, ist egal
            for uid in zum_verschieben:
                typ, _ = imap.uid("COPY", uid, ziel)
                if typ == "OK":
                    imap.uid("STORE", uid, "+FLAGS", r"(\Deleted)")
                    ergebnis["verschoben"] += 1
            imap.expunge()
    finally:
        try:
            imap.logout()
        except Exception:
            pass
    return ergebnis


def abruf_mit_protokoll(con):
    """Abruf inkl. Speichern von Zeitpunkt/Fehler in den Einstellungen (für Hintergrund und Knopf)."""
    einst = dbm.einstellungen(con)
    try:
        ergebnis = abrufen(con, einst)
        fehler = ""
    except AbrufFehler as e:
        ergebnis, fehler = None, str(e)
    except (OSError, imaplib.IMAP4.error) as e:
        ergebnis, fehler = None, f"Abruf fehlgeschlagen: {e}"
    with dbm.Transaktion(con):
        dbm.einstellungen_speichern({"anfragen_letzter_abruf": dbm.jetzt(), "anfragen_letzter_fehler": fehler}, con)
        if fehler:
            dbm.protokollieren("anfragen_abruf_fehler", "anfrage", None, fehler, con=con)
    aufraeumen(con, einst)
    if fehler:
        raise AbrufFehler(fehler)
    return ergebnis


def anfrage_anzeigename(a):
    return kunde_name({"vorname": a["vorname"], "nachname": a["nachname"]}) or a["name"] or a["email"] or "–"
