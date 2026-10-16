"""Datenbankzugriff, Einstellungen und Änderungsprotokoll."""
import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path

from flask import current_app, g, has_request_context, session

SCHEMA = Path(__file__).with_name("schema.sql")

# Checklisten-Vorlagen je Leistung (Einstellungen → Annahme & Abholung)
CHECKLISTEN_STANDARD = """[Ölwechsel]
Ölsorte und Menge laut Herstellerfreigabe geprüft
Motoröl abgelassen
Ölfilter gewechselt
Ablassschraube mit neuem Dichtring nach Drehmoment angezogen
Neues Motoröl eingefüllt
Ölstand kontrolliert, Motor auf Dichtheit geprüft
Serviceintervall zurückgesetzt
Ölwechsel-Anhänger bzw. Serviceheft ausgefüllt

[Fehlerspeicher auslesen]
Diagnosegerät angeschlossen, Fahrzeug identifiziert
Fehlerspeicher aller Steuergeräte ausgelesen
Fehlercodes dokumentiert (Protokoll oder Foto)
Ergebnis mit dem Kunden besprochen bzw. KVA erstellt
Fehlerspeicher nach Behebung gelöscht
Kontrolle bzw. Probefahrt ohne neuen Fehler

[Reifenwechsel]
Fahrzeug angehoben, Räder abgenommen
Räder markiert (VL, VR, HL, HR)
Profiltiefe und Zustand der Reifen geprüft
Räder montiert, Radschrauben nach Drehmoment angezogen
Reifendruck eingestellt, RDKS geprüft
Abgenommene Räder beschriftet und eingelagert bzw. mitgegeben
Kunde auf Nachziehen der Radschrauben nach 50 km hingewiesen

[Reifenmontage]
Alte Reifen demontiert
Felgen geprüft und gereinigt
Ventile erneuert bzw. RDKS-Sensoren geprüft
Neue Reifen montiert (Laufrichtung beachtet)
Reifendruck eingestellt
Altreifen entsorgt bzw. dem Kunden mitgegeben

[Auswuchten]
Alte Auswuchtgewichte entfernt
Räder auf der Wuchtmaschine ausgewuchtet
Kontrolllauf ohne Unwucht

[Inspektion]
Inspektion nach Herstellervorgabe durchgeführt
Flüssigkeitsstände geprüft und ergänzt
Beleuchtung geprüft
Bremsen und Reifen geprüft
Serviceintervall zurückgesetzt, Serviceheft gestempelt

[Bremsen]
Bremsbeläge und -scheiben geprüft
Verschlissene Teile getauscht
Bremsflüssigkeit geprüft
Probefahrt mit Bremstest
"""

