"""Legt Beispieldaten zum Ausprobieren an: python -m rsb.beispieldaten

Nur für einen leeren Test-Datenordner gedacht (z. B. RSB_DATEN=Testdaten)!
"""
import sys

from . import create_app
from . import db as dbm
from .logik import naechste_kundennr, summen_speichern

KUNDEN = [
    dict(typ="privat", anrede="Frau", vorname="Anna", nachname="Müller", strasse="Hauptstraße 5", plz="74219",
         ort="Möckmühl", email="anna.mueller@example.com", telefon="0151 2345678"),
    dict(typ="firma", firma="Bäckerei Schön GmbH", anrede="Herr", vorname="Peter", nachname="Schön",
         strasse="Marktplatz 2", plz="74177", ort="Bad Friedrichshall", email="buero@baeckerei-schoen.example",
         telefon="07136 12345", notizen="Siebträger La Marzocco, jährliche Wartung im März"),
    dict(typ="privat", anrede="Herr", vorname="Jonas", nachname="Weber", strasse="Ringstraße 17", plz="74238",
         ort="Krautheim", email="jonas.weber@example.com"),
]

ARTIKEL = [
    ("Akkutausch Smartphone", "inkl. Ersatzakku und Funktionstest", "Smartphone", "leistung", "pauschal", 7900, 2200, None),
    ("Displaytausch iPhone 13", "Ersatzdisplay (Premium-Qualität), Einbau und Test", "Smartphone", "leistung", "pauschal", 18900, 9500, None),
    ("Ladebuchse reinigen/tauschen", "", "Smartphone", "leistung", "pauschal", 4900, 600, None),
    ("Kaffeemaschinen-Wartung", "Entkalken, Brühgruppe reinigen und fetten, Dichtungen prüfen", "Kaffeemaschine", "leistung", "pauschal", 8900, 1200, None),
    ("Dichtungssatz Brühgruppe", "", "Kaffeemaschine", "material", "Stk.", 1490, 690, 116),
    ("PC-Reinigung & Wärmeleitpaste", "Innenreinigung, Lüfter, neue Wärmeleitpaste", "PC/Laptop", "leistung", "pauschal", 5900, 400, None),
    ("SSD-Upgrade 1 TB inkl. Datenübernahme", "", "PC/Laptop", "leistung", "pauschal", 14900, 6500, None),
    ("Arbeitszeit", "je angefangene Stunde", "Sonstiges", "leistung", "Std.", 5500, 0, None),
]


def main():
    app = create_app()
    with app.app_context():
        con = dbm.get_db()
        if con.execute("SELECT 1 FROM kunden LIMIT 1").fetchone():
            print("Es sind bereits Kunden vorhanden – Beispieldaten werden nicht angelegt.")
            sys.exit(1)
        with dbm.Transaktion(con):
            dbm.einstellungen_speichern({
                "strasse": "Musterstraße 1", "plz": "74219", "telefon": "0151 00000000",
                "steuernummer": "00/000/00000 (Beispiel)", "bank_name": "Beispielbank",
                "iban": "DE02120300000000202051", "bic": "BYLADEM1001",
            }, con)
            einst = dbm.einstellungen(con)
            for k in KUNDEN:
                felder = {"land": "Deutschland", **k}
                con.execute(
                    f"INSERT INTO kunden (kundennr, {', '.join(felder)}, erstellt_am, geaendert_am) "
                    f"VALUES (?, {', '.join('?' * len(felder))}, ?, ?)",
                    [naechste_kundennr(con, einst), *felder.values(), dbm.jetzt(), dbm.jetzt()])
            for name, beschr, art, typ, einheit, preis, teile, aufschlag in ARTIKEL:
                con.execute(
                    "INSERT INTO artikel (name, beschreibung, leistungsart, typ, einheit, preis, teilekosten, "
                    "aufschlag_prozent, steuersatz, aktiv, erstellt_am, geaendert_am) VALUES (?,?,?,?,?,?,?,?,19,1,?,?)",
                    (name, beschr, art, typ, einheit, preis, teile, aufschlag, dbm.jetzt(), dbm.jetzt()))
            dbm.protokollieren("beispieldaten_angelegt", "system", con=con)
        print("Beispieldaten angelegt: 3 Kunden, 8 Leistungen/Artikel.")


if __name__ == "__main__":
    main()
