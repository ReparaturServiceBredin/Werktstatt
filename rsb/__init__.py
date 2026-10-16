"""Werkstatt Sauter – Aufträge, Rechnungen & Buchhaltung."""
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from flask import abort, Flask, flash, redirect, request, session, url_for

from . import db as dbm
from . import navigation
from .hilfen import EingabeFehler, datum_de, euro, kunde_name, menge_text, zeit_de
from .sicherheit import csrf_pruefen, csrf_token, sitzungs_schluessel

VERSION_NUMMER = "1.1.0"
VERSION = VERSION_NUMMER
if getattr(sys, "frozen", False):
    # EXE-Version: Programmordner = Ordner der EXE (die Daten liegen am festen Ort, siehe datenort.py)
    PROJEKT = Path(sys.executable).resolve().parent
else:
    PROJEKT = Path(__file__).resolve().parent.parent


def create_app(daten_dir=None, testing=False):
    from .datenort import ermitteln
    daten = Path(daten_dir).resolve() if daten_dir else ermitteln()  # fester Ort, unabhängig vom Startordner
    for unterordner in ("dokumente", "belege", "bilder", "backups", "geheim", "fotos"):
        (daten / unterordner).mkdir(parents=True, exist_ok=True)

    app = Flask(__name__)
    app.config.update(
        DATEN=str(daten),
        DB_PFAD=str(daten / "werkstatt.db"),
        SECRET_KEY=sitzungs_schluessel(daten),
        PERMANENT_SESSION_LIFETIME=timedelta(hours=10),
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_HTTPONLY=True,
        MAX_CONTENT_LENGTH=60 * 1024 * 1024,  # Fotos vom Handy können groß sein
        TESTING=testing,
    )
    from . import wiederherstellung
    bericht = wiederherstellung.ausfuehren(daten)  # vorgemerkte Wiederherstellung – bevor die Datenbank offen ist
    dbm.initialisieren(app.config["DB_PFAD"])
    app.config["GESTARTET"] = datetime.now().isoformat(timespec="seconds")
    if bericht:
        con = dbm.verbinden(app.config["DB_PFAD"])
        try:
            dbm.einstellungen_speichern({"wiederherstellung_bericht": bericht}, con)
            dbm.protokollieren("wiederherstellung", "system", None, bericht, con=con)
        finally:
            con.close()
    app.teardown_appcontext(dbm.schliessen)

    def tage_seit(iso):
        try:
            return (date.today() - datetime.fromisoformat(iso).date()).days
        except (TypeError, ValueError):
            return ""

    def zeit_sek(iso):
        """ISO-Zeitstempel -> 15.10.2026 14:03:27 (mit Sekunden)."""
        try:
            return datetime.fromisoformat(iso).strftime("%d.%m.%Y %H:%M:%S")
        except (TypeError, ValueError):
            return iso or ""

    app.jinja_env.filters.update(zeit_sek=zeit_sek, euro=euro, datum=datum_de, zeit=zeit_de, menge=menge_text, kunde_name=kunde_name,
                                 tage_seit=tage_seit)
    def zubehoer_teilen(text):
        from .annahme import zubehoer_aufteilen, zubehoer_vorlagen
        vorlagen = zubehoer_vorlagen(dbm.einstellungen())
        gewaehlt, rest = zubehoer_aufteilen(text, vorlagen)
        return {"vorlagen": vorlagen, "gewaehlt": gewaehlt, "rest": rest}

    from .annahme import ZUGANG_ARTEN
    def kva_gebuehren_liste():
        from .auftraege import kva_gebuehren
        return kva_gebuehren(dbm.einstellungen())

    def einst_garantie():
        from .garantie import standard_monate
        return standard_monate(dbm.einstellungen())

    from .kalender import text as termin_text
    app.jinja_env.globals.update(termin_text=termin_text, csrf_token=csrf_token, version=VERSION, zubehoer_teilen=zubehoer_teilen,
                                 einst_garantie=einst_garantie, kva_gebuehren_liste=kva_gebuehren_liste,
                                 zugang_arten=ZUGANG_ARTEN)

    from .views import bp
    app.register_blueprint(bp)

    offen = {"main.login", "main.einrichten", "main.version_info", "static"}

    mobil = {"main.mobil", "main.mobil_fotos", "main.mobil_foto_vorschau", "main.mobil_inventur"}  # Handy-Seiten (QR-Code mit Zugangs-Token)
    lokal = {"127.0.0.1", "::1", "::ffff:127.0.0.1"}

    @app.before_request
    def anmeldung_pruefen():
        if request.endpoint == "static":
            return None
        if request.endpoint in mobil:
            csrf_pruefen()  # Zugriff nur mit gültigem Token, das prüft die Seite selbst
            return None
        if (request.remote_addr or "127.0.0.1") not in lokal and not (
                dbm.einstellung("login_aktiv") and dbm.einstellung("passwort_hash")):
            # Aus dem WLAN ohne Passwortschutz: nur die QR-Code-Seiten
            abort(403, "Zugriff aus dem Netzwerk ist nur mit eingeschaltetem Passwortschutz möglich.")
        if request.endpoint in offen:
            return None
        if not dbm.einstellung("login_aktiv"):
            # Passwortschutz ausgeschaltet: direkt angemeldet (Programm ist nur am eigenen PC erreichbar)
            session["angemeldet"] = True
            session["benutzer"] = "inhaber"
            csrf_pruefen()
            return None
        if not dbm.einstellung("passwort_hash"):
            return redirect(url_for("main.einrichten"))
        if not session.get("angemeldet"):
            return redirect(url_for("main.login", weiter=request.path))
        csrf_pruefen()
        return None

    @app.context_processor
    def globale_werte():
        if request.endpoint in ("static",):
            return {}
        # Einstellungen immer echt laden: ein Fehler darf nie zu leeren Formularen führen (Speichern würde sonst
        # die echten Werte überschreiben). Nur die Zähler sind „weich“ – fällt einer aus, steht dort 0.
        einst = dbm.einstellungen()
        con = dbm.get_db()

        def zahl(sql, standard=0):
            try:
                return con.execute(sql).fetchone()[0]
            except Exception as e:  # z. B. Spalte fehlt – Seite trotzdem anzeigen
                print(f"Hinweis: Zähler nicht verfügbar ({e})")
                return standard

        offene_anfragen = zahl("SELECT COUNT(*) FROM anfragen WHERE status='neu' AND einstufung<>'spam'")
        leihen_ueberfaellig = zahl(
            "SELECT COUNT(*) FROM leihen WHERE rueckgabe_am IS NULL AND storniert_am IS NULL "
            "AND rueckgabe_geplant < date('now', 'localtime')")
        posten_ueberfaellig = zahl(
            "SELECT COUNT(*) FROM dokumente d WHERE typ='rechnung' AND status='festgeschrieben' "
            "AND faellig_am < date('now', 'localtime') AND summe_brutto + COALESCE((SELECT SUM(g.summe_brutto) "
            "FROM dokumente g WHERE g.bezug_id=d.id AND g.typ='gutschrift' AND g.status<>'entwurf'), 0) "
            "> bezahlt_betrag")
        try:
            from .lager import unter_mindestbestand_anzahl
            lager_unter_min = unter_mindestbestand_anzahl(con)
        except Exception as e:
            print(f"Hinweis: Zähler nicht verfügbar ({e})")
            lager_unter_min = 0
        benachrichtigungen_offen = zahl("SELECT COUNT(*) FROM benachrichtigungen WHERE status IN ('offen', 'fehler')")
        offene_auftraege = zahl("SELECT COUNT(*) FROM auftraege WHERE status<>'erledigt'")
        glocke_ungelesen = zahl(
            "SELECT COUNT(*) FROM benachrichtigungen WHERE gelesen_am IS NULL AND status IN ('offen', 'fehler')")
        try:
            glocke = con.execute(
                "SELECT b.*, a.auftragsnr, a.geraet FROM benachrichtigungen b JOIN auftraege a ON a.id=b.auftrag_id "
                "WHERE b.status<>'verworfen' ORDER BY (b.gelesen_am IS NULL AND b.status IN ('offen', 'fehler')) DESC, "
                "b.id DESC LIMIT 8").fetchall()
        except Exception as e:
            print(f"Hinweis: Benachrichtigungen nicht verfügbar ({e})")
            glocke = []
        try:
            from .fixkosten import hinweise as fix_hinweise
            fix_hinweise = fix_hinweise(con, nur_ungelesen=True)
        except Exception as e:
            print(f"Hinweis: Fixkosten-Hinweise nicht verfügbar ({e})")
            fix_hinweise = []
        glocke_ungelesen += len(fix_hinweise)
        ui = einst.get(f"oberflaeche:{session.get('benutzer') or 'inhaber'}") or {}
        if not isinstance(ui, dict):
            ui = {}
        from .update import ist_exe, ist_neuer
        update_da = einst.get("update_verfuegbar") if ist_neuer(einst.get("update_verfuegbar"), VERSION_NUMMER) \
            else None
        return {"einst": einst, "offene_anfragen": offene_anfragen, "leihen_ueberfaellig": leihen_ueberfaellig,
                "posten_ueberfaellig": posten_ueberfaellig, "benachrichtigungen_offen": benachrichtigungen_offen,
                "lager_unter_min": lager_unter_min, "offene_auftraege": offene_auftraege, "glocke": glocke,
                "glocke_ungelesen": glocke_ungelesen, "ui": ui, "nav": navigation, "fix_hinweise": fix_hinweise,
                "zaehler": {"offene_anfragen": offene_anfragen, "offene_auftraege": offene_auftraege,
                            "leihen_ueberfaellig": leihen_ueberfaellig, "posten_ueberfaellig": posten_ueberfaellig,
                            "lager_unter_min": lager_unter_min},
                "update_da": update_da, "ist_exe": ist_exe()}

    @app.errorhandler(EingabeFehler)
    def eingabefehler(e):
        flash(str(e), "fehler")
        return redirect(request.referrer or url_for("main.start"))

    return app
