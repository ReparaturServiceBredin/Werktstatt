"""Reifen & Teile: Reifengrößen, Reifeneinlagerung („Reifenhotel“) und Thekenverkauf.

Reifeneinlagerung
  Ein Datensatz = ein Satz Räder bzw. Reifen eines Kunden mit Lagerplatz, Profiltiefe und DOT je Rad.
  Beim Saisonwechsel wird der eingelagerte Satz ausgelagert und der abgenommene Satz am selben Platz eingelagert
  („Tausch“). Etiketten und Einlagerungsschein kommen als PDF. Zum Saisonwechsel zeigt das Programm, welche Kunden
  noch erinnert werden müssen (E-Mail mit einem Klick oder Telefon abhaken).

Thekenverkauf
  Teile/Reifen direkt verkaufen: Rechnung wird sofort festgeschrieben, die Zahlung (bar → Kassenbuch, EC-Karte)
  erfasst und lagerführende Artikel werden ausgebucht. Ohne Kundenauswahl geht der Verkauf an den „Laufkunden“
  (Kleinbetragsrechnung bis 250 € brutto, § 33 UStDV).
"""
import io
import re
from datetime import date
from xml.sax.saxutils import escape

from . import db as dbm
from .hilfen import EingabeFehler, cent_aus_text, datum_de, euro, heute, heute_datum, kunde_name, zahl_aus_text

SAISONS = {"sommer": "Sommer", "winter": "Winter", "ganzjahr": "Ganzjahres"}
ARTEN = {"raeder": "Kompletträder (mit Felge)", "reifen": "nur Reifen"}
FELGEN = ["Alu", "Stahl"]
POSITIONEN = [("vl", "VL"), ("vr", "VR"), ("hl", "HL"), ("hr", "HR")]
POSITION_NAMEN = {"VL": "vorne links", "VR": "vorne rechts", "HL": "hinten links", "HR": "hinten rechts"}

# ---------------------------------------------------------------------- Reifengröße

_GROESSE = re.compile(r"(\d{3})\s*[/ ]?\s*(\d{2})\s*(?:Z?R|-|\s)\s*F?\s*(\d{2}(?:[.,]5)?)"
                      r"(?:\s*C?\s*(\d{2,3}(?:/\d{2,3})?)\s*([A-Z]{1,2})\b)?", re.I)


def groesse_zerlegen(text):
    """'205/55 R16 91V' -> {breite: 205, quer: 55, zoll: '16', last: '91', speed: 'V'} oder None."""
    m = _GROESSE.search(text or "")
    if not m:
        return None
    return {"breite": int(m.group(1)), "quer": int(m.group(2)), "zoll": m.group(3).replace(",", "."),
            "last": m.group(4) or "", "speed": (m.group(5) or "").upper()}


def groesse_text(text):
    """Einheitliche Schreibweise: '205 55 16' -> '205/55 R16'."""
    g = groesse_zerlegen(text)
    if not g:
        return (text or "").strip()
    return f"{g['breite']}/{g['quer']} R{g['zoll']}" + (f" {g['last']}{g['speed']}" if g["last"] else "")


def groesse_schluessel(text):
    """Ziffernfolge für die Suche: '205/55 R16 91V' -> '2055516'."""
    g = groesse_zerlegen(text)
    if g:
        return f"{g['breite']}{g['quer']}{g['zoll'].replace('.', '')}"
    return re.sub(r"\D", "", text or "")


def ist_groessen_suche(q):
    """'205/55 R16', '2055516', '205 55 16', '205/55' – aber nicht 'Ölfilter' oder eine EAN."""
    q = (q or "").strip()
    return bool(re.fullmatch(r"\d{3}\s*[/ ]?\s*\d{0,2}\s*(?:Z?R|-)?\s*\d{0,2}(?:[.,]5)?", q, re.I)) \
        and 3 <= len(re.sub(r"\D", "", q)) <= 8


def groesse_passt(groesse, q):
    return bool(groesse) and groesse_schluessel(groesse).startswith(re.sub(r"\D", "", q or ""))


# ---------------------------------------------------------------------- DOT und Profil

def dot_datum(dot):
    """DOT-Code 'WWJJ' (z. B. 2321 = KW 23/2021) -> date oder None."""
    ziffern = re.sub(r"\D", "", dot or "")[-4:]
    if len(ziffern) != 4:
        return None
    woche, jahr = int(ziffern[:2]), 2000 + int(ziffern[2:])
    if not 1 <= woche <= 53:
        return None
    try:
        return date.fromisocalendar(jahr, min(woche, 52), 1)
    except ValueError:
        return None


