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


_SEITENLEISTE_SAUTER = [
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
# Reifen & Teile: Reifenwerkstatt mit Autoteile-Verkauf (Lager, Einkauf, Theke, Reifeneinlagerung)
_SEITENLEISTE_REIFEN = [
    Gruppe("", "", [Eintrag("start", "Übersicht", "layout-dashboard", "main.start", stichworte="Start Dashboard Heute")]),
    Gruppe("werkstatt", "Werkstatt", [
        Eintrag("auftraege", "Aufträge", "wrench", "main.kalender", "offene_auftraege",
                zaehler_titel="offene Aufträge",
                stichworte="Kalender Termine Wochenplan Einplanen Tafel Annahme Abholung Checkliste Räderwechsel"),
        Eintrag("einlagerung", "Reifeneinlagerung", "boxes", "main.einlagerungen", "einlagerung_erinnern",
                zaehler_titel="Kunden für den Saisonwechsel noch nicht erinnert",
                stichworte="Reifenhotel Räder einlagern auslagern Lagerplatz Etikett Saisonwechsel Winterreifen "
                           "Sommerreifen Erinnerung"),
        Eintrag("kunden", "Kunden", "users", "main.kunden", stichworte="Adressen Fahrzeuge"),
    ]),
    Gruppe("verkauf", "Verkauf", [
        Eintrag("theke", "Thekenverkauf", "shopping-cart", "main.theke",
                stichworte="Ladenverkauf Barverkauf Kasse Teile verkaufen Quittung EC-Karte"),
        Eintrag("rechnungen", "Rechnungen", "receipt", "main.dokumente", "posten_ueberfaellig", True,
                "überfällige Rechnungen", "Kostenvoranschläge KVA Offene Posten Mahnwesen Gutschrift Storno Einnahmen"),
        Eintrag("artikel", "Reifen, Teile & Leistungen", "tag", "main.artikel_liste",
                stichworte="Katalog Preise Teile Reifengröße Dimension Felgen Autoteile OE-Nummer"),
        Eintrag("lager", "Lager", "package", "main.lager", "lager_unter_min",
                zaehler_titel="Artikel unter Mindestbestand", stichworte="Bestand Inventur Mindestbestand Lagerort"),
        Eintrag("einkauf", "Einkauf", "truck", "main.bestellungen",
                stichworte="Bestellungen Lieferanten Großhändler Teilehändler Wareneingang"),
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
_REITER = {
    "rechnungen": [("Rechnungen", "main.dokumente"), ("Kostenvoranschläge", "main.kostenvoranschlaege"),
                   ("Offene Posten", "main.offene_posten"), ("Mahnwesen", "main.mahnwesen")],
    "einkauf": [("Bestellungen", "main.bestellungen"), ("Lieferanten", "main.lieferanten"),
                ("Eingangsrechnungen", "main.eingangsrechnungen")],
    "auftraege": [("Kalender", "main.kalender"), ("Tafel", "main.auftraege")],
    "einlagerung": [("Eingelagert", "main.einlagerungen"), ("Saisonwechsel", "main.einlagerung_saison"),
                    ("Ausgelagert", "main.einlagerungen_archiv")],
}

# Welcher Menüpunkt ist bei welchem Endpoint aktiv (erster passender Präfix gewinnt, ohne „main.“)
ZUORDNUNG = [
    ("start", "start"), ("einlagerung", "einlagerung"), ("theke", "theke"), ("kalender", "auftraege"), ("anfrage", "anfragen"), ("auftr", "auftraege"),
    ("geraet_pruefen", "auftraege"), ("beleg", "auftraege"), ("foto", "auftraege"),
    ("leihe_ausgeben", "leihgeraete"), ("leih", "leihgeraete"), ("kunde", "kunden"), ("vertr", "vertraege"),
    ("dokument", "rechnungen"), ("kostenvoranschlaege", "rechnungen"), ("offene_posten", "rechnungen"),
    ("mahn", "rechnungen"), ("zahlung", "rechnungen"), ("artikel", "artikel"), ("lager", "lager"),
    ("inventur", "lager"), ("bestellung", "einkauf_oder_belege"), ("lieferant", "einkauf_oder_belege"), ("eingangsrechnung", "belege"), ("er_", "belege"),
    ("bank", "bank"), ("kasse", "kasse"), ("datev", "datev"), ("fixkosten", "fixkosten"), ("finanz", "finanzen"),
    ("einstellungen", "einstellungen"), ("backup", "einstellungen"), ("logo", "einstellungen"),
    ("musterrechnung", "einstellungen"), ("textbaustein", "einstellungen"), ("protokoll", "einstellungen"),
    ("pruefung", "einstellungen"), ("datenschutz", "einstellungen"), ("verfahrensdoku", "einstellungen"),
    ("versionen", "einstellungen"), ("passwort", "einstellungen"), ("testmail", "einstellungen"),
    ("update", "einstellungen"),
]

# Einstellungen: Unternavigation (Schlüssel = Bereich, sonst Endpoint für eigene Seiten)
_EINSTELLUNGS_GRUPPEN_SAUTER = [
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
_EINSTELLUNGS_GRUPPEN_REIFEN = [
    (g, ([("annahme", "Aufträge, Checklisten & Kalender", "clipboard-check"),
          ("einlagerung", "Reifeneinlagerung", "boxes")] + [x for x in liste if x[0] != "annahme"])
     if g == "Werkstatt & Rechnungen" else liste)
    for g, liste in _EINSTELLUNGS_GRUPPEN_SAUTER
]
BEREICHS_TITEL = {b: t for _, liste in _EINSTELLUNGS_GRUPPEN_REIFEN for b, t, _ in liste}

# Schnellaktionen (Strg+K und „+ Neu“)
_NEU_SAUTER = [
    ("Neuer Auftrag", "main.auftrag_neu", {}, "wrench"),
    ("Neuer Kunde", "main.kunde", {}, "user-plus"),
    ("Neuer KVA", "main.dokument_neu", {"typ": "kva"}, "file-plus"),
    ("Neue Rechnung", "main.dokument_neu", {"typ": "rechnung"}, "receipt"),
    ("Neuer Beleg", "main.eingangsrechnung_neu", {"neu": 1}, "file-plus"),
    ("Kassenbuchung", "main.kassenbuch", {}, "wallet"),
]


_NEU_REIFEN = [
    ("Neuer Auftrag", "main.auftrag_neu", {}, "wrench"),
    ("Neue Einlagerung", "main.einlagerung", {}, "boxes"),
    ("Thekenverkauf", "main.theke", {}, "shopping-cart"),
    ("Neuer Kunde", "main.kunde", {}, "user-plus"),
    ("Neue Rechnung", "main.dokument_neu", {"typ": "rechnung"}, "receipt"),
    ("Neuer Beleg", "main.eingangsrechnung_neu", {"neu": 1}, "file-plus"),
]


def __getattr__(name):
    """SEITENLEISTE und NEU hängen von der Programm-Variante ab (rsb/variante.py)."""
    from . import variante
    if name == "SEITENLEISTE":
        return _SEITENLEISTE_REIFEN if variante.hat("reifen") else _SEITENLEISTE_SAUTER
    if name == "REITER":
        return _REITER if variante.hat("reifen") else {k: v for k, v in _REITER.items() if k != "einlagerung"}
    if name == "EINSTELLUNGS_GRUPPEN":
        return _EINSTELLUNGS_GRUPPEN_REIFEN if variante.hat("reifen") else _EINSTELLUNGS_GRUPPEN_SAUTER
    if name == "NEU":
        return _NEU_REIFEN if variante.hat("reifen") else _NEU_SAUTER
    raise AttributeError(name)


def alle_eintraege():
    for g in __getattr__("SEITENLEISTE"):
        for e in g.eintraege:
            yield g, e
    yield None, EINSTELLUNGEN


def aktiver_schluessel(endpoint):
    name = (endpoint or "").removeprefix("main.")
    for praefix, schluessel in ZUORDNUNG:
        if name.startswith(praefix):
            if schluessel == "einkauf_oder_belege":  # Reifen & Teile hat einen eigenen Menüpunkt „Einkauf“
                from . import variante
                return "einkauf" if variante.hat("reifen") else "belege"
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
