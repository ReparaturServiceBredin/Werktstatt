"""Annahme- und Abholschein mit digitaler Unterschrift, Gerätezugang (verschlüsselt) und Handy-Zugang per QR-Code.

Unterschriebene Scheine werden als PDF unverändert archiviert (Daten/dokumente/auftraege/<Jahr>/…) und mit
SHA-256 in der Tabelle auftrag_belege festgehalten; die Tabelle ist per Trigger gegen Ändern/Löschen geschützt.
"""
import base64
import hashlib
import io
import json
import secrets
import socket
from datetime import datetime, timedelta
from pathlib import Path

from . import db as dbm
from .hilfen import EingabeFehler, euro, kunde_name, sicherer_dateiname

ARTEN = {"annahme": "Annahmeschein", "abholung": "Abholschein"}
KUERZEL = {"annahme": "AN", "abholung": "AB"}
ZWECKE = {"fotos": "Fotos aufnehmen", "annahme": "Annahmeschein unterschreiben",
          "abholung": "Abholschein unterschreiben"}
ZUGANG_ARTEN = {"": "nicht angegeben", "pin": "PIN", "passwort": "Passwort", "muster": "Entsperrmuster",
                "telefonisch": "Kunde gibt den Zugang bei Bedarf telefonisch durch",
                "keiner": "keine Sperre / kein Zugang nötig"}
MIT_GEHEIMNIS = ("pin", "passwort", "muster")
TOKEN_MINUTEN = 30


# ---------------------------------------------------------------------- Zubehör-Checkliste

def zubehoer_vorlagen(einst):
    return [z.strip() for z in (einst.get("annahme_zubehoer") or "").splitlines() if z.strip()]


def zubehoer_aufteilen(text, vorlagen):
    """„Ladekabel, Hülle, rote Tasche“ → ({Ladekabel, Hülle}, "rote Tasche") anhand der Checkliste."""
    teile = [t.strip() for t in (text or "").split(",") if t.strip()]
    klein = {v.lower(): v for v in vorlagen}
    gewaehlt = {klein[t.lower()] for t in teile if t.lower() in klein}
    rest = ", ".join(t for t in teile if t.lower() not in klein)
    return gewaehlt, rest


def zubehoer_zusammen(gewaehlt, sonstiges, vorlagen):
    reihe = [v for v in vorlagen if v in gewaehlt]
    if sonstiges and sonstiges.strip():
        reihe.append(sonstiges.strip())
    return ", ".join(reihe)


# ---------------------------------------------------------------------- Gerätezugang

def zugang_setzen(con, auftrag_id, art, wert="", loeschen=False):
    """Zugangsart speichern; ein neuer Wert wird verschlüsselt abgelegt. Muss in einer Transaktion laufen."""
    from .auftraege import verlauf
    from .sicherheit import verschluesseln
    if art not in ZUGANG_ARTEN:
        raise EingabeFehler("Unbekannte Art des Gerätezugangs.")
    a = con.execute("SELECT * FROM auftraege WHERE id=?", (auftrag_id,)).fetchone()
    wert = (wert or "").strip()
    if wert and art not in MIT_GEHEIMNIS:
        raise EingabeFehler("Zugangsdaten bitte nur bei PIN, Passwort oder Muster eintragen.")
    if wert and a["status"] == "erledigt":
        raise EingabeFehler("Der Auftrag ist erledigt – Zugangsdaten werden nicht mehr gespeichert.")
    if art != (a["zugang_art"] or ""):
        con.execute("UPDATE auftraege SET zugang_art=? WHERE id=?", (art or None, auftrag_id))
        verlauf(con, auftrag_id, "Gerätezugang: Art geändert", ZUGANG_ARTEN[art])
    if wert:
        con.execute("UPDATE auftraege SET zugang_geheim=?, zugang_geloescht_am=NULL WHERE id=?",
                    (verschluesseln(wert), auftrag_id))
        verlauf(con, auftrag_id, "Gerätezugang hinterlegt", f"{ZUGANG_ARTEN[art]} (verschlüsselt gespeichert)")
        dbm.protokollieren("geraetezugang_gespeichert", "auftrag", auftrag_id, {"art": art}, con=con)
    elif a["zugang_geheim"] and (loeschen or art not in MIT_GEHEIMNIS):
        zugang_loeschen(con, auftrag_id, "manuell gelöscht" if loeschen else "Zugangsart geändert")