def dot_alter_jahre(dot, heute_=None):
    d = dot_datum(dot)
    if not d:
        return None
    return round(((heute_ or heute_datum()) - d).days / 365.25, 1)


def warnungen(e, einst):
    """Hinweise zu einem Satz: zu wenig Profil, alte Reifen (DOT)."""
    erg = []
    grenze = float(einst.get(f"einlagerung_profil_warnung_{'winter' if e['saison'] == 'winter' else 'sommer'}") or 3)
    for feld, kurz in POSITIONEN:
        p = e[f"profil_{feld}"]
        if p is not None and p < grenze:
            erg.append(f"{kurz}: nur {str(p).replace('.', ',')} mm Profil (unter {str(grenze).replace('.', ',')} mm)")
    max_jahre = float(einst.get("einlagerung_dot_warnung_jahre") or 6)
    alte = [kurz for feld, kurz in POSITIONEN if (dot_alter_jahre(e[f"dot_{feld}"]) or 0) >= max_jahre]
    if alte:
        erg.append(f"{', '.join(alte)}: Reifen älter als {int(max_jahre)} Jahre (DOT)")
    if erg:
        erg.append("→ Neue Reifen anbieten")
    return erg


# ---------------------------------------------------------------------- Einlagerung

FELDER = ["kunde_id", "auftrag_id", "vorgaenger_id", "kennzeichen", "fahrzeug", "saison", "art", "felge", "anzahl",
          "hersteller", "groesse", "profil_vl", "profil_vr", "profil_hl", "profil_hr", "dot_vl", "dot_vr", "dot_hl",
          "dot_hr", "zubehoer", "lagerplatz", "gebuehr", "bemerkung", "eingelagert_am"]
FELDNAMEN = {"kennzeichen": "Kennzeichen", "fahrzeug": "Fahrzeug", "saison": "Saison", "art": "Art",
             "felge": "Felge", "anzahl": "Anzahl", "hersteller": "Hersteller/Modell", "groesse": "Größe",
             "lagerplatz": "Lagerplatz", "gebuehr": "Gebühr (Cent)", "bemerkung": "Bemerkung",
             "zubehoer": "Zubehör", "eingelagert_am": "Eingelagert am",
             **{f"profil_{f}": f"Profil {k}" for f, k in POSITIONEN}, **{f"dot_{f}": f"DOT {k}" for f, k in POSITIONEN}}


def felder_aus_formular(form, einst):
    """Formular -> geprüfte Felder."""
    def text(n):
        return (form.get(n) or "").strip()

    kid = text("kunde_id")
    if not kid.isdigit():
        raise EingabeFehler("Bitte einen Kunden auswählen.")
    saison = text("saison") or "winter"
    if saison not in SAISONS:
        raise EingabeFehler("Bitte die Saison wählen.")
    art = text("art") or "raeder"
    if art not in ARTEN:
        art = "raeder"
    anzahl = int(text("anzahl")) if text("anzahl").isdigit() else 4
    if not 1 <= anzahl <= 10:
        raise EingabeFehler("Bitte eine Anzahl zwischen 1 und 10 angeben.")
    felder = {
        "kunde_id": int(kid),
        "auftrag_id": int(text("auftrag_id")) if text("auftrag_id").isdigit() else None,
        "vorgaenger_id": int(text("vorgaenger_id")) if text("vorgaenger_id").isdigit() else None,
        "kennzeichen": text("kennzeichen").upper(), "fahrzeug": text("fahrzeug"), "saison": saison, "art": art,
        "felge": text("felge") if art == "raeder" else "", "anzahl": anzahl, "hersteller": text("hersteller"),
        "groesse": groesse_text(text("groesse")), "zubehoer": text("zubehoer"), "lagerplatz": text("lagerplatz").upper(),
        "gebuehr": cent_aus_text(text("gebuehr"), leer=None), "bemerkung": text("bemerkung"),
        "eingelagert_am": text("eingelagert_am") or heute(),
    }
    for feld, kurz in POSITIONEN:
        p = text(f"profil_{feld}")
        wert = zahl_aus_text(p, None) if p else None
        if wert is not None and not 0 <= wert <= 20:
            raise EingabeFehler(f"Profiltiefe {kurz}: bitte in mm angeben (0–20).")
        felder[f"profil_{feld}"] = wert
        dot = re.sub(r"\D", "", text(f"dot_{feld}"))
        if dot and not dot_datum(dot):
            raise EingabeFehler(f"DOT {kurz}: bitte die vierstellige DOT-Nummer angeben (Woche + Jahr, z. B. 2321).")
        felder[f"dot_{feld}"] = dot[-4:] if dot else ""
    try:
        if date.fromisoformat(felder["eingelagert_am"]) > heute_datum():
            raise EingabeFehler("Das Einlagerungsdatum darf nicht in der Zukunft liegen.")
    except ValueError:
        raise EingabeFehler("Bitte ein gültiges Einlagerungsdatum angeben.")
    return felder


