"""Aufträge: Tafel mit den Spalten offen / in Arbeit / erledigt.

Wird ein Auftrag auf „erledigt“ gezogen, entsteht automatisch ein Rechnungsentwurf
mit den Positionen aus dem Kostenvoranschlag (falls vorhanden).
"""
from datetime import date

from . import db as dbm
from . import logik
from .hilfen import EingabeFehler

STATUS = {"offen": "Offen", "in_arbeit": "In Arbeit", "erledigt": "Erledigt"}
# Spalten der Tafel: „Wartet auf Teil“ ist ein In-Arbeit-Auftrag mit gesetztem wartet_teil_seit
TAFEL = {"offen": "Offen", "in_arbeit": "In Arbeit", "wartet_teil": "Wartet auf Teil", "erledigt": "Erledigt"}


def tafel_status(a):
    return "wartet_teil" if a["status"] == "in_arbeit" and a["wartet_teil_seit"] else a["status"]


def naechste_auftragsnr(con):
    jahr = date.today().year
    praefix = f"AU-{jahr}-"
    nr = 0
    for r in con.execute("SELECT auftragsnr FROM auftraege WHERE auftragsnr LIKE ?", (praefix + "%",)):
        try:
            nr = max(nr, int(r["auftragsnr"].rsplit("-", 1)[1]))
        except (ValueError, IndexError):
            pass
    return f"{praefix}{nr + 1:04d}"


ANNAHME_FELDER = ("zustand_eingang", "kosten_obergrenze", "kva_gewuenscht", "kva_gebuehr", "fertig_bis", "zugang_art",
                  "auftragsart", "garantie_bezug_id", "garantie_monate", "interne_kosten", "interne_kosten_notiz",
                  "geraetetyp", "kennzeichen", "km_stand", "erstzulassung", "hu_bis", "termin_beginn",
                  "termin_dauer")


def anlegen(con, kunde_id, geraet="", fehler="", leistungsart="", seriennummer="", zubehoer="", notizen="",
            anfrage_id=None, **annahme):
    """Legt einen Auftrag in der Spalte „offen“ an. Muss in einer Transaktion laufen.

    annahme: optionale Felder aus ANNAHME_FELDER (Kosten-Obergrenze, KVA-Wunsch, Fertigstellung …).
    """
    if not con.execute("SELECT 1 FROM kunden WHERE id=?", (kunde_id,)).fetchone():
        raise EingabeFehler("Bitte einen Kunden auswählen.")
    nr = naechste_auftragsnr(con)
    reihenfolge = (con.execute("SELECT MAX(reihenfolge) FROM auftraege WHERE status='offen'").fetchone()[0] or 0) + 1
    cur = con.execute(
        "INSERT INTO auftraege (auftragsnr, kunde_id, anfrage_id, status, geraet, leistungsart, seriennummer, zubehoer, "
        "fehler, notizen, reihenfolge, eingang_am, erstellt_am, geaendert_am) "
        "VALUES (?,?,?,'offen',?,?,?,?,?,?,?,?,?,?)",
        (nr, kunde_id, anfrage_id, geraet, leistungsart, seriennummer, zubehoer, fehler, notizen, reihenfolge,
         dbm.jetzt(), dbm.jetzt(), dbm.jetzt()))
    weitere = {k: v for k, v in annahme.items() if k in ANNAHME_FELDER}
    for k in ("teil_info", "teil_erwartet"):
        if annahme.get(k):
            weitere[k] = annahme[k]
    if weitere:
        con.execute(f"UPDATE auftraege SET {', '.join(f'{k}=?' for k in weitere)} WHERE id=?",
                    (*weitere.values(), cur.lastrowid))
    from .checkliste import ergaenzen
    ergaenzen(con, cur.lastrowid, leistungsart, dbm.einstellungen(con))
    dbm.protokollieren("auftrag_angelegt", "auftrag", cur.lastrowid, {"auftragsnr": nr}, con=con)
    verlauf(con, cur.lastrowid, "Auftrag angelegt", nr)
    from .benachrichtigung import vorschlagen
    vorschlagen(con, cur.lastrowid, "angenommen")
    return cur.lastrowid


def verlauf(con, auftrag_id, ereignis, details=None):
    """Hängt einen Eintrag an den Verlauf des Auftrags an (Zeit Europe/Berlin, Benutzer)."""
    con.execute("INSERT INTO auftrag_verlauf (auftrag_id, zeitpunkt, benutzer, ereignis, details) VALUES (?,?,?,?,?)",
                (auftrag_id, dbm.jetzt_berlin(), dbm.aktueller_benutzer(), ereignis, details))


