# Versionsprotokoll

Alle Versionen von Werkstatt Sauter mit Neuerungen, Änderungen und Fehlerbehebungen. Die neueste Version steht oben.

**So funktionieren Versionen**
- Die Versionsnummer steht unten links im Programm und unter *Einstellungen → Programm & Updates*.
- Aufbau: `Haupt.Funktion.Korrektur`. Die mittlere Zahl steigt bei neuen Funktionen, die letzte Zahl bei
  reinen Fehlerbehebungen.
- Jede Version gibt es als `Werkstatt-Sauter.exe` unter
  [GitHub → Releases](https://github.com/ReparaturServiceBredin/Werktstatt/releases).
  Das Programm installiert neue Versionen selbst und erstellt vorher ein Backup.
- Ihre Daten bleiben bei jedem Update erhalten. Neue Datenbankfelder ergänzt das Programm beim Start selbst.

| Version | Datum | Schwerpunkt |
|---|---|---|
| 1.1.0 | 16.10.2026 | Werkstattkalender: Aufträge per Ziehen einplanen |
| 1.0.1 | 16.10.2026 | Updates kommen aus dem richtigen Projekt |
| 1.0.0 | 16.10.2026 | Erste Version für die Kfz-Werkstatt |

## 1.1.0 – 16.10.2026
Neu: Werkstattkalender. Vor der Erweiterung der Datenbank legt das Programm automatisch eine Sicherung an.

### Neu: Kalender (*Werkstatt → Kalender*)
- Wochenansicht Montag bis Samstag mit Uhrzeiten. Links stehen alle offenen Aufträge ohne Termin.
- **Einplanen per Ziehen:** Auftrag mit der Maus auf Tag und Uhrzeit ziehen. Der Termin rastet auf die
  Viertelstunde ein, eine Vorschau zeigt beim Ziehen Beginn und Ende.
- **Verschieben** durch erneutes Ziehen, **zurück in die Liste** ziehen entfernt den Termin.
  Mit **−** und **+** an der Terminkarte wird der Termin 15 Minuten kürzer bzw. länger.
- Jede Terminkarte zeigt Uhrzeit, Kunde, Kennzeichen, Fahrzeug, Leistungen und den Stand der Checkliste.
  Klick öffnet den Auftrag. Überschneidende Termine stehen nebeneinander.
- **Dauer automatisch:** Die Richtzeiten der Leistungen werden zusammengezählt (z. B. Reifenwechsel 30 +
  Auswuchten 30 = 60 Minuten). Richtzeiten, Uhrzeiten und Samstag unter
  *Einstellungen → Annahme & Abholung → Kalender*.
- Je Tag: Anzahl der Termine und verplante Zeit. Heute ist hervorgehoben, eine rote Linie zeigt die aktuelle Uhrzeit.
- Termine stehen im Verlauf des Auftrags (geplant, verschoben, entfernt).

### Außerdem
- Im Auftrag unter „Auftragsdaten“: Termin und Dauer direkt eintragen.
- Auftragstafel: Karten zeigen den Termin, Klick darauf öffnet die Woche im Kalender.
- Übersicht: neue Karte „Heute in der Werkstatt“ mit allen Terminen des Tages.

---

## 1.0.1 – 16.10.2026
### Behoben
- Die automatische Aktualisierung sucht neue Versionen im richtigen GitHub-Projekt.

---

## 1.0.0 – 16.10.2026
Erste Version von Werkstatt Sauter. Sie baut auf der bewährten Buchhaltung von Reparatur Service Bredin auf
(Rechnungen, KVA, Mahnwesen, Lager, Einkauf, Bank, Kasse, Fixkosten, Finanzen, DATEV, Datenschutz) und ist auf
die Kfz-Werkstatt umgestellt.

### Eigenständig
- Eigener Programmname, eigenes Logo, eigener Datenordner (`%LOCALAPPDATA%\Werkstatt-Sauter\Daten`) und eigene
  Updates. Läuft das Programm auf demselben PC wie die RSB-Buchhaltung, bleiben die Daten vollständig getrennt.
- Startet ohne Kundendaten. Firmendaten unter *Einstellungen → Firmendaten* eintragen.

### Aufträge
- Aus „Reparaturaufträgen“ werden **Aufträge** (Nummern `AU-Jahr-Nummer`).
- **Fahrzeugdaten:** Fahrzeug (Marke, Modell, Motor), Kennzeichen, FIN, Kilometerstand, Erstzulassung,
  HU/TÜV fällig. Kennzeichen erscheint auf der Tafel und ist über die Suche (Strg+K) auffindbar.
- **Mehrere Leistungen je Auftrag** zum Ankreuzen: Ölwechsel, Fehlerspeicher auslesen, Reifenwechsel,
  Reifenmontage, Auswuchten, Inspektion, Bremsen, Sonstiges (unter *Firmendaten → Leistungsarten* änderbar).
- **Checkliste je Auftrag:** Für jede angekreuzte Leistung erscheinen die passenden Arbeitsschritte zum Abhaken.
  Jeder Haken speichert sofort Zeitpunkt und Benutzer und steht im Verlauf. Eigene Schritte lassen sich ergänzen.
  Die Tafel zeigt den Fortschritt (z. B. „4/18 erledigt“).
- Vorlagen der Checklisten unter *Einstellungen → Annahme & Abholung → Checklisten je Leistung*.
- Annahme- und Abholschein, Kundennachrichten, Garantie- und Abholtexte auf Fahrzeuge umgestellt. Abgegebene
  Gegenstände zum Ankreuzen: Schlüssel, Zweitschlüssel, Fahrzeugschein, Serviceheft, Räder …
- KVA-Pauschale je Fahrzeugart (PKW, SUV/Van, Transporter, Motorrad).
