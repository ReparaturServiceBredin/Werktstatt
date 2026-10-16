"""Kundenbenachrichtigung bei Statuswechseln (E-Mail; SMS-Schnittstelle vorbereitet).

Ablauf: Ein Ereignis (Auftrag angenommen, KVA, Warten auf Teil, fertig, Abhol-Erinnerung) legt einen
Benachrichtigungs-Vorschlag an. Vor dem Versand wird er als Vorschau angezeigt; dort kann man Text ändern,
senden oder „diesmal nicht senden“. Ist die Vorschau in den Einstellungen ausgeschaltet, wird sofort gesendet.
Gesendete Mails landen über mail.senden automatisch in der E-Mail-Historie des Kunden.
"""
import re
from datetime import date, datetime

from . import db as dbm
from .hilfen import EingabeFehler, anrede_brief, euro, kunde_name

ANLAESSE = {
    "angenommen": "Auftrag angenommen",
    "kva": "Kostenvoranschlag versendet",
    "wartet_teil": "Warten auf Ersatzteil",
    "fertig": "Gerät fertig zur Abholung",
    "erinnerung": "Erinnerung: Gerät noch nicht abgeholt",
}
KANAELE = {"email": "E-Mail", "sms": "SMS"}
STATUS = {"offen": "wartet auf Freigabe", "gesendet": "gesendet", "verworfen": "nicht gesendet", "fehler": "Fehler"}
PLATZHALTER = ["{Anrede}", "{Kundenname}", "{Auftragsnummer}", "{Gerät}", "{Betrag}", "{Öffnungszeiten}",
               "{Fertig bis}", "{Firma}"]

_GRUSS = "\n\nMit freundlichen Grüßen\n{Firma}"
STANDARD = {
    "angenommen": ("Ihr Reparaturauftrag {Auftragsnummer}",
                   "{Anrede}\n\nvielen Dank für Ihren Auftrag. Wir haben Ihr Gerät ({Gerät}) unter der Auftragsnummer "
                   "{Auftragsnummer} angenommen und melden uns, sobald es Neuigkeiten gibt.{Fertig bis Satz}" + _GRUSS),
    "kva": ("Kostenvoranschlag zu Auftrag {Auftragsnummer}",
            "{Anrede}\n\nfür die Reparatur Ihres Geräts ({Gerät}) liegt Ihr Kostenvoranschlag über {Betrag} vor. "
            "Bitte teilen Sie uns kurz mit, ob wir die Reparatur durchführen sollen." + _GRUSS),
    "wartet_teil": ("Ihr Auftrag {Auftragsnummer}: Ersatzteil bestellt",
                    "{Anrede}\n\nfür die Reparatur Ihres Geräts ({Gerät}) haben wir das benötigte Ersatzteil bestellt. "
                    "Sobald es eingetroffen ist, setzen wir die Reparatur fort." + _GRUSS),
    "fertig": ("Ihr Gerät ist abholbereit (Auftrag {Auftragsnummer})",
               "{Anrede}\n\nIhr Gerät ({Gerät}) ist fertig und kann abgeholt werden. Betrag: {Betrag}.\n\n"
               "Unsere Öffnungszeiten:\n{Öffnungszeiten}\n\nBitte bringen Sie Ihren Annahmeschein oder einen Ausweis mit."
               + _GRUSS),
    "erinnerung": ("Erinnerung: Ihr Gerät wartet auf Sie (Auftrag {Auftragsnummer})",
                   "{Anrede}\n\nIhr Gerät ({Gerät}) liegt seit einigen Tagen abholbereit bei uns. Bitte holen Sie es "
                   "zu unseren Öffnungszeiten ab:\n{Öffnungszeiten}" + _GRUSS),
}


def einstellungs_standard():
    """Standardwerte für db.STANDARD_EINSTELLUNGEN."""
    werte = {"benachrichtigung_vorschau": True, "benachrichtigung_kanal": "email", "erinnerung_tage": "7, 14, 30",
             "oeffnungszeiten": "Mo–Fr 9:00–18:00 Uhr, Sa 10:00–14:00 Uhr", "sms_anbieter": ""}
    for anlass, (betreff, text) in STANDARD.items():
        werte[f"ben_{anlass}_aktiv"] = True
        werte[f"ben_{anlass}_betreff"] = betreff
        werte[f"ben_{anlass}_text"] = text
    return werte


