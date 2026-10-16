"""Mahnwesen: Zahlungserinnerung (ohne Gebühr), 1. und 2. Mahnung, optional Verzugszinsen.

Mahnungen erhalten eine fortlaufende Nummer (eigener Nummernkreis), werden als PDF erzeugt und – wie Rechnungen –
unverändert mit SHA-256-Prüfsumme archiviert (PDF + Daten als JSON).
"""
import hashlib
import json
from datetime import date, timedelta
from pathlib import Path

from . import db as dbm
from . import zahlungen as zlg
from .hilfen import (EingabeFehler, anrede_brief, anschrift_zeilen, datum_de, euro, kunde_name, platzhalter_ersetzen,
                     sicherer_dateiname)

TITEL = {0: "Zahlungserinnerung", 1: "1. Mahnung", 2: "2. Mahnung"}


def _d(text):
    return date.fromisoformat(text[:10])


def faellig_ab(dok, stufe, letzte, einst):
    """Ab welchem Tag ist die nächste Stufe fällig? (None = keine weitere Stufe)"""
    if stufe == 0:
        return _d(dok["faellig_am"]) + timedelta(days=int(einst.get("mahn_erinnerung_tage") or 0))
    if stufe in (1, 2) and letzte:
        tage = int(einst.get("mahn_stufe1_tage" if stufe == 1 else "mahn_stufe2_tage") or 0)
        return _d(letzte["frist_bis"]) + timedelta(days=tage)
    return None


def naechste_stufe(con, dok, einst=None, heute=None):
    """(stufe, fällig_ab) der nächsten Mahnstufe oder (None, None)."""
    einst = einst or dbm.einstellungen(con)
    s = zlg.stand(con, dok, heute)
    if s["status"] in ("bezahlt", "storniert", "erstattung") or s["offen"] <= 0 or not dok["faellig_am"]:
        return None, None
    letzte = s["letzte_mahnung"]
    stufe = 0 if letzte is None else letzte["stufe"] + 1
    if stufe > 2:
        return None, None
    return stufe, faellig_ab(dok, stufe, letzte, einst)


def vorschlaege(con, heute=None):
    """Rechnungen, bei denen die nächste Mahnstufe fällig ist."""
    heute_d = _d(heute or date.today().isoformat())
    einst = dbm.einstellungen(con)
    ergebnis = []
    for p in zlg.offene_posten(con, nur_ueberfaellig=True, heute=heute):
        stufe, ab = naechste_stufe(con, p["d"], einst, heute)
        if stufe is not None and ab and ab <= heute_d:
            ergebnis.append({**p, "stufe": stufe, "titel": TITEL[stufe], "faellig_ab": ab.isoformat()})
    return ergebnis


def ausgeschoepft(con, heute=None):
    """Rechnungen nach der 2. Mahnung, deren Frist abgelaufen ist (Inkasso / Mahnbescheid prüfen)."""
    heute = heute or date.today().isoformat()
    return [p for p in zlg.offene_posten(con, nur_ueberfaellig=True, heute=heute)
            if p["s"]["mahnstufe"] == 2 and p["s"]["letzte_mahnung"]["frist_bis"] < heute]


def zinsen_berechnen(con, dok, kunde, offen, bis, einst):
    """Verzugszinsen (§ 288 BGB): (Basiszinssatz + Aufschlag) p. a. auf den offenen Rechnungsbetrag.

    Beginn je nach Einstellung: Tag nach Fälligkeit oder Datum der 1. Mahnung. Gibt (Cent, Text) zurück.
    """
    if not einst.get("zinsen_aktiv"):
        return 0, ""
    try:
        basis = float(str(einst.get("basiszinssatz") or "").replace(",", "."))
    except ValueError:
        return 0, ""
    if str(einst.get("basiszinssatz") or "").strip() == "":
        return 0, ""
    firma = bool(kunde and kunde["typ"] == "firma")
    satz = basis + float(einst.get("zinsen_aufschlag_firma" if firma else "zinsen_aufschlag_privat") or 0)
    if einst.get("zinsen_ab") == "faelligkeit":
        start = _d(dok["faellig_am"]) + timedelta(days=1)
    else:
        erste = con.execute("SELECT datum FROM mahnungen WHERE dokument_id=? AND stufe=1", (dok["id"],)).fetchone()
        if not erste:
            return 0, ""
        start = _d(erste["datum"])
    tage = (_d(bis) - start).days
    if tage <= 0 or offen <= 0 or satz <= 0:
        return 0, ""
    betrag = int(round(offen * satz / 100 * tage / 365))
    return betrag, (f"Verzugszinsen {satz:.2f} % p. a. ({basis:.2f} % Basiszinssatz + "
                    f"{satz - basis:.0f} Prozentpunkte) auf {euro(offen)} vom {datum_de(start.isoformat())} bis "
                    f"{datum_de(bis)} ({tage} Tage)").replace(".", ",", 2)


