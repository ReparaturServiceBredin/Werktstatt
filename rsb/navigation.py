"""Navigation: Seitenleiste, Brotkrumen, Reiter, Einstellungs-Gruppen und Ziele der Schnellsuche (Strg+K).

Eine Stelle für die Menüstruktur – Seitenleiste, Kopfzeile, Schnellsuche und Tests lesen alle von hier.
"""
from dataclasses import dataclass, field


@dataclass
class Eintrag:
    schluessel: str
    titel: str
    symbol: str
    endpoint: str
    zaehler: str = ""          # Name des Zählers aus dem Kontext (z. B. „offene_anfragen“)
    zaehler_rot: bool = False  # rot nur bei Überfälligem
    zaehler_titel: str = ""
    stichworte: str = ""       # zusätzliche Suchbegriffe
    args: dict = field(default_factory=dict)


@dataclass
class Gruppe:
    schluessel: str
    titel: str
    eintraege: list


SEITENLEISTE = [
    Gruppe("", "", [Eintrag("start", "Übersicht", "layout-dashboard", "main.start", stichworte="Start Dashboard")]),
    Gruppe("werkstatt", "Werkstatt", [
        Eintrag("anfragen", "Anfragen", "inbox", "main.anfragen_liste", "offene_anfragen",
                zaehler_titel="neue Anfragen", stichworte="Kontaktformular Posteingang"),
        Eintrag("auftraege", "Reparaturaufträge", "wrench", "main.auftraege", "offene_auftraege",
                zaehler_titel="offene Aufträge", stichworte="Tafel Reparatur Annahme Abholung"),
        Eintrag("leihgeraete", "Leihgeräte", "laptop", "main.leihgeraete", "leihen_ueberfaellig", True,
                "überfällige Rückgaben", "Leihe Ersatzgerät"),
    ]),
    Gruppe("kunden", "Kunden", [
        Eintrag("kunden", "Kunden", "users", "main.kunden", stichworte="Interessenten Adressen"),
        Eintrag("vertraege", "Verträge & Lizenzen", "scroll-text", "main.vertraege_liste",
                stichworte="Wertgarantie ESET MSP Abo Lizenz"),
    ]),
    Gruppe("verkauf", "Verkauf", [
        Eintrag("rechnungen", "Rechnungen", "receipt", "main.dokumente", "posten_ueberfaellig", True,
                "überfällige Rechnungen", "Kostenvoranschläge KVA Offene Posten Mahnwesen Gutschrift Storno"),
        Eintrag("artikel", "Leistungen & Artikel", "tag", "main.artikel_liste", stichworte="Katalog Preise"),
    ]),
    Gruppe("einkauf", "Einkauf & Lager", [
        Eintrag("lager", "Lager", "boxes", "main.lager", "lager_unter_min", False, "unter Mindestbestand",
                "Bestand Inventur Mindestbestand"),
        Eintrag("einkauf", "Einkauf", "shopping-cart", "main.bestellungen",
                stichworte="Bestellungen Lieferanten Eingangsrechnungen"),
    ]),
    Gruppe("buchhaltung", "Buchhaltung", [
        Eintrag("bank", "Bankabgleich", "landmark", "main.bank", stichworte="Kontoauszug Zahlungen CSV"),
        Eintrag("kasse", "Kassenbuch", "wallet", "main.kassenbuch", stichworte="Bargeld Kassensturz Privateinlage"),
        Eintrag("fixkosten", "Fixkosten", "calendar-clock", "main.fixkosten_liste",
                stichworte="Miete Strom Versicherung Leasing Abo wiederkehrende Ausgaben Kündigungsfrist"),
        Eintrag("finanzen", "Finanzen", "chart-column", "main.finanzen",
                stichworte="Finanzübersicht Umsatz Ergebnis Rohertrag Break-even Auswertung Gewinn"),
        Eintrag("datev", "DATEV-Export", "file-output", "main.datev", stichworte="Steuerberater Buchungsstapel"),
    ]),
]
EINSTELLUNGEN = Eintrag("einstellungen", "Einstellungen", "settings", "main.einstellungen",
                        stichworte="Konfiguration Optionen", args={"bereich": "firma"})

# Reiter auf zusammengefassten Seiten
REITER = {
    "rechnungen": [("Rechnungen", "main.dokumente"), ("Kostenvoranschläge", "main.kostenvoranschlaege"),
                   ("Offene Posten", "main.offene_posten"), ("Mahnwesen", "main.mahnwesen")],
    "einkauf": [("Bestellungen", "main.bestellungen"), ("Lieferanten", "main.lieferanten"),
                ("Eingangsrechnungen", "main.eingangsrechnungen")],
}