def erinnerung_stufen(einst):
    stufen = sorted({int(x) for x in re.findall(r"\d+", str(einst.get("erinnerung_tage") or "")) if int(x) > 0})
    return stufen


# ---------------------------------------------------------------------- Texte

def _betrag(con, a, anlass):
    if anlass == "fertig" and a["rechnung_id"]:
        r = con.execute("SELECT summe_brutto, status FROM dokumente WHERE id=?", (a["rechnung_id"],)).fetchone()
        if r and r["status"] != "storniert":
            return euro(r["summe_brutto"])
    if a["kva_id"]:
        k = con.execute("SELECT summe_brutto FROM dokumente WHERE id=?", (a["kva_id"],)).fetchone()
        if k:
            return euro(k["summe_brutto"])
    return "laut Rechnung"


def werte(con, a, anlass, einst=None):
    einst = einst or dbm.einstellungen(con)
    k = con.execute("SELECT * FROM kunden WHERE id=?", (a["kunde_id"],)).fetchone()
    fertig = ""
    if a["fertig_bis"]:
        fertig = datetime.fromisoformat(a["fertig_bis"]).strftime("%d.%m.%Y")
    return {"{Anrede}": anrede_brief(k), "{Kundenname}": kunde_name(k), "{Auftragsnummer}": a["auftragsnr"],
            "{Gerät}": a["geraet"] or "Ihr Gerät", "{Betrag}": _betrag(con, a, anlass),
            "{Öffnungszeiten}": einst.get("oeffnungszeiten") or "", "{Fertig bis}": fertig,
            "{Fertig bis Satz}": f" Voraussichtlich ist es bis zum {fertig} fertig." if fertig else "",
            "{Firma}": "\n".join(x for x in [einst.get("inhaber"), einst.get("firma_name")] if x)}


def ersetzen(text, w):
    for k, v in sorted(w.items(), key=lambda kv: -len(kv[0])):
        text = text.replace(k, v)
    return text


def texte(con, a, anlass, einst=None):
    einst = einst or dbm.einstellungen(con)
    w = werte(con, a, anlass, einst)
    betreff = einst.get(f"ben_{anlass}_betreff") or STANDARD[anlass][0]
    text = einst.get(f"ben_{anlass}_text") or STANDARD[anlass][1]
    return ersetzen(betreff, w), ersetzen(text, w)


# ---------------------------------------------------------------------- Vorschläge

def vorschlagen(con, auftrag_id, anlass, stufe=None, manuell=False):
    """Legt einen Vorschlag an (falls der Anlass eingeschaltet ist und es keinen gleichen gibt). Gibt die ID oder None.

    Muss in einer Transaktion laufen. Versendet wird erst nach Freigabe (oder sofort, wenn die Vorschau aus ist –
    das erledigt offene_automatisch_senden() nach der Transaktion).
    """
    if anlass not in ANLAESSE:
        raise EingabeFehler("Unbekannter Anlass.")
    einst = dbm.einstellungen(con)
    if not manuell and not einst.get(f"ben_{anlass}_aktiv"):
        return None
    a = con.execute("SELECT * FROM auftraege WHERE id=?", (auftrag_id,)).fetchone()
    if not a:
        return None
    from .leihgeraete import ist_intern
    if ist_intern(con, a["kunde_id"]):
        return None
    if not manuell and con.execute(
            "SELECT 1 FROM benachrichtigungen WHERE auftrag_id=? AND anlass=? AND COALESCE(stufe, 0)=? "
            "AND status IN ('offen', 'gesendet')", (auftrag_id, anlass, stufe or 0)).fetchone():
        return None
    k = con.execute("SELECT * FROM kunden WHERE id=?", (a["kunde_id"],)).fetchone()
    kanal = einst.get("benachrichtigung_kanal") or "email"
    an = k["telefon"] if kanal == "sms" else k["email"]
    betreff, text = texte(con, a, anlass, einst)
    cur = con.execute(
        "INSERT INTO benachrichtigungen (auftrag_id, kunde_id, anlass, stufe, kanal, an, betreff, text, status, "
        "erstellt_am, benutzer) VALUES (?,?,?,?,?,?,?,?,'offen',?,?)",
        (auftrag_id, a["kunde_id"], anlass, stufe, kanal, an or "", betreff, text, dbm.jetzt_berlin(),
         dbm.aktueller_benutzer()))
    return cur.lastrowid


