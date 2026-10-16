"""Alle Seiten der Weboberfläche."""
import hashlib
import io
import json
import re
from datetime import date
from pathlib import Path

from flask import (Blueprint, abort, current_app, flash, g, jsonify, redirect, render_template, request, send_file,
                   session, url_for)
from markupsafe import Markup
from PIL import Image
from werkzeug.security import check_password_hash, generate_password_hash

from . import db as dbm
from . import benachrichtigung as ben
from . import katalog, logik
from . import navigation as nav
from . import lager as lgr
from .backup import backup_erstellen
from .hilfen import (EingabeFehler, anrede_brief, cent_aus_text, datum_de, euro, heute, kunde_name, menge_text, platzhalter_ersetzen, plus_tage,
                     zahl_aus_text)
from .mail import MailFehler, senden
from .pdf import SCHRIFTEN, pdf_erzeugen
from .sicherheit import verschluesseln
from .textbausteine_standard import PLATZHALTER_HILFE

bp = Blueprint("main", __name__)


def daten_dir():
    return current_app.config["DATEN"]


def _f(name, standard=""):
    return (request.form.get(name) or standard).strip()


def _benachrichtigungen_automatisch():
    """Ist die Vorschau ausgeschaltet, werden neue Benachrichtigungen sofort gesendet."""
    for ok, text in ben.offene_automatisch_senden(dbm.get_db()):
        flash(("Kunde benachrichtigt – " if ok else "Benachrichtigung fehlgeschlagen – ") + text,
              "ok" if ok else "warnung")


# ====================================================================== Anmeldung

@bp.route("/einrichten", methods=["GET", "POST"])
def einrichten():
    if not dbm.einstellung("login_aktiv"):
        return redirect(url_for("main.start"))
    if dbm.einstellung("passwort_hash"):
        return redirect(url_for("main.login"))
    if request.method == "POST":
        pw, pw2 = request.form.get("passwort", ""), request.form.get("passwort2", "")
        if len(pw) < 8:
            flash("Das Passwort muss mindestens 8 Zeichen lang sein.", "fehler")
        elif pw != pw2:
            flash("Die beiden Passwörter stimmen nicht überein.", "fehler")
        else:
            con = dbm.get_db()
            with dbm.Transaktion(con):
                dbm.einstellungen_speichern({"passwort_hash": generate_password_hash(pw)}, con)
                dbm.protokollieren("passwort_eingerichtet", "system", con=con)
            session.clear()
            session["angemeldet"] = True
            session["benutzer"] = "inhaber"
            session.permanent = True
            flash("Willkommen! Bitte tragen Sie zuerst Ihre Firmendaten ein.", "ok")
            return redirect(url_for("main.einstellungen"))
    return render_template("einrichten.html")


@bp.route("/login", methods=["GET", "POST"])
def login():
    if not dbm.einstellung("login_aktiv"):
        return redirect(url_for("main.start"))
    if request.method == "POST":
        if check_password_hash(dbm.einstellung("passwort_hash") or "", request.form.get("passwort", "")):
            session.clear()
            session["angemeldet"] = True
            session["benutzer"] = "inhaber"
            session.permanent = True
            weiter = request.args.get("weiter") or ""
            return redirect(weiter if weiter.startswith("/") and not weiter.startswith("//") else url_for("main.start"))
        con = dbm.get_db()
        with dbm.Transaktion(con):
            dbm.protokollieren("anmeldung_fehlgeschlagen", "system", con=con)
        flash("Das Passwort ist falsch.", "fehler")
    return render_template("login.html")


@bp.route("/abmelden", methods=["POST"])
def abmelden():
    session.clear()
    return redirect(url_for("main.login"))


# ====================================================================== Start