def erstellen(con, dok_id, stufe, daten_dir, heute=None):
    """Erzeugt die Mahnung der angegebenen Stufe (nur die jeweils nächste Stufe). Gibt die ID zurück."""
    from .logik import naechste_nummer
    from .pdf import pdf_erzeugen
    einst = dbm.einstellungen(con)
    heute = heute or date.today().isoformat()
    with dbm.Transaktion(con):
        dok = con.execute("SELECT * FROM dokumente WHERE id=?", (dok_id,)).fetchone()
        if not dok or dok["typ"] != "rechnung" or dok["status"] != "festgeschrieben":
            raise EingabeFehler("Mahnungen sind nur für festgeschriebene, nicht stornierte Rechnungen möglich.")
        naechste, _ = naechste_stufe(con, dok, einst, heute)
        if naechste is None:
            raise EingabeFehler("Für diese Rechnung ist keine (weitere) Mahnung möglich – sie ist bezahlt oder "
                                "bereits zweimal gemahnt.")
        if stufe != naechste:
            raise EingabeFehler(f"Als Nächstes ist die {TITEL[naechste]} dran – Stufen können nicht übersprungen werden.")
        s = zlg.stand(con, dok, heute)
        kunde = con.execute("SELECT * FROM kunden WHERE id=?", (dok["kunde_id"],)).fetchone()
        gebuehr = 0 if stufe == 0 else int(einst.get("mahngebuehr_cent" if stufe == 1 else "mahngebuehr_2_cent") or 0)
        gebuehren_vorher = s["gebuehren_offen"] - (s["letzte_mahnung"]["zinsen"] if s["letzte_mahnung"] else 0)
        gebuehren_vorher = max(0, gebuehren_vorher)
        zinsen, zinstext = zinsen_berechnen(con, dok, kunde, s["offen"], heute, einst)
        if stufe == 1 and einst.get("zinsen_ab") != "faelligkeit":
            zinsen, zinstext = 0, ""  # Zinsen laufen erst ab dieser 1. Mahnung
        gesamt = s["offen"] + gebuehren_vorher + gebuehr + zinsen
        frist = (_d(heute) + timedelta(days=int(einst.get("mahn_frist_tage") or 10))).isoformat()
        nummer = naechste_nummer(con, einst.get("praefix_mahnung") or "MA", int(heute[:4]), einst["nummern_format"])
        rech_snap = json.loads(dok["snapshot_json"] or "{}")
        positionen = [{"bezeichnung": f"Offener Betrag aus Rechnung {dok['nummer']} vom {datum_de(dok['datum'])}",
                       "beschreibung": f"Rechnungsbetrag {euro(s['forderung'])}"
                                       + (f", bereits gezahlt {euro(s['bezahlt'])}" if s["bezahlt"] else "")
                                       + f", fällig seit {datum_de(dok['faellig_am'])}",
                       "betrag": s["offen"]}]
        if gebuehren_vorher:
            positionen.append({"bezeichnung": "Mahngebühren aus früheren Mahnungen", "beschreibung": "",
                               "betrag": gebuehren_vorher})
        if gebuehr:
            positionen.append({"bezeichnung": f"Mahngebühr {TITEL[stufe]}", "beschreibung": "", "betrag": gebuehr})
        if zinsen:
            positionen.append({"bezeichnung": "Verzugszinsen", "beschreibung": zinstext, "betrag": zinsen})
        werte = {"anrede_brief": anrede_brief(kunde), "kunde_name": kunde_name(kunde), "titel": TITEL[stufe],
                 "rechnung_nummer": dok["nummer"], "rechnung_datum": datum_de(dok["datum"]),
                 "rechnung_betrag": euro(s["forderung"]), "faellig_am": datum_de(dok["faellig_am"]),
                 "offen_rechnung": euro(s["offen"]), "gebuehr": euro(gebuehr), "zinsen": euro(zinsen),
                 "gesamt": euro(gesamt), "frist_bis": datum_de(frist), "nummer": nummer, "datum": datum_de(heute),
                 "firma_name": einst.get("firma_name", ""), "inhaber": einst.get("inhaber", "")}
        from .logik import FIRMA_FELDER, LAYOUT_FELDER
        text = platzhalter_ersetzen(einst.get(f"mahn_text_{stufe}") or "", werte)
        gruss = text.find("Mit freundlichen Grüßen")  # Grußformel unter die Aufstellung setzen
        einleitung, schluss = (text[:gruss].rstrip(), text[gruss:]) if gruss > 0 else (text, "")
        kunde_snap = rech_snap.get("kunde") or {}
        if kunde and not kunde["anonymisiert_am"]:
            kunde_snap = {"kundennr": kunde["kundennr"], "name": kunde_name(kunde),
                          "anschrift": anschrift_zeilen(kunde), "ust_idnr": kunde["ust_idnr"] or "", "typ": kunde["typ"]}
        snap = {
            "version": 1, "typ": "mahnung", "titel": TITEL[stufe], "stufe": stufe, "nummer": nummer, "datum": heute,
            "faellig_am": frist, "betreff": f"{TITEL[stufe]} zu Rechnung {dok['nummer']}",
            "einleitung": einleitung, "schlusstext": schluss, "hinweise": "", "steuer_modus": "kleinunternehmer", "kleinunternehmer_hinweis": "",
            "zahlungsarten_text": einst.get("zahlungsarten_text", ""), "verwendungszweck": dok["nummer"],
            "bezug": {"nummer": dok["nummer"], "datum": dok["datum"]}, "kunde": kunde_snap,
            "firma": {k: einst.get(k, "") for k in FIRMA_FELDER}, "layout": {k: einst.get(k) for k in LAYOUT_FELDER},
            "positionen": [{"pos": i, "bezeichnung": p["bezeichnung"], "beschreibung": p["beschreibung"], "menge": 1,
                            "einheit": "", "einzelpreis": p["betrag"], "steuersatz": 0, "betrag": p["betrag"]}
                           for i, p in enumerate(positionen, 1)],
            "summen": {"netto": gesamt, "steuer": 0, "brutto": gesamt, "gruppen": []},
        }
        pdf = pdf_erzeugen(snap, daten_dir=daten_dir)
        rel = Path("dokumente") / heute[:4] / f"{sicherer_dateiname(nummer)}.pdf"
        ziel = Path(daten_dir) / rel
        ziel.parent.mkdir(parents=True, exist_ok=True)
        ziel.write_bytes(pdf)
        daten = json.dumps(snap, ensure_ascii=False, sort_keys=True, indent=1).encode("utf-8")
        ziel.with_suffix(".json").write_bytes(daten)
        cur = con.execute(
            "INSERT INTO mahnungen (dokument_id, stufe, nummer, datum, frist_bis, offen_rechnung, gebuehr, "
            "gebuehren_vorher, zinsen, gesamt, snapshot_json, pdf_pfad, pdf_sha256, snapshot_sha256, erstellt_am, "
            "benutzer) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (dok_id, stufe, nummer, heute, frist, s["offen"], gebuehr, gebuehren_vorher, zinsen, gesamt,
             json.dumps(snap, ensure_ascii=False), rel.as_posix(), hashlib.sha256(pdf).hexdigest(),
             hashlib.sha256(daten).hexdigest(), dbm.jetzt_berlin(), dbm.aktueller_benutzer()))
        dbm.ereignis_erfassen(con, "dokument", dok_id, TITEL[stufe] + " erstellt",
                              f"{nummer}: {euro(gesamt)}, Frist bis {datum_de(frist)}")
        dbm.protokollieren("mahnung_erstellt", "dokument", dok_id, {"mahnung": nummer, "stufe": stufe,
                                                                    "gesamt": gesamt}, con=con)
        zlg._auftrag_verlauf(con, dok_id, TITEL[stufe] + " erstellt", f"{nummer} zu {dok['nummer']}: {euro(gesamt)}")
    return cur.lastrowid


