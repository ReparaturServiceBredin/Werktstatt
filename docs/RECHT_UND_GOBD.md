# Recht, GoBD und Datenschutz – was gilt für Sie, und wo liegen die Grenzen?

> **Wichtig:** Ich bin kein Steuerberater oder Rechtsanwalt. Diese Übersicht beruht auf einer Recherche im
> Oktober 2026. Ich konnte dabei die amtlichen Gesetzestexte (gesetze-im-internet.de) aus technischen Gründen
> nicht direkt abrufen, sondern nur Fachportale und Kammern (IHK, ZDH, Haufe, NWB, dejure). Unsichere Punkte
> sind mit ⚠️ markiert. Die Liste am Ende sollten Sie einmal mit einem Steuerberater oder dem Finanzamt durchgehen.

## 1. Pflichtangaben auf Ihren Rechnungen (Kleinunternehmer)

Seit 1.1.2025 regelt **§ 34a UStDV** die Mindestangaben für Rechnungen von Kleinunternehmern (§ 19 UStG):

| Pflichtangabe nach § 34a UStDV | Im Tool |
|---|---|
| Vollständiger Name und Anschrift des leistenden Unternehmers | ✔ Absenderzeile und Fußzeile (aus *Einstellungen → Firmendaten*) |
| Vollständiger Name und Anschrift des Leistungsempfängers | ✔ Anschriftenfeld |
| Steuernummer, USt-IdNr. oder Kleinunternehmer-Identifikationsnummer | ✔ Fußzeile, **sobald Sie die Steuernummer eintragen** |
| Ausstellungsdatum | ✔ „Datum“ |
| Menge und Art der Lieferung bzw. Umfang und Art der Leistung | ✔ Positionen |
| Entgelt in einer Summe (ohne Umsatzsteuerausweis) | ✔ „Gesamtbetrag“, keine USt |
| Hinweis auf die Steuerbefreiung als Kleinunternehmer | ✔ automatisch: „Gemäß § 19 UStG wird keine Umsatzsteuer berechnet …“ |

**Zusätzlich** druckt das Tool die **fortlaufende Rechnungsnummer** und das **Leistungsdatum**.
Laut den Quellen sind beide für Kleinunternehmer nicht mehr zwingend. Für eine saubere Buchführung und die
Zuordnung von Zahlungen sind sie aber sinnvoll, und sie schaden nicht.

- **Kleinbetragsrechnungen bis 250 € brutto** (§ 33 UStDV) dürften noch weniger Angaben haben. Das Tool erstellt trotzdem immer die vollständige Rechnung. Das ist unproblematisch.
- **Wichtig:** Weisen Sie als Kleinunternehmer **niemals Umsatzsteuer aus**. Sonst schulden Sie diese ans Finanzamt (§ 14c UStG). Das Tool verhindert das im Kleinunternehmer-Modus.
- **Kleinunternehmergrenzen (seit 2025):** höchstens 25.000 € Umsatz im Vorjahr und höchstens 100.000 € im laufenden Jahr. Wird die 100.000-€-Grenze im laufenden Jahr überschritten, endet die Befreiung **sofort**. Die Übersicht im Tool zeigt Ihren Stand. ⚠️ Ob Brutto- oder Nettowerte und welche Umsätze genau zählen, bitte mit dem Steuerberater klären.

## 2. E-Rechnung

| Thema | Was gilt für Sie |
|---|---|
| **Empfangen** | Seit 1.1.2025 müssen **alle** Unternehmen E-Rechnungen von anderen Firmen empfangen können, auch Kleinunternehmer. Ein E-Mail-Postfach genügt. Die XML-Dateien (XRechnung/ZUGFeRD) müssen Sie im **Originalformat** aufbewahren. → Die Belegablage mit Anzeige von E-Rechnungen kommt in Etappe 4. |
| **Ausstellen** | Kleinunternehmer sind laut den Quellen nach § 34a UStDV **dauerhaft von der Pflicht befreit**, E-Rechnungen auszustellen. Ihre PDF-Rechnungen bleiben also zulässig, auch an Firmenkunden. |
| **Freiwillig** | Manche Firmenkunden wünschen trotzdem eine E-Rechnung. Ich kann ZUGFeRD einbauen (PDF mit eingebetteter XML), z. B. in Etappe 2. |
| **Falls Sie umstellen** | Bei Regelbesteuerung gilt die Ausstellungspflicht für Inlandsumsätze an Firmen ab 1.1.2027 (Vorjahresumsatz über 800.000 €) bzw. ab 1.1.2028 (alle anderen). ⚠️ Die Quellen widersprechen sich, ob kleinere Firmen Papier- oder PDF-Rechnungen bis Ende 2026 oder bis Ende 2027 nutzen dürfen. Spätestens dann braucht das Tool ZUGFeRD/XRechnung. |