def _umzug_hinweis(con):
    """Einmaliger Hinweis nach der Übernahme der Daten an den festen Ort."""
    pfad = Path(daten_dir()) / "umzug.json"
    if not pfad.is_file() or dbm.einstellung("umzug_hinweis_gezeigt", con):
        return
    try:
        b = json.loads(pfad.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    flash(f"Ihre Daten liegen jetzt fest an einem Ort ({b['nach']}) – egal, von wo das Programm gestartet wird. "
          f"Übernommen aus {b['von']}, Datensätze und Dateien geprüft.", "info")
    if b.get("weitere_ordner"):
        flash("Weitere ältere Datenordner gefunden: " + ", ".join(b["weitere_ordner"]) + ". Falls dort etwas "
              "fehlt: Einstellungen → Backup → Sicherung wiederherstellen.", "warnung")
    with dbm.Transaktion(con):
        dbm.einstellungen_speichern({"umzug_hinweis_gezeigt": dbm.jetzt()}, con)
        dbm.protokollieren("daten_umgezogen", "system", None, b, con=con)


@bp.route("/")
def start():
    con = dbm.get_db()
    jahr = date.today().year
    _umzug_hinweis(con)

    def umsatz(j):
        return con.execute(
            "SELECT COALESCE(SUM(summe_brutto),0) FROM dokumente WHERE status<>'entwurf' "
            "AND typ IN ('rechnung','storno') AND substr(datum,1,4)=?", (str(j),)).fetchone()[0]

    zahlen = {
        "kunden": con.execute("SELECT COUNT(*) FROM kunden WHERE archiviert=0").fetchone()[0],
        "entwuerfe": con.execute("SELECT COUNT(*) FROM dokumente WHERE status='entwurf'").fetchone()[0],
        "umsatz_jahr": umsatz(jahr),
        "umsatz_vorjahr": umsatz(jahr - 1),
        "offen": _zlg().summe_offen(con),
        "ueberfaellig": len(_zlg().offene_posten(con, nur_ueberfaellig=True)),
    }
    zahlen["auftraege"] = {r[0]: r[1] for r in con.execute(
        "SELECT status, COUNT(*) FROM auftraege WHERE status<>'erledigt' OR erledigt_am >= date('now','-30 day') "
        "GROUP BY status")}
    from . import vertraege as _v
    _vs = con.execute("SELECT * FROM vertraege").fetchall()
    _einst = dbm.einstellungen(con)
    _zust = [(v, _v.zustand(v, erinnerung_tage=int(_einst.get("vertrag_erinnerung_tage") or 60))[0]) for v in _vs]
    zahlen["vertraege_monatlich"] = sum(_v.monatswert(v) for v, z in _zust if z in ("aktiv", "laeuft_ab", "gekuendigt"))
    zahlen["vertraege_aktiv"] = len([1 for _, z in _zust if z in ("aktiv", "laeuft_ab")])
    zahlen["vertraege_laeuft_ab"] = len([1 for _, z in _zust if z == "laeuft_ab"])
    zahlen["anfragen"] = con.execute("SELECT COUNT(*) FROM anfragen WHERE status='neu' AND einstufung<>'spam'"
                                     ).fetchone()[0]
    letzte = con.execute(
        "SELECT d.*, k.firma, k.vorname, k.nachname, k.typ AS ktyp FROM dokumente d "
        "LEFT JOIN kunden k ON k.id=d.kunde_id ORDER BY d.geaendert_am DESC LIMIT 8").fetchall()
    return render_template("start.html", zahlen=zahlen, letzte=letzte, jahr=jahr)


# ====================================================================== Kunden

@bp.route("/kunden")
def kunden():
    q = request.args.get("q", "").strip()
    archiv = request.args.get("archiv") == "1"
    nur_interessenten = request.args.get("interessenten") == "1"
    sql = "SELECT * FROM kunden WHERE archiviert=?" + (" AND interessent=1" if nur_interessenten else "")
    args = [1 if archiv else 0]
    if q:
        sql += (" AND (kundennr LIKE ? OR firma LIKE ? OR vorname LIKE ? OR nachname LIKE ? OR email LIKE ? "
                "OR ort LIKE ? OR telefon LIKE ?)")
        args += [f"%{q}%"] * 7
    sql += " ORDER BY COALESCE(NULLIF(firma,''), nachname), vorname"
    return render_template("kunden.html", kunden=dbm.get_db().execute(sql, args).fetchall(), q=q, archiv=archiv,
                           nur_interessenten=nur_interessenten)


@bp.route("/kunden/neu", methods=["GET", "POST"])
@bp.route("/kunden/<int:kid>", methods=["GET", "POST"])
def kunde(kid=None):
    con = dbm.get_db()
    k = con.execute("SELECT * FROM kunden WHERE id=?", (kid,)).fetchone() if kid else None
    if kid and not k:
        abort(404)
    if request.method == "POST":
        felder = {f: _f(f) for f in ("typ", "firma", "anrede", "vorname", "nachname", "strasse", "plz", "ort", "land",
                                     "email", "telefon", "ust_idnr", "notizen", "email_weitere", "e_rechnung",
                                     "leitweg_id")}
        if felder["e_rechnung"] not in ("auto", "pdf", "zugferd", "xrechnung"):
            felder["e_rechnung"] = "auto"
        if felder["typ"] not in ("privat", "firma"):
            felder["typ"] = "privat"
        if not (felder["firma"] or felder["nachname"]):
            raise EingabeFehler("Bitte mindestens Nachname oder Firma angeben.")
        ziel = _f("zahlungsziel_tage")
        felder["zahlungsziel_tage"] = int(ziel) if ziel.isdigit() else None
        felder["interessent"] = 1 if request.form.get("interessent") else 0
        with dbm.Transaktion(con):
            if k:
                if k["anonymisiert_am"]:
                    raise EingabeFehler("Dieser Kunde wurde anonymisiert und kann nicht mehr bearbeitet werden.")
                con.execute(f"UPDATE kunden SET {', '.join(f'{f}=?' for f in felder)}, geaendert_am=? WHERE id=?",
                            [*felder.values(), dbm.jetzt(), kid])
                dbm.protokollieren("kunde_geaendert", "kunde", kid, con=con)
                dbm.aenderungen_erfassen(con, "kunde", kid, k, felder, namen=KUNDE_FELDNAMEN)
            else:
                nr = logik.naechste_kundennr(con, dbm.einstellungen(con))
                cur = con.execute(
                    f"INSERT INTO kunden (kundennr, {', '.join(felder)}, erstellt_am, geaendert_am) "
                    f"VALUES (?, {', '.join('?' * len(felder))}, ?, ?)",
                    [nr, *felder.values(), dbm.jetzt(), dbm.jetzt()])
                kid = cur.lastrowid
                dbm.protokollieren("kunde_angelegt", "kunde", kid, {"kundennr": nr}, con=con)
                dbm.aenderungen_erfassen(con, "kunde", kid, None, {"kundennr": nr, **felder}, aktion="angelegt",
                                         namen=KUNDE_FELDNAMEN)
        flash("Kunde gespeichert.", "ok")
        _historie_nachholen(k, felder)
        if request.form.get("danach") == "rechnung":
            return redirect(url_for("main.dokument_neu", kunde_id=kid))
        return redirect(url_for("main.kunde", kid=kid))
    dokumente = con.execute("SELECT * FROM dokumente WHERE kunde_id=? ORDER BY datum DESC, id DESC",
                            (kid,)).fetchall() if kid else []
    kunden_anfragen = con.execute("SELECT * FROM anfragen WHERE kunde_id=? ORDER BY eingang_am DESC",
                                  (kid,)).fetchall() if kid else []
    kunden_vertraege = [_vertrag_zusatz(v, dbm.einstellungen(con)) for v in con.execute(
        "SELECT * FROM vertraege WHERE kunde_id=? ORDER BY status, beginn DESC", (kid,)).fetchall()] if kid else []
    kunden_auftraege = con.execute("SELECT * FROM auftraege WHERE kunde_id=? ORDER BY eingang_am DESC",
                                   (kid,)).fetchall() if kid else []
    kunden_leihen = con.execute(
        "SELECT l.*, g.bezeichnung, (SELECT COUNT(*) FROM schadensfaelle s WHERE s.leihe_id=l.id "
        "AND s.storniert_am IS NULL) AS schaden_anzahl, (SELECT COALESCE(SUM(betrag), 0) FROM schadensfaelle s "
        "WHERE s.leihe_id=l.id AND s.storniert_am IS NULL) AS schaden_summe FROM leihen l "
        "JOIN leihgeraete g ON g.id=l.geraet_id WHERE l.kunde_id=? ORDER BY l.ausgabe_am DESC", (kid,)).fetchall() \
        if kid else []
    return render_template("kunde.html", k=k, dokumente=dokumente, anfragen=kunden_anfragen,
                           aenderungen=dbm.aenderungen_liste(con, "kunde", kid) if kid else [],
                           auftraege=kunden_auftraege, vertraege=kunden_vertraege, abrechnung=vtr.ABRECHNUNG,
                           leihen=kunden_leihen, heute=date.today().isoformat(),
                           emails=_kunden_emails(con, kid, request.args.get("mails") == "alle"),
                           offene=_zlg().offene_posten(con, kunde_id=kid) if kid else [],
                           zahlungen=con.execute(
                               "SELECT z.*, d.nummer FROM zahlungen z JOIN dokumente d ON d.id=z.dokument_id "
                               "WHERE d.kunde_id=? ORDER BY z.datum DESC, z.id DESC", (kid,)).fetchall() if kid else [],
                           zahlarten=_zlg().ZAHLARTEN,
                           email_anzahl=con.execute("SELECT COUNT(*) FROM email_kunden WHERE kunde_id=?",
                                                    (kid,)).fetchone()[0] if kid else 0)


def _kunden_emails(con, kid, alle=False):
    if not kid:
        return []
    from .email_historie import fuer_kunde
    return fuer_kunde(con, kid, None if alle else 50)


def _historie_nachholen(alt, felder):
    """Neue Adresse beim Kunden → im Hintergrund gezielt im Postfach nach früheren Mails suchen."""
    from . import email_historie as eh
    einst = dbm.einstellungen()
    if not einst.get("historie_aktiv"):
        return
    vorher = set(eh.adressen_aus_text(alt["email"]) + eh.adressen_aus_text(alt["email_weitere"])) if alt else set()
    neu = [a for a in eh.adressen_aus_text(felder["email"]) + eh.adressen_aus_text(felder["email_weitere"])
           if a not in vorher]
    if neu:
        eh.im_hintergrund(current_app._get_current_object(), eh.adressen_nachholen, neu,
                          synchron=current_app.config.get("HISTORIE_SYNCHRON", False))
        flash(f"Das Postfach wird im Hintergrund nach E-Mails von/an {', '.join(neu)} durchsucht.", "info")


KUNDE_FELDNAMEN = {"kundennr": "Kundennummer", "typ": "Typ", "firma": "Firma", "anrede": "Anrede", "vorname": "Vorname",
                   "nachname": "Nachname", "strasse": "Straße", "plz": "PLZ", "ort": "Ort", "land": "Land",
                   "email": "E-Mail", "telefon": "Telefon", "ust_idnr": "USt-IdNr.", "notizen": "Notizen",
                   "email_weitere": "Weitere E-Mail-Adressen", "zahlungsziel_tage": "Zahlungsziel (Tage)",
                   "interessent": "Interessent", "e_rechnung": "Rechnungsformat", "leitweg_id": "Leitweg-ID"}


@bp.route("/kunden/<int:kid>/archivieren", methods=["POST"])
def kunde_archivieren(kid):
    con = dbm.get_db()
    wert = 0 if request.form.get("zurueck") else 1
    with dbm.Transaktion(con):
        con.execute("UPDATE kunden SET archiviert=?, geaendert_am=? WHERE id=?", (wert, dbm.jetzt(), kid))
        dbm.aenderungen_erfassen(con, "kunde", kid, {"archiviert": 1 - wert}, {"archiviert": wert},
                                 namen={"archiviert": "archiviert"})
        dbm.protokollieren("kunde_archiviert" if wert else "kunde_reaktiviert", "kunde", kid, con=con)
    flash("Kunde archiviert." if wert else "Kunde wieder aktiv.", "ok")
    return redirect(url_for("main.kunde", kid=kid))


@bp.route("/kunden/<int:kid>/loeschen", methods=["GET", "POST"])
def kunde_loeschen(kid):
    """Löschen mit Prüfung der Aufbewahrungsfristen: vollständig löschen oder anonymisieren."""
    from . import aufbewahrung
    con = dbm.get_db()
    k = con.execute("SELECT * FROM kunden WHERE id=?", (kid,)).fetchone() or abort(404)
    if k["anonymisiert_am"]:
        raise EingabeFehler("Dieser Kunde wurde bereits anonymisiert.")
    if request.method == "GET":
        return render_template("kunde_loeschen.html", k=k, bericht=aufbewahrung.pruefen(con, kid))
    from . import datenschutz as ds
    anlass = "Löschanfrage des Kunden (Art. 17 DSGVO)" if request.form.get("anfrage") else "manuell"
    with dbm.Transaktion(con):
        bericht, pid = ds.kunde_loeschen(con, kid, anlass)
    if bericht["anonymisieren"]:
        flash(f"Kunde anonymisiert. Wegen Aufbewahrungspflichten bleiben die Belege bis "
              f"{datum_de(bericht['bis'])} erhalten; Name und Anschrift stehen nur noch darin.", "ok")
    else:
        flash("Kunde vollständig gelöscht.", "ok")
    flash("Das Löschprotokoll und die Bestätigung für den Kunden finden Sie unter Datenschutz.", "info")
    return redirect(url_for("main.datenschutz", protokoll=pid) + "#protokolle")


@bp.route("/kunden/<int:kid>/auskunft")
def kunde_auskunft(kid):
    """Auskunft nach Art. 15 DSGVO: ZIP mit Auskunftsschreiben, allen Daten und Kopien."""
    from . import datenschutz as ds
    con = dbm.get_db()
    k = con.execute("SELECT * FROM kunden WHERE id=?", (kid,)).fetchone() or abort(404)
    daten = ds.auskunft_zip(con, kid, daten_dir())
    with dbm.Transaktion(con):
        dbm.protokollieren("datenschutz_auskunft", "kunde", kid, {"kundennr": k["kundennr"]}, con=con)
        dbm.ereignis_erfassen(con, "kunde", kid, "Auskunft nach Art. 15 DSGVO erstellt", None)
    return send_file(io.BytesIO(daten), mimetype="application/zip", as_attachment=True,
                     download_name=f"Auskunft_{k['kundennr']}_{date.today().isoformat()}.zip")


@bp.route("/datenschutz", methods=["GET", "POST"])
def datenschutz():
    from . import datenschutz as ds
    con = dbm.get_db()
    if request.method == "POST":
        with dbm.Transaktion(con):
            z = ds.loeschlauf(con, daten_dir())
        flash("Löschlauf ausgeführt: " + ", ".join(f"{v} {k.replace('_', ' ')}" for k, v in z.items() if v)
              if any(z.values()) else "Löschlauf ausgeführt – nichts war fällig.", "ok")
        return redirect(url_for("main.datenschutz") + "#protokolle")
    return render_template("datenschutz.html", k=ds.kandidaten(con), protokolle=ds.protokolle(con),
                           zurueck=ds.zurueckstellungen(con), arten=ds.ARTEN, heute=date.today(),
                           fristen=ds.FRISTEN, gewaehlt=request.args.get("protokoll", type=int), json=json)


@bp.route("/datenschutz/zurueckstellen", methods=["POST"])
def datenschutz_zurueckstellen():
    from . import datenschutz as ds
    con = dbm.get_db()
    with dbm.Transaktion(con):
        ds.zurueckstellen(con, request.form.get("art", ""), request.form.get("objekt_id", type=int),
                          request.form.get("grund"), request.form.get("bis") or None)
    flash("Löschung zurückgestellt.", "ok")
    return redirect(url_for("main.datenschutz") + "#vorschau")


@bp.route("/datenschutz/zurueckstellung/<int:zid>/aufheben", methods=["POST"])
def datenschutz_zurueckstellung_aufheben(zid):
    from . import datenschutz as ds
    con = dbm.get_db()
    with dbm.Transaktion(con):
        ds.zurueckstellung_aufheben(con, zid)
    flash("Zurückstellung aufgehoben – der Eintrag wird beim nächsten Löschlauf wieder berücksichtigt.", "ok")
    return redirect(url_for("main.datenschutz") + "#vorschau")


@bp.route("/datenschutz/protokoll/<int:pid>.pdf")
def datenschutz_protokoll(pid):
    from . import datenschutz as ds
    con = dbm.get_db()
    p = con.execute("SELECT * FROM loeschprotokolle WHERE id=?", (pid,)).fetchone() or abort(404)
    return send_file(io.BytesIO(ds.loeschbestaetigung_pdf(con, p)), mimetype="application/pdf",
                     download_name=f"Loeschbestaetigung_{pid}.pdf")


@bp.route("/datenschutz/verzeichnis")
def datenschutz_verzeichnis():
    from . import datenschutz as ds
    from . import verfahrensdoku as vd
    abschnitte = ds.verzeichnis(dbm.get_db())
    if request.args.get("pdf"):
        return send_file(io.BytesIO(vd.pdf(abschnitte, dbm.einstellung("firma_name") or "",
                                           titel="Verzeichnis der Verarbeitungstätigkeiten (Art. 30 DSGVO)")),
                         mimetype="application/pdf", download_name=f"VVT_{date.today().isoformat()}.pdf")
    return render_template("vvt.html", abschnitte=abschnitte, ergaenzen=vd.ERGAENZEN, markiert=vd.markiert)


# ====================================================================== Leistungen & Artikel

def _leistungsarten():
    return [x.strip() for x in (dbm.einstellung("leistungsarten") or "").split(",") if x.strip()]


@bp.route("/artikel")
def artikel_liste():
    q = request.args.get("q", "").strip()
    sql, args = "SELECT * FROM artikel WHERE 1=1", []
    if q:
        sql += (" AND (name LIKE ? OR artikelnr LIKE ? OR leistungsart LIKE ? OR beschreibung LIKE ? OR ean LIKE ? "
                "OR herstellernr LIKE ? OR kompatibilitaet LIKE ?)")
        args += [f"%{q}%"] * 7
    sql += " ORDER BY aktiv DESC, leistungsart, name"
    return render_template("artikel_liste.html", artikel=dbm.get_db().execute(sql, args).fetchall(), q=q)


@bp.route("/artikel/neu", methods=["GET", "POST"])
@bp.route("/artikel/<int:aid>", methods=["GET", "POST"])
def artikel(aid=None):
    con = dbm.get_db()
    a = con.execute("SELECT * FROM artikel WHERE id=?", (aid,)).fetchone() if aid else None
    if aid and not a:
        abort(404)
    if request.method == "POST":
        if not _f("name"):
            raise EingabeFehler("Bitte eine Bezeichnung angeben.")
        ek_unbekannt = 1 if not _f("teilekosten") else 0
        teile = cent_aus_text(_f("teilekosten"))
        aufschlag = _f("aufschlag_prozent")
        aufschlag = zahl_aus_text(aufschlag) if aufschlag else None
        preis = cent_aus_text(_f("preis"), leer=None)
        if preis is None:
            if aufschlag is None or ek_unbekannt:
                raise EingabeFehler("Bitte einen Verkaufspreis oder Einkaufspreis mit Aufschlag angeben.")
            preis = int(round(teile * (1 + aufschlag / 100)))
        if not ek_unbekannt and aufschlag is None:
            aufschlag = katalog.aufschlag(preis, teile)
        felder = {
            "artikelnr": _f("artikelnr"), "name": _f("name"), "beschreibung": _f("beschreibung"),
            "leistungsart": _f("leistungsart"), "typ": _f("typ") if _f("typ") in ("leistung", "material") else "leistung",
            "einheit": _f("einheit", "Stk."), "preis": preis, "teilekosten": teile, "aufschlag_prozent": aufschlag,
            "steuersatz": zahl_aus_text(_f("steuersatz"), 19), "aktiv": 1 if request.form.get("aktiv") else 0,
            "ek_unbekannt": ek_unbekannt,
            "garantie_monate": int(_f("garantie_monate")) if _f("garantie_monate").isdigit() else None,
            "lagerfuehrend": 1 if request.form.get("lagerfuehrend") else 0,
            "mindestbestand": zahl_aus_text(_f("mindestbestand"), None) if _f("mindestbestand") else None,
            "lagerort": _f("lagerort"), "ean": _f("ean"), "herstellernr": _f("herstellernr"),
            "kompatibilitaet": _f("kompatibilitaet"),
        }
        if a and a["lagerfuehrend"] and not felder["lagerfuehrend"] and (a["bestand"] or 0):
            raise EingabeFehler("Der Artikel hat noch Lagerbestand. Bitte erst auf 0 korrigieren, dann „lagerführend“ "
                                "ausschalten.")
        with dbm.Transaktion(con):
            if a:
                con.execute(f"UPDATE artikel SET {', '.join(f'{f}=?' for f in felder)}, geaendert_am=? WHERE id=?",
                            [*felder.values(), dbm.jetzt(), aid])
                dbm.protokollieren("artikel_geaendert", "artikel", aid, con=con)
                dbm.aenderungen_erfassen(con, "artikel", aid, a, felder, namen=ARTIKEL_FELDNAMEN)
            else:
                cur = con.execute(f"INSERT INTO artikel ({', '.join(felder)}, erstellt_am, geaendert_am) "
                                  f"VALUES ({', '.join('?' * len(felder))}, ?, ?)",
                                  [*felder.values(), dbm.jetzt(), dbm.jetzt()])
                aid = cur.lastrowid
                dbm.protokollieren("artikel_angelegt", "artikel", aid, con=con)
                dbm.aenderungen_erfassen(con, "artikel", aid, None, felder, aktion="angelegt",
                                         namen=ARTIKEL_FELDNAMEN)
        flash("Leistung/Artikel gespeichert.", "ok")
        if felder["lagerfuehrend"]:
            return redirect(url_for("main.artikel", aid=aid) + "#lager")
        return redirect(url_for("main.artikel_liste"))
    return render_template("artikel.html", a=a, leistungsarten=_leistungsarten(),
                           aenderungen=dbm.aenderungen_liste(con, "artikel", aid) if aid else [],
                           bewegungen=lgr.bewegungen(con, aid, 100) if aid else [], lagerarten=lgr.ARTEN,
                           reserviert=lgr.reserviert(con, aid) if aid else 0,
                           quellen=ek.bezugsquellen(con, aid) if aid else [],
                           alle_lieferanten=ek.lieferanten(con, nur_aktive=True))


ARTIKEL_FELDNAMEN = {"artikelnr": "Artikelnummer", "name": "Bezeichnung", "beschreibung": "Beschreibung",
                     "leistungsart": "Leistungsart", "typ": "Typ", "einheit": "Einheit", "preis": "Preis (Cent)",
                     "teilekosten": "Einkauf (Cent)", "aufschlag_prozent": "Aufschlag %", "steuersatz": "Steuersatz",
                     "aktiv": "aktiv", "ek_unbekannt": "Einkauf unbekannt",
                     "garantie_monate": "Garantie (Monate)", "lagerfuehrend": "lagerführend",
                     "mindestbestand": "Mindestbestand", "lagerort": "Lagerort", "ean": "EAN",
                     "herstellernr": "Herstellernummer", "kompatibilitaet": "Kompatibilität"}


@bp.route("/artikel/<int:aid>/loeschen", methods=["POST"])
def artikel_loeschen(aid):
    con = dbm.get_db()
    with dbm.Transaktion(con):
        if con.execute("SELECT 1 FROM positionen WHERE artikel_id=? UNION SELECT 1 FROM lagerbewegungen "
                       "WHERE artikel_id=? UNION SELECT 1 FROM lager_reservierungen WHERE artikel_id=?",
                       (aid, aid, aid)).fetchone():
            con.execute("UPDATE artikel SET aktiv=0, geaendert_am=? WHERE id=?", (dbm.jetzt(), aid))
            dbm.aenderungen_erfassen(con, "artikel", aid, {"aktiv": 1}, {"aktiv": 0}, namen=ARTIKEL_FELDNAMEN)
            flash("Der Artikel wird in Dokumenten oder im Lager verwendet und wurde deshalb nur deaktiviert.", "info")
        else:
            alt = con.execute("SELECT name FROM artikel WHERE id=?", (aid,)).fetchone()
            dbm.ereignis_erfassen(con, "artikel", aid, "gelöscht", alt["name"] if alt else "")
            con.execute("DELETE FROM artikel WHERE id=?", (aid,))
            flash("Artikel gelöscht.", "ok")
        dbm.protokollieren("artikel_geloescht", "artikel", aid, con=con)
    return redirect(url_for("main.artikel_liste"))


# ====================================================================== Lager

@bp.route("/lager")
def lager():
    con = dbm.get_db()
    ansicht = request.args.get("ansicht", "bestand")
    q = request.args.get("q", "").strip()
    stichtag = request.args.get("stichtag") or date.today().isoformat()
    daten = {}
    if ansicht == "wert":
        try:
            date.fromisoformat(stichtag)
        except ValueError:
            raise EingabeFehler("Bitte einen gültigen Stichtag angeben.")
        daten["wert_zeilen"], daten["wert_summe"] = lgr.lagerwert(con, stichtag)
    elif ansicht == "bewegungen":
        daten["bewegungen"] = lgr.bewegungen(con, limit=500)
    elif ansicht == "inventur":
        daten["inventuren"] = con.execute("SELECT * FROM inventuren ORDER BY id DESC").fetchall()
    else:
        daten["zeilen"] = lgr.uebersicht(con, q, nur_unter_min=ansicht == "mindest")
    return render_template("lager.html", ansicht=ansicht, q=q, stichtag=stichtag, arten=lgr.ARTEN,
                           unter_min=lgr.unter_mindestbestand_anzahl(con), heute=date.today().isoformat(), **daten)


@bp.route("/lager/<int:artikel_id>/buchen", methods=["POST"])
def lager_buchen(artikel_id):
    con = dbm.get_db()
    art = _f("art")
    with dbm.Transaktion(con):
        _, negativ = lgr.bewegung_buchen(con, artikel_id, art, _f("menge"), _f("grund"))
    flash(f"{lgr.ARTEN.get(art, 'Buchung')} gebucht.", "ok")
    if negativ:
        flash("Achtung: Der Bestand ist jetzt negativ. Bitte prüfen (Zählung/Korrektur).", "warnung")
    return _zurueck(url_for("main.artikel", aid=artikel_id) + "#lager")


@bp.route("/lager/bestellvorschlag")
def lager_bestellvorschlag():
    con = dbm.get_db()
    vorschlag = lgr.bestellvorschlag(con)
    if request.args.get("format") == "csv":
        import csv
        puffer = io.StringIO()
        w = csv.writer(puffer, delimiter=";")
        w.writerow(["Artikel", "Artikelnr.", "Herstellernr.", "EAN", "Lagerort", "verfügbar", "Mindestbestand",
                    "Bestellmenge", "Einheit", "EK", "Summe"])
        for z in vorschlag:
            a = z["a"]
            w.writerow([a["name"], a["artikelnr"] or "", a["herstellernr"] or "", a["ean"] or "", a["lagerort"] or "",
                        menge_text(z["verfuegbar"]), menge_text(a["mindestbestand"]), z["menge"], a["einheit"] or "",
                        euro(a["teilekosten"] or 0, False), euro(z["summe"], False)])
        return send_file(io.BytesIO(puffer.getvalue().encode("utf-8-sig")), mimetype="text/csv",
                         download_name=f"Bestellvorschlag_{date.today().isoformat()}.csv", as_attachment=True)
    return render_template("lager_bestellvorschlag.html", vorschlag=vorschlag,
                           summe=sum(z["summe"] for z in vorschlag), heute=date.today().isoformat())


@bp.route("/lager/inventur/neu", methods=["POST"])
def inventur_neu():
    con = dbm.get_db()
    with dbm.Transaktion(con):
        iid = lgr.inventur_anlegen(con, _f("stichtag") or date.today().isoformat(), _f("bezeichnung"))
    flash("Inventur angelegt. Jetzt zählen – am PC, ausgedruckt oder per Handy.", "ok")
    return redirect(url_for("main.inventur", iid=iid))


def _inventur_laden(iid):
    inv = dbm.get_db().execute("SELECT * FROM inventuren WHERE id=?", (iid,)).fetchone()
    if not inv:
        abort(404)
    return inv


@bp.route("/lager/inventur/<int:iid>", methods=["GET", "POST"])
def inventur(iid):
    con = dbm.get_db()
    inv = _inventur_laden(iid)
    if request.method == "POST":
        werte = {int(k[4:]): v for k, v in request.form.items() if k.startswith("ist_") and k[4:].isdigit()}
        with dbm.Transaktion(con):
            n = lgr.zaehlen(con, iid, werte)
        flash(f"{n} Zählung(en) gespeichert.", "ok")
        return redirect(url_for("main.inventur", iid=iid, ort=request.args.get("ort", "")))
    positionen = lgr.inventur_positionen(con, iid)
    return render_template("inventur.html", inv=inv, positionen=positionen, druck=request.args.get("druck") == "1",
                           orte=sorted({p["lagerort"] or "" for p in positionen}), ort=request.args.get("ort"),
                           mobil=False, ziel=url_for("main.inventur", iid=iid))


@bp.route("/lager/inventur/<int:iid>/abschliessen", methods=["POST"])
def inventur_abschliessen(iid):
    con = dbm.get_db()
    _inventur_laden(iid)
    with dbm.Transaktion(con):
        diff, wert = lgr.inventur_abschliessen(con, iid, daten_dir(), bool(request.form.get("ungezaehlt_wie_soll")))
    flash(f"Inventur abgeschlossen: {diff} Differenz(en) gebucht, Lagerwert {euro(wert)}. Protokoll archiviert.", "ok")
    return redirect(url_for("main.inventur", iid=iid))


@bp.route("/lager/inventur/<int:iid>/protokoll.pdf")
def inventur_protokoll(iid):
    inv = _inventur_laden(iid)
    if not inv["pdf_datei"]:
        abort(404)
    pfad = Path(daten_dir()) / inv["pdf_datei"]
    daten = pfad.read_bytes() if pfad.is_file() else None
    if daten is None or hashlib.sha256(daten).hexdigest() != inv["pdf_sha256"]:
        return render_template("pdf_fehler.html", d={"nummer": f"Inventur {inv['stichtag']}",
                                                     "pdf_pfad": inv["pdf_datei"], "pdf_sha256": inv["pdf_sha256"]},
                               fehlt=daten is None), 409
    return send_file(io.BytesIO(daten), mimetype="application/pdf", download_name=Path(inv["pdf_datei"]).name)


@bp.route("/lager/inventur/<int:iid>/handy", methods=["POST"])
def inventur_handy(iid):
    con = dbm.get_db()
    inv = _inventur_laden(iid)
    with dbm.Transaktion(con):
        token = lgr.zaehl_token(con, iid)
    port = current_app.config.get("SERVER_PORT") or request.host.rsplit(":", 1)[-1]
    url = ann.basis_url(dbm.einstellungen(con), port) + url_for("main.mobil_inventur", token=token)
    im_netz = current_app.config.get("SERVER_HOST") == "0.0.0.0" or bool(dbm.einstellung("handy_adresse"))
    return render_template("inventur_qr.html", inv=inv, url=url, qr=Markup(ann.qr_svg(url)), im_netz=im_netz)


@bp.route("/m/inventur/<token>", methods=["GET", "POST"])
def mobil_inventur(token):
    con = dbm.get_db()
    z = lgr.zaehl_token_pruefen(con, token)
    if not z:
        return render_template("mobil.html", abgelaufen=True), 410
    g.benutzer_ersatz = "Inventur (Handy)"
    inv = _inventur_laden(z["inventur_id"])
    if request.method == "POST":
        werte = {int(k[4:]): v for k, v in request.form.items() if k.startswith("ist_") and k[4:].isdigit()}
        with dbm.Transaktion(con):
            n = lgr.zaehlen(con, inv["id"], werte)
        flash(f"{n} Zählung(en) gespeichert.", "ok")
        return redirect(url_for("main.mobil_inventur", token=token, ort=request.args.get("ort", "")))
    positionen = lgr.inventur_positionen(con, inv["id"])
    return render_template("inventur.html", inv=inv, positionen=positionen, druck=False, mobil=True,
                           orte=sorted({p["lagerort"] or "" for p in positionen}), ort=request.args.get("ort"),
                           ziel=url_for("main.mobil_inventur", token=token))


@bp.route("/auftraege/<int:aid>/material", methods=["POST"])
def auftrag_material(aid):
    con = dbm.get_db()
    _auftrag_laden(aid)
    with dbm.Transaktion(con):
        if request.form.get("aus_kva"):
            anzahl, warnungen = lgr.aus_kva_reservieren(con, aid)
            flash(f"{anzahl} Position(en) aus dem KVA reserviert." if anzahl else
                  "Keine (weiteren) lagerführenden Positionen im KVA.", "ok" if anzahl else "info")
        else:
            _, w = lgr.reservieren(con, aid, request.form.get("artikel_id", type=int), _f("menge", "1"))
            warnungen = [w] if w else []
            flash("Material reserviert.", "ok")
    for w in warnungen:
        flash(w, "warnung")
    return redirect(url_for("main.auftrag", aid=aid) + "#material")


@bp.route("/material/<int:rid>/stornieren", methods=["POST"])
def material_stornieren(rid):
    con = dbm.get_db()
    r = con.execute("SELECT * FROM lager_reservierungen WHERE id=?", (rid,)).fetchone()
    if not r:
        abort(404)
    with dbm.Transaktion(con):
        lgr.reservierung_stornieren(con, rid, _f("grund"))
    flash("Material storniert." if r["status"] == "reserviert" else "Material wieder ins Lager gebucht.", "ok")
    return redirect(url_for("main.auftrag", aid=r["auftrag_id"]) + "#material")


@bp.route("/dokumente/<int:did>/xml")
def dokument_xml(did):
    d = dbm.get_db().execute("SELECT * FROM dokumente WHERE id=?", (did,)).fetchone()
    if not d or not d["xml_pfad"]:
        abort(404)
    pfad = Path(daten_dir()) / d["xml_pfad"]
    daten = pfad.read_bytes() if pfad.is_file() else None
    if daten is None or hashlib.sha256(daten).hexdigest() != d["xml_sha256"]:
        return render_template("pdf_fehler.html", d={"nummer": d["nummer"], "pdf_pfad": d["xml_pfad"],
                                                     "pdf_sha256": d["xml_sha256"]}, fehlt=daten is None), 409
    return send_file(io.BytesIO(daten), mimetype="application/xml", as_attachment=True,
                     download_name=Path(d["xml_pfad"]).name)


# ====================================================================== Einkauf: Lieferanten, Bestellungen, Eingangsrechnungen

from . import einkauf as ek  # noqa: E402
from . import erechnung as erech  # noqa: E402


@bp.route("/einkauf/lieferanten")
def lieferanten():
    return render_template("lieferanten.html", liste=ek.lieferanten(dbm.get_db()))


@bp.route("/lieferanten/neu", methods=["GET", "POST"])
@bp.route("/lieferanten/<int:lid>", methods=["GET", "POST"])
def lieferant(lid=None):
    con = dbm.get_db()
    l = con.execute("SELECT * FROM lieferanten WHERE id=?", (lid,)).fetchone() if lid else None
    if lid and not l:
        abort(404)
    if request.method == "POST":
        daten = {k: _f(k) for k in ek.LIEFERANT_FELDER}
        daten["aktiv"] = request.form.get("aktiv") if lid else "1"
        with dbm.Transaktion(con):
            lid = ek.lieferant_speichern(con, daten, lid)
        flash("Lieferant gespeichert.", "ok")
        return redirect(url_for("main.lieferant", lid=lid))
    artikel = con.execute("SELECT al.*, a.name, a.einheit, a.teilekosten FROM artikel_lieferanten al JOIN artikel a "
                          "ON a.id=al.artikel_id WHERE al.lieferant_id=? ORDER BY a.name", (lid,)).fetchall() if lid else []
    return render_template("lieferant.html", l=l, artikel=artikel,
                           bestellungen=[b for b in ek.bestellungen(con) if b["lieferant_id"] == lid] if lid else [],
                           rechnungen=con.execute(ek.ER_SQL + "WHERE e.lieferant_id=? ORDER BY e.datum DESC LIMIT 50",
                                                  (lid,)).fetchall() if lid else [],
                           aenderungen=dbm.aenderungen_liste(con, "lieferant", lid) if lid else [])


@bp.route("/artikel/<int:aid>/bezugsquelle", methods=["POST"])
def artikel_bezugsquelle(aid):
    con = dbm.get_db()
    lid = request.form.get("lieferant_id", type=int)
    preis = cent_aus_text(_f("ek"), None)
    garantie = int(_f("garantie_monate")) if _f("garantie_monate").isdigit() else None
    with dbm.Transaktion(con):
        if request.form.get("entfernen"):
            con.execute("DELETE FROM artikel_lieferanten WHERE artikel_id=? AND lieferant_id=?", (aid, lid))
            dbm.ereignis_erfassen(con, "artikel", aid, "Bezugsquelle entfernt", f"Lieferant #{lid}")
            warnung = None
        else:
            ek.bezugsquelle_speichern(con, aid, lid, preis, _f("lieferanten_artnr"), garantie)
            warnung = None
            if request.form.get("als_ek") and preis is not None:
                warnung = ek.ek_aktualisieren(con, aid, preis, "Bezugsquelle")
    flash("Bezugsquelle gespeichert.", "ok")
    if warnung:
        flash(warnung, "warnung")
    return redirect(url_for("main.artikel", aid=aid) + "#bezugsquellen")


@bp.route("/einkauf/bestellungen")
def bestellungen():
    con = dbm.get_db()
    status = request.args.get("status", "offen")
    return render_template("bestellungen.html", liste=ek.bestellungen(con, status if status != "alle" else None),
                           status=status, status_namen=ek.BESTELL_STATUS)


@bp.route("/bestellungen/neu", methods=["GET", "POST"])
def bestellung_neu():
    con = dbm.get_db()
    if request.method == "POST":
        f = request.form
        pos = []
        for artikel_id, bez, artnr, menge, preis in zip(f.getlist("p_artikel_id"), f.getlist("p_bezeichnung"),
                                                         f.getlist("p_artnr"), f.getlist("p_menge"), f.getlist("p_ek")):
            pos.append({"artikel_id": int(artikel_id) if artikel_id.isdigit() else None, "bezeichnung": bez,
                        "lieferanten_artnr": artnr, "menge": zahl_aus_text(menge, 0), "ek": cent_aus_text(preis, None)})
        with dbm.Transaktion(con):
            bid = ek.bestellung_anlegen(con, f.get("lieferant_id", type=int), pos, _f("notiz"),
                                        auftrag_id=f.get("auftrag_id", type=int))
        flash("Bestellung angelegt. Prüfen, dann senden bzw. „als bestellt markieren“.", "ok")
        return redirect(url_for("main.bestellung", bid=bid))
    auftrag_row = _auftrag_laden(request.args.get("auftrag_id", type=int)) if request.args.get("auftrag_id") else None
    vorauswahl = []
    lieferant_id = request.args.get("lieferant_id", type=int)
    if request.args.get("artikel_id"):
        a = con.execute("SELECT * FROM artikel WHERE id=?", (request.args.get("artikel_id", type=int),)).fetchone()
        if a:
            q = ek.guenstigste_quelle(con, a["id"])
            lieferant_id = lieferant_id or (q["lieferant_id"] if q else None)
            vorauswahl.append({"artikel_id": a["id"], "bezeichnung": a["name"], "menge": 1,
                               "ek": q["ek"] if q and q["ek"] is not None else a["teilekosten"],
                               "lieferanten_artnr": q["lieferanten_artnr"] if q else ""})
    quellen = {a["id"]: [dict(q) for q in ek.bezugsquellen(con, a["id"])] for a in con.execute(
        "SELECT DISTINCT artikel_id AS id FROM artikel_lieferanten").fetchall()}
    return render_template("bestellung_neu.html", lieferanten=ek.lieferanten(con, nur_aktive=True),
                           artikel=[dict(a) for a in con.execute("SELECT id, name, teilekosten, einheit FROM artikel "
                                                                 "WHERE aktiv=1 ORDER BY name")],
                           quellen=quellen, a=auftrag_row, vorauswahl=vorauswahl, lieferant_id=lieferant_id)


@bp.route("/bestellungen/aus-vorschlag", methods=["POST"])
def bestellungen_aus_vorschlag():
    con = dbm.get_db()
    auswahl = [(int(a), zahl_aus_text(request.form.get(f"menge_{a}"), 0)) for a in request.form.getlist("artikel_id")
               if a.isdigit()]
    auswahl = [(a, m) for a, m in auswahl if m > 0]
    if not auswahl:
        raise EingabeFehler("Bitte mindestens einen Artikel auswählen.")
    with dbm.Transaktion(con):
        ids, ohne = ek.aus_vorschlag(con, auswahl)
    if ids:
        flash(f"{len(ids)} Bestellung(en) angelegt (je Lieferant der günstigste).", "ok")
    if ohne:
        flash("Ohne Lieferant (bitte beim Artikel eine Bezugsquelle eintragen): " + ", ".join(ohne), "warnung")
    return redirect(url_for("main.bestellung", bid=ids[0]) if len(ids) == 1 else url_for("main.bestellungen"))


@bp.route("/bestellungen/<int:bid>", methods=["GET", "POST"])
def bestellung(bid):
    con = dbm.get_db()
    b = ek.bestellung(con, bid)
    if request.method == "POST":
        aktion = request.form.get("aktion")
        with dbm.Transaktion(con):
            if aktion == "bestellt":
                ek.bestellt_markieren(con, bid, _f("erwartet_am") or None)
                meldung = "Als bestellt markiert."
            elif aktion == "stornieren":
                ek.bestellung_stornieren(con, bid, _f("grund"))
                meldung = "Bestellung storniert."
            elif aktion == "wareneingang":
                mengen = {int(k[6:]): v for k, v in request.form.items() if k.startswith("menge_") and k[6:].isdigit()}
                eks = {int(k[3:]): cent_aus_text(v, None) for k, v in request.form.items()
                       if k.startswith("ek_") and k[3:].isdigit() and v.strip()}
                anzahl, warnungen, auftraege = ek.wareneingang(con, bid, mengen, eks, _f("lieferschein"),
                                                               bool(request.form.get("auftrag_fortsetzen")))
                meldung = f"Wareneingang gebucht ({anzahl} Position(en))." + (
                    f" Betroffene Aufträge wurden benachrichtigt ({len(auftraege)})." if auftraege else "")
                for w in warnungen:
                    flash(w, "warnung")
            else:
                abort(400)
        flash(meldung, "ok")
        _benachrichtigungen_automatisch()
        return redirect(url_for("main.bestellung", bid=bid))
    return render_template("bestellung.html", b=b, positionen=ek.positionen(con, bid), status_namen=ek.BESTELL_STATUS,
                           eingaenge=con.execute("SELECT w.*, p.bezeichnung FROM wareneingaenge w JOIN bestell_positionen p "
                                                 "ON p.id=w.position_id WHERE w.bestellung_id=? ORDER BY w.id",
                                                 (bid,)).fetchall(),
                           rechnungen=con.execute(ek.ER_SQL + "WHERE e.bestellung_id=?", (bid,)).fetchall())


@bp.route("/bestellungen/<int:bid>/pdf")
def bestellung_pdf(bid):
    con = dbm.get_db()
    b = ek.bestellung(con, bid)
    return send_file(io.BytesIO(ek.bestellung_pdf(con, bid, daten_dir())), mimetype="application/pdf",
                     download_name=f"Bestellung_{b['nummer']}.pdf")


@bp.route("/bestellungen/<int:bid>/email", methods=["GET", "POST"])
def bestellung_email(bid):
    con = dbm.get_db()
    b = ek.bestellung(con, bid)
    einst = dbm.einstellungen(con)
    if request.method == "POST":
        an = _f("an")
        if "@" not in an:
            raise EingabeFehler("Bitte eine gültige E-Mail-Adresse angeben.")
        try:
            hinweis = senden(con, None, an, _f("betreff"), request.form.get("text", ""),
                             ek.bestellung_pdf(con, bid, daten_dir()), f"Bestellung_{b['nummer']}.pdf")
        except MailFehler as e:
            flash(f"E-Mail wurde NICHT gesendet: {e}", "fehler")
            return redirect(url_for("main.bestellung_email", bid=bid))
        with dbm.Transaktion(con):
            con.execute("UPDATE bestellungen SET versendet_an=? WHERE id=?", (an, bid))
            if b["status"] == "entwurf":
                ek.bestellt_markieren(con, bid)
        flash(f"Bestellung an {an} gesendet und als bestellt markiert.", "ok")
        if hinweis:
            flash(hinweis, "warnung")
        _benachrichtigungen_automatisch()
        return redirect(url_for("main.bestellung", bid=bid))
    text = (f"Guten Tag,\n\nanbei unsere Bestellung {b['nummer']}"
            + (f" (Kundennummer {b['kundennr_bei']})" if b["kundennr_bei"] else "")
            + ". Bitte bestätigen Sie kurz den Liefertermin.\n\nMit freundlichen Grüßen\n"
            + f"{einst.get('inhaber') or ''}\n{einst.get('firma_name') or ''}")
    return render_template("bestellung_email.html", b=b, an=b["lemail"] or "", text=text,
                           betreff=f"Bestellung {b['nummer']} – {einst.get('firma_name') or ''}",
                           smtp_ok=bool(einst.get("smtp_host")))


def _kostenarten():
    return [k.strip() for k in (dbm.einstellung("kostenarten") or "").splitlines() if k.strip()]


@bp.route("/einkauf/eingangsrechnungen")
def eingangsrechnungen():
    con = dbm.get_db()
    status = request.args.get("status", "offen")
    q = request.args.get("q", "").strip()
    return render_template("eingangsrechnungen.html", liste=ek.eingangsrechnungen(con, status, q), status=status, q=q,
                           summe_offen=ek.summe_offen(con), status_namen=ek.ER_STATUS, heute=date.today().isoformat())


@bp.route("/eingangsrechnungen/neu", methods=["GET", "POST"])
def eingangsrechnung_neu():
    con = dbm.get_db()
    vorlage = session.get("er_datei") or {}
    if request.method == "POST":
        datei = request.files.get("datei")
        if datei and datei.filename:
            vorlage = _er_vorlage(con, datei.read(), datei.filename, "Upload")
            if vorlage.get("e_rechnung") and not (_f("brutto") or _f("netto")):
                flash("E-Rechnung erkannt – die Angaben wurden aus der XML übernommen. Bitte prüfen und speichern.", "ok")
                return redirect(url_for("main.eingangsrechnung_neu"))
        felder = ek.er_felder(request.form)
        e_daten = None
        if vorlage.get("e_rechnung"):
            bt, _ = erech.einlesen((Path(daten_dir()) / vorlage["rel"]).read_bytes(), vorlage.get("name"))
            e_daten = json.dumps(bt, ensure_ascii=False, default=str) if bt else None
        with dbm.Transaktion(con):
            eid = ek.er_anlegen(con, felder, vorlage.get("rel"), vorlage.get("sha"), vorlage.get("name"),
                                vorlage.get("quelle") or "manuell", vorlage.get("message_id"), e_daten)
        session.pop("er_datei", None)
        flash("Eingangsrechnung erfasst.", "ok")
        return redirect(url_for("main.eingangsrechnung", eid=eid))
    if request.args.get("neu"):
        session.pop("er_datei", None)
        vorlage = {}
    werte = dict(vorlage.get("werte") or {})
    if request.args.get("bestellung_id"):
        b = ek.bestellung(con, request.args.get("bestellung_id", type=int))
        werte.update(lieferant_id=b["lieferant_id"], bestellung_id=b["id"], kostenart=(_kostenarten() or [""])[0])
    return render_template("eingangsrechnung.html", e=None, vorlage=vorlage, werte=werte,
                           lieferanten=ek.lieferanten(con), kostenarten=_kostenarten(),
                           bestellungen=ek.bestellungen(con), heute=date.today().isoformat())


def _er_vorlage(con, daten, name, quelle, message_id=None, werte=None):
    """Beleg ablegen, E-Rechnung auslesen, Lieferant zuordnen; Ergebnis in der Sitzung merken (nur Verweise)."""
    rel, sha = ek.datei_ablegen(daten_dir(), daten, name)
    werte = dict(werte or {})
    bt, _ = erech.einlesen(daten, name)
    if bt:
        e = erech.eingangswerte(bt)
        werte.update({k: v for k, v in e.items() if v not in (None, "") and k not in ("iban", "ust_idnr", "email")})
        werte.setdefault("email", e["email"])
        werte["ust_idnr"] = e["ust_idnr"]
    l = None
    if werte.get("ust_idnr"):
        l = con.execute("SELECT id FROM lieferanten WHERE replace(upper(ust_idnr), ' ', '')=?",
                        (werte["ust_idnr"].replace(" ", "").upper(),)).fetchone()
    if not l and werte.get("email"):
        l = con.execute("SELECT id FROM lieferanten WHERE lower(email)=lower(?)", (werte["email"],)).fetchone()
    if not l and werte.get("lieferant_name"):
        l = con.execute("SELECT id FROM lieferanten WHERE lower(name)=lower(?)", (werte["lieferant_name"],)).fetchone()
    if l:
        werte["lieferant_id"] = l["id"]
    werte = {k: v for k, v in werte.items() if k in ("lieferant_id", "lieferant_name", "nummer", "datum", "faellig_am",
                                                     "netto", "steuer", "brutto", "steuersatz", "beschreibung")}
    vorlage = {"rel": rel, "sha": sha, "name": name, "quelle": quelle + (" (E-Rechnung)" if bt else ""),
               "message_id": message_id, "werte": werte, "e_rechnung": bool(bt)}
    session["er_datei"] = vorlage
    return vorlage


@bp.route("/eingangsrechnungen/<int:eid>/e-rechnung")
def eingangsrechnung_e(eid):
    """Lesbare Ansicht einer empfangenen E-Rechnung (XRechnung/ZUGFeRD); ?pdf=1 als PDF speichern."""
    e = dbm.get_db().execute("SELECT * FROM eingangsrechnungen WHERE id=?", (eid,)).fetchone()
    if not e or not e["e_daten"]:
        abort(404)
    r = erech.lesbar(json.loads(e["e_daten"]))
    if request.args.get("pdf"):
        return send_file(io.BytesIO(erech.ansicht_pdf(r)), mimetype="application/pdf",
                         download_name=f"E-Rechnung_{e['lfd_nr']}.pdf")
    return render_template("e_rechnung_ansicht.html", e=e, r=r)


@bp.route("/eingangsrechnungen/<int:eid>", methods=["GET", "POST"])
def eingangsrechnung(eid):
    con = dbm.get_db()
    e = con.execute(ek.ER_SQL + "WHERE e.id=?", (eid,)).fetchone()
    if not e:
        abort(404)
    if request.method == "POST":
        aktion = request.form.get("aktion")
        with dbm.Transaktion(con):
            if aktion == "speichern":
                ek.er_aendern(con, eid, ek.er_felder(request.form))
                meldung = "Änderungen gespeichert (im Änderungsprotokoll vermerkt)."
            elif aktion == "zahlung":
                ek.er_zahlung(con, eid, _f("datum"), cent_aus_text(_f("betrag"), 0), _f("zahlart"), _f("notiz"))
                meldung = "Zahlung erfasst."
            elif aktion == "zahlung_storno":
                ek.er_zahlung_stornieren(con, request.form.get("zahlung_id", type=int), _f("grund"))
                meldung = "Zahlung storniert."
            elif aktion == "stornieren":
                ek.er_stornieren(con, eid, _f("grund"))
                meldung = "Eingangsrechnung storniert."
            else:
                abort(400)
        flash(meldung, "ok")
        return redirect(url_for("main.eingangsrechnung", eid=eid))
    return render_template("eingangsrechnung.html", e=e, vorlage={}, werte=dict(e), lieferanten=ek.lieferanten(con),
                           fix_liste=fxk.alle(con),
                           kostenarten=_kostenarten(), bestellungen=ek.bestellungen(con),
                           zahlungen=con.execute("SELECT * FROM er_zahlungen WHERE eingangsrechnung_id=? ORDER BY datum, id",
                                                 (eid,)).fetchall(), zahlarten=ek.ZAHLARTEN,
                           aenderungen=dbm.aenderungen_liste(con, "eingangsrechnung", eid), heute=date.today().isoformat())


@bp.route("/eingangsrechnungen/datei/<sha>")
def eingangsrechnung_datei(sha):
    con = dbm.get_db()
    e = con.execute("SELECT datei, datei_name, datei_sha256 FROM eingangsrechnungen WHERE datei_sha256=?",
                    (sha,)).fetchone()
    v = session.get("er_datei") or {}
    rel = e["datei"] if e else (v.get("rel") if v.get("sha") == sha else None)
    if not rel:
        abort(404)
    pfad = Path(daten_dir()) / rel
    daten = pfad.read_bytes() if pfad.is_file() else None
    if daten is None or hashlib.sha256(daten).hexdigest() != sha:
        return render_template("pdf_fehler.html", d={"nummer": "Eingangsrechnung", "pdf_pfad": rel, "pdf_sha256": sha},
                               fehlt=daten is None), 409
    endung = rel.rsplit(".", 1)[-1].lower()
    return send_file(io.BytesIO(daten), mimetype=ek.ER_ENDUNGEN.get(endung, "application/octet-stream"),
                     download_name=(e["datei_name"] if e else v.get("name")) or f"beleg.{endung}")


@bp.route("/eingangsrechnungen/postfach", methods=["GET", "POST"])
def eingangsrechnungen_postfach():
    from . import er_postfach
    from .anfragen import AbrufFehler
    con = dbm.get_db()
    einst = dbm.einstellungen(con)
    if request.method == "POST":
        try:
            daten, name, kopf = er_postfach.anhang_holen(einst, _f("uid"), request.form.get("index", type=int))
        except AbrufFehler as e:
            raise EingabeFehler(str(e))
        vorlage = _er_vorlage(con, daten, name, "Postfach", kopf["message_id"],
                              {"datum": kopf["datum"], "lieferant_name": kopf["von"], "email": kopf["von_adresse"]})
        if vorlage.get("e_rechnung"):
            flash("E-Rechnung erkannt – die Angaben wurden aus der XML übernommen. Bitte prüfen und speichern.", "ok")
        return redirect(url_for("main.eingangsrechnung_neu"))
    try:
        liste = er_postfach.mails(con, einst)
        fehler = None
    except AbrufFehler as e:
        liste, fehler = [], str(e)
    return render_template("er_postfach.html", liste=liste, fehler=fehler, ordner=einst.get("er_imap_ordner"))


@bp.route("/bank/<int:uid>/eingangsrechnung", methods=["POST"])
def bank_er_zuordnen(uid):
    con = dbm.get_db()
    eid = request.form.get("eingangsrechnung_id", type=int)
    if not eid:
        raise EingabeFehler("Bitte eine Eingangsrechnung auswählen.")
    with dbm.Transaktion(con):
        ek.bank_zuordnen(con, uid, eid)
    flash("Ausgang der Eingangsrechnung zugeordnet.", "ok")
    return redirect(url_for("main.bank"))


# ====================================================================== Kassenbuch & DATEV

from . import datev as dtv  # noqa: E402
from . import kasse as kas  # noqa: E402


@bp.route("/kasse")
def kassenbuch():
    con = dbm.get_db()
    heute_iso = date.today().isoformat()
    von = request.args.get("von") or heute_iso[:8] + "01"
    bis = request.args.get("bis") or heute_iso
    zeilen = kas.buchungen(con, von, bis)
    if request.args.get("druck"):
        return render_template("kasse_druck.html", zeilen=zeilen, von=von, bis=bis, arten=kas.ARTEN,
                               abschluesse=con.execute("SELECT * FROM kassen_abschluesse WHERE datum BETWEEN ? AND ? "
                                                       "ORDER BY datum", (von, bis)).fetchall())
    gegengebucht = {r[0] for r in con.execute("SELECT gegenbuchung_zu FROM kassenbuch WHERE gegenbuchung_zu IS NOT NULL")}
    offene_re = con.execute(_zlg().RECHNUNG_SQL + "WHERE d.typ='rechnung' AND d.status='festgeschrieben' "
                            "AND d.summe_brutto > d.bezahlt_betrag ORDER BY d.datum DESC LIMIT 100").fetchall()
    return render_template("kasse.html", zeilen=zeilen, von=von, bis=bis, arten=kas.ARTEN, heute=heute_iso,
                           offen=session.get("kasse_offen"),
                           bestand=kas.bestand(con), letzter=kas.letzter_abschluss(con), gegengebucht=gegengebucht,
                           kostenarten=_kostenarten(), scheine=kas.SCHEINE, offene_re=offene_re,
                           abschluesse=con.execute("SELECT * FROM kassen_abschluesse ORDER BY datum DESC LIMIT 15").fetchall())


def _kasse_ausfuehren(con, b):
    with dbm.Transaktion(con):
        if b["art"] == "einnahme" and b.get("dokument_id"):  # Barzahlung einer Rechnung (bucht selbst in die Kasse)
            _zlg().erfassen(con, b["dokument_id"], b["datum"], b["betrag"], "bar", b["text"])
        else:
            kas.buchen(con, b["datum"], b["art"], b["betrag"], b["text"], b.get("steuersatz"),
                       beleg=tuple(b["beleg"]) if b.get("beleg") else None, kostenart=b.get("kostenart"))


@bp.route("/kasse/buchen", methods=["POST"])
def kasse_buchen():
    """Kassenbuchung. Würde der Bestand an einem Tag negativ, bleibt die Buchung vorgemerkt: Nach dem Erfassen der
    fehlenden Einnahme bzw. Privateinlage (nachholen=1) wird sie automatisch erneut versucht."""
    con = dbm.get_db()
    datei = request.files.get("beleg")
    beleg = kas.beleg_ablegen(daten_dir(), datei.read(), datei.filename) if datei and datei.filename else None
    b = {"datum": _f("datum"), "art": _f("art"), "betrag": cent_aus_text(_f("betrag"), 0), "text": _f("text"),
         "steuersatz": zahl_aus_text(_f("steuersatz"), None) if _f("steuersatz") else None,
         "dokument_id": request.form.get("dokument_id", type=int), "kostenart": _f("kostenart") or None,
         "beleg": list(beleg) if beleg else None}
    nachholen = request.form.get("nachholen") == "1" and session.get("kasse_offen")
    try:
        _kasse_ausfuehren(con, b)
    except kas.KassenFehlbetrag as e:
        if not nachholen:  # neue Buchung vormerken; bei einer Nachhol-Buchung bleibt die ursprüngliche vorgemerkt
            session["kasse_offen"] = {"buchung": b, "tag": e.tag, "fehlbetrag": e.fehlbetrag}
        else:
            session["kasse_offen"] = {**session["kasse_offen"], "tag": e.tag, "fehlbetrag": e.fehlbetrag}
        flash(str(e), "fehler")
        return redirect(url_for("main.kassenbuch", von=min(e.tag, date.today().isoformat()[:8] + "01")) + "#fehlbetrag")
    if not nachholen:
        session.pop("kasse_offen", None)
        flash("Kassenbuchung gespeichert.", "ok")
        return redirect(url_for("main.kassenbuch"))
    offen = session["kasse_offen"]["buchung"]
    flash(f"{kas.ARTEN[b['art']]} über {euro(b['betrag'])} am {datum_de(b['datum'])} gebucht.", "ok")
    try:
        _kasse_ausfuehren(con, offen)
    except kas.KassenFehlbetrag as e:
        session["kasse_offen"] = {"buchung": offen, "tag": e.tag, "fehlbetrag": e.fehlbetrag}
        flash("Die ursprüngliche Buchung ist noch nicht möglich: " + str(e), "fehler")
        return redirect(url_for("main.kassenbuch", von=min(e.tag, date.today().isoformat()[:8] + "01")) + "#fehlbetrag")
    except EingabeFehler as e:
        session.pop("kasse_offen", None)
        flash(f"Die ursprüngliche Buchung konnte nicht nachgeholt werden: {e}", "fehler")
        return redirect(url_for("main.kassenbuch"))
    session.pop("kasse_offen", None)
    flash(f"Ursprüngliche Buchung „{offen['text']}“ ({euro(offen['betrag'])}) wurde automatisch nachgeholt.", "ok")
    return redirect(url_for("main.kassenbuch", von=min(offen["datum"], date.today().isoformat()[:8] + "01")))


@bp.route("/kasse/vormerkung-verwerfen", methods=["POST"])
def kasse_vormerkung_verwerfen():
    session.pop("kasse_offen", None)
    flash("Vorgemerkte Buchung verworfen.", "ok")
    return redirect(url_for("main.kassenbuch"))


@bp.route("/kasse/<int:bid>/gegenbuchung", methods=["POST"])
def kasse_gegenbuchung(bid):
    con = dbm.get_db()
    with dbm.Transaktion(con):
        kas.gegenbuchen(con, bid, _f("grund"))
    flash("Gegenbuchung erfasst.", "ok")
    return redirect(url_for("main.kassenbuch"))


@bp.route("/kasse/abschluss", methods=["POST"])
def kasse_abschluss():
    con = dbm.get_db()
    zaehlung = {str(w): int(request.form.get(f"anzahl_{w}") or 0) for w in kas.SCHEINE
                if (request.form.get(f"anzahl_{w}") or "").strip().isdigit() and int(request.form.get(f"anzahl_{w}"))}
    ist = cent_aus_text(_f("ist"), None)
    if ist is None and zaehlung:
        ist = sum(int(w) * n for w, n in zaehlung.items())
    with dbm.Transaktion(con):
        _, differenz = kas.tagesabschluss(con, _f("datum"), ist, _f("begruendung"), zaehlung or None)
    flash("Tagesabschluss gespeichert" + (f" – Differenz {euro(differenz)} gebucht." if differenz else
                                         " – Kasse stimmt."), "ok")
    return redirect(url_for("main.kassenbuch"))


@bp.route("/kasse/<int:bid>/beleg")
def kasse_beleg(bid):
    b = dbm.get_db().execute("SELECT * FROM kassenbuch WHERE id=?", (bid,)).fetchone()
    if not b or not b["beleg_datei"]:
        abort(404)
    pfad = Path(daten_dir()) / b["beleg_datei"]
    daten = pfad.read_bytes() if pfad.is_file() else None
    if daten is None or hashlib.sha256(daten).hexdigest() != b["beleg_sha256"]:
        return render_template("pdf_fehler.html", d={"nummer": f"Kassenbeleg {b['lfd_nr']}", "pdf_pfad": b["beleg_datei"],
                                                     "pdf_sha256": b["beleg_sha256"]}, fehlt=daten is None), 409
    endung = b["beleg_datei"].rsplit(".", 1)[-1].lower()
    return send_file(io.BytesIO(daten), mimetype=ek.ER_ENDUNGEN.get(endung, "application/octet-stream"),
                     download_name=b["beleg_name"] or f"Kassenbeleg_{b['lfd_nr']}.{endung}")


@bp.route("/datev", methods=["GET", "POST"])
def datev():
    con = dbm.get_db()
    heute_d = date.today()
    erster = heute_d.replace(day=1)
    vormonat_ende = erster.fromordinal(erster.toordinal() - 1)
    von = request.values.get("von") or vormonat_ende.replace(day=1).isoformat()
    bis = request.values.get("bis") or vormonat_ende.isoformat()
    erneut = bool(request.values.get("erneut"))
    if request.method == "POST":
        with dbm.Transaktion(con):
            eid = dtv.exportieren(con, von, bis, daten_dir(), erneut)
        flash("DATEV-Export erstellt.", "ok")
        return redirect(url_for("main.datev", von=von, bis=bis, neu=eid))
    try:
        vorschau = dtv.buchungen(con, von, bis, erneut)
    except ValueError:
        raise EingabeFehler("Bitte einen gültigen Zeitraum angeben.")
    einst = dbm.einstellungen(con)
    return render_template("datev.html", von=von, bis=bis, erneut=erneut, vorschau=vorschau,
                           exporte=con.execute("SELECT * FROM datev_exporte ORDER BY id DESC LIMIT 30").fetchall(),
                           neu=request.args.get("neu", type=int),
                           fehlt=not (einst.get("datev_beraternr") and einst.get("datev_mandantennr")))


@bp.route("/datev/<int:eid>/download")
def datev_download(eid):
    e = dbm.get_db().execute("SELECT * FROM datev_exporte WHERE id=?", (eid,)).fetchone()
    if not e:
        abort(404)
    pfad = Path(daten_dir()) / e["datei"]
    daten = pfad.read_bytes() if pfad.is_file() else None
    if daten is None or hashlib.sha256(daten).hexdigest() != e["sha256"]:
        return render_template("pdf_fehler.html", d={"nummer": f"DATEV-Export {e['von']}–{e['bis']}", "pdf_pfad": e["datei"],
                                                     "pdf_sha256": e["sha256"]}, fehlt=daten is None), 409
    return send_file(io.BytesIO(daten), mimetype="application/zip", as_attachment=True, download_name=Path(e["datei"]).name)


# ====================================================================== Dokumente

@bp.route("/verkauf/rechnungen")
def dokumente():
    return _dokumentliste(request.args.get("typ") or "rechnung")


@bp.route("/verkauf/kostenvoranschlaege")
def kostenvoranschlaege():
    return _dokumentliste("kva")


def _dokumentliste(typ):
    status = request.args.get("status", "")
    q = request.args.get("q", "").strip()
    sql = ("SELECT d.*, k.firma, k.vorname, k.nachname, k.typ AS ktyp FROM dokumente d "
           "LEFT JOIN kunden k ON k.id=d.kunde_id WHERE 1=1")
    args = []
    if status:
        sql += " AND d.status=?"
        args.append(status)
    if typ == "kva":
        sql += " AND d.typ='kva'"
    elif typ == "rechnung":
        sql += " AND d.typ IN ('rechnung','storno','gutschrift')"
    if q:
        sql += " AND (d.nummer LIKE ? OR d.betreff LIKE ? OR k.firma LIKE ? OR k.nachname LIKE ?)"
        args += [f"%{q}%"] * 4
    sql += " ORDER BY CASE d.status WHEN 'entwurf' THEN 0 ELSE 1 END, d.datum DESC, d.id DESC"
    con = dbm.get_db()
    liste = con.execute(sql, args).fetchall()
    zahlstatus = {d["id"]: _zlg().stand(con, d) for d in liste if d["typ"] == "rechnung" and d["status"] != "entwurf"}
    return render_template("dokumente.html", dokumente=liste, status=status, q=q, typ=typ, zahlstatus=zahlstatus)


def _zlg():
    from . import zahlungen
    return zahlungen


def _zahlungsziel(einst, kunde):
    return logik.zahlungsziel(einst, kunde)


@bp.route("/dokumente/neu")
def dokument_neu():
    con = dbm.get_db()
    typ = request.args.get("typ", "rechnung")
    if typ not in ("rechnung", "kva"):
        abort(400)
    with dbm.Transaktion(con):
        did = logik.neuer_entwurf(con, dbm.einstellungen(con), typ, request.args.get("kunde_id", type=int))
    return redirect(url_for("main.dokument", did=did))


def _dokument_laden(did):
    d = dbm.get_db().execute("SELECT * FROM dokumente WHERE id=?", (did,)).fetchone()
    if not d:
        abort(404)
    return d


@bp.route("/dokumente/<int:did>", methods=["GET", "POST"])
def dokument(did):
    con = dbm.get_db()
    d = _dokument_laden(did)
    einst = dbm.einstellungen(con)
    if request.method == "POST":
        if d["status"] != "entwurf":
            raise EingabeFehler("Festgeschriebene Dokumente können nicht mehr bearbeitet werden.")
        _entwurf_speichern(con, d, einst)
        aktion = request.form.get("aktion")
        if aktion == "vorschau":
            return redirect(url_for("main.dokument", did=did, vorschau=1))
        if aktion == "festschreiben":
            nummer = logik.festschreiben(con, did, daten_dir())
            with dbm.Transaktion(con):
                auf.dokument_ereignis(con, did, "KVA festgeschrieben", "Rechnung festgeschrieben")
                if d["typ"] == "kva":
                    ben.kva_ereignis(con, did, "festgeschrieben")
            _benachrichtigungen_automatisch()
            flash(f"{logik.titel(d['typ'])} {nummer} wurde festgeschrieben und archiviert.", "ok")
            return redirect(url_for("main.dokument", did=did))
        flash("Entwurf gespeichert.", "ok")
        return redirect(url_for("main.dokument", did=did))

    kunde = con.execute("SELECT * FROM kunden WHERE id=?", (d["kunde_id"],)).fetchone() if d["kunde_id"] else None
    g.auftrag = con.execute("SELECT * FROM auftraege WHERE kva_id=? OR rechnung_id=? LIMIT 1", (did, did)).fetchone()
    if d["status"] != "entwurf":
        snap = json.loads(d["snapshot_json"])
        versand = con.execute("SELECT * FROM versandprotokoll WHERE dokument_id=? ORDER BY id DESC", (did,)).fetchall()
        bezug = con.execute("SELECT id, nummer FROM dokumente WHERE id=?", (d["bezug_id"],)).fetchone()
        storno = con.execute("SELECT id, nummer FROM dokumente WHERE id=?", (d["storniert_durch"],)).fetchone()
        gutschriften = con.execute("SELECT id, nummer, status FROM dokumente WHERE bezug_id=? AND typ='gutschrift'",
                                   (did,)).fetchall()
        zahl = None
        if d["typ"] == "rechnung":
            from . import mahnwesen as mw
            zahl = {"stand": _zlg().stand(con, d), "zahlungen": _zlg().liste(con, did), "zahlarten": _zlg().ZAHLARTEN,
                    "mahnungen": con.execute("SELECT * FROM mahnungen WHERE dokument_id=? ORDER BY id", (did,)).fetchall(),
                    "naechste": mw.naechste_stufe(con, d, einst), "titel": mw.TITEL, "heute": heute()}
        return render_template("dokument_ansicht.html", d=d, snap=snap, kunde=kunde, versand=versand, zahl=zahl,
                               bezug=bezug, storno=storno, gutschriften=gutschriften,
                               aufbewahren_bis=logik.aufbewahren_bis(d, einst),
                               aenderungen=dbm.aenderungen_liste(con, "dokument", did))
    positionen = con.execute("SELECT * FROM positionen WHERE dokument_id=? ORDER BY pos", (did,)).fetchall()
    kunden_liste = con.execute("SELECT * FROM kunden WHERE archiviert=0 OR id=? "
                               "ORDER BY COALESCE(NULLIF(firma,''), nachname), vorname", (d["kunde_id"],)).fetchall()
    artikel_liste = [dict(a) for a in con.execute("SELECT * FROM artikel WHERE aktiv=1 ORDER BY leistungsart, name")]
    bausteine = [dict(t) for t in con.execute(
        "SELECT * FROM textbausteine WHERE kategorie IN ('einleitung','schluss','hinweis') "
        "AND dokumenttyp IN (?, 'alle') ORDER BY kategorie, name", (d["typ"],))]
    summen = logik.summen_berechnen(positionen, einst["steuer_modus"])
    konflikte = session.get("preis_konflikte")
    if konflikte and konflikte.get("dokument_id") != did:
        konflikte = None
    return render_template("dokument_bearbeiten.html", d=d, kunde=kunde, positionen=positionen, konflikte=konflikte,
                           kunden=kunden_liste, artikel=artikel_liste, bausteine=bausteine, summen=summen,
                           leistungsarten=_leistungsarten(), titel=logik.titel(d["typ"]),
                           vorschau=request.args.get("vorschau"), pflicht=logik.pflichtangaben_pruefen(con, d, einst),
                           aenderungen=dbm.aenderungen_liste(con, "dokument", did),
                           bezug=con.execute("SELECT id, nummer FROM dokumente WHERE id=?", (d["bezug_id"],)).fetchone()
                           if d["bezug_id"] else None)


DOKUMENT_FELDNAMEN = {"kunde_id": "Kunde (ID)", "datum": "Datum", "leistungsdatum": "Leistungsdatum",
                      "leistungsdatum_bis": "Leistungsdatum bis", "zahlungsziel_tage": "Zahlungsziel (Tage)",
                      "faellig_am": "Fällig am", "betreff": "Betreff", "einleitung": "Einleitung",
                      "schlusstext": "Schlusstext", "hinweise": "Hinweise", "steuer_modus": "Steuermodus",
                      "summe_netto": "Summe netto (Cent)", "summe_steuer": "Steuer (Cent)",
                      "summe_brutto": "Summe brutto (Cent)", "positionen": "Positionen"}


def _positionen_text(positionen):
    """Positionen als lesbarer Text für das Änderungsprotokoll."""
    return "\n".join(f"{p['pos']}. {p['bezeichnung']} | {menge_text(p['menge'])} {p['einheit'] or ''} × "
                     f"{euro(p['einzelpreis'])} | {p['steuersatz']:g} %" for p in positionen)


def _entwurf_speichern(con, d, einst):
    kid = request.form.get("kunde_id", type=int)
    kunde = con.execute("SELECT * FROM kunden WHERE id=?", (kid,)).fetchone() if kid else None
    datum = _f("datum") or heute()
    ziel = _f("zahlungsziel_tage")
    if ziel.isdigit():
        ziel = int(ziel)
    elif d["typ"] == "kva":
        ziel = int(einst.get("kva_gueltig_tage") or 30)
    else:
        ziel = _zahlungsziel(einst, kunde)
    try:
        faellig = plus_tage(datum, ziel)
        for feld in ("leistungsdatum", "leistungsdatum_bis"):
            if _f(feld):
                date.fromisoformat(_f(feld))
    except ValueError:
        raise EingabeFehler("Bitte ein gültiges Datum eingeben.")
    f = request.form
    anzahl = len(f.getlist("p_bezeichnung"))

    def liste(name, standard=""):
        werte = f.getlist(name)
        return werte + [standard] * (anzahl - len(werte))  # ältere Formulare ohne das Feld

    zeilen = zip(f.getlist("p_bezeichnung"), liste("p_beschreibung"), liste("p_menge", "1"), liste("p_einheit"),
                 liste("p_preis", "0"), liste("p_teilekosten"), liste("p_steuersatz", "19"), liste("p_leistungsart"),
                 liste("p_artikel_id"), liste("p_katalog", "0"), liste("p_typ"), liste("p_garantie"))
    positionen = []
    for bez, beschr, menge, einheit, preis, teile, satz, art, aid, katalog_flag, typ, garantie in zeilen:
        if not bez.strip():
            continue
        positionen.append({
            "bezeichnung": bez.strip(), "beschreibung": beschr.strip("\n\r "), "menge": zahl_aus_text(menge, 1),
            "einheit": einheit.strip(), "preis": cent_aus_text(preis),
            "teilekosten": cent_aus_text(teile, leer=None), "steuersatz": zahl_aus_text(satz, 19),
            "leistungsart": art.strip(), "artikel_id": int(aid) if aid.isdigit() else None,
            "katalog": katalog_flag == "1", "typ": typ,
            "garantie_monate": int(garantie) if garantie.strip().isdigit() else None,
        })
    if d["typ"] == "gutschrift":  # Gutschrift: Eingabe positiv, gespeichert als Minderung (negativ)
        for p in positionen:
            p["preis"], p["teilekosten"], p["katalog"] = -abs(p["preis"]), 0, False
    alt_kopf = dict(d)
    alt_pos = _positionen_text(con.execute("SELECT * FROM positionen WHERE dokument_id=? ORDER BY pos",
                                           (d["id"],)).fetchall())
    konflikte = []
    with dbm.Transaktion(con):
        con.execute(
            "UPDATE dokumente SET kunde_id=?, datum=?, leistungsdatum=?, leistungsdatum_bis=?, zahlungsziel_tage=?, "
            "faellig_am=?, betreff=?, einleitung=?, schlusstext=?, hinweise=?, steuer_modus=?, geaendert_am=? "
            "WHERE id=? AND status='entwurf'",
            (kunde["id"] if kunde else None, datum, _f("leistungsdatum") or None, _f("leistungsdatum_bis") or None,
             ziel, faellig, _f("betreff"), f.get("einleitung", ""), f.get("schlusstext", ""), f.get("hinweise", ""),
             einst["steuer_modus"], dbm.jetzt(), d["id"]))
        con.execute("DELETE FROM positionen WHERE dokument_id=?", (d["id"],))
        for i, p in enumerate(positionen, 1):
            if p["artikel_id"] is None and p["katalog"]:
                # manuell eingegebene Position -> in „Leistungen und Artikel“ übernehmen und verknüpfen
                p["artikel_id"], konflikt = katalog.uebernehmen(con, p)
                if konflikt:
                    konflikte.append(konflikt)
            con.execute(
                "INSERT INTO positionen (dokument_id, pos, bezeichnung, beschreibung, menge, einheit, einzelpreis, "
                "teilekosten, steuersatz, leistungsart, artikel_id, garantie_monate) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (d["id"], i, p["bezeichnung"], p["beschreibung"], p["menge"], p["einheit"], p["preis"],
                 p["teilekosten"] or 0, p["steuersatz"], p["leistungsart"], p["artikel_id"], p["garantie_monate"]))
        logik.summen_speichern(con, d["id"])
        neu_kopf = dict(con.execute("SELECT * FROM dokumente WHERE id=?", (d["id"],)).fetchone())
        neu_pos = _positionen_text(con.execute("SELECT * FROM positionen WHERE dokument_id=? ORDER BY pos",
                                               (d["id"],)).fetchall())
        dbm.aenderungen_erfassen(con, "dokument", d["id"], {**alt_kopf, "positionen": alt_pos},
                                 {**{f: neu_kopf[f] for f in DOKUMENT_FELDNAMEN if f in neu_kopf}, "positionen": neu_pos},
                                 namen=DOKUMENT_FELDNAMEN)
    if konflikte:
        session["preis_konflikte"] = {"dokument_id": d["id"], "liste": konflikte}