def offene(con, auftrag_id=None):
    """Offene Vorschläge; Texte werden mit den aktuellen Auftragsdaten neu erzeugt (z. B. Rechnungsbetrag)."""
    einst = dbm.einstellungen(con)
    for b in con.execute("SELECT b.id, b.anlass, b.auftrag_id FROM benachrichtigungen b WHERE b.status='offen'"
                         + (" AND b.auftrag_id=?" if auftrag_id else ""), (auftrag_id,) if auftrag_id else ()):
        a = con.execute("SELECT * FROM auftraege WHERE id=?", (b["auftrag_id"],)).fetchone()
        betreff, text = texte(con, a, b["anlass"], einst)
        con.execute("UPDATE benachrichtigungen SET betreff=?, text=? WHERE id=?", (betreff, text, b["id"]))
    sql = ("SELECT b.*, a.auftragsnr, a.geraet, k.kundennr, k.firma, k.vorname, k.nachname, k.typ AS ktyp "
           "FROM benachrichtigungen b JOIN auftraege a ON a.id=b.auftrag_id JOIN kunden k ON k.id=b.kunde_id "
           "WHERE b.status='offen' ")
    args = []
    if auftrag_id:
        sql += "AND b.auftrag_id=? "
        args.append(auftrag_id)
    return con.execute(sql + "ORDER BY b.id", args).fetchall()


def liste(con, auftrag_id=None, limit=200):
    sql = ("SELECT b.*, a.auftragsnr, a.geraet, k.kundennr, k.firma, k.vorname, k.nachname, k.typ AS ktyp "
           "FROM benachrichtigungen b JOIN auftraege a ON a.id=b.auftrag_id JOIN kunden k ON k.id=b.kunde_id ")
    args = []
    if auftrag_id:
        sql += "WHERE b.auftrag_id=? "
        args.append(auftrag_id)
    return con.execute(sql + "ORDER BY b.id DESC LIMIT ?", (*args, limit)).fetchall()


def verwerfen(con, bid, grund="diesmal nicht senden"):
    from .auftraege import verlauf
    b = con.execute("SELECT * FROM benachrichtigungen WHERE id=? AND status='offen'", (bid,)).fetchone()
    if not b:
        return False
    con.execute("UPDATE benachrichtigungen SET status='verworfen', erledigt_am=?, hinweis=?, benutzer=? WHERE id=?",
                (dbm.jetzt_berlin(), grund, dbm.aktueller_benutzer(), bid))
    verlauf(con, b["auftrag_id"], f"Benachrichtigung nicht gesendet: {ANLAESSE[b['anlass']]}", grund)
    return True


def senden(con, bid, an=None, betreff=None, text=None):
    """Versendet einen Vorschlag (optional mit geänderten Texten). Nicht in einer offenen Transaktion aufrufen.

    Gibt (ok, meldung) zurück.
    """
    from .auftraege import verlauf
    b = con.execute("SELECT * FROM benachrichtigungen WHERE id=? AND status IN ('offen', 'fehler')", (bid,)).fetchone()
    if not b:
        return False, "Die Benachrichtigung wurde bereits bearbeitet."
    an = (an if an is not None else b["an"]).strip()
    betreff = betreff if betreff is not None else b["betreff"]
    text = text if text is not None else b["text"]
    hinweis = None
    try:
        if b["kanal"] == "sms":
            from . import sms
            sms.senden(dbm.einstellungen(con), an, text)
        else:
            if "@" not in an:
                raise EingabeFehler("Beim Kunden ist keine gültige E-Mail-Adresse hinterlegt.")
            from .mail import MailFehler
            from .mail import senden as mail_senden
            try:
                hinweis = mail_senden(con, None, an, betreff, text)
            except MailFehler as e:
                raise EingabeFehler(str(e))
    except EingabeFehler as e:
        with dbm.Transaktion(con):
            con.execute("UPDATE benachrichtigungen SET status='fehler', an=?, betreff=?, text=?, hinweis=? WHERE id=?",
                        (an, betreff, text, str(e), bid))
            verlauf(con, b["auftrag_id"], f"Benachrichtigung fehlgeschlagen: {ANLAESSE[b['anlass']]}", str(e))
        return False, str(e)
    with dbm.Transaktion(con):
        con.execute("UPDATE benachrichtigungen SET status='gesendet', an=?, betreff=?, text=?, erledigt_am=?, "
                    "benutzer=?, hinweis=? WHERE id=?",
                    (an, betreff, text, dbm.jetzt_berlin(), dbm.aktueller_benutzer(), hinweis, bid))
        verlauf(con, b["auftrag_id"], f"Kunde benachrichtigt: {ANLAESSE[b['anlass']]}",
                f"{KANAELE.get(b['kanal'], b['kanal'])} an {an}: {betreff}")
    return True, hinweis


