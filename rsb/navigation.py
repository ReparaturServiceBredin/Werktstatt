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
    Gruppe("", "", [Eintrag("start", "Übersicht", "layout-dashboard", "main.start", stichworte="Start Dashboard Heute")]),
    Gruppe("werkstatt", "Werkstatt", [
        Eintrag("auftraege", "Aufträge", "wrench", "main.kalender", "offene_auftraege",
                zaehler_titel="offene Aufträge",
                stichworte="Kalender Termine Wochenplan Einplanen Tafel Annahme Abholung Checkliste"),
        Eintrag("kunden", "Kunden", "users", "main.kunden", stichworte="Adressen Fahrzeuge"),
    ]),
    Gruppe("verkauf", "Rechnungen", [
        Eintrag("rechnungen", "Rechnungen", "receipt", "main.dokumente", "posten_ueberfaellig", True,
                "überfällige Rechnungen", "Kostenvoranschläge KVA Offene Posten Mahnwesen Gutschrift Storno Einnahmen"),
        Eintrag("artikel", "Leistungen & Artikel", "tag", "main.artikel_liste", stichworte="Katalog Preise Teile"),
    ]),
    Gruppe("buchhaltung", "Buchhaltung", [
        Eintrag("belege", "Belege & Ausgaben", "file-text", "main.eingangsrechnungen",
                stichworte="Eingangsrechnungen scannen hochladen Ausgaben Kosten Quittung"),
        Eintrag("kasse", "Kassenbuch", "wallet", "main.kassenbuch", stichworte="Bargeld Bareinnahme Barzahlung Kassensturz"),
        Eintrag("finanzen", "Finanzen", "chart-column", "main.finanzen",
                stichworte="Kostenübersicht Einnahmen Ausgaben Umsatz Ergebnis Gewinn"),
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
    "auftraege": [("Kalender", "main.kalender"), ("Tafel", "main.auftraege")],
}

# Welcher Menüpunkt ist bei welchem Endpoint aktiv (erster passender Präfix gewinnt, ohne „main.“)
ZUORDNUNG = [
    ("start", "start"), ("kalender", "auftraege"), ("anfrage", "anfragen"), ("auftr", "auftraege"),
    ("geraet_pruefen", "auftraege"), ("beleg", "auftraege"), ("foto", "auftraege"),
    ("leihe_ausgeben", "leihgeraete"), ("leih", "leihgeraete"), ("kunde", "kunden"), ("vertr", "vertraege"),
    ("dokument", "rechnungen"), ("kostenvoranschlaege", "rechnungen"), ("offene_posten", "rechnungen"),
    ("mahn", "rechnungen"), ("zahlung", "rechnungen"), ("artikel", "artikel"), ("lager", "lager"),
    ("inventur", "lager"), ("bestellung", "belege"), ("lieferant", "belege"), ("eingangsrechnung", "belege"), ("er_", "belege"),
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
    ("Werkstatt & Rechnungen", [("annahme", "Aufträge, Checklisten & Kalender", "clipboard-check"),
                                ("rechnung", "Rechnung & Steuer", "calculator"),
                                ("mahnwesen", "Mahnwesen", "file-clock")]),
    ("Kommunikation", [("email", "E-Mail", "mail"), ("benachrichtigung", "Kundennachrichten", "bell")]),
    ("Buchhaltung", [("einkauf", "Belege & Kostenarten", "file-text")]),
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
    ("Neuer Beleg", "main.eingangsrechnung_neu", {"neu": 1}, "file-plus"),
    ("Kassenbuchung", "main.kassenbuch", {}, "wallet"),
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