@bp.route("/artikel/preise-aktualisieren", methods=["POST"])
def artikel_preise_aktualisieren():
    """Antwort auf die Rückfrage „Preise im Katalog aktualisieren?“."""
    daten = session.pop("preis_konflikte", None) or {}
    con = dbm.get_db()
    if request.form.get("antwort") == "ja":
        gewaehlt = {int(i) for i in request.form.getlist("artikel_id") if i.isdigit()}
        with dbm.Transaktion(con):
            for k in daten.get("liste", []):
                if k["artikel_id"] in gewaehlt:
                    katalog.preise_aktualisieren(con, k["artikel_id"], k["neu_preis"], k["neu_ek"])
        flash(f"Preise von {len(gewaehlt)} Katalogeintrag/-einträgen aktualisiert.", "ok")
    else:
        flash("Katalogpreise bleiben unverändert.", "info")
    return redirect(url_for("main.dokument", did=daten["dokument_id"]) if daten.get("dokument_id")
                    else url_for("main.artikel_liste"))


@bp.route("/artikel/aus-dokumenten", methods=["GET", "POST"])
def artikel_aus_dokumenten():
    """Einmalige Übernahme: manuelle Positionen aus bisherigen Rechnungen und Kostenvoranschlägen."""
    con = dbm.get_db()
    if request.method == "POST":
        with dbm.Transaktion(con):
            n = katalog.aus_dokumenten_importieren(con, request.form.getlist("schluessel"))
        flash(f"{n} Einträge in „Leistungen und Artikel“ übernommen.", "ok")
        return redirect(url_for("main.artikel_liste"))
    return render_template("artikel_import.html", vorschlaege=katalog.aus_dokumenten_sammeln(con))


@bp.route("/dokumente/<int:did>/pdf")
def dokument_pdf(did):
    d = _dokument_laden(did)
    herunterladen = request.args.get("download") == "1"
    if d["status"] == "entwurf":
        snap = logik.snapshot_bauen(dbm.get_db(), did)
        pdf = pdf_erzeugen(snap, daten_dir=daten_dir(), entwurf=True)
        from io import BytesIO
        return send_file(BytesIO(pdf), mimetype="application/pdf", download_name=f"Entwurf_{did}.pdf",
                         as_attachment=herunterladen)
    pfad = Path(daten_dir()) / d["pdf_pfad"]
    import hashlib
    if not pfad.is_file() or hashlib.sha256(pfad.read_bytes()).hexdigest() != d["pdf_sha256"]:
        dbm.protokollieren("pdf_pruefsumme_fehler", "dokument", did, {"nummer": d["nummer"]})
        return render_template("pdf_fehler.html", d=d, fehlt=not pfad.is_file()), 409
    return send_file(pfad, mimetype="application/pdf", download_name=f"{d['nummer']}.pdf", as_attachment=herunterladen)


@bp.route("/dokumente/<int:did>/drucken")
def dokument_drucken(did):
    d = _dokument_laden(did)
    return render_template("drucken.html", d=d)


@bp.route("/dokumente/<int:did>/loeschen", methods=["POST"])
def dokument_loeschen(did):
    con = dbm.get_db()
    d = _dokument_laden(did)
    if d["status"] != "entwurf":
        raise EingabeFehler("Festgeschriebene Dokumente können nicht gelöscht werden. Bitte stornieren.")
    with dbm.Transaktion(con):
        for a in con.execute("SELECT id, kva_id FROM auftraege WHERE kva_id=? OR rechnung_id=?", (did, did)).fetchall():
            spalte = "kva_id" if a["kva_id"] == did else "rechnung_id"
            con.execute(f"UPDATE auftraege SET {spalte}=NULL WHERE id=?", (a["id"],))
            auf.verlauf(con, a["id"], "KVA-Entwurf gelöscht" if spalte == "kva_id" else "Rechnungsentwurf gelöscht")
        con.execute("UPDATE leihen SET rechnung_id=NULL WHERE rechnung_id=?", (did,))  # wieder abrechenbar
        con.execute("UPDATE schadensfaelle SET rechnung_id=NULL WHERE rechnung_id=?", (did,))
        con.execute("DELETE FROM positionen WHERE dokument_id=?", (did,))
        con.execute("DELETE FROM dokumente WHERE id=?", (did,))
        dbm.protokollieren("entwurf_geloescht", "dokument", did, con=con)
    flash("Entwurf gelöscht.", "ok")
    return redirect(url_for("main.dokumente"))


@bp.route("/dokumente/<int:did>/stornieren", methods=["POST"])
def dokument_stornieren(did):
    neu_id, nummer = logik.stornieren(dbm.get_db(), did, daten_dir(), _f("grund"))
    flash(f"Stornorechnung {nummer} wurde erstellt.", "ok")
    return redirect(url_for("main.dokument", did=neu_id))


@bp.route("/dokumente/<int:did>/gutschrift", methods=["POST"])
def dokument_gutschrift(did):
    con = dbm.get_db()
    _dokument_laden(did)
    with dbm.Transaktion(con):
        neu = logik.gutschrift_entwurf(con, did)
    flash("Gutschrift-Entwurf angelegt. Positionen/Beträge anpassen (Beträge positiv eingeben) und festschreiben.",
          "ok")
    return redirect(url_for("main.dokument", did=neu))


@bp.route("/dokumente/<int:did>/kopieren", methods=["POST"])
def dokument_kopieren(did):
    """Neuer Rechnungsentwurf mit denselben Positionen (Korrektur nach Storno oder KVA → Rechnung)."""
    con = dbm.get_db()
    d = _dokument_laden(did)
    pos = con.execute("SELECT * FROM positionen WHERE dokument_id=? ORDER BY pos", (did,)).fetchall()
    with dbm.Transaktion(con):
        neu = logik.neuer_entwurf(con, dbm.einstellungen(con), "rechnung", d["kunde_id"],
                                  d["betreff"] if d["typ"] in ("rechnung", "kva") else "", pos)
        if d["typ"] in ("rechnung", "kva") and d["hinweise"]:
            con.execute("UPDATE dokumente SET hinweise=? WHERE id=?", (d["hinweise"], neu))
        # gehört der KVA zu einem Reparaturauftrag ohne Rechnung -> Rechnung dort eintragen
        for a in con.execute("SELECT id FROM auftraege WHERE kva_id=? AND rechnung_id IS NULL", (did,)).fetchall():
            con.execute("UPDATE auftraege SET rechnung_id=?, geaendert_am=? WHERE id=?", (neu, dbm.jetzt(), a["id"]))
            auf.verlauf(con, a["id"], "Rechnung erstellt", f"Entwurf aus KVA {d['nummer'] or ''}".strip())
        dbm.protokollieren("entwurf_kopiert", "dokument", neu, {"von": d["nummer"] or did}, con=con)
    flash("Rechnungsentwurf aus dem Kostenvoranschlag erstellt." if d["typ"] == "kva"
          else "Neuer Entwurf als Kopie angelegt.", "ok")
    return redirect(url_for("main.dokument", did=neu))


@bp.route("/dokumente/<int:did>/email", methods=["GET", "POST"])
def dokument_email(did):
    con = dbm.get_db()
    d = _dokument_laden(did)
    if d["status"] == "entwurf":
        raise EingabeFehler("Bitte das Dokument zuerst festschreiben. Entwürfe werden nicht versendet.")
    einst = dbm.einstellungen(con)
    kunde = con.execute("SELECT * FROM kunden WHERE id=?", (d["kunde_id"],)).fetchone()
    if request.method == "POST":
        an = _f("an")
        if "@" not in an:
            raise EingabeFehler("Bitte eine gültige E-Mail-Adresse angeben.")
        pdf = (Path(daten_dir()) / d["pdf_pfad"]).read_bytes()
        weitere = []
        if d["e_format"] == "xrechnung" and d["xml_pfad"]:
            weitere.append(((Path(daten_dir()) / d["xml_pfad"]).read_bytes(), f"{d['nummer']}_xrechnung.xml"))
        try:
            hinweis = senden(con, None, an, _f("betreff"), request.form.get("text", ""), pdf, f"{d['nummer']}.pdf",
                             did, weitere=weitere)
        except MailFehler as e:
            flash(f"E-Mail wurde NICHT gesendet: {e}", "fehler")
            return redirect(url_for("main.dokument_email", did=did))
        flash(f"E-Mail an {an} wurde gesendet.", "ok")
        with dbm.Transaktion(con):
            auf.dokument_ereignis(con, did, "KVA per E-Mail versendet", "Rechnung per E-Mail versendet")
            if d["typ"] == "kva":
                ben.kva_ereignis(con, did, "email")
        if hinweis:
            flash(hinweis, "warnung")
        return redirect(url_for("main.dokument", did=did))
    bezug = con.execute("SELECT * FROM dokumente WHERE id=?", (d["bezug_id"],)).fetchone() if d["bezug_id"] else None
    werte = logik.platzhalter_werte(d, kunde, einst, bezug=bezug)
    texte = logik.standard_texte(con, d["typ"])
    return render_template("dokument_email.html", d=d, kunde=kunde,
                           an=(kunde["email"] if kunde else "") or "",
                           betreff=platzhalter_ersetzen(texte.get("email_betreff", "{nummer}"), werte),
                           text=platzhalter_ersetzen(texte.get("email_text", ""), werte),
                           smtp_ok=bool(einst.get("smtp_host")))


# ====================================================================== Einstellungen

EINSTELLUNGS_BEREICHE = {
    "firma": ["firma_name", "firma_zusatz", "inhaber", "strasse", "plz", "ort", "land", "telefon", "email", "web",
              "steuernummer", "ust_idnr", "bank_name", "kontoinhaber", "iban", "bic"],
    "rechnung": ["steuer_modus", "regel_steuersatz", "kleinunternehmer_hinweis", "zahlungsziel_privat",
                 "zahlungsziel_firma", "zahlungsarten_text", "kva_gueltig_tage", "anzahlung_prozent",
                 "nummern_format", "praefix_rechnung", "praefix_gutschrift", "praefix_angebot", "praefix_kunde",
                 "leistungsarten", "aufbewahrung_belege_jahre", "aufbewahrung_briefe_jahre"],
    "layout": ["farbe_primaer", "farbe_sekundaer", "schrift", "schriftgroesse", "logo_breite_mm", "logo_position",
               "kopfzeile_text", "fusszeile_text", "faltmarken", "girocode"],
    "email": ["smtp_host", "smtp_port", "smtp_sicherheit", "smtp_benutzer", "absender_name", "absender_email",
              "bcc_an_mich", "gesendet_aktiv", "gesendet_imap_host", "gesendet_imap_port", "gesendet_imap_sicherheit",
              "gesendet_gleiche_zugangsdaten", "gesendet_imap_benutzer", "gesendet_ordner"],
    "backup": ["backup_auto", "backup_ziel", "backup_behalten"],
    "programm": ["update_auto", "fenster_modus"],
    "vertraege": ["abo_modus", "vertrag_erinnerung_tage"],
    "leihgeraete": ["leihbedingungen"],
    "benachrichtigung": ["benachrichtigung_vorschau", "benachrichtigung_kanal", "erinnerung_tage", "oeffnungszeiten"]
    + [f"ben_{a}_{t}" for a in ben.ANLAESSE for t in ("aktiv", "betreff", "text")],
    "datev": ["datev_beraternr", "datev_mandantennr", "datev_skr", "datev_wj_beginn", "datev_kontenlaenge",
              "datev_debitor_start", "datev_kreditor_start", "datev_konten", "datev_kostenarten"],
    "datenschutz": ["ds_auto", "interessent_loeschen_monate", "ds_kunde_inaktiv_jahre", "ds_fotos_jahre",
                    "ds_leihe_jahre", "ds_vorschau_tage", "ds_zugang_tage", "ds_email_jahre", "ds_verantwortlicher"],
    "einkauf": ["mindest_marge_prozent", "praefix_bestellung", "praefix_eingangsrechnung", "kostenarten",
                "er_imap_ordner", "fixkosten_kategorien", "fixkosten_hinweis_tage", "wareneinsatz_kostenarten"],
    "annahme": ["garantie_monate", "garantie_text", "kva_gebuehren", "annahme_kva_text", "annahme_zubehoer",
                "annahme_datenschutz", "annahme_abholbedingungen",
                "abholschein_text", "handy_im_netz", "handy_adresse"],
    "mahnwesen": ["mahn_erinnerung_tage", "mahn_stufe1_tage", "mahn_stufe2_tage", "mahn_frist_tage", "mahngebuehr_cent",
                  "mahngebuehr_2_cent", "mahn_text_0", "mahn_text_1", "mahn_text_2", "mahn_email_betreff",
                  "mahn_email_text", "zinsen_aktiv", "basiszinssatz", "zinsen_aufschlag_privat",
                  "zinsen_aufschlag_firma", "zinsen_ab"],
    "anfragen": ["historie_aktiv", "historie_ordner_eingang", "historie_ordner_gesendet", "historie_zeitraum_tage",
                 "historie_eigene_adressen",
                 "anfragen_aktiv", "anfragen_intervall_min", "imap_host", "imap_port", "imap_sicherheit", "imap_benutzer",
                 "imap_ordner", "imap_zielordner", "imap_verschieben", "anfrage_erkennung", "anfrage_auto_kunde",
                 "anfrage_schwelle_unsicher", "anfrage_schwelle_spam", "anfrage_namensreihenfolge",
                 "interessent_loeschen_monate"],
}
JA_NEIN = {f"ben_{a}_aktiv" for a in ben.ANLAESSE} | {"ds_auto", "benachrichtigung_vorschau", "handy_im_netz", "zinsen_aktiv", "historie_aktiv", "gesendet_aktiv", "gesendet_gleiche_zugangsdaten", "update_auto", "faltmarken", "girocode", "bcc_an_mich", "backup_auto", "anfragen_aktiv", "imap_verschieben",
           "anfrage_auto_kunde"}
