"""Verfahrensdokumentation (Vorlage nach GoBD Rz. 151 ff.) – erzeugt aus den tatsächlichen Einstellungen.

Die Inhalte beschreiben, wie das Programm Belege erstellt, festschreibt, archiviert und sichert. Organisatorische
Angaben, die nur der Inhaber kennt, sind als „[bitte ergänzen]“ markiert.
"""
import io
from datetime import datetime

from . import db as dbm
from .hilfen import datum_de

ERGAENZEN = "[bitte ergänzen]"


def inhalt(con, daten_dir, version):
    """Liste von Abschnitten: (Überschrift, [Bausteine]); Baustein = str | ("liste", [...]) | ("tabelle", [[...]])."""
    e = dbm.einstellungen(con)
    kreise = con.execute("SELECT * FROM nummernkreise ORDER BY praefix, jahr").fetchall()
    anzahl = {r[0]: r[1] for r in con.execute(
        "SELECT typ, COUNT(*) FROM dokumente WHERE status<>'entwurf' GROUP BY typ")}
    steuer = ("Kleinunternehmer nach § 19 UStG – keine Umsatzsteuer, Hinweistext: „"
              f"{e.get('kleinunternehmer_hinweis')}“") if e.get("steuer_modus") == "kleinunternehmer" else \
        f"Regelbesteuerung, Standard-Steuersatz {e.get('regel_steuersatz')} %"
    return [
        ("1. Allgemeines", [
            f"Unternehmen: {e.get('firma_name') or ERGAENZEN}, Inhaber {e.get('inhaber') or ERGAENZEN}, "
            f"{e.get('strasse') or ERGAENZEN}, {e.get('plz') or ''} {e.get('ort') or ''}. "
            f"Steuernummer: {e.get('steuernummer') or ERGAENZEN}"
            + (f", USt-IdNr.: {e['ust_idnr']}" if e.get("ust_idnr") else "") + ".",
            "Tätigkeit: Reparatur von Smartphones, Computern, Kaffeemaschinen und ähnlichen Geräten, Verkauf von "
            "Zubehör, Verträge/Lizenzen (z. B. Wertgarantie, Virenschutz, IT-Betreuung). " + ERGAENZEN,
            f"Besteuerung: {steuer}.",
            f"Eingesetztes Programm: „Werkstatt-Sauter“ Version {version}, eigenentwickelt, läuft lokal auf einem "
            f"Windows-PC; Datenbank SQLite, Datenordner: {daten_dir}.",
            f"Bedient von: {ERGAENZEN} (Name, Rolle). Zugriffsschutz: "
            + ("Passwortschutz eingeschaltet." if e.get("login_aktiv") else
               "kein Programm-Passwort; das Programm ist nur am eigenen PC erreichbar, Schutz über die "
               "Windows-Anmeldung. " + ERGAENZEN),
        ]),
        ("2. Belegarten und Nummernkreise", [
            "Das Programm erstellt Kostenvoranschläge, Rechnungen, Stornorechnungen und Gutschriften. Jede "
            "Belegart hat einen Nummernkreis; Stornorechnungen verwenden den Nummernkreis der Rechnungen.",
            ("tabelle", [["Nummernkreis", "Jahr", "Format", "letzte Nummer"]]
             + ([[k["praefix"], str(k["jahr"]), k["format"], str(k["letzte_nummer"])] for k in kreise]
                or [["noch keine Nummer vergeben", "", e.get("nummern_format") or "", ""]])),
            f"Festgeschriebene Belege bisher: Rechnungen {anzahl.get('rechnung', 0)}, Stornorechnungen "
            f"{anzahl.get('storno', 0)}, Gutschriften {anzahl.get('gutschrift', 0)}, Kostenvoranschläge "
            f"{anzahl.get('kva', 0)} (Stand {datetime.now():%d.%m.%Y}).",
        ]),
        ("3. Belegfluss: Erstellen, Festschreiben, Versenden", [
            ("liste", [
                "Entwurf: Ein Beleg wird als Entwurf angelegt (ohne Nummer) und kann frei bearbeitet oder gelöscht "
                "werden. Entwürfe erscheinen nur mit dem Wasserzeichen „ENTWURF“ und können nicht per E-Mail "
                "versendet werden.",
                "Pflichtangaben-Prüfung: Vor dem Festschreiben prüft das Programm die Angaben nach § 14 Abs. 4 UStG "
                "(Name/Anschrift beider Seiten, Steuernummer oder USt-IdNr., Datum, Leistungsdatum, Menge/Bezeichnung, "
                "Beträge, Steuersatz bzw. Kleinunternehmer-Hinweis). Fehlt etwas, wird nicht festgeschrieben.",
                "Festschreiben: Erst jetzt wird die nächste fortlaufende Nummer vergeben – in derselben "
                "Datenbank-Transaktion, in der das PDF erzeugt und archiviert wird. Schlägt ein Schritt fehl, wird "
                "keine Nummer verbraucht (lückenlose Nummernfolge). Das Belegdatum darf nicht vor dem des letzten "
                "Belegs desselben Nummernkreises liegen.",
                "Versand: per E-Mail aus dem Programm (Versandprotokoll mit Prüfsumme des Anhangs) oder Druck des "
                "archivierten PDFs.",
                "Korrekturen: Festgeschriebene Belege können nicht geändert oder gelöscht werden. Korrektur nur durch "
                "Stornorechnung (eigene Nummer, Bezug auf das Original, negative Beträge) und neue Rechnung bzw. "
                "durch Gutschrift mit eigenem Nummernkreis.",
            ]),
        ]),
        ("4. Unveränderbarkeit und Archivierung", [
            ("liste", [
                "Beim Festschreiben werden das PDF und sämtliche Rechnungsdaten (als JSON) im Ordner "
                "„Daten\\dokumente\\<Jahr>\\“ abgelegt, jeweils mit SHA-256-Prüfsumme in der Datenbank.",
                "Beim späteren Öffnen wird immer dieses archivierte Original angezeigt (kein Neuerzeugen) und die "
                "Prüfsumme kontrolliert; bei Abweichung wird nicht angezeigt, sondern ein Hinweis ausgegeben.",
                "Datenbank-Trigger verhindern Änderungen an festgeschriebenen Belegen und ihren Positionen, das "
                "Löschen festgeschriebener Belege, das Zurücksetzen von Nummernkreisen sowie das Ändern/Löschen von "
                "Protokollen – auch bei Zugriff an der Programmoberfläche vorbei.",
                "Änderungsprotokoll: Änderungen an Belegentwürfen, Kostenvoranschlägen, Kunden und Artikeln werden "
                "feldgenau gespeichert (Zeitpunkt in deutscher Zeit mit Sekunden, Benutzer, Feld, alter und neuer "
                "Wert). Dieses Protokoll ist nicht änderbar.",
                "Ereignisprotokoll: Alle wesentlichen Vorgänge (Festschreiben, Storno, Versand, Einstellungen, "
                "Datensicherung) werden in einem Protokoll mit Hash-Verkettung gespeichert; eine nachträgliche "
                "Änderung würde die Kette brechen. Prüfung unter „Datenprüfung“.",
                "Datenprüfung: prüft Prüfsummen aller Archiv-PDFs und -Daten, die Lückenlosigkeit der Nummern und die "
                "Protokollkette.",
            ]),
        ]),
        ("5. Zahlungen, offene Posten und Mahnwesen", [
            ("liste", [
                "Zahlungseingänge werden je Rechnung mit Datum, Betrag, Zahlungsart und Notiz erfasst (auch "
                "Teilzahlungen). Zahlungen sind nicht löschbar; Korrekturen nur durch Stornierung mit Begründung.",
                "Bankabgleich: Kontoauszüge (CSV oder CAMT.053) werden eingelesen, doppelte Umsätze automatisch "
                "erkannt. Das Programm schlägt Zuordnungen vor (Rechnungsnummer im Verwendungszweck, Betrag, Name); "
                "jede Zuordnung bestätigt der Inhaber. Importierte Umsätze sind unveränderbar.",
                "Mahnwesen: Zahlungserinnerung, 1. und 2. Mahnung mit eigenem Nummernkreis; jedes Schreiben wird wie "
                "eine Rechnung als PDF und Daten mit Prüfsumme archiviert und ist nicht änderbar.",
            ]),
        ]),
        ("6. Aufbewahrung und Löschung", [
            f"Aufbewahrungsfristen: Rechnungen/Buchungsbelege {e.get('aufbewahrung_belege_jahre')} Jahre, Handels- "
            f"und Geschäftsbriefe (z. B. Kostenvoranschläge, Leihverträge, versandte Belege) "
            f"{e.get('aufbewahrung_briefe_jahre')} Jahre; Fristbeginn mit Ende des Kalenderjahres.",
            "Wird ein Kunde gelöscht, prüft das Programm die Fristen: Gibt es aufbewahrungspflichtige Unterlagen, "
            "werden nur die Stammdaten anonymisiert; Name und Anschrift bleiben unverändert in den archivierten "
            "Belegen. Nicht aufbewahrungspflichtige Daten (z. B. Anfragen, Entwürfe) werden gelöscht. Der Vorgang "
            "wird ohne personenbezogene Daten protokolliert.",
            "Eingehende Belege in Papierform: " + ERGAENZEN + " (Ablage, ggf. Scan-Verfahren).",
        ]),
        ("7. Datensicherung", [
            ("liste", [
                "Automatische Sicherung: " + ("eingeschaltet, täglich beim Start" if e.get("backup_auto")
                                              else "ausgeschaltet – bitte einschalten") + "; ZIP-Archiv mit Datenbank, "
                "Belegen, Fotos.",
                f"Zusätzliche Kopie nach: {e.get('backup_ziel') or ERGAENZEN + ' (z. B. NAS)'}; aufbewahrt werden die "
                f"letzten {e.get('backup_behalten')} Sicherungen.",
                "Vor jeder Datenbank-Erweiterung (Programm-Update) legt das Programm automatisch eine Sicherung an.",
                "Wiederherstellung: Programm beenden, Sicherung in den Ordner „Daten“ entpacken, Programm starten, "
                "Datenprüfung ausführen. Zuletzt getestet am: " + ERGAENZEN,
                "Updates werden aus dem offiziellen Projekt geladen, mit Prüfsumme kontrolliert; alle Versionen sind "
                "im Versionsprotokoll beschrieben.",
            ]),
        ]),
        ("8. Internes Kontrollsystem", [
            ("liste", [
                "Monatlich „Datenprüfung“ ausführen und Ergebnis kontrollieren. " + ERGAENZEN,
                "Sicherungen regelmäßig auf Vollständigkeit prüfen. " + ERGAENZEN,
                "Wöchentlich Kontoauszug einlesen und Zahlungen zuordnen, Mahnvorschläge prüfen. " + ERGAENZEN,
            ]),
            f"Stand dieser Dokumentation: {datum_de(datetime.now().date().isoformat())}, erzeugt vom Programm. Bitte "
            "ausdrucken, ergänzen, unterschreiben und bei jeder wesentlichen Änderung neu erzeugen.",
        ]),
    ]