# Standardwerte für alle Einstellungen. Alles hier ist später in der Oberfläche änderbar.
STANDARD_EINSTELLUNGEN = {
    # Firma
    "firma_name": "Werkstatt Sauter",
    "firma_zusatz": "Kfz-Service",
    "inhaber": "",
    "strasse": "",
    "plz": "",
    "ort": "",
    "land": "Deutschland",
    "telefon": "",
    "email": "",
    "web": "",
    "steuernummer": "",
    "ust_idnr": "",
    "bank_name": "",
    "kontoinhaber": "",
    "iban": "",
    "bic": "",
    # Steuer
    "steuer_modus": "kleinunternehmer",  # oder "regel"
    "regel_steuersatz": 19,
    "kleinunternehmer_hinweis": "Gemäß § 19 UStG wird keine Umsatzsteuer berechnet (Kleinunternehmerregelung).",
    # Zahlung
    "zahlungsziel_privat": 14,
    "zahlungsziel_firma": 30,
    "zahlungsarten_text": "Zahlbar per Überweisung oder in bar bei Abholung.",
    "anzahlung_prozent": 50,
    "mahngebuehr_cent": 395,                # Gebühr 1. Mahnung (alt: für alle Mahnungen)
    "mahnstufen": 2,
    # Mahnwesen: Tage nach Fälligkeit bzw. nach Ablauf der vorigen Frist, Zahlungsfrist je Schreiben, Gebühren
    "mahn_erinnerung_tage": 7,              # Zahlungserinnerung … Tage nach Fälligkeit
    "mahn_stufe1_tage": 7,                  # 1. Mahnung … Tage nach Ablauf der Frist der Erinnerung
    "mahn_stufe2_tage": 7,                  # 2. Mahnung … Tage nach Ablauf der Frist der 1. Mahnung
    "mahn_frist_tage": 10,                  # neue Zahlungsfrist in jedem Schreiben
    "mahngebuehr_2_cent": 395,              # Gebühr 2. Mahnung (Zahlungserinnerung immer ohne Gebühr)
    "mahn_text_0": ("{anrede_brief}\n\nsicher haben Sie es im Alltag übersehen: Die Rechnung {rechnung_nummer} vom "
                    "{rechnung_datum} über {rechnung_betrag} war am {faellig_am} fällig. Offen sind noch "
                    "{offen_rechnung}.\n\nBitte überweisen Sie den Betrag bis zum {frist_bis}. Sollten Sie inzwischen "
                    "gezahlt haben, betrachten Sie dieses Schreiben bitte als gegenstandslos.\n\nMit freundlichen "
                    "Grüßen\n{inhaber}"),
    "mahn_text_1": ("{anrede_brief}\n\nauf unsere Zahlungserinnerung haben wir leider keinen Zahlungseingang "
                    "festgestellt. Bitte überweisen Sie den offenen Gesamtbetrag von {gesamt} bis spätestens "
                    "{frist_bis}.\n\nSollten Sie inzwischen gezahlt haben, betrachten Sie dieses Schreiben bitte als "
                    "gegenstandslos.\n\nMit freundlichen Grüßen\n{inhaber}"),
    "mahn_text_2": ("{anrede_brief}\n\ntrotz Erinnerung und Mahnung ist die Rechnung {rechnung_nummer} weiterhin "
                    "offen. Bitte überweisen Sie den Gesamtbetrag von {gesamt} bis spätestens {frist_bis}. Nach "
                    "Ablauf dieser Frist behalten wir uns weitere Schritte vor.\n\nMit freundlichen Grüßen\n{inhaber}"),
    "mahn_email_betreff": "{titel} zu Rechnung {rechnung_nummer} – {firma_name}",
    "mahn_email_text": ("{anrede_brief}\n\nanbei erhalten Sie unsere {titel} zur Rechnung {rechnung_nummer}. "
                        "Offen sind {gesamt}, bitte bis {frist_bis}.\n\nMit freundlichen Grüßen\n{inhaber}\n{firma_name}"),
    # Verzugszinsen (§ 288 BGB): Basiszinssatz + 5 (Verbraucher) bzw. 9 Prozentpunkte (Unternehmen)
    "zinsen_aktiv": False,
    "basiszinssatz": "",                    # in % – bitte aktuellen Wert der Bundesbank eintragen
    "zinsen_aufschlag_privat": 5,
    "zinsen_aufschlag_firma": 9,
    "zinsen_ab": "mahnung1",                # ab Datum der 1. Mahnung (vorsichtig) oder „faelligkeit“
    "kva_gueltig_tage": 30,
    # Verträge & Lizenzen
    "abo_modus": "automatisch",      # automatisch = festschreiben + per E-Mail senden / entwurf = nur Entwürfe anlegen
    "abo_letzter_lauf": "",
    "vertrag_erinnerung_tage": 60,   # so viele Tage vor Ablauf einer Lizenz/Garantie erinnern
    # Layout
    "farbe_primaer": "#1C54A3",
    "farbe_sekundaer": "#5D6670",
    "schrift": "Montserrat",
    "schriftgroesse": 9.5,
    "logo_datei": "",            # leer = mitgeliefertes Logo
    "logo_breite_mm": 62,
    "logo_position": "rechts",   # links / mitte / rechts
    "kopfzeile_text": "",
    "fusszeile_text": "",
    "faltmarken": True,
    "girocode": True,
    # Nummern
    "nummern_format": "{praefix}-{jahr}-{nummer:04d}",
    "praefix_rechnung": "RE",
    "praefix_angebot": "KV",
    "praefix_auftrag": "AB",
    "praefix_gutschrift": "GS",
    "praefix_mahnung": "MA",
    "praefix_kunde": "K",
    "leistungsarten": "Ölwechsel, Fehlerspeicher auslesen, Reifenwechsel, Reifenmontage, Auswuchten, Inspektion, Bremsen, Sonstiges",
    # Aufbewahrung (§ 147 AO / § 257 HGB): Frist beginnt mit Ende des Kalenderjahres des Belegs
    "aufbewahrung_belege_jahre": 8,         # Rechnungen, Stornos, Gutschriften, Buchungsbelege
    "aufbewahrung_briefe_jahre": 6,         # Handels- und Geschäftsbriefe (z. B. Kostenvoranschläge, versandte Mails)
    # Leihgeräte
    "leihbedingungen": (
        "1. Das Leihgerät bleibt Eigentum von {firma}. Es wird für die Dauer der Reparatur überlassen und ist "
        "spätestens am vereinbarten Rückgabetag zurückzugeben.\n"
        "2. Das Gerät ist vollständig (mit dem oben aufgeführten Zubehör), sauber und im gleichen Zustand wie bei der "
        "Ausgabe zurückzugeben. Normale Gebrauchsspuren sind kein Schaden.\n"
        "3. Der Entleiher haftet für Beschädigung, Verlust und Diebstahl ab Übergabe bis zur Rückgabe. Reparaturkosten "
        "bzw. fehlendes Zubehör werden in Rechnung gestellt, bei Verlust oder Totalschaden der Zeitwert. Eine erhaltene "
        "Kaution wird damit verrechnet.\n"
        "4. Wird das Gerät nach dem vereinbarten Rückgabetag zurückgegeben, wird für jeden weiteren Tag die vereinbarte "
        "Tagesgebühr berechnet; ist keine vereinbart, behalten wir uns eine angemessene Nutzungsentschädigung vor.\n"
        "5. Das Gerät darf nicht an Dritte weitergegeben, verändert oder geöffnet werden. Störungen sind uns sofort zu "
        "melden.\n"
        "6. Datenschutz: Bitte löschen Sie vor der Rückgabe alle eigenen Daten, Konten und Passwörter. Wir setzen das "
        "Gerät nach der Rückgabe zurück; für dann noch vorhandene Daten übernehmen wir keine Haftung."),
    # E-Mail
    "smtp_host": "",
    "smtp_port": 587,
    "smtp_sicherheit": "starttls",  # starttls / ssl / keine
    "smtp_benutzer": "",
    "smtp_passwort_enc": "",
    "absender_name": "Werkstatt Sauter",
    "absender_email": "",
    "bcc_an_mich": True,
    # Kopie gesendeter Mails per IMAP im Postfach ablegen
    "gesendet_aktiv": False,
    "gesendet_imap_host": "imap.ionos.de",
    "gesendet_imap_port": 993,
    "gesendet_imap_sicherheit": "ssl",      # ssl (Port 993) / starttls (Port 143)
    "gesendet_gleiche_zugangsdaten": True,
    "gesendet_imap_benutzer": "",
    "gesendet_imap_passwort_enc": "",
    "gesendet_ordner": "",
    # Backup
    "backup_auto": True,
    "backup_ziel": "",
    "backup_behalten": 30,
    "letztes_backup": "",
    # Anfragen aus dem Kontaktformular
    "anfragen_aktiv": False,
    "anfragen_intervall_min": 5,
    "imap_host": "imap.ionos.de",
    "imap_port": 993,
    "imap_sicherheit": "ssl",               # ssl (Port 993) / starttls (Port 143)
    # E-Mail-Historie bei Kunden (nutzt den IMAP-Zugang oben und das Abrufintervall der Anfragen)
    "historie_aktiv": False,
    "historie_ordner_eingang": "INBOX",      # eine Zeile je Ordner
    "historie_ordner_gesendet": "Gesendete Objekte",
    "historie_zeitraum_tage": 182,           # erster Import: 30 / 182 / 365 Tage, 0 = alles
    "historie_eigene_adressen": "",          # weitere eigene Adressen (werden beim Abgleich ignoriert)
    "imap_benutzer": "",
    "imap_passwort_enc": "",
    "imap_ordner": "INBOX",
    "imap_zielordner": "Anfragen erledigt",
    "imap_verschieben": True,
    "anfrage_erkennung": "A new form has been submitted",
    "anfrage_auto_kunde": True,
    "anfrage_schwelle_unsicher": 2,
    "anfrage_schwelle_spam": 5,
    "anfrage_namensreihenfolge": "auto",   # auto / vorname_nachname / nachname_vorname
    "interessent_loeschen_monate": 6,
    "anfragen_letzter_abruf": "",
    "anfragen_letzter_fehler": "",
    # Annahme-/Abholschein (Reparaturannahme)
    "annahme_zubehoer": "Fahrzeugschlüssel\nZweitschlüssel\nFahrzeugschein\nServiceheft\nFelgenschloss-Adapter\n"
                        "Sommerräder\nWinterräder\nRadkappen\nWarndreieck / Verbandskasten",
    "checklisten": CHECKLISTEN_STANDARD,
    # Werkstattkalender
    "kalender_von": 7,                      # erste Stunde im Kalender
    "kalender_bis": 18,                     # letzte Stunde (Ende)
    "kalender_samstag": True,
    "dauer_je_leistung": ("Ölwechsel = 45\nFehlerspeicher auslesen = 30\nReifenwechsel = 30\nReifenmontage = 60\n"
                          "Auswuchten = 30\nInspektion = 120\nBremsen = 90\nSonstiges = 60"),
    "annahme_kva_gebuehr_cent": 0,          # (bis 0.20) Vorschlag für neue Aufträge – ersetzt durch kva_gebuehren
    # KVA-Pauschale je Gerätetyp (brutto, „Gerätetyp = Betrag“ je Zeile); bei Annahme verrechnet, bei Ablehnung fällig
    "kva_gebuehren": "PKW = 29,00\nSUV / Van = 29,00\nTransporter = 39,00\nMotorrad = 19,00",
    "annahme_kva_text": (
        "Für die Erstellung eines Kostenvoranschlags berechnen wir pauschal {KVA-Gebühr}. Wird der "
        "Kostenvoranschlag angenommen, wird dieser Betrag vollständig verrechnet. Bei Ablehnung wird die Pauschale "
        "fällig. Das Fahrzeug wird – soweit technisch möglich – im fahrbereiten Zustand zurückgegeben."),
    # Freiwillige Garantie (Text auf Rechnung und Abholschein)
    "garantie_text": (
        "Auf die durchgeführten Arbeiten und die dabei verbauten Teile gewähren wir eine freiwillige Garantie "
        "von {Garantiedauer} ab Abholung (bis {Garantieende}). Sie umfasst ausschließlich die durchgeführte Arbeit "
        "bzw. das verbaute Teil. Ausgeschlossen sind Unfallschäden, unsachgemäße Nutzung, Eingriffe Dritter sowie "
        "normaler Verschleiß (z. B. Reifen- und Bremsenabnutzung). Zur Inanspruchnahme bitte das Fahrzeug mit "
        "Rechnung bei {Firmenname}, {Firmenanschrift} vorstellen. Ihre gesetzlichen "
        "Gewährleistungsrechte bleiben von dieser Garantie unberührt und bestehen unabhängig davon."),
    "annahme_datenschutz": (
        "Bitte entnehmen Sie Wertsachen aus dem Fahrzeug – für im Fahrzeug zurückgelassene Gegenstände übernehmen "
        "wir keine Haftung. Zum Auslesen des Fehlerspeichers verbinden wir ein Diagnosegerät mit dem Fahrzeug; "
        "dabei werden nur fahrzeugtechnische Daten gelesen, soweit für den Auftrag erforderlich. Probefahrten "
        "erfolgen nur, soweit sie für den Auftrag nötig sind. Ihre Kontaktdaten verarbeiten wir zur Durchführung "
        "des Auftrags (Art. 6 Abs. 1 lit. b DSGVO)."),
    "annahme_abholbedingungen": (
        "Wir informieren Sie, sobald Ihr Fahrzeug abholbereit ist. Bitte holen Sie es innerhalb von 3 Werktagen nach "
        "dieser Mitteilung ab. Danach können wir eine angemessene Standgebühr berechnen. Eingelagerte Räder werden "
        "bis zum nächsten Radwechsel aufbewahrt. Die Herausgabe erfolgt gegen Vorlage dieses Annahmescheins oder "
        "eines Ausweises."),
    "abholschein_text": "Ich habe mein Fahrzeug mit den oben aufgeführten Gegenständen vollständig und in "
                        "ordnungsgemäßem Zustand zurückerhalten.",
    "garantie_monate": 12,
    # Einkauf
    "mindest_marge_prozent": 30,            # Warnung, wenn die Marge (vom VK) nach EK-Änderung darunter fällt
    "praefix_bestellung": "BE",
    "praefix_eingangsrechnung": "ER",
    "kostenarten": "Wareneinkauf / Ersatzteile\nWerkzeug & Geräte\nMiete & Nebenkosten\nTelefon & Internet\n"
                   "Software & Lizenzen\nPorto & Versand\nWerbung\nFahrzeugkosten\nBürobedarf\nFortbildung\n"
                   "Versicherungen & Beiträge\nBankgebühren\nSonstiges",
    "er_imap_ordner": "INBOX",
    "fixkosten_kategorien": "Werkstattmiete\nStrom\nInternet\nTelefon\nVersicherungen\nLeasing\nSoftware-Abos\nKfz\n"
                            "Steuerberater\nKammerbeiträge\nSonstiges",
    "fixkosten_hinweis_tage": 30,          # Hinweis auf Vertragsende / Kündigungsfrist so viele Tage vorher
    "wareneinsatz_kostenarten": "Wareneinkauf / Ersatzteile",  # Kostenarten, die als Wareneinsatz zählen (Finanzen)
    # DATEV-Export (Kontenrahmen SKR03/SKR04; leere Konten = Standard des Kontenrahmens)
    "datev_beraternr": "",
    "datev_mandantennr": "",
    "datev_skr": "03",
    "datev_wj_beginn": "01-01",           # Beginn des Wirtschaftsjahres als MM-TT
    "datev_kontenlaenge": 4,
    "datev_debitor_start": 10000,
    "datev_kreditor_start": 70000,
    "datev_konten": "",                    # Abweichungen „Name=Konto“, eine je Zeile
    "datev_kostenarten": "",               # „Kostenart=Konto“, eine je Zeile              # Postfach-Ordner für Eingangsrechnungen                  # freiwillige Garantie auf Reparaturen (6 / 12 Monate …), 0 = keine
    "handy_im_netz": False,                 # Server im WLAN erreichbar machen (für QR-Code am Handy), Neustart nötig
    "handy_adresse": "",                    # optional: feste Adresse, z. B. 192.168.178.20:5000
    # Kundenbenachrichtigung: siehe benachrichtigung.einstellungs_standard() (unten ergänzt)
    # Programm-Updates
    "update_auto": True,
    "update_letzte_pruefung": "",
    "update_verfuegbar": "",
    "update_hinweise": "",
    "update_fehler": "",
    # Sicherheit
    "login_aktiv": False,        # Passwortabfrage beim Öffnen (in den Einstellungen einschaltbar)
    "passwort_hash": "",
    # Programmfenster
    "fenster_modus": "app",      # app = eigenes Fenster (Edge-App-Modus) / browser = normaler Browser-Tab
}