GANZZAHL = {"fixkosten_hinweis_tage", "ds_kunde_inaktiv_jahre", "ds_fotos_jahre", "ds_leihe_jahre", "ds_vorschau_tage", "ds_zugang_tage", "ds_email_jahre", "datev_kontenlaenge", "datev_debitor_start", "datev_kreditor_start", "mindest_marge_prozent", "garantie_monate", "mahn_erinnerung_tage", "mahn_stufe1_tage", "mahn_stufe2_tage", "mahn_frist_tage",
            "zinsen_aufschlag_privat", "zinsen_aufschlag_firma", "aufbewahrung_belege_jahre", "aufbewahrung_briefe_jahre", "historie_zeitraum_tage", "gesendet_imap_port", "vertrag_erinnerung_tage", "zahlungsziel_privat", "zahlungsziel_firma", "kva_gueltig_tage", "anzahlung_prozent", "mahnstufen", "smtp_port",
            "backup_behalten", "regel_steuersatz", "anfragen_intervall_min", "imap_port", "anfrage_schwelle_unsicher",
            "anfrage_schwelle_spam", "interessent_loeschen_monate"}
KOMMAZAHL = {"schriftgroesse", "logo_breite_mm"}


@bp.route("/einstellungen", methods=["GET", "POST"])
@bp.route("/einstellungen/<bereich>", methods=["GET", "POST"])
def einstellungen(bereich=None):
    if bereich is None:  # alte Adresse /einstellungen?bereich=… → /einstellungen/…
        bereich = request.args.get("bereich") or "firma"
        if request.method == "GET":
            weitere = {k: v for k, v in request.args.items() if k != "bereich"}
            return redirect(url_for("main.einstellungen", bereich=_bereich_gueltig(bereich), **weitere))
    bereich = _bereich_gueltig(bereich)
    if request.method == "POST" and bereich == "backup" and "backup_behalten" not in request.form:
        return backup_jetzt()  # Formular „Backup jetzt erstellen“ aus einer noch offenen alten Seite
    con = dbm.get_db()
    if request.method == "POST" and bereich in EINSTELLUNGS_BEREICHE:
        neu = {}
        for feld in EINSTELLUNGS_BEREICHE[bereich]:
            if feld in JA_NEIN:
                neu[feld] = bool(request.form.get(feld))
            elif feld in ("mahngebuehr_cent", "mahngebuehr_2_cent", "annahme_kva_gebuehr_cent"):
                neu[feld] = cent_aus_text(_f(feld))
            elif feld in GANZZAHL:
                neu[feld] = int(zahl_aus_text(_f(feld), 0))
            elif feld in KOMMAZAHL:
                neu[feld] = zahl_aus_text(_f(feld), 0)
            else:
                neu[feld] = _f(feld)
        from .hilfen import UNERLAUBT_IM_DATEINAMEN
        for k, v in neu.items():  # Präfixe und Nummernformat werden Teil von Dateinamen (Windows und Linux)
            if k == "nummern_format":
                try:
                    v = logik.nummer_formatieren(v, "RE", 2026, 1)  # geprüft wird das Ergebnis, z. B. RE-2026-0001
                except (KeyError, ValueError, IndexError):
                    continue  # ungültiges Format meldet die Prüfung weiter unten
            if (k.startswith("praefix_") or k == "nummern_format") and any(c in str(v) for c in UNERLAUBT_IM_DATEINAMEN):
                raise EingabeFehler("Präfixe und Nummernformat dürfen diese Zeichen nicht enthalten: "
                                    + " ".join(UNERLAUBT_IM_DATEINAMEN))
        if bereich == "firma":
            neu["iban"] = neu["iban"].replace(" ", "").upper()
        if bereich == "email" and request.form.get("smtp_passwort"):
            neu["smtp_passwort_enc"] = verschluesseln(request.form["smtp_passwort"])
        if bereich == "email" and request.form.get("gesendet_imap_passwort"):
            neu["gesendet_imap_passwort_enc"] = verschluesseln(request.form["gesendet_imap_passwort"])
        if bereich == "email":
            if neu["gesendet_imap_sicherheit"] not in ("ssl", "starttls"):
                neu["gesendet_imap_sicherheit"] = "ssl"
            if not 1 <= int(neu["smtp_port"] or 0) <= 65535:
                raise EingabeFehler("Bitte einen gültigen SMTP-Port angeben (587 für STARTTLS, 465 für SSL/TLS).")
            if neu["gesendet_aktiv"] and not neu["gesendet_imap_host"]:
                raise EingabeFehler("Für die Ablage im Gesendet-Ordner bitte einen IMAP-Server angeben.")
        if bereich == "benachrichtigung" and neu["benachrichtigung_kanal"] not in ben.KANAELE:
            neu["benachrichtigung_kanal"] = "email"
        if bereich == "annahme":
            if not auf.kva_gebuehren({"kva_gebuehren": neu["kva_gebuehren"]}):
                raise EingabeFehler("Bitte mindestens einen Gerätetyp mit Pauschale angeben, z. B. „Smartphone / Tablet "
                                    "= 19,00“.")
            neu["kva_gebuehren"] = "\n".join(f"{t} = {euro(c, False)}" for t, c in auf.kva_gebuehren(
                {"kva_gebuehren": neu["kva_gebuehren"]}))
            neu["annahme_kva_text"] = request.form.get("annahme_kva_text", "").strip()
            neu["garantie_text"] = request.form.get("garantie_text", "").strip()
        if bereich == "datev":
            if neu["datev_skr"] not in ("03", "04"):
                neu["datev_skr"] = "03"
            if not re.fullmatch(r"\d{2}-\d{2}", neu["datev_wj_beginn"] or ""):
                raise EingabeFehler("Beginn des Wirtschaftsjahres bitte als MM-TT angeben, z. B. 01-01.")
            for f in ("datev_beraternr", "datev_mandantennr"):
                if neu[f] and not neu[f].isdigit():
                    raise EingabeFehler("Berater- und Mandantennummer bestehen nur aus Ziffern.")
        if bereich == "anfragen" and neu["imap_sicherheit"] not in ("ssl", "starttls"):
            neu["imap_sicherheit"] = "ssl"
        if bereich == "anfragen":
            from .email_historie import ZEITRAUM, ordner_liste
            if neu["historie_zeitraum_tage"] not in ZEITRAUM:
                neu["historie_zeitraum_tage"] = 182
            neu["historie_ordner_eingang"] = "\n".join(ordner_liste(request.form.get("historie_ordner_eingang"))) \
                or "INBOX"
            neu["historie_ordner_gesendet"] = "\n".join(ordner_liste(request.form.get("historie_ordner_gesendet")))
            neu["historie_eigene_adressen"] = request.form.get("historie_eigene_adressen", "").strip()
        if bereich == "anfragen" and request.form.get("imap_passwort"):
            neu["imap_passwort_enc"] = verschluesseln(request.form["imap_passwort"])
        if bereich == "mahnwesen":
            if neu["zinsen_ab"] not in ("mahnung1", "faelligkeit"):
                neu["zinsen_ab"] = "mahnung1"
            basis = str(neu["basiszinssatz"]).strip().replace(",", ".")
            if basis:
                try:
                    float(basis)
                except ValueError:
                    raise EingabeFehler("Bitte den Basiszinssatz als Zahl angeben, z. B. 2,27.")
            if neu["zinsen_aktiv"] and not basis:
                raise EingabeFehler("Für Verzugszinsen bitte den aktuellen Basiszinssatz eintragen.")
            neu["basiszinssatz"] = basis
            for k in ("mahn_text_0", "mahn_text_1", "mahn_text_2", "mahn_email_text"):
                neu[k] = request.form.get(k, "").strip()
        if bereich == "vertraege" and neu["abo_modus"] not in ("entwurf", "automatisch"):
            neu["abo_modus"] = "entwurf"
        if bereich == "anfragen" and neu["anfrage_schwelle_spam"] <= neu["anfrage_schwelle_unsicher"]:
            raise EingabeFehler("Die Spam-Schwelle muss größer sein als die Schwelle für „unsicher“.")
        if bereich == "rechnung":
            if neu["aufbewahrung_belege_jahre"] < 8 or neu["aufbewahrung_briefe_jahre"] < 6:
                raise EingabeFehler("Die Aufbewahrungsfristen dürfen die gesetzlichen Mindestfristen nicht unterschreiten "
                                    "(Rechnungen/Buchungsbelege 8 Jahre, Geschäftsbriefe 6 Jahre).")
            if neu["praefix_gutschrift"].strip().upper() in (neu["praefix_rechnung"].strip().upper(),
                                                           neu["praefix_angebot"].strip().upper()):
                raise EingabeFehler("Gutschriften brauchen einen eigenen Nummernkreis – bitte ein anderes Präfix wählen.")
            if neu["steuer_modus"] not in ("kleinunternehmer", "regel"):
                neu["steuer_modus"] = "kleinunternehmer"
            try:
                logik.nummer_formatieren(neu["nummern_format"], "RE", 2026, 1)
                neu["nummern_format"].format(praefix="RE", jahr=2026, nummer=1)
            except (KeyError, ValueError, IndexError):
                raise EingabeFehler("Das Nummernformat ist ungültig. Beispiel: {praefix}-{jahr}-{nummer:04d}")
        with dbm.Transaktion(con):
            alt = dbm.einstellungen(con)
            dbm.einstellungen_speichern(neu, con)
            geheim = ("smtp_passwort_enc", "imap_passwort_enc", "gesendet_imap_passwort_enc")
            geaendert = {k: v for k, v in neu.items() if alt.get(k) != v and k not in geheim}
            for k in geheim:
                if k in neu:
                    geaendert[k.replace("_enc", "")] = "(geändert)"
            dbm.protokollieren("einstellungen_geaendert", "einstellungen", None, geaendert, con=con)
        flash("Einstellungen gespeichert.", "ok")
        return redirect(url_for("main.einstellungen", bereich=bereich))
    return render_template("einstellungen.html", **_einstellungs_werte(bereich), gruppen=nav.EINSTELLUNGS_GRUPPEN,
                           verwaltung=nav.VERWALTUNG)


def _bereich_gueltig(bereich):
    return bereich if bereich in EINSTELLUNGS_BEREICHE or bereich == "sicherheit" else "firma"


def _einstellungs_werte(bereich):
    extra = {}
    if bereich == "backup":
        from . import wiederherstellung as wh
        extra = dict(wh_quellen=wh.quellen(daten_dir(), None if request.args.get("suche") else []),
                     daten_ordner=daten_dir(), onedrive="onedrive" in str(daten_dir()).lower())
    return dict(**extra,bereich=bereich, bereich_titel=nav.BEREICHS_TITEL.get(bereich, "Einstellungen"),
                schriften=list(SCHRIFTEN), smtp_passwort_gesetzt=bool(dbm.einstellung("smtp_passwort_enc")),
                gesendet_passwort_gesetzt=bool(dbm.einstellung("gesendet_imap_passwort_enc")),
                imap_passwort_gesetzt=bool(dbm.einstellung("imap_passwort_enc")), backups=_backup_liste())


_EINSTELLUNGS_INDEX = {}


def einstellungs_index():
    """Alle Abschnitte und Felder der Einstellungen (für die Suche) – aus den gerenderten Seiten gelesen."""
    if "liste" not in _EINSTELLUNGS_INDEX:
        from .einstellungs_suche import felder_lesen
        liste = []
        for _, eintraege in nav.EINSTELLUNGS_GRUPPEN:
            for b, titel, _ in eintraege:
                html = render_template("_einstellungen_inhalt.html", **_einstellungs_werte(b))
                liste.append({"bereich": b, "bereich_titel": titel, "abschnitt": "", "feld": "", "titel": titel,
                              "anker": ""})
                for f in felder_lesen(html):
                    liste.append({"bereich": b, "bereich_titel": titel, **f})
        _EINSTELLUNGS_INDEX["liste"] = liste
    return _EINSTELLUNGS_INDEX["liste"]


@bp.route("/einstellungen/suche.json")
def einstellungen_suche():
    q = request.args.get("q", "")
    return jsonify([{**t, "url": url_for("main.einstellungen", bereich=t["bereich"]) + (f"#{t['anker']}" if t["anker"]
                                                                                     else "")}
                    for t in einstellungen_treffer(q, 30)])


def einstellungen_treffer(q, limit=8):
    from .einstellungs_suche import passt
    return [t for t in einstellungs_index() if passt(q, t)][:limit]


def _backup_liste():
    ordner = Path(daten_dir()) / "backups"
    return sorted(((p.name, p.stat().st_size) for p in ordner.glob("backup_*.zip")), reverse=True)[:10]


@bp.route("/einstellungen/logo", methods=["POST"])
def logo_hochladen():
    datei = request.files.get("logo")
    con = dbm.get_db()
    if request.form.get("entfernen"):
        with dbm.Transaktion(con):
            dbm.einstellungen_speichern({"logo_datei": ""}, con)
            dbm.protokollieren("logo_entfernt", "einstellungen", con=con)
        flash("Eigenes Logo entfernt, das Standardlogo wird verwendet.", "ok")
        return redirect(url_for("main.einstellungen", bereich="layout"))
    if not datei or not datei.filename:
        raise EingabeFehler("Bitte eine Bilddatei auswählen.")
    try:
        bild = Image.open(datei.stream)
        bild.load()
    except Exception:
        raise EingabeFehler("Die Datei konnte nicht als Bild gelesen werden (erlaubt: PNG, JPG).")
    rel = Path("bilder") / f"logo_{date.today():%Y%m%d}_{abs(hash(datei.filename)) % 10000}.png"
    bild.convert("RGBA").save(Path(daten_dir()) / rel)
    with dbm.Transaktion(con):
        dbm.einstellungen_speichern({"logo_datei": rel.as_posix()}, con)
        dbm.protokollieren("logo_geaendert", "einstellungen", None, {"datei": rel.as_posix()}, con=con)
    flash("Logo gespeichert.", "ok")
    return redirect(url_for("main.einstellungen", bereich="layout"))


@bp.route("/einstellungen/logo.png")
def logo_anzeigen():
    eigen = dbm.einstellung("logo_datei")
    pfad = Path(daten_dir()) / eigen if eigen else None
    if not pfad or not pfad.is_file():
        pfad = Path(__file__).parent / "static" / "bilder" / "logo_standard.png"
    return send_file(pfad, mimetype="image/png")


@bp.route("/einstellungen/musterrechnung.pdf")
def musterrechnung():
    """Zeigt das aktuelle Layout mit Beispieldaten – ohne etwas zu speichern."""
    einst = dbm.einstellungen()
    pos = [
        {"pos": 1, "bezeichnung": "Akkutausch Smartphone", "beschreibung": "inkl. Ersatzakku und Funktionstest",
         "menge": 1, "einheit": "Stk.", "einzelpreis": 7900, "steuersatz": 19, "betrag": 7900},
        {"pos": 2, "bezeichnung": "Kaffeemaschinen-Wartung", "beschreibung": "Entkalken, Brühgruppe reinigen",
         "menge": 1, "einheit": "pauschal", "einzelpreis": 8900, "steuersatz": 19, "betrag": 8900},
    ]
    s = logik.summen_berechnen(pos, einst["steuer_modus"])
    texte = logik.standard_texte(dbm.get_db(), "rechnung")
    werte = {"anrede_brief": "Sehr geehrte Frau Muster,", "nummer": "RE-2026-0000", "betrag": euro(s["brutto"]),
             "faellig_am": "28.10.2026", "datum": "14.10.2026", "inhaber": einst["inhaber"],
             "firma_name": einst["firma_name"]}
    snap = {
        "typ": "rechnung", "titel": "Rechnung", "nummer": "RE-2026-0000", "datum": heute(), "leistungsdatum": heute(),
        "leistungsdatum_bis": None, "faellig_am": plus_tage(heute(), 14), "betreff": "Musterrechnung (Layoutvorschau)",
        "einleitung": platzhalter_ersetzen(texte.get("einleitung", ""), werte),
        "schlusstext": platzhalter_ersetzen(texte.get("schluss", ""), werte), "hinweise": "",
        "steuer_modus": einst["steuer_modus"],
        "kleinunternehmer_hinweis": einst["kleinunternehmer_hinweis"] if einst["steuer_modus"] == "kleinunternehmer" else "",
        "zahlungsarten_text": einst["zahlungsarten_text"], "bezug": None,
        "kunde": {"kundennr": "K-0000", "name": "Erika Muster",
                  "anschrift": ["Frau Erika Muster", "Musterweg 1", "12345 Musterstadt"], "ust_idnr": "", "typ": "privat"},
        "firma": {k: einst.get(k, "") for k in logik.FIRMA_FELDER},
        "layout": {k: einst.get(k) for k in logik.LAYOUT_FELDER},
        "positionen": pos, "summen": s,
    }
    from io import BytesIO
    return send_file(BytesIO(pdf_erzeugen(snap, daten_dir=daten_dir(), entwurf=True)), mimetype="application/pdf",
                     download_name="Musterrechnung.pdf")


@bp.route("/einstellungen/testmail", methods=["POST"])
def testmail():
    con = dbm.get_db()
    einst = dbm.einstellungen(con)
    an = _f("an") or einst.get("absender_email")
    try:
        hinweis = senden(con, {"bcc_an_mich": False}, an, "Test-E-Mail aus der Buchhaltung",
                         "Diese Test-E-Mail bestätigt, dass der E-Mail-Versand funktioniert.")
        flash(f"Test-E-Mail an {an} gesendet." + (" Eine Kopie liegt im Gesendet-Ordner."
                                                   if einst.get("gesendet_aktiv") and not hinweis else ""), "ok")
        if hinweis:
            flash(hinweis, "warnung")
    except MailFehler as e:
        flash(f"Test fehlgeschlagen: {e}", "fehler")
    return redirect(url_for("main.einstellungen", bereich="email"))


@bp.route("/einstellungen/passwort", methods=["POST"])
def passwort_aendern():
    """Passwortschutz ein-/ausschalten oder Passwort ändern."""
    con = dbm.get_db()
    aktion = request.form.get("aktion", "aendern")
    if aktion == "aus":
        with dbm.Transaktion(con):
            dbm.einstellungen_speichern({"login_aktiv": False}, con)
            dbm.protokollieren("passwortschutz_aus", "system", con=con)
        flash("Passwortschutz ausgeschaltet. Das Programm öffnet sich ohne Anmeldung.", "ok")
        return redirect(url_for("main.einstellungen", bereich="sicherheit"))
    bisher = dbm.einstellung("passwort_hash")
    if aktion == "aendern" and bisher and not check_password_hash(bisher, request.form.get("alt", "")):
        raise EingabeFehler("Das bisherige Passwort ist falsch.")
    neu = request.form.get("neu", "")
    if len(neu) < 8 or neu != request.form.get("neu2"):
        raise EingabeFehler("Das Passwort muss mindestens 8 Zeichen haben und zweimal gleich eingegeben werden.")
    with dbm.Transaktion(con):
        werte = {"passwort_hash": generate_password_hash(neu)}
        if aktion == "an":
            werte["login_aktiv"] = True
        dbm.einstellungen_speichern(werte, con)
        dbm.protokollieren("passwortschutz_an" if aktion == "an" else "passwort_geaendert", "system", con=con)
    flash("Passwortschutz eingeschaltet." if aktion == "an" else "Passwort geändert.", "ok")
    return redirect(url_for("main.einstellungen", bereich="sicherheit"))


@bp.route("/einstellungen/backup/erstellen", methods=["POST"])
def backup_jetzt():
    con = dbm.get_db()
    einst = dbm.einstellungen(con)
    ziel, extern = backup_erstellen(daten_dir(), current_app.config["DB_PFAD"], einst)
    with dbm.Transaktion(con):
        dbm.einstellungen_speichern({"letztes_backup": dbm.jetzt()}, con)
        dbm.protokollieren("backup_manuell", "system", None, {"datei": ziel.name, "extern": extern}, con=con)
    meldung = f"Backup {ziel.name} erstellt."
    if extern:
        meldung += f" Kopie: {extern}"
    flash(meldung, "fehler" if extern and extern.startswith("FEHLER") else "ok")
    return redirect(url_for("main.einstellungen", bereich="backup"))


@bp.route("/einstellungen/backup/<name>")
def backup_herunterladen(name):
    pfad = Path(daten_dir()) / "backups" / Path(name).name
    if not pfad.is_file() or not pfad.name.startswith("backup_"):
        abort(404)
    return send_file(pfad, as_attachment=True)


# ====================================================================== Textbausteine

@bp.route("/textbausteine")
def textbausteine():
    liste = dbm.get_db().execute("SELECT * FROM textbausteine ORDER BY dokumenttyp, kategorie, name").fetchall()
    return render_template("textbausteine.html", liste=liste)


TB_KATEGORIEN = {"einleitung": "Einleitung", "schluss": "Schlusstext", "hinweis": "Hinweis",
                 "email_betreff": "E-Mail-Betreff", "email_text": "E-Mail-Text"}
TB_TYPEN = {"alle": "Alle Dokumente", "rechnung": "Rechnung", "storno": "Stornorechnung", "kva": "Kostenvoranschlag"}


@bp.route("/textbausteine/neu", methods=["GET", "POST"])
@bp.route("/textbausteine/<int:tid>", methods=["GET", "POST"])
def textbaustein(tid=None):
    con = dbm.get_db()
    t = con.execute("SELECT * FROM textbausteine WHERE id=?", (tid,)).fetchone() if tid else None
    if request.method == "POST":
        if request.form.get("loeschen") and t:
            with dbm.Transaktion(con):
                con.execute("DELETE FROM textbausteine WHERE id=?", (tid,))
                dbm.protokollieren("textbaustein_geloescht", "textbaustein", tid, con=con)
            flash("Textbaustein gelöscht.", "ok")
            return redirect(url_for("main.textbausteine"))
        kat, typ = _f("kategorie"), _f("dokumenttyp")
        if kat not in TB_KATEGORIEN or typ not in TB_TYPEN or not _f("name"):
            raise EingabeFehler("Bitte Name, Kategorie und Dokumenttyp angeben.")
        standard = 1 if request.form.get("standard") else 0
        with dbm.Transaktion(con):
            if standard:
                con.execute("UPDATE textbausteine SET standard=0 WHERE kategorie=? AND dokumenttyp=?", (kat, typ))
            werte = (kat, typ, _f("name"), request.form.get("text", ""), standard)
            if t:
                con.execute("UPDATE textbausteine SET kategorie=?, dokumenttyp=?, name=?, text=?, standard=? "
                            "WHERE id=?", (*werte, tid))
            else:
                tid = con.execute("INSERT INTO textbausteine (kategorie, dokumenttyp, name, text, standard) "
                                  "VALUES (?,?,?,?,?)", werte).lastrowid
            dbm.protokollieren("textbaustein_gespeichert", "textbaustein", tid, con=con)
        flash("Textbaustein gespeichert.", "ok")
        return redirect(url_for("main.textbausteine"))
    return render_template("textbaustein.html", t=t, kategorien=TB_KATEGORIEN, typen=TB_TYPEN,
                           platzhalter=PLATZHALTER_HILFE)


# ====================================================================== Protokoll & Prüfung

@bp.route("/protokoll")
def protokoll():
    con = dbm.get_db()
    eintraege = con.execute("SELECT * FROM protokoll ORDER BY id DESC LIMIT 300").fetchall()
    versand = con.execute("SELECT v.*, d.nummer FROM versandprotokoll v LEFT JOIN dokumente d ON d.id=v.dokument_id "
                          "ORDER BY v.id DESC LIMIT 100").fetchall()
    return render_template("protokoll.html", eintraege=eintraege, versand=versand)


@bp.route("/pruefung")
def pruefung():
    ergebnis = logik.integritaet_pruefen(dbm.get_db(), daten_dir())
    return render_template("pruefung.html", e=ergebnis)


@bp.route("/verfahrensdokumentation")
def verfahrensdokumentation():
    from . import VERSION_NUMMER
    from . import verfahrensdoku as vd
    abschnitte = vd.inhalt(dbm.get_db(), daten_dir(), VERSION_NUMMER)
    if request.args.get("pdf"):
        from io import BytesIO
        return send_file(BytesIO(vd.pdf(abschnitte, dbm.einstellung("firma_name") or "")), mimetype="application/pdf",
                         download_name=f"Verfahrensdokumentation_{date.today().isoformat()}.pdf",
                         as_attachment=request.args.get("download") == "1")
    return render_template("verfahrensdoku.html", abschnitte=abschnitte, ergaenzen=vd.ERGAENZEN, markiert=vd.markiert)


@bp.app_template_filter("kname")
def _kname(row):
    d = dict(row) if row else {}
    if "ktyp" in d and not d.get("typ"):
        d["typ"] = d["ktyp"]
    return kunde_name(d)


# ====================================================================== Anfragen (Kontaktformular)

from . import anfragen as anf  # noqa: E402

ANFRAGE_FILTER = {
    "offen": ("Zu prüfen", "status='neu' AND einstufung<>'spam'"),
    "kunden": ("Kunde angelegt/zugeordnet", "status IN ('kunde_angelegt','zugeordnet')"),
    "spam": ("Spam", "status='neu' AND einstufung='spam'"),
    "verworfen": ("Verworfen", "status='verworfen'"),
    "alle": ("Alle", "1=1"),
}


@bp.route("/anfragen")
def anfragen_liste():
    con = dbm.get_db()
    filt = request.args.get("filter", "offen")
    if filt not in ANFRAGE_FILTER:
        filt = "offen"
    liste = con.execute(f"SELECT a.*, k.kundennr FROM anfragen a LEFT JOIN kunden k ON k.id=a.kunde_id "
                        f"WHERE {ANFRAGE_FILTER[filt][1]} ORDER BY a.eingang_am DESC LIMIT 300").fetchall()
    anzahl = {k: con.execute(f"SELECT COUNT(*) FROM anfragen WHERE {w}").fetchone()[0]
              for k, (_, w) in ANFRAGE_FILTER.items()}
    loeschvorschlaege = anf.interessenten_zum_loeschen(con, dbm.einstellungen(con))
    return render_template("anfragen.html", liste=liste, filt=filt, filter=ANFRAGE_FILTER, anzahl=anzahl,
                           loeschvorschlaege=loeschvorschlaege, anzeigename=anf.anfrage_anzeigename)


@bp.route("/anfragen/abrufen", methods=["POST"])
def anfragen_abrufen():
    try:
        e = anf.abruf_mit_protokoll(dbm.get_db())
    except anf.AbrufFehler as fehler:
        flash(str(fehler), "fehler")
        return redirect(url_for("main.anfragen_liste"))
    flash(f"Postfach geprüft: {e['neu']} neue Anfrage(n) – {e['echt']} echt, {e['unsicher']} unsicher, "
          f"{e['spam']} Spam. {e['verschoben']} E-Mail(s) in den Ordner „{dbm.einstellung('imap_zielordner')}“ "
          f"verschoben.", "ok")
    return redirect(url_for("main.anfragen_liste"))


@bp.route("/anfragen/einfuegen", methods=["GET", "POST"])
def anfrage_einfuegen():
    """Formular-E-Mail per Kopieren/Einfügen übernehmen (z. B. zum Testen oder ohne IMAP)."""
    if request.method == "POST":
        text = request.form.get("text", "").strip()
        if not text:
            raise EingabeFehler("Bitte den Text der Anfrage einfügen.")
        if "<" in text and ">" in text and re.search(r"</?(p|div|br|td|strong)\b", text, re.I):
            text = anf.html_zu_text(text)
        con = dbm.get_db()
        aid = anf.verarbeiten(con, text, dbm.einstellungen(con), quelle="manuell")
        return redirect(url_for("main.anfrage", aid=aid))
    return render_template("anfrage_einfuegen.html")


def _anfrage_laden(aid):
    a = dbm.get_db().execute("SELECT * FROM anfragen WHERE id=?", (aid,)).fetchone()
    if not a:
        abort(404)
    return a


@bp.route("/anfragen/<int:aid>")
def anfrage(aid):
    con = dbm.get_db()
    a = _anfrage_laden(aid)
    kunde = con.execute("SELECT * FROM kunden WHERE id=?", (a["kunde_id"],)).fetchone() if a["kunde_id"] else None
    vorhanden = None if kunde else anf.passender_kunde(con, a["email"], a["telefon"])
    g.auftrag = con.execute("SELECT * FROM auftraege WHERE anfrage_id=? LIMIT 1", (aid,)).fetchone()
    return render_template("anfrage.html", a=a, kunde=kunde, vorhanden=vorhanden,
                           felder=json.loads(a["felder_json"] or "{}"), gruende=json.loads(a["gruende_json"] or "[]"),
                           leistungsart=anf.geraet_zu_leistungsart(a["geraet"]), anzeigename=anf.anfrage_anzeigename)


@bp.route("/anfragen/<int:aid>/aktion", methods=["POST"])
def anfrage_aktion(aid):
    con = dbm.get_db()
    a = _anfrage_laden(aid)
    aktion = request.form.get("aktion")
    with dbm.Transaktion(con):
        if aktion == "kunde":
            if a["kunde_id"]:
                raise EingabeFehler("Zu dieser Anfrage gibt es bereits einen Kunden.")
            con.execute("UPDATE anfragen SET vorname=?, nachname=? WHERE id=?",
                        (_f("vorname"), _f("nachname"), aid))
            kid, neu = anf.kunde_aus_anfrage(con, aid, dbm.einstellungen(con), _f("vorname"), _f("nachname"))
            meldung = "Kunde als Interessent angelegt." if neu else "Anfrage dem vorhandenen Kunden zugeordnet."
        elif aktion == "verwerfen":
            con.execute("UPDATE anfragen SET status='verworfen', bearbeitet_am=? WHERE id=?", (dbm.jetzt(), aid))
            dbm.protokollieren("anfrage_verworfen", "anfrage", aid, con=con)
            meldung, kid = "Anfrage verworfen (wird nach 30 Tagen automatisch gelöscht).", None
        elif aktion == "spam":
            con.execute("UPDATE anfragen SET einstufung='spam', status='neu', bearbeitet_am=? WHERE id=?",
                        (dbm.jetzt(), aid))
            dbm.protokollieren("anfrage_als_spam", "anfrage", aid, con=con)
            meldung, kid = "Als Spam markiert.", None
        elif aktion == "kein_spam":
            con.execute("UPDATE anfragen SET einstufung='unsicher', bearbeitet_am=? WHERE id=?", (dbm.jetzt(), aid))
            dbm.protokollieren("anfrage_kein_spam", "anfrage", aid, con=con)
            meldung, kid = "Anfrage zurück in „Zu prüfen“ verschoben.", None
        else:
            abort(400)
    flash(meldung, "ok")
    if kid and request.form.get("danach") == "kunde":
        return redirect(url_for("main.kunde", kid=kid))
    return redirect(url_for("main.anfrage", aid=aid))