def zugang_loeschen(con, auftrag_id, grund, frist=None):
    """Gerätezugangsdaten endgültig löschen (Feld geleert, secure_delete überschreibt die alten Seiten) und im
    Löschprotokoll vermerken – ohne die Daten selbst."""
    from .auftraege import verlauf
    from .datenschutz import _protokoll
    a = con.execute("SELECT zugang_geheim, auftragsnr FROM auftraege WHERE id=?", (auftrag_id,)).fetchone()
    if not a or not a["zugang_geheim"]:
        return False
    con.execute("UPDATE auftraege SET zugang_geheim=NULL, zugang_geloescht_am=? WHERE id=?",
                (dbm.jetzt_berlin(), auftrag_id))
    verlauf(con, auftrag_id, "Gerätezugang gelöscht", grund)
    dbm.protokollieren("geraetezugang_geloescht", "auftrag", auftrag_id, {"grund": grund}, con=con)
    _protokoll(con, grund, f"Auftrag {a['auftragsnr']}", ["Gerätezugangsdaten (PIN/Passwort/Muster)"], [], None,
               frist or "sofort bei Abholung, Abschluss oder Stornierung")
    return True


def zugang_anzeigen(con, auftrag_id):
    """Entschlüsselt die Zugangsdaten und vermerkt den Zugriff im Verlauf/Protokoll."""
    from .auftraege import verlauf
    from .sicherheit import entschluesseln
    a = con.execute("SELECT zugang_geheim, zugang_art FROM auftraege WHERE id=?", (auftrag_id,)).fetchone()
    if not a or not a["zugang_geheim"]:
        return ""
    with dbm.Transaktion(con):
        verlauf(con, auftrag_id, "Gerätezugang angezeigt", ZUGANG_ARTEN.get(a["zugang_art"] or "", ""))
        dbm.protokollieren("geraetezugang_angezeigt", "auftrag", auftrag_id, con=con)
    return entschluesseln(a["zugang_geheim"])


def zugang_text(a):
    art = a["zugang_art"] or ""
    text = ZUGANG_ARTEN.get(art, art)
    if art in MIT_GEHEIMNIS:
        if a["zugang_geheim"]:
            text += " – hinterlegt (verschlüsselt, wird nach Abschluss automatisch gelöscht)"
        elif a["zugang_geloescht_am"]:
            text += " – bereits gelöscht"
        else:
            text += " – nicht hinterlegt"
    return text


# ---------------------------------------------------------------------- Unterschrift

def unterschrift_pruefen(daten_url):
    """data:image/png;base64,… → PNG-Bytes. Leere Unterschriften werden abgelehnt."""
    from PIL import Image
    praefix = "data:image/png;base64,"
    if not daten_url or not daten_url.startswith(praefix):
        raise EingabeFehler("Bitte unterschreiben Sie im Unterschriftsfeld.")
    try:
        png = base64.b64decode(daten_url[len(praefix):], validate=True)
    except ValueError:
        raise EingabeFehler("Die Unterschrift konnte nicht gelesen werden. Bitte erneut unterschreiben.")
    if len(png) > 3 * 1024 * 1024 or not png.startswith(b"\x89PNG"):
        raise EingabeFehler("Die Unterschrift konnte nicht gelesen werden. Bitte erneut unterschreiben.")
    try:
        bild = Image.open(io.BytesIO(png))
        bild.load()
    except Exception:
        raise EingabeFehler("Die Unterschrift konnte nicht gelesen werden. Bitte erneut unterschreiben.")
    weiss = Image.new("RGBA", bild.size, (255, 255, 255, 255))
    weiss.alpha_composite(bild.convert("RGBA"))
    grau = weiss.convert("L").point(lambda v: 255 if v < 200 else 0)
    box = grau.getbbox()
    if not box or (box[2] - box[0] < 25 and box[3] - box[1] < 25):
        raise EingabeFehler("Das Unterschriftsfeld ist leer. Bitte unterschreiben.")
    return png


