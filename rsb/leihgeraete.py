"""Leihgeräte, die Kunden während einer Reparatur mitgegeben werden.

Ablauf: Gerät anlegen → im Reparaturauftrag ausgeben (Leihvertrag/Übergabeprotokoll) → zurücknehmen
(Rückgabeprotokoll, Leihgebühr) → ggf. Schadensfall mit Kautionsverrechnung → Abrechnung in der Rechnung
des Auftrags. Protokolle und Schadensfälle sind gegen Ändern/Löschen geschützt (Datenbank-Trigger) und lassen
sich nur mit Begründung stornieren.
"""
import json
from datetime import date, datetime

from . import db as dbm
from .hilfen import EingabeFehler, euro

STATUS = {"verfuegbar": "Verfügbar", "verliehen": "Verliehen", "defekt": "Defekt / in Reparatur",
          "ausgemustert": "Ausgemustert"}
GEBUEHR_ARTEN = {"kostenlos": "kostenlos", "pauschal": "pauschal", "tag": "pro Tag"}
LEIHE_GEBUEHR_ARTEN = {"kostenlos": "kostenlos", "kulanz": "kostenlos (Kulanz)", "pauschal": "pauschal",
                       "tag": "pro Tag"}
KOSTENARTEN = {"reparatur": "Reparaturkosten", "zubehoer": "Zubehör-Ersatz", "totalschaden": "Totalschaden/Verlust (Zeitwert)"}
KAUTION_STATUS = {"keine": "keine Kaution", "gehalten": "liegt vor", "zurueckzuzahlen": "zurückzuzahlen",
                  "zurueckgezahlt": "zurückgezahlt", "verrechnet": "mit Schaden verrechnet"}
ZAHLARTEN = ["Bar", "EC-Karte", "Überweisung", "PayPal"]
KATALOG = {"pauschal": "Leihgebühr pauschal", "tag": "Leihgebühr pro Tag", "schaden": "Schadenersatz Leihgerät"}


# ---------------------------------------------------------------- Hilfen

def liste_aus_json(text):
    try:
        wert = json.loads(text or "[]")
        return [str(x) for x in wert] if isinstance(wert, list) else []
    except (ValueError, TypeError):
        return []


def zubehoer_aus_text(text):
    """Eine Zeile oder ein Komma je Zubehörteil → Liste ohne Doppelte."""
    teile = []
    for zeile in (text or "").replace(",", "\n").splitlines():
        z = zeile.strip()
        if z and z.lower() not in (t.lower() for t in teile):
            teile.append(z)
    return teile


def zeit_aus_eingabe(text):
    """'2026-10-15T14:03:27' (datetime-local) → ISO mit Sekunden und Zeitzone Europe/Berlin. Leer → jetzt."""
    if not (text or "").strip():
        return dbm.jetzt_berlin()
    try:
        dt = datetime.fromisoformat(text.strip())
    except ValueError:
        raise EingabeFehler(f"„{text}“ ist kein gültiger Zeitpunkt.")
    if dt.tzinfo is None:
        try:
            from zoneinfo import ZoneInfo
            dt = dt.replace(tzinfo=ZoneInfo("Europe/Berlin"))
        except Exception:
            dt = dt.astimezone()
    return dt.isoformat(timespec="seconds")


def _datum(iso):
    return datetime.fromisoformat(iso).date() if "T" in (iso or "") else date.fromisoformat(iso)


def ist_ueberfaellig(leihe, heute=None):
    if leihe["rueckgabe_am"] or leihe["storniert_am"] or not leihe["rueckgabe_geplant"]:
        return False
    return leihe["rueckgabe_geplant"] < (heute or date.today().isoformat())


def verlauf(con, geraet_id, ereignis, details=None):
    con.execute("INSERT INTO leihgeraet_verlauf (geraet_id, zeitpunkt, benutzer, ereignis, details) "
                "VALUES (?,?,?,?,?)", (geraet_id, dbm.jetzt_berlin(), dbm.aktueller_benutzer(), ereignis, details))


def _auftrag_verlauf(con, auftrag_id, ereignis, details=None):
    if auftrag_id:
        from .auftraege import verlauf as a_verlauf
        a_verlauf(con, auftrag_id, ereignis, details)


def gebuehr_beschreibung(art, betrag, frei_tage=0):
    if art == "kostenlos":
        return "kostenlos"
    if art == "kulanz":
        return "kostenlos (Kulanz)"
    if art == "pauschal":
        return f"{euro(betrag)} pauschal"
    return f"{euro(betrag)} pro Tag" + (f", die ersten {frei_tage} Tage kostenlos" if frei_tage else "")


# ---------------------------------------------------------------- Geräte

GERAET_FELDER = ["bezeichnung", "geraetetyp", "hersteller", "modell", "seriennummer", "inventarnr", "zubehoer",
                 "zustand", "anschaffung_am", "anschaffungswert", "zeitwert", "gebuehr_art", "gebuehr_betrag",
                 "frei_tage", "kaution"]