@bp.route("/anfragen/interessenten-loeschen", methods=["POST"])
def interessenten_loeschen():
    con = dbm.get_db()
    ids = [int(i) for i in request.form.getlist("kunde_id") if i.isdigit()]
    erlaubt = {k["id"] for k in anf.interessenten_zum_loeschen(con, dbm.einstellungen(con))}
    with dbm.Transaktion(con):
        for kid in ids:
            if kid in erlaubt:
                con.execute("DELETE FROM anfragen WHERE kunde_id=?", (kid,))
                con.execute("DELETE FROM kunden WHERE id=?", (kid,))
                dbm.protokollieren("interessent_geloescht", "kunde", kid, "Löschfrist abgelaufen, kein Auftrag",
                                   con=con)
    flash(f"{len([i for i in ids if i in erlaubt])} Interessent(en) gelöscht.", "ok")
    return redirect(url_for("main.anfragen_liste"))


# ====================================================================== Reparaturaufträge (Tafel)

from . import annahme as ann  # noqa: E402
from . import garantie as gar  # noqa: E402
from . import annahme_pdf as ann_pdf  # noqa: E402
from . import auftraege as auf  # noqa: E402
from . import fotos as fot  # noqa: E402

AUFTRAG_SQL = (
    "SELECT a.*, k.kundennr, k.firma, k.vorname, k.nachname, k.typ AS ktyp, k.telefon AS ktelefon, "
    "kv.status AS kva_status, kv.nummer AS kva_nummer, kv.summe_brutto AS kva_betrag, kv.datum AS kva_datum, "
    "kv.kva_status AS kva_entscheidung, kv.kunde_id AS kva_kunde_id, kv.versendet_am AS kva_versendet_am, "
    "re.status AS re_status, re.nummer AS re_nummer, re.summe_brutto AS re_betrag, "
    "(SELECT COUNT(*) FROM auftrag_fotos f WHERE f.auftrag_id=a.id AND f.geloescht_am IS NULL) AS foto_anzahl, "
    "(SELECT COUNT(*) FROM leihen l WHERE l.auftrag_id=a.id AND l.rueckgabe_am IS NULL AND l.storniert_am IS NULL) "
    "AS leihen_offen, (SELECT MIN(l.rueckgabe_geplant) FROM leihen l WHERE l.auftrag_id=a.id "
    "AND l.rueckgabe_am IS NULL AND l.storniert_am IS NULL) AS leihe_bis, "
    "(a.kunde_id = (SELECT CAST(wert AS INTEGER) FROM einstellungen WHERE schluessel='interner_kunde_id')) AS intern "
    "FROM auftraege a JOIN kunden k ON k.id=a.kunde_id "
    "LEFT JOIN dokumente kv ON kv.id=a.kva_id LEFT JOIN dokumente re ON re.id=a.rechnung_id ")


def _kunden_liste(con, auch_id=None):
    return con.execute("SELECT * FROM kunden WHERE archiviert=0 OR id=? "
                       "ORDER BY COALESCE(NULLIF(firma,''), nachname), vorname", (auch_id or 0,)).fetchall()


@bp.route("/auftraege")
def auftraege():
    con = dbm.get_db()
    alle_erledigten = request.args.get("alle") == "1"
    spalten = {}
    for status in auf.TAFEL:
        sql = AUFTRAG_SQL + "WHERE a.status=? "
        args = ["in_arbeit" if status == "wartet_teil" else status]
        if status == "in_arbeit":
            sql += "AND a.wartet_teil_seit IS NULL "
        if status == "wartet_teil":
            sql += "AND a.wartet_teil_seit IS NOT NULL "
        if status == "erledigt" and not alle_erledigten:
            sql += "AND a.erledigt_am >= date('now', '-30 day') "
        sql += "ORDER BY a.reihenfolge, a.id"
        spalten[status] = con.execute(sql, args).fetchall()
    with dbm.Transaktion(con):
        ben.erinnerungen_pruefen(con)
    return render_template("auftraege.html", spalten=spalten, status_namen=auf.TAFEL, leihe_offen_text=LEIHE_OFFEN_TEXT,
                           alle_erledigten=alle_erledigten, heute=date.today().isoformat(),
                           benachrichtigungen=ben.offene(con), anlaesse=ben.ANLAESSE)


def _auftrag_felder():
    felder = {f: _f(f) for f in ("geraet", "leistungsart", "seriennummer", "zubehoer", "fehler", "notizen")}
    if "annahme_felder" not in request.form:  # z. B. Auftrag aus einer Anfrage
        return felder
    vorlagen = ann.zubehoer_vorlagen(dbm.einstellungen())
    felder["zubehoer"] = ann.zubehoer_zusammen(set(request.form.getlist("zubehoer_check")), _f("zubehoer_sonstiges"),
                                               vorlagen)
    felder["zustand_eingang"] = _f("zustand_eingang")
    felder["kosten_obergrenze"] = cent_aus_text(_f("kosten_obergrenze"), None) or None
    felder["kva_gewuenscht"] = 1 if request.form.get("kva_gewuenscht") else 0
    felder["geraetetyp"] = _f("geraetetyp") or None
    if request.form.get("kva_kostenlos"):
        felder["kva_gebuehr"] = 0
    elif _f("kva_gebuehr"):
        felder["kva_gebuehr"] = cent_aus_text(_f("kva_gebuehr"))
    else:  # leer = Pauschale des Gerätetyps laut Einstellungen
        felder["kva_gebuehr"] = auf.kva_gebuehr_fuer(dbm.einstellungen(), felder["geraetetyp"])
    fertig = _f("fertig_bis")
    if fertig:
        try:
            date.fromisoformat(fertig)
        except ValueError:
            raise EingabeFehler("Bitte ein gültiges Datum für die voraussichtliche Fertigstellung angeben.")
    felder["fertig_bis"] = fertig or None
    felder["teil_info"] = _f("teil_info")
    felder["teil_erwartet"] = _f("teil_erwartet") or None
    felder["auftragsart"] = _f("auftragsart") if _f("auftragsart") in gar.AUFTRAGSARTEN else "reparatur"
    felder["garantie_bezug_id"] = request.form.get("garantie_bezug_id", type=int) \
        if felder["auftragsart"] == "garantie" else None
    felder["garantie_monate"] = int(_f("garantie_monate")) if _f("garantie_monate").isdigit() else None
    felder["interne_kosten"] = cent_aus_text(_f("interne_kosten"), None) or None
    felder["interne_kosten_notiz"] = _f("interne_kosten_notiz")
    return felder


def _zugang_aus_formular(con, aid):
    if "annahme_felder" in request.form:
        ann.zugang_setzen(con, aid, _f("zugang_art"), request.form.get("zugang_wert", ""),
                          loeschen=bool(request.form.get("zugang_loeschen")))


def _norm(x):
    return "" if x is None else str(x)


FELD_NAMEN = {"geraet": "Gerät", "leistungsart": "Leistungsart", "seriennummer": "Seriennr./IMEI",
              "zubehoer": "Zubehör", "fehler": "Fehlerbeschreibung", "notizen": "Notizen", "kunde_id": "Kunde",
              "zustand_eingang": "Zustand bei Eingang", "kosten_obergrenze": "Kosten-Obergrenze",
              "kva_gewuenscht": "KVA gewünscht", "kva_gebuehr": "KVA-Pauschale", "geraetetyp": "Gerätetyp",
              "fertig_bis": "voraussichtliche Fertigstellung", "teil_info": "Ersatzteil",
              "teil_erwartet": "Ersatzteil erwartet am", "auftragsart": "Auftragsart",
              "garantie_bezug_id": "Garantie-Bezug", "garantie_monate": "Garantie (Monate)",
              "interne_kosten": "interne Kosten", "interne_kosten_notiz": "Notiz interne Kosten"}


UPLOAD_SCHLUESSEL = ("auftrag_upload_token", "leihe_ausgabe_token", "leihe_rueckgabe_token")


def _upload_token(neu=False, schluessel="auftrag_upload_token"):
    """Kennung für Fotos, die in einem Formular (z. B. „+ Neuer Auftrag“) vor dem Speichern hochgeladen werden.

    Sie bleibt in der Sitzung erhalten, bis das Formular erfolgreich gespeichert wurde – so gehen Fotos
    auch dann nicht verloren, wenn das Speichern einmal fehlschlägt.
    """
    import secrets
    if neu or not session.get(schluessel):
        session[schluessel] = secrets.token_hex(16)
    return session[schluessel]


def _ohne_kva_bestaetigt():
    return request.form.get("ohne_kva") == "1"


KEIN_KVA_TEXT = "Kein KVA verknüpft – leeren Rechnungsentwurf erstellen oder KVA jetzt verknüpfen?"
LEIHE_OFFEN_TEXT = "Das Leihgerät ist noch nicht zurück. Leihgerät jetzt zurücknehmen oder später separat abrechnen?"


def _leihen_spaeter_abrechnen(con, aid):
    for le in lg.offene_leihen_auftrag(con, aid):
        con.execute("UPDATE leihen SET separat_abrechnen=1 WHERE id=?", (le["id"],))
        auf.verlauf(con, aid, "Leihgerät wird später separat abgerechnet", f"{le['bezeichnung']} ({le['leihnr']})")


@bp.route("/auftraege/neu", methods=["GET", "POST"])
def auftrag_neu():
    con = dbm.get_db()
    if request.method == "POST" and request.form.get("anfrage_id"):
        # Aus einer Kontaktanfrage (Knopf auf der Anfrage-Seite)
        kid = request.form.get("kunde_id", type=int)
        anfrage_id = request.form.get("anfrage_id", type=int)
        with dbm.Transaktion(con):
            if not kid:
                a = con.execute("SELECT * FROM anfragen WHERE id=?", (anfrage_id,)).fetchone()
                kid = a["kunde_id"] if a and a["kunde_id"] else anf.kunde_aus_anfrage(con, anfrage_id,
                                                                                      dbm.einstellungen(con))[0]
            aid = auf.anlegen(con, kid, anfrage_id=anfrage_id, **_auftrag_felder())
        flash("Reparaturauftrag angelegt.", "ok")
        return redirect(url_for("main.auftrag", aid=aid))
    token = _upload_token()
    werte = {"kunde_id": request.args.get("kunde_id", "")}
    if request.method == "POST":
        werte = request.form.to_dict()
        werte["zubehoer"] = ann.zubehoer_zusammen(set(request.form.getlist("zubehoer_check")),
                                                  _f("zubehoer_sonstiges"), ann.zubehoer_vorlagen(dbm.einstellungen()))
        try:
            kid = request.form.get("kunde_id", type=int)
            status = request.form.get("status", "offen")
            kva_id = request.form.get("kva_id", type=int)
            if status == "erledigt" and not kva_id and not _ohne_kva_bestaetigt():
                raise EingabeFehler(KEIN_KVA_TEXT)
            with dbm.Transaktion(con):
                aid = auf.anlegen(con, kid, **_auftrag_felder())
                _zugang_aus_formular(con, aid)
                warnung = auf.kva_verknuepfen(con, aid, kva_id) if kva_id else False
                anzahl = fot.zuordnen(con, request.form.get("upload_token") or token, aid)
                neue_rechnung = auf.status_setzen(con, aid, status) if status != "offen" else None
        except EingabeFehler as e:
            flash(f"Der Auftrag wurde NICHT gespeichert: {e} Ihre Eingaben und bereits hochgeladenen Fotos "
                  "sind noch da.", "fehler")
        else:
            _upload_token(neu=True)
            flash("Reparaturauftrag angelegt" + (f" – {anzahl} Foto(s) zugeordnet." if anzahl else "."), "ok")
            if warnung:
                flash("Achtung: Der verknüpfte Kostenvoranschlag gehört zu einem anderen Kunden.", "warnung")
            if neue_rechnung:
                flash("Rechnungsentwurf wurde erstellt. Bitte prüfen und festschreiben.", "ok")
                return redirect(url_for("main.dokument", did=neue_rechnung))
            _benachrichtigungen_automatisch()
            flash("Jetzt den Annahmeschein vom Kunden unterschreiben lassen (am PC/Tablet oder per QR-Code am Handy).",
                  "info")
            return redirect(url_for("main.auftrag", aid=aid) + "#annahmeschein")
    if request.method == "GET":
        werte["kva_gebuehr"] = None  # wird aus dem Gerätetyp vorgeschlagen
    kva_vorauswahl = None
    if werte.get("kva_id"):
        kva_vorauswahl = con.execute("SELECT * FROM dokumente WHERE id=? AND typ='kva'", (werte["kva_id"],)).fetchone()
    return render_template("auftrag_neu.html", werte=werte, status_namen=auf.TAFEL, leistungsarten=_leistungsarten(),
                           kunden=_kunden_liste(con), token=token, kategorien=fot.KATEGORIEN,
                           fotos=fot.liste(con, upload_token=token, mit_geloeschten=False),
                           kva_vorauswahl=kva_vorauswahl, kein_kva_text=KEIN_KVA_TEXT)


def _auftrag_laden(aid):
    a = dbm.get_db().execute(AUFTRAG_SQL + "WHERE a.id=?", (aid,)).fetchone()
    if not a:
        abort(404)
    return a


@bp.route("/auftraege/<int:aid>", methods=["GET", "POST"])
def auftrag(aid):
    con = dbm.get_db()
    a = _auftrag_laden(aid)
    if request.method == "POST":
        felder = _auftrag_felder()
        kid = request.form.get("kunde_id", type=int) or a["kunde_id"]
        status = request.form.get("status") or auf.tafel_status(a)
        if kid != a["kunde_id"] and not con.execute("SELECT 1 FROM kunden WHERE id=?", (kid,)).fetchone():
            raise EingabeFehler("Bitte einen Kunden auswählen.")
        if status == "erledigt" and a["status"] != "erledigt" and a["leihen_offen"] \
                and request.form.get("leihe_spaeter") != "1":
            flash(LEIHE_OFFEN_TEXT + " Die Änderungen wurden noch nicht gespeichert.", "warnung")
            return redirect(url_for("main.auftrag", aid=aid) + "#leihgeraet")
        if status == "erledigt" and a["status"] != "erledigt" and not a["kva_id"] and not a["intern"] and a["auftragsart"] != "garantie" \
                and not _ohne_kva_bestaetigt():
            flash(KEIN_KVA_TEXT + " Die Änderungen wurden noch nicht gespeichert.", "warnung")
            return redirect(url_for("main.auftrag", aid=aid) + "#kostenvoranschlag")
        felder["kunde_id"] = kid
        geaendert = [FELD_NAMEN[k] for k, v in felder.items() if _norm(a[k]) != _norm(v)]
        neue_rechnung = None
        with dbm.Transaktion(con):
            con.execute(f"UPDATE auftraege SET {', '.join(f'{k}=?' for k in felder)}, geaendert_am=? WHERE id=?",
                        (*felder.values(), dbm.jetzt(), aid))
            _zugang_aus_formular(con, aid)
            if a["abgeholt_am"]:
                gar.ende_speichern(con, aid)  # Garantiedauer nachträglich geändert
            if geaendert:
                dbm.protokollieren("auftrag_geaendert", "auftrag", aid, {"felder": geaendert}, con=con)
                auf.verlauf(con, aid, "Auftragsdaten geändert", ", ".join(geaendert))
            if status != auf.tafel_status(a):
                if status == "erledigt" and a["leihen_offen"]:
                    _leihen_spaeter_abrechnen(con, aid)
                neue_rechnung = auf.status_setzen(con, aid, status)
        flash("Auftrag gespeichert.", "ok")
        _benachrichtigungen_automatisch()
        if kid != a["kunde_id"] and a["kva_id"] and a["kva_kunde_id"] != kid:
            flash("Achtung: Der verknüpfte Kostenvoranschlag gehört zu einem anderen Kunden.", "warnung")
        if neue_rechnung:
            flash("Auftrag erledigt – Rechnungsentwurf wurde erstellt. Bitte prüfen und festschreiben.", "ok")
            return redirect(url_for("main.dokument", did=neue_rechnung))
        return redirect(url_for("main.auftrag", aid=aid))
    anfrage_row = con.execute("SELECT * FROM anfragen WHERE id=?", (a["anfrage_id"],)).fetchone() \
        if a["anfrage_id"] else None
    material = lgr.auftrag_material(con, aid)
    kva_kunde = con.execute("SELECT * FROM kunden WHERE id=?", (a["kva_kunde_id"],)).fetchone() \
        if a["kva_id"] and a["kva_kunde_id"] != a["kunde_id"] else None
    return render_template("auftrag.html", a=a, status_namen=auf.TAFEL, tafel_status=auf.tafel_status(a),
                           benachrichtigungen=ben.offene(con, aid), ben_liste=ben.liste(con, aid),
                           vorbesuche=gar.vorbesuche(con, a["seriennummer"], aid), garantie=gar.status(a, dbm.einstellungen(con)),
                           garantie_bezug=con.execute("SELECT id, auftragsnr FROM auftraege WHERE id=?",
                                                      (a["garantie_bezug_id"],)).fetchone() if a["garantie_bezug_id"] else None,
                           garantiefaelle=gar.garantiefaelle_zu(con, aid), interne_kosten=gar.interne_kosten(con, a),
                           material=material, res_status=lgr.RES_STATUS,
                           lief_garantie={m["id"]: ek.lieferantengarantie(con, m["artikel_id"], m["erledigt_am"] or m["erstellt_am"])
                                          for m in material},
                           bestellungen_auftrag=ek.bestellungen(con, auftrag_id=aid),
                           lager_artikel=con.execute("SELECT id, name, einheit, bestand, lagerort, kompatibilitaet "
                                                     "FROM artikel WHERE lagerfuehrend=1 AND aktiv=1 ORDER BY name").fetchall(),
                           anlaesse=ben.ANLAESSE, leistungsarten=_leistungsarten(),
                           anfrage=anfrage_row, kunden=_kunden_liste(con, a["kunde_id"]), kva_kunde=kva_kunde,
                           fotos=fot.liste(con, aid), kategorien=fot.KATEGORIEN,
                           verlauf=auf.verlauf_liste(con, aid), kva_status_namen=auf.KVA_STATUS,
                           kein_kva_text=KEIN_KVA_TEXT, leihe_offen_text=LEIHE_OFFEN_TEXT,
                           leihen=_leihen_zum_auftrag(con, aid), alle_kategorien=fot.ALLE_KATEGORIEN,
                           heute=date.today().isoformat(), belege=ann.belege(con, aid), belegarten=ann.ARTEN,
                           geaendert_seit_unterschrift=ann.geaendert_seit_unterschrift(con, aid),
                           zugang_text=ann.zugang_text(a))


@bp.route("/auftraege/<int:aid>/status", methods=["POST"])
def auftrag_status(aid):
    """Wird von der Tafel (Ziehen & Ablegen) per fetch aufgerufen, oder per Knopf als normales Formular."""
    con = dbm.get_db()
    a = _auftrag_laden(aid)
    status = request.form.get("status", "")
    per_fetch = request.headers.get("X-Requested-With") == "fetch"
    if status == "erledigt" and a["status"] != "erledigt" and a["leihen_offen"]:
        if request.form.get("leihe_spaeter") != "1":
            if per_fetch:
                return jsonify(ok=False, leihe_offen=True, meldung=LEIHE_OFFEN_TEXT,
                               auftrag_url=url_for("main.auftrag", aid=aid) + "#leihgeraet")
            flash(LEIHE_OFFEN_TEXT, "warnung")
            return redirect(url_for("main.auftrag", aid=aid) + "#leihgeraet")
    if status == "erledigt" and a["status"] != "erledigt" and not a["kva_id"] and not a["intern"] and a["auftragsart"] != "garantie" \
            and not _ohne_kva_bestaetigt():
        if per_fetch:
            return jsonify(ok=False, kein_kva=True, meldung=KEIN_KVA_TEXT,
                           auftrag_url=url_for("main.auftrag", aid=aid) + "#kostenvoranschlag")
        flash(KEIN_KVA_TEXT, "warnung")
        return redirect(url_for("main.auftrag", aid=aid) + "#kostenvoranschlag")
    with dbm.Transaktion(con):
        if status == "erledigt" and a["leihen_offen"]:
            _leihen_spaeter_abrechnen(con, aid)
        neue_rechnung = auf.status_setzen(con, aid, status, request.form.get("vor_id", type=int))
    _benachrichtigungen_automatisch()
    ziel = url_for("main.dokument", did=neue_rechnung) if neue_rechnung else None
    if neue_rechnung:
        flash("Auftrag erledigt – Rechnungsentwurf wurde erstellt. Bitte prüfen und festschreiben.", "ok")
    if per_fetch:
        return jsonify(ok=True, rechnung_url=ziel)
    if neue_rechnung:
        return redirect(ziel)
    return redirect(request.referrer or url_for("main.auftraege"))


@bp.route("/auftraege/<int:aid>/kva", methods=["POST"])
def auftrag_kva(aid):
    """Neuen KVA aus dem Auftrag erstellen (vorausgefüllt) und automatisch verknüpfen."""
    con = dbm.get_db()
    _auftrag_laden(aid)
    with dbm.Transaktion(con):
        did = auf.kva_erstellen(con, aid)
    flash("Kostenvoranschlag erstellt und mit dem Auftrag verknüpft.", "ok")
    return redirect(url_for("main.dokument", did=did))


@bp.route("/auftraege/kva-auswahl")
def auftrag_kva_auswahl():
    """Liste der KVAs, die noch keinem Auftrag zugeordnet sind (für die Verknüpfen-Auswahl)."""
    con = dbm.get_db()
    zeilen = auf.kva_kandidaten(con, request.args.get("kunde_id", type=int), request.args.get("alle") == "1",
                                request.args.get("q", ""))
    return jsonify([{"id": d["id"], "nummer": d["nummer"] or "Entwurf", "datum": datum_de(d["datum"]),
                     "betrag": euro(d["summe_brutto"]), "betreff": d["betreff"] or "",
                     "kunde": f"{d['kundennr'] or ''} · {kunde_name({**dict(d), 'typ': d['ktyp']})}"
                     if d["kunde_id"] else "–",
                     "kunde_id": d["kunde_id"], "status": d["status"],
                     "entscheidung": d["kva_status"] or "offen"} for d in zeilen])


@bp.route("/auftraege/<int:aid>/kva-verknuepfen", methods=["POST"])
def auftrag_kva_verknuepfen(aid):
    con = dbm.get_db()
    _auftrag_laden(aid)
    kva_id = request.form.get("kva_id", type=int)
    if not kva_id:
        raise EingabeFehler("Bitte einen Kostenvoranschlag auswählen.")
    with dbm.Transaktion(con):
        warnung = auf.kva_verknuepfen(con, aid, kva_id)
    flash("Kostenvoranschlag verknüpft.", "ok")
    if warnung:
        flash("Achtung: Der Kostenvoranschlag gehört zu einem anderen Kunden als der Auftrag.", "warnung")
    return redirect(url_for("main.auftrag", aid=aid) + "#kostenvoranschlag")


@bp.route("/auftraege/<int:aid>/kva-loesen", methods=["POST"])
def auftrag_kva_loesen(aid):
    con = dbm.get_db()
    _auftrag_laden(aid)
    with dbm.Transaktion(con):
        auf.kva_loesen(con, aid)
    flash("Verknüpfung gelöst. Der Kostenvoranschlag selbst bleibt erhalten.", "ok")
    return redirect(url_for("main.auftrag", aid=aid) + "#kostenvoranschlag")


@bp.route("/dokumente/<int:did>/kva-status", methods=["POST"])
def kva_status(did):
    con = dbm.get_db()
    with dbm.Transaktion(con):
        neue = auf.kva_status_setzen(con, did, request.form.get("kva_status", ""))
    flash("Status des Kostenvoranschlags gespeichert.", "ok")
    if neue:
        flash("KVA abgelehnt – die KVA-Pauschale ist fällig. Ein Rechnungsentwurf darüber wurde vorbereitet: bitte "
              "prüfen und festschreiben (oder löschen, falls Sie auf die Pauschale verzichten).", "warnung")
        return redirect(url_for("main.dokument", did=neue[0]))
    return redirect(request.referrer or url_for("main.dokument", did=did))


@bp.route("/auftraege/<int:aid>/rechnung", methods=["POST"])
def auftrag_rechnung(aid):
    con = dbm.get_db()
    _auftrag_laden(aid)
    with dbm.Transaktion(con):
        did, neu = auf.rechnung_erstellen(con, aid)
    if neu:
        flash("Rechnungsentwurf erstellt. Bitte prüfen und festschreiben.", "ok")
    return redirect(url_for("main.dokument", did=did))


@bp.route("/auftraege/<int:aid>/loeschen", methods=["POST"])
def auftrag_loeschen(aid):
    con = dbm.get_db()
    a = _auftrag_laden(aid)
    if a["re_status"] in ("festgeschrieben", "storniert"):
        raise EingabeFehler("Zu diesem Auftrag gibt es eine festgeschriebene Rechnung – er kann nicht gelöscht werden.")
    if con.execute("SELECT 1 FROM auftrag_fotos WHERE auftrag_id=?", (aid,)).fetchone():
        raise EingabeFehler("Zu diesem Auftrag gibt es eine Fotodokumentation – er kann nicht gelöscht werden.")
    if con.execute("SELECT 1 FROM leihen WHERE auftrag_id=?", (aid,)).fetchone():
        raise EingabeFehler("Zu diesem Auftrag wurde ein Leihgerät ausgegeben – er kann nicht gelöscht werden.")
    if con.execute("SELECT 1 FROM lagerbewegungen WHERE auftrag_id=?", (aid,)).fetchone():
        raise EingabeFehler("Für diesen Auftrag wurde Material aus dem Lager gebucht – er kann nicht gelöscht werden.")
    if con.execute("SELECT 1 FROM auftrag_belege WHERE auftrag_id=?", (aid,)).fetchone():
        raise EingabeFehler("Zu diesem Auftrag gibt es einen unterschriebenen Annahme-/Abholschein – er kann nicht "
                            "gelöscht werden.")
    with dbm.Transaktion(con):
        ann.zugang_loeschen(con, aid, "Auftrag storniert/gelöscht")  # endgültig, mit Löschprotokoll
        con.execute("DELETE FROM mobil_zugaenge WHERE auftrag_id=?", (aid,))
        con.execute("DELETE FROM lager_reservierungen WHERE auftrag_id=?", (aid,))
        con.execute("UPDATE auftraege SET kva_id=NULL, rechnung_id=NULL WHERE id=?", (aid,))
        if a["rechnung_id"]:  # automatisch erzeugter Rechnungsentwurf wird mitgelöscht, der KVA bleibt erhalten
            if con.execute("SELECT 1 FROM dokumente WHERE id=? AND status='entwurf'", (a["rechnung_id"],)).fetchone():
                con.execute("DELETE FROM positionen WHERE dokument_id=?", (a["rechnung_id"],))
                con.execute("DELETE FROM dokumente WHERE id=?", (a["rechnung_id"],))
        con.execute("DELETE FROM auftraege WHERE id=?", (aid,))
        auf.verlauf(con, aid, "Auftrag gelöscht", a["auftragsnr"])
        dbm.protokollieren("auftrag_geloescht", "auftrag", aid, {"auftragsnr": a["auftragsnr"]}, con=con)
    flash("Auftrag gelöscht. Ein verknüpfter Kostenvoranschlag bleibt erhalten.", "ok")
    return redirect(url_for("main.auftraege"))


@bp.route("/auftraege/geraet-pruefen")
def geraet_pruefen():
    """Frühere Aufträge mit derselben Seriennummer/IMEI (für den Hinweis beim Anlegen)."""
    con = dbm.get_db()
    ergebnis = []
    for v in gar.vorbesuche(con, request.args.get("sn", ""), request.args.get("ohne", type=int)):
        a = v["a"]
        ergebnis.append({
            "id": a["id"], "auftragsnr": a["auftragsnr"], "eingang": datum_de(a["eingang_am"][:10]),
            "kunde": _kname(a), "geraet": a["geraet"] or "", "fehler": a["fehler"] or "",
            "art": gar.AUFTRAGSARTEN.get(a["auftragsart"], ""), "garantie": v["garantie"]["text"],
            "laeuft": v["garantie"]["laeuft"], "fotos": a["foto_anzahl"],
            "url": url_for("main.auftrag", aid=a["id"]),
            "rechnung": a["re_nummer"] or "", "rechnung_url": url_for("main.dokument", did=a["rechnung_id"])
            if a["rechnung_id"] else ""})
    return jsonify(ergebnis)


# ---------------------------------------------------------------------- Kundenbenachrichtigung

@bp.route("/benachrichtigungen")
def benachrichtigungen():
    con = dbm.get_db()
    with dbm.Transaktion(con):
        ben.erinnerungen_pruefen(con)
    return render_template("benachrichtigungen.html", offene=ben.offene(con), liste=ben.liste(con),
                           nicht_abgeholt=ben.nicht_abgeholt(con), anlaesse=ben.ANLAESSE, status_namen=ben.STATUS,
                           kanaele=ben.KANAELE)


def _zurueck(standard):
    ziel = request.form.get("weiter") or ""
    return redirect(ziel if ziel.startswith("/") and not ziel.startswith("//") else standard)


@bp.route("/benachrichtigungen/<int:bid>/senden", methods=["POST"])
def benachrichtigung_senden(bid):
    con = dbm.get_db()
    ok, meldung = ben.senden(con, bid, request.form.get("an"), request.form.get("betreff"), request.form.get("text"))
    if ok:
        flash("Benachrichtigung wurde gesendet.", "ok")
        if meldung:
            flash(meldung, "warnung")
    else:
        flash(f"Benachrichtigung wurde NICHT gesendet: {meldung}", "fehler")
    return _zurueck(url_for("main.benachrichtigungen"))


@bp.route("/benachrichtigungen/<int:bid>/verwerfen", methods=["POST"])
def benachrichtigung_verwerfen(bid):
    con = dbm.get_db()
    with dbm.Transaktion(con):
        ben.verwerfen(con, bid)
    flash("Diesmal nicht gesendet.", "ok")
    return _zurueck(url_for("main.benachrichtigungen"))


@bp.route("/auftraege/<int:aid>/benachrichtigen", methods=["POST"])
def auftrag_benachrichtigen(aid):
    con = dbm.get_db()
    _auftrag_laden(aid)
    with dbm.Transaktion(con):
        bid = ben.vorschlagen(con, aid, _f("anlass"), manuell=True)
    if not bid:
        flash("Für interne Aufträge werden keine Benachrichtigungen erstellt.", "warnung")
    return redirect(url_for("main.auftrag", aid=aid))


@bp.route("/auftraege/<int:aid>/abgeholt", methods=["POST"])
def auftrag_abgeholt(aid):
    """Abholung ohne digitalen Abholschein vermerken (z. B. Papier-Unterschrift)."""
    con = dbm.get_db()
    a = _auftrag_laden(aid)
    with dbm.Transaktion(con):
        if not a["abgeholt_am"]:
            con.execute("UPDATE auftraege SET abgeholt_am=? WHERE id=?", (dbm.jetzt_berlin(), aid))
            auf.verlauf(con, aid, "Gerät abgeholt", _f("notiz") or "ohne digitalen Abholschein")
            gar.ende_speichern(con, aid)
            ann.zugang_loeschen(con, aid, "Gerät abgeholt")
        for b in con.execute("SELECT id FROM benachrichtigungen WHERE auftrag_id=? AND anlass='erinnerung' "
                             "AND status='offen'", (aid,)).fetchall():
            ben.verwerfen(con, b["id"], "Gerät wurde abgeholt")
    flash("Abholung vermerkt.", "ok")
    return _zurueck(url_for("main.auftrag", aid=aid))


# ---------------------------------------------------------------------- Annahme-/Abholschein, Handy (QR-Code)