# ---------------------------------------------------------------------- Belege

def _firma(einst):
    return {"name": einst.get("firma_name") or "", "inhaber": einst.get("inhaber") or "",
            "strasse": einst.get("strasse") or "", "plz_ort": " ".join(x for x in [einst.get("plz"), einst.get("ort")]
                                                                      if x),
            "telefon": einst.get("telefon") or "", "email": einst.get("email") or "", "web": einst.get("web") or ""}


def snapshot(con, auftrag_id, art):
    """Alle Angaben, die auf dem Schein stehen (wird beim Unterschreiben eingefroren)."""
    a = con.execute("SELECT * FROM auftraege WHERE id=?", (auftrag_id,)).fetchone()
    if not a:
        raise EingabeFehler("Auftrag nicht gefunden.")
    k = con.execute("SELECT * FROM kunden WHERE id=?", (a["kunde_id"],)).fetchone()
    einst = dbm.einstellungen(con)
    vorlagen = zubehoer_vorlagen(einst)
    gewaehlt, sonstiges = zubehoer_aufteilen(a["zubehoer"], vorlagen)
    fotos = con.execute("SELECT id, kategorie, dateiname, sha256, pfad FROM auftrag_fotos WHERE auftrag_id=? "
                        "AND geloescht_am IS NULL AND kategorie IN (?, ?) ORDER BY hochgeladen_am, id",
                        (auftrag_id, "Geräteeingang", "Vorschaden" if art == "annahme" else "Geräteausgabe"))
    snap = {
        "art": art, "titel": ARTEN[art], "auftragsnr": a["auftragsnr"], "eingang_am": a["eingang_am"],
        "firma": _firma(einst),
        "kunde": {"name": kunde_name(k), "kundennr": k["kundennr"], "strasse": k["strasse"] or "",
                  "plz_ort": " ".join(x for x in [k["plz"], k["ort"]] if x), "telefon": k["telefon"] or "",
                  "email": k["email"] or ""},
        "geraet": a["geraet"] or "", "seriennummer": a["seriennummer"] or "", "leistungsart": a["leistungsart"] or "",
        "fehler": a["fehler"] or "", "zustand_eingang": a["zustand_eingang"] or "",
        "zubehoer": [{"name": v, "dabei": v in gewaehlt} for v in vorlagen], "zubehoer_sonstiges": sonstiges,
        "kosten_obergrenze": a["kosten_obergrenze"], "kva_gewuenscht": bool(a["kva_gewuenscht"]),
        "kva_gebuehr": a["kva_gebuehr"], "fertig_bis": a["fertig_bis"] or "",
        "kva_text": _kva_text(einst, a["kva_gebuehr"]),
        "zugang": zugang_text(a), "datenschutz": einst.get("annahme_datenschutz") or "",
        "abholbedingungen": einst.get("annahme_abholbedingungen") or "",
        "fotos": [dict(f) for f in fotos],
    }
    if art == "abholung":
        snap["erklaerung"] = einst.get("abholschein_text") or ""
        if a["rechnung_id"]:
            r = con.execute("SELECT * FROM dokumente WHERE id=?", (a["rechnung_id"],)).fetchone()
            if r and r["status"] != "entwurf":
                from .zahlungen import stand
                s = stand(con, r)
                snap["rechnung"] = {"nummer": r["nummer"], "datum": r["datum"], "betrag": r["summe_brutto"],
                                    "offen": s["offen"], "status": s["status_text"]}
        snap["garantie"] = garantie_info(con, a)
    return snap


def _kva_text(einst, kva_gebuehr):
    from .auftraege import kva_text
    return kva_text(einst, kva_gebuehr)


def garantie_info(con, a):
    """Platzhalter für Phase 5 (Garantie). Gibt Text oder leer zurück."""
    try:
        from .garantie import text_fuer_auftrag
    except ImportError:
        return ""
    return text_fuer_auftrag(con, a)


def _ordner(daten_dir, jahr):
    pfad = Path(daten_dir) / "dokumente" / "auftraege" / str(jahr)
    pfad.mkdir(parents=True, exist_ok=True)
    return pfad