FELD_NAMEN = {"bezeichnung": "Bezeichnung", "geraetetyp": "Gerätetyp", "hersteller": "Hersteller", "modell": "Modell",
              "seriennummer": "Seriennummer", "inventarnr": "Inventarnummer", "zubehoer": "Zubehör",
              "zustand": "Zustand", "anschaffung_am": "Anschaffungsdatum", "anschaffungswert": "Anschaffungswert",
              "zeitwert": "Zeitwert", "gebuehr_art": "Abrechnungsart", "gebuehr_betrag": "Leihgebühr",
              "frei_tage": "kostenlose Tage", "kaution": "Kaution"}


def geraet_speichern(con, geraet_id, daten):
    """Legt ein Leihgerät an (geraet_id=None) oder ändert die Stammdaten. Muss in einer Transaktion laufen."""
    if not (daten.get("bezeichnung") or "").strip():
        raise EingabeFehler("Bitte eine Bezeichnung angeben (z. B. „Lenovo ThinkPad T14 #1“).")
    if daten.get("gebuehr_art") not in GEBUEHR_ARTEN:
        raise EingabeFehler("Bitte die Abrechnungsart der Leihgebühr wählen.")
    if daten["gebuehr_art"] == "kostenlos":
        daten["gebuehr_betrag"], daten["frei_tage"] = 0, 0
    if daten["gebuehr_art"] == "pauschal":
        daten["frei_tage"] = 0
    werte = [daten.get(f) for f in GERAET_FELDER]
    if geraet_id is None:
        cur = con.execute(f"INSERT INTO leihgeraete ({', '.join(GERAET_FELDER)}, status, erstellt_am, geaendert_am) "
                          f"VALUES ({', '.join('?' * len(GERAET_FELDER))}, 'verfuegbar', ?, ?)",
                          (*werte, dbm.jetzt(), dbm.jetzt()))
        gid = cur.lastrowid
        verlauf(con, gid, "Leihgerät angelegt", daten["bezeichnung"])
        dbm.protokollieren("leihgeraet_angelegt", "leihgeraet", gid, {"bezeichnung": daten["bezeichnung"]}, con=con)
        return gid
    alt = con.execute("SELECT * FROM leihgeraete WHERE id=?", (geraet_id,)).fetchone()
    geaendert = [FELD_NAMEN[f] for f in GERAET_FELDER if (alt[f] if alt[f] is not None else "") !=
                 (daten.get(f) if daten.get(f) is not None else "")]
    con.execute(f"UPDATE leihgeraete SET {', '.join(f'{f}=?' for f in GERAET_FELDER)}, geaendert_am=? WHERE id=?",
                (*werte, dbm.jetzt(), geraet_id))
    if geaendert:
        verlauf(con, geraet_id, "Stammdaten geändert", ", ".join(geaendert))
        dbm.protokollieren("leihgeraet_geaendert", "leihgeraet", geraet_id, {"felder": geaendert}, con=con)
    return geraet_id


def status_setzen(con, geraet_id, status, grund=""):
    """Manueller Statuswechsel (z. B. nach der Reparatur wieder „Verfügbar“). „Verliehen“ ergibt sich nur aus Leihen."""
    g = con.execute("SELECT * FROM leihgeraete WHERE id=?", (geraet_id,)).fetchone()
    if not g:
        raise EingabeFehler("Leihgerät nicht gefunden.")
    if status not in STATUS or status == "verliehen":
        raise EingabeFehler("Dieser Status kann nicht von Hand gesetzt werden.")
    if g["status"] == "verliehen":
        raise EingabeFehler("Das Gerät ist verliehen – bitte zuerst im Reparaturauftrag zurücknehmen.")
    if status == g["status"]:
        return
    con.execute("UPDATE leihgeraete SET status=?, geaendert_am=? WHERE id=?", (status, dbm.jetzt(), geraet_id))
    verlauf(con, geraet_id, "Status geändert",
            f"{STATUS[g['status']]} → {STATUS[status]}" + (f" – {grund}" if grund else ""))
    dbm.protokollieren("leihgeraet_status", "leihgeraet", geraet_id, {"von": g["status"], "nach": status,
                                                                      "grund": grund}, con=con)


# ---------------------------------------------------------------- Ausgabe

def naechste_leihnr(con):
    praefix = f"LV-{date.today().year}-"
    nr = 0
    for r in con.execute("SELECT leihnr FROM leihen WHERE leihnr LIKE ?", (praefix + "%",)):
        try:
            nr = max(nr, int(r["leihnr"].rsplit("-", 1)[1]))
        except (ValueError, IndexError):
            pass
    return f"{praefix}{nr + 1:04d}"