def verlauf_liste(con, auftrag_id):
    """Verlauf eines Auftrags. Einträge eines früher gelöschten Auftrags mit derselben ID werden ausgeblendet."""
    grenze = con.execute("SELECT MAX(id) FROM auftrag_verlauf WHERE auftrag_id=? AND ereignis='Auftrag gelöscht'",
                         (auftrag_id,)).fetchone()[0] or 0
    return con.execute("SELECT * FROM auftrag_verlauf WHERE auftrag_id=? AND id>? ORDER BY zeitpunkt, id",
                       (auftrag_id, grenze)).fetchall()


KVA_STATUS = {"offen": "offen", "angenommen": "angenommen", "abgelehnt": "abgelehnt"}


def _kva_text(d):
    return f"{d['nummer'] or 'Entwurf'} ({d['summe_brutto'] / 100:.2f} €)".replace(".", ",")


def kva_kandidaten(con, kunde_id=None, alle=False, suche=""):
    """KVAs, die noch keinem Auftrag zugeordnet sind (standardmäßig nur vom selben Kunden)."""
    sql = ("SELECT d.*, k.kundennr, k.firma, k.vorname, k.nachname, k.typ AS ktyp FROM dokumente d "
           "LEFT JOIN kunden k ON k.id=d.kunde_id WHERE d.typ='kva' AND d.status<>'storniert' "
           "AND d.id NOT IN (SELECT kva_id FROM auftraege WHERE kva_id IS NOT NULL) ")
    args = []
    if not alle and kunde_id:
        sql += "AND d.kunde_id=? "
        args.append(kunde_id)
    suche = (suche or "").strip()
    if suche:
        from .hilfen import cent_aus_text
        bedingungen = ["d.nummer LIKE ?", "d.datum LIKE ?", "d.betreff LIKE ?", "strftime('%d.%m.%Y', d.datum) LIKE ?"]
        args += [f"%{suche}%"] * 4
        try:
            betrag = cent_aus_text(suche)
            if betrag:
                bedingungen.append("d.summe_brutto=?")
                args.append(betrag)
        except Exception:
            pass
        sql += "AND (" + " OR ".join(bedingungen) + ") "
    return con.execute(sql + "ORDER BY d.datum DESC, d.id DESC LIMIT 200", args).fetchall()


def kva_verknuepfen(con, auftrag_id, kva_id):
    """Verknüpft einen bestehenden KVA. Gibt True zurück, wenn der Kunde des KVA abweicht (Warnung)."""
    a = con.execute("SELECT * FROM auftraege WHERE id=?", (auftrag_id,)).fetchone()
    d = con.execute("SELECT * FROM dokumente WHERE id=? AND typ='kva'", (kva_id,)).fetchone()
    if not a or not d:
        raise EingabeFehler("Kostenvoranschlag nicht gefunden.")
    if a["kva_id"] == kva_id:
        return d["kunde_id"] != a["kunde_id"]
    if a["kva_id"]:
        raise EingabeFehler("Es ist bereits ein Kostenvoranschlag verknüpft. Bitte zuerst die Verknüpfung lösen.")
    andere = con.execute("SELECT auftragsnr FROM auftraege WHERE kva_id=? AND id<>?", (kva_id, auftrag_id)).fetchone()
    if andere:
        raise EingabeFehler(f"Dieser Kostenvoranschlag gehört bereits zu Auftrag {andere['auftragsnr']}.")
    con.execute("UPDATE auftraege SET kva_id=?, geaendert_am=? WHERE id=?", (kva_id, dbm.jetzt(), auftrag_id))
    dbm.protokollieren("auftrag_kva_verknuepft", "auftrag", auftrag_id, {"kva": kva_id, "nummer": d["nummer"]},
                       con=con)
    verlauf(con, auftrag_id, "KVA verknüpft", _kva_text(d))
    return d["kunde_id"] != a["kunde_id"]


def kva_loesen(con, auftrag_id):
    a = con.execute("SELECT * FROM auftraege WHERE id=?", (auftrag_id,)).fetchone()
    if not a or not a["kva_id"]:
        raise EingabeFehler("Es ist kein Kostenvoranschlag verknüpft.")
    d = con.execute("SELECT * FROM dokumente WHERE id=?", (a["kva_id"],)).fetchone()
    con.execute("UPDATE auftraege SET kva_id=NULL, geaendert_am=? WHERE id=?", (dbm.jetzt(), auftrag_id))
    dbm.protokollieren("auftrag_kva_geloest", "auftrag", auftrag_id, {"kva": a["kva_id"]}, con=con)
    verlauf(con, auftrag_id, "KVA-Verknüpfung gelöst", _kva_text(d) if d else None)