def _naechste_nummer(con, jahr):
    zeilen = con.execute("SELECT nummer FROM einlagerungen WHERE nummer LIKE ?", (f"EL-{jahr}-%",)).fetchall()
    hoechste = max((int(z[0].rsplit("-", 1)[1]) for z in zeilen if z[0].rsplit("-", 1)[1].isdigit()), default=0)
    return f"EL-{jahr}-{hoechste + 1:04d}"


def platz_belegt(con, lagerplatz, ausser_id=None):
    """Eingelagerter Satz eines anderen Kunden am selben Platz (oder None)."""
    if not lagerplatz:
        return None
    return con.execute("SELECT e.*, k.vorname, k.nachname, k.firma, k.typ FROM einlagerungen e "
                       "JOIN kunden k ON k.id=e.kunde_id WHERE e.lagerplatz=? AND e.ausgelagert_am IS NULL AND e.id<>?",
                       (lagerplatz, ausser_id or 0)).fetchone()


def anlegen(con, felder):
    """Muss in einer Transaktion laufen. Gibt die ID zurück."""
    if not con.execute("SELECT 1 FROM kunden WHERE id=?", (felder["kunde_id"],)).fetchone():
        raise EingabeFehler("Kunde nicht gefunden.")
    nummer = _naechste_nummer(con, felder["eingelagert_am"][:4])
    cur = con.execute(f"INSERT INTO einlagerungen (nummer, {', '.join(FELDER)}, erstellt_am, geaendert_am) "
                      f"VALUES (?, {', '.join('?' * len(FELDER))}, ?, ?)",
                      [nummer, *[felder.get(f) for f in FELDER], dbm.jetzt(), dbm.jetzt()])
    eid = cur.lastrowid
    dbm.protokollieren("einlagerung_angelegt", "einlagerung", eid, {"nummer": nummer}, con=con)
    dbm.aenderungen_erfassen(con, "einlagerung", eid, None, felder, aktion="angelegt", namen=FELDNAMEN)
    if felder.get("auftrag_id"):
        from .auftraege import verlauf
        verlauf(con, felder["auftrag_id"], "Räder eingelagert",
                f"{nummer}, Lagerplatz {felder.get('lagerplatz') or '–'}")
    return eid


def aendern(con, eid, felder):
    alt = laden(con, eid)
    felder = {k: v for k, v in felder.items() if k not in ("auftrag_id", "vorgaenger_id")}
    con.execute(f"UPDATE einlagerungen SET {', '.join(f'{f}=?' for f in felder)}, geaendert_am=? WHERE id=?",
                [*felder.values(), dbm.jetzt(), eid])
    dbm.aenderungen_erfassen(con, "einlagerung", eid, alt, felder, namen=FELDNAMEN)
    dbm.protokollieren("einlagerung_geaendert", "einlagerung", eid, con=con)


def laden(con, eid):
    e = con.execute("SELECT * FROM einlagerungen WHERE id=?", (eid,)).fetchone()
    if not e:
        raise EingabeFehler("Einlagerung nicht gefunden.")
    return e


def auslagern(con, eid, datum=None, notiz=""):
    e = laden(con, eid)
    if e["ausgelagert_am"]:
        raise EingabeFehler("Dieser Satz ist bereits ausgelagert.")
    datum = datum or heute()
    if datum < e["eingelagert_am"]:
        raise EingabeFehler("Das Auslagerungsdatum liegt vor der Einlagerung.")
    con.execute("UPDATE einlagerungen SET ausgelagert_am=?, auslagerung_notiz=?, geaendert_am=? WHERE id=?",
                (datum, notiz or None, dbm.jetzt(), eid))
    dbm.ereignis_erfassen(con, "einlagerung", eid, "ausgelagert", f"{e['nummer']} am {datum_de(datum)}")
    dbm.protokollieren("einlagerung_ausgelagert", "einlagerung", eid, {"datum": datum}, con=con)


def wieder_einlagern(con, eid):
    """Auslagerung rückgängig (z. B. versehentlich ausgelagert)."""
    e = laden(con, eid)
    if not e["ausgelagert_am"]:
        return
    belegt = platz_belegt(con, e["lagerplatz"], eid)
    if belegt:
        raise EingabeFehler(f"Lagerplatz {e['lagerplatz']} ist inzwischen mit {belegt['nummer']} belegt.")
    con.execute("UPDATE einlagerungen SET ausgelagert_am=NULL, auslagerung_notiz=NULL, geaendert_am=? WHERE id=?",
                (dbm.jetzt(), eid))
    dbm.ereignis_erfassen(con, "einlagerung", eid, "wieder eingelagert", e["nummer"])