def ausgeben(con, auftrag_id, geraet_id, ausgabe_am, rueckgabe_geplant, zubehoer, zustand, gebuehr_art,
             gebuehr_betrag=0, frei_tage=0, kaution_erhalten=False, kaution_betrag=0, kaution_zahlart=""):
    """Gibt ein verfügbares Leihgerät zum Auftrag aus. Muss in einer Transaktion laufen. Gibt die Leih-ID zurück."""
    a = con.execute("SELECT * FROM auftraege WHERE id=?", (auftrag_id,)).fetchone()
    g = con.execute("SELECT * FROM leihgeraete WHERE id=?", (geraet_id,)).fetchone()
    if not a:
        raise EingabeFehler("Auftrag nicht gefunden.")
    if not g:
        raise EingabeFehler("Bitte ein Leihgerät auswählen.")
    if g["status"] != "verfuegbar":
        raise EingabeFehler(f"„{g['bezeichnung']}“ ist nicht verfügbar ({STATUS[g['status']]}).")
    if gebuehr_art not in LEIHE_GEBUEHR_ARTEN:
        raise EingabeFehler("Bitte die Leihgebühr wählen.")
    if gebuehr_art in ("kostenlos", "kulanz"):
        gebuehr_betrag, frei_tage = 0, 0
    if rueckgabe_geplant:
        try:
            date.fromisoformat(rueckgabe_geplant)
        except ValueError:
            raise EingabeFehler("Bitte ein gültiges Rückgabedatum angeben.")
        if rueckgabe_geplant < _datum(ausgabe_am).isoformat():
            raise EingabeFehler("Die voraussichtliche Rückgabe liegt vor der Ausgabe.")
    if kaution_erhalten and kaution_betrag <= 0:
        raise EingabeFehler("Bitte den Betrag der erhaltenen Kaution angeben.")
    nr = naechste_leihnr(con)
    cur = con.execute(
        "INSERT INTO leihen (leihnr, geraet_id, auftrag_id, auftragsnr, kunde_id, ausgabe_am, rueckgabe_geplant, "
        "zubehoer_ausgabe, zustand_ausgabe, gebuehr_art, gebuehr_betrag, frei_tage, kaution_erhalten, kaution_betrag, "
        "kaution_zahlart, ausgegeben_von, erfasst_am, kaution_status) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (nr, geraet_id, auftrag_id, a["auftragsnr"], a["kunde_id"], ausgabe_am, rueckgabe_geplant or None,
         json.dumps(zubehoer, ensure_ascii=False), zustand, gebuehr_art, gebuehr_betrag, frei_tage,
         1 if kaution_erhalten else 0, kaution_betrag if kaution_erhalten else 0,
         kaution_zahlart if kaution_erhalten else None, dbm.aktueller_benutzer(), dbm.jetzt_berlin(),
         "gehalten" if kaution_erhalten else "keine"))
    lid = cur.lastrowid
    con.execute("UPDATE leihgeraete SET status='verliehen', geaendert_am=? WHERE id=?", (dbm.jetzt(), geraet_id))
    kunde = con.execute("SELECT * FROM kunden WHERE id=?", (a["kunde_id"],)).fetchone()
    from .hilfen import kunde_name
    text = (f"{nr} an {kunde['kundennr']} · {kunde_name(kunde)} (Auftrag {a['auftragsnr']}), "
            f"Rückgabe {'bis ' + rueckgabe_geplant if rueckgabe_geplant else 'offen'}, "
            f"Gebühr {gebuehr_beschreibung(gebuehr_art, gebuehr_betrag, frei_tage)}"
            + (f", Kaution {euro(kaution_betrag)} ({kaution_zahlart})" if kaution_erhalten else ""))
    verlauf(con, geraet_id, "Verliehen", text)
    _auftrag_verlauf(con, auftrag_id, "Leihgerät ausgegeben", f"{g['bezeichnung']} – {text}")
    dbm.protokollieren("leihgeraet_ausgegeben", "leihe", lid, {"leihnr": nr, "geraet": geraet_id,
                                                               "auftrag": auftrag_id}, con=con)
    return lid


# ---------------------------------------------------------------- Rückgabe & Gebühr

def tage_berechnen(ausgabe_am, rueckgabe_am):
    """Leihtage = Kalendertage zwischen Ausgabe und Rückgabe, mindestens 1 (Rückgabe am selben Tag = 1 Tag)."""
    return max(1, (_datum(rueckgabe_am) - _datum(ausgabe_am)).days)


def gebuehr_berechnen(leihe, rueckgabe_am):
    """Gibt (tage, berechnete Tage, Betrag in Cent, Erklärung) zurück."""
    tage = tage_berechnen(leihe["ausgabe_am"], rueckgabe_am)
    art, betrag, frei = leihe["gebuehr_art"], leihe["gebuehr_betrag"], leihe["frei_tage"] or 0
    if art in ("kostenlos", "kulanz"):
        return tage, 0, 0, f"{tage} Tag(e), {LEIHE_GEBUEHR_ARTEN[art]}"
    if art == "pauschal":
        return tage, 0, betrag, f"{tage} Tag(e), pauschal {euro(betrag)}"
    berechnet = max(0, tage - frei)
    text = f"{tage} Tag(e)" + (f" − {frei} kostenlose Tag(e)" if frei else "") + \
        f" = {berechnet} Tag(e) à {euro(betrag)} = {euro(berechnet * betrag)}"
    return tage, berechnet, berechnet * betrag, text