def markiert(text):
    """HTML: Text sicher maskieren und „[bitte ergänzen]“ hervorheben."""
    from markupsafe import Markup, escape
    return Markup(str(escape(text)).replace(ERGAENZEN, f"<mark>{ERGAENZEN}</mark>"))


def pdf(abschnitte, firma="", titel="Verfahrensdokumentation – Rechnungsstellung und Belegarchivierung"):
    from xml.sax.saxutils import escape

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import ListFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    from .pdf import _schrift_registrieren
    f_norm, f_fett, _ = _schrift_registrieren("Montserrat")
    st = ParagraphStyle("n", fontName=f_norm, fontSize=9.5, leading=13.5, spaceAfter=4)
    st_h = ParagraphStyle("h", fontName=f_fett, fontSize=12, leading=16, spaceBefore=10, spaceAfter=4,
                          textColor=colors.HexColor("#1C54A3"), keepWithNext=1)
    st_t = ParagraphStyle("t", fontName=f_fett, fontSize=17, leading=22, textColor=colors.HexColor("#1C54A3"))
    puffer = io.BytesIO()
    doc = SimpleDocTemplate(puffer, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=18 * mm,
                            bottomMargin=18 * mm, title=titel.split(" – ")[0], author=firma)
    teile = [Paragraph(escape(titel), st_t),
             Paragraph(escape(firma), st), Spacer(1, 4 * mm)]
    for titel, bausteine in abschnitte:
        teile.append(Paragraph(escape(titel), st_h))
        for b in bausteine:
            if isinstance(b, tuple) and b[0] == "liste":
                teile.append(ListFlowable([Paragraph(escape(x), st) for x in b[1]], bulletType="bullet", leftIndent=12))
            elif isinstance(b, tuple) and b[0] == "tabelle":
                t = Table([[Paragraph(escape(z), st) for z in zeile] for zeile in b[1]], repeatRows=1)
                t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.3, colors.HexColor("#D5D9DE")),
                                       ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8EFF9"))]))
                teile.append(t)
            else:
                teile.append(Paragraph(escape(b), st))
    teile += [Spacer(1, 14 * mm), Paragraph("Ort, Datum, Unterschrift: ______________________________", st)]
    doc.build(teile)
    return puffer.getvalue()