from .benachrichtigung import einstellungs_standard as _ben_standard  # noqa: E402

STANDARD_EINSTELLUNGEN.update(_ben_standard())
from .datenschutz import einstellungs_standard as _ds_standard  # noqa: E402

STANDARD_EINSTELLUNGEN.update(_ds_standard())


# Mitgelieferte Vertragsarten (Preise bitte anpassen; alles unter Verträge & Lizenzen → Vertragsarten änderbar)
# (name, kategorie, beschreibung, abrechnung, laufzeit, mindestlaufzeit, preis_cent, einkauf_cent, auto_verlaengern)
STANDARD_VERTRAGSARTEN = [
    ("Wertgarantie Geräteschutz", "Garantie/Versicherung",
     "Nur zur Dokumentation – der Kunde zahlt direkt an Wertgarantie.", "keine", None, None, 0, 0, 0),
    ("ESET Antivirus – 1 Jahr", "Lizenz", "Lizenz für 1 Gerät, Laufzeit 1 Jahr", "laufzeit", 12, None, 0, 0, 0),
    ("ESET Antivirus – 2 Jahre", "Lizenz", "Lizenz für 1 Gerät, Laufzeit 2 Jahre", "laufzeit", 24, None, 0, 0, 0),
    ("ESET Antivirus – 3 Jahre", "Lizenz", "Lizenz für 1 Gerät, Laufzeit 3 Jahre", "laufzeit", 36, None, 0, 0, 0),
    ("MSP Basis (monatlich)", "MSP", "IT-Betreuung: Überwachung, Updates, Virenschutz", "monatlich", None, 12, 0, 0, 0),
]