def _liste_sql(where, args, sortierung="e.lagerplatz, e.nummer"):
    return (f"SELECT e.*, k.kundennr, k.vorname, k.nachname, k.firma, k.typ, k.email, k.telefon, k.anrede "
            f"FROM einlagerungen e JOIN kunden k ON k.id=e.kunde_id WHERE {where} ORDER BY {sortierung}", args)


def liste(con, q="", saison="", archiv=False, kunde_id=None):
    where = ["e.ausgelagert_am IS NOT NULL" if archiv else "e.ausgelagert_am IS NULL"]
    args = []
    if kunde_id:
        where, args = ["e.kunde_id=?"], [kunde_id]
    if saison in SAISONS:
        where.append("e.saison=?")
        args.append(saison)
    if q:
        such = f"%{q.strip()}%"
        kz = f"%{re.sub(r'[^A-Za-z0-9ÄÖÜäöü]', '', q).upper()}%"
        where.append("(e.nummer LIKE ? OR e.lagerplatz LIKE ? OR e.fahrzeug LIKE ? OR e.hersteller LIKE ? "
                     "OR e.groesse LIKE ? OR k.nachname LIKE ? OR k.vorname LIKE ? OR k.firma LIKE ? "
                     "OR k.kundennr LIKE ? OR REPLACE(REPLACE(UPPER(e.kennzeichen), '-', ''), ' ', '') LIKE ?)")
        args += [such] * 9 + [kz]
    sql, args = _liste_sql(" AND ".join(where), args,
                           "e.ausgelagert_am DESC, e.nummer DESC" if archiv else "e.lagerplatz, e.nummer")
    zeilen = con.execute(sql, args).fetchall()
    if q and ist_groessen_suche(q):  # zusätzlich nach Reifengröße
        ids = {z["id"] for z in zeilen}
        sql, args2 = _liste_sql(where[0], [])
        zeilen += [z for z in con.execute(sql, args2).fetchall() if z["id"] not in ids and groesse_passt(z["groesse"], q)]
    return zeilen


def kunde_einlagerungen(con, kunde_id):
    return con.execute(*_liste_sql("e.kunde_id=?", [kunde_id], "e.ausgelagert_am IS NOT NULL, e.eingelagert_am DESC")
                       ).fetchall()


def zahlen(con):
    r = con.execute("SELECT COUNT(*), COALESCE(SUM(anzahl), 0), COUNT(DISTINCT lagerplatz) FROM einlagerungen "
                    "WHERE ausgelagert_am IS NULL").fetchone()
    return {"saetze": r[0], "raeder": r[1], "plaetze": r[2]}


# ---------------------------------------------------------------------- Saisonwechsel

def saison_ziel(einst, heute_=None):
    """Welche Räder stehen gerade an? 'winter' rund um den Erinnerungsmonat für Winterräder, 'sommer' entsprechend,
    sonst None. Fenster: Vormonat bis Folgemonat."""
    monat = (heute_ or heute_datum()).month

    def nah(m):
        m = int(m or 0)
        return m and min((monat - m) % 12, (m - monat) % 12) <= 1

    if nah(einst.get("erinnerung_winter_monat") or 10):
        return "winter"
    if nah(einst.get("erinnerung_sommer_monat") or 4):
        return "sommer"
    return None


def saison_liste(con, saison):
    """Eingelagerte Sätze der Saison, die jetzt montiert werden – mit Erinnerungsstand."""
    sql, args = _liste_sql("e.ausgelagert_am IS NULL AND e.saison=?", [saison], "e.erinnert_am IS NOT NULL, k.nachname")
    return con.execute(sql, args).fetchall()


def frisch_erinnert(e, heute_=None):
    """In dieser Saison schon erinnert? (innerhalb der letzten 120 Tage)"""
    if not e["erinnert_am"]:
        return False
    try:
        return ((heute_ or heute_datum()) - date.fromisoformat(e["erinnert_am"][:10])).days <= 120
    except ValueError:
        return False


def noch_zu_erinnern(con, einst=None):
    einst = einst or dbm.einstellungen(con)
    ziel = saison_ziel(einst)
    if not ziel:
        return 0
    return sum(1 for e in saison_liste(con, ziel) if not frisch_erinnert(e))


def erinnert(con, eid, wie):
    con.execute("UPDATE einlagerungen SET erinnert_am=?, erinnert_wie=?, geaendert_am=? WHERE id=?",
                (heute(), wie, dbm.jetzt(), eid))
    dbm.ereignis_erfassen(con, "einlagerung", eid, "Kunde erinnert", wie)