def zuruecknehmen(con, leihe_id, rueckgabe_am, zubehoer_zurueck, zustand, notiz, gebuehr_cent, schaden=None):
    """Rücknahme. schaden = {beschreibung, kostenart, betrag} legt zusätzlich einen Schadensfall an.

    Gibt die ID des Schadensfalls zurück (oder None). Muss in einer Transaktion laufen.
    """
    le = con.execute("SELECT * FROM leihen WHERE id=?", (leihe_id,)).fetchone()
    if not le or le["storniert_am"]:
        raise EingabeFehler("Leihvorgang nicht gefunden.")
    if le["rueckgabe_am"]:
        raise EingabeFehler("Das Leihgerät wurde bereits zurückgenommen.")
    if zustand not in ("einwandfrei", "schaden"):
        raise EingabeFehler("Bitte den Zustand bei Rückgabe angeben.")
    if rueckgabe_am[:19] < le["ausgabe_am"][:19]:
        raise EingabeFehler("Die Rückgabe liegt vor der Ausgabe.")
    ausgabe = liste_aus_json(le["zubehoer_ausgabe"])
    fehlt = [z for z in ausgabe if z not in zubehoer_zurueck]
    if (zustand == "schaden" or fehlt) and not schaden:
        raise EingabeFehler("Bei einem Schaden oder fehlendem Zubehör bitte den Schadensfall beschreiben.")
    tage, _, vorschlag, text = gebuehr_berechnen(le, rueckgabe_am)
    if gebuehr_cent is None:
        gebuehr_cent = vorschlag
    if gebuehr_cent != vorschlag:
        text += f" – angepasst auf {euro(gebuehr_cent)}"
    kaution_status = le["kaution_status"]
    if le["kaution_erhalten"]:
        kaution_status = "verrechnet" if schaden else "zurueckzuzahlen"
    con.execute("UPDATE leihen SET rueckgabe_am=?, zubehoer_rueckgabe=?, zustand_rueckgabe=?, rueckgabe_notiz=?, "
                "zurueckgenommen_von=?, rueckgabe_erfasst_am=?, tage=?, gebuehr_berechnet=?, gebuehr_text=?, "
                "kaution_status=? WHERE id=?",
                (rueckgabe_am, json.dumps(zubehoer_zurueck, ensure_ascii=False), zustand, notiz,
                 dbm.aktueller_benutzer(), dbm.jetzt_berlin(), tage, gebuehr_cent, text, kaution_status, leihe_id))
    g = con.execute("SELECT * FROM leihgeraete WHERE id=?", (le["geraet_id"],)).fetchone()
    details = (f"{le['leihnr']}: {'einwandfrei' if zustand == 'einwandfrei' else 'Schaden festgestellt'}"
               + (f", fehlt: {', '.join(fehlt)}" if fehlt else "") + f", Leihgebühr {euro(gebuehr_cent)} ({text})")
    verlauf(con, g["id"], "Zurückgenommen", details)
    _auftrag_verlauf(con, le["auftrag_id"], "Leihgerät zurückgenommen", f"{g['bezeichnung']} – {details}")
    dbm.protokollieren("leihgeraet_zurueck", "leihe", leihe_id, {"zustand": zustand, "fehlt": fehlt,
                                                                 "gebuehr": gebuehr_cent}, con=con)
    if schaden:
        return schadensfall_anlegen(con, leihe_id, schaden.get("beschreibung", ""), schaden.get("kostenart", ""),
                                    schaden.get("betrag", 0))
    con.execute("UPDATE leihgeraete SET status='verfuegbar', geaendert_am=? WHERE id=?", (dbm.jetzt(), g["id"]))
    return None


# ---------------------------------------------------------------- Schadensfall

def schadensfall_anlegen(con, leihe_id, beschreibung, kostenart, betrag):
    le = con.execute("SELECT * FROM leihen WHERE id=?", (leihe_id,)).fetchone()
    if not le or le["storniert_am"]:
        raise EingabeFehler("Leihvorgang nicht gefunden.")
    beschreibung = (beschreibung or "").strip()
    if len(beschreibung) < 3:
        raise EingabeFehler("Bitte den Schaden beschreiben.")
    if kostenart not in KOSTENARTEN:
        raise EingabeFehler("Bitte die Kostenart des Schadens wählen.")
    if betrag < 0:
        raise EingabeFehler("Der Schadensbetrag darf nicht negativ sein.")
    cur = con.execute("INSERT INTO schadensfaelle (leihe_id, geraet_id, beschreibung, kostenart, betrag, erstellt_am, "
                      "benutzer) VALUES (?,?,?,?,?,?,?)",
                      (leihe_id, le["geraet_id"], beschreibung, kostenart, betrag, dbm.jetzt_berlin(),
                       dbm.aktueller_benutzer()))
    sid = cur.lastrowid
    neuer_status = "ausgemustert" if kostenart == "totalschaden" else "defekt"
    g = con.execute("SELECT * FROM leihgeraete WHERE id=?", (le["geraet_id"],)).fetchone()
    anderweitig_verliehen = con.execute(
        "SELECT 1 FROM leihen WHERE geraet_id=? AND id<>? AND rueckgabe_am IS NULL AND storniert_am IS NULL",
        (g["id"], leihe_id)).fetchone()
    if anderweitig_verliehen:  # Schaden wird nachträglich erfasst, das Gerät ist inzwischen wieder verliehen
        neuer_status = g["status"]
    else:
        con.execute("UPDATE leihgeraete SET status=?, geaendert_am=? WHERE id=?", (neuer_status, dbm.jetzt(), g["id"]))
    if le["kaution_erhalten"] and le["kaution_status"] in ("gehalten", "zurueckzuzahlen"):
        con.execute("UPDATE leihen SET kaution_status='verrechnet' WHERE id=?", (leihe_id,))
    text = f"{le['leihnr']}: {KOSTENARTEN[kostenart]} {euro(betrag)} – {beschreibung}"
    verlauf(con, g["id"], "Schadensfall angelegt", text + f" (Status: {STATUS[neuer_status]})")
    _auftrag_verlauf(con, le["auftrag_id"], "Schadensfall Leihgerät", f"{g['bezeichnung']} – {text}")
    dbm.protokollieren("schadensfall_angelegt", "leihe", leihe_id, {"schadensfall": sid, "betrag": betrag,
                                                                    "kostenart": kostenart}, con=con)
    return sid