def jetzt():
    return datetime.now().isoformat(timespec="seconds")


def jetzt_berlin():
    """Server-Zeitstempel in deutscher Zeit (Europe/Berlin) mit Sekunden und Zeitzonen-Angabe."""
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("Europe/Berlin")).isoformat(timespec="seconds")
    except Exception:  # z. B. fehlende Zeitzonendaten – dann lokale Zeit mit Abstand zu UTC
        return datetime.now().astimezone().isoformat(timespec="seconds")


def aktueller_benutzer():
    if not has_request_context():
        return "system"
    return g.get("benutzer_ersatz") or session.get("benutzer", "system")


def verbinden(pfad):
    con = sqlite3.connect(pfad, timeout=15, isolation_level=None)  # Autocommit, Transaktionen explizit
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA journal_mode = WAL")
    con.execute("PRAGMA secure_delete = ON")  # gelöschte Inhalte (z. B. Gerätezugangsdaten) werden überschrieben
    return con


def festschreiben(pfad):
    """Alle Änderungen aus der WAL-Zwischendatei in die Datenbankdatei übernehmen (vor Beenden/Neustart)."""
    try:
        con = sqlite3.connect(pfad, timeout=15)
        try:
            con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        finally:
            con.close()
    except sqlite3.Error as e:
        print(f"Hinweis: Datenbank konnte nicht festgeschrieben werden ({e})")