def _art_pruefen(art):
    if art not in ann.ARTEN:
        abort(404)
    return art


@bp.route("/auftraege/<int:aid>/schein/<art>.pdf")
def auftrag_schein_vorschau(aid, art):
    """Nicht unterschriebener Schein (Vorschau / zum Ausdrucken und Unterschreiben auf Papier)."""
    con = dbm.get_db()
    _auftrag_laden(aid)
    snap = ann.snapshot(con, aid, _art_pruefen(art))
    pdf = ann_pdf.erstellen(snap, daten_dir(), dbm.einstellungen(con))
    return send_file(io.BytesIO(pdf), mimetype="application/pdf", download_name=ann_pdf.dateiname(snap))


@bp.route("/auftraege/<int:aid>/unterschreiben/<art>", methods=["GET", "POST"])
def auftrag_unterschreiben(aid, art):
    con = dbm.get_db()
    a = _auftrag_laden(aid)
    _art_pruefen(art)
    if request.method == "POST":
        if not request.form.get("bestaetigt"):
            raise EingabeFehler("Bitte bestätigen Sie die Angaben (Haken setzen).")
        with dbm.Transaktion(con):
            bid = ann.beleg_erstellen(con, aid, art, request.form.get("unterschrift", ""), _f("unterzeichner"),
                                      daten_dir(), quelle="PC/Tablet", ip=request.remote_addr)
        flash(f"{ann.ARTEN[art]} wurde unterschrieben und archiviert.", "ok")
        return redirect(url_for("main.auftrag", aid=aid, beleg=bid) + "#annahmeschein")
    snap = ann.snapshot(con, aid, art)
    return render_template("unterschreiben.html", a=a, art=art, snap=snap, titel=ann.ARTEN[art],
                           ziel=url_for("main.auftrag_unterschreiben", aid=aid, art=art), mobil=False,
                           zurueck=url_for("main.auftrag", aid=aid) + "#annahmeschein")


@bp.route("/belege/<int:bid>.pdf")
def beleg_pdf(bid):
    b = dbm.get_db().execute("SELECT * FROM auftrag_belege WHERE id=?", (bid,)).fetchone()
    if not b:
        abort(404)
    daten, ok = ann.beleg_pdf(daten_dir(), b)
    if not ok:
        return render_template("pdf_fehler.html", d={"nummer": b["nummer"], "pdf_pfad": b["pdf_datei"],
                                                     "pdf_sha256": b["pdf_sha256"]}, fehlt=daten is None), 409
    return send_file(io.BytesIO(daten), mimetype="application/pdf", download_name=f"{b['nummer']}.pdf")


@bp.route("/belege/<int:bid>/email", methods=["GET", "POST"])
def beleg_email(bid):
    con = dbm.get_db()
    b = con.execute("SELECT * FROM auftrag_belege WHERE id=?", (bid,)).fetchone()
    if not b:
        abort(404)
    a = _auftrag_laden(b["auftrag_id"])
    einst = dbm.einstellungen(con)
    titel = ann.ARTEN[b["art"]]
    if request.method == "POST":
        an = _f("an")
        if "@" not in an:
            raise EingabeFehler("Bitte eine gültige E-Mail-Adresse angeben.")
        daten, ok = ann.beleg_pdf(daten_dir(), b)
        if not ok:
            raise EingabeFehler("Das archivierte PDF ist nicht mehr unverändert vorhanden – Versand abgebrochen.")
        try:
            hinweis = senden(con, None, an, _f("betreff"), request.form.get("text", ""), daten, f"{b['nummer']}.pdf")
        except MailFehler as e:
            flash(f"E-Mail wurde NICHT gesendet: {e}", "fehler")
            return redirect(url_for("main.beleg_email", bid=bid))
        with dbm.Transaktion(con):
            auf.verlauf(con, a["id"], f"{titel} per E-Mail versendet", f"{b['nummer']} an {an}")
        flash(f"E-Mail an {an} wurde gesendet.", "ok")
        if hinweis:
            flash(hinweis, "warnung")
        return redirect(url_for("main.auftrag", aid=a["id"]) + "#annahmeschein")
    k = con.execute("SELECT * FROM kunden WHERE id=?", (a["kunde_id"],)).fetchone()
    text = (f"{anrede_brief(k)}\n\nanbei erhalten Sie Ihren {titel} {b['nummer']} zum Reparaturauftrag "
            f"{a['auftragsnr']}" + (f" ({a['geraet']})" if a["geraet"] else "") + ".\n\n"
            f"Mit freundlichen Grüßen\n{einst.get('inhaber') or ''}\n{einst.get('firma_name') or ''}")
    return render_template("beleg_email.html", b=b, a=a, titel=titel, an=k["email"] or "",
                           betreff=f"{titel} {b['nummer']} – {einst.get('firma_name') or ''}", text=text,
                           smtp_ok=bool(einst.get("smtp_host")))


@bp.route("/auftraege/<int:aid>/zugang", methods=["POST"])
def auftrag_zugang_anzeigen(aid):
    _auftrag_laden(aid)
    return jsonify(wert=ann.zugang_anzeigen(dbm.get_db(), aid))


@bp.route("/auftraege/<int:aid>/handy/<zweck>", methods=["POST"])
def auftrag_handy(aid, zweck):
    con = dbm.get_db()
    a = _auftrag_laden(aid)
    if zweck not in ann.ZWECKE:
        abort(404)
    with dbm.Transaktion(con):
        ann.tokens_aufraeumen(con)
        token = ann.token_erstellen(con, aid, zweck)
    port = current_app.config.get("SERVER_PORT") or request.host.rsplit(":", 1)[-1]
    url = ann.basis_url(dbm.einstellungen(con), port) + url_for("main.mobil", token=token)
    im_netz = current_app.config.get("SERVER_HOST") == "0.0.0.0" or bool(dbm.einstellung("handy_adresse"))
    return render_template("handy_qr.html", a=a, zweck=zweck, zweck_text=ann.ZWECKE[zweck], url=url,
                           qr=Markup(ann.qr_svg(url)), minuten=ann.TOKEN_MINUTEN, im_netz=im_netz,
                           stand=_auftrag_stand(con, aid))


def _auftrag_stand(con, aid):
    return {"belege": con.execute("SELECT COUNT(*) FROM auftrag_belege WHERE auftrag_id=?", (aid,)).fetchone()[0],
            "fotos": con.execute("SELECT COUNT(*) FROM auftrag_fotos WHERE auftrag_id=?", (aid,)).fetchone()[0]}


@bp.route("/auftraege/<int:aid>/stand.json")
def auftrag_stand(aid):
    _auftrag_laden(aid)
    return jsonify(_auftrag_stand(dbm.get_db(), aid))


def _mobil_zugang(token):
    con = dbm.get_db()
    z = ann.token_pruefen(con, token)
    if not z:
        return None, None
    g.benutzer_ersatz = f"{z['benutzer'] or 'system'} (Handy)"
    return z, con.execute(AUFTRAG_SQL + "WHERE a.id=?", (z["auftrag_id"],)).fetchone()


@bp.route("/m/<token>", methods=["GET", "POST"])
def mobil(token):
    con = dbm.get_db()
    z, a = _mobil_zugang(token)
    if not z:
        return render_template("mobil.html", abgelaufen=True), 410
    if z["zweck"] == "fotos":
        return render_template("mobil.html", z=z, a=a, kategorien=fot.KATEGORIEN, token=token,
                               fotos=fot.liste(con, a["id"], mit_geloeschten=False))
    if request.method == "POST":
        try:
            if not request.form.get("bestaetigt"):
                raise EingabeFehler("Bitte bestätigen Sie die Angaben (Haken setzen).")
            with dbm.Transaktion(con):
                ann.beleg_erstellen(con, a["id"], z["zweck"], request.form.get("unterschrift", ""),
                                    _f("unterzeichner"), daten_dir(), quelle="Handy (QR-Code)",
                                    ip=request.remote_addr)
                ann.token_benutzt(con, token)
        except EingabeFehler as e:
            flash(str(e), "fehler")
            return redirect(url_for("main.mobil", token=token))
        return render_template("mobil.html", fertig=True, titel=ann.ARTEN[z["zweck"]])
    snap = ann.snapshot(con, a["id"], z["zweck"])
    return render_template("unterschreiben.html", a=a, art=z["zweck"], snap=snap, titel=ann.ARTEN[z["zweck"]],
                           ziel=url_for("main.mobil", token=token), mobil=True, zurueck=None)


@bp.route("/m/<token>/fotos", methods=["POST"])
def mobil_fotos(token):
    z, a = _mobil_zugang(token)
    if not z or z["zweck"] != "fotos":
        return jsonify(ok=False, meldung="Der QR-Code ist abgelaufen. Bitte am PC einen neuen erzeugen."), 410
    return _foto_hochladen(auftrag_id=a["id"], kategorien=fot.KATEGORIEN)


@bp.route("/m/<token>/foto/<int:fid>")
def mobil_foto_vorschau(token, fid):
    z, a = _mobil_zugang(token)
    f = dbm.get_db().execute("SELECT * FROM auftrag_fotos WHERE id=?", (fid,)).fetchone()
    if not z or not f or f["auftrag_id"] != a["id"]:
        abort(404)
    pfad = fot.vorschau_pfad(daten_dir(), f["sha256"])
    if not pfad.exists():
        abort(404)
    return send_file(pfad, mimetype="image/jpeg")


# ---------------------------------------------------------------------- Fotos

def _foto_hochladen(auftrag_id=None, token=None, kategorien=None, **zuordnung):
    con = dbm.get_db()
    dateien = request.files.getlist("foto")
    if not dateien:
        return jsonify(ok=False, meldung="Keine Datei empfangen."), 400
    ergebnis = []
    for datei in dateien:
        try:
            kategorie = request.form.get("kategorie", "")
            if kategorien and kategorie not in kategorien:
                raise EingabeFehler("Bitte eine passende Foto-Kategorie auswählen.")
            with dbm.Transaktion(con):
                fid = fot.speichern(con, daten_dir(), datei.read(), datei.filename, kategorie,
                                    auftrag_id=auftrag_id, upload_token=token, **zuordnung)
            ergebnis.append({"ok": True, "id": fid, "datei": datei.filename})
        except EingabeFehler as e:
            ergebnis.append({"ok": False, "datei": datei.filename, "meldung": str(e)})
    return jsonify(ok=all(e["ok"] for e in ergebnis), dateien=ergebnis)


@bp.route("/auftraege/<int:aid>/fotos", methods=["POST"])
def auftrag_fotos_hochladen(aid):
    _auftrag_laden(aid)
    return _foto_hochladen(auftrag_id=aid, kategorien=fot.KATEGORIEN)


@bp.route("/auftraege/neu/fotos", methods=["POST"])
def auftrag_neu_fotos():
    token = request.form.get("upload_token") or ""
    if token != session.get("auftrag_upload_token"):
        return jsonify(ok=False, meldung="Sitzung abgelaufen – bitte die Seite neu laden."), 400
    return _foto_hochladen(token=token, kategorien=fot.KATEGORIEN)


def _foto_laden(fid):
    f = dbm.get_db().execute("SELECT * FROM auftrag_fotos WHERE id=?", (fid,)).fetchone()
    if not f or (not f["auftrag_id"] and not f["leihgeraet_id"]
                 and f["upload_token"] not in [session.get(s) for s in UPLOAD_SCHLUESSEL]):
        abort(404)
    return f


@bp.route("/fotos/<int:fid>")
def foto_original(fid):
    f = _foto_laden(fid)
    return send_file(Path(daten_dir()) / f["pfad"], mimetype=f["mime"], download_name=f["dateiname"],
                     as_attachment=request.args.get("download") == "1")


@bp.route("/fotos/<int:fid>/vorschau")
def foto_vorschau(fid):
    f = _foto_laden(fid)
    pfad = fot.vorschau_pfad(daten_dir(), f["sha256"])
    if not pfad.exists():
        original = Path(daten_dir()) / f["pfad"]
        if not original.exists() or not fot.vorschau_erzeugen(daten_dir(), f["sha256"], original.read_bytes()):
            return redirect(url_for("static", filename="bilder/keine_vorschau.svg"))
    return send_file(pfad, mimetype="image/jpeg", max_age=86400)


@bp.route("/fotos/<int:fid>/loeschen", methods=["POST"])
def foto_loeschen(fid):
    con = dbm.get_db()
    f = _foto_laden(fid)
    with dbm.Transaktion(con):
        fot.als_geloescht_markieren(con, fid, _f("grund"))
    flash("Foto als gelöscht markiert. Es bleibt zur Nachvollziehbarkeit gespeichert.", "ok")
    if request.form.get("zurueck", "").startswith("/"):
        return redirect(request.form["zurueck"])
    if f["leihe_id"]:
        return redirect(url_for("main.leihe", lid=f["leihe_id"]) + "#fotos")
    if f["leihgeraet_id"]:
        return redirect(url_for("main.leihgeraet", gid=f["leihgeraet_id"]) + "#fotos")
    if f["auftrag_id"]:
        return redirect(url_for("main.auftrag", aid=f["auftrag_id"]) + "#fotos")
    return redirect(url_for("main.auftrag_neu"))


@bp.route("/auftraege/<int:aid>/fotodokumentation.pdf")
def auftrag_fotos_pdf(aid):
    con = dbm.get_db()
    a = con.execute("SELECT * FROM auftraege WHERE id=?", (aid,)).fetchone()
    if not a:
        abort(404)
    pdf = fot.pdf_dokumentation(con, a, daten_dir())
    from io import BytesIO
    return send_file(BytesIO(pdf), mimetype="application/pdf", download_name=f"Fotodokumentation_{a['auftragsnr']}.pdf",
                     as_attachment=request.args.get("download") == "1")


# ====================================================================== Zahlungen, offene Posten, Mahnwesen, Bank

@bp.route("/dokumente/<int:did>/zahlung", methods=["POST"])
def zahlung_erfassen(did):
    con = dbm.get_db()
    _dokument_laden(did)
    betrag = cent_aus_text(_f("betrag"))
    if request.form.get("erstattung"):
        betrag = -abs(betrag)
    with dbm.Transaktion(con):
        _zlg().erfassen(con, did, _f("datum") or heute(), betrag, _f("zahlart"), _f("notiz"))
    flash("Zahlung erfasst.", "ok")
    return redirect(url_for("main.dokument", did=did) + "#zahlungen")


@bp.route("/zahlungen/<int:zid>/stornieren", methods=["POST"])
def zahlung_stornieren(zid):
    con = dbm.get_db()
    z = con.execute("SELECT * FROM zahlungen WHERE id=?", (zid,)).fetchone() or abort(404)
    with dbm.Transaktion(con):
        _zlg().stornieren(con, zid, _f("grund"))
    flash("Zahlung storniert (bleibt markiert gespeichert).", "ok")
    return redirect(request.form.get("zurueck") or url_for("main.dokument", did=z["dokument_id"]) + "#zahlungen")


@bp.route("/verkauf/offene-posten")
def offene_posten():
    con = dbm.get_db()
    kunde_id = request.args.get("kunde_id", type=int)
    nur = request.args.get("filter") == "ueberfaellig"
    posten = _zlg().offene_posten(con, kunde_id=kunde_id, nur_ueberfaellig=nur)
    kunden_ids = {p["d"]["kunde_id"] for p in _zlg().offene_posten(con)}
    kunden_liste = [k for k in con.execute("SELECT * FROM kunden ORDER BY COALESCE(NULLIF(firma,''), nachname)")
                    if k["id"] in kunden_ids]
    return render_template("offene_posten.html", posten=posten, kunden=kunden_liste, kunde_id=kunde_id, nur=nur,
                           summe=sum(p["s"]["offen"] for p in posten),
                           summe_gebuehren=sum(p["s"]["gebuehren_offen"] for p in posten),
                           summe_ueberfaellig=sum(p["s"]["offen"] for p in posten if p["s"]["status"] == "ueberfaellig"))


@bp.route("/verkauf/mahnwesen")
def mahnwesen():
    from . import mahnwesen as mw
    con = dbm.get_db()
    letzte = con.execute("SELECT m.*, d.nummer AS rechnung_nummer, d.id AS did, k.firma, k.vorname, k.nachname, "
                         "k.typ AS ktyp FROM mahnungen m JOIN dokumente d ON d.id=m.dokument_id "
                         "LEFT JOIN kunden k ON k.id=d.kunde_id ORDER BY m.id DESC LIMIT 50").fetchall()
    return render_template("mahnwesen.html", vorschlaege=mw.vorschlaege(con), ausgeschoepft=mw.ausgeschoepft(con),
                           letzte=letzte, titel=mw.TITEL)


@bp.route("/mahnwesen/erstellen", methods=["POST"])
def mahnungen_erstellen():
    from . import mahnwesen as mw
    con = dbm.get_db()
    erstellt, fehler = [], []
    for wert in request.form.getlist("auswahl"):
        did, stufe = (int(x) for x in wert.split(":"))
        try:
            erstellt.append(mw.erstellen(con, did, stufe, daten_dir()))
        except EingabeFehler as e:
            fehler.append(str(e))
    if erstellt:
        flash(f"{len(erstellt)} Schreiben erstellt und archiviert. Jetzt per E-Mail senden oder ausdrucken.", "ok")
    for f in fehler:
        flash(f, "fehler")
    if len(erstellt) == 1 and request.form.get("einzeln"):
        return redirect(url_for("main.mahnung", mid=erstellt[0]))
    return redirect(url_for("main.mahnwesen"))


def _mahnung_laden(mid):
    m = dbm.get_db().execute(
        "SELECT m.*, d.nummer AS rechnung_nummer, d.kunde_id, k.email AS kemail FROM mahnungen m "
        "JOIN dokumente d ON d.id=m.dokument_id LEFT JOIN kunden k ON k.id=d.kunde_id WHERE m.id=?", (mid,)).fetchone()
    if not m:
        abort(404)
    return m


@bp.route("/mahnungen/<int:mid>")
def mahnung(mid):
    from . import mahnwesen as mw
    m = _mahnung_laden(mid)
    return render_template("mahnung.html", m=m, titel=mw.TITEL[m["stufe"]])


@bp.route("/mahnungen/<int:mid>/pdf")
def mahnung_pdf(mid):
    import hashlib
    m = _mahnung_laden(mid)
    pfad = Path(daten_dir()) / m["pdf_pfad"]
    if not pfad.is_file() or hashlib.sha256(pfad.read_bytes()).hexdigest() != m["pdf_sha256"]:
        return render_template("pdf_fehler.html", d={"nummer": m["nummer"], "pdf_pfad": m["pdf_pfad"],
                                                     "pdf_sha256": m["pdf_sha256"]}, fehlt=not pfad.is_file()), 409
    return send_file(pfad, mimetype="application/pdf", download_name=f"{m['nummer']}.pdf",
                     as_attachment=request.args.get("download") == "1")


@bp.route("/mahnungen/<int:mid>/email", methods=["GET", "POST"])
def mahnung_email(mid):
    from . import mahnwesen as mw
    con = dbm.get_db()
    m = _mahnung_laden(mid)
    if request.method == "POST":
        an = _f("an")
        if "@" not in an:
            raise EingabeFehler("Bitte eine gültige E-Mail-Adresse angeben.")
        pdf = (Path(daten_dir()) / m["pdf_pfad"]).read_bytes()
        try:
            hinweis = senden(con, None, an, _f("betreff"), request.form.get("text", ""), pdf, f"{m['nummer']}.pdf",
                             m["dokument_id"])
        except MailFehler as e:
            flash(f"E-Mail wurde NICHT gesendet: {e}", "fehler")
            return redirect(url_for("main.mahnung_email", mid=mid))
        with dbm.Transaktion(con):
            mw.versand_vermerken(con, mid, "email")
        flash(f"{mw.TITEL[m['stufe']]} an {an} gesendet.", "ok")
        if hinweis:
            flash(hinweis, "warnung")
        return redirect(url_for("main.mahnung", mid=mid))
    betreff, text, an = mw.email_texte(con, m)
    return render_template("mahnung_email.html", m=m, titel=mw.TITEL[m["stufe"]], an=an, betreff=betreff, text=text,
                           smtp_ok=bool(dbm.einstellung("smtp_host")))


@bp.route("/mahnungen/<int:mid>/versendet", methods=["POST"])
def mahnung_versendet(mid):
    from . import mahnwesen as mw
    con = dbm.get_db()
    _mahnung_laden(mid)
    with dbm.Transaktion(con):
        mw.versand_vermerken(con, mid, "pdf")
    flash("Als per Post/ausgedruckt versendet vermerkt.", "ok")
    return redirect(url_for("main.mahnung", mid=mid))


@bp.route("/mahnungen/<int:mid>/erlassen", methods=["POST"])
def mahnung_erlassen(mid):
    from . import mahnwesen as mw
    con = dbm.get_db()
    m = _mahnung_laden(mid)
    with dbm.Transaktion(con):
        mw.gebuehren_erlassen(con, mid, _f("grund"))
    flash("Gebühren/Zinsen dieser Mahnung erlassen.", "ok")
    return redirect(url_for("main.dokument", did=m["dokument_id"]) + "#zahlungen")


@bp.route("/bank", methods=["GET", "POST"])
def bank():
    from . import bankabgleich as ba
    con = dbm.get_db()
    if request.method == "POST":
        datei = request.files.get("datei")
        if not datei or not datei.filename:
            raise EingabeFehler("Bitte eine Datei auswählen.")
        with dbm.Transaktion(con):
            e = ba.importieren(con, datei.filename, datei.read())
        flash(f"Kontoauszug ({e['format']}) eingelesen: {e['neu']} neue Umsätze"
              + (f", {e['doppelt']} bereits bekannte übersprungen" if e["doppelt"] else "") + ".", "ok")
        return redirect(url_for("main.bank"))
    ansicht = request.args.get("ansicht", "offen")
    sql = "SELECT * FROM bank_umsaetze WHERE "
    sql += {"offen": "status='offen'", "zugeordnet": "status='zugeordnet'", "ignoriert": "status='ignoriert'"}.get(
        ansicht, "status='offen'")
    umsaetze = con.execute(sql + " ORDER BY buchungstag DESC, id DESC LIMIT 300").fetchall()
    offene = _zlg().offene_posten(con)
    vorschlaege = {u["id"]: ba.vorschlag(con, u, offene) for u in umsaetze if u["status"] == "offen"}
    from . import einkauf
    offene_er = einkauf.offene_er(con)
    er_vorschlaege = {u["id"]: einkauf.bank_vorschlag(con, u, offene_er) for u in umsaetze
                      if u["status"] == "offen" and u["betrag"] < 0}
    importe = con.execute("SELECT * FROM bank_importe ORDER BY id DESC LIMIT 10").fetchall()
    zahl = {r[0]: r[1] for r in con.execute("SELECT status, COUNT(*) FROM bank_umsaetze GROUP BY status")}
    fix_liste = fxk.alle(con)
    fix_vorschlaege = {u["id"]: fxk.bank_vorschlag(con, u, fix_liste) for u in umsaetze
                       if u["status"] == "offen" and u["betrag"] < 0}
    fix_namen = {f["id"]: f["bezeichnung"] for f in fix_liste}
    fix_fehlt = [(f, s) for f in fix_liste for s in fxk.zahlungsstand(con, [f]).get(f["id"], [])
                 if s["status"] != "bezahlt"][-12:]
    return render_template("bank.html", umsaetze=umsaetze, vorschlaege=vorschlaege, offene=offene, importe=importe,
                           offene_er=offene_er, er_vorschlaege=er_vorschlaege, fix_liste=fix_liste,
                           fix_vorschlaege=fix_vorschlaege, fix_namen=fix_namen, fix_fehlt=fix_fehlt,
                           ansicht=ansicht, zahl=zahl)


@bp.route("/bank/<int:uid>/zuordnen", methods=["POST"])
def bank_zuordnen(uid):
    from . import bankabgleich as ba
    con = dbm.get_db()
    did = request.form.get("dokument_id", type=int)
    if not did:
        raise EingabeFehler("Bitte eine Rechnung auswählen.")
    with dbm.Transaktion(con):
        ba.zuordnen(con, uid, did)
    flash("Zahlung zugeordnet und bei der Rechnung erfasst.", "ok")
    return redirect(url_for("main.bank"))


@bp.route("/bank/<int:uid>/ignorieren", methods=["POST"])
def bank_ignorieren(uid):
    from . import bankabgleich as ba
    con = dbm.get_db()
    with dbm.Transaktion(con):
        ba.ignorieren(con, uid, wieder_oeffnen=bool(request.form.get("oeffnen")))
    return redirect(url_for("main.bank", ansicht=request.form.get("ansicht", "offen")))


# ====================================================================== Leihgeräte

from . import leih_pdf as lpdf  # noqa: E402
from . import leihgeraete as lg  # noqa: E402

LEIHE_SQL = ("SELECT l.*, g.bezeichnung, g.seriennummer AS g_seriennummer, g.inventarnr, g.zeitwert, "
             "k.kundennr, k.firma, k.vorname, k.nachname, k.typ AS ktyp, k.email AS kemail FROM leihen l "
             "JOIN leihgeraete g ON g.id=l.geraet_id JOIN kunden k ON k.id=l.kunde_id ")


def _leihe_laden(lid):
    le = dbm.get_db().execute(LEIHE_SQL + "WHERE l.id=?", (lid,)).fetchone()
    if not le:
        abort(404)
    return le


def _leihen_zum_auftrag(con, aid):
    return [dict(le, schaeden=lg.schaeden(con, le["id"]), offen_abzurechnen=lg.offen_abzurechnen(con, le),
                 ueberfaellig=lg.ist_ueberfaellig(le))
            for le in con.execute(LEIHE_SQL + "WHERE l.auftrag_id=? ORDER BY l.id DESC", (aid,)).fetchall()]


def _geraet_laden(gid):
    g = dbm.get_db().execute("SELECT * FROM leihgeraete WHERE id=?", (gid,)).fetchone()
    if not g:
        abort(404)
    return g


def _geraet_felder():
    datum = _f("anschaffung_am")
    if datum:
        try:
            date.fromisoformat(datum)
        except ValueError:
            raise EingabeFehler("Bitte ein gültiges Anschaffungsdatum angeben.")
    return {
        "bezeichnung": _f("bezeichnung"), "geraetetyp": _f("geraetetyp"), "hersteller": _f("hersteller"),
        "modell": _f("modell"), "seriennummer": _f("seriennummer"), "inventarnr": _f("inventarnr"),
        "zubehoer": json.dumps(lg.zubehoer_aus_text(request.form.get("zubehoer", "")), ensure_ascii=False),
        "zustand": _f("zustand"), "anschaffung_am": datum or None,
        "anschaffungswert": cent_aus_text(_f("anschaffungswert")), "zeitwert": cent_aus_text(_f("zeitwert")),
        "gebuehr_art": _f("gebuehr_art", "kostenlos"), "gebuehr_betrag": cent_aus_text(_f("gebuehr_betrag")),
        "frei_tage": int(zahl_aus_text(_f("frei_tage"), 0)), "kaution": cent_aus_text(_f("kaution")),
    }


@bp.route("/leihgeraete")
def leihgeraete():
    con = dbm.get_db()
    status = request.args.get("status", "")
    suche = request.args.get("q", "").strip()
    sql = ("SELECT g.*, l.id AS leihe_id, l.leihnr, l.ausgabe_am, l.rueckgabe_geplant, l.auftrag_id, l.auftragsnr, "
           "k.id AS kunde_id, k.kundennr, k.firma, k.vorname, k.nachname, k.typ AS ktyp FROM leihgeraete g "
           "LEFT JOIN leihen l ON l.geraet_id=g.id AND l.rueckgabe_am IS NULL AND l.storniert_am IS NULL "
           "LEFT JOIN kunden k ON k.id=l.kunde_id WHERE 1=1 ")
    args = []
    if status in lg.STATUS:
        sql += "AND g.status=? "
        args.append(status)
    elif status != "alle":
        sql += "AND g.status<>'ausgemustert' "
    if suche:
        sql += ("AND (g.bezeichnung LIKE ? OR g.seriennummer LIKE ? OR g.inventarnr LIKE ? OR g.hersteller LIKE ? "
                "OR g.modell LIKE ? OR g.geraetetyp LIKE ? OR k.nachname LIKE ? OR k.firma LIKE ? OR l.auftragsnr LIKE ?) ")
        args += [f"%{suche}%"] * 9
    geraete = con.execute(sql + "ORDER BY g.bezeichnung", args).fetchall()
    zahlen = {r[0]: r[1] for r in con.execute("SELECT status, COUNT(*) FROM leihgeraete GROUP BY status")}
    return render_template("leihgeraete.html", geraete=geraete, status=status, suche=suche, status_namen=lg.STATUS,
                           zahlen=zahlen, heute=date.today().isoformat(), gebuehr=lg.gebuehr_beschreibung)


@bp.route("/leihgeraete/neu", methods=["GET", "POST"])
@bp.route("/leihgeraete/<int:gid>", methods=["GET", "POST"])
def leihgeraet(gid=None):
    con = dbm.get_db()
    g = _geraet_laden(gid) if gid else None
    if request.method == "POST":
        felder = _geraet_felder()
        with dbm.Transaktion(con):
            gid = lg.geraet_speichern(con, gid, felder)
        flash("Leihgerät gespeichert.", "ok")
        return redirect(url_for("main.leihgeraet", gid=gid))
    leihen_liste, verlauf, alle_schaeden, aktiv = [], [], [], None
    if g:
        leihen_liste = con.execute(LEIHE_SQL + "WHERE l.geraet_id=? ORDER BY l.ausgabe_am DESC", (gid,)).fetchall()
        aktiv = next((le for le in leihen_liste if not le["rueckgabe_am"] and not le["storniert_am"]), None)
        verlauf = con.execute("SELECT * FROM leihgeraet_verlauf WHERE geraet_id=? ORDER BY zeitpunkt DESC, id DESC",
                              (gid,)).fetchall()
        alle_schaeden = con.execute("SELECT s.*, l.leihnr FROM schadensfaelle s JOIN leihen l ON l.id=s.leihe_id "
                                    "WHERE s.geraet_id=? ORDER BY s.id DESC", (gid,)).fetchall()
    return render_template("leihgeraet.html", g=g, status_namen=lg.STATUS, gebuehr_arten=lg.GEBUEHR_ARTEN,
                           zubehoer=lg.liste_aus_json(g["zubehoer"]) if g else [], leihen=leihen_liste, aktiv=aktiv,
                           verlauf=verlauf, schaeden=alle_schaeden, kostenarten=lg.KOSTENARTEN,
                           fotos=fot.liste(con, leihgeraet_id=gid) if g else [], heute=date.today().isoformat(),
                           gebuehr=lg.gebuehr_beschreibung)


@bp.route("/leihgeraete/<int:gid>/status", methods=["POST"])
def leihgeraet_status(gid):
    con = dbm.get_db()
    _geraet_laden(gid)
    with dbm.Transaktion(con):
        lg.status_setzen(con, gid, _f("status"), _f("grund"))
    flash("Status geändert.", "ok")
    return redirect(url_for("main.leihgeraet", gid=gid))


@bp.route("/leihgeraete/<int:gid>/fotos", methods=["POST"])
def leihgeraet_fotos(gid):
    _geraet_laden(gid)
    return _foto_hochladen(kategorien=["Leihgerät"], leihgeraet_id=gid)


# ---------------------------------------------------------------------- Ausgabe