def offene_automatisch_senden(con):
    """Wenn die Vorschau ausgeschaltet ist: alle offenen Vorschläge sofort senden. Gibt Meldungen zurück."""
    if dbm.einstellungen(con).get("benachrichtigung_vorschau", True):
        return []
    meldungen = []
    for b in offene(con):
        ok, meldung = senden(con, b["id"])
        meldungen.append((ok, f"{ANLAESSE[b['anlass']]} ({b['auftragsnr']}): " + ("gesendet" if ok else meldung)))
    return meldungen


def erinnerungen_pruefen(con, heute=None):
    """Abholerinnerungen für fertige, nicht abgeholte Geräte vorschlagen. Muss in einer Transaktion laufen."""
    einst = dbm.einstellungen(con)
    if not einst.get("ben_erinnerung_aktiv"):
        return 0
    stufen = erinnerung_stufen(einst)
    if not stufen:
        return 0
    heute = date.fromisoformat(heute) if isinstance(heute, str) else (heute or date.today())
    anzahl = 0
    for a in con.execute("SELECT id, erledigt_am FROM auftraege WHERE status='erledigt' AND abgeholt_am IS NULL "
                         "AND erledigt_am IS NOT NULL").fetchall():
        tage = (heute - datetime.fromisoformat(a["erledigt_am"]).date()).days
        faellig = [s for s in stufen if s <= tage]
        if not faellig:
            continue
        stufe = faellig[-1]
        schon = con.execute("SELECT MAX(COALESCE(stufe, 0)) FROM benachrichtigungen WHERE auftrag_id=? "
                            "AND anlass='erinnerung'", (a["id"],)).fetchone()[0] or 0
        if schon >= stufe:
            continue
        if vorschlagen(con, a["id"], "erinnerung", stufe=stufe):
            anzahl += 1
    return anzahl


def nicht_abgeholt(con, heute=None):
    heute = heute or date.today().isoformat()
    return con.execute("SELECT a.*, k.kundennr, k.firma, k.vorname, k.nachname, k.typ AS ktyp, "
                       "CAST(julianday(?) - julianday(date(a.erledigt_am)) AS INTEGER) AS tage FROM auftraege a "
                       "JOIN kunden k ON k.id=a.kunde_id WHERE a.status='erledigt' AND a.abgeholt_am IS NULL "
                       "AND a.erledigt_am >= date(?, '-365 day') ORDER BY a.erledigt_am", (heute, heute)).fetchall()


def kva_ereignis(con, dokument_id, art):
    """KVA festgeschrieben → Vorschlag „KVA versendet“; KVA direkt per E-Mail gesendet → Vorschlag erübrigt sich.

    Muss in einer Transaktion laufen.
    """
    for a in con.execute("SELECT id FROM auftraege WHERE kva_id=?", (dokument_id,)).fetchall():
        if art == "festgeschrieben":
            vorschlagen(con, a["id"], "kva")
        elif art == "email":
            for b in con.execute("SELECT id FROM benachrichtigungen WHERE auftrag_id=? AND anlass='kva' "
                                 "AND status='offen'", (a["id"],)).fetchall():
                verwerfen(con, b["id"], "KVA wurde direkt per E-Mail an den Kunden gesendet")