def get_db():
    if "db" not in g:
        g.db = verbinden(current_app.config["DB_PFAD"])
    return g.db


def schliessen(_exc=None):
    con = g.pop("db", None)
    if con is not None:
        con.close()


def initialisieren(pfad):
    con = verbinden(pfad)
    gesichert = bool(_migrieren(con, pfad))  # zuerst: Indizes/Trigger im Schema dürfen sich auf neue Spalten beziehen
    tabellen = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if not gesichert and "kunden" in tabellen and set(NEUE_TABELLEN) - tabellen:
        _sicherung_vor_migration(con, pfad)
    con.executescript(SCHEMA.read_text(encoding="utf-8"))
    _migrieren(con, pfad)
    vorhanden = {r["schluessel"] for r in con.execute("SELECT schluessel FROM einstellungen")}
    if "imap_sicherheit" not in vorhanden and "imap_port" in vorhanden:
        # Umstellung (0.9.1): bisher immer SSL – vorhandener Port 993 → SSL/TLS, sonst STARTTLS
        from .imap_verbindung import sicherheit_aus_port
        port = json.loads(con.execute("SELECT wert FROM einstellungen WHERE schluessel='imap_port'").fetchone()[0])
        con.execute("INSERT INTO einstellungen VALUES ('imap_sicherheit', ?)", (json.dumps(sicherheit_aus_port(port)),))
        vorhanden.add("imap_sicherheit")
    for k, v in STANDARD_EINSTELLUNGEN.items():
        if k not in vorhanden:
            con.execute("INSERT INTO einstellungen VALUES (?, ?)", (k, json.dumps(v)))
    # Einmalige Umstellung (Version 0.6.1, Wunsch des Inhabers): Vertragsrechnungen vollautomatisch
    if not con.execute("SELECT 1 FROM einstellungen WHERE schluessel='umstellung_abo_automatisch'").fetchone():
        con.execute("UPDATE einstellungen SET wert=? WHERE schluessel='abo_modus'", (json.dumps("automatisch"),))
        con.execute("INSERT INTO einstellungen VALUES ('umstellung_abo_automatisch', ?)", (json.dumps(jetzt()),))
    if not con.execute("SELECT 1 FROM vertragsarten LIMIT 1").fetchone():
        for va in STANDARD_VERTRAGSARTEN:
            con.execute("INSERT INTO vertragsarten (name, kategorie, beschreibung, abrechnung, laufzeit_monate, "
                        "mindestlaufzeit_monate, preis, einkauf, auto_verlaengern, erstellt_am) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?)", (*va, jetzt()))
    _verlauf_nachtragen(con)
    _leih_artikel_anlegen(con)
    _garantie_ende_nachtragen(con)
    from .textbausteine_standard import STANDARD_TEXTBAUSTEINE
    vorhandene_typen = {r[0] for r in con.execute("SELECT DISTINCT dokumenttyp FROM textbausteine")}
    leer = not vorhandene_typen
    for tb in STANDARD_TEXTBAUSTEINE:
        # beim ersten Start alle; bei Updates nur Bausteine für neu hinzugekommene Dokumenttypen
        if leer or tb["dokumenttyp"] not in vorhandene_typen:
            con.execute(
                "INSERT INTO textbausteine (kategorie, dokumenttyp, name, text, standard) VALUES (?,?,?,?,?)",
                (tb["kategorie"], tb["dokumenttyp"], tb["name"], tb["text"], tb["standard"]),
            )
    con.close()


