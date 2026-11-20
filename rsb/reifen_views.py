"""Seiten von Reifen & Teile: Reifeneinlagerung, Saisonwechsel, Thekenverkauf (nur Variante „reifen“)."""
from flask import abort, flash, jsonify, redirect, render_template, request, send_file, url_for
import io

from . import db as dbm
from . import reifen as rf
from . import variante
from .hilfen import EingabeFehler, heute, kunde_name
from .views import _f, _kunden_liste, bp, daten_dir

ENDPOINTS = {"main.einlagerungen", "main.einlagerungen_archiv", "main.einlagerung", "main.einlagerung_auslagern",
             "main.einlagerung_tausch", "main.einlagerung_wieder", "main.einlagerung_pdf", "main.einlagerung_rechnung",
             "main.einlagerung_saison", "main.einlagerung_erinnern", "main.einlagerung_erinnern_alle",
             "main.theke", "main.theke_suche"}


@bp.before_app_request
def _nur_reifen():
    if request.endpoint in ENDPOINTS and not variante.hat("reifen"):
        abort(404)


# ====================================================================== Reifeneinlagerung

@bp.route("/einlagerung")
def einlagerungen():
    con = dbm.get_db()
    q, saison = request.args.get("q", "").strip(), request.args.get("saison", "")
    einst = dbm.einstellungen(con)
    zeilen = rf.liste(con, q, saison)
    return render_template("einlagerungen.html", zeilen=zeilen, q=q, saison=saison, archiv=False,
                           zahlen=rf.zahlen(con), warn={z["id"]: rf.warnungen(z, einst) for z in zeilen},
                           saisons=rf.SAISONS)


@bp.route("/einlagerung/ausgelagert")
def einlagerungen_archiv():
    con = dbm.get_db()
    q = request.args.get("q", "").strip()
    return render_template("einlagerungen.html", zeilen=rf.liste(con, q, archiv=True), q=q, saison="", archiv=True,
                           zahlen=rf.zahlen(con), warn={}, saisons=rf.SAISONS)


@bp.route("/einlagerung/neu", methods=["GET", "POST"])
@bp.route("/einlagerung/<int:eid>", methods=["GET", "POST"])
def einlagerung(eid=None):
    con = dbm.get_db()
    einst = dbm.einstellungen(con)
    e = rf.laden(con, eid) if eid else None
    if request.method == "POST":
        felder = rf.felder_aus_formular(request.form, einst)
        belegt = rf.platz_belegt(con, felder["lagerplatz"], eid)
        if belegt and belegt["kunde_id"] != felder["kunde_id"] and not request.form.get("platz_trotzdem"):
            raise EingabeFehler(f"Lagerplatz {felder['lagerplatz']} ist schon belegt ({belegt['nummer']}, "
                                f"{kunde_name(belegt)}). Bitte anderen Platz wählen oder „trotzdem“ ankreuzen.")
        with dbm.Transaktion(con):
            if e:
                if e["ausgelagert_am"]:
                    raise EingabeFehler("Ausgelagerte Sätze können nicht mehr geändert werden.")
                rf.aendern(con, eid, felder)
            else:
                eid = rf.anlegen(con, felder)
                if felder.get("vorgaenger_id"):
                    v = rf.laden(con, felder["vorgaenger_id"])
                    if not v["ausgelagert_am"]:
                        rf.auslagern(con, v["id"], felder["eingelagert_am"], "Saisontausch")
        e = rf.laden(con, eid)
        hinweise = rf.warnungen(e, einst)
        flash(f"Einlagerung {e['nummer']} gespeichert." + (" Hinweis: " + " · ".join(hinweise) if hinweise else ""),
              "warnung" if hinweise else "ok")
        return redirect(url_for("main.einlagerung", eid=eid, gespeichert=1))
    vorlage = {}
    if not e:
        a = request.args
        if a.get("auftrag_id", type=int):  # aus einem Auftrag: Kunde und Fahrzeug übernehmen
            au = con.execute("SELECT * FROM auftraege WHERE id=?", (a.get("auftrag_id", type=int),)).fetchone()
            if au:
                vorlage = {"kunde_id": au["kunde_id"], "auftrag_id": au["id"], "kennzeichen": au["kennzeichen"],
                           "fahrzeug": au["geraet"]}
        if a.get("tausch", type=int):  # Saisontausch: abgenommene Räder an den Platz des ausgelagerten Satzes
            v = con.execute("SELECT * FROM einlagerungen WHERE id=?", (a.get("tausch", type=int),)).fetchone()
            if v:
                vorlage = {"kunde_id": v["kunde_id"], "vorgaenger_id": v["id"], "kennzeichen": v["kennzeichen"],
                           "fahrzeug": v["fahrzeug"], "lagerplatz": v["lagerplatz"], "gebuehr": v["gebuehr"],
                           "saison": "sommer" if v["saison"] == "winter" else "winter",
                           "auftrag_id": a.get("auftrag_id", type=int)}
        if a.get("kunde_id", type=int):
            vorlage.setdefault("kunde_id", a.get("kunde_id", type=int))
        vorlage.setdefault("gebuehr", einst.get("einlagerung_gebuehr_cent"))
    kid = e["kunde_id"] if e else vorlage.get("kunde_id")
    kunde = con.execute("SELECT * FROM kunden WHERE id=?", (kid,)).fetchone() if kid else None
    kennzeichen_vorschlag = []
    if kunde:
        kennzeichen_vorschlag = [r[0] for r in con.execute(
            "SELECT DISTINCT kennzeichen FROM auftraege WHERE kunde_id=? AND kennzeichen<>'' UNION "
            "SELECT DISTINCT kennzeichen FROM einlagerungen WHERE kunde_id=? AND kennzeichen<>''", (kunde["id"], kunde["id"]))]
    plaetze = [z.strip().upper() for z in (einst.get("einlagerung_lagerplaetze") or "").splitlines() if z.strip()]
    belegt = {r[0] for r in con.execute("SELECT lagerplatz FROM einlagerungen WHERE ausgelagert_am IS NULL "
                                        "AND lagerplatz<>''")}
    nachfolger = con.execute("SELECT id, nummer FROM einlagerungen WHERE vorgaenger_id=?", (eid,)).fetchone() if eid else None
    return render_template("einlagerung.html", e=e, v=vorlage, kunde=kunde, kunden=_kunden_liste(con),
                           saisons=rf.SAISONS, arten=rf.ARTEN, felgen=rf.FELGEN, positionen=rf.POSITIONEN,
                           warnungen=rf.warnungen(e, einst) if e else [], kennzeichen=kennzeichen_vorschlag,
                           freie_plaetze=[p for p in plaetze if p not in belegt], nachfolger=nachfolger,
                           aenderungen=dbm.aenderungen_liste(con, "einlagerung", eid) if eid else [],
                           dot_alter=rf.dot_alter_jahre, heute=heute())