def erinnerung_text(e, einst):
    from .hilfen import platzhalter_ersetzen
    anrede = {"Frau": f"Sehr geehrte Frau {e['nachname'] or ''}", "Herr": f"Sehr geehrter Herr {e['nachname'] or ''}"}
    werte = {"anrede": anrede.get(e["anrede"] or "", "Guten Tag").strip(), "saison": SAISONS[e["saison"]],
             "kennzeichen": e["kennzeichen"] or e["fahrzeug"] or e["nummer"], "lagerplatz": e["lagerplatz"] or "–",
             "telefon": einst.get("telefon") or "", "firma": einst.get("firma_name") or "", "nummer": e["nummer"]}
    betreff = f"Zeit für Ihre {SAISONS[e['saison']]}räder – {werte['kennzeichen']}"
    return betreff, platzhalter_ersetzen(einst.get("erinnerung_text") or "", werte)


def erinnerung_senden(con, eid):
    """E-Mail an den Kunden; wirft MailFehler/EingabeFehler. Muss außerhalb einer Transaktion laufen."""
    from . import mail
    einst = dbm.einstellungen(con)
    e = con.execute(*_liste_sql("e.id=?", [eid])).fetchone()
    if not e:
        raise EingabeFehler("Einlagerung nicht gefunden.")
    if not (e["email"] or "").strip():
        raise EingabeFehler(f"{kunde_name(e)} hat keine E-Mail-Adresse – bitte anrufen und abhaken.")
    betreff, text = erinnerung_text(e, einst)
    mail.senden(con, an=e["email"], betreff=betreff, text=text)
    with dbm.Transaktion(con):
        erinnert(con, eid, "E-Mail")


# ---------------------------------------------------------------------- Abrechnung der Einlagerung

def rechnung_entwurf(con, eid):
    """Rechnungsentwurf über die Einlagerungsgebühr. Muss in einer Transaktion laufen."""
    from . import logik
    e = laden(con, eid)
    einst = dbm.einstellungen(con)
    brutto = e["gebuehr"] if e["gebuehr"] is not None else int(einst.get("einlagerung_gebuehr_cent") or 0)
    satz = 19.0
    preis = brutto if einst["steuer_modus"] == "kleinunternehmer" else int(round(brutto / (1 + satz / 100)))
    bez = f"Reifeneinlagerung {SAISONS[e['saison']]}räder"
    beschr = " · ".join(x for x in (e["kennzeichen"], e["fahrzeug"], e["groesse"], f"Lagerplatz {e['lagerplatz']}"
                                    if e["lagerplatz"] else "", e["nummer"]) if x)
    pos = [{"artikel_id": None, "bezeichnung": bez, "beschreibung": beschr, "menge": 1, "einheit": "Satz",
            "einzelpreis": preis, "teilekosten": 0, "steuersatz": satz, "leistungsart": "Einlagerung"}]
    did = logik.neuer_entwurf(con, einst, "rechnung", e["kunde_id"], betreff=bez, positionen=pos)
    con.execute("UPDATE einlagerungen SET rechnung_id=?, geaendert_am=? WHERE id=?", (did, dbm.jetzt(), eid))
    return did


# ---------------------------------------------------------------------- PDF: Einlagerungsschein und Etiketten