def naechste_nummer(con, auftrag_id, art):
    a = con.execute("SELECT auftragsnr FROM auftraege WHERE id=?", (auftrag_id,)).fetchone()
    n = con.execute("SELECT COUNT(*) FROM auftrag_belege WHERE auftrag_id=? AND art=?", (auftrag_id, art)).fetchone()[0]
    return f"{a['auftragsnr']}-{KUERZEL[art]}{n + 1}"


def beleg_erstellen(con, auftrag_id, art, daten_url, unterzeichner, daten_dir, quelle="PC/Tablet", ip=None):
    """Unterschriebenen Schein erzeugen und archivieren. Muss in einer Transaktion laufen. Gibt die Beleg-ID zurück."""
    from . import annahme_pdf
    from .auftraege import verlauf
    if art not in ARTEN:
        raise EingabeFehler("Unbekannte Belegart.")
    png = unterschrift_pruefen(daten_url)
    unterzeichner = (unterzeichner or "").strip()
    if len(unterzeichner) < 2:
        raise EingabeFehler("Bitte den Namen der unterschreibenden Person angeben.")
    zeitpunkt = dbm.jetzt_berlin()
    snap = snapshot(con, auftrag_id, art)
    nummer = naechste_nummer(con, auftrag_id, art)
    snap.update({"nummer": nummer, "unterzeichner": unterzeichner, "unterschrieben_am": zeitpunkt, "quelle": quelle})
    pdf = annahme_pdf.erstellen(snap, daten_dir, dbm.einstellungen(con), unterschrift=png)
    ordner = _ordner(daten_dir, zeitpunkt[:4])
    pdf_datei = ordner / f"{sicherer_dateiname(nummer)}.pdf"
    if pdf_datei.exists():
        raise EingabeFehler("Für diese Nummer liegt bereits ein archiviertes PDF vor. Bitte den Vorgang wiederholen.")
    pdf_datei.write_bytes(pdf)
    (ordner / f"{sicherer_dateiname(nummer)}_unterschrift.png").write_bytes(png)
    snap_text = json.dumps(snap, ensure_ascii=False, sort_keys=True, indent=1)
    (ordner / f"{sicherer_dateiname(nummer)}.json").write_text(snap_text, encoding="utf-8")
    rel = pdf_datei.relative_to(Path(daten_dir)).as_posix()
    cur = con.execute(
        "INSERT INTO auftrag_belege (auftrag_id, art, nummer, unterzeichner, unterschrieben_am, unterschrift_sha256, "
        "quelle, ip, pdf_datei, pdf_sha256, snapshot, benutzer, erstellt_am) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (auftrag_id, art, nummer, unterzeichner, zeitpunkt, hashlib.sha256(png).hexdigest(), quelle, ip, rel,
         hashlib.sha256(pdf).hexdigest(), snap_text, dbm.aktueller_benutzer(), zeitpunkt))
    verlauf(con, auftrag_id, f"{ARTEN[art]} unterschrieben", f"{nummer} von {unterzeichner} ({quelle})")
    dbm.protokollieren("beleg_unterschrieben", "auftrag", auftrag_id,
                       {"nummer": nummer, "art": art, "pdf_sha256": hashlib.sha256(pdf).hexdigest()}, con=con)
    if art == "abholung":
        con.execute("UPDATE auftraege SET abgeholt_am=COALESCE(abgeholt_am, ?) WHERE id=?", (zeitpunkt, auftrag_id))
        from .garantie import ende_speichern
        ende_speichern(con, auftrag_id)
        zugang_loeschen(con, auftrag_id, "Gerät abgeholt")
        from .benachrichtigung import verwerfen
        for b in con.execute("SELECT id FROM benachrichtigungen WHERE auftrag_id=? AND anlass='erinnerung' "
                             "AND status='offen'", (auftrag_id,)).fetchall():
            verwerfen(con, b["id"], "Gerät wurde abgeholt")
    return cur.lastrowid


def belege(con, auftrag_id):
    return con.execute("SELECT * FROM auftrag_belege WHERE auftrag_id=? ORDER BY id", (auftrag_id,)).fetchall()