## 3. Aufbewahrungsfristen

| Unterlagen | Frist |
|---|---|
| Rechnungen (eigene und erhaltene), Kontoauszüge, sonstige Buchungsbelege | **8 Jahre** (verkürzt durch das 4. Bürokratieentlastungsgesetz, gilt seit 1.1.2025) |
| Aufzeichnungen und Bücher (EÜR, Einnahmen-/Ausgabenaufstellung), Verfahrensdokumentation | **10 Jahre** |
| Geschäftsbriefe, auch geschäftliche E-Mails (z. B. Angebot per Mail) | 6 Jahre |

- Die Frist beginnt mit **Ende des Kalenderjahres**, in dem das Dokument entstanden ist. Beispiel: Eine Rechnung vom 14.10.2026 darf ab dem 1.1.2035 vernichtet werden.
- ⚠️ Für ältere Belege aus der Zeit vor 2025 gibt es eine Übergangsregel, die die Quellen unterschiedlich beschreiben. Löschen Sie Altbestände nur nach Rücksprache.
- Elektronisch erhaltene Dokumente (E-Mail-PDF, E-Rechnung-XML) müssen **elektronisch** aufbewahrt werden. Ein Ausdruck genügt nicht.

## 4. GoBD – was das Tool leistet

Die GoBD (Grundsätze ordnungsmäßiger Buchführung in elektronischer Form) verlangen vor allem:
Unveränderbarkeit, Nachvollziehbarkeit, Vollständigkeit, zeitgerechte Erfassung, Datenzugriff fürs Finanzamt
und eine Verfahrensdokumentation.

| GoBD-Anforderung | Umsetzung im Tool |
|---|---|
| Unveränderbarkeit | Festgeschriebene Rechnungen sind in der Datenbank gegen Ändern und Löschen gesperrt (Datenbank-Trigger, nicht nur Oberfläche). Korrekturen gehen nur über eine Stornorechnung. |
| Lückenlose Nummern | Die Nummer wird erst beim Festschreiben vergeben, in einer einzigen Transaktion. Schlägt ein Schritt fehl, wird keine Nummer verbraucht. Nummernkreise lassen sich nicht zurücksetzen. |
| Original-Archiv | Das PDF wird beim Festschreiben einmalig erzeugt und archiviert, mit SHA-256-Prüfsumme. Zusätzlich speichert das Tool alle Rechnungsdaten als „Schnappschuss“. Spätere Änderungen an Logo, Kunde oder Preisen ändern alte Rechnungen nicht. |
| Protokollierung | Jeder wichtige Vorgang (Anlegen, Festschreiben, Storno, Versand, Einstellungsänderungen, fehlgeschlagene Anmeldungen) wird mit Zeitstempel protokolliert. Die Einträge sind über Prüfsummen verkettet, sodass ein gelöschter oder veränderter Eintrag auffällt. |
| Versandnachweis | Das Versandprotokoll hält Empfänger, Betreff, Text, Prüfsumme des Anhangs und Erfolg oder Fehler fest. |
| Kontrolle | Die Seite *Datenprüfung* prüft PDFs, Nummernfolge und Protokollkette. |

## 5. Ehrlich: Grenzen gegenüber gekaufter Software (z. B. Lexware)