# Welcher Menüpunkt ist bei welchem Endpoint aktiv (erster passender Präfix gewinnt, ohne „main.“)
ZUORDNUNG = [
    ("start", "start"), ("anfrage", "anfragen"), ("auftr", "auftraege"),
    ("geraet_pruefen", "auftraege"), ("beleg", "auftraege"), ("foto", "auftraege"),
    ("leihe_ausgeben", "leihgeraete"), ("leih", "leihgeraete"), ("kunde", "kunden"), ("vertr", "vertraege"),
    ("dokument", "rechnungen"), ("kostenvoranschlaege", "rechnungen"), ("offene_posten", "rechnungen"),
    ("mahn", "rechnungen"), ("zahlung", "rechnungen"), ("artikel", "artikel"), ("lager", "lager"),
    ("inventur", "lager"), ("bestellung", "einkauf"), ("lieferant", "einkauf"), ("eingangsrechnung", "einkauf"),
    ("bank", "bank"), ("kasse", "kasse"), ("datev", "datev"), ("fixkosten", "fixkosten"), ("finanz", "finanzen"),
    ("einstellungen", "einstellungen"), ("backup", "einstellungen"), ("logo", "einstellungen"),
    ("musterrechnung", "einstellungen"), ("textbaustein", "einstellungen"), ("protokoll", "einstellungen"),
    ("pruefung", "einstellungen"), ("datenschutz", "einstellungen"), ("verfahrensdoku", "einstellungen"),
    ("versionen", "einstellungen"), ("passwort", "einstellungen"), ("testmail", "einstellungen"),
    ("update", "einstellungen"),
]

# Einstellungen: Unternavigation (Schlüssel = Bereich, sonst Endpoint für eigene Seiten)
EINSTELLUNGS_GRUPPEN = [
    ("Unternehmen", [("firma", "Firmendaten", "building-2"), ("layout", "Layout & Dokumente", "palette")]),
    ("Verkauf & Werkstatt", [("rechnung", "Rechnung & Steuer", "calculator"),
                             ("annahme", "Annahme & Abholung", "clipboard-check"),
                             ("leihgeraete", "Leihgeräte", "laptop"), ("vertraege", "Verträge", "scroll-text"),
                             ("mahnwesen", "Mahnwesen", "file-clock")]),
    ("Kommunikation", [("email", "E-Mail (Versand und IMAP)", "mail"), ("anfragen", "Anfragen", "inbox"),
                       ("benachrichtigung", "Benachrichtigungen", "bell")]),
    ("Einkauf & Buchhaltung", [("einkauf", "Einkauf", "truck"), ("datev", "DATEV", "file-output")]),
    ("System", [("datenschutz", "Datenschutz", "shield"), ("backup", "Backup", "hard-drive"),
                ("sicherheit", "Passwortschutz", "lock"), ("programm", "Programm & Updates", "refresh-cw")]),
]
# Weitere Verwaltungsseiten (früher eigene Menüpunkte) – in der Einstellungs-Navigation verlinkt
VERWALTUNG = [
    ("main.textbausteine", "Textbausteine", "type", "Vorlagen E-Mail Texte Einleitung Schlusstext"),
    ("main.datenschutz", "Datenschutz-Übersicht & Löschfristen", "shield", "Löschlauf Löschprotokoll DSGVO Auskunft"),
    ("main.protokoll", "Protokoll", "history", "Änderungsprotokoll Audit GoBD"),
    ("main.pruefung", "Datenprüfung", "list-checks", "Prüfung Integrität Kontrolle"),
    ("main.verfahrensdokumentation", "Verfahrensdokumentation", "file-text", "GoBD Dokumentation"),
    ("main.versionen", "Versionsprotokoll", "file-clock", "Änderungen Version Neuerungen"),
]
BEREICHS_TITEL = {b: t for _, liste in EINSTELLUNGS_GRUPPEN for b, t, _ in liste}

# Schnellaktionen (Strg+K und „+ Neu“)
NEU = [
    ("Neuer Auftrag", "main.auftrag_neu", {}, "wrench"),
    ("Neuer Kunde", "main.kunde", {}, "user-plus"),
    ("Neuer KVA", "main.dokument_neu", {"typ": "kva"}, "file-plus"),
    ("Neue Rechnung", "main.dokument_neu", {"typ": "rechnung"}, "receipt"),
    ("Leihgerät ausgeben", "main.leihe_ausgabe_waehlen", {}, "laptop"),
]


def alle_eintraege():
    for g in SEITENLEISTE:
        for e in g.eintraege:
            yield g, e
    yield None, EINSTELLUNGEN


def aktiver_schluessel(endpoint):
    name = (endpoint or "").removeprefix("main.")
    for praefix, schluessel in ZUORDNUNG:
        if name.startswith(praefix):
            return schluessel
    return ""


def eintrag(schluessel):
    for g, e in alle_eintraege():
        if e.schluessel == schluessel:
            return g, e
    return None, None


def aktive_gruppe(endpoint):
    g, _ = eintrag(aktiver_schluessel(endpoint))
    return g.schluessel if g else ""