def schaden_stornieren(con, schaden_id, grund):
    grund = (grund or "").strip()
    if len(grund) < 3:
        raise EingabeFehler("Bitte einen Grund für die Stornierung angeben.")
    s = con.execute("SELECT * FROM schadensfaelle WHERE id=?", (schaden_id,)).fetchone()
    if not s or s["storniert_am"]:
        raise EingabeFehler("Schadensfall nicht gefunden oder bereits storniert.")
    if s["rechnung_id"] and con.execute("SELECT 1 FROM dokumente WHERE id=? AND status<>'entwurf'",
                                        (s["rechnung_id"],)).fetchone():
        raise EingabeFehler("Der Schaden ist bereits in einer festgeschriebenen Rechnung – bitte die Rechnung stornieren.")
    con.execute("UPDATE schadensfaelle SET storniert_am=?, storniert_von=?, storno_grund=? WHERE id=?",
                (dbm.jetzt_berlin(), dbm.aktueller_benutzer(), grund, schaden_id))
    le = con.execute("SELECT * FROM leihen WHERE id=?", (s["leihe_id"],)).fetchone()
    if le["kaution_erhalten"] and le["kaution_status"] == "verrechnet" and not con.execute(
            "SELECT 1 FROM schadensfaelle WHERE leihe_id=? AND storniert_am IS NULL", (le["id"],)).fetchone():
        con.execute("UPDATE leihen SET kaution_status='zurueckzuzahlen' WHERE id=?", (le["id"],))
    verlauf(con, s["geraet_id"], "Schadensfall storniert", f"{euro(s['betrag'])} – Grund: {grund}")
    _auftrag_verlauf(con, le["auftrag_id"], "Schadensfall Leihgerät storniert", f"Grund: {grund}")
    dbm.protokollieren("schadensfall_storniert", "leihe", le["id"], {"schadensfall": schaden_id, "grund": grund},
                       con=con)


def leihe_stornieren(con, leihe_id, grund):
    """Irrtümliche Ausgabe rückgängig machen (nur vor der Rückgabe). Der Datensatz bleibt markiert erhalten."""
    grund = (grund or "").strip()
    if len(grund) < 3:
        raise EingabeFehler("Bitte einen Grund für die Stornierung angeben.")
    le = con.execute("SELECT * FROM leihen WHERE id=?", (leihe_id,)).fetchone()
    if not le or le["storniert_am"]:
        raise EingabeFehler("Leihvorgang nicht gefunden oder bereits storniert.")
    if le["rueckgabe_am"]:
        raise EingabeFehler("Bereits zurückgenommene Leihen können nicht storniert werden.")
    con.execute("UPDATE leihen SET storniert_am=?, storniert_von=?, storno_grund=?, kaution_status=? WHERE id=?",
                (dbm.jetzt_berlin(), dbm.aktueller_benutzer(), grund,
                 "zurueckzuzahlen" if le["kaution_erhalten"] else "keine", leihe_id))
    con.execute("UPDATE leihgeraete SET status='verfuegbar', geaendert_am=? WHERE id=? AND status='verliehen'",
                (dbm.jetzt(), le["geraet_id"]))
    verlauf(con, le["geraet_id"], "Leihe storniert", f"{le['leihnr']} – Grund: {grund}")
    _auftrag_verlauf(con, le["auftrag_id"], "Leihgerät-Ausgabe storniert", f"{le['leihnr']} – Grund: {grund}")
    dbm.protokollieren("leihe_storniert", "leihe", leihe_id, {"grund": grund}, con=con)


def schaeden(con, leihe_id, mit_stornierten=False):
    sql = "SELECT * FROM schadensfaelle WHERE leihe_id=?" + ("" if mit_stornierten else " AND storniert_am IS NULL")
    return con.execute(sql + " ORDER BY id", (leihe_id,)).fetchall()


def kaution_verrechnung(con, leihe):
    """Transparente Verrechnung: Schadenssumme − Kaution → noch zu zahlen bzw. Erstattung."""
    summe = sum(s["betrag"] for s in schaeden(con, leihe["id"]))
    kaution = leihe["kaution_betrag"] if leihe["kaution_erhalten"] else 0
    angerechnet = min(kaution, summe)
    return {"kaution": kaution, "schaden": summe, "angerechnet": angerechnet, "nachzahlung": summe - angerechnet,
            "erstattung": kaution - angerechnet}