def pdf(con, eid, einst, nur_etiketten=False):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas as rl_canvas
    from reportlab.platypus import Paragraph, Table, TableStyle
    from .pdf import _farbe, _schrift_registrieren

    e = con.execute(*_liste_sql("e.id=?", [eid])).fetchone()
    if not e:
        raise EingabeFehler("Einlagerung nicht gefunden.")
    f_norm, f_fett, _ = _schrift_registrieren(einst.get("schrift") or "Montserrat")
    blau = _farbe(einst.get("farbe_primaer"))
    puffer = io.BytesIO()
    c = rl_canvas.Canvas(puffer, pagesize=A4)
    c.setTitle(f"Einlagerung {e['nummer']}")
    c.setCreator(einst.get("firma_name") or "")
    breite, hoehe = A4
    kunde = kunde_name(e)
    firma = einst.get("firma_name") or ""

    if not nur_etiketten:
        st = ParagraphStyle("n", fontName=f_norm, fontSize=9.5, leading=13)
        st_f = ParagraphStyle("f", parent=st, fontName=f_fett)
        y = hoehe - 22 * mm
        c.setFont(f_fett, 9)
        c.setFillColor(colors.grey)
        c.drawString(22 * mm, y, " · ".join(x for x in (firma, einst.get("strasse"), f"{einst.get('plz') or ''} "
                                                        f"{einst.get('ort') or ''}".strip(), einst.get("telefon")) if x))
        y -= 14 * mm
        c.setFillColor(blau)
        c.setFont(f_fett, 17)
        c.drawString(22 * mm, y, f"Einlagerungsschein {e['nummer']}")
        y -= 7 * mm
        c.setFillColor(colors.black)
        c.setFont(f_norm, 10)
        c.drawString(22 * mm, y, f"{SAISONS[e['saison']]}räder · eingelagert am {datum_de(e['eingelagert_am'])}"
                     + (f" · ausgelagert am {datum_de(e['ausgelagert_am'])}" if e["ausgelagert_am"] else ""))

        def p(t, s=st):
            return Paragraph(escape(str(t or "–")), s)

        daten = [
            [p("Kunde", st_f), p(f"{kunde} ({e['kundennr']})")],
            [p("Fahrzeug", st_f), p(" · ".join(x for x in (e["kennzeichen"], e["fahrzeug"]) if x))],
            [p("Art", st_f), p(f"{e['anzahl']} × {ARTEN[e['art']]}" + (f", {e['felge']}felge" if e["felge"] else ""))],
            [p("Reifen", st_f), p(" · ".join(x for x in (e["hersteller"], e["groesse"]) if x))],
            [p("Lagerplatz", st_f), p(e["lagerplatz"])],
            [p("Zubehör", st_f), p(e["zubehoer"])],
            [p("Bemerkung", st_f), p(e["bemerkung"])],
        ]
        if e["gebuehr"] is not None:
            daten.append([p("Gebühr je Saison", st_f), p(euro(e["gebuehr"]) + " (brutto)")])
        t = Table(daten, colWidths=[40 * mm, 126 * mm])
        t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, -1), 0.3, colors.lightgrey),
                               ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
        _, th = t.wrap(166 * mm, 200 * mm)
        y -= 8 * mm
        t.drawOn(c, 22 * mm, y - th)
        y -= th + 8 * mm
        kopf = [p("Rad", st_f), p("Profiltiefe", st_f), p("DOT (Woche/Jahr)", st_f), p("Alter", st_f)]
        zeilen = [kopf]
        for feld, kurz in POSITIONEN:
            pr = e[f"profil_{feld}"]
            dot = e[f"dot_{feld}"]
            alter = dot_alter_jahre(dot)
            zeilen.append([p(f"{kurz} ({POSITION_NAMEN[kurz]})"),
                           p(f"{str(pr).replace('.', ',')} mm" if pr is not None else "–"),
                           p(f"{dot[:2]}/20{dot[2:]}" if dot else "–"),
                           p(f"{str(alter).replace('.', ',')} Jahre" if alter is not None else "–")])
        t2 = Table(zeilen, colWidths=[56 * mm, 36 * mm, 40 * mm, 34 * mm])
        t2.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.3, colors.lightgrey),
                                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EEF2F6"))]))
        _, th = t2.wrap(166 * mm, 200 * mm)
        t2.drawOn(c, 22 * mm, y - th)
        y -= th + 8 * mm
        w = warnungen(e, einst)
        if w:
            c.setFont(f_fett, 10)
            c.setFillColor(colors.HexColor("#B42318"))
            for zeile in w:
                c.drawString(22 * mm, y, zeile)
                y -= 5.5 * mm
            c.setFillColor(colors.black)
        hinweis = Paragraph(escape(
            "Die Räder werden bis zur Abholung bzw. zum nächsten Saisonwechsel bei uns eingelagert. Bitte bringen Sie "
            "diesen Schein oder Ihr Kennzeichen mit. Nach der Montage Radschrauben nach 50 km nachziehen lassen."), st)
        _, hh = hinweis.wrap(166 * mm, 40 * mm)
        hinweis.drawOn(c, 22 * mm, 60 * mm)
        c.line(22 * mm, 38 * mm, 90 * mm, 38 * mm)
        c.line(110 * mm, 38 * mm, 188 * mm, 38 * mm)
        c.setFont(f_norm, 8)
        c.drawString(22 * mm, 34 * mm, "Datum, Unterschrift Kunde")
        c.drawString(110 * mm, 34 * mm, f"Unterschrift {firma}")
        c.showPage()

    # Etiketten: 4 Felder (2 × 2) je Seite, je Rad eines
    positionen = [k for _, k in POSITIONEN][:e["anzahl"]] if e["anzahl"] <= 4 else \
        [k for _, k in POSITIONEN] + [f"Ersatz {i}" for i in range(1, e["anzahl"] - 3)]
    feld_b, feld_h = (breite - 20 * mm) / 2, (hoehe - 20 * mm) / 2
    for i, pos in enumerate(positionen):
        if i and i % 4 == 0:
            c.showPage()
        spalte, reihe = i % 2, (i % 4) // 2
        x0 = 10 * mm + spalte * feld_b
        y0 = hoehe - 10 * mm - (reihe + 1) * feld_h
        c.setStrokeColor(colors.grey)
        c.setDash(3, 3)
        c.rect(x0, y0, feld_b, feld_h)
        c.setDash()
        mitte = x0 + feld_b / 2
        oben = y0 + feld_h - 16 * mm
        c.setFillColor(colors.black)
        c.setFont(f_fett, 34)
        c.drawCentredString(mitte, oben - 6 * mm, (e["kennzeichen"] or e["nummer"])[:14])
        c.setFont(f_fett, 64)
        c.setFillColor(blau)
        c.drawCentredString(mitte, oben - 36 * mm, pos if len(pos) <= 3 else pos[:9])
        c.setFillColor(colors.black)
        c.setFont(f_norm, 12)
        c.drawCentredString(mitte, oben - 46 * mm, POSITION_NAMEN.get(pos, ""))
        c.setFont(f_fett, 20)
        c.drawCentredString(mitte, oben - 62 * mm, f"Platz {e['lagerplatz'] or '—'}")
        c.setFont(f_norm, 11)
        c.drawCentredString(mitte, oben - 72 * mm, kunde[:40])
        c.drawCentredString(mitte, oben - 79 * mm, f"{SAISONS[e['saison']]} · {e['groesse'] or ''}".strip(" ·"))
        c.setFont(f_norm, 9)
        c.drawCentredString(mitte, oben - 87 * mm, f"{e['nummer']} · {datum_de(e['eingelagert_am'])}")
    c.showPage()
    c.save()
    return puffer.getvalue()