@bp.route("/einlagerung/<int:eid>/auslagern", methods=["POST"])
def einlagerung_auslagern(eid):
    con = dbm.get_db()
    with dbm.Transaktion(con):
        rf.auslagern(con, eid, _f("datum") or heute(), _f("notiz"))
    flash("Satz ausgelagert.", "ok")
    return redirect(url_for("main.einlagerung", eid=eid))


@bp.route("/einlagerung/<int:eid>/tausch", methods=["POST"])
def einlagerung_tausch(eid):
    """Saisonwechsel: diesen Satz auslagern und den abgenommenen Satz am selben Platz einlagern."""
    rf.laden(dbm.get_db(), eid)
    return redirect(url_for("main.einlagerung", tausch=eid))


@bp.route("/einlagerung/<int:eid>/wieder-einlagern", methods=["POST"])
def einlagerung_wieder(eid):
    con = dbm.get_db()
    with dbm.Transaktion(con):
        rf.wieder_einlagern(con, eid)
    flash("Satz ist wieder als eingelagert geführt.", "ok")
    return redirect(url_for("main.einlagerung", eid=eid))


@bp.route("/einlagerung/<int:eid>.pdf")
def einlagerung_pdf(eid):
    con = dbm.get_db()
    e = rf.laden(con, eid)
    nur = request.args.get("etiketten") == "1"
    daten = rf.pdf(con, eid, dbm.einstellungen(con), nur_etiketten=nur)
    name = f"{'Etiketten' if nur else 'Einlagerung'}_{e['nummer']}.pdf"
    return send_file(io.BytesIO(daten), mimetype="application/pdf", download_name=name, as_attachment=False)


@bp.route("/einlagerung/<int:eid>/rechnung", methods=["POST"])
def einlagerung_rechnung(eid):
    con = dbm.get_db()
    with dbm.Transaktion(con):
        did = rf.rechnung_entwurf(con, eid)
    flash("Rechnungsentwurf für die Einlagerung angelegt – bitte prüfen und festschreiben.", "ok")
    return redirect(url_for("main.dokument", did=did))


@bp.route("/einlagerung/saisonwechsel")
def einlagerung_saison():
    con = dbm.get_db()
    einst = dbm.einstellungen(con)
    saison = request.args.get("saison") or rf.saison_ziel(einst) or "winter"
    if saison not in ("sommer", "winter"):
        saison = "winter"
    zeilen = rf.saison_liste(con, saison)
    return render_template("einlagerung_saison.html", zeilen=zeilen, saison=saison, saisons=rf.SAISONS,
                           erinnert={z["id"]: rf.frisch_erinnert(z) for z in zeilen},
                           texte={z["id"]: rf.erinnerung_text(z, einst) for z in zeilen},
                           aktiv=rf.saison_ziel(einst), mail_bereit=bool(einst.get("smtp_host")))