# Spalten, die in neueren Versionen dazugekommen sind: (Tabelle, Spalte, Definition)
MIGRATIONEN = [
    ("auftraege", "kennzeichen", "TEXT"),
    ("auftraege", "km_stand", "INTEGER"),
    ("auftraege", "erstzulassung", "TEXT"),
    ("auftraege", "hu_bis", "TEXT"),
    ("auftraege", "termin_beginn", "TEXT"),
    ("auftraege", "termin_dauer", "INTEGER"),
    ("kunden", "interessent", "INTEGER NOT NULL DEFAULT 0"),
    ("kunden", "quelle", "TEXT"),
    ("vertraege", "abgerechnet_bis", "TEXT"),
    ("versandprotokoll", "ablage", "TEXT"),
    ("artikel", "ek_unbekannt", "INTEGER NOT NULL DEFAULT 0"),
    ("dokumente", "kva_status", "TEXT"),
    ("auftrag_fotos", "leihgeraet_id", "INTEGER"),
    ("auftrag_fotos", "leihe_id", "INTEGER"),
    ("auftrag_fotos", "schadensfall_id", "INTEGER"),
    ("kunden", "email_weitere", "TEXT"),
    ("dokumente", "snapshot_sha256", "TEXT"),
    ("kunden", "anonymisiert_am", "TEXT"),
    ("auftraege", "zustand_eingang", "TEXT"),
    ("auftraege", "kosten_obergrenze", "INTEGER"),
    ("auftraege", "kva_gewuenscht", "INTEGER NOT NULL DEFAULT 0"),
    ("auftraege", "kva_gebuehr", "INTEGER"),
    ("auftraege", "fertig_bis", "TEXT"),
    ("auftraege", "zugang_art", "TEXT"),
    ("auftraege", "zugang_geheim", "TEXT"),
    ("auftraege", "zugang_geloescht_am", "TEXT"),
    ("auftraege", "abgeholt_am", "TEXT"),
    ("auftraege", "wartet_teil_seit", "TEXT"),
    ("auftraege", "teil_info", "TEXT"),
    ("auftraege", "teil_erwartet", "TEXT"),
    ("auftraege", "auftragsart", "TEXT NOT NULL DEFAULT 'reparatur'"),
    ("auftraege", "garantie_bezug_id", "INTEGER"),
    ("auftraege", "garantie_monate", "INTEGER"),
    ("auftraege", "interne_kosten", "INTEGER"),
    ("auftraege", "interne_kosten_notiz", "TEXT"),
    ("positionen", "garantie_monate", "INTEGER"),
    ("artikel", "garantie_monate", "INTEGER"),
    ("artikel", "lagerfuehrend", "INTEGER NOT NULL DEFAULT 0"),
    ("artikel", "bestand", "REAL NOT NULL DEFAULT 0"),
    ("artikel", "mindestbestand", "REAL"),
    ("artikel", "lagerort", "TEXT"),
    ("artikel", "ean", "TEXT"),
    ("artikel", "herstellernr", "TEXT"),
    ("artikel", "kompatibilitaet", "TEXT"),
    ("bank_umsaetze", "er_zahlung_id", "INTEGER"),
    ("kunden", "e_rechnung", "TEXT"),
    ("kunden", "leitweg_id", "TEXT"),
    ("dokumente", "e_format", "TEXT"),
    ("dokumente", "xml_pfad", "TEXT"),
    ("dokumente", "xml_sha256", "TEXT"),
    ("eingangsrechnungen", "e_daten", "TEXT"),
    ("auftraege", "garantie_ende", "TEXT"),
    ("auftraege", "geraetetyp", "TEXT"),
    ("leihen", "protokoll_geloescht_am", "TEXT"),
    ("benachrichtigungen", "gelesen_am", "TEXT"),
    ("bank_umsaetze", "fixkosten_id", "INTEGER"),          # Abbuchung einer Fixkosten-Zahlung (0.24.0)
    ("bank_umsaetze", "fixkosten_monat", "TEXT"),          # Monat der erwarteten Fälligkeit (JJJJ-MM)
    ("eingangsrechnungen", "fixkosten_id", "INTEGER"),     # Rechnung gehört zu einer Fixkosten-Position
    ("loeschprotokolle", "frist", "TEXT"),
]

# Tabellen, die mit neueren Versionen dazukommen: fehlen sie in einer bestehenden Datenbank, wird vorher gesichert
NEUE_TABELLEN = ["auftrag_fotos", "auftrag_verlauf", "leihgeraete", "leihen", "schadensfaelle", "leihgeraet_verlauf",
                 "email_nachrichten", "email_kunden", "imap_ordner_status", "feldaenderungen", "zahlungen",
                 "bank_importe", "bank_umsaetze", "mahnungen", "auftrag_belege", "mobil_zugaenge", "benachrichtigungen", "lagerbewegungen",
                 "lager_reservierungen", "inventuren", "inventur_positionen", "inventur_zugaenge", "lieferanten",
                 "artikel_lieferanten", "bestellungen", "bestell_positionen", "wareneingaenge", "eingangsrechnungen",
                 "er_zahlungen", "kassenbuch", "kassen_abschluesse", "datev_exporte", "datev_posten",
                 "loeschprotokolle", "loeschfreigaben", "loesch_zurueckstellungen", "fixkosten",
                 "fixkosten_betraege", "hinweise_gelesen", "auftrag_checkliste"]