# ---------------------------------------------------------------------- Thekenverkauf

LAUFKUNDE_NAME = "Laufkunde (Barverkauf)"


def laufkunde(con, einst):
    """Kunde für Verkäufe ohne Namen (Kleinbetragsrechnung). Wird beim ersten Mal angelegt. In Transaktion."""
    kid = einst.get("theke_laufkunde_id")
    if kid and con.execute("SELECT 1 FROM kunden WHERE id=? AND anonymisiert_am IS NULL", (kid,)).fetchone():
        return kid
    from .logik import naechste_kundennr
    cur = con.execute("INSERT INTO kunden (kundennr, typ, nachname, notizen, erstellt_am, geaendert_am) "
                      "VALUES (?, 'privat', ?, ?, ?, ?)",
                      (naechste_kundennr(con, einst), LAUFKUNDE_NAME,
                       "Sammelkunde für den Thekenverkauf ohne Namen (Kleinbetragsrechnungen bis 250 €).",
                       dbm.jetzt(), dbm.jetzt()))
    dbm.einstellungen_speichern({"theke_laufkunde_id": cur.lastrowid}, con)
    return cur.lastrowid


def theke_positionen(form):
    """Formular -> Positionen [{artikel_id, bezeichnung, menge, preis_brutto}]."""
    erg = []
    for aid, bez, menge, preis in zip(form.getlist("t_artikel_id"), form.getlist("t_bezeichnung"),
                                      form.getlist("t_menge"), form.getlist("t_preis")):
        if not bez.strip():
            continue
        m = zahl_aus_text(menge, 1)
        if m <= 0:
            raise EingabeFehler(f"„{bez.strip()}“: Bitte eine Menge größer 0 angeben.")
        erg.append({"artikel_id": int(aid) if aid.strip().isdigit() else None, "bezeichnung": bez.strip(),
                    "menge": m, "preis_brutto": cent_aus_text(preis)})
    if not erg:
        raise EingabeFehler("Bitte mindestens einen Artikel in den Warenkorb legen.")
    return erg