def versand_vermerken(con, mahnung_id, art):
    m = con.execute("SELECT * FROM mahnungen WHERE id=?", (mahnung_id,)).fetchone()
    con.execute("UPDATE mahnungen SET versendet_am=?, versandart=? WHERE id=?", (dbm.jetzt_berlin(), art, mahnung_id))
    dbm.ereignis_erfassen(con, "dokument", m["dokument_id"], "Mahnung versendet",
                          f"{m['nummer']} ({'E-Mail' if art == 'email' else 'Post/ausgedruckt'})")


def gebuehren_erlassen(con, mahnung_id, grund):
    grund = (grund or "").strip()
    if len(grund) < 3:
        raise EingabeFehler("Bitte einen Grund angeben.")
    m = con.execute("SELECT * FROM mahnungen WHERE id=?", (mahnung_id,)).fetchone()
    if not m or m["erledigt_am"]:
        raise EingabeFehler("Mahnung nicht gefunden oder bereits erledigt.")
    con.execute("UPDATE mahnungen SET erledigt_am=? WHERE id=?", (dbm.jetzt_berlin(), mahnung_id))
    dbm.ereignis_erfassen(con, "dokument", m["dokument_id"], "Mahngebühren/Zinsen erlassen",
                          f"{m['nummer']}: {euro(m['gebuehr'] + m['zinsen'])} – {grund}")
    dbm.protokollieren("mahngebuehr_erlassen", "dokument", m["dokument_id"], {"mahnung": m["nummer"], "grund": grund},
                       con=con)


def email_texte(con, m):
    einst = dbm.einstellungen(con)
    dok = con.execute("SELECT * FROM dokumente WHERE id=?", (m["dokument_id"],)).fetchone()
    kunde = con.execute("SELECT * FROM kunden WHERE id=?", (dok["kunde_id"],)).fetchone()
    werte = {"anrede_brief": anrede_brief(kunde), "titel": TITEL[m["stufe"]], "rechnung_nummer": dok["nummer"],
             "gesamt": euro(m["gesamt"]), "frist_bis": datum_de(m["frist_bis"]), "nummer": m["nummer"],
             "firma_name": einst.get("firma_name", ""), "inhaber": einst.get("inhaber", "")}
    return (platzhalter_ersetzen(einst.get("mahn_email_betreff") or "", werte),
            platzhalter_ersetzen(einst.get("mahn_email_text") or "", werte), (kunde["email"] or "") if kunde else "")