def _migrieren(con, pfad=None):
    """Ergänzt neue Spalten in bestehenden Datenbanken (Updates ohne Datenverlust).

    Vor jeder Änderung wird eine Sicherungskopie der Datenbank im Ordner backups angelegt.
    """
    fehlend = []
    for tabelle, spalte, definition in MIGRATIONEN:
        spalten = {r["name"] for r in con.execute(f"PRAGMA table_info({tabelle})")}
        if spalten and spalte not in spalten:
            fehlend.append((tabelle, spalte, definition))
    if not fehlend:
        return []
    if pfad:
        _sicherung_vor_migration(con, pfad)
    for tabelle, spalte, definition in fehlend:
        con.execute(f"ALTER TABLE {tabelle} ADD COLUMN {spalte} {definition}")
    return fehlend


LEIH_ARTIKEL = [  # (Name, Einheit, Beschreibung) – einheitliche Positionen für Rechnungen
    ("Leihgebühr pauschal", "pauschal", "Leihgerät für die Dauer der Reparatur"),
    ("Leihgebühr pro Tag", "Tag", "Leihgerät je angefangenem Kalendertag"),
    ("Schadenersatz Leihgerät", "pauschal", "Schaden oder fehlendes Zubehör am Leihgerät"),
]


def _leih_artikel_anlegen(con):
    """Einmalig die Katalog-Positionen für Leihgebühr und Schadenersatz anlegen (Steuersatz wie übrige Leistungen)."""
    if con.execute("SELECT 1 FROM einstellungen WHERE schluessel='leih_artikel_angelegt'").fetchone():
        return
    satz = json.loads(con.execute("SELECT wert FROM einstellungen WHERE schluessel='regel_steuersatz'").fetchone()[0])
    for name, einheit, beschreibung in LEIH_ARTIKEL:
        if not con.execute("SELECT 1 FROM artikel WHERE lower(name)=lower(?)", (name,)).fetchone():
            con.execute("INSERT INTO artikel (name, beschreibung, leistungsart, typ, einheit, preis, teilekosten, "
                        "steuersatz, ek_unbekannt, erstellt_am, geaendert_am) VALUES (?,?,?,'leistung',?,0,0,?,1,?,?)",
                        (name, beschreibung, "Sonstiges", einheit, satz, jetzt(), jetzt()))
    con.execute("INSERT INTO einstellungen VALUES ('leih_artikel_angelegt', ?)", (json.dumps(jetzt()),))


def _garantie_ende_nachtragen(con):
    """Einmalig (0.21.0): Garantieende für bereits abgeholte Aufträge aus Abholdatum + Garantiedauer speichern."""
    if con.execute("SELECT 1 FROM einstellungen WHERE schluessel='garantie_ende_nachgetragen'").fetchone():
        return
    from .garantie import ende_berechnen, _datum
    werte = dict(STANDARD_EINSTELLUNGEN)
    for r in con.execute("SELECT schluessel, wert FROM einstellungen"):
        werte[r["schluessel"]] = json.loads(r["wert"])
    for a in con.execute("SELECT * FROM auftraege WHERE abgeholt_am IS NOT NULL AND garantie_ende IS NULL").fetchall():
        ende = ende_berechnen(a, werte, _datum(a["abgeholt_am"]))
        if ende:
            con.execute("UPDATE auftraege SET garantie_ende=? WHERE id=?", (ende.isoformat(), a["id"]))
    con.execute("INSERT INTO einstellungen VALUES ('garantie_ende_nachgetragen', ?)", (json.dumps(jetzt()),))


def _verlauf_nachtragen(con):
    """Einmalig: Für Aufträge aus älteren Versionen den Verlauf aus dem Änderungsprotokoll übernehmen."""
    if con.execute("SELECT 1 FROM einstellungen WHERE schluessel='verlauf_nachgetragen'").fetchone():
        return
    texte = {"auftrag_angelegt": "Auftrag angelegt", "auftrag_geaendert": "Auftragsdaten geändert"}
    for a in con.execute("SELECT id, eingang_am FROM auftraege").fetchall():
        eintraege = con.execute("SELECT * FROM protokoll WHERE objekt='auftrag' AND objekt_id=? ORDER BY id",
                                (a["id"],)).fetchall()
        if not eintraege:
            con.execute("INSERT INTO auftrag_verlauf (auftrag_id, zeitpunkt, benutzer, ereignis, details) "
                        "VALUES (?,?,?,?,?)", (a["id"], a["eingang_am"], "system", "Auftrag angelegt", None))
        for e in eintraege:
            if e["aktion"] == "auftrag_status":
                d = json.loads(e["details"] or "{}")
                text, details = "Status geändert", f"{d.get('von')} → {d.get('nach')}"
            else:
                text, details = texte.get(e["aktion"], e["aktion"]), None
            con.execute("INSERT INTO auftrag_verlauf (auftrag_id, zeitpunkt, benutzer, ereignis, details) "
                        "VALUES (?,?,?,?,?)", (a["id"], e["zeitpunkt"], e["benutzer"], text, details))
    con.execute("INSERT INTO einstellungen VALUES ('verlauf_nachgetragen', ?)", (json.dumps(jetzt()),))


def _sicherung_vor_migration(con, pfad):
    ziel_ordner = Path(pfad).parent / "backups"
    ziel_ordner.mkdir(parents=True, exist_ok=True)
    ziel = ziel_ordner / f"vor_update_{datetime.now():%Y-%m-%d_%H%M%S}.db"
    if ziel.exists():  # nie eine ältere Sicherung überschreiben
        ziel = ziel.with_name(f"{ziel.stem}_{datetime.now():%f}.db")
    kopie = sqlite3.connect(ziel)
    with kopie:
        con.backup(kopie)
    kopie.close()