@bp.route("/einlagerung/<int:eid>/erinnern", methods=["POST"])
def einlagerung_erinnern(eid):
    con = dbm.get_db()
    wie = _f("wie")
    if wie == "email":
        try:
            rf.erinnerung_senden(con, eid)
            flash("Erinnerung per E-Mail gesendet.", "ok")
        except Exception as e:  # MailFehler, EingabeFehler: Meldung zeigen, Liste bleibt
            flash(str(e), "fehler")
    else:
        with dbm.Transaktion(con):
            rf.erinnert(con, eid, {"telefon": "Telefon", "persoenlich": "persönlich", "brief": "Brief"}.get(wie, "Telefon"))
        flash("Als erinnert abgehakt.", "ok")
    return redirect(request.referrer or url_for("main.einlagerung_saison"))


@bp.route("/einlagerung/erinnern-alle", methods=["POST"])
def einlagerung_erinnern_alle():
    con = dbm.get_db()
    saison = _f("saison")
    gesendet, fehler = 0, []
    for z in rf.saison_liste(con, saison):
        if rf.frisch_erinnert(z) or not (z["email"] or "").strip():
            continue
        try:
            rf.erinnerung_senden(con, z["id"])
            gesendet += 1
        except Exception as e:
            fehler.append(f"{kunde_name(z)}: {e}")
            if len(fehler) >= 3 and not gesendet:  # E-Mail grundsätzlich nicht eingerichtet: abbrechen
                break
    if gesendet:
        flash(f"{gesendet} Erinnerung(en) per E-Mail gesendet.", "ok")
    if fehler:
        flash("Nicht gesendet: " + " · ".join(fehler[:5]), "fehler")
    if not gesendet and not fehler:
        flash("Keine offenen Erinnerungen mit E-Mail-Adresse.", "info")
    return redirect(url_for("main.einlagerung_saison", saison=saison))


# ====================================================================== Thekenverkauf

@bp.route("/theke", methods=["GET", "POST"])
def theke():
    con = dbm.get_db()
    if request.method == "POST":
        positionen = rf.theke_positionen(request.form)
        kid = request.form.get("kunde_id", type=int)
        did, nummer, hinweise = rf.theke_verkaufen(con, positionen, _f("zahlart"), daten_dir(), kid)
        for h in hinweise:
            flash(h, "warnung")
        flash(f"Verkauf gebucht: Rechnung {nummer}" + (" – Zahlung im Kassenbuch." if _f("zahlart") == "bar" else "."),
              "ok")
        return redirect(url_for("main.theke", fertig=did))
    fertig = None
    if request.args.get("fertig", type=int):
        fertig = con.execute("SELECT * FROM dokumente WHERE id=?", (request.args.get("fertig", type=int),)).fetchone()
    heute_verkauf = [dict(d, kunde_name=kunde_name({"typ": d["k_typ"], "firma": d["firma"], "vorname": d["vorname"],
                                                     "nachname": d["nachname"]})) for d in con.execute(
        "SELECT d.*, k.typ AS k_typ, k.firma, k.vorname, k.nachname, (SELECT GROUP_CONCAT(z.zahlart) FROM zahlungen z "
        "WHERE z.dokument_id=d.id AND z.storniert_am IS NULL) AS zahlarten FROM dokumente d "
        "LEFT JOIN kunden k ON k.id=d.kunde_id WHERE d.typ='rechnung' AND d.status<>'entwurf' AND d.datum=? "
        "AND d.betreff='Verkauf' ORDER BY d.id DESC", (heute(),)).fetchall()]
    return render_template("theke.html", kunden=_kunden_liste(con), fertig=fertig, heute_verkauf=heute_verkauf,
                           steuer_modus=dbm.einstellung("steuer_modus"))


@bp.route("/theke/suche.json")
def theke_suche():
    con = dbm.get_db()
    einst = dbm.einstellungen(con)
    erg = []
    for a in rf.artikel_suche(con, request.args.get("q", ""), limit=25):
        brutto = a["preis"] if einst["steuer_modus"] == "kleinunternehmer" else \
            int(round(a["preis"] * (1 + float(a["steuersatz"] or 0) / 100)))
        erg.append({"id": a["id"], "name": a["name"], "nr": a["artikelnr"] or a["herstellernr"] or "",
                    "groesse": a["reifen_groesse"] or "", "brutto": brutto, "bestand": a["bestand"],
                    "lager": bool(a["lagerfuehrend"]), "einheit": a["einheit"] or "Stk."})
    return jsonify(erg)
