# Versionsprotokoll

Alle Versionen der Buchhaltung von Reparatur Service Bredin mit Neuerungen, Änderungen, Fehlerbehebungen und
technischen Hinweisen. Die neueste Version steht oben.

**So funktionieren Versionen**
- Die Versionsnummer steht unten links im Programm und unter *Einstellungen → Programm & Updates*.
- Aufbau: `Haupt.Funktion.Korrektur`. Die mittlere Zahl steigt bei neuen Funktionen, die letzte Zahl bei
  reinen Fehlerbehebungen.
- Ab Version 0.4.0 gibt es jede Version als `Werkstatt-Sauter.exe` unter
  [GitHub → Releases](https://github.com/ReparaturServiceBredin/Werkstatt/releases).
  Das Programm installiert neue Versionen selbst und erstellt vorher ein Backup.
- Ihre Daten im Ordner `Daten` bleiben bei jedem Update erhalten. Neue Datenbankfelder ergänzt das Programm beim
  Start selbst.
- Der Abschnitt einer Version erscheint im Programm als Hinweistext, wenn diese Version zum Update bereitsteht.

| Version | Datum | Schwerpunkt |
|---|---|---|
| 0.24.1 | 16.10.2026 | Dunkelmodus: alle Texte gut lesbar |
| 0.24.0 | 16.10.2026 | Fixkosten und Finanzübersicht |
| 0.23.1 | 16.10.2026 | Technik: feste Versionen, sichere Dateinamen, Pfadprüfung, Entwickler-Regeln |
| 0.23.0 | 16.10.2026 | Fester Datenordner – egal, von wo das Programm gestartet wird |
| 0.22.2 | 16.10.2026 | Sicherung wiederherstellen mit Inhaltsvorschau, Hinweis bei OneDrive |
| 0.22.1 | 16.10.2026 | Fehlerbehebung: Einstellungen werden nie mehr leer angezeigt |
| 0.22.0 | 16.10.2026 | Neue Navigation: Gruppen, Schnellsuche (Strg+K), Glocke, Einstellungen mit Suche, Dunkelmodus |
| 0.21.0 | 16.10.2026 | KVA-Pauschale je Gerätetyp, freiwillige Garantie ab Abholung, Löschvorschau, Kassen-Fehlbetrag |
| 0.20.0 | 16.10.2026 | Datenschutz: Löschfristen, Auskunft, Löschprotokoll, Verzeichnis |
| 0.19.0 | 16.10.2026 | Kassenbuch mit Tagesabschluss, DATEV-Export |
| 0.18.0 | 16.10.2026 | E-Rechnung: ZUGFeRD/Factur-X und XRechnung erzeugen und empfangen |
| 0.17.0 | 15.10.2026 | Lieferanten, Bestellungen, Wareneingang, Eingangsrechnungen |
| 0.16.0 | 15.10.2026 | Lager: Bestand, Reservierung, Mindestbestand, Inventur, Lagerwert |
| 0.15.0 | 15.10.2026 | Garantie, Geräte-Wiedererkennung per SN/IMEI, Garantiefälle |
| 0.14.0 | 15.10.2026 | Kundenbenachrichtigung, Spalte „Wartet auf Teil“, Abhol-Erinnerungen |
| 0.13.0 | 15.10.2026 | Annahme- und Abholschein mit digitaler Unterschrift, Handy per QR-Code |
| 0.12.0 | 15.10.2026 | Zahlungen, offene Posten, Bankabgleich, Mahnwesen |
| 0.11.0 | 15.10.2026 | GoBD-Grundlagen: Gutschrift, Pflichtangaben, Änderungsprotokoll, Aufbewahrung |
| 0.10.0 | 15.10.2026 | Automatische E-Mail-Historie je Kunde |
| 0.9.1 | 15.10.2026 | IMAP-Abruf auch mit STARTTLS (Port 143), Verbindungstest |
| 0.9.0 | 15.10.2026 | Leihgeräte: Ausgabe, Rückgabe, Schadensfall, Abrechnung |
| 0.8.0 | 15.10.2026 | Auftrags-Detailansicht: KVA verknüpfen, Fotodokumentation, Verlauf |
| 0.7.0 | 15.10.2026 | Gesendet-Ordner per IMAP, Katalog-Übernahme, ausführliche Beschreibungen |
| 0.6.1 | 15.10.2026 | Vertragsrechnungen vollautomatisch |
| 0.6.0 | 15.10.2026 | Verträge & Lizenzen (Wertgarantie, ESET, MSP) mit wiederkehrenden Rechnungen |
| 0.5.1 | 15.10.2026 | Versionsprotokoll im Programm |
| 0.5.0 | 14.10.2026 | Kein Konsolenfenster, kein Passwortzwang |
| 0.4.0 | 14.10.2026 | EXE-Datei mit automatischen Updates |
| 0.3.0 | 14.10.2026 | Reparaturaufträge (Tafel) und Kostenvoranschlag |
| 0.2.0 | 14.10.2026 | Anfragen aus dem Kontaktformular |
| 0.1.0 | 14.10.2026 | Grundversion: Kunden, Leistungen, Rechnungen, E-Mail |

---

## 0.24.1 – 16.10.2026
Fehlerbehebung Dunkelmodus.

### Behoben
- **Unterschriftsseite (Annahme- und Abholschein):** Die Kästen „Datenschutz und Datensicherung“ und
  „Abholbedingungen“ hatten im Dunkelmodus einen hellen Hintergrund mit heller Schrift. Der Text war dadurch nicht
  lesbar.
- **Weitere feste Farben** passen sich jetzt ebenfalls an:
  - Warnhinweise, Rahmen von Meldungen
  - Garantie- und Teile-Hinweise auf der Auftragstafel
  - Hinweis „Ungespeicherte Änderungen“
- **Auftragstafel:** Die Spaltenköpfe „In Arbeit“ und „Erledigt“ samt Zählern sind in Hell und Dunkel kontrastreicher.

### Geprüft
- Alle Seiten in Hell und Dunkel wurden automatisch auf Lesbarkeit geprüft, jeder sichtbare Text gegen seinen
  tatsächlichen Hintergrund. Kein Text liegt mehr unter dem Kontrast 4,5:1 (Fließtext), außer den kleinen Zählern
  der Auftragstafel, die jetzt deutlich besser lesbar sind.

---

## 0.24.0 – 16.10.2026
Fixkosten und Finanzübersicht. Vor der Erweiterung der Datenbank legt das Programm automatisch eine Sicherung an.
Alle bisherigen Daten bleiben unverändert.

### Neu: Fixkosten (*Buchhaltung → Fixkosten*)
- Wiederkehrende Ausgaben wie Miete, Strom, Internet, Telefon, Versicherungen, Leasing, Software-Abos, Kfz,
  Steuerberater und Kammerbeiträge.
- **Felder:**
  - Bezeichnung, Kategorie (einstellbar), Betrag netto/brutto mit Steuersatz
  - Rhythmus (monatlich, vierteljährlich, halbjährlich, jährlich) und Fälligkeitstag (31 = Monatsende)
  - Beginn, Ende, Kündigungsfrist, Zahlungsart
  - Empfänger bzw. Lieferant, Suchbegriff für den Kontoauszug, Notiz, Vertrag als PDF
- **Betragsänderungen mit „gültig ab“:** Der alte Betrag bleibt für vergangene Zeiträume gültig, etwa bei einer
  Mieterhöhung ab 01.01.2027. Der Verlauf wird angezeigt. Ein noch nicht gültiger Betrag lässt sich wieder entfernen.
- **Übersicht:** Summe pro Monat und pro Jahr, jeweils nach Kategorie. Jährliche und vierteljährliche Kosten werden
  anteilig umgerechnet.
- **Bankabgleich:**
  - Abbuchungen werden der passenden Fixkosten-Position vorgeschlagen (Empfänger bzw. Suchbegriff und Betrag). Sie
    bestätigen per Klick; eine Zuordnung lässt sich wieder lösen.
  - Fehlt eine erwartete Zahlung in einem Monat mit eingelesenem Kontoauszug oder weicht der Betrag ab, wird das
    markiert: in der Fixkosten-Liste und im Bankabgleich.
- **Hinweise** auf bald endende Verträge und nahende Kündigungsfristen (Standard: 30 Tage vorher), auch in der
  Glocke.
- Eingangsrechnungen lassen sich einer Fixkosten-Position zuordnen, z. B. die Jahresrechnung des Steuerberaters.
  Sie zählen dann nur einmal.

### Neu: Finanzübersicht (*Buchhaltung → Finanzen*)
- **Zeitraum:** Monat, Quartal, Halbjahr, Jahr oder frei wählbar. Dazu Schnellauswahl und Pfeile zum Blättern.
- **Kennzahlen:**
  - Umsatz netto und brutto (Rechnungen minus Stornos und Gutschriften), aufgeteilt in Reparaturen &
    Dienstleistungen, Artikelverkauf, Leihgebühren und KVA-Gebühren
  - Zahlungseingänge; Einnahmen umschaltbar „nach Rechnungsdatum“ bzw. „nach Zahlungseingang“
  - Ausgaben: Fixkosten, Wareneinsatz, sonstige Eingangsrechnungen, Kassenausgaben, jeweils nach Kategorie
  - Rohertrag und Ergebnis
  - Umsatzsteuer, Vorsteuer und Zahllast als Orientierung (bei Kleinunternehmer ausgeblendet)
  - Offene Forderungen und Verbindlichkeiten zum Stichtag
  - Aufträge, Ø Auftragswert, Ø Marge
- **Fixkosten im Monat:** anteilig (Standard) oder im Fälligkeitsmonat.
- **Diagramme:** Einnahmen und Ausgaben je Monat, Ergebnisverlauf, Ausgaben nach Kategorie. Darunter eine
  Monatstabelle mit Summenzeile.
- **Vergleich** mit Vorjahreszeitraum oder Vorperiode, absolut und in %.
- **Break-even** mit Fortschrittsbalken und **Vorschau** der nächsten 3 Monate.
- **Jede Zahl ist anklickbar** und zeigt die Belege dahinter.
- **Export** als PDF und CSV (öffnet in Excel).
- Deutlicher Hinweis: betriebswirtschaftliche Übersicht, nicht die steuerliche Gewinnermittlung bzw. EÜR.

### Einstellungen
- Unter *Einstellungen → Einkauf*: Kategorien für Fixkosten, Kostenarten für den Wareneinsatz und die Vorlaufzeit
  für Hinweise.

### Technisch
- Neue Tabellen `fixkosten`, `fixkosten_betraege` (Beträge sind gegen Überschreiben geschützt) und
  `hinweise_gelesen`.
- Neue Felder `bank_umsaetze.fixkosten_id/fixkosten_monat` und `eingangsrechnungen.fixkosten_id`.
- Vertrags-PDFs liegen im Datenordner unter `belege/fixkosten` und sind damit im Backup.
- Datumswerte der neuen Funktionen werden ausdrücklich in Europe/Berlin berechnet.

---

## 0.23.1 – 16.10.2026
Technische Vorbereitung für den späteren Betrieb unter Linux/Docker. An der Bedienung ändert sich nichts.

### Neu
- **Datenprüfung:** Neuer Abschnitt „Gespeicherte Dateipfade“. Er prüft, dass alle in der Datenbank gespeicherten
  Dateipfade relativ zum Datenordner sind, nur `/` enthalten (also unter Windows und Linux lesbar) und dass
  Fotos, Kassenbelege und DATEV-Exporte vorhanden sind.

### Geändert
- Präfixe und Nummernformat werden beim Speichern auf Zeichen geprüft, die in Dateinamen unter Windows oder Linux
  nicht erlaubt sind (`\ / : * ? " < > |`).
- Dateinamen für Belege, Mahnungen und Annahme-/Abholscheine werden immer gültig gebildet. Bestehende Namen bleiben
  unverändert.
- Alle Abhängigkeiten haben feste, getestete Versionen (`requirements.txt`). Geprüft für Windows (Python 3.12/3.13)
  und Linux.

### Technisch
- Neue Entwickler-Regeln in `docs/ENTWICKLUNG.md`: keine Windows-Pfade oder -Bibliotheken außerhalb der dafür
  vorgesehenen Module, alle Daten im Datenordner, Konfiguration über Umgebung, Zeitzone und Zeichensatz ausdrücklich.
- `tests/test_regeln.py` prüft diese Regeln bei jedem Testlauf.

---

## 0.23.0 – 16.10.2026
Ein fester Datenordner – nie mehr getrennte Datenbestände.

### Geändert
- Bisher lag der Ordner `Daten` neben der EXE bzw. dem Programmordner. Wurde das Programm von einer anderen Stelle
  gestartet (Downloads, Desktop, start.bat), entstand dort ein neuer, leerer Datenbestand.
- **Jetzt liegen alle Daten an einem festen Ort**, egal von wo das Programm gestartet wird. Unter Windows ist das
  `%LOCALAPPDATA%\Werkstatt-Sauter\Daten`; der Ordner wird nicht von OneDrive synchronisiert.
- **Automatische Übernahme beim ersten Start:**
  - Das Programm sucht die bisherigen Datenordner (neben dem Programm, Desktop, Downloads, Dokumente, OneDrive) und
    übernimmt den mit den meisten Daten.
  - Es kopiert, verschiebt nicht. Danach prüft es, ob jede Tabelle gleich viele Datensätze hat und keine Datei fehlt.
    Stimmt etwas nicht, verwirft es die Kopie und arbeitet mit dem bisherigen Ordner weiter.
  - Der alte Ordner bleibt mit einer Notiz liegen.
  - Auf der Übersicht erscheint einmal ein Hinweis, auch zu weiteren gefundenen Ordnern.
- Der Datenordner steht unter *Einstellungen → Backup* und ist über das Symbol neben der Uhr erreichbar.
- Mit der Umgebungsvariable `RSB_DATEN` lässt sich der Ort weiterhin selbst festlegen (z. B. für Docker).

---

## 0.22.2 – 16.10.2026
Neu: Sicherungen selbst wiederherstellen.

### Neu
- *Einstellungen → Backup → Sicherung wiederherstellen* listet jede Sicherung mit Inhalt: Kunden, Aufträge,
  Artikel, Belege, Fotos und Firmendaten. Ein Klick spielt die gewählte Sicherung ein.
  - Vorher wird der aktuelle Stand **vollständig** gesichert (`vor_wiederherstellung_….zip`). Diese Sicherung erscheint
    danach ebenfalls in der Liste und lässt sich zurückspielen.
  - Fotos und PDFs werden ergänzt, nie gelöscht. Das Programm startet dafür kurz neu.
  - „Auch andere Datenordner suchen“ findet Datenordner unter Desktop, Downloads, Dokumente und OneDrive, etwa wenn
    das Programm früher an einem anderen Ort lag.
- Liegt der Datenordner in OneDrive, erscheint ein Hinweis mit Empfehlung. OneDrive kann eine geöffnete Datenbank
  durch eine ältere Fassung ersetzen.
- DATEV-Exporte (`Daten/exporte`) sind jetzt in jedem Backup enthalten.

---

## 0.22.1 – 16.10.2026
Fehlerbehebung.

### Behoben
- Konnte einer der Zähler in Menü oder Glocke nicht ermittelt werden, zeigte das Programm alle Einstellungen leer an
  (z. B. Firmenanschrift, IMAP). Die gespeicherten Werte waren dabei nicht verloren. Jetzt werden die Einstellungen
  immer aus der Datenbank angezeigt; ein ausgefallener Zähler zeigt nur 0.

### Technisch
- Beim Beenden über das Symbol neben der Uhr und vor dem Neustart nach einem Update werden alle Änderungen fest in
  die Datenbankdatei geschrieben (WAL-Checkpoint). Das schützt besonders, wenn der Programmordner per OneDrive
  synchronisiert wird.

---

## 0.22.0 – 16.10.2026
Neue, übersichtlichere Navigation. Keine Funktion entfällt. Alte Adressen und Lesezeichen leiten auf die neue Stelle
weiter.

### Seitenleiste
- **Gruppen:**
  - Werkstatt: Anfragen, Reparaturaufträge, Leihgeräte
  - Kunden: Kunden, Verträge & Lizenzen
  - Verkauf: Rechnungen, Leistungen & Artikel
  - Einkauf & Lager: Lager, Einkauf
  - Buchhaltung: Bankabgleich, Kassenbuch, DATEV-Export
  - *Einstellungen* steht fest unten.
- **Bedienung:**
  - Gruppen per Klick einklappbar. Der Zustand wird je Benutzer gemerkt; die Gruppe der geöffneten Seite ist immer
    offen.
  - Die Seitenleiste lässt sich auf Symbole verkleinern, mit Namen als Tooltip.
  - Am Handy öffnet sie sich über das Menü-Symbol ☰.
- **Symbole:** einheitlich ([Lucide](https://lucide.dev), lokal eingebunden, ISC-Lizenz).
- **Zähler:** neue Anfragen, offene Aufträge, Artikel unter Mindestbestand (dezent). Überfällige Rechnungen und
  überfällige Leihgeräte sind rot.

### Zusammengefasste Seiten
- **Rechnungen**, mit Reitern: Rechnungen | Kostenvoranschläge | Offene Posten | Mahnwesen.
- **Einkauf**, mit Reitern: Bestellungen | Lieferanten | Eingangsrechnungen.

### Kopfzeile
- **Brotkrumen**, z. B. *Verkauf › Rechnungen › Offene Posten*.
- **Schnellsuche** (Strg+K): Seiten, Einstellungen und einzelne Felder, Kunden, Aufträge, Rechnungen/KVAs,
  Artikel, Leihgeräte. Dazu Schnellaktionen „Neuer Auftrag“, „Neuer Kunde“, „Neuer KVA“, „Neue Rechnung“.
- **+ Neu:** Auftrag, Kunde, KVA, Rechnung, Leihgerät ausgeben. Für „Leihgerät ausgeben“ gibt es eine neue Seite zur
  Auswahl des Auftrags.
- **Glocke** statt Menüpunkt „Benachrichtigungen“: die letzten Benachrichtigungen, „als gelesen markieren“ und ein
  Link zur Übersicht.
- **Hell/Dunkel** umschaltbar, wird gemerkt.

### Einstellungen
- Links eine Unternavigation in Gruppen, rechts der Inhalt:
  - Unternehmen
  - Verkauf & Werkstatt
  - Kommunikation
  - Einkauf & Buchhaltung
  - System
  - Verwaltung & Prüfung: Textbausteine, Datenschutz-Übersicht, Protokoll, Datenprüfung, Verfahrensdokumentation,
    Versionsprotokoll (früher eigene Menüpunkte)
- **Suchfeld:** findet auch einzelne Felder, springt hin und hebt sie kurz hervor.
- Lange Seiten sind in einklappbare Abschnitte gegliedert.
- Der Knopf „Speichern“ bleibt unten sichtbar.
- Beim Verlassen mit ungespeicherten Änderungen fragt das Programm nach.

### Neue Adressen (alte leiten weiter)
| alt | neu |
|---|---|
| `/dokumente` | `/verkauf/rechnungen?typ=alle` (alle Belege wie bisher) |
| `/dokumente?typ=rechnung` | `/verkauf/rechnungen` |
| `/dokumente?typ=kva` | `/verkauf/kostenvoranschlaege` |
| `/offene-posten` | `/verkauf/offene-posten` |
| `/mahnwesen` | `/verkauf/mahnwesen` |
| `/bestellungen` | `/einkauf/bestellungen` |
| `/lieferanten` | `/einkauf/lieferanten` |
| `/eingangsrechnungen` | `/einkauf/eingangsrechnungen` |
| `/einstellungen` | `/einstellungen/firma` |
| `/einstellungen?bereich=…` | `/einstellungen/…` |

- Filter in der Adresse (z. B. `?status=…`) bleiben erhalten.
- Unterseiten wie `/dokumente/123`, `/lieferanten/5` oder `/mahnwesen/erstellen` behalten ihre Adresse.

### Technisch
- Neues Feld `benachrichtigungen.gelesen_am`. Beim ersten Start wird vorher automatisch ein Backup angelegt.
- „Backup jetzt erstellen“ läuft jetzt über `/einstellungen/backup/erstellen`.

---

## 0.21.0 – 16.10.2026
Anpassungen an KVA, Garantie, Löschfristen und Kassenbuch. Beim ersten Start legt das Programm vor der Umstellung der
Datenbank automatisch ein Backup an (`Daten/backups/vor_update_…`). Es gehen keine Daten verloren.

**Nicht geändert** (wird noch mit dem Steuerberater geklärt): DATEV-Kontenzuordnung, TSE, Aufbewahrungsfristen für
Rechnungen, Buchungsbelege, Geschäftsbriefe und E-Mail-Verlauf.

### KVA-Pauschale
- Pauschale je **Gerätetyp** unter *Einstellungen → Annahme & Abholung → KVA-Pauschalen*, eine Zeile je Typ
  (`Gerätetyp = Betrag`). Vorgabe: Laptop / PC / All-in-One 29,00 €, Smartphone / Tablet 19,00 €, Sonstige Geräte
  29,00 €. Weitere Typen einfach als neue Zeile ergänzen.
- Im Auftrag den Gerätetyp wählen. Die Pauschale wird vorgeschlagen und lässt sich je Auftrag ändern oder mit
  „kostenlos“ ganz streichen.
- **KVA angenommen:** Die Pauschale wird verrechnet, sie entfällt.
- **KVA abgelehnt:** Es öffnet sich sofort ein **Rechnungsentwurf** mit der Position
  „Kostenvoranschlag / Fehlerdiagnose – Gerät: …“. Die Leistung wird bei Bedarf unter *Leistungen und Artikel* angelegt.
- Auf dem Annahmeschein steht ein **bearbeitbarer Hinweistext** mit dem Betrag. Er ist vor der Unterschrift deutlich
  sichtbar (Platzhalter `{KVA-Gebühr}`).

### Freiwillige Garantie
- Standard 12 Monate **ab Abholung**. Abweichungen je Auftrag oder Position, auch „keine Garantie“ (0).
- Das **Garantieende** wird bei der Abholung im Auftrag gespeichert und angezeigt. Bereits abgeholte Aufträge bekommen
  es beim ersten Start einmalig nachgetragen. Die Garantieprüfung über SN/IMEI nutzt dieses gespeicherte Datum.
- Ein **bearbeitbarer Garantietext** steht auf Rechnung und Abholschein, mit Firmenname und Anschrift aus den
  Firmendaten. Platzhalter: `{Garantiedauer}`, `{Garantieende}`, `{Firmenname}`, `{Firmenanschrift}`. Der Text
  trennt die freiwillige Garantie klar von der gesetzlichen Gewährleistung.
- Wird die Rechnung vor der Abholung geschrieben, steht dort „bis Ablauf von … nach Abholung“ statt eines Datums.

### Löschfristen (nur Daten ohne steuerliche Aufbewahrungspflicht)
| Daten | Frist |
|---|---|
| Gerätezugangsdaten | sofort und endgültig bei Abholung, Abschluss oder Stornierung (Löschung wird ohne Inhalt protokolliert) |
| Interessenten | 6 Monate nach Anlage bzw. letztem Kontakt |
| Fotos und Annahme-/Abholscheine | 3 Jahre ab Ende des Kalenderjahres der Abholung (Abholung 15.10.2026 → ab 01.01.2030) |
| Leihprotokolle und -fotos | 3 Jahre ab Ende des Jahres der Rückgabe bzw. des Abschlusses eines Schadensfalls |
| inaktive Kunden | 3 Jahre ab Ende des Jahres des letzten Kontakts (Auftrag, Rechnung, E-Mail); mit Belegen nur Anonymisierung wie bisher |

- **Sperren:** laufende Aufträge, offene Rechnungen, offene Schadensfälle und laufende Garantien verhindern die
  Löschung des Kunden und seiner Fotos.
- **Vorschau:** *Verwaltung → Datenschutz* zeigt „Folgende Daten werden in den nächsten 30 Tagen gelöscht“, jeweils
  mit Status *fällig*, *vorgemerkt*, *gesperrt* (mit Grund) oder *zurückgestellt*.
- **Zurückstellen:** Einzelne Einträge lassen sich mit Begründung zurückstellen, z. B. bei einem Streitfall.
  Optional mit Enddatum, jederzeit aufhebbar.
- Jede Löschung steht im Löschprotokoll: was, wann und nach welcher Frist, ohne Inhalte.
- Bei Leihvorgängen werden Zustandsbeschreibungen, Zubehörlisten, Notizen und Fotos entfernt. Leihnummer, Daten
  und Beträge bleiben für Rechnung und Kaution erhalten.

### Kassenbuch
- Der Bestand wird **chronologisch nach Buchungsdatum über die ganze Historie** geprüft, auch bei rückdatierten
  Buchungen. Beispielmeldung: „Kassenbestand wäre am 12.10.2026 um 35,00 € negativ. Wahrscheinlich fehlt eine
  Einnahme oder eine Privateinlage.“
- Die abgelehnte Buchung bleibt vorgemerkt. Mit **„Fehlende Einnahme erfassen“** oder **„Privateinlage buchen“**
  (Datum und Betrag vorbelegt) wird die Lücke geschlossen. Danach bucht das Programm die ursprüngliche Buchung
  automatisch.
- **Privateinlage und Privatentnahme** sind eigene Buchungsarten mit Datum, Betrag, Begründung und fortlaufender
  Nummer, immer ohne Umsatzsteuer.

### Technisch
- Neue Felder: `auftraege.garantie_ende`, `auftraege.geraetetyp`, `leihen.protokoll_geloescht_am`,
  `loeschprotokolle.frist`.
- Neue Tabellen: `loesch_zurueckstellungen`, `loeschfreigaben`. Die zweite hebt den Schutz einer einzelnen Zeile nur
  innerhalb eines Löschlaufs auf.
- SQLite `secure_delete` ist eingeschaltet: Gelöschte Inhalte werden in der Datenbankdatei überschrieben.
- Ältere Datensicherungen enthalten die verschlüsselten Zugangsdaten weiterhin, bis sie selbst gelöscht werden.

---

## 0.20.0 – 16.10.2026
Datenschutz nach DSGVO (Ausbaustufe 10 von 10).

### Neu

**Löschfristen** (*Einstellungen → Datenschutz*):

| Daten | Frist (Vorschlag) |
|---|---|
| Interessenten ohne Auftrag | 6 Monate |
| inaktive Kunden | 3 Jahre ohne Kontakt |
| Eingangs- und Reparaturfotos | 24 Monate nach Abholung |
| Gerätezugangsdaten bei liegengebliebenen Aufträgen | 90 Tage (bei Abschluss ohnehin sofort) |
| E-Mails ohne Belegbezug | 6 Jahre |

**Löschlauf:** Unter *Verwaltung → Datenschutz* sehen Sie, was heute fällig wäre. Mit „Löschlauf jetzt ausführen“
oder automatisch täglich (einschaltbar) wird gelöscht.
- **Aufbewahrungspflichten haben Vorrang:** Ein inaktiver Kunde mit Rechnungen wird anonymisiert, nicht gelöscht.
- Kunden mit offenen Rechnungen, laufenden Verträgen oder offenen Aufträgen bleiben unberührt.
- Bei Fotos verschwindet die Datei. Der Eintrag bleibt als „gelöscht (Löschfrist)“ nachvollziehbar.

**Auskunft nach Art. 15 DSGVO:** Beim Kunden den Knopf **„Auskunft herunterladen“** drücken. Sie bekommen ein ZIP
mit:
- Auskunftsschreiben (Zwecke, Empfänger, Speicherdauer, Rechte)
- allen gespeicherten Daten (JSON)
- Rechnungen, Annahme-/Abholscheinen und Fotos

Gerätezugangsdaten sind nie im Klartext enthalten.

**Löschanfrage (Art. 17):** Beim Löschen eines Kunden „Der Kunde hat die Löschung verlangt“ anhaken. Ins
unveränderliche **Löschprotokoll** kommt, was gelöscht und was bis wann aufbewahrt wird. Dazu gibt es eine
**Bestätigung als PDF** für den Kunden.

**Verzeichnis der Verarbeitungstätigkeiten (Art. 30):** Vorlage, erzeugt aus den tatsächlich gespeicherten Daten
und Ihren Löschfristen. Sie enthält Zwecke, Rechtsgrundlagen, Datenkategorien, Empfänger, Bestand, technische
Maßnahmen und Auftragsverarbeiter, als Seite und als PDF.

### Technisch
- Neue Tabelle `loeschprotokolle` (unveränderlich).
- Der Löschlauf läuft im vorhandenen Hintergrund-Thread einmal täglich, wenn eingeschaltet.

## 0.19.0 – 16.10.2026
Kassenbuch und DATEV-Export (Ausbaustufe 9 von 10).

### Neu

**Kassenbuch** (Menü *Buchhaltung → Kassenbuch*):
- Jede Buchung bekommt eine fortlaufende Nummer, mit Datum, Betrag, Steuersatz, Text, Kostenart (bei Ausgaben)
  und Beleg (Foto/PDF).
- Arten: Einnahme, Ausgabe, Privateinlage, Privatentnahme, Einzahlung auf die Bank, Geld von der Bank,
  Anfangsbestand.
- **Barzahlungen** auf Rechnungen und bar bezahlte Eingangsrechnungen kommen automatisch ins Kassenbuch. Bei einer
  Einnahme können Sie direkt die Rechnung wählen; dann wird gleichzeitig die Zahlung erfasst.
- Buchungen sind **unveränderlich**. Korrekturen gehen nur per **Gegenbuchung** mit Grund. Storniert man eine
  Barzahlung, entsteht die Gegenbuchung automatisch.
- **Der Kassenbestand kann nicht negativ werden.** Eine Buchung, die das verursachen würde, lehnt das Programm mit
  Erklärung ab.
- **Tagesabschluss mit Kassensturz:** gezählten Bestand eintragen oder über das Zählprotokoll (Scheine/Münzen)
  ausrechnen lassen. Eine Differenz wird mit Begründung als eigene Buchung erfasst. Danach ist der Tag gesperrt.
- Druckansicht des Kassenbuchs für jeden Zeitraum.

**DATEV-Export** (Menü *Buchhaltung → DATEV-Export*):
- Zeitraum wählen, Vorschau prüfen, „Export erstellen“. Sie bekommen ein ZIP mit dem **DATEV-Buchungsstapel**
  (EXTF 700) und allen Belegen: Rechnungs-PDFs und -XML, Eingangsrechnungen, Kassenbelege.
- Enthalten sind: Ausgangsrechnungen, Gutschriften, Stornos, Zahlungseingänge, Eingangsrechnungen,
  Zahlungsausgänge und Kassenbuchungen.
- Exportierte Buchungen werden vermerkt und beim nächsten Export nicht erneut ausgegeben. Auf Wunsch geht das doch,
  dann mit Kennzeichnung „erneut“.
- Das Exportprotokoll enthält Zeitraum, Zeitpunkt, Anzahl und Prüfsumme (SHA-256). Exportierte
  Eingangsrechnungen lassen sich nicht mehr ändern.
- *Einstellungen → DATEV:* Berater- und Mandantennummer, SKR03/SKR04, Beginn des Wirtschaftsjahres,
  Debitoren-/Kreditorennummern, abweichende Konten und Konten je Kostenart.

### Wichtig
- Die Kontenzuordnung entspricht den Standardkonten von SKR03/SKR04, z. B. Kleinunternehmer-Erlöse 8195/4185 und
  Wareneingang 3200/5200. **Bitte den ersten Export mit dem Steuerberater durchgehen.**
- **Keine TSE:** Hinweise zur TSE-Pflicht stehen in der Anleitung, Abschnitt 25.

### Technisch
- Neue Tabellen:
  - `kassenbuch`, `kassen_abschluesse` (beide gegen Ändern und Löschen geschützt)
  - `datev_exporte`, `datev_posten`
- Vor der Umstellung wird automatisch gesichert. Die Datenprüfung prüft die lückenlose Nummerierung des
  Kassenbuchs, die Tagesabschlüsse und den Bestand (nie negativ).

## 0.18.0 – 16.10.2026
E-Rechnung (Ausbaustufe 8 von 10).

### Neu

**ZUGFeRD / Factur-X (EN 16931):** Rechnungen, Gutschriften und Stornos an Firmenkunden werden beim Festschreiben
automatisch als ZUGFeRD-PDF archiviert. Das ist ein PDF mit eingebetteter XML im Profil EN 16931 und
PDF/A-3-Kennzeichnung. Für Kleinunternehmer steht in der XML die Steuerbefreiung nach § 19 UStG
(Kategorie „E“), bei Regelbesteuerung die Steuer je Steuersatz.

**Format je Kunde:** Unter *Kunden → Rechnungsformat* gibt es vier Einstellungen:
- automatisch: Firma bekommt ZUGFeRD, Privatkunde PDF
- PDF
- ZUGFeRD
- XRechnung, mit Feld für die **Leitweg-ID**

Eine XRechnung wird als eigene XML-Datei archiviert. Beim E-Mail-Versand hängt das Programm die XML mit an.

**Prüfung vor dem Festschreiben:** Fehlen Stammdaten, wird nicht festgeschrieben und das Programm nennt den Grund auf
Deutsch. Fehlen können:
- Ihre IBAN, Anschrift, Steuernummer bzw. USt-IdNr.
- PLZ/Ort des Kunden
- bei XRechnung: Leitweg-ID, E-Mail des Kunden, Ihre Telefonnummer

Die erzeugte XML wird gegen das offizielle Schema (XSD) und die wichtigsten Rechenregeln der EN 16931 geprüft. Ist sie
ungültig, wird nicht festgeschrieben und auch keine Nummer verbraucht.

**Dokument-Ansicht:** zeigt das Format und bietet „XML herunterladen“ an. Die XML ist mit SHA-256 gesichert und wird
in der Datenprüfung mitgeprüft.

**E-Rechnungen empfangen:** ZUGFeRD-PDFs und XRechnungen (CII oder UBL) beim Hochladen oder aus dem Postfach werden
erkannt. Lieferant, Nummer, Datum, Fälligkeit und Beträge werden übernommen. Den Lieferanten ordnet das Programm über
USt-IdNr., E-Mail oder Namen zu. Mit **„E-Rechnung lesbar anzeigen“** sehen Sie die XRechnung übersichtlich und
können sie **als PDF speichern**.

### Wichtig / ehrlich
- Geprüft wird gegen das XSD und die zentralen Rechenregeln. Die vollständige Schematron- bzw. KoSIT-Prüfung braucht
  einen externen Validator und wird bewusst nicht im Programm gemacht. Für die erste echte XRechnung an eine Behörde
  empfehle ich, sie einmal mit einem Validator zu prüfen, z. B. dem kostenlosen KoSIT-Prüftool.
- Die ZUGFeRD-PDFs tragen PDF/A-3-Kennzeichnung und sRGB-Farbprofil. Eine formale PDF/A-Prüfung (z. B. mit veraPDF)
  habe ich nicht durchgeführt.

### Technisch
- Neue Bibliotheken: `factur-x` und `drafthorse` (Open Source).
- Neue Spalten:
  - `kunden.e_rechnung`, `kunden.leitweg_id`
  - `dokumente.e_format`, `xml_pfad`, `xml_sha256` (geschützt)
  - `eingangsrechnungen.e_daten`
- Vor der Umstellung wird automatisch gesichert. Bereits festgeschriebene Rechnungen bleiben unverändert.

## 0.17.0 – 15.10.2026
Einkauf: Lieferanten, Bestellungen und Eingangsrechnungen (Ausbaustufe 7 von 10).

### Neu

Im Menü gibt es die neue Gruppe **Einkauf**.

**Lieferanten:** Erfasst werden:
- Name, Kontakt, Webshop
- Ihre Kundennummer beim Lieferanten
- Zahlungsbedingungen, Zahlungsziel, Lieferzeit
- IBAN, USt-IdNr. und Kreditorennummer (für den späteren DATEV-Export)

**Bezugsquellen je Artikel:** Ein Artikel kann mehrere Lieferanten haben, jeweils mit EK, Lieferanten-Artikelnummer
und Lieferantengarantie. Der günstigste ist markiert und wird beim Bestellen vorgeschlagen. Wird ein EK als
Einkaufspreis übernommen, berechnet das Programm die Marge neu. Unter der Mindestmarge (Standard 30 %) erscheint eine
Warnung.

**Bestellungen:**
- Aus dem Bestellvorschlag des Lagers (je Lieferant eine Bestellung)
- Aus dem Auftrag mit „Teil für diesen Auftrag bestellen“
- Von Hand

Bestellungen gibt es als PDF und per E-Mail an den Lieferanten. Der Status läuft von „Entwurf“ über „bestellt“ und
„teilweise geliefert“ bis „geliefert“. Ist ein Teil für einen Auftrag bestellt, wandert der Auftrag in die Spalte
„Wartet auf Teil“. Auf der Karte stehen dann Bestellung und Liefertermin.

**Wareneingang:** In der Bestellung die gelieferten Mengen (und ggf. den neuen EK) eintragen. Das Programm macht dann:
- bucht lagerführende Artikel ein und aktualisiert den Einkaufspreis
- reserviert Teile für Aufträge dort und vermerkt sie im Verlauf
- setzt den Auftrag wieder auf „In Arbeit“, wenn alles da ist

Die Lieferantengarantie wird je Lieferung festgehalten. Im Auftrag sehen Sie beim Material Lieferant und
Garantie-Ende.

**Eingangsrechnungen:**
- PDF, Bild oder XML hochladen, oder **aus dem Postfach übernehmen**. Das Postfach wird dabei nur gelesen, nichts
  wird verschoben.
- Felder: Lieferant, Rechnungsnummer, Datum, Netto/Steuer/Brutto (das Programm rechnet fehlende Werte aus),
  Fälligkeit (automatisch aus dem Zahlungsziel), Kostenart, Bestellung.
- Die Originaldatei wird unverändert mit SHA-256 abgelegt.
- Löschen geht nicht, nur Stornieren mit Grund. Änderungen stehen im Änderungsprotokoll.
- Doppelt erfasste Rechnungen (gleiche Nummer oder gleiche Datei) werden abgelehnt.

**Bankabgleich für Ausgänge:** Abbuchungen lassen sich jetzt Eingangsrechnungen zuordnen. Es gibt einen Vorschlag
über die Rechnungsnummer im Verwendungszweck oder über Betrag und Lieferant. Danach gilt die Rechnung als bezahlt.

**Einstellungen → Einkauf:** Mindestmarge, Nummernpräfixe, Kostenarten und der Postfach-Ordner für Rechnungen.

### Technisch
- Neue Tabellen:
  - `lieferanten`, `artikel_lieferanten`
  - `bestellungen`, `bestell_positionen`
  - `wareneingaenge` (geschützt)
  - `eingangsrechnungen` (Datei geschützt, nicht löschbar)
  - `er_zahlungen`
- Neue Spalte `bank_umsaetze.er_zahlung_id`. Vor der Umstellung wird automatisch gesichert.
- Die Datenprüfung prüft auch die Originaldateien der Eingangsrechnungen und die Nummernkreise BE und ER.

## 0.16.0 – 15.10.2026
Lagerverwaltung (Ausbaustufe 6 von 10).

### Neu

**Lagerführende Artikel:** In *Leistungen & Artikel* den Haken „lagerführend“ setzen. Dazu gibt es diese Felder:
- Mindestbestand, Lagerort
- EAN und Herstellernummer
- „Kompatibel mit“, z. B. „iPhone 13, iPhone 13 Pro“; danach kann man suchen

**Bestand nur über Buchungen:** Zugang, Abgang und Korrektur werden immer mit Grund, Benutzer und Zeitpunkt gebucht.
Lagerbewegungen sind unveränderlich; Fehler berichtigt eine Korrekturbuchung. Den Bestand überschreibt das Programm
nie direkt.

**Material zum Auftrag:**
- Im Auftrag gibt es den Reiter **„Material“**. Dort Ersatzteile reservieren oder „Lagerartikel aus dem KVA
  übernehmen“.
- Beim Erledigen wird das Material ausgebucht.
- Beim Storno der Rechnung oder mit „zurückbuchen“ kommt es wieder ins Lager.
- Bei Garantiefällen zählen die ausgebuchten Teile zum Einkaufspreis automatisch zu den internen Kosten.

**Unter Mindestbestand:** Die Warnliste steht unter *Lager → Unter Mindestbestand*, mit Zähler im Menü.
**„Bestellvorschlag erstellen“** zeigt einen Vorschlag zum Drucken oder als CSV. Er füllt auf das Doppelte des
Mindestbestands auf.

**Inventur:**
1. Stichtag wählen. Gezählt wird am PC, auf der ausgedruckten Zählliste oder per QR-Code am Handy.
2. Abschließen. Die Differenzen werden als Inventurbuchung gebucht.
3. Das Inventurprotokoll (PDF) wird unverändert mit SHA-256 archiviert.

**Lagerwert zum Stichtag** zum Einkaufspreis: *Lager → Lagerwert*.

**Datenprüfung** prüft zusätzlich, ob der Lagerbestand der Summe der Buchungen entspricht. Sie prüft auch die PDFs
von Annahmescheinen und Inventuren.

### Technisch
- Neue Tabellen:
  - `lagerbewegungen` (gegen Ändern und Löschen geschützt)
  - `lager_reservierungen`
  - `inventuren`, `inventur_positionen` (nach Abschluss geschützt)
  - `inventur_zugaenge`
- Neue Artikel-Spalten. Vor der Umstellung wird automatisch gesichert.

## 0.15.0 – 15.10.2026
Garantie und Gewährleistung (Ausbaustufe 5 von 10).

### Neu

**Garantie je Reparatur:** Den Standard (z. B. 6 oder 12 Monate) stellen Sie unter
*Einstellungen → Annahme & Abholung* ein. Abweichen können Sie an drei Stellen:
- im Auftrag
- je Rechnungsposition (kleines Feld „Garantie … Monate“)
- als Vorschlag beim Artikel in *Leistungen & Artikel*

Die Garantie steht auf der Rechnung und auf dem Abholschein, jeweils mit dem Satz: „Ihre gesetzlichen
Gewährleistungsrechte bleiben davon unberührt.“ Sie beginnt mit der Abholung.

**Gerät schon einmal hier?** Bei der Seriennummer/IMEI prüft das Programm sofort frühere Aufträge, auch wenn die
Schreibweise mit Leerzeichen oder Bindestrichen abweicht. Es zeigt:
- Datum, Fehler und Garantiestand (läuft / abgelaufen)
- Links zu Auftrag, Fotos und Rechnung

Läuft die Garantie noch, ist der Hinweis gelb.

**Garantiefall:** Im Hinweis auf „als Garantiefall zu RA-…“ klicken. Der neue Auftrag wird dann so behandelt:
- Er ist mit dem ursprünglichen Auftrag verknüpft und standardmäßig kostenlos.
- Beim Erledigen entsteht keine Rechnung, und es gibt keine KVA-Rückfrage.
- Interne Kosten (Teile, Zeit) erfassen Sie am Auftrag.

Bei Bedarf erstellt „Rechnung jetzt erstellen“ trotzdem eine Rechnung.

### Hinweis
Lieferantengarantie auf eingekaufte Teile folgt mit Lieferanten und Bestellungen (Ausbaustufe 7).

### Technisch
- Neue Spalten in `auftraege` (`auftragsart`, `garantie_bezug_id`, `garantie_monate`, `interne_kosten`,
  `interne_kosten_notiz`), `positionen.garantie_monate`, `artikel.garantie_monate`. Vor der Umstellung wird
  automatisch gesichert.

## 0.14.0 – 15.10.2026
Kundenbenachrichtigung (Ausbaustufe 4 von 10).

### Neu

**Nachricht an den Kunden bei Statuswechseln:** Das Programm schlägt bei diesen Ereignissen eine E-Mail vor:
- Auftrag angenommen
- Kostenvoranschlag festgeschrieben (entfällt automatisch, wenn Sie den KVA direkt per E-Mail senden)
- Warten auf Ersatzteil
- Gerät fertig zur Abholung

**Vorschau vor jedem Versand:** Der Vorschlag erscheint oben im Auftrag, auf der Tafel und unter
*Verkauf → Benachrichtigungen*. Sie können Empfänger, Betreff und Text ändern, dann **„Jetzt senden“** oder
**„Diesmal nicht senden“**. Gesendete Mails stehen in der E-Mail-Historie des Kunden und im Verlauf des Auftrags.

**Abhol-Erinnerungen:** Ist ein Gerät fertig, aber nicht abgeholt, schlägt das Programm Erinnerungen vor. Standard ist
nach 7, 14 und 30 Tagen. Abgeholt gilt ein Gerät durch den Abholschein oder den Knopf **„abgeholt“**.

**Neue Spalte „Wartet auf Teil“** auf der Tafel. Auf der Karte stehen das Ersatzteil und das erwartete Lieferdatum.

**Vorlagen:** Unter *Einstellungen → Benachrichtigungen* stellen Sie je Anlass ein:
- an/aus
- Betreff und Text mit Platzhaltern: {Anrede}, {Kundenname}, {Auftragsnummer}, {Gerät}, {Betrag}, {Öffnungszeiten},
  {Fertig bis}, {Firma}

Dort tragen Sie auch Ihre Öffnungszeiten ein.

**SMS:** Die Schnittstelle ist vorbereitet. Ein Anbieter ist noch nicht angebunden.

### Technisch
- Neue Tabelle `benachrichtigungen` und neue Spalten `wartet_teil_seit`, `teil_info`, `teil_erwartet` in `auftraege`.
  Vor der Umstellung wird automatisch gesichert.
- `rsb/sms.py`: Basisklasse `SmsAnbieter` für einen späteren Anbieter.

## 0.13.0 – 15.10.2026
Annahmeschein mit digitaler Unterschrift (Ausbaustufe 3 von 10).

### Neu

**Mehr Angaben bei der Annahme:** Im Auftrag gibt es jetzt:
- Zustand bei Eingang
- Zubehör als Checkliste
- Kosten-Obergrenze (Reparatur ohne Rückfrage bis zu diesem Betrag)
- „KVA gewünscht“ und eine Gebühr für den Fall, dass der KVA abgelehnt wird
- voraussichtliche Fertigstellung

**Gerätezugang:** PIN, Passwort oder Entsperrmuster lassen sich hinterlegen. Fürs Muster gibt es ein Punkte-Raster
zum Antippen. Alternativ: „Kunde gibt den Zugang bei Bedarf telefonisch durch“.
- Die Daten werden verschlüsselt gespeichert und nie gedruckt.
- Jede Anzeige wird im Verlauf vermerkt.
- Nach Abschluss oder Abholung löscht das Programm sie automatisch.

**Annahmeschein und Abholschein:** Im Auftrag gibt es den neuen Reiter „Annahme / Abholung“. Der Kunde unterschreibt
direkt am PC oder Tablet mit Finger, Stift oder Maus, oder auf dem Handy über einen QR-Code.
- Das PDF mit Unterschrift, Zeitpunkt (Serverzeit) und Eingangsfotos wird unverändert archiviert und mit SHA-256 gesichert.
- Danach lässt es sich ausdrucken oder per E-Mail senden.
- Für die Unterschrift auf Papier gibt es eine Vorschau ohne Unterschrift.
- Der Abholschein bestätigt „vollständig und funktionsfähig erhalten“ und trägt das Abholdatum ein.

**Fotos mit dem Handy:** Im Reiter Fotos erzeugt „Fotos mit dem Handy (QR-Code)“ einen 30 Minuten gültigen Link. Die
Fotos landen direkt im Auftrag.

**Abgelehnter KVA:** Ist eine Gebühr vereinbart, enthält der Rechnungsentwurf nur diese Gebühr statt der KVA-Positionen.

**Einstellungen → Annahme & Abholung:** Hier pflegen Sie:
- Zubehör-Liste
- Gebühren-Vorschlag
- Datenschutz-Hinweis
- Abholbedingungen
- Text des Abholscheins
- Freigabe fürs WLAN

### Wichtig
- Damit Handys den QR-Code öffnen können, schalten Sie „Programm im WLAN erreichbar machen“ ein und starten das
  Programm neu. Windows fragt dann nach der Firewall: nur **private Netzwerke** erlauben.
- Aus dem WLAN sind ohne Passwortschutz nur die QR-Seiten erreichbar.
- Die mitgelieferten Texte zu Datenschutz und Abholung sind Vorschläge. Bitte rechtlich prüfen lassen.

### Technisch
- Neue Tabellen `auftrag_belege` (gegen Ändern und Löschen geschützt) und `mobil_zugaenge`.
- Neue Spalten in `auftraege`. Vor der Umstellung wird automatisch gesichert.

## 0.12.0 – 15.10.2026
Zahlungseingänge, offene Posten, Bankabgleich und Mahnwesen (Ausbaustufe 2 von 10).

### Neu
- **Zahlungsstatus je Rechnung:** offen, teilweise bezahlt, bezahlt, überfällig (dazu storniert, Guthaben).
  Sichtbar in der Rechnung, in der Rechnungsliste, bei den offenen Posten und beim Kunden. Gutschriften mindern den
  offenen Betrag.
- **Zahlung erfassen** in der Rechnung: Datum, Betrag, Zahlungsart (Überweisung, Bar, EC/Karte, PayPal,
  Verrechnung) und Notiz.
  - Teilzahlungen und Erstattungen sind möglich.
  - Zahlungen lassen sich nicht löschen, nur mit Begründung stornieren. Sie bleiben sichtbar und stehen im
    Änderungsprotokoll.
- **Offene Posten** (Menü *Verkauf*): Summe offen, davon überfällig, offene Mahngebühren, Filter „nur überfällige“
  und nach Kunde. Im Menü steht ein Zähler überfälliger Rechnungen.
- **Bankabgleich:**
  - Kontoauszug als CSV (Sparkasse, Volksbank, N26, DKB, ING, Postbank, Commerzbank …, Spalten werden automatisch
    erkannt) oder CAMT.053 (XML/ZIP) einlesen.
  - Doppelte Umsätze werden erkannt.
  - Zuordnungsvorschlag über Rechnungs- oder Mahnnummer im Verwendungszweck, sonst über Betrag und Name.
  - Jede Zuordnung bestätigen Sie selbst. Wird die Zahlung storniert, ist der Umsatz wieder frei.
- **Mahnwesen:**
  - Stufen: Zahlungserinnerung (ohne Gebühr), 1. und 2. Mahnung, mit einstellbaren Fristen, Gebühren und Texten
    (*Einstellungen → Mahnwesen*).
  - Vorschlagsliste fälliger Schreiben; Stufen können nicht übersprungen werden.
  - Jedes Schreiben bekommt eine Nummer (MA-…) und wird wie eine Rechnung als PDF und Daten mit Prüfsumme
    unveränderbar archiviert (Datenprüfung inklusive).
  - Versand per E-Mail (Versandprotokoll und E-Mail-Historie des Kunden) oder ausdrucken und als „per Post
    versendet“ vermerken.
  - Gebühren oder Zinsen einer Mahnung können mit Begründung erlassen werden.
  - Nach der 2. Mahnung erscheint ein Hinweis auf weitere Schritte.
- **Verzugszinsen (optional):** Basiszinssatz einstellbar, Aufschlag für Privat- und Geschäftskunden getrennt
  (5 bzw. 9 Prozentpunkte). Beginn wahlweise ab der 1. Mahnung (Standard) oder ab Fälligkeit.
- **Startseite:** „Noch nicht bezahlt“ berücksichtigt Zahlungen und Gutschriften und zeigt die Zahl überfälliger
  Rechnungen.

### Technik
- Neue Tabellen `zahlungen`, `bank_importe`, `bank_umsaetze` und `mahnungen`, alle mit Datenbank-Schutz gegen
  Ändern und Löschen. Vorher automatische Sicherung `vor_update_….db`.
- Neue Module `rsb/zahlungen.py`, `rsb/bankabgleich.py` und `rsb/mahnwesen.py`. 130 automatische Tests.

---

## 0.11.0 – 15.10.2026
GoBD-Grundlagen für Rechnungen und Belege (Ausbaustufe 1 von 10).

### Neu
- **Gutschrift mit eigenem Nummernkreis** (Standard „GS-2026-0001“): bei einer festgeschriebenen Rechnung über
  „Gutschrift erstellen“. Positionen sind vorbelegt, Beträge werden positiv eingegeben und als Minderung gebucht.
  Mit Bezug auf die Rechnung und eigenen Textbausteinen.
- **Pflichtangaben-Prüfung vor dem Festschreiben** (§ 14 Abs. 4 UStG):
  - Ihr vollständiger Name und Ihre Anschrift, Steuernummer oder USt-IdNr.
  - Name und Anschrift des Kunden (bei Kleinbetragsrechnungen bis 250 € nur Hinweis)
  - Rechnungsdatum, Leistungsdatum, Bezeichnung und Menge je Position
  - Steuersatz bzw. Hinweis nach § 19 UStG
  - Was fehlt, steht schon im Entwurf oben mit Link zu den Firmendaten.
- **Feldgenaues Änderungsprotokoll** für Rechnungen und KVA (Entwürfe), Kunden und Artikel: wer, wann (mit
  Sekunden), welches Feld, alter und neuer Wert, dazu Festschreiben und Storno als Ereignis. Nicht änderbar,
  aufklappbar auf den jeweiligen Seiten.
- **Archiv der Rechnungsdaten:** Beim Festschreiben werden neben dem PDF auch alle Rechnungsdaten als JSON-Datei mit
  eigener SHA-256-Prüfsumme archiviert.
- **Prüfsummenkontrolle beim Öffnen:** Angezeigt wird immer das archivierte Original-PDF. Wurde es verändert oder
  fehlt es, erscheint ein deutlicher Hinweis statt eines neu erzeugten PDFs.
- **Aufbewahrungsfristen** unter *Einstellungen → Rechnung & Steuer*: Belege 8 Jahre, Geschäftsbriefe 6 Jahre. Die
  gesetzlichen Mindestfristen können nicht unterschritten werden. Jede festgeschriebene Rechnung zeigt
  „Aufbewahren bis“.
- **Kunden löschen mit Fristprüfung:** Vorschau, was gelöscht und was bis wann aufbewahrt wird.
  - Bei Aufbewahrungspflicht werden die Stammdaten anonymisiert; Name und Anschrift bleiben nur in den
    archivierten Belegen.
  - Sonst wird der Kunde vollständig gelöscht.
- **Verfahrensdokumentation** (Menü *Verwaltung*): aus den tatsächlichen Einstellungen erzeugte Vorlage für den
  Steuerberater, als Seite und PDF.

### Geändert
- Festschreiben ist erst möglich, wenn alle Pflichtangaben vorhanden sind. **Bitte unter Einstellungen →
  Firmendaten Straße, PLZ und Steuernummer (oder USt-IdNr.) prüfen.**
- Datenbank-Schutz erweitert: Auch Zahlungsziel und Daten-Prüfsumme festgeschriebener Belege sind gesperrt.
- Datenprüfung kontrolliert zusätzlich die archivierten Rechnungsdaten.
- Zeitpunkt des Festschreibens in deutscher Zeit mit Sekunden.

### Technik
- Neue Tabelle `feldaenderungen` (nur anhängen, Trigger gegen Ändern und Löschen), neue Felder
  `dokumente.snapshot_sha256` und `kunden.anonymisiert_am`. Vorher automatische Sicherung `vor_update_….db`.
- Neue Module `rsb/aufbewahrung.py` und `rsb/verfahrensdoku.py`. 119 automatische Tests.

---

## 0.10.0 – 15.10.2026
Alle E-Mails mit Kunden erscheinen automatisch beim Kunden, egal ob aus dem Programm, aus Outlook oder vom Handy
gesendet.

### Neu
- **E-Mail-Verlauf beim Kunden:** gesendete (↗) und empfangene (↙) Mails mit Datum, Betreff, Absender/Empfänger,
  Anhangsnamen und Text zum Aufklappen. Verweise auf das versendete Dokument bzw. die Kontaktformular-Anfrage.
- **Einstellungen → Anfragen → „E-Mail-Historie bei Kunden“:**
  - einschalten
  - Ordner für empfangene Mails (mehrere, auch Unterordner) und für gesendete Mails (bei IONOS meist „Gesendete
    Objekte“); „Ordner abrufen“ zeigt alle Ordner zum Ankreuzen, Umlaute in IMAP-UTF-7 werden richtig dargestellt
  - erster Import: 30 Tage, 6 Monate, 1 Jahr oder alles
  - weitere eigene Adressen
  - Es wird der vorhandene IMAP-Zugang verwendet, ohne doppelte Felder. Abgerufen wird im Intervall der Anfragen.
  - Dazu die Knöpfe „Jetzt abgleichen“ und „Alle Ordner neu abgleichen“ mit Anzeige des letzten Abgleichs und
    eventueller Hinweise.
- **Kunden:** neues Feld „Weitere E-Mail-Adressen / Ansprechpartner“ (eine je Zeile).
- **Nachträglicher Abgleich:** Neuer Kunde oder neue Adresse beim Kunden → das Postfach wird im Hintergrund gezielt
  nach Mails von/an/cc dieser Adresse im Importzeitraum durchsucht.

### So arbeitet der Abgleich
- From, To, Cc und Reply-To werden mit allen Kunden-Adressen verglichen. Groß-/Kleinschreibung, Leerzeichen und
  Anzeigenamen werden ignoriert, eigene Adressen zählen nie.
- **Ohne Kundentreffer wird nichts gespeichert,** auch nicht im Protokoll. Das Protokoll enthält nur Anzahlen.
- Trifft eine Mail mehrere Kunden, steht sie bei jedem.
- Richtung: „gesendet“ aus dem Gesendet-Ordner oder bei eigener Absenderadresse, sonst „empfangen“.
- Kontaktformular-Mails werden mit der vorhandenen Anfrage verknüpft und nicht doppelt angelegt.
- **Nur lesen:** Ordner werden mit EXAMINE geöffnet und Inhalte mit BODY.PEEK[] geholt. Nichts wird als gelesen
  markiert, verschoben oder gelöscht.
- **Inkrementell:** je Ordner UIDVALIDITY und letzte UID. Ändert sich die UIDVALIDITY, wird der Ordner im
  Importzeitraum neu abgeglichen.
- Zuerst werden nur die Kopfzeilen geladen, der vollständige Inhalt nur bei einem Kundentreffer.
- Keine Duplikate dank Message-ID. Mails, die das Programm selbst verschickt (KVA, Rechnung, Leihvertrag …), werden
  direkt beim Versand gespeichert und später mit dem Fund im Postfach zusammengeführt.
- Der Abruf läuft im Hintergrund mit Zeitlimit. Fehler erscheinen als Hinweis; ein fehlender Ordner hält die übrigen
  nicht auf.

### Datenschutz
- Beim Löschen eines Kunden wird auch sein E-Mail-Verlauf im Programm gelöscht (Mails, die zusätzlich bei anderen
  Kunden stehen, bleiben dort). Das Postfach selbst bleibt unverändert.
- Anhänge werden nicht kopiert, nur ihre Namen und Größen. Die Dateien bleiben im Postfach.

### Technik
- Neue Tabellen `email_nachrichten`, `email_kunden` und `imap_ordner_status`, neues Feld `kunden.email_weitere`.
  Vor der Erweiterung wird automatisch `Daten\backups\vor_update_….db` angelegt.
- Neues Modul `rsb/email_historie.py`. 111 automatische Tests.

---

## 0.9.1 – 15.10.2026
Anfragen-Abruf funktioniert jetzt auch, wenn Port 993 gesperrt ist.

### Neu
- **Verschlüsselung für den Anfragen-Abruf (IMAP):** In *Einstellungen → Anfragen* wählen Sie jetzt
  „SSL/TLS (meist Port 993)“ oder „STARTTLS (meist Port 143)“, wie beim E-Mail-Versand. Beim Wechsel wird der
  passende Port vorgeschlagen, solange noch der Standardport eingetragen ist.
- **„Verbindung testen“** im IMAP-Bereich der Anfragen: prüft Verbindung, Anmeldung und ob die Ordner „INBOX“ und
  „Anfragen erledigt“ existieren, auch vor dem Speichern.

### Geändert
- Kontaktformular-Abruf und Ablage im Gesendet-Ordner nutzen denselben, gemeinsamen Verbindungsaufbau.
- STARTTLS: Anmeldung erst nach erfolgreicher Verschlüsselung. Bietet der Server kein STARTTLS an oder schlägt es
  fehl, bricht das Programm mit klarer Meldung ab – **nie Anmeldung ohne Verschlüsselung**.
- Verständliche deutsche Fehlermeldungen, z. B. bei „WRONG_VERSION_NUMBER“: *„Port und Verschlüsselung passen nicht
  zusammen (993 = SSL, 143 = STARTTLS).“*, außerdem bei unbekanntem Server, gesperrtem Port, Zeitüberschreitung,
  Zertifikatsproblemen und falschem Passwort.
- Ordnernamen mit Umlauten werden beim Abruf korrekt kodiert.

### Fehlerbehebung
- Port 143 führte zu „[SSL: WRONG_VERSION_NUMBER] wrong version number“, weil der Abruf immer direkt SSL verwendete.

### Technik
- Bestehende Einstellungen werden beim Start einmalig umgestellt: Port 993 → SSL/TLS, sonst STARTTLS.
- Neues Modul `rsb/imap_verbindung.py`. 102 automatische Tests, darunter echte Verbindungstests gegen einen lokalen
  Test-Server (SSL auf einem Klartext-Port, Server ohne STARTTLS: es wird kein Passwort gesendet).

---

## 0.9.0 – 15.10.2026
Leihgeräte für Kunden während der Reparatur, mit Leihvertrag, Rückgabeprotokoll, Schadensfällen und Abrechnung.

### Neu
- **Menüpunkt „Leihgeräte“:**
  - Übersicht mit Status (Verfügbar, Verliehen, Defekt / in Reparatur, Ausgemustert), Filter und Suche
  - verliehene Geräte zeigen Kunde, Auftrag, Ausgabe und Rückgabedatum; überfällige Rückgaben sind rot markiert
  - im Menü ein Zähler für überfällige Rückgaben
- **Je Leihgerät:**
  - Bezeichnung, Typ, Hersteller, Modell, Seriennummer, Inventarnummer
  - Standard-Zubehör als Checkliste, Zustand, Anschaffungsdatum, Anschaffungs- und Zeitwert
  - Leihgebühr kostenlos / pauschal / pro Tag mit kostenlosen Tagen, optionale Kaution
  - Fotos und eine Historie aller Leihen, Schäden und Statuswechsel
  - Geräte werden nicht gelöscht, sondern ausgemustert
- **Reiter „Leihgerät“ im Reparaturauftrag:**
  - **Ausgeben:** nur verfügbare Geräte. Erfasst werden Zeitpunkt (Server-Zeit, vorbelegt), voraussichtliche Rückgabe,
    Zubehör zum Abhaken, Leihgebühr (vorbelegt, änderbar, auch „kostenlos (Kulanz)“), Kaution mit Zahlungsart sowie
    Zustand mit Notiz und Fotos („Leihgerät Ausgabe“).
  - **Leihvertrag / Übergabeprotokoll als PDF:** Kunde, Gerät mit Seriennummer, Zubehör, Zustand mit Fotos,
    Leihgebühr, Kaution, Rückgabedatum, Leihbedingungen und Unterschriftsfelder. Auf Wunsch direkt per E-Mail an
    den Kunden.
  - Die Leihbedingungen sind unter *Einstellungen → Leihgeräte* frei bearbeitbar.
- **Rücknahme:**
  - Zeitpunkt, Zubehör-Checkliste (was fehlt?), Zustand „einwandfrei“ oder „Schaden festgestellt“, Notiz und
    Fotos („Leihgerät Rückgabe“). Die Fotos von Ausgabe und Rückgabe stehen nebeneinander zum Vergleich.
  - Die Leihgebühr wird automatisch berechnet (Kalendertage minus kostenlose Tage, bzw. Pauschale) und kann vor der
    Übernahme geändert werden.
  - Ohne Schaden ist das Gerät wieder verfügbar und die Kaution steht auf „zurückzuzahlen“.
  - Rückgabeprotokoll als PDF.
- **Schadensfall** (bei Schaden oder fehlendem Zubehör):
  - Beschreibung, Fotos und Kostenart (Reparatur, Zubehör-Ersatz, Totalschaden/Verlust mit dem Zeitwert vorbelegt)
  - transparente Verrechnung mit der Kaution: noch zu zahlen bzw. Erstattung
  - das Gerät wird automatisch auf „Defekt“ bzw. „Ausgemustert“ gesetzt
  - per Klick ein interner Reparaturauftrag für das Leihgerät (ohne Rechnung; nach dem Erledigen ist das Gerät
    wieder verfügbar)
  - Schadensfall-Dokumentation als PDF mit Fotos und Verlauf
- **Abrechnung:**
  - Beim Ziehen auf „Erledigt“ kommen Leihgebühr und Schäden als eigene Positionen in den Rechnungsentwurf, z. B.
    „Leihgerät Lenovo ThinkPad T14 #1, 2 Tage à 5,00 €“ und „Schaden Leihgerät: Netzteil fehlt“.
  - Die Kautionsverrechnung steht als Hinweis auf der Rechnung.
  - Ist das Gerät noch nicht zurück, fragt das Programm: „Leihgerät jetzt zurücknehmen oder später separat
    abrechnen?“
- **Katalog:** neue Positionen „Leihgebühr pauschal“, „Leihgebühr pro Tag“ und „Schadenersatz Leihgerät“ unter
  *Leistungen & Artikel*.
- **Tafel:** Auftragskarten zeigen „🔁 Leihgerät“, bei überfälliger Rückgabe rot.
- **Kunde:** Hinweis, wenn der Kunde gerade ein Leihgerät hat, sowie eine Liste früherer Leihen mit Schadensfällen.

### Geändert
- Aufträge mit Leihgerät und Kunden mit Leihvorgängen lassen sich nicht mehr löschen (Archivieren ist möglich).
- Interne Aufträge (Reparatur eigener Leihgeräte) erzeugen beim Erledigen keine Rechnung und fragen nicht nach
  einem KVA.

### Technik
- Neue Tabellen `leihgeraete`, `leihen`, `schadensfaelle` und `leihgeraet_verlauf`, neue Foto-Felder
  `leihgeraet_id`, `leihe_id` und `schadensfall_id`. Datenbank-Trigger verhindern das Ändern von Ausgabe- und
  Rückgabeprotokollen und das Löschen von Leihvorgängen, Schadensfällen, Historie und Geräten. Korrekturen gehen nur
  als Stornierung mit Begründung.
- Zeitstempel serverseitig in Europe/Berlin mit Sekunden.
- Vor der Datenbank-Erweiterung wird automatisch `Daten\backups\vor_update_….db` angelegt.
- 94 automatische Tests.

---

## 0.8.0 – 15.10.2026
Reparaturaufträge mit Detailansicht: Kostenvoranschlag verknüpfen, Fotos dokumentieren, lückenloser Verlauf.

### Neu
- **Detailansicht je Auftrag:** Ein Klick auf eine Karte öffnet den Auftrag. Ziehen & Ablegen und die Pfeil-Knöpfe
  funktionieren wie bisher. Kopf mit Auftragsnummer, Status und Eingangsdatum, Reiter **Auftragsdaten**,
  **Kostenvoranschlag**, **Fotos** und **Verlauf**. Alle Felder sind bearbeitbar, auch Kunde und Status.
- **KVA verknüpfen:**
  - **„Bestehenden KVA verknüpfen“** zeigt freie Kostenvoranschläge des Kunden. Suche nach Nummer, Datum oder
    Betrag, optional „alle Kunden anzeigen“.
  - **„Neuen KVA aus diesem Auftrag erstellen“** füllt den KVA vor und verknüpft ihn automatisch.
  - Ist ein KVA verknüpft: Nummer, Datum, Betrag und Status (offen / angenommen / abgelehnt) sowie die Knöpfe
    Öffnen, PDF, Per E-Mail senden und **Verknüpfung lösen** (mit Rückfrage; der KVA bleibt erhalten).
  - Warnung, wenn KVA und Auftrag zu unterschiedlichen Kunden gehören.
  - Die KVA-Seite zeigt den zugehörigen Auftrag mit Link und den KVA-Status.
- **Erledigt ohne KVA:** Statt stillschweigend eine leere Rechnung anzulegen, fragt das Programm:
  „Kein KVA verknüpft – leeren Rechnungsentwurf erstellen oder KVA jetzt verknüpfen?“ (Tafel, Knopf und
  Detailansicht).
- **Fotodokumentation:**
  - mehrere Fotos auf einmal, Ziehen & Ablegen, am Handy direkt die Kamera
  - Kategorien: Geräteeingang, Vorschaden, Während der Reparatur, Nach der Reparatur, Geräteausgabe
  - Gespeichert werden: Server-Zeit (deutsche Zeit, mit Sekunden), Aufnahmezeit aus der Kamera (EXIF), Benutzer
    und SHA-256-Prüfsumme. Das Original bleibt unverändert.
  - Löschen nur als Markierung mit Pflicht-Begründung; das Foto bleibt erhalten.
  - Fotodokumentation als PDF mit Änderungsprotokoll
- **Karten auf der Tafel** zeigen 📷 Anzahl Fotos und „KVA ✓“ bzw. „kein KVA“.
- **„+ Neuer Auftrag“** ist jetzt eine eigene Seite mit denselben Feldern wie die Detailansicht. Dort können Sie
  gleich einen KVA verknüpfen und Fotos hochladen. Die Fotos werden sofort gespeichert und bleiben erhalten, auch
  wenn das Speichern des Auftrags einmal fehlschlägt (z. B. Kunde vergessen). Ihre Eingaben bleiben dann ebenfalls
  stehen.
- **Verlauf** je Auftrag mit Zeitpunkt und Benutzer:
  - angelegt, Daten geändert, Statuswechsel
  - KVA verknüpft, gelöst, festgeschrieben, angenommen/abgelehnt, per E-Mail versendet
  - Fotos hochgeladen oder als gelöscht markiert
  - Rechnung erstellt

### Geändert
- Beim Löschen eines Auftrags bleibt ein verknüpfter KVA jetzt erhalten (bisher wurde ein KVA-Entwurf
  mitgelöscht). Aufträge mit Fotos oder festgeschriebener Rechnung lassen sich nicht löschen. Kunden, zu deren
  Aufträgen es Fotos gibt, ebenfalls nicht; sie können archiviert werden.
- Größere Uploads möglich (bis 60 MB je Foto).

### Technik
- Neue Tabellen `auftrag_fotos` und `auftrag_verlauf`, beide durch Datenbank-Trigger gegen Ändern und Löschen
  geschützt. Neues Feld `dokumente.kva_status`. Fotos liegen in `Daten\fotos\JJJJ\MM\` (Vorschaubilder in
  `Daten\fotos\vorschau\`) und sind Teil des Backups.
- Vor der Datenbank-Erweiterung wird automatisch `Daten\backups\vor_update_….db` angelegt. Für bestehende
  Aufträge wird der Verlauf einmalig aus dem Änderungsprotokoll nachgetragen.
- 82 automatische Tests.

---

## 0.7.0 – 15.10.2026
Versendete Mails im Postfach, manuelle Positionen automatisch im Katalog, ausführliche Artikelbeschreibungen.

### Neu
- **Kopie im Gesendet-Ordner (IMAP):** *Einstellungen → E-Mail → IMAP*. Jede versendete Mail wird nach dem
  erfolgreichen SMTP-Versand mit Anhängen, Datum und Message-ID per IMAP im gewählten Ordner abgelegt
  (als gelesen markiert).
  - IMAP-Server, Port (993), Verschlüsselung (SSL/TLS oder STARTTLS/143), gleiche Zugangsdaten wie SMTP oder eigene
    (Passwort verschlüsselt gespeichert)
  - **„Ordner abrufen“** listet die Ordner des Postfachs (Umlaute/IMAP-UTF-7 werden richtig angezeigt),
    der Gesendet-Ordner wird vorausgewählt
  - **„Verbindung testen“** mit verständlicher Meldung: Erfolg, falsches Passwort, Server nicht erreichbar,
    Ordner fehlt
  - Schlägt die Ablage fehl, gilt die Mail trotzdem als gesendet – gelber Hinweis, Eintrag im Protokoll,
    **kein erneuter Versand**. Das Versandprotokoll vermerkt, ob die Kopie abgelegt wurde.
- **Manuelle Positionen → „Leistungen und Artikel“:** Von Hand eingegebene Positionen in KVA und Rechnungen werden
  beim Speichern automatisch in den Katalog übernommen (Bezeichnung, Beschreibung, Einheit, Einkauf, Preis, Marge,
  Steuersatz, Typ) und mit der Position verknüpft.
  - pro Position Haken **„In Leistungen und Artikel speichern“** (für einmalige Sonderpositionen abwählen) und Typ
    Leistung/Artikel (mit Einkaufspreis automatisch „Artikel“)
  - keine Duplikate (Groß-/Kleinschreibung und Leerzeichen werden ignoriert); weichen die Preise ab, kommt die
    Rückfrage **„Preise im Katalog aktualisieren?“** (Ja/Nein)
  - fehlt der Einkaufspreis, bleibt die Marge leer (statt 0 % oder 100 %)
- **„Aus bisherigen Dokumenten übernehmen“** (in *Leistungen & Artikel*): sammelt alle manuellen Positionen aus
  früheren KVA und Rechnungen, fasst Duplikate zusammen und zeigt eine Vorschau mit Preisen, früheren Preisen und
  Margen zum Abhaken.
- **Ausführliche Beschreibung** für Leistungen und Artikel (großes mehrzeiliges Feld, keine Längenbegrenzung):
  wird beim Einfügen in KVA/Rechnung übernommen und kann dort für den Einzelfall angepasst werden, ohne den
  Katalog zu ändern. Im PDF steht sie kleiner unter der Bezeichnung, Zeilenumbrüche bleiben erhalten, lange Texte
  brechen sauber auf die nächste Seite um.
- Artikelsuche durchsucht auch die Beschreibung (z. B. „USB-C“, „HDMI“); die Liste zeigt nur die erste Zeile.

### Geändert
- E-Mail-Versand liest die Zugangsdaten immer frisch aus den gespeicherten Einstellungen. Fehlen sie oder sind sie
  ungültig (z. B. leer oder „localhost“), kommt eine klare Meldung statt eines Verbindungsversuchs.
- Zeitlimit 20 Sekunden für SMTP und IMAP (auch beim Abholen der Anfragen).
- Bei „Verbindung abgelehnt“ (z. B. WinError 10061) ein zweiter Verbindungsversuch nach 2 Sekunden – nur beim
  Verbindungsaufbau, es wird nie doppelt gesendet; die Fehlermeldung nennt Server und Port.
- Einkaufspreis bei Leistungen/Artikeln darf leer bleiben (= unbekannt, keine Marge).

### Technik
- Neue Felder `artikel.ek_unbekannt`, `versandprotokoll.ablage`. Vor jeder Datenbank-Erweiterung wird automatisch
  eine Sicherung `Daten\backups\vor_update_….db` angelegt.
- 73 automatische Tests.

---

## 0.6.1 – 15.10.2026
Vertragsrechnungen gehen ab jetzt vollautomatisch raus.

### Geändert
- **Wiederkehrende Rechnungen vollautomatisch:** Fällige Vertragsrechnungen werden automatisch festgeschrieben und
  per E-Mail an den Kunden gesendet. Die Umstellung erfolgt bei diesem Update einmalig. Wer lieber erst prüfen will,
  stellt unter *Einstellungen → Verträge* auf „als Entwurf anlegen“ zurück – diese Wahl bleibt dann erhalten.
- Warnhinweis auf der Übersicht und bei den Verträgen, solange der E-Mail-Zugang fehlt (dann werden Rechnungen nur
  festgeschrieben, aber nicht versendet).

---

## 0.6.0 – 15.10.2026
Verträge, Lizenzen und Garantien beim Kunden – mit automatischen wiederkehrenden Rechnungen.

### Neu
- **Verträge & Lizenzen** (*Verkauf → Verträge & Lizenzen*) und beim Kunden unter „Verträge, Lizenzen & Garantien“:
  - Bezeichnung, Kategorie (Garantie/Versicherung, Lizenz, MSP, Wartung, Sonstiges), Vertrags-/Policen-/Lizenznummer,
    Gerät/Seriennummer, Beginn, Laufzeit, Mindestlaufzeit, Preis, Einkauf (Marge), Anzahl (z. B. Geräte), Notizen
- **Abrechnungsarten:**
  - *nur Dokumentation* – z. B. Wertgarantie (Kunde zahlt direkt an den Versicherer)
  - *monatlich, vierteljährlich, halbjährlich, jährlich* – z. B. MSP-Pakete, im Voraus bis zur Kündigung
  - *einmal je Laufzeit* – z. B. ESET 1, 2 oder 3 Jahre; optional „verlängert sich automatisch“
- **Vertragsarten** als Vorlagen, jederzeit erweiterbar (*Verträge & Lizenzen → Vertragsarten*). Mitgeliefert:
  Wertgarantie, ESET 1/2/3 Jahre, MSP Basis (Preise bitte eintragen).
- **Wiederkehrende Rechnungen:** täglich automatisch (und per Knopf „Jetzt abrechnen“) eine Rechnung je Kunde mit
  allen fälligen Verträgen, Zeitraum und Lizenznummer stehen auf der Rechnung. Wahlweise als **Entwurf** oder
  **automatisch festschreiben und per E-Mail senden** (*Einstellungen → Verträge*).
- **Kündigen:** Vertrag als gekündigt hinterlegen (Eingang, Ende zum, Grund). Bis zum Kündigungsdatum wird noch
  berechnet, danach **keine Rechnung mehr**. Kündigung kann zurückgenommen werden. Vorschlag für das Enddatum:
  Ende der laufenden Periode bzw. Mindestlaufzeit.
- **Lizenz verlängern** per Knopf: neue Laufzeit + Rechnungsentwurf.
- **Erinnerung:** Lizenzen/Garantien, die in den nächsten 60 Tagen (einstellbar) ablaufen, erscheinen unter
  „Laufen bald ab“ und auf der Übersicht.
- **Kennzahlen:** aktive Verträge, regelmäßige Einnahmen pro Monat, fällige Abrechnungen.
- **Bestehende Verträge übernehmen:** Feld „Bereits berechnet bis“ – frühere Zeiträume (z. B. aus Lexware)
  werden nicht noch einmal berechnet.

### Behoben
- In leeren Feldern der Kunden-, Artikel- und Textbaustein-Formulare stand „None“.

### Hinweise
- Keine doppelten Rechnungen: Jeder berechnete Zeitraum wird gespeichert. Wird ein Rechnungsentwurf gelöscht,
  gilt der Zeitraum wieder als offen.
- Verträge mit festgeschriebenen Rechnungen können nicht gelöscht, nur gekündigt werden.

---

## 0.5.1 – 15.10.2026
Versionsprotokoll direkt im Programm.

### Neu
- **Versionsprotokoll im Programm:** *Einstellungen → Programm & Updates → Versionsprotokoll anzeigen*.
  Ein Klick auf die Versionsnummer unten links öffnet es ebenfalls.
- Ausführliches Versionsprotokoll mit allen bisherigen Versionen (auch unter `docs/AENDERUNGEN.md`).

---

## 0.5.0 – 14.10.2026
Das Programm verhält sich jetzt wie eine normale Windows-Anwendung.

### Neu
- **Eigenes Programmfenster** ohne Adressleiste und Tabs (Microsoft Edge im App-Modus, bei Windows 11 vorhanden).
  Gibt es Edge nicht, öffnet sich der Standardbrowser.
- **Symbol im Infobereich** (unten rechts neben der Uhr):
  - Klick: Buchhaltung öffnen
  - Rechtsklick: „Buchhaltung öffnen“, „Daten-Ordner öffnen“, „Beenden“
- Einstellung **Programmfenster**: eigenes Fenster oder Tab im normalen Browser
  (*Einstellungen → Programm & Updates*).
- Programmmeldungen stehen in `Daten\programm.log`. Ab 1 MB wird die Datei automatisch gewechselt.

### Geändert
- **Kein schwarzes Konsolenfenster** mehr beim Start.
- **Keine Passwortabfrage** mehr. Bei Bedarf unter *Einstellungen → Passwortschutz* einschalten (mind. 8 Zeichen)
  und dort auch wieder ausschalten.
- Der Knopf „Abmelden“ erscheint nur noch bei eingeschaltetem Passwortschutz.

### Hinweise
- Ohne Passwort schützt die Windows-Anmeldung (PIN/Passwort) und die Bildschirmsperre (`Win + L`).
  Von anderen Geräten ist das Programm nicht erreichbar.

### Technik
- Webserver im Hintergrund, Infobereichssymbol über `pystray`, EXE ohne Konsole (`console=False`).
- Neue Einstellungen: `login_aktiv` (Standard: aus), `fenster_modus` (Standard: eigenes Fenster).
- 48 automatische Tests, Windows-Start-Test bei GitHub bestanden.

---

## 0.4.0 – 14.10.2026
Erste Version als EXE-Datei – keine Python-Installation und kein Installer mehr nötig.

### Neu
- **Werkstatt-Sauter.exe** – eine einzige Datei. Ordner anlegen (z. B. `C:\Werkstatt-Sauter`), Datei hineinlegen,
  starten. Der Ordner `Daten` entsteht direkt daneben.
- **Automatische Updates:**
  - Prüfung beim Start und alle 6 Stunden bei GitHub (kostenlos, ohne Login, es werden keine Daten übertragen)
  - neue Version wird beim nächsten Start installiert: Download → Prüfsummen-Kontrolle (SHA-256) → Backup →
    Austausch der EXE → Neustart
  - Hinweisleiste „Neue Programmversion verfügbar“ mit Knopf **„Jetzt aktualisieren“**
  - abschaltbar unter *Einstellungen → Programm & Updates*
- Ein zweiter Doppelklick auf die EXE, während das Programm schon läuft, öffnet nur die Oberfläche
  und startet das Programm kein zweites Mal.
- Dateieigenschaften der EXE (Firma, Produkt, Version) und eigenes Programmsymbol.

### Behoben
- Veröffentlichung bei GitHub scheiterte an Sonderzeichen (→) in den Hinweistexten (UTF-8 erzwungen).

### Technik
- Bau mit PyInstaller. GitHub Actions baut die Windows-EXE bei jeder neuen Versionsnummer, testet sie
  (Programmstart und Versionsabfrage unter Windows) und veröffentlicht sie mit Prüfsumme als Release.
- Update-Ablauf lokal geprüft: Version 0.4.0 → 0.4.1 automatisch beim Start und über den Knopf, jeweils mit Backup
  und Aufräumen der alten Datei.

### Umstieg von start.bat
- Den Ordner `Daten` aus der alten Installation neben die EXE kopieren. Alles bleibt erhalten, auch das
  gespeicherte E-Mail-Passwort.

---

## 0.3.0 – 14.10.2026
Reparaturaufträge und Kostenvoranschläge. *(Nur als Quellcode, noch keine EXE.)*

### Neu
- **Reparaturaufträge als Tafel** (*Verkauf → Reparaturaufträge*) mit den Spalten **Offen → In Arbeit → Erledigt**:
  - Karten per **Ziehen & Ablegen** verschieben, auch innerhalb einer Spalte (Reihenfolge)
  - alternativ Knöpfe auf jeder Karte („Starten →“, „Erledigt ✓“, „←“), z. B. für Tablets
  - Karte zeigt Auftragsnummer (`RA-2026-0001`), Kunde, Gerät, Fehler, Tage seit Eingang, KVA und Rechnung
  - Spalte „Erledigt“ zeigt die letzten 30 Tage, ältere über „alle anzeigen“
- **Auftragsdetails:** Gerät, Seriennummer/IMEI, mitgegebenes Zubehör, Fehlerbeschreibung, interne Notizen,
  Zeitpunkte für Eingang, Beginn und Erledigung.
- Auftrag anlegen auf der Tafel, **aus einer Anfrage** (übernimmt Gerät und Fehler) oder beim Kunden.
- **Kostenvoranschlag (KVA)** als neue Dokumentart:
  - eigene Nummern `KV-2026-0001`, „Gültig bis“ (Standard 30 Tage, einstellbar)
  - eigene Textbausteine (Einleitung, Schluss, E-Mail), PDF, Druck, E-Mail-Versand
  - „In Rechnung übernehmen“ übernimmt alle Positionen
- **Auftrag auf „Erledigt“ ziehen → Rechnungsentwurf** mit den KVA-Positionen, Gerät und IMEI im Betreff und
  dem heutigen Datum als Leistungsdatum. Der Entwurf öffnet sich direkt zum Prüfen und Festschreiben.
  Wird ein Auftrag zurück und erneut auf „Erledigt“ gezogen, entsteht keine zweite Rechnung.
- Übersicht: Kacheln mit der Anzahl offener, laufender und erledigter Aufträge.
- Rechnungsliste mit Filter nach Art (Rechnungen / Kostenvoranschläge).

### Behoben
- Bestätigungsdialog beim Festschreiben wurde wegen Anführungszeichen nicht angezeigt.

### Hinweise
- Rechnungen werden bewusst **nicht automatisch festgeschrieben**, damit ein versehentliches Ziehen keine
  Rechnungsnummer verbraucht.

---

## 0.2.0 – 14.10.2026
Anfragen aus dem Kontaktformular der Website. *(Nur als Quellcode, noch keine EXE.)*

### Neu
- **Automatischer Abruf** der Formular-E-Mails aus dem Postfach (IMAP, z. B. IONOS oder Gmail), alle 5 Minuten
  (einstellbar). Nur E-Mails mit dem Text „A new form has been submitted“ werden verarbeitet.
  Erledigte E-Mails kommen in den Ordner „Anfragen erledigt“.
- **Auslesen** der Felder Name, Telefon, Email, Gerät und Nachricht. Vor- und Nachname werden automatisch
  getrennt, auch bei „Nachname Vorname“.
- **Spam-/Unsinn-Erkennung** mit Punkten und Begründung: Links, Werbewörter, Zeichensalat, fremde Schrift,
  ungültige Kontaktdaten, englische Werbetexte – dagegen zählen Themenwörter (Display, Akku, Jura, Laptop …).
  - **Echte Anfrage:** Kunde wird automatisch als **Interessent** angelegt
  - **Unsicher:** Liste „Zu prüfen“, Kunde mit einem Klick anlegen (Name korrigierbar)
  - **Spam:** kein Kunde, automatische Löschung nach 30 Tagen
- **Keine Dubletten:** gleiche E-Mail oder Telefonnummer → Anfrage wird dem vorhandenen Kunden zugeordnet.
- Interessent wird mit der ersten Rechnung automatisch zum Kunden.
- **Datenschutz:** Interessenten ohne Auftrag werden nach 6 Monaten (einstellbar) zum Löschen vorgeschlagen.
- „Anfrage einfügen“ zum Testen oder ohne Postfachzugang.
- Hinweis auf neue Anfragen in der Navigation (rote Zahl) und auf der Übersicht.

---

## 0.1.0 – 14.10.2026
Grundversion (Etappe 1). *(Nur als Quellcode, Start über `installieren.bat` / `start.bat`.)*

### Neu
- **Kundenstamm:** Privat- und Firmenkunden, Kundennummern `K-0001`, Suche, Notizen, eigenes Zahlungsziel,
  Archivieren und Löschen (nur ohne Rechnungen).
- **Leistungen & Artikel:** Festpreise, Teilekosten, Aufschlag, **Marge in € und %**, Leistungsarten für
  Auswertungen (Smartphone, Kaffeemaschine, PC/Laptop, Sonstiges).
- **Rechnungen:**
  - Entwurf mit Vorschau, danach **Festschreiben** mit fortlaufender, lückenloser Nummer `RE-2026-0001`
  - festgeschriebene Rechnungen sind unveränderbar (Schutz direkt in der Datenbank). Korrektur nur über
    **Stornorechnung** und „Als neue Rechnung kopieren“
  - Zahlungsziel 14 Tage (privat) bzw. 30 Tage (Firma)
- **PDF** nach DIN 5008 mit Logo, Farben, Schrift (Montserrat), Falzmarken, Fußzeile mit Firmen-, Bank- und
  Steuerdaten und **QR-Code zum Bezahlen (GiroCode)**. Druck direkt aus dem Programm.
- **Kleinunternehmer-Modus** (§ 19 UStG) mit Pflichthinweis, umschaltbar auf Regelbesteuerung (19 %/7 %).
- **E-Mail-Versand** über das eigene Postfach (SMTP), Textvorlagen, Kopie an sich selbst, **Versandprotokoll**.
  Das Passwort wird verschlüsselt gespeichert.
- **Layout ohne Programmierung:** Farben, Schrift, Logo, Kopf- und Fußzeile, Live-Vorschau.
- **Textbausteine** mit Platzhaltern wie `{nummer}`, `{betrag}`, `{faellig_am}`.
- **Änderungsprotokoll** mit Prüfsummenkette und Seite **Datenprüfung** (PDF-Prüfsummen, lückenlose Nummern,
  Protokoll).
- **Backup:** täglich automatisch als ZIP, zusätzliche Kopie auf ein NAS, Backup per Knopf.
- Übersicht mit Umsatz und Anzeige der Kleinunternehmergrenze.
- Dokumentation: Installation, Bedienung, Recht/GoBD/Datenschutz.

---

## Geplant
- SEPA-Lastschrift für Vertragsrechnungen (Mandatsverwaltung)
- Bankabgleich: N26-Umsätze (CSV) importieren und Zahlungen per Rechnungsnummer zuordnen (wartet auf
  Beispieldatei)
- Anzahlungsrechnung (50 %) und Schlussrechnung mit Abzug, Auftragsbestätigung, Gutschrift
- Zahlungsstatus (offen, teilweise, bezahlt, überfällig), Zahlungserinnerung und 2 Mahnstufen à 3,95 €
- Einnahmen/Ausgaben mit Belegen, EÜR nach Anlage EÜR, Monats- und Jahresübersicht
- Export für Steuer/Finanzamt, Kunden-Import aus CSV, Wiederherstellung per Knopfdruck, Vorlage
  Verfahrensdokumentation