# ---------------------------------------------------------------- Einstellungen

def einstellungen(con=None):
    con = con or get_db()
    werte = dict(STANDARD_EINSTELLUNGEN)
    for r in con.execute("SELECT schluessel, wert FROM einstellungen"):
        try:
            werte[r["schluessel"]] = json.loads(r["wert"])
        except (TypeError, ValueError):
            werte[r["schluessel"]] = r["wert"]
    return werte


def einstellung(name, con=None):
    return einstellungen(con).get(name)


def einstellungen_speichern(werte: dict, con=None):
    con = con or get_db()
    for k, v in werte.items():
        con.execute(
            "INSERT INTO einstellungen (schluessel, wert) VALUES (?, ?) "
            "ON CONFLICT(schluessel) DO UPDATE SET wert = excluded.wert",
            (k, json.dumps(v)),
        )


# ---------------------------------------------------------------- Protokoll

def _hash(vorher, zeitpunkt, benutzer, aktion, objekt, objekt_id, details):
    roh = json.dumps([vorher, zeitpunkt, benutzer, aktion, objekt, objekt_id, details], ensure_ascii=False)
    return hashlib.sha256(roh.encode("utf-8")).hexdigest()


def _als_text(wert):
    if wert is None:
        return ""
    if isinstance(wert, float) and wert.is_integer():
        wert = int(wert)
    return str(wert)


def aenderungen_erfassen(con, objekt, objekt_id, alt, neu, aktion="geaendert", namen=None):
    """Feldgenaues Änderungsprotokoll: schreibt je geändertem Feld eine Zeile (alt → neu).

    alt/neu: dict oder sqlite3.Row (alt=None bei Neuanlage). Gibt die Liste der geänderten Felder zurück.
    """
    alt = dict(alt) if alt is not None else {}
    geaendert = []
    zeit, benutzer = jetzt_berlin(), aktueller_benutzer()
    for feld, wert in neu.items():
        if feld in ("geaendert_am", "erstellt_am"):
            continue
        a, n = _als_text(alt.get(feld)), _als_text(wert)
        if a == n:
            continue
        geaendert.append(feld)
        con.execute("INSERT INTO feldaenderungen (zeitpunkt, benutzer, objekt, objekt_id, aktion, feld, alt, neu) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    (zeit, benutzer, objekt, objekt_id, aktion, (namen or {}).get(feld, feld), a, n))
    return geaendert


def ereignis_erfassen(con, objekt, objekt_id, aktion, text=""):
    """Ereignis ohne Feldbezug (z. B. festgeschrieben, storniert, gelöscht) im Änderungsprotokoll."""
    con.execute("INSERT INTO feldaenderungen (zeitpunkt, benutzer, objekt, objekt_id, aktion, feld, alt, neu) "
                "VALUES (?,?,?,?,?,?,?,?)", (jetzt_berlin(), aktueller_benutzer(), objekt, objekt_id, aktion, None,
                                            None, text))


def aenderungen_liste(con, objekt, objekt_id):
    return con.execute("SELECT * FROM feldaenderungen WHERE objekt=? AND objekt_id=? ORDER BY id DESC",
                       (objekt, objekt_id)).fetchall()


def protokollieren(aktion, objekt=None, objekt_id=None, details=None, con=None):
    """Schreibt einen Eintrag ins Änderungsprotokoll. Jeder Eintrag enthält den Hash des vorherigen."""
    con = con or get_db()
    benutzer = aktueller_benutzer()
    if details is not None and not isinstance(details, str):
        details = json.dumps(details, ensure_ascii=False, default=str)
    letzte = con.execute("SELECT hash FROM protokoll ORDER BY id DESC LIMIT 1").fetchone()
    vorher = letzte["hash"] if letzte else "0" * 64
    zeit = jetzt()
    h = _hash(vorher, zeit, benutzer, aktion, objekt, objekt_id, details)
    con.execute(
        "INSERT INTO protokoll (zeitpunkt, benutzer, aktion, objekt, objekt_id, details, hash_vorher, hash) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (zeit, benutzer, aktion, objekt, objekt_id, details, vorher, h),
    )


def protokoll_pruefen(con=None):
    """Prüft die Hash-Kette. Gibt eine Liste mit Fehlern zurück (leer = in Ordnung)."""
    con = con or get_db()
    fehler = []
    vorher = "0" * 64
    for r in con.execute("SELECT * FROM protokoll ORDER BY id"):
        if r["hash_vorher"] != vorher:
            fehler.append(f"Eintrag {r['id']}: Verkettung unterbrochen (Eintrag davor fehlt oder wurde verändert).")
        erwartet = _hash(r["hash_vorher"], r["zeitpunkt"], r["benutzer"], r["aktion"], r["objekt"],
                         r["objekt_id"], r["details"])
        if erwartet != r["hash"]:
            fehler.append(f"Eintrag {r['id']}: Inhalt wurde nachträglich verändert.")
        vorher = r["hash"]
    return fehler


class Transaktion:
    """Kontextmanager für eine schreibende Transaktion (BEGIN IMMEDIATE sperrt sofort)."""

    def __init__(self, con):
        self.con = con

    def __enter__(self):
        self.con.execute("BEGIN IMMEDIATE")
        return self.con

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self.con.execute("COMMIT")
        else:
            self.con.execute("ROLLBACK")
        return False