@bp.route("/auftraege/<int:aid>/leihgeraet-ausgeben", methods=["GET", "POST"])
def leihe_ausgeben(aid):
    con = dbm.get_db()
    a = _auftrag_laden(aid)
    token = _upload_token(schluessel="leihe_ausgabe_token")
    werte = {}
    if request.method == "POST":
        werte = request.form.to_dict()
        try:
            gid = request.form.get("geraet_id", type=int)
            art = _f("gebuehr_art")
            with dbm.Transaktion(con):
                lid = lg.ausgeben(
                    con, aid, gid, lg.zeit_aus_eingabe(_f("ausgabe_am")), _f("rueckgabe_geplant"),
                    request.form.getlist("zubehoer"), _f("zustand_ausgabe"), art,
                    cent_aus_text(_f("gebuehr_betrag")), int(zahl_aus_text(_f("frei_tage"), 0)),
                    bool(request.form.get("kaution_erhalten")), cent_aus_text(_f("kaution_betrag")),
                    _f("kaution_zahlart"))
                g = con.execute("SELECT * FROM leihgeraete WHERE id=?", (gid,)).fetchone()
                anzahl = fot.zuordnen(con, request.form.get("upload_token") or token, auftrag_id=aid,
                                      leihgeraet_id=gid, leihe_id=lid, text=f"bei Ausgabe von {g['bezeichnung']}")
        except EingabeFehler as e:
            flash(f"Das Leihgerät wurde NICHT ausgegeben: {e} Ihre Eingaben und Fotos sind noch da.", "fehler")
        else:
            _upload_token(neu=True, schluessel="leihe_ausgabe_token")
            flash("Leihgerät ausgegeben" + (f" – {anzahl} Foto(s) zugeordnet." if anzahl else ".")
                  + " Bitte das Übergabeprotokoll drucken und unterschreiben lassen.", "ok")
            return redirect(url_for("main.leihe", lid=lid))
    geraete = con.execute("SELECT * FROM leihgeraete WHERE status='verfuegbar' ORDER BY bezeichnung").fetchall()
    geraete_json = {g["id"]: {"zubehoer": lg.liste_aus_json(g["zubehoer"]), "gebuehr_art": g["gebuehr_art"],
                              "gebuehr_betrag": euro(g["gebuehr_betrag"]).replace(" €", ""),
                              "frei_tage": g["frei_tage"], "kaution": euro(g["kaution"]).replace(" €", ""),
                              "zustand": g["zustand"] or ""} for g in geraete}
    jetzt = dbm.jetzt_berlin()[:19]
    return render_template("leihe_ausgabe.html", a=a, geraete=geraete, geraete_json=geraete_json, werte=werte,
                           zubehoer_auswahl=request.form.getlist("zubehoer") if request.method == "POST" else None,
                           token=token, jetzt=jetzt, rueckgabe_vorschlag=plus_tage(heute(), 7),
                           gebuehr_arten=lg.LEIHE_GEBUEHR_ARTEN, zahlarten=lg.ZAHLARTEN,
                           fotos=fot.liste(con, upload_token=token, mit_geloeschten=False))


@bp.route("/leihen/fotos/vorab", methods=["POST"])
def leihe_fotos_vorab():
    token = request.form.get("upload_token") or ""
    if not token or token not in (session.get("leihe_ausgabe_token"), session.get("leihe_rueckgabe_token")):
        return jsonify(ok=False, meldung="Sitzung abgelaufen – bitte die Seite neu laden."), 400
    return _foto_hochladen(token=token, kategorien=fot.LEIH_KATEGORIEN)


# ---------------------------------------------------------------------- Leihvorgang

@bp.route("/leihen/<int:lid>")
def leihe(lid):
    con = dbm.get_db()
    le = _leihe_laden(lid)
    fotos = fot.liste(con, leihe_id=lid)
    rechnung = con.execute("SELECT id, nummer, status FROM dokumente WHERE id=?", (le["rechnung_id"],)).fetchone() \
        if le["rechnung_id"] else None
    auftrag_re = con.execute("SELECT d.id, d.status, d.nummer FROM auftraege a JOIN dokumente d ON d.id=a.rechnung_id "
                             "WHERE a.id=?", (le["auftrag_id"],)).fetchone() if le["auftrag_id"] else None
    alle = lg.schaeden(con, lid, mit_stornierten=True)
    interne = {s["id"]: con.execute("SELECT id, auftragsnr, status FROM auftraege WHERE id=?",
                                    (s["interner_auftrag_id"],)).fetchone() for s in alle if s["interner_auftrag_id"]}
    return render_template("leihe.html", le=le, fotos=fotos, schaeden=alle, verrechnung=lg.kaution_verrechnung(con, le),
                           rechnung=rechnung, auftrag_re=auftrag_re, offen_abzurechnen=lg.offen_abzurechnen(con, le),
                           ziel=lg.abrechnungsziel(con, le)[0],
                           ueberfaellig=lg.ist_ueberfaellig(le), zubehoer_aus=lg.liste_aus_json(le["zubehoer_ausgabe"]),
                           zubehoer_zurueck=lg.liste_aus_json(le["zubehoer_rueckgabe"]) if le["rueckgabe_am"] else None,
                           gebuehr=lg.gebuehr_beschreibung(le["gebuehr_art"], le["gebuehr_betrag"], le["frei_tage"]),
                           kostenarten=lg.KOSTENARTEN, kaution_status=lg.KAUTION_STATUS, interne=interne,
                           leih_kategorien=fot.LEIH_KATEGORIEN)


@bp.route("/leihen/<int:lid>/fotos", methods=["POST"])
def leihe_fotos(lid):
    le = _leihe_laden(lid)
    return _foto_hochladen(auftrag_id=le["auftrag_id"], kategorien=fot.LEIH_KATEGORIEN,
                           leihgeraet_id=le["geraet_id"], leihe_id=lid)


@bp.route("/leihen/<int:lid>/rueckgabe", methods=["GET", "POST"])
def leihe_rueckgabe(lid):
    con = dbm.get_db()
    le = _leihe_laden(lid)
    if le["rueckgabe_am"] or le["storniert_am"]:
        flash("Dieses Leihgerät wurde bereits zurückgenommen.", "warnung")
        return redirect(url_for("main.leihe", lid=lid))
    token = _upload_token(schluessel="leihe_rueckgabe_token")
    werte = {}
    if request.method == "POST":
        werte = request.form.to_dict()
        try:
            zustand = _f("zustand")
            zurueck = request.form.getlist("zubehoer")
            fehlt = [z for z in lg.liste_aus_json(le["zubehoer_ausgabe"]) if z not in zurueck]
            schaden = None
            if zustand == "schaden" or fehlt:
                schaden = {"beschreibung": _f("schaden_beschreibung"), "kostenart": _f("kostenart"),
                           "betrag": cent_aus_text(_f("schaden_betrag"))}
            gebuehr = _f("gebuehr")
            with dbm.Transaktion(con):
                sid = lg.zuruecknehmen(con, lid, lg.zeit_aus_eingabe(_f("rueckgabe_am")), zurueck, zustand,
                                       _f("rueckgabe_notiz"), cent_aus_text(gebuehr) if gebuehr else None, schaden)
                fot.zuordnen(con, request.form.get("upload_token") or token, auftrag_id=le["auftrag_id"],
                             leihgeraet_id=le["geraet_id"], leihe_id=lid, schadensfall_id=sid,
                             text=f"bei Rückgabe von {le['bezeichnung']}")
                if sid and request.form.get("interner_auftrag"):
                    lg.interner_auftrag(con, sid)
                neue_rechnung = None
                if request.form.get("abrechnen"):
                    neue_rechnung = _leihe_abrechnen(con, lid)
        except EingabeFehler as e:
            flash(f"Die Rückgabe wurde NICHT gespeichert: {e} Ihre Eingaben und Fotos sind noch da.", "fehler")
        else:
            _upload_token(neu=True, schluessel="leihe_rueckgabe_token")
            flash("Leihgerät zurückgenommen." + (" Schadensfall angelegt." if sid else ""), "ok")
            if neue_rechnung:
                return redirect(url_for("main.dokument", did=neue_rechnung))
            return redirect(url_for("main.leihe", lid=lid))
    jetzt = dbm.jetzt_berlin()[:19]
    tage, berechnet, vorschlag, text = lg.gebuehr_berechnen(le, dbm.jetzt_berlin())
    return render_template("leihe_rueckgabe.html", le=le, werte=werte, token=token, jetzt=jetzt,
                           zubehoer_auswahl=request.form.getlist("zubehoer") if request.method == "POST" else None,
                           tage=tage, berechnet=berechnet, ziel=lg.abrechnungsziel(con, le)[0],
                           zubehoer_aus=lg.liste_aus_json(le["zubehoer_ausgabe"]), vorschlag=vorschlag, text=text,
                           kostenarten=lg.KOSTENARTEN, gebuehr=lg.gebuehr_beschreibung(
                               le["gebuehr_art"], le["gebuehr_betrag"], le["frei_tage"]),
                           ausgabe_fotos=fot.liste(con, leihe_id=lid, kategorie="Leihgerät Ausgabe",
                                                   mit_geloeschten=False),
                           fotos=fot.liste(con, upload_token=token, mit_geloeschten=False))


def _leihe_abrechnen(con, lid, separat_erzwingen=False):
    """In den Rechnungsentwurf des Auftrags übernehmen – oder eigene Rechnung. Gibt die Dokument-ID zurück.

    Läuft der Auftrag noch (ohne Rechnungsentwurf), wird nichts abgerechnet (None): die Übernahme erfolgt dann
    automatisch beim Erledigen – außer separat_erzwingen.
    """
    le = con.execute("SELECT * FROM leihen WHERE id=?", (lid,)).fetchone()
    ziel, did = lg.abrechnungsziel(con, le)
    if ziel == "entwurf":
        lg.in_rechnung_uebernehmen(con, lid, did)
        return did
    if ziel == "warten" and not separat_erzwingen:
        return None
    if ziel == "warten":
        con.execute("UPDATE leihen SET separat_abrechnen=1 WHERE id=?", (lid,))
    return lg.separat_abrechnen(con, lid)


@bp.route("/leihen/<int:lid>/abrechnen", methods=["POST"])
def leihe_abrechnen(lid):
    con = dbm.get_db()
    _leihe_laden(lid)
    with dbm.Transaktion(con):
        did = _leihe_abrechnen(con, lid, separat_erzwingen=True)
    flash("Leihgebühr/Schaden in den Rechnungsentwurf übernommen. Bitte prüfen und festschreiben.", "ok")
    return redirect(url_for("main.dokument", did=did))


@bp.route("/leihen/<int:lid>/schaden", methods=["POST"])
def leihe_schaden(lid):
    con = dbm.get_db()
    le = _leihe_laden(lid)
    if not le["rueckgabe_am"]:
        raise EingabeFehler("Schäden bitte bei der Rücknahme erfassen.")
    with dbm.Transaktion(con):
        sid = lg.schadensfall_anlegen(con, lid, _f("beschreibung"), _f("kostenart"), cent_aus_text(_f("betrag")))
        if request.form.get("interner_auftrag"):
            lg.interner_auftrag(con, sid)
    flash("Schadensfall angelegt.", "ok")
    return redirect(url_for("main.leihe", lid=lid) + "#schaden")


@bp.route("/schaeden/<int:sid>/stornieren", methods=["POST"])
def schaden_stornieren(sid):
    con = dbm.get_db()
    s = con.execute("SELECT * FROM schadensfaelle WHERE id=?", (sid,)).fetchone() or abort(404)
    with dbm.Transaktion(con):
        lg.schaden_stornieren(con, sid, _f("grund"))
    flash("Schadensfall storniert (bleibt markiert gespeichert).", "ok")
    return redirect(url_for("main.leihe", lid=s["leihe_id"]) + "#schaden")


@bp.route("/schaeden/<int:sid>/interner-auftrag", methods=["POST"])
def schaden_interner_auftrag(sid):
    con = dbm.get_db()
    with dbm.Transaktion(con):
        aid = lg.interner_auftrag(con, sid)
    flash("Interner Reparaturauftrag für das Leihgerät angelegt.", "ok")
    return redirect(url_for("main.auftrag", aid=aid))


@bp.route("/leihen/<int:lid>/stornieren", methods=["POST"])
def leihe_stornieren(lid):
    con = dbm.get_db()
    _leihe_laden(lid)
    with dbm.Transaktion(con):
        lg.leihe_stornieren(con, lid, _f("grund"))
    flash("Ausgabe storniert. Das Leihgerät ist wieder verfügbar; der Vorgang bleibt markiert gespeichert.", "ok")
    return redirect(url_for("main.leihe", lid=lid))


@bp.route("/leihen/<int:lid>/kaution-zurueck", methods=["POST"])
def leihe_kaution_zurueck(lid):
    con = dbm.get_db()
    _leihe_laden(lid)
    with dbm.Transaktion(con):
        lg.kaution_zurueckgezahlt(con, lid)
    flash("Rückzahlung der Kaution vermerkt.", "ok")
    return redirect(url_for("main.leihe", lid=lid))


@bp.route("/leihen/<int:lid>/<art>.pdf")
def leihe_pdf(lid, art):
    if art not in lpdf.TITEL:
        abort(404)
    le = _leihe_laden(lid)
    if art != "ausgabe" and not le["rueckgabe_am"]:
        raise EingabeFehler("Das Leihgerät ist noch nicht zurückgenommen.")
    from io import BytesIO
    pdf = lpdf.protokoll_pdf(dbm.get_db(), lid, art, daten_dir())
    return send_file(BytesIO(pdf), mimetype="application/pdf", download_name=lpdf.dateiname(le, art),
                     as_attachment=request.args.get("download") == "1")


@bp.route("/leihen/<int:lid>/email", methods=["GET", "POST"])
def leihe_email(lid):
    con = dbm.get_db()
    le = _leihe_laden(lid)
    art = request.values.get("art", "ausgabe")
    if art not in lpdf.TITEL or (art != "ausgabe" and not le["rueckgabe_am"]):
        abort(404)
    einst = dbm.einstellungen(con)
    if request.method == "POST":
        an = _f("an")
        if "@" not in an:
            raise EingabeFehler("Bitte eine gültige E-Mail-Adresse angeben.")
        pdf = lpdf.protokoll_pdf(con, lid, art, daten_dir())
        try:
            hinweis = senden(con, None, an, _f("betreff"), request.form.get("text", ""), pdf, lpdf.dateiname(le, art))
        except MailFehler as e:
            flash(f"E-Mail wurde NICHT gesendet: {e}", "fehler")
            return redirect(url_for("main.leihe_email", lid=lid, art=art))
        with dbm.Transaktion(con):
            text = f"{lpdf.TITEL[art]} {le['leihnr']} an {an}"
            lg.verlauf(con, le["geraet_id"], "Protokoll per E-Mail versendet", text)
            if le["auftrag_id"]:
                auf.verlauf(con, le["auftrag_id"], "Leihgerät-Protokoll per E-Mail versendet", text)
        flash(f"E-Mail an {an} wurde gesendet.", "ok")
        if hinweis:
            flash(hinweis, "warnung")
        return redirect(url_for("main.leihe", lid=lid))
    name = kunde_name({**dict(le), "typ": le["ktyp"]})
    titel = lpdf.TITEL[art]
    text = (f"Guten Tag {name},\n\nanbei erhalten Sie {('den ' + titel) if art == 'ausgabe' else ('das ' + titel)} "
            f"{le['leihnr']} zum Leihgerät {le['bezeichnung']}"
            + (f" (Reparaturauftrag {le['auftragsnr']})" if le["auftragsnr"] else "") + ".\n\n"
            + ("Bitte denken Sie daran, vor der Rückgabe Ihre persönlichen Daten vom Gerät zu löschen.\n\n"
               if art == "ausgabe" else "")
            + f"Mit freundlichen Grüßen\n{einst.get('inhaber') or ''}\n{einst.get('firma_name') or ''}")
    return render_template("leihe_email.html", le=le, art=art, titel=titel, an=le["kemail"] or "",
                           betreff=f"{titel} {le['leihnr']} – {einst.get('firma_name') or ''}", text=text,
                           smtp_ok=bool(einst.get("smtp_host")))


# ====================================================================== Programm-Version & Updates

from . import update as upd  # noqa: E402


@bp.route("/version")
def version_info():
    from . import VERSION_NUMMER
    return jsonify(version=VERSION_NUMMER, gestartet=current_app.config.get("GESTARTET"))


@bp.route("/update/pruefen", methods=["POST"])
def update_pruefen():
    from . import VERSION_NUMMER
    con = dbm.get_db()
    try:
        info = upd.neueste_version()
    except upd.UpdateFehler as e:
        with dbm.Transaktion(con):
            dbm.einstellungen_speichern({"update_letzte_pruefung": dbm.jetzt(), "update_fehler": str(e)}, con)
        flash(str(e), "fehler")
        return redirect(url_for("main.einstellungen", bereich="programm"))
    neuer = upd.ist_neuer(info["version"], VERSION_NUMMER)
    with dbm.Transaktion(con):
        dbm.einstellungen_speichern({"update_letzte_pruefung": dbm.jetzt(), "update_fehler": "",
                                     "update_verfuegbar": info["version"] if neuer else "",
                                     "update_hinweise": info["hinweise"][:4000]}, con)
    flash(f"Neue Version {info['version']} verfügbar." if neuer else f"Sie haben die aktuelle Version ({VERSION_NUMMER}).",
          "info" if neuer else "ok")
    return redirect(url_for("main.einstellungen", bereich="programm"))


@bp.route("/update/installieren", methods=["POST"])
def update_installieren():
    from . import VERSION_NUMMER
    if not upd.ist_exe():
        raise EingabeFehler("Automatische Updates gibt es nur in der EXE-Version. Bei der Installation per "
                            "start.bat bitte die neue Version von GitHub herunterladen.")
    con = dbm.get_db()
    try:
        info = upd.neueste_version()
    except upd.UpdateFehler as e:
        flash(str(e), "fehler")
        return redirect(url_for("main.einstellungen", bereich="programm"))
    if not upd.ist_neuer(info["version"], VERSION_NUMMER):
        flash("Es ist bereits die neueste Version installiert.", "ok")
        return redirect(url_for("main.einstellungen", bereich="programm"))

    def backup_vorher():
        ziel, _ = backup_erstellen(daten_dir(), current_app.config["DB_PFAD"], dbm.einstellungen(con))
        with dbm.Transaktion(con):
            dbm.protokollieren("backup_vor_update", "system", None,
                               {"datei": ziel.name, "von": VERSION_NUMMER, "nach": info["version"]}, con=con)

    try:
        upd.installieren(info, vor_austausch=backup_vorher)
    except upd.UpdateFehler as e:
        flash(f"Update fehlgeschlagen – es bleibt bei Version {VERSION_NUMMER}: {e}", "fehler")
        return redirect(url_for("main.einstellungen", bereich="programm"))
    upd.neu_starten(verzoegerung=1.5)
    return render_template("update_laeuft.html", alt=VERSION_NUMMER, neu=info["version"])


@bp.route("/versionen")
def versionen():
    from .versionen import protokoll_html
    return render_template("versionen.html", inhalt=protokoll_html())


# ====================================================================== Verträge & Lizenzen

from . import vertraege as vtr  # noqa: E402

VERTRAG_FELDER = ("bezeichnung", "kategorie", "abrechnung", "beginn", "laufzeit_monate", "mindestlaufzeit_monate",
                  "preis", "einkauf", "anzahl", "auto_verlaengern", "vertragsnummer", "geraet", "notizen",
                  "abgerechnet_bis")


def _vertrag_zusatz(v, einst):
    stufe, text = vtr.zustand(v, erinnerung_tage=int(einst.get("vertrag_erinnerung_tage") or 60))
    return {**dict(v), "zustand": stufe, "zustand_text": text, "monatswert": vtr.monatswert(v)}


@bp.route("/vertraege")
def vertraege_liste():
    con = dbm.get_db()
    einst = dbm.einstellungen(con)
    filt = request.args.get("filter", "aktiv")
    kategorie = request.args.get("kategorie", "")
    zeilen = con.execute("SELECT v.*, k.kundennr, k.firma, k.vorname, k.nachname, k.typ AS ktyp FROM vertraege v "
                         "JOIN kunden k ON k.id=v.kunde_id ORDER BY COALESCE(v.ende, '9999'), v.beginn").fetchall()
    alle = [_vertrag_zusatz(v, einst) for v in zeilen]
    if kategorie:
        alle = [v for v in alle if v["kategorie"] == kategorie]
    gruppen = {
        "aktiv": [v for v in alle if v["zustand"] in ("aktiv", "laeuft_ab", "gekuendigt")],
        "laeuft_ab": [v for v in alle if v["zustand"] == "laeuft_ab"],
        "gekuendigt": [v for v in alle if v["zustand"] in ("gekuendigt", "beendet", "abgelaufen")],
        "alle": alle,
    }
    faellig = sum(len(vtr.faellige_zeitraeume(con, v)) for v in zeilen)
    kennzahlen = {
        "aktiv": len([v for v in alle if v["zustand"] in ("aktiv", "laeuft_ab")]),
        "monatlich": sum(v["monatswert"] for v in alle if v["zustand"] in ("aktiv", "laeuft_ab", "gekuendigt")),
        "laeuft_ab": len(gruppen["laeuft_ab"]),
        "faellig": faellig,
    }
    return render_template("vertraege.html", liste=gruppen.get(filt, gruppen["aktiv"]), filt=filt,
                           anzahl={k: len(v) for k, v in gruppen.items()}, kennzahlen=kennzahlen,
                           kategorien=vtr.KATEGORIEN, kategorie=kategorie, abrechnung=vtr.ABRECHNUNG)


def _vertrag_formular():
    f = {k: _f(k) for k in VERTRAG_FELDER}
    if not f["bezeichnung"]:
        raise EingabeFehler("Bitte eine Bezeichnung angeben.")
    if f["abrechnung"] not in vtr.ABRECHNUNG:
        raise EingabeFehler("Bitte eine Abrechnungsart wählen.")
    try:
        date.fromisoformat(f["beginn"])
    except ValueError:
        raise EingabeFehler("Bitte ein gültiges Beginndatum angeben.")
    for k in ("laufzeit_monate", "mindestlaufzeit_monate"):
        f[k] = int(f[k]) if f[k].isdigit() and int(f[k]) > 0 else None
    if f["abrechnung"] == "laufzeit" and not f["laufzeit_monate"]:
        raise EingabeFehler("Bei Abrechnung „je Laufzeit“ bitte die Laufzeit in Monaten angeben (12, 24, 36 …).")
    f["preis"] = cent_aus_text(f["preis"])
    f["einkauf"] = cent_aus_text(f["einkauf"])
    f["anzahl"] = zahl_aus_text(f["anzahl"], 1) or 1
    f["auto_verlaengern"] = 1 if request.form.get("auto_verlaengern") else 0
    f["kategorie"] = f["kategorie"] or "Sonstiges"
    if f["abgerechnet_bis"]:
        try:
            date.fromisoformat(f["abgerechnet_bis"])
        except ValueError:
            raise EingabeFehler("„Bereits berechnet bis“ ist kein gültiges Datum.")
    else:
        f["abgerechnet_bis"] = None
    ende = vtr.laufzeit_ende(date.fromisoformat(f["beginn"]), f["laufzeit_monate"])
    return f, ende.isoformat() if ende else None


@bp.route("/vertraege/neu", methods=["GET", "POST"])
@bp.route("/vertraege/<int:vid>", methods=["GET", "POST"])
def vertrag(vid=None):
    con = dbm.get_db()
    einst = dbm.einstellungen(con)
    v = con.execute("SELECT * FROM vertraege WHERE id=?", (vid,)).fetchone() if vid else None
    if vid and not v:
        abort(404)
    if request.method == "POST":
        felder, ende = _vertrag_formular()
        with dbm.Transaktion(con):
            if v:
                bereits = con.execute("SELECT MAX(bis) FROM vertrag_abrechnungen WHERE vertrag_id=?", (vid,)).fetchone()[0]
                if bereits and felder["beginn"] != v["beginn"]:
                    raise EingabeFehler("Der Beginn kann nicht mehr geändert werden, weil schon abgerechnet wurde.")
                if v["abrechnung"] == "laufzeit" and v["ende"] and bereits:
                    ende = max(ende or "", v["ende"])  # bereits verlängerte Laufzeit behalten
                con.execute(f"UPDATE vertraege SET {', '.join(f'{k}=?' for k in felder)}, ende=?, geaendert_am=? "
                            "WHERE id=?", (*felder.values(), ende, dbm.jetzt(), vid))
                dbm.protokollieren("vertrag_geaendert", "vertrag", vid, con=con)
            else:
                kid = request.form.get("kunde_id", type=int)
                if not kid or not con.execute("SELECT 1 FROM kunden WHERE id=?", (kid,)).fetchone():
                    raise EingabeFehler("Bitte einen Kunden auswählen.")
                art = request.form.get("vertragsart_id", type=int)
                cur = con.execute(
                    f"INSERT INTO vertraege (kunde_id, vertragsart_id, {', '.join(felder)}, ende, erstellt_am, "
                    f"geaendert_am) VALUES (?, ?, {', '.join('?' * len(felder))}, ?, ?, ?)",
                    (kid, art, *felder.values(), ende, dbm.jetzt(), dbm.jetzt()))
                vid = cur.lastrowid
                dbm.protokollieren("vertrag_angelegt", "vertrag", vid, {"kunde": kid, "bezeichnung": felder["bezeichnung"]},
                                   con=con)
        flash("Vertrag gespeichert.", "ok")
        if request.form.get("danach") == "kunde":
            return redirect(url_for("main.kunde", kid=request.form.get("kunde_id", type=int) or v["kunde_id"]))
        return redirect(url_for("main.vertrag", vid=vid))
    kunde = con.execute("SELECT * FROM kunden WHERE id=?",
                        (v["kunde_id"] if v else request.args.get("kunde_id", type=int),)).fetchone()
    abrechnungen = con.execute(
        "SELECT a.*, d.nummer, d.status AS dstatus FROM vertrag_abrechnungen a JOIN dokumente d ON d.id=a.dokument_id "
        "WHERE a.vertrag_id=? ORDER BY a.von DESC", (vid,)).fetchall() if vid else []
    return render_template(
        "vertrag.html", v=_vertrag_zusatz(v, einst) if v else None, kunde=kunde,
        kunden=con.execute("SELECT * FROM kunden WHERE archiviert=0 ORDER BY COALESCE(NULLIF(firma,''), nachname), "
                           "vorname").fetchall(),
        arten=[dict(a) for a in con.execute("SELECT * FROM vertragsarten WHERE aktiv=1 ORDER BY kategorie, name")],
        kategorien=vtr.KATEGORIEN, abrechnung=vtr.ABRECHNUNG, abrechnungen=abrechnungen, heute=heute(),
        kuendigung_vorschlag=vtr.fruehestes_kuendigungsdatum(v).isoformat() if v else "",
        faellig=vtr.faellige_zeitraeume(con, v) if v else [])


@bp.route("/vertraege/<int:vid>/kuendigen", methods=["POST"])
def vertrag_kuendigen(vid):
    con = dbm.get_db()
    v = con.execute("SELECT * FROM vertraege WHERE id=?", (vid,)).fetchone() or abort(404)
    if request.form.get("zuruecknehmen"):
        with dbm.Transaktion(con):
            con.execute("UPDATE vertraege SET status='aktiv', gekuendigt_am=NULL, kuendigung_zum=NULL, "
                        "kuendigungsgrund=NULL, geaendert_am=? WHERE id=?", (dbm.jetzt(), vid))
            dbm.protokollieren("vertrag_kuendigung_zurueck", "vertrag", vid, con=con)
        flash("Kündigung zurückgenommen – der Vertrag läuft weiter.", "ok")
        return redirect(url_for("main.vertrag", vid=vid))
    zum = _f("kuendigung_zum")
    try:
        date.fromisoformat(zum)
    except ValueError:
        raise EingabeFehler("Bitte das Datum angeben, zu dem der Vertrag endet.")
    with dbm.Transaktion(con):
        con.execute("UPDATE vertraege SET status='gekuendigt', gekuendigt_am=?, kuendigung_zum=?, kuendigungsgrund=?, "
                    "geaendert_am=? WHERE id=?", (_f("gekuendigt_am") or heute(), zum, _f("kuendigungsgrund"),
                                                  dbm.jetzt(), vid))
        dbm.protokollieren("vertrag_gekuendigt", "vertrag", vid, {"zum": zum, "grund": _f("kuendigungsgrund")}, con=con)
    flash(f"Vertrag gekündigt zum {datum_de_kurz(zum)}. Danach werden keine Rechnungen mehr erstellt.", "ok")
    return redirect(url_for("main.vertrag", vid=vid))


def datum_de_kurz(iso):
    from .hilfen import datum_de
    return datum_de(iso)


@bp.route("/vertraege/<int:vid>/verlaengern", methods=["POST"])
def vertrag_verlaengern(vid):
    did = vtr.verlaengern(dbm.get_db(), vid)
    flash("Lizenz verlängert – Rechnungsentwurf für die neue Laufzeit wurde erstellt.", "ok")
    return redirect(url_for("main.dokument", did=did))


@bp.route("/vertraege/<int:vid>/loeschen", methods=["POST"])
def vertrag_loeschen(vid):
    con = dbm.get_db()
    if con.execute("SELECT 1 FROM vertrag_abrechnungen a JOIN dokumente d ON d.id=a.dokument_id "
                   "WHERE a.vertrag_id=? AND d.status<>'entwurf'", (vid,)).fetchone():
        raise EingabeFehler("Zu diesem Vertrag gibt es festgeschriebene Rechnungen. Bitte kündigen statt löschen.")
    kid = con.execute("SELECT kunde_id FROM vertraege WHERE id=?", (vid,)).fetchone()
    with dbm.Transaktion(con):
        for r in con.execute("SELECT DISTINCT dokument_id FROM vertrag_abrechnungen WHERE vertrag_id=?", (vid,)).fetchall():
            con.execute("DELETE FROM positionen WHERE dokument_id=?", (r[0],))
            con.execute("DELETE FROM dokumente WHERE id=? AND status='entwurf'", (r[0],))
        con.execute("DELETE FROM vertraege WHERE id=?", (vid,))
        dbm.protokollieren("vertrag_geloescht", "vertrag", vid, con=con)
    flash("Vertrag gelöscht.", "ok")
    return redirect(url_for("main.kunde", kid=kid[0]) if kid else url_for("main.vertraege_liste"))


@bp.route("/vertraege/abrechnen", methods=["POST"])
def vertraege_abrechnen():
    e = vtr.abrechnungslauf(dbm.get_db(), daten_dir())
    if not e["rechnungen"]:
        flash("Es ist nichts zur Abrechnung fällig.", "info")
    else:
        text = f"{e['rechnungen']} Rechnung(en) erstellt"
        if e["festgeschrieben"]:
            text += f", {e['festgeschrieben']} festgeschrieben, {e['versendet']} per E-Mail versendet"
        else:
            text += " (Entwürfe – bitte prüfen und festschreiben)"
        flash(text + ".", "ok")
    for f in e["fehler"]:
        flash(f, "fehler")
    return redirect(url_for("main.dokumente", status="entwurf") if e["rechnungen"] and not e["festgeschrieben"]
                    else url_for("main.vertraege_liste"))