def theke_verkaufen(con, positionen, zahlart, daten_dir, kunde_id=None):
    """Rechnung anlegen, festschreiben, Zahlung erfassen, Lager ausbuchen. Gibt (dokument_id, nummer, hinweise)."""
    from . import lager, logik, zahlungen
    if zahlart not in ("bar", "karte", "ueberweisung"):
        raise EingabeFehler("Bitte die Zahlungsart wählen.")
    einst = dbm.einstellungen(con)
    hinweise = []
    with dbm.Transaktion(con):
        if not kunde_id:
            kunde_id = laufkunde(con, einst)
            if zahlart == "ueberweisung":
                raise EingabeFehler("Zahlung per Überweisung nur mit Kundenauswahl (Rechnungsanschrift).")
        pos = []
        for p in positionen:
            a = con.execute("SELECT * FROM artikel WHERE id=?", (p["artikel_id"],)).fetchone() if p["artikel_id"] else None
            satz = float(a["steuersatz"]) if a else 19.0
            netto = p["preis_brutto"] if einst["steuer_modus"] == "kleinunternehmer" else \
                int(round(p["preis_brutto"] / (1 + satz / 100)))
            beschr = (a["reifen_groesse"] or "") if a and a["reifen_groesse"] else ""
            if a and a["herstellernr"]:
                beschr = (beschr + " · " if beschr else "") + f"Art.-Nr. {a['herstellernr']}"
            pos.append({"artikel_id": a["id"] if a else None, "bezeichnung": p["bezeichnung"], "beschreibung": beschr,
                        "menge": p["menge"], "einheit": (a["einheit"] if a else "") or "Stk.", "einzelpreis": netto,
                        "teilekosten": (a["teilekosten"] if a else 0) or 0, "steuersatz": satz,
                        "leistungsart": (a["leistungsart"] if a else "") or "Teileverkauf",
                        "garantie_monate": a["garantie_monate"] if a else None})
        did = logik.neuer_entwurf(con, einst, "rechnung", kunde_id, betreff="Verkauf", positionen=pos)
        if zahlart in ("bar", "karte"):
            con.execute("UPDATE dokumente SET zahlungsziel_tage=0, faellig_am=datum WHERE id=?", (did,))
    nummer = logik.festschreiben(con, did, daten_dir)  # eigene Transaktion; schlägt sie fehl, bleibt der Entwurf
    with dbm.Transaktion(con):
        d = con.execute("SELECT * FROM dokumente WHERE id=?", (did,)).fetchone()
        if zahlart in ("bar", "karte"):
            zahlungen.erfassen(con, did, d["datum"], d["summe_brutto"], zahlart, "Thekenverkauf")
        for p in pos:
            if not p["artikel_id"]:
                continue
            a = con.execute("SELECT * FROM artikel WHERE id=?", (p["artikel_id"],)).fetchone()
            if a["lagerfuehrend"]:
                _, negativ = lager.bewegung_buchen(con, a["id"], "abgang", p["menge"], f"Thekenverkauf {nummer}",
                                                   dokument_id=did)
                if negativ:
                    hinweise.append(f"Lagerbestand von „{a['name']}“ ist jetzt negativ – bitte Bestand prüfen.")
        dbm.protokollieren("thekenverkauf", "dokument", did, {"nummer": nummer, "zahlart": zahlart}, con=con)
    return did, nummer, hinweise


def theke_storniert(con, dokument_id):
    """Storno einer Thekenrechnung: ausgebuchte Artikel wieder einbuchen. Muss in einer Transaktion laufen."""
    from . import lager
    anzahl = 0
    for b in con.execute("SELECT * FROM lagerbewegungen WHERE dokument_id=? AND art='abgang' AND grund LIKE "
                         "'Thekenverkauf %'", (dokument_id,)).fetchall():
        lager.bewegung_buchen(con, b["artikel_id"], "zugang", abs(b["menge"]), f"Storno {b['grund']}",
                              dokument_id=dokument_id, ek=b["ek"])
        anzahl += 1
    return anzahl


def artikel_suche(con, q, nur_aktive=True, limit=None):
    """Artikelsuche für Liste und Theke: Name, Nummern, EAN, OE-Nummer, Fahrzeug – und Reifengröße."""
    q = (q or "").strip()
    basis = "SELECT * FROM artikel WHERE " + ("aktiv=1" if nur_aktive else "1=1")
    if not q:
        return con.execute(basis + " ORDER BY aktiv DESC, leistungsart, name" + (f" LIMIT {int(limit)}" if limit else "")
                           ).fetchall()
    such = f"%{q}%"
    zeilen = con.execute(basis + " AND (name LIKE ? OR artikelnr LIKE ? OR leistungsart LIKE ? OR beschreibung LIKE ? "
                         "OR ean LIKE ? OR herstellernr LIKE ? OR kompatibilitaet LIKE ? OR reifen_groesse LIKE ?) "
                         "ORDER BY aktiv DESC, leistungsart, name", [such] * 8).fetchall()
    if ist_groessen_suche(q):
        ids = {z["id"] for z in zeilen}
        zeilen += [z for z in con.execute(basis + " AND reifen_groesse IS NOT NULL AND reifen_groesse<>'' "
                                          "ORDER BY name").fetchall()
                   if z["id"] not in ids and groesse_passt(z["reifen_groesse"], q)]
    return zeilen[:limit] if limit else zeilen