def kaution_zurueckgezahlt(con, leihe_id):
    le = con.execute("SELECT * FROM leihen WHERE id=?", (leihe_id,)).fetchone()
    if not le or not le["kaution_erhalten"]:
        raise EingabeFehler("Zu diesem Leihvorgang gibt es keine Kaution.")
    v = kaution_verrechnung(con, le)
    if le["kaution_status"] == "zurueckgezahlt" or (le["kaution_status"] == "verrechnet" and not v["erstattung"]):
        raise EingabeFehler("Es ist nichts mehr zurückzuzahlen.")
    if le["kaution_status"] == "gehalten":
        raise EingabeFehler("Das Gerät ist noch nicht zurück.")
    betrag = v["erstattung"] if le["kaution_status"] == "verrechnet" else v["kaution"]
    con.execute("UPDATE leihen SET kaution_status='zurueckgezahlt', kaution_erledigt_am=? WHERE id=?",
                (dbm.jetzt_berlin(), leihe_id))
    verlauf(con, le["geraet_id"], "Kaution zurückgezahlt", f"{le['leihnr']}: {euro(betrag)}")
    _auftrag_verlauf(con, le["auftrag_id"], "Kaution zurückgezahlt", f"{le['leihnr']}: {euro(betrag)}")
    dbm.protokollieren("kaution_zurueckgezahlt", "leihe", leihe_id, {"betrag": betrag}, con=con)


# ---------------------------------------------------------------- Interner Reparaturauftrag

def interner_kunde(con):
    """Eigener (archivierter) Kunde für Reparaturen an Leihgeräten. Für ihn entstehen keine Rechnungen."""
    einst = dbm.einstellungen(con)
    kid = einst.get("interner_kunde_id")
    if kid and con.execute("SELECT 1 FROM kunden WHERE id=?", (kid,)).fetchone():
        return kid
    from .logik import naechste_kundennr
    cur = con.execute("INSERT INTO kunden (kundennr, typ, firma, notizen, archiviert, erstellt_am, geaendert_am) "
                      "VALUES (?, 'firma', ?, ?, 1, ?, ?)",
                      (naechste_kundennr(con, einst), f"{einst.get('firma_name') or 'Eigener Betrieb'} (intern)",
                       "Interner Kunde für Reparaturen an eigenen Leihgeräten – es werden keine Rechnungen erstellt.",
                       dbm.jetzt(), dbm.jetzt()))
    dbm.einstellungen_speichern({"interner_kunde_id": cur.lastrowid}, con)
    return cur.lastrowid


def ist_intern(con, kunde_id):
    return bool(kunde_id) and dbm.einstellungen(con).get("interner_kunde_id") == kunde_id


def interner_auftrag(con, schaden_id):
    s = con.execute("SELECT * FROM schadensfaelle WHERE id=?", (schaden_id,)).fetchone()
    if not s or s["storniert_am"]:
        raise EingabeFehler("Schadensfall nicht gefunden.")
    if s["interner_auftrag_id"]:
        return s["interner_auftrag_id"]
    g = con.execute("SELECT * FROM leihgeraete WHERE id=?", (s["geraet_id"],)).fetchone()
    le = con.execute("SELECT * FROM leihen WHERE id=?", (s["leihe_id"],)).fetchone()
    from .auftraege import anlegen
    aid = anlegen(con, interner_kunde(con), geraet=g["bezeichnung"], fehler=s["beschreibung"],
                  leistungsart="Sonstiges", seriennummer=g["seriennummer"] or g["inventarnr"] or "",
                  notizen=f"Interne Reparatur des Leihgeräts {g['bezeichnung']} (Inventar-Nr. {g['inventarnr'] or '–'}) "
                          f"nach Schadensfall aus Leihvertrag {le['leihnr']}. Keine Rechnung an Kunden.")
    con.execute("UPDATE schadensfaelle SET interner_auftrag_id=? WHERE id=?", (aid, schaden_id))
    verlauf(con, g["id"], "Interner Reparaturauftrag angelegt",
            con.execute("SELECT auftragsnr FROM auftraege WHERE id=?", (aid,)).fetchone()[0])
    return aid


def interner_auftrag_erledigt(con, auftrag_id):
    """Wird ein interner Reparaturauftrag erledigt, ist das Leihgerät wieder verfügbar."""
    for s in con.execute("SELECT * FROM schadensfaelle WHERE interner_auftrag_id=?", (auftrag_id,)).fetchall():
        g = con.execute("SELECT * FROM leihgeraete WHERE id=?", (s["geraet_id"],)).fetchone()
        if g["status"] == "defekt":
            con.execute("UPDATE leihgeraete SET status='verfuegbar', geaendert_am=? WHERE id=?", (dbm.jetzt(), g["id"]))
            verlauf(con, g["id"], "Reparatur abgeschlossen", "Status: Verfügbar")


# ---------------------------------------------------------------- Abrechnung