def kva_status_setzen(con, kva_id, status):
    if status not in KVA_STATUS:
        raise EingabeFehler("Unbekannter KVA-Status.")
    d = con.execute("SELECT * FROM dokumente WHERE id=? AND typ='kva'", (kva_id,)).fetchone()
    if not d:
        raise EingabeFehler("Kostenvoranschlag nicht gefunden.")
    con.execute("UPDATE dokumente SET kva_status=? WHERE id=?", (status, kva_id))
    dbm.aenderungen_erfassen(con, "dokument", kva_id, {"kva_status": d["kva_status"] or "offen"}, {"kva_status": status},
                             namen={"kva_status": "KVA-Status"})
    dbm.protokollieren("kva_status", "dokument", kva_id, {"status": status}, con=con)
    neue_rechnungen = []
    for a in con.execute("SELECT * FROM auftraege WHERE kva_id=?", (kva_id,)).fetchall():
        verlauf(con, a["id"], f"KVA {status}", _kva_text(d))
        if status == "angenommen" and a["kva_gebuehr"]:
            verlauf(con, a["id"], "KVA-Pauschale entfällt", f"{_euro(a['kva_gebuehr'])} wird mit der Reparatur verrechnet")
        if status == "abgelehnt" and a["kva_gebuehr"] and a["auftragsart"] != "garantie":
            did, neu = rechnung_erstellen(con, a["id"])  # Rechnungsentwurf über die fällige Pauschale vorschlagen
            if neu:
                neue_rechnungen.append(did)
    return neue_rechnungen


def _euro(cent):
    from .hilfen import euro
    return euro(cent)


# ---------------------------------------------------------------------- KVA-Pauschale je Gerätetyp

SONSTIGE = "Sonstige Geräte"
KVA_ARTIKEL = "Kostenvoranschlag / Fehlerdiagnose"


def kva_gebuehren(einst):
    """Einstellung „Gerätetyp = Betrag“ je Zeile → Liste [(Gerätetyp, Cent brutto)] in der eingetragenen Reihenfolge."""
    from .hilfen import cent_aus_text
    liste = []
    for zeile in (einst.get("kva_gebuehren") or "").splitlines():
        if "=" not in zeile:
            continue
        typ, betrag = zeile.rsplit("=", 1)
        try:
            cent = cent_aus_text(betrag.strip(), None)
        except EingabeFehler:
            continue
        if typ.strip() and cent is not None:
            liste.append((typ.strip(), cent))
    return liste


def kva_gebuehr_fuer(einst, geraetetyp):
    """Standard-Pauschale für einen Gerätetyp (unbekannt → „Sonstige Geräte“, sonst 0)."""
    werte = dict(kva_gebuehren(einst))
    if geraetetyp in werte:
        return werte[geraetetyp]
    return werte.get(SONSTIGE, 0)


def kva_text(einst, kva_gebuehr):
    """Hinweis für den Annahmeschein (vor der Unterschrift sichtbar)."""
    if kva_gebuehr is None:
        return ""
    if not kva_gebuehr:
        return "Der Kostenvoranschlag ist für Sie kostenlos."
    from .hilfen import euro
    return (einst.get("annahme_kva_text") or "").replace("{KVA-Gebühr}", euro(kva_gebuehr))


def dokument_ereignis(con, dokument_id, ereignis_kva, ereignis_rechnung):
    """Ereignis (z. B. Versand) eines Dokuments im Verlauf der zugehörigen Aufträge vermerken."""
    d = con.execute("SELECT * FROM dokumente WHERE id=?", (dokument_id,)).fetchone()
    if not d:
        return
    for a in con.execute("SELECT id, kva_id FROM auftraege WHERE kva_id=? OR rechnung_id=?",
                         (dokument_id, dokument_id)).fetchall():
        text = ereignis_kva if a["kva_id"] == dokument_id else ereignis_rechnung
        if text:
            verlauf(con, a["id"], text, f"{d['nummer'] or 'Entwurf'}")


def betreff(a):
    teile = [a["geraet"] or "Reparatur"]
    if a["seriennummer"]:
        teile.append(f"SN/IMEI {a['seriennummer']}")
    return f"Reparatur {', '.join(teile)} (Auftrag {a['auftragsnr']})" if a["geraet"] else \
        f"Reparatur (Auftrag {a['auftragsnr']})"