1. **Keine Prüfung durch Dritte.** Eine amtliche GoBD-Zertifizierung gibt es nicht. Große Anbieter lassen ihre Software aber von Wirtschaftsprüfern testieren (z. B. nach IDW PS 880). Für dieses Tool gibt es so ein Testat nicht. Verantwortlich für die Ordnungsmäßigkeit sind **immer Sie**, auch mit Lexware.
2. **Technische Manipulation ist nicht unmöglich.** Wer Administratorrechte am PC hat, kann die Datenbankdatei mit Spezialwerkzeugen bearbeiten. Das Tool **erkennt** viele solcher Eingriffe (Prüfsummen, Protokollkette), kann sie aber nicht physisch verhindern. Wer *alles* konsequent neu berechnet, könnte unentdeckt bleiben. Das gilt grundsätzlich auch für andere lokale Software.
   → Mehr Sicherheit bringen regelmäßige Backups auf das NAS mit Versionierung bzw. Schreibschutz. Die alten Stände dienen dann als Vergleich.
3. **Verfahrensdokumentation fehlt noch.** Die GoBD verlangen eine schriftliche Beschreibung, wie Belege erfasst, gebucht, archiviert und gesichert werden. Diese muss **Sie** erstellen. Ich liefere in Etappe 5 eine ausgefüllte Vorlage, die Sie nur noch anpassen.
4. **Datenzugriff fürs Finanzamt.** Bei einer Prüfung muss das Finanzamt die Daten maschinell auswerten können. Den Export (CSV und PDF) baue ich in Etappe 5. ⚠️ Ob zusätzlich ein Export im „Beschreibungsstandard für die Datenüberlassung“ nötig ist, bitte klären.
5. **Barzahlung bei Abholung ⚠️ (wichtig).** Bargeldeinnahmen sind täglich aufzuzeichnen. Ein **elektronisches** System mit Kassenfunktion braucht eine zertifizierte technische Sicherheitseinrichtung (TSE, KassenSichV). Dieses Tool ist **keine Kasse und hat keine TSE**. Ab Etappe 3 können Sie eine Rechnung als „bar bezahlt“ markieren. Ob das für Sie unkritisch ist, z. B. bei einer offenen Ladenkasse mit Kassenbericht und Rechnung für jede Barzahlung, oder ob Sie dafür etwas anderes brauchen, **müssen Sie unbedingt mit dem Steuerberater oder Finanzamt klären.**
6. **Stammdaten-Historie.** Änderungen an Kunden und Artikeln werden protokolliert, aber ohne die alten Werte. Für die Rechnungen ist das unerheblich, weil sie ihren eigenen Schnappschuss haben.
7. **Zeitstempel** stammen von der PC-Uhr und sind kein qualifizierter Zeitstempel. Die Windows-Uhrzeit sollte automatisch gestellt werden (Standard).
8. **Einzelplatz:** Das Tool ist für eine Person gedacht. Eine Benutzerverwaltung mit Rechten gibt es nicht.

## 6. Datenschutz und Löschkonzept

**Umgesetzt:**
- Alle Daten liegen **nur lokal** im Ordner `Daten`. Es gibt keine Cloud, und das Tool sendet nichts nach außen, außer den E-Mails, die Sie selbst verschicken.
- Das Programm ist nur am eigenen PC erreichbar (`127.0.0.1`), nicht von anderen Geräten. Ein Passwortschutz ist auf Wunsch abgeschaltet und kann unter *Einstellungen → Passwortschutz* eingeschaltet werden (gespeichert wird dann nur ein sicherer Hash). Ohne Passwort ist die Windows-Anmeldung mit PIN/Passwort und Bildschirmsperre der Schutz – bitte unbedingt nutzen.
- Das E-Mail-Passwort wird verschlüsselt gespeichert (AES über die Bibliothek *cryptography*). Der Schlüssel liegt in `Daten\geheim` und ist **nicht** im Backup. Wer allerdings vollen Zugriff auf Ihren PC hat, kann ihn verwenden.
  → Empfehlung: Windows-Anmeldung mit Passwort/PIN und **Geräteverschlüsselung bzw. BitLocker** aktivieren (*Einstellungen → Datenschutz und Sicherheit → Geräteverschlüsselung*).
- Backups enthalten Kundendaten. Der NAS-Ordner sollte deshalb nur für Sie zugänglich sein.

**Löschkonzept:**