def _katalog(con, schluessel):
    name = KATALOG[schluessel]
    a = con.execute("SELECT * FROM artikel WHERE lower(name)=lower(?) ORDER BY aktiv DESC, id LIMIT 1",
                    (name,)).fetchone()
    satz = float(dbm.einstellungen(con).get("regel_steuersatz") or 19)
    return (a["id"] if a else None, a["steuersatz"] if a else satz, (a["leistungsart"] if a else None) or "Sonstiges")


def positionen(con, leihe):
    """Rechnungspositionen für Leihgebühr und (noch nicht abgerechnete) Schäden eines Leihvorgangs."""
    g = con.execute("SELECT * FROM leihgeraete WHERE id=?", (leihe["geraet_id"],)).fetchone()
    from .hilfen import datum_de
    zeitraum = f"Leihvertrag {leihe['leihnr']}, Ausgabe {datum_de(leihe['ausgabe_am'][:10])}, " \
               f"Rückgabe {datum_de(leihe['rueckgabe_am'][:10])}"
    if g["seriennummer"]:
        zeitraum += f", SN {g['seriennummer']}"
    pos = []
    if not leihe["rechnung_id"]:
        art = leihe["gebuehr_art"]
        betrag = leihe["gebuehr_berechnet"] or 0
        if art == "tag":
            _, berechnet, vorschlag, text = gebuehr_berechnen(leihe, leihe["rueckgabe_am"])
            artikel_id, satz, la = _katalog(con, "tag")
            if betrag == vorschlag and berechnet:
                pos.append(dict(bezeichnung=f"Leihgerät {g['bezeichnung']}, {berechnet} Tage à {euro(leihe['gebuehr_betrag'])}",
                                menge=berechnet, einheit="Tag", einzelpreis=leihe["gebuehr_betrag"],
                                beschreibung=f"{zeitraum}. {text}", artikel_id=artikel_id, steuersatz=satz,
                                leistungsart=la))
            else:
                pos.append(dict(bezeichnung=f"Leihgerät {g['bezeichnung']}, {leihe['tage']} Tage", menge=1,
                                einheit="pauschal", einzelpreis=betrag, beschreibung=f"{zeitraum}. {leihe['gebuehr_text']}",
                                artikel_id=artikel_id, steuersatz=satz, leistungsart=la))
        else:
            artikel_id, satz, la = _katalog(con, "pauschal")
            titel = {"pauschal": "pauschal", "kostenlos": "kostenlos", "kulanz": "kostenlos (Kulanz)"}[art]
            pos.append(dict(bezeichnung=f"Leihgerät {g['bezeichnung']}, {titel}", menge=1, einheit="pauschal",
                            einzelpreis=betrag, beschreibung=f"{zeitraum}. {leihe['tage']} Tag(e).",
                            artikel_id=artikel_id, steuersatz=satz, leistungsart=la))
    for s in schaeden(con, leihe["id"]):
        if s["rechnung_id"]:
            continue
        artikel_id, satz, la = _katalog(con, "schaden")
        pos.append(dict(bezeichnung=f"Schaden Leihgerät: {s['beschreibung'].splitlines()[0][:120]}", menge=1,
                        einheit="pauschal", einzelpreis=s["betrag"],
                        beschreibung=f"{KOSTENARTEN[s['kostenart']]} – {g['bezeichnung']}, {zeitraum}",
                        artikel_id=artikel_id, steuersatz=satz, leistungsart=la, schaden_id=s["id"]))
    for p in pos:
        p.setdefault("teilekosten", 0)
    return pos


def kaution_hinweis(con, leihe):
    if not leihe["kaution_erhalten"]:
        return ""
    g = con.execute("SELECT bezeichnung FROM leihgeraete WHERE id=?", (leihe["geraet_id"],)).fetchone()
    v = kaution_verrechnung(con, leihe)
    text = f"Kaution Leihgerät {g['bezeichnung']} ({leihe['leihnr']}): erhalten {euro(v['kaution'])}"
    text += f" ({leihe['kaution_zahlart']})." if leihe["kaution_zahlart"] else "."
    if v["schaden"]:
        text += (f" Verrechnung mit dem Schadenersatz von {euro(v['schaden'])}: {euro(v['angerechnet'])} sind durch "
                 f"die Kaution bereits bezahlt")
        text += f", noch zu zahlen {euro(v['nachzahlung'])}." if v["nachzahlung"] else "."
        if v["erstattung"]:
            text += f" Den Überschuss von {euro(v['erstattung'])} erstatten wir Ihnen."
    else:
        text += " Die Kaution wird nicht verrechnet und zurückgezahlt."
    return text