@bp.route("/vertragsarten", methods=["GET", "POST"])
@bp.route("/vertragsarten/<int:aid>", methods=["GET", "POST"])
def vertragsarten(aid=None):
    con = dbm.get_db()
    art = con.execute("SELECT * FROM vertragsarten WHERE id=?", (aid,)).fetchone() if aid else None
    if request.method == "POST":
        if request.form.get("loeschen") and art:
            with dbm.Transaktion(con):
                con.execute("DELETE FROM vertragsarten WHERE id=?", (aid,))
                dbm.protokollieren("vertragsart_geloescht", "vertragsart", aid, con=con)
            flash("Vertragsart gelöscht (bestehende Verträge bleiben erhalten).", "ok")
            return redirect(url_for("main.vertragsarten"))
        if not _f("name") or _f("abrechnung") not in vtr.ABRECHNUNG:
            raise EingabeFehler("Bitte Name und Abrechnungsart angeben.")
        zahl = lambda k: int(_f(k)) if _f(k).isdigit() and int(_f(k)) > 0 else None  # noqa: E731
        werte = (_f("name"), _f("kategorie") or "Sonstiges", _f("beschreibung"), _f("abrechnung"), zahl("laufzeit_monate"),
                 zahl("mindestlaufzeit_monate"), cent_aus_text(_f("preis")), cent_aus_text(_f("einkauf")),
                 1 if request.form.get("auto_verlaengern") else 0, 1 if request.form.get("aktiv") else 0)
        with dbm.Transaktion(con):
            if art:
                con.execute("UPDATE vertragsarten SET name=?, kategorie=?, beschreibung=?, abrechnung=?, laufzeit_monate=?, "
                            "mindestlaufzeit_monate=?, preis=?, einkauf=?, auto_verlaengern=?, aktiv=? WHERE id=?",
                            (*werte, aid))
            else:
                con.execute("INSERT INTO vertragsarten (name, kategorie, beschreibung, abrechnung, laufzeit_monate, "
                            "mindestlaufzeit_monate, preis, einkauf, auto_verlaengern, aktiv, erstellt_am) "
                            "VALUES (?,?,?,?,?,?,?,?,?,?,?)", (*werte, dbm.jetzt()))
            dbm.protokollieren("vertragsart_gespeichert", "vertragsart", aid, {"name": werte[0]}, con=con)
        flash("Vertragsart gespeichert.", "ok")
        return redirect(url_for("main.vertragsarten"))
    liste = con.execute("SELECT * FROM vertragsarten ORDER BY aktiv DESC, kategorie, name").fetchall()
    return render_template("vertragsarten.html", liste=liste, art=art, kategorien=vtr.KATEGORIEN,
                           abrechnung=vtr.ABRECHNUNG, neu=request.args.get("neu") or aid)


# ====================================================================== IMAP: Gesendet-Ordner (Einstellungen)

def _gesendet_cfg_aus_formular():
    """IMAP-Konfiguration aus den (evtl. noch nicht gespeicherten) Formularfeldern."""
    from .imap_ablage import konfiguration
    f = request.form
    werte = {
        "gesendet_imap_host": f.get("gesendet_imap_host", "").strip(),
        "gesendet_imap_port": f.get("gesendet_imap_port", "").strip() or 993,
        "gesendet_imap_sicherheit": f.get("gesendet_imap_sicherheit") or "ssl",
        "gesendet_gleiche_zugangsdaten": f.get("gesendet_gleiche_zugangsdaten") in ("on", "1", "true"),
        "gesendet_imap_benutzer": f.get("gesendet_imap_benutzer", "").strip(),
        "gesendet_ordner": f.get("gesendet_ordner", "").strip(),
    }
    if f.get("smtp_benutzer"):
        werte["smtp_benutzer"] = f.get("smtp_benutzer").strip()
    pw = f.get("smtp_passwort") if werte["gesendet_gleiche_zugangsdaten"] else f.get("gesendet_imap_passwort")
    if pw:
        werte["passwort_klartext"] = pw
    return konfiguration(dbm.einstellungen(), werte)


@bp.route("/einstellungen/imap-ordner", methods=["POST"])
def imap_ordner_abrufen():
    from .imap_ablage import AblageFehler, _abmelden, ordner_auflisten, verbinden
    try:
        imap = verbinden(_gesendet_cfg_aus_formular())
        try:
            ordner = ordner_auflisten(imap)
        finally:
            _abmelden(imap)
    except AblageFehler as e:
        return jsonify(ok=False, meldung=str(e))
    return jsonify(ok=True, ordner=ordner,
                   meldung=f"{len(ordner)} Ordner gefunden." + (" Der Gesendet-Ordner ist vorausgewählt."
                                                                 if any(o["gesendet"] for o in ordner) else ""))


@bp.route("/einstellungen/historie/abrufen", methods=["POST"])
def historie_abrufen():
    from . import email_historie as eh
    if request.form.get("neu_abgleichen"):
        eh.zuruecksetzen(dbm.get_db())
    eh.im_hintergrund(current_app._get_current_object(), eh.abgleich_mit_protokoll,
                      synchron=current_app.config.get("HISTORIE_SYNCHRON", False))
    flash("E-Mail-Historie wird im Hintergrund abgeglichen. Das Ergebnis steht nach kurzer Zeit hier und bei den "
          "Kunden.", "ok")
    return redirect(url_for("main.einstellungen", bereich="anfragen") + "#historie")


@bp.route("/einstellungen/anfragen/imap-ordner", methods=["POST"])
def anfragen_imap_ordner():
    """Ordnerliste des Anfragen-/Historie-Postfachs (Namen in IMAP-UTF-7 werden lesbar dekodiert)."""
    from .imap_ablage import ordner_auflisten
    f = request.form
    werte = {"imap_host": f.get("imap_host", "").strip(), "imap_port": f.get("imap_port", "").strip(),
             "imap_sicherheit": f.get("imap_sicherheit", ""), "imap_benutzer": f.get("imap_benutzer", "").strip(),
             "imap_passwort_klartext": f.get("imap_passwort", "")}
    try:
        imap = anf.imap_anmelden(anf.imap_zugang(dbm.einstellungen(), werte))
        try:
            ordner = ordner_auflisten(imap)
        finally:
            from .imap_verbindung import abmelden
            abmelden(imap)
    except Exception as e:
        return jsonify(ok=False, meldung=str(e))
    return jsonify(ok=True, ordner=ordner, meldung=f"{len(ordner)} Ordner gefunden.")


@bp.route("/einstellungen/anfragen/imap-test", methods=["POST"])
def anfragen_imap_testen():
    """„Verbindung testen“ im Bereich Anfragen – mit den (evtl. noch nicht gespeicherten) Formularwerten."""
    f = request.form
    werte = {"imap_host": f.get("imap_host", "").strip(), "imap_port": f.get("imap_port", "").strip(),
             "imap_sicherheit": f.get("imap_sicherheit", ""), "imap_benutzer": f.get("imap_benutzer", "").strip(),
             "imap_passwort_klartext": f.get("imap_passwort", ""), "imap_ordner": f.get("imap_ordner", "").strip(),
             "imap_zielordner": f.get("imap_zielordner", "").strip(),
             "imap_verschieben": bool(f.get("imap_verschieben"))}
    try:
        ok, zeilen = anf.verbindung_testen(dbm.einstellungen(), werte)
    except anf.AbrufFehler as e:
        return jsonify(ok=False, meldung=str(e))
    return jsonify(ok=ok, meldung="\n".join(zeilen))


@bp.route("/einstellungen/imap-test", methods=["POST"])
def imap_verbindung_testen():
    from .imap_ablage import AblageFehler, verbindung_testen
    try:
        return jsonify(ok=True, meldung=verbindung_testen(_gesendet_cfg_aus_formular()))
    except AblageFehler as e:
        return jsonify(ok=False, meldung=str(e))


# ====================================================================== Navigation: alte Adressen, Suche, Oberfläche

# Alte Adressen der früheren Einzelseiten → neue Stelle (Lesezeichen und Links bleiben gültig)
ALTE_ADRESSEN = {
    "/dokumente": "main.dokumente",
    "/offene-posten": "main.offene_posten",
    "/mahnwesen": "main.mahnwesen",
    "/bestellungen": "main.bestellungen",
    "/lieferanten": "main.lieferanten",
    "/eingangsrechnungen": "main.eingangsrechnungen",
}


def _alte_adresse():
    ziel = ALTE_ADRESSEN[request.url_rule.rule]
    args = request.args.to_dict(flat=False)
    if ziel == "main.dokumente":
        typ = (args.pop("typ", [""]) or [""])[0]
        ziel = "main.kostenvoranschlaege" if typ == "kva" else ziel
        if typ == "":
            args["typ"] = ["alle"]  # früher: alle Arten zusammen
        elif typ not in ("rechnung", "kva"):
            args["typ"] = [typ]
    return redirect(url_for(ziel, **args), 301)


for _alt in ALTE_ADRESSEN:
    bp.add_url_rule(_alt, f"alt_{_alt.strip('/').replace('-', '_')}", _alte_adresse)


@bp.route("/leihgeraete/ausgeben")
def leihe_ausgabe_waehlen():
    """„+ Neu → Leihgerät ausgeben“: Ein Leihgerät wird immer zu einem Auftrag ausgegeben – hier den Auftrag wählen."""
    con = dbm.get_db()
    auftraege = con.execute(AUFTRAG_SQL + "WHERE a.status<>'erledigt' ORDER BY a.eingang_am DESC").fetchall()
    frei = con.execute("SELECT COUNT(*) FROM leihgeraete WHERE status='verfuegbar'").fetchone()[0]
    return render_template("leihe_ausgabe_waehlen.html", auftraege=auftraege, frei=frei)


def _oberflaeche_schluessel():
    return f"oberflaeche:{session.get('benutzer') or 'inhaber'}"


@bp.route("/oberflaeche", methods=["POST"])
def oberflaeche_speichern():
    """Zustand der Oberfläche je Benutzer merken: eingeklappte Gruppen, schmale Seitenleiste, Hell/Dunkel."""
    daten = request.get_json(silent=True) or {}
    con = dbm.get_db()
    zustand = dict(dbm.einstellung(_oberflaeche_schluessel(), con) or {})
    gruppen = {g.schluessel for g in nav.SEITENLEISTE if g.schluessel}
    if isinstance(daten.get("zu"), list):
        zustand["zu"] = [g for g in daten["zu"] if g in gruppen]
    if "schmal" in daten:
        zustand["schmal"] = bool(daten["schmal"])
    if daten.get("design") in ("hell", "dunkel", "auto"):
        zustand["design"] = daten["design"]
    with dbm.Transaktion(con):
        dbm.einstellungen_speichern({_oberflaeche_schluessel(): zustand}, con)
    return jsonify({"ok": True})


@bp.route("/benachrichtigungen/gelesen", methods=["POST"])
def benachrichtigungen_gelesen():
    con = dbm.get_db()
    bid = request.form.get("id", type=int)
    with dbm.Transaktion(con):
        if bid:
            con.execute("UPDATE benachrichtigungen SET gelesen_am=? WHERE id=? AND gelesen_am IS NULL",
                        (dbm.jetzt_berlin(), bid))
        else:
            con.execute("UPDATE benachrichtigungen SET gelesen_am=? WHERE gelesen_am IS NULL", (dbm.jetzt_berlin(),))
            from .fixkosten import hinweis_gelesen
            hinweis_gelesen(con)  # auch Fixkosten-Hinweise (Vertragsende, Kündigungsfrist)
    if request.headers.get("X-Requested-With") == "fetch":
        return jsonify({"ok": True})
    return _zurueck(url_for("main.benachrichtigungen"))


@bp.route("/benachrichtigungen/<int:bid>/oeffnen")
def benachrichtigung_oeffnen(bid):
    con = dbm.get_db()
    b = con.execute("SELECT * FROM benachrichtigungen WHERE id=?", (bid,)).fetchone() or abort(404)
    with dbm.Transaktion(con):
        con.execute("UPDATE benachrichtigungen SET gelesen_am=COALESCE(gelesen_am, ?) WHERE id=?",
                    (dbm.jetzt_berlin(), bid))
    return redirect(url_for("main.auftrag", aid=b["auftrag_id"]) + "#benachrichtigung")


def _seiten_ziele():
    """Seiten, Reiter, Schnellaktionen und Verwaltungsseiten für die Schnellsuche."""
    ziele = []
    for gruppe, e in nav.alle_eintraege():
        ziele.append({"titel": e.titel, "unter": gruppe.titel if gruppe else "", "url": url_for(e.endpoint, **e.args),
                      "symbol": e.symbol, "stichworte": e.stichworte})
    for haupt, reiter in nav.REITER.items():
        _, e = nav.eintrag(haupt)
        for titel, ep_ in reiter[1:]:
            ziele.append({"titel": titel, "unter": e.titel, "url": url_for(ep_), "symbol": e.symbol, "stichworte": ""})
    ziele.append({"titel": "Benachrichtigungen", "unter": "Werkstatt", "url": url_for("main.benachrichtigungen"),
                  "symbol": "bell", "stichworte": "Kundenbenachrichtigung E-Mail SMS Abholung Erinnerung"})
    for ep_, titel, sym, stichworte in nav.VERWALTUNG:
        ziele.append({"titel": titel, "unter": "Einstellungen", "url": url_for(ep_), "symbol": sym,
                      "stichworte": stichworte})
    return ziele


def _rang(q, titel):
    """Reihenfolge: genauer Treffer, Anfang des Titels, im Titel, nur in Stichworten."""
    from .einstellungs_suche import normal
    q, t = normal(q), normal(titel)
    return 0 if t == q else 1 if t.startswith(q) else 2 if q in t else 3


@bp.route("/suche.json")
def schnellsuche():
    """Strg+K: Seiten, Einstellungen, Kunden, Aufträge, Rechnungen/KVA, Artikel und Leihgeräte."""
    from .einstellungs_suche import normal, passt
    q = request.args.get("q", "").strip()
    gruppen = []
    aktionen = [{"titel": t, "url": url_for(ep_, **args), "symbol": sym} for t, ep_, args, sym in nav.NEU]
    if not q:
        return jsonify([{"art": "Schnellaktionen", "eintraege": aktionen},
                        {"art": "Seiten", "eintraege": [z for z in _seiten_ziele() if not z["unter"] == "Einstellungen"
                                                        ][:9]}])
    treffer = [a for a in aktionen if passt(q, a, "titel") or normal(q) in ("neu", "neue", "neuer")]
    if treffer:
        gruppen.append({"art": "Schnellaktionen", "eintraege": treffer})
    seiten = sorted((z for z in _seiten_ziele() if passt(q, z, "titel", "unter", "stichworte")),
                    key=lambda z: _rang(q, z["titel"]))
    if seiten:
        gruppen.append({"art": "Seiten", "eintraege": seiten[:8]})
    einst = sorted(einstellungen_treffer(q, 30), key=lambda t: _rang(q, t["titel"]))[:6]
    if einst:
        gruppen.append({"art": "Einstellungen", "eintraege": [
            {"titel": t["titel"], "unter": " › ".join(x for x in (t["bereich_titel"], t["abschnitt"]) if x and
                                                       x != t["titel"]),
             "url": url_for("main.einstellungen", bereich=t["bereich"]) + (f"#{t['anker']}" if t["anker"] else ""),
             "symbol": "settings"} for t in einst]})
    con = dbm.get_db()
    muster = f"%{q}%"
    ziffern = re.sub(r"\D", "", q)
    tel = f"%{ziffern}%" if len(ziffern) >= 4 else "\x00"
    daten = [
        ("Kunden", "users", con.execute(
            "SELECT * FROM kunden WHERE anonymisiert_am IS NULL AND (kundennr LIKE :m OR firma LIKE :m OR "
            "vorname LIKE :m OR nachname LIKE :m OR (vorname || ' ' || nachname) LIKE :m OR email LIKE :m OR "
            "replace(replace(replace(replace(COALESCE(telefon,''),' ',''),'/',''),'-',''),'+49','0') LIKE :t) "
            "ORDER BY archiviert, geaendert_am DESC LIMIT 6", {"m": muster, "t": tel}).fetchall(),
         lambda k: (kunde_name(k), " · ".join(x for x in (k["kundennr"], k["email"], k["telefon"]) if x),
                    url_for("main.kunde", kid=k["id"]))),
        ("Aufträge", "wrench", con.execute(
            "SELECT a.*, k.firma, k.vorname, k.nachname, k.typ AS ktyp FROM auftraege a JOIN kunden k "
            "ON k.id=a.kunde_id WHERE a.auftragsnr LIKE :m OR a.geraet LIKE :m OR a.seriennummer LIKE :m "
            "ORDER BY a.eingang_am DESC LIMIT 6", {"m": muster}).fetchall(),
         lambda a: (f"{a['auftragsnr']} · {a['geraet'] or ''}", " · ".join(
             x for x in (_kname(a), a["seriennummer"], auf.STATUS.get(a["status"], a["status"])) if x),
                    url_for("main.auftrag", aid=a["id"]))),
        ("Rechnungen & KVA", "receipt", con.execute(
            "SELECT d.*, k.firma, k.vorname, k.nachname, k.typ AS ktyp FROM dokumente d LEFT JOIN kunden k "
            "ON k.id=d.kunde_id WHERE d.nummer LIKE :m OR d.betreff LIKE :m ORDER BY d.datum DESC, d.id DESC LIMIT 6",
            {"m": muster}).fetchall(),
         lambda d: (f"{d['nummer'] or 'Entwurf'} · {d['betreff'] or ''}",
                    " · ".join(x for x in ({"rechnung": "Rechnung", "kva": "KVA", "storno": "Storno",
                                            "gutschrift": "Gutschrift"}.get(d["typ"], d["typ"]),
                                           kunde_name({**dict(d), "typ": d["ktyp"]}) if d["kunde_id"] else "",
                                           euro(d["summe_brutto"])) if x),
                    url_for("main.dokument", did=d["id"]))),
        ("Leistungen & Artikel", "tag", con.execute(
            "SELECT * FROM artikel WHERE name LIKE :m OR artikelnr LIKE :m OR ean LIKE :m OR herstellernr LIKE :m "
            "ORDER BY aktiv DESC, name LIMIT 6", {"m": muster}).fetchall(),
         lambda a: (a["name"], " · ".join(x for x in (a["artikelnr"], euro(a["preis"])) if x),
                    url_for("main.artikel", aid=a["id"]))),
        ("Fixkosten", "calendar-clock", con.execute(
            "SELECT * FROM fixkosten WHERE bezeichnung LIKE :m OR kategorie LIKE :m OR empfaenger LIKE :m "
            "ORDER BY bezeichnung LIMIT 6", {"m": muster}).fetchall(),
         lambda f: (f["bezeichnung"], " · ".join(x for x in (f["kategorie"], f["empfaenger"]) if x),
                    url_for("main.fixkosten", fid=f["id"]))),
        ("Leihgeräte", "laptop", con.execute(
            "SELECT * FROM leihgeraete WHERE bezeichnung LIKE :m OR inventarnr LIKE :m OR seriennummer LIKE :m "
            "ORDER BY bezeichnung LIMIT 6", {"m": muster}).fetchall(),
         lambda g: (g["bezeichnung"], " · ".join(x for x in (g["inventarnr"], g["seriennummer"]) if x),
                    url_for("main.leihgeraet", gid=g["id"]))),
    ]
    for art, sym, zeilen, form in daten:
        if zeilen:
            gruppen.append({"art": art, "eintraege": [dict(zip(("titel", "unter", "url"), form(z)), symbol=sym)
                                                      for z in zeilen]})
    return jsonify(gruppen)


# ====================================================================== Wiederherstellung aus einer Sicherung

@bp.route("/einstellungen/backup/wiederherstellen", methods=["POST"])
def wiederherstellen():
    from . import wiederherstellung as wh
    quelle = request.form.get("quelle", "")
    try:
        wh.vormerken(daten_dir(), quelle)
    except ValueError as e:
        raise EingabeFehler(str(e))
    con = dbm.get_db()
    with dbm.Transaktion(con):
        dbm.protokollieren("wiederherstellung_vorgemerkt", "system", None, {"quelle": quelle}, con=con)
    if not upd.ist_exe():
        flash("Wiederherstellung vorgemerkt. Bitte das Programm jetzt beenden und neu starten – vorher wird der "
              "aktuelle Stand vollständig gesichert.", "warnung")
        return redirect(url_for("main.einstellungen", bereich="backup"))
    dbm.festschreiben(current_app.config["DB_PFAD"])
    upd.neu_starten(verzoegerung=1.5)
    return render_template("wiederherstellung_laeuft.html", gestartet=current_app.config.get("GESTARTET"))


# ====================================================================== Fixkosten

from . import fixkosten as fxk  # noqa: E402
from .hilfen import heute_datum  # noqa: E402


def _fix_betrag_aus_formular():
    satz = zahl_aus_text(_f("steuersatz"), 0) if _f("steuersatz") else 0.0
    netto, brutto = cent_aus_text(_f("netto"), None), cent_aus_text(_f("brutto"), None)
    if netto is None and brutto is None:
        return None
    netto, _ = fxk.betrag_rechnen(netto=netto, steuersatz=satz) if netto is not None else \
        fxk.betrag_rechnen(brutto=brutto, steuersatz=satz)
    return netto, satz


@bp.route("/fixkosten")
def fixkosten_liste():
    con = dbm.get_db()
    heute_d = heute_datum()
    liste = fxk.alle(con)
    stand = fxk.zahlungsstand(con, liste, heute_d)
    for f in liste:
        f["aktuell"] = fxk.betrag_am(f, heute_d)
        f["naechste"] = fxk.naechste_faelligkeit(f, heute_d)
        f["aktiv"] = fxk.aktiv_am(f, heute_d) or fxk._d(f["beginn"]) > heute_d
        f["kuendigung_bis"] = fxk.kuendigung_bis(f)
        f["stand"] = [s for s in stand.get(f["id"], []) if s["status"] != "bezahlt"][-6:]
    return render_template("fixkosten.html", liste=liste, ue=fxk.uebersicht(con, heute_d, liste),
                           hinweise=fxk.hinweise(con, heute_d, liste), rhythmen=fxk.RHYTHMEN,
                           zahlungsarten=fxk.ZAHLUNGSARTEN, heute=heute_d)


@bp.route("/fixkosten/neu", methods=["GET", "POST"])
@bp.route("/fixkosten/<int:fid>", methods=["GET", "POST"])
def fixkosten(fid=None):
    con = dbm.get_db()
    einst = dbm.einstellungen(con)
    f = fxk.eine(con, fid) if fid else None
    if fid and not f:
        abort(404)
    if request.method == "POST":
        aktion = request.form.get("aktion", "speichern")
        with dbm.Transaktion(con):
            if aktion == "speichern":
                werte = {k: request.form.get(k, "") for k in fxk.FELDER}
                fid = fxk.speichern(con, werte, einst, fid, None if fid else _fix_betrag_aus_formular())
                datei = request.files.get("vertrag")
                if datei and datei.filename:
                    rel, sha = fxk.vertrag_ablegen(daten_dir(), datei.read(), datei.filename)
                    con.execute("UPDATE fixkosten SET datei=?, datei_name=?, datei_sha256=? WHERE id=?",
                                (rel, datei.filename, sha, fid))
                    dbm.ereignis_erfassen(con, "fixkosten", fid, "Vertrag hochgeladen", datei.filename)
                meldung = "Fixkosten gespeichert."
            elif aktion == "betrag":
                b = _fix_betrag_aus_formular()
                if not b:
                    raise EingabeFehler("Bitte den neuen Betrag angeben.")
                fxk.betrag_neu(con, fid, _f("gueltig_ab"), *b, notiz=_f("notiz_betrag"))
                meldung = f"Neuer Betrag ab {datum_de(_f('gueltig_ab'))} gespeichert – frühere Zeiträume bleiben unverändert."
            elif aktion == "betrag_entfernen":
                fxk.betrag_entfernen(con, request.form.get("betrag_id", type=int))
                meldung = "Geplanten Betrag entfernt."
            elif aktion == "loeschen":
                fxk.loeschen(con, fid)
                flash("Fixkosten-Position gelöscht.", "ok")
                return redirect(url_for("main.fixkosten_liste"))
            else:
                abort(400)
        flash(meldung, "ok")
        return redirect(url_for("main.fixkosten", fid=fid))
    stand = fxk.zahlungsstand(con, [f], heute_datum()).get(fid, []) if f else []
    zahlungen = con.execute("SELECT * FROM bank_umsaetze WHERE fixkosten_id=? ORDER BY buchungstag DESC",
                            (fid,)).fetchall() if fid else []
    rechnungen = con.execute(ek.ER_SQL + "WHERE e.fixkosten_id=? ORDER BY e.datum DESC", (fid,)).fetchall() if fid else []
    return render_template("fixkosten_form.html", f=f, kategorien=fxk.kategorien(einst), rhythmen=fxk.RHYTHMEN,
                           zahlungsarten=fxk.ZAHLUNGSARTEN, einheiten=fxk.EINHEITEN, lieferanten=ek.lieferanten(con),
                           stand=list(reversed(stand))[:24], zahlungen=zahlungen, rechnungen=rechnungen,
                           heute=heute_datum().isoformat(), aktuell=fxk.betrag_am(f, heute_datum()) if f else None,
                           kuendigung_bis=fxk.kuendigung_bis(f) if f else None,
                           aenderungen=dbm.aenderungen_liste(con, "fixkosten", fid) if fid else [],
                           standard_satz=einst.get("regel_steuersatz") or 19)


@bp.route("/fixkosten/<int:fid>/vertrag")
def fixkosten_vertrag(fid):
    f = dbm.get_db().execute("SELECT * FROM fixkosten WHERE id=?", (fid,)).fetchone()
    if not f or not f["datei"]:
        abort(404)
    pfad = Path(daten_dir()) / f["datei"]
    if not pfad.is_file():
        abort(404)
    endung = f["datei"].rsplit(".", 1)[-1].lower()
    return send_file(pfad, mimetype={"pdf": "application/pdf", "png": "image/png"}.get(endung, "image/jpeg"),
                     download_name=f["datei_name"] or f"Vertrag.{endung}")


@bp.route("/fixkosten/hinweis")
def fixkosten_hinweis():
    """Hinweis aus der Glocke öffnen: als gelesen markieren und zur Position springen."""
    con = dbm.get_db()
    s = request.args.get("s", "")
    if s.startswith("fixkosten:"):
        with dbm.Transaktion(con):
            fxk.hinweis_gelesen(con, s)
    return redirect(url_for("main.fixkosten", fid=request.args.get("fid", type=int)) if request.args.get("fid")
                    else url_for("main.fixkosten_liste"))


@bp.route("/fixkosten/hinweis-gelesen", methods=["POST"])
def fixkosten_hinweis_gelesen():
    con = dbm.get_db()
    with dbm.Transaktion(con):
        fxk.hinweis_gelesen(con, request.form.get("schluessel") or None)
    if request.headers.get("X-Requested-With") == "fetch":
        return jsonify({"ok": True})
    return _zurueck(url_for("main.fixkosten_liste"))


@bp.route("/bank/<int:uid>/fixkosten", methods=["POST"])
def bank_fixkosten(uid):
    con = dbm.get_db()
    with dbm.Transaktion(con):
        if request.form.get("loesen"):
            fxk.bank_loesen(con, uid)
            flash("Zuordnung gelöst – der Umsatz ist wieder offen.", "ok")
        else:
            fxk.bank_zuordnen(con, uid, request.form.get("fixkosten_id", type=int))
            flash("Abbuchung der Fixkosten-Position zugeordnet.", "ok")
    return redirect(url_for("main.bank", ansicht=request.form.get("ansicht", "offen")))


@bp.route("/eingangsrechnungen/<int:eid>/fixkosten", methods=["POST"])
def eingangsrechnung_fixkosten(eid):
    con = dbm.get_db()
    fid = request.form.get("fixkosten_id", type=int)
    with dbm.Transaktion(con):
        con.execute("UPDATE eingangsrechnungen SET fixkosten_id=? WHERE id=?", (fid, eid))
        dbm.ereignis_erfassen(con, "eingangsrechnung", eid, "Fixkosten-Zuordnung",
                              (fxk.eine(con, fid) or {}).get("bezeichnung", "") if fid else "aufgehoben")
    flash("Zuordnung gespeichert. In der Finanzübersicht zählt die Rechnung jetzt bei den Fixkosten." if fid
          else "Zuordnung aufgehoben.", "ok")
    return redirect(url_for("main.eingangsrechnung", eid=eid))


# ====================================================================== Finanzübersicht

from . import finanzen as fin  # noqa: E402


def _fin_parameter():
    a = request.args
    art = a.get("art") if a.get("art") in fin.ARTEN else "monat"
    return dict(art=art, jahr=a.get("jahr", type=int), nr=a.get("nr", type=int), von=a.get("von"), bis=a.get("bis"),
                basis="zahlung" if a.get("basis") == "zahlung" else "rechnung",
                fix_modus="faellig" if a.get("fix") == "faellig" else "anteilig")


@bp.route("/finanzen")
def finanzen():
    con = dbm.get_db()
    p = _fin_parameter()
    vgl = "vorperiode" if request.args.get("vergleich") == "vorperiode" else "vorjahr"
    a = fin.auswertung(con, **p, vergleich_mit=vgl)
    if request.args.get("export") == "csv":
        return send_file(io.BytesIO(fin.csv_export(a)), mimetype="text/csv", as_attachment=True,
                         download_name=f"Finanzuebersicht_{a['von']}_{a['bis']}.csv")
    if request.args.get("export") == "pdf":
        return send_file(io.BytesIO(fin.pdf_export(a, dbm.einstellung("firma_name") or "")),
                         mimetype="application/pdf", download_name=f"Finanzuebersicht_{a['von']}_{a['bis']}.pdf")
    jahr, nr = a["von"].year, None
    if p["art"] in ("monat", "quartal", "halbjahr"):
        nr = {"monat": a["von"].month, "quartal": (a["von"].month - 1) // 3 + 1,
              "halbjahr": (a["von"].month - 1) // 6 + 1}[p["art"]]
    basis_args = {k: v for k, v in dict(basis=p["basis"], fix=p["fix_modus"], vergleich=vgl).items()}
    nav_ = {}
    if p["art"] != "frei":
        for name, s in (("zurueck", -1), ("vor", 1)):
            j, n = fin.blaettern(p["art"], jahr, nr or 1, s)
            nav_[name] = url_for("main.finanzen", art=p["art"], jahr=j, nr=n if p["art"] != "jahr" else None,
                                 **basis_args)
    return render_template("finanzen.html", a=a, p=p, jahr=jahr, nr=nr, blaettern=nav_, basis_args=basis_args,
                           schnell=[(t, {**x, **basis_args}) for t, x in fin.schnellauswahl()], vgl=vgl, balken=fin.svg_balken(a["monate"]),
                           linie=fin.svg_linie(a["monate"]), be=fin.break_even(con, ku=a["ku"]),
                           vorschau=fin.vorschau(con, ku=a["ku"]), arten=fin.ARTEN, monate_namen=fin.MONATE,
                           max_kat=max([w for _, w, _ in a["kategorien"]] + [1]))


@bp.route("/finanzen/belege")
def finanzen_belege():
    con = dbm.get_db()
    p = _fin_parameter()
    schluessel = request.args.get("s", "umsatz")
    titel, liste = fin.belege(con, schluessel, **p)
    ziele = {"dokument": lambda i: url_for("main.dokument", did=i),
             "eingangsrechnung": lambda i: url_for("main.eingangsrechnung", eid=i),
             "kasse": None,
             "fixkosten": lambda i: url_for("main.fixkosten", fid=i),
             "auftrag": lambda i: url_for("main.auftrag", aid=i)}
    for x in liste:
        art_, i = x["ziel"]
        x["url"] = (url_for("main.kassenbuch", von=x["datum"].isoformat(), bis=x["datum"].isoformat()) + f"#k{i}"
                    if art_ == "kasse" else ziele[art_](i))
    return render_template("finanzen_belege.html", liste=liste, titel=titel, schluessel=schluessel,
                           zurueck=url_for("main.finanzen", **{k: v for k, v in request.args.items() if k != "s"}),
                           summe=sum(x["wert"] for x in liste))