def kva_erstellen(con, auftrag_id):
    """Legt einen KVA-Entwurf zum Auftrag an (oder gibt den vorhandenen zurück)."""
    a = con.execute("SELECT * FROM auftraege WHERE id=?", (auftrag_id,)).fetchone()
    if a["kva_id"]:
        return a["kva_id"]
    did = logik.neuer_entwurf(con, dbm.einstellungen(con), "kva", a["kunde_id"], betreff(a))
    if a["fehler"]:
        con.execute("UPDATE dokumente SET hinweise=? WHERE id=?", (f"Fehlerbeschreibung: {a['fehler']}", did))
    con.execute("UPDATE dokumente SET kva_status='offen' WHERE id=?", (did,))
    con.execute("UPDATE auftraege SET kva_id=?, geaendert_am=? WHERE id=?", (did, dbm.jetzt(), auftrag_id))
    verlauf(con, auftrag_id, "KVA erstellt und verknüpft", "neuer Entwurf")
    return did


def rechnung_erstellen(con, auftrag_id):
    """Legt den Rechnungsentwurf an – mit den Positionen des Kostenvoranschlags, falls vorhanden.

    Gibt (dokument_id, neu) zurück. Gibt es schon eine (nicht stornierte) Rechnung, wird diese verwendet.
    """
    a = con.execute("SELECT * FROM auftraege WHERE id=?", (auftrag_id,)).fetchone()
    if a["rechnung_id"]:
        r = con.execute("SELECT status FROM dokumente WHERE id=?", (a["rechnung_id"],)).fetchone()
        if r and r["status"] != "storniert":
            return a["rechnung_id"], False
    positionen = []
    einst = dbm.einstellungen(con)
    kva = con.execute("SELECT * FROM dokumente WHERE id=?", (a["kva_id"],)).fetchone() if a["kva_id"] else None
    if kva and kva["kva_status"] == "abgelehnt" and a["kva_gebuehr"]:
        positionen = [kva_gebuehr_position(con, einst, a["kva_gebuehr"], kva, a)]
        art = "Entwurf über die KVA-Pauschale (KVA abgelehnt)"
    elif kva:
        positionen = con.execute("SELECT * FROM positionen WHERE dokument_id=? ORDER BY pos", (a["kva_id"],)).fetchall()
        art = "Entwurf mit Positionen aus dem KVA"
    did = logik.neuer_entwurf(con, einst, "rechnung", a["kunde_id"], betreff(a), positionen,
                              leistungsdatum=date.today().isoformat())
    con.execute("UPDATE auftraege SET rechnung_id=?, geaendert_am=? WHERE id=?", (did, dbm.jetzt(), auftrag_id))
    verlauf(con, auftrag_id, "Rechnung erstellt", art if positionen else "leerer Rechnungsentwurf")
    from .leihgeraete import fuer_auftragsrechnung
    fuer_auftragsrechnung(con, auftrag_id, did)  # Leihgebühr/Schäden zurückgenommener Leihgeräte
    return did, True


def kva_artikel(con, einst):
    """Leistung „Kostenvoranschlag / Fehlerdiagnose“ im Katalog (wird bei Bedarf angelegt). Gibt die ID zurück."""
    a = con.execute("SELECT id FROM artikel WHERE lower(name)=lower(?)", (KVA_ARTIKEL,)).fetchone()
    if a:
        return a["id"]
    cur = con.execute("INSERT INTO artikel (name, beschreibung, leistungsart, typ, einheit, preis, teilekosten, "
                      "steuersatz, ek_unbekannt, erstellt_am, geaendert_am) VALUES (?,?,?,'leistung','pauschal',0,0,?,1,?,?)",
                      (KVA_ARTIKEL, "Pauschale für Fehlerdiagnose und Kostenvoranschlag; wird bei Annahme des KVA "
                                    "verrechnet", "Sonstiges", float(einst.get("regel_steuersatz") or 19),
                       dbm.jetzt(), dbm.jetzt()))
    dbm.ereignis_erfassen(con, "artikel", cur.lastrowid, "angelegt", "automatisch für die KVA-Pauschale")
    return cur.lastrowid