def beleg_pdf(daten_dir, beleg):
    """Archiviertes PDF lesen; (bytes, ok) – ok=False, wenn die Prüfsumme nicht mehr stimmt."""
    pfad = Path(daten_dir) / beleg["pdf_datei"]
    if not pfad.is_file():
        return None, False
    daten = pfad.read_bytes()
    return daten, hashlib.sha256(daten).hexdigest() == beleg["pdf_sha256"]


def geaendert_seit_unterschrift(con, auftrag_id):
    """True, wenn sich die Angaben seit dem letzten Annahmeschein geändert haben."""
    letzter = con.execute("SELECT snapshot FROM auftrag_belege WHERE auftrag_id=? AND art='annahme' "
                          "ORDER BY id DESC LIMIT 1", (auftrag_id,)).fetchone()
    if not letzter:
        return False
    alt = json.loads(letzter["snapshot"])
    neu = snapshot(con, auftrag_id, "annahme")
    felder = ("geraet", "seriennummer", "fehler", "zustand_eingang", "zubehoer", "zubehoer_sonstiges",
              "kosten_obergrenze", "kva_gewuenscht", "kva_gebuehr", "fertig_bis", "kunde")
    return any(alt.get(f) != neu.get(f) for f in felder)


# ---------------------------------------------------------------------- Handy (QR-Code)

def _jetzt():
    return datetime.fromisoformat(dbm.jetzt_berlin())


def token_erstellen(con, auftrag_id, zweck, minuten=TOKEN_MINUTEN):
    if zweck not in ZWECKE:
        raise EingabeFehler("Unbekannter Zweck.")
    token = secrets.token_urlsafe(24)
    jetzt = _jetzt()
    con.execute("INSERT INTO mobil_zugaenge (token, auftrag_id, zweck, erstellt_am, gueltig_bis, benutzer) "
                "VALUES (?,?,?,?,?,?)", (token, auftrag_id, zweck, jetzt.isoformat(timespec="seconds"),
                                         (jetzt + timedelta(minutes=minuten)).isoformat(timespec="seconds"),
                                         dbm.aktueller_benutzer()))
    return token


def token_pruefen(con, token):
    """Gültigen Handy-Zugang laden (oder None). Unterschrift-Zugänge gelten nur einmal."""
    if not token or len(token) > 64:
        return None
    z = con.execute("SELECT * FROM mobil_zugaenge WHERE token=?", (token,)).fetchone()
    if not z or datetime.fromisoformat(z["gueltig_bis"]) < _jetzt():
        return None
    if z["zweck"] != "fotos" and z["benutzt_am"]:
        return None
    return z


def token_benutzt(con, token):
    con.execute("UPDATE mobil_zugaenge SET benutzt_am=? WHERE token=?", (dbm.jetzt_berlin(), token))


def tokens_aufraeumen(con):
    grenze = (_jetzt() - timedelta(days=1)).isoformat(timespec="seconds")
    con.execute("DELETE FROM mobil_zugaenge WHERE gueltig_bis < ?", (grenze,))


def netz_adresse():
    """IP-Adresse dieses PCs im lokalen Netz (ohne Daten zu senden)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
        finally:
            s.close()
    except OSError:
        return "127.0.0.1"


def basis_url(einst, port):
    fest = (einst.get("handy_adresse") or "").strip().rstrip("/")
    if fest:
        return fest if fest.startswith("http") else f"http://{fest}"
    return f"http://{netz_adresse()}:{port}"


def qr_svg(text, groesse=240):
    """QR-Code als SVG (ReportLab, ohne zusätzliche Bibliothek)."""
    from reportlab.graphics import renderSVG
    from reportlab.graphics.barcode.qr import QrCodeWidget
    from reportlab.graphics.shapes import Drawing
    qr = QrCodeWidget(text, barLevel="M")
    x1, y1, x2, y2 = qr.getBounds()
    d = Drawing(groesse, groesse, transform=[groesse / (x2 - x1), 0, 0, groesse / (y2 - y1), 0, 0])
    d.add(qr)
    svg = renderSVG.drawToString(d)
    return svg[svg.find("<svg"):]


def betrag_text(cent, leer="–"):
    return euro(cent) if cent else leer