def in_rechnung_uebernehmen(con, leihe_id, dokument_id):
    """Hängt Leihgebühr/Schäden als Positionen an einen Rechnungsentwurf an. Gibt die Anzahl Positionen zurück."""
    from .logik import summen_speichern
    le = con.execute("SELECT * FROM leihen WHERE id=?", (leihe_id,)).fetchone()
    d = con.execute("SELECT * FROM dokumente WHERE id=?", (dokument_id,)).fetchone()
    if not d or d["status"] != "entwurf" or d["typ"] != "rechnung":
        raise EingabeFehler("Leihgebühren können nur in einen Rechnungsentwurf übernommen werden.")
    if not le["rueckgabe_am"] or le["storniert_am"]:
        raise EingabeFehler("Das Leihgerät ist noch nicht zurückgenommen.")
    pos = positionen(con, le)
    nr = con.execute("SELECT COALESCE(MAX(pos), 0) FROM positionen WHERE dokument_id=?", (dokument_id,)).fetchone()[0]
    for i, p in enumerate(pos, nr + 1):
        con.execute("INSERT INTO positionen (dokument_id, pos, artikel_id, bezeichnung, beschreibung, menge, einheit, "
                    "einzelpreis, teilekosten, steuersatz, leistungsart) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (dokument_id, i, p["artikel_id"], p["bezeichnung"], p["beschreibung"], p["menge"], p["einheit"],
                     p["einzelpreis"], 0, p["steuersatz"], p["leistungsart"]))
        if p.get("schaden_id"):
            con.execute("UPDATE schadensfaelle SET rechnung_id=? WHERE id=?", (dokument_id, p["schaden_id"]))
    if not le["rechnung_id"]:
        con.execute("UPDATE leihen SET rechnung_id=? WHERE id=?", (dokument_id, leihe_id))
    hinweis = kaution_hinweis(con, le)
    if hinweis and hinweis not in (d["hinweise"] or ""):
        con.execute("UPDATE dokumente SET hinweise=? WHERE id=?",
                    ("\n\n".join(t for t in [d["hinweise"], hinweis] if t), dokument_id))
    summen_speichern(con, dokument_id)
    if pos:
        _auftrag_verlauf(con, le["auftrag_id"], "Leihgerät abgerechnet",
                         f"{le['leihnr']}: {len(pos)} Position(en) in Rechnungsentwurf übernommen")
        dbm.protokollieren("leihe_abgerechnet", "leihe", leihe_id, {"dokument": dokument_id, "positionen": len(pos)},
                           con=con)
    return len(pos)


def abrechnungsziel(con, leihe):
    """Wohin gehören Leihgebühr/Schäden? ('entwurf', id) = Rechnungsentwurf des Auftrags, ('separat', None) = eigene
    Rechnung, ('warten', None) = Auftrag läuft noch – Übernahme automatisch beim Erledigen."""
    if leihe["separat_abrechnen"] or not leihe["auftrag_id"]:
        return "separat", None
    a = con.execute("SELECT * FROM auftraege WHERE id=?", (leihe["auftrag_id"],)).fetchone()
    if not a:
        return "separat", None
    if a["rechnung_id"]:
        d = con.execute("SELECT * FROM dokumente WHERE id=?", (a["rechnung_id"],)).fetchone()
        if d and d["status"] == "entwurf":
            return "entwurf", d["id"]
        return "separat", None
    return ("separat", None) if a["status"] == "erledigt" else ("warten", None)


def offen_abzurechnen(con, leihe):
    if leihe["storniert_am"] or not leihe["rueckgabe_am"]:
        return False
    return not leihe["rechnung_id"] or any(not s["rechnung_id"] for s in schaeden(con, leihe["id"]))


def fuer_auftragsrechnung(con, auftrag_id, dokument_id):
    """Beim Erstellen der Auftragsrechnung: alle zurückgenommenen, noch offenen Leihen übernehmen."""
    anzahl = 0
    for le in con.execute("SELECT * FROM leihen WHERE auftrag_id=? AND separat_abrechnen=0 ORDER BY id",
                          (auftrag_id,)).fetchall():
        if offen_abzurechnen(con, le):
            anzahl += in_rechnung_uebernehmen(con, le["id"], dokument_id)
    return anzahl


def separat_abrechnen(con, leihe_id):
    """Eigene Rechnung nur für Leihgebühr/Schäden (z. B. wenn die Auftragsrechnung schon festgeschrieben ist)."""
    from .logik import neuer_entwurf
    le = con.execute("SELECT * FROM leihen WHERE id=?", (leihe_id,)).fetchone()
    if not offen_abzurechnen(con, le):
        raise EingabeFehler("Für diesen Leihvorgang ist nichts mehr abzurechnen.")
    g = con.execute("SELECT * FROM leihgeraete WHERE id=?", (le["geraet_id"],)).fetchone()
    did = neuer_entwurf(con, dbm.einstellungen(con), "rechnung", le["kunde_id"],
                        f"Leihgerät {g['bezeichnung']} ({le['leihnr']}" +
                        (f", Auftrag {le['auftragsnr']})" if le["auftragsnr"] else ")"),
                        leistungsdatum=le["rueckgabe_am"][:10])
    in_rechnung_uebernehmen(con, leihe_id, did)
    return did


def offene_leihen_auftrag(con, auftrag_id):
    return con.execute("SELECT l.*, g.bezeichnung FROM leihen l JOIN leihgeraete g ON g.id=l.geraet_id "
                       "WHERE l.auftrag_id=? AND l.rueckgabe_am IS NULL AND l.storniert_am IS NULL",
                       (auftrag_id,)).fetchall()