def kva_gebuehr_position(con, einst, brutto, kva, a):
    """Rechnungsposition über die KVA-Pauschale (der Betrag auf dem Annahmeschein ist brutto)."""
    satz = float(einst.get("regel_steuersatz") or 19)
    netto = int(round(brutto * 100 / (100 + satz))) if einst["steuer_modus"] == "regel" else brutto
    return {"artikel_id": kva_artikel(con, einst),
            "bezeichnung": f"{KVA_ARTIKEL} – Gerät: {a['geraet'] or 'ohne Angabe'}",
            "beschreibung": f"Kostenvoranschlag {kva['nummer'] or ''} wurde nicht angenommen; Pauschale laut "
                            f"Annahmeschein (Auftrag {a['auftragsnr']})", "menge": 1, "einheit": "pauschal",
            "einzelpreis": netto, "teilekosten": 0, "steuersatz": satz, "leistungsart": "Sonstiges"}


def status_setzen(con, auftrag_id, status, vor_id=None):
    """Verschiebt einen Auftrag in eine Spalte (optional vor eine andere Karte).

    Gibt die ID eines neu erzeugten Rechnungsentwurfs zurück (nur beim Wechsel nach „erledigt“).
    """
    if status not in TAFEL:
        raise EingabeFehler("Unbekannter Status.")
    a = con.execute("SELECT * FROM auftraege WHERE id=?", (auftrag_id,)).fetchone()
    if not a:
        raise EingabeFehler("Auftrag nicht gefunden.")
    from .benachrichtigung import vorschlagen
    if status == "wartet_teil":
        status = "in_arbeit"
        if not a["wartet_teil_seit"]:
            con.execute("UPDATE auftraege SET wartet_teil_seit=? WHERE id=?", (dbm.jetzt(), auftrag_id))
            verlauf(con, auftrag_id, "Wartet auf Ersatzteil", a["teil_info"] or None)
            vorschlagen(con, auftrag_id, "wartet_teil")
    elif a["wartet_teil_seit"]:
        con.execute("UPDATE auftraege SET wartet_teil_seit=NULL WHERE id=?", (auftrag_id,))
        verlauf(con, auftrag_id, "Ersatzteil da – Warten beendet", None)
    # Reihenfolge: vor die Karte vor_id, sonst ans Ende der Spalte
    if vor_id:
        ziel = con.execute("SELECT reihenfolge FROM auftraege WHERE id=? AND status=?", (vor_id, status)).fetchone()
    else:
        ziel = None
    if ziel:
        davor = con.execute("SELECT MAX(reihenfolge) FROM auftraege WHERE status=? AND reihenfolge<? AND id<>?",
                            (status, ziel["reihenfolge"], auftrag_id)).fetchone()[0]
        reihenfolge = ((davor if davor is not None else ziel["reihenfolge"] - 1) + ziel["reihenfolge"]) / 2
    else:
        reihenfolge = (con.execute("SELECT MAX(reihenfolge) FROM auftraege WHERE status=? AND id<>?",
                                   (status, auftrag_id)).fetchone()[0] or 0) + 1
    felder = {"status": status, "reihenfolge": reihenfolge, "geaendert_am": dbm.jetzt()}
    if status == "in_arbeit" and not a["begonnen_am"]:
        felder["begonnen_am"] = dbm.jetzt()
    felder["erledigt_am"] = dbm.jetzt() if status == "erledigt" else None
    con.execute(f"UPDATE auftraege SET {', '.join(f'{k}=?' for k in felder)} WHERE id=?",
                (*felder.values(), auftrag_id))
    neue_rechnung = None
    if status != a["status"]:
        dbm.protokollieren("auftrag_status", "auftrag", auftrag_id, {"von": a["status"], "nach": status}, con=con)
        verlauf(con, auftrag_id, "Status geändert", f"{STATUS[a['status']]} → {STATUS[status]}")
        from .leihgeraete import interner_auftrag_erledigt, ist_intern
        if status == "erledigt":
            from .annahme import zugang_loeschen
            from .lager import auftrag_erledigt
            zugang_loeschen(con, auftrag_id, "Auftrag abgeschlossen (automatisch)")
            auftrag_erledigt(con, auftrag_id)  # reserviertes Material ausbuchen
        if status == "erledigt" and ist_intern(con, a["kunde_id"]):
            interner_auftrag_erledigt(con, auftrag_id)  # interne Reparatur eines Leihgeräts: keine Rechnung
        elif status == "erledigt" and a["auftragsart"] == "garantie":
            verlauf(con, auftrag_id, "Garantiefall erledigt – keine Rechnung",
                    "kostenlos; interne Kosten werden am Auftrag erfasst")
        elif status == "erledigt":
            did, neu = rechnung_erstellen(con, auftrag_id)
            if neu:
                neue_rechnung = did
        if status == "erledigt":
            vorschlagen(con, auftrag_id, "fertig")
    return neue_rechnung