| Daten | Regel |
|---|---|
| Kunde ohne festgeschriebene Rechnung (z. B. nur Anfrage) | Jederzeit vollständig löschbar (*Kunde → Löschen*) |
| Kunde mit Rechnungen | Nicht löschbar, solange die Aufbewahrungsfrist läuft (DSGVO Art. 17 Abs. 3 lit. b). Stattdessen **archivieren**, sodass der Kunde nicht mehr in Listen und Auswahlfeldern erscheint. |
| Nach Ablauf der Fristen (8 bzw. 10 Jahre nach Jahresende der letzten Rechnung) | Kundendaten anonymisieren, Rechnungen und PDFs löschen. → Eine Funktion „abgelaufene Daten anzeigen und löschen“ kommt in Etappe 5. |
| Backups | Werden automatisch nach der eingestellten Anzahl (Standard 30) überschrieben. |
| Löschanfrage eines Kunden | Daten ohne Aufbewahrungspflicht löschen (Notizen, Telefon, E-Mail können Sie leeren). Den Rest archivieren und dem Kunden mitteilen, dass die Daten bis zum Fristende gesperrt aufbewahrt werden. |

⚠️ Datenschutzerklärung (Website, Anfrageformular), Verzeichnis von Verarbeitungstätigkeiten und ggf. ein
Auftragsverarbeitungsvertrag mit Ihrem E-Mail-Anbieter sind Ihre Aufgabe. Das Tool kann das nicht ersetzen.

## 7. Mit Steuerberater oder Finanzamt klären

1. **Barzahlungen bei Abholung:** offene Ladenkasse, Kassenbericht, ist eine TSE nötig? (siehe Punkt 5.5)
2. Reicht die Steuernummer auf der Rechnung, oder wird eine Kleinunternehmer-ID nötig (nur bei EU-Geschäften relevant)?
3. Wie wird die Kleinunternehmergrenze genau berechnet, und wann wird die Umstellung auf Regelbesteuerung fällig?
4. Ist die Verfahrensdokumentation (Vorlage folgt in Etappe 5) so ausreichend?
5. Welches Exportformat wird im Fall einer Betriebsprüfung gebraucht?
6. Übergangsregeln bei den Aufbewahrungsfristen für Belege aus der Zeit vor 2025, bevor Sie etwas vernichten.
7. Die Gewährleistungs- und Haftungstexte für Reparaturen (eher eine Frage für einen Rechtsanwalt oder die Handwerkskammer).

## Quellen (Recherche Oktober 2026)

- [§ 34a UStDV – dejure.org](https://dejure.org/gesetze/UStDV/34a.html), [NWB](https://datenbank.nwb.de/Dokument/78926_34a/), [Haufe](https://www.haufe.de/id/norm/umsatzsteuer-durchfuehrungsverordnung-34a-rechnungen-von-kleinunternehmern-HI775669_p34a.html), [gesetze-im-internet.de](https://www.gesetze-im-internet.de/ustdv_1980/__34a.html)
- [ZDH – Anforderungen an Rechnungen](https://www.zdh.de/presse/publikationen/info-flyer/aktualisierter-flyer-zur-umsatzsteuer-anforderungen-an-rechnungen/?L=0)
- [ZDH – Elektronische Rechnung](https://www.zdh.de/ueber-uns/fachbereich-steuern-und-finanzen/elektronische-rechnung/), [IHK Rhein-Neckar – E-Rechnungspflicht](https://www.ihk.de/rhein-neckar/recht/steuerrecht/umsatzsteuer/e-rechnungspflicht-5931752), [Haufe – E-Rechnung](https://www.haufe.de/wissen/finance/e-rechnung), [ETL – Zeitplan](https://www.etl.de/e-rechnung/zeitplan/)
- [IHK Karlsruhe – 4. Bürokratieentlastungsgesetz](https://www.ihk.de/karlsruhe/fachthemen/steuerrecht/aktuelles/neuer-inhalt4-buerokratieentlastungsgesetz-6347138), [Forum Verlag – Aufbewahrungsfristen](https://forum-verlag.com/aufbewahrungsfristen)
- [steuerberater-dill.de – Hinweis in der Rechnung](https://steuerberater-dill.de/2025/07/29/ein-hinweis-in-der-rechnung-muss-sein/)
