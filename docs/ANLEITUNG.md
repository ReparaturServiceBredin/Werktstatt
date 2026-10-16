# Bedienungsanleitung

## 1. Erste Schritte

1. `Werkstatt-Sauter.exe` starten. Die Buchhaltung öffnet sich als eigenes Fenster; das Programmsymbol neben der
   Uhr zeigt, dass sie läuft (Rechtsklick → Beenden). Ein Passwort ist standardmäßig aus
   (einschaltbar unter *Einstellungen → Passwortschutz*).
2. **Einstellungen → Firmendaten:** Anschrift, Telefon, Steuernummer, Bank und IBAN eintragen.
   Diese Angaben erscheinen in der Fußzeile jeder Rechnung.
3. **Einstellungen → E-Mail (Versand und IMAP):** Den Zugang zu Ihrem Postfach eintragen und mit „Test-E-Mail senden“ prüfen.
4. **Leistungen & Artikel:** Ihre Festpreise anlegen, z. B. „Kaffeemaschinen-Wartung“ für 89 €.

### Bedienung: Menü, Schnellsuche, Benachrichtigungen

- **Menü links**, in Gruppen: Werkstatt, Kunden, Verkauf, Einkauf & Lager, Buchhaltung.
  - Eine Gruppe klappen Sie per Klick auf die Überschrift ein und aus. Das Programm merkt sich das. Die Gruppe der
    gerade geöffneten Seite ist immer offen.
  - „Seitenleiste einklappen“ (unten) zeigt nur noch Symbole. Fahren Sie mit der Maus über ein Symbol, erscheint der
    Name.
  - Am Handy öffnen Sie das Menü über ☰ oben links.
- **Zusammengefasste Seiten mit Reitern:**
  - *Rechnungen*: Rechnungen, Kostenvoranschläge, Offene Posten, Mahnwesen.
  - *Einkauf*: Bestellungen, Lieferanten, Eingangsrechnungen.
- **Schnellsuche:** Oben „Suchen oder springen …“ oder **Strg+K**. Gefunden werden Seiten, Einstellungen (z. B.
  „SMTP“, „Backup“), Kunden (Name, E-Mail, Telefon), Aufträge (Nummer, Gerät, Seriennummer), Rechnungen und KVAs
  (Nummer), Artikel und Leihgeräte. Mit ↑/↓ wählen, mit Enter öffnen.
- **+ Neu** (oben rechts): Auftrag, Kunde, KVA, Rechnung, Leihgerät ausgeben.
- **Glocke:** Die letzten Kundenbenachrichtigungen. Die Zahl nennt Vorschläge und Fehler, die Sie noch nicht angesehen
  haben. „Alle als gelesen“ setzt sie zurück; die Vorschläge warten trotzdem weiter auf Ihre Freigabe.
- **Mond/Sonne:** Hell oder dunkel, wird gemerkt.
- **Einstellungen:** Links die Bereiche, oben ein Suchfeld (z. B. „IMAP“ springt zum Feld und hebt es hervor).
  - Der Knopf „Speichern“ bleibt unten sichtbar.
  - Wollen Sie eine Seite mit ungespeicherten Änderungen verlassen, fragt das Programm nach.
  - Textbausteine, Datenschutz-Übersicht, Protokoll, Datenprüfung, Verfahrensdokumentation und Versionsprotokoll
    finden Sie dort unter „Verwaltung & Prüfung“.

## 2. Eine Rechnung schreiben

1. **Rechnungen → + Neue Rechnung** (oder beim Kunden „+ Rechnung für diesen Kunden“).
2. Den Kunden wählen. Das Zahlungsziel wird automatisch gesetzt: 14 Tage für Privat- und 30 Tage für Firmenkunden.
3. Das **Leistungsdatum** eintragen, also den Tag der Reparatur.
4. Positionen hinzufügen:
   - über **„Leistung/Artikel aus Liste einfügen“** oder
   - über **„+ Freie Position“** für Einzelfälle.

   Zu jeder Position sehen Sie Teilekosten und Marge. Diese Werte erscheinen **nicht** auf der Rechnung.
5. **Speichern & Vorschau** zeigt das PDF mit dem Aufdruck „ENTWURF“.
6. **Festschreiben & Nummer vergeben** gibt der Rechnung die nächste Nummer (z. B. `RE-2026-0001`) und archiviert das PDF.
   **Ab diesem Moment ist die Rechnung nicht mehr änderbar.**
7. Danach stehen diese Knöpfe zur Verfügung:
   - **Per E-Mail senden:** Die Rechnung geht als PDF-Anhang an den Kunden, mit dem Standardtext aus den Textbausteinen.
   - **Drucken:** Das PDF öffnet sich mit dem Druckdialog.
   - **PDF herunterladen**

### Fehler in einer festgeschriebenen Rechnung?

Löschen oder Ändern ist absichtlich nicht möglich (siehe GoBD). So gehen Sie stattdessen vor:

1. Die Rechnung öffnen und auf **Stornieren** klicken. Es entsteht eine **Stornorechnung** mit eigener Nummer und negativem Betrag.
2. **Als neue Rechnung kopieren** übernimmt alle Positionen in einen neuen Entwurf. Dort korrigieren Sie den Fehler und schreiben die neue Rechnung fest.
3. Schicken Sie dem Kunden beides: die Stornorechnung und die neue Rechnung.

## 3. Layout ändern (ohne Programmierung)

Unter **Einstellungen → Layout & Dokumente** zeigt rechts eine Musterrechnung, wie das Ergebnis aussieht.

| Einstellung | Wirkung |
|---|---|
| Hauptfarbe | Titel, Tabellenkopf, Linien (Standard: Blau aus Ihrem Logo `#1C54A3`) |
| Zweitfarbe | Grautöne für kleine Texte |
| Schrift | Montserrat (wie im Logo), Open Sans, Lato, Helvetica, Times |
| Schriftgröße | Grundgröße in Punkt (Standard 9,5) |
| Logo, Logobreite, Position | Eigenes Logo hochladen (PNG mit transparentem Hintergrund ist ideal), Breite in mm, links/mitte/rechts |
| Kopfzeile / zusätzliche Fußzeile | Freier Text, z. B. Öffnungszeiten |
| Falzmarken | Kleine Striche am linken Rand zum Falten für Fensterumschläge |
| GiroCode | QR-Code, den der Kunde mit seiner Banking-App scannt (IBAN, Betrag und Rechnungsnummer sind dann schon ausgefüllt) |

Nach **Speichern** auf **Vorschau aktualisieren** klicken.

> Layout-Änderungen gelten nur für **neue** Rechnungen. Bereits festgeschriebene Rechnungen bleiben unverändert,
> denn ihr Original-PDF ist archiviert.

Die Fußzeile wird automatisch aus den Firmendaten gebaut (Anschrift, Kontakt, Bank, Steuernummer).

## 4. Textbausteine

Unter **Textbausteine** verwalten Sie diese Texte:

- **Einleitung** (über den Positionen), **Schlusstext** (unter der Rechnung), **Hinweise** (klein gedruckt)
- **E-Mail-Betreff** und **E-Mail-Text** für den Versand

Ein Baustein mit Haken bei **Standard** wird automatisch in jede neue Rechnung bzw. E-Mail übernommen.
Alle anderen fügen Sie beim Schreiben einer Rechnung über das Auswahlfeld „Textbaustein einfügen …“ ein.

**Platzhalter** werden automatisch ersetzt. Die vollständige Liste steht beim Bearbeiten eines Bausteins. Die wichtigsten:

| Platzhalter | Beispiel |
|---|---|
| `{anrede_brief}` | Sehr geehrte Frau Müller, |
| `{nummer}` | RE-2026-0001 |
| `{datum}` / `{faellig_am}` | 14.10.2026 / 28.10.2026 |
| `{betrag}` | 307,80 € |
| `{inhaber}` / `{firma_name}` | Dennis Bredin / Reparatur Service Bredin |

Die mitgelieferten Bausteine „Datensicherung“ und „Gewährleistung“ sind **Beispieltexte**.
Bitte ersetzen Sie sie durch Ihre eigenen Texte und lassen Sie rechtliche Formulierungen im Zweifel prüfen.

## 5. E-Mail-Einstellungen

| Anbieter | SMTP-Server | Port | Verschlüsselung |
|---|---|---|---|
| IONOS (1&1) | smtp.ionos.de | 587 | STARTTLS |
| Strato | smtp.strato.de | 465 | SSL |
| GMX | mail.gmx.net | 587 | STARTTLS |
| web.de | smtp.web.de | 587 | STARTTLS |
| Gmail | smtp.gmail.com | 587 | STARTTLS (nur mit „App-Passwort“) |

Bitte prüfen Sie die Werte bei Ihrem Anbieter. Benutzername ist meist die vollständige E-Mail-Adresse.

**Kopie im Ordner „Gesendet“ (IMAP):** Darunter im Abschnitt *IMAP* den Haken „Gesendete Mails im Postfach
ablegen“ setzen, `imap.ionos.de`, Port 993, SSL/TLS. „Gleiche Zugangsdaten wie SMTP“ angehakt lassen. Dann
**„Ordner abrufen“** (wählt „Gesendete Objekte“ vor) → **„Verbindung testen“** → Speichern. Danach liegt jede
versendete Rechnung auch im Postfach unter „Gesendet“. Klappt die Ablage einmal nicht, ist die Mail trotzdem
verschickt – Sie sehen dann einen gelben Hinweis.

**Fehler „Zielcomputer verweigerte die Verbindung“ (WinError 10061):** Das Programm versucht es automatisch ein
zweites Mal. Bleibt der Fehler, blockiert meist ein Virenschutz den Versand aus Programmen (z. B. ESET
„E-Mail-Client-Schutz“ bzw. Firewall-Regel). Dann `Werkstatt-Sauter.exe` dort als vertrauenswürdig freigeben.
Das Passwort wird verschlüsselt gespeichert.
„Kopie an mich (BCC)“ legt jede versendete Rechnung zusätzlich in Ihrem Postfach ab.
Jeder Versand und jeder Fehlversuch steht unter **Protokoll**.

## 6. Backup und Wiederherstellung

**Datenordner:** Alle Daten liegen an einem festen Ort, egal von wo das Programm gestartet wird (Windows:
`%LOCALAPPDATA%\Werkstatt-Sauter\Daten`). Öffnen: Rechtsklick auf das Symbol neben der Uhr → „Daten-Ordner öffnen“.

**Automatisch:** Beim Programmstart entsteht einmal täglich eine ZIP-Datei im Unterordner `backups` des Datenordners.
Die letzten 30 Backups bleiben erhalten (einstellbar).

**NAS:** Unter *Einstellungen → Backup* tragen Sie einen zweiten Ordner ein, z. B. `\\NAS\Backup\Buchhaltung`
oder ein Netzlaufwerk wie `Z:\Backup\Buchhaltung`. Jedes Backup wird dorthin kopiert.
**Empfehlung:** Zusätzlich gelegentlich auf einen USB-Stick kopieren, der nicht dauerhaft am PC steckt (Schutz vor Verschlüsselungstrojanern).

**Manuell:** *Einstellungen → Backup → Backup jetzt erstellen*.

**Wiederherstellen auf demselben PC:** *Einstellungen → Backup → Sicherung wiederherstellen*. Jede Sicherung wird mit
ihrem Inhalt angezeigt; vorher wird der aktuelle Stand vollständig gesichert.

**Wiederherstellen auf einem neuen PC:**
1. `Werkstatt-Sauter.exe` irgendwohin legen und einmal starten, dann über das Symbol neben der Uhr beenden.
2. Die Backup-ZIP in den Datenordner (`%LOCALAPPDATA%\Werkstatt-Sauter\Daten`) entpacken und vorhandene Dateien
   ersetzen.
3. Die EXE starten (falls der Passwortschutz eingeschaltet war: mit dem bisherigen Passwort anmelden).
4. Unter *Einstellungen → E-Mail* das E-Mail-Passwort **neu eingeben**. Der Schlüssel dafür ist aus Sicherheitsgründen nicht im Backup enthalten.
5. Unter **Datenprüfung** kontrollieren, ob alles „In Ordnung“ ist.

Eine Wiederherstellung per Knopfdruck kommt in Etappe 5.

## 7. Datenprüfung

Die Seite **Datenprüfung** prüft drei Dinge:
- Sind alle archivierten PDFs unverändert? Das wird über eine Prüfsumme kontrolliert.
- Sind alle vergebenen Rechnungsnummern lückenlos vorhanden?
- Ist das Änderungsprotokoll vollständig und unverändert?

Rufen Sie sie z. B. einmal im Monat und vor jeder Weitergabe an das Finanzamt auf.

## 8. Umstellung auf Umsatzsteuer (später)

Unter *Einstellungen → Rechnung & Steuer → Besteuerung* auf **Regelbesteuerung** umstellen. Die Folgen:
- Preise in Leistungen und Artikeln gelten dann als **Nettopreise**. Jede Leistung hat einen Steuersatz (Standard 19 %).
- Neue Rechnungen zeigen Netto, USt je Steuersatz und Brutto. Der § 19-Hinweis entfällt.
- Bereits festgeschriebene Rechnungen bleiben unverändert.

Den Zeitpunkt der Umstellung bitte mit dem Finanzamt bzw. einem Steuerberater abstimmen.
Prüfen Sie dann auch Ihre Preise, denn bisher sind es Endpreise.

## 9. Kunden löschen (Datenschutz)

- Kunden **ohne** festgeschriebene Rechnungen können Sie vollständig löschen.
- Kunden **mit** Rechnungen müssen wegen der Aufbewahrungspflicht erhalten bleiben. Sie lassen sich **archivieren** und verschwinden dann aus den Listen.
- Das vollständige Löschkonzept steht in [RECHT_UND_GOBD.md](RECHT_UND_GOBD.md#datenschutz-und-löschkonzept).

## 10. Anfragen aus dem Kontaktformular

Wer auf www.reparatur-bredin.de das Kontaktformular ausfüllt, erzeugt eine E-Mail an kontakt@reparatur-bredin.de.
Das Tool holt diese E-Mails selbst ab und wertet sie aus:

1. Es liest die Felder **Name, Telefon, Email, Geraet und Nachricht**.
   Vor- und Nachname werden automatisch getrennt, auch bei „Kochendörfer Kai“, also Nachname zuerst.
2. Es vergibt **Punkte** nach festen Regeln. Für Spam sprechen zum Beispiel Links, Werbewörter wie SEO oder Krypto,
   Zeichensalat, fremde Schriftzeichen, ungültige Kontaktdaten und englische Werbetexte. Für eine echte Anfrage sprechen
   Wörter wie Display, Akku, Jura, Laptop, defekt oder eine deutsche Telefonnummer.
   Unter jeder Anfrage steht, wie die Punkte zustande kamen.
3. Das Ergebnis:
   - **Echte Anfrage:** Der Kunde wird automatisch als **Interessent** angelegt, die Anfrage steht in seinen Notizen.
     Gibt es die E-Mail-Adresse oder Telefonnummer schon, wird die Anfrage dem **vorhandenen** Kunden zugeordnet.
   - **Unsicher:** Die Anfrage erscheint unter *Anfragen → Zu prüfen*. Sie können den Namen korrigieren und mit
     einem Klick den Kunden anlegen. Alternativ verwerfen oder als Spam markieren.
   - **Spam:** Es wird kein Kunde angelegt. Spam wird nach 30 Tagen automatisch gelöscht.
4. Schreiben Sie dem Interessenten eine Rechnung, wird er automatisch zum normalen Kunden.
5. Interessenten ohne Auftrag schlägt das Tool nach 6 Monaten (einstellbar) zum Löschen vor (Datenschutz).

Neue Anfragen sehen Sie in der Navigation an der roten Zahl neben **Anfragen** und auf der Übersicht.

### Einrichtung (Einstellungen → Anfragen)

| Feld | Eintrag |
|---|---|
| IMAP-Server | `imap.ionos.de` |
| Port / Verschlüsselung | `993` mit **SSL/TLS** – oder, falls Port 993 in Ihrem Netz gesperrt ist, `143` mit **STARTTLS** |
| Benutzername / Passwort | leer lassen, dann werden die Zugangsdaten vom E-Mail-Versand verwendet |
| Ordner | `INBOX` (Posteingang) |
| Erledigte verschieben nach | `Anfragen erledigt` (der Ordner wird automatisch angelegt) |
| Formular-E-Mails erkennen am Text | `A new form has been submitted` |

Mit **„Verbindung testen“** prüfen Sie sofort (auch vor dem Speichern) Verbindung, Anmeldung und ob die Ordner
„INBOX“ und „Anfragen erledigt“ vorhanden sind. Beim Wechsel der Verschlüsselung schlägt das Programm den passenden Port
vor. Beide Varianten sind verschlüsselt: Bei STARTTLS meldet sich das Programm erst an, nachdem die Verbindung
verschlüsselt ist. Klappt das nicht, bricht es ab und sendet das Passwort nie unverschlüsselt.

Dann den Haken **„Postfach automatisch prüfen“** setzen und einmal **„Postfach jetzt prüfen“** klicken.
Andere E-Mails im Postfach werden **nicht** angefasst.

**Wichtig – Weiterleitung an Gmail:** Das Tool liest bei IONOS nur E-Mails, die dort auch **gespeichert**
bleiben. Prüfen Sie im IONOS-Webmail bzw. Kundenkonto bei der Weiterleitung von kontakt@ an Gmail, dass
**„Kopie im Postfach behalten“** (oder ähnlich) eingeschaltet ist. Ist kontakt@ nur eine reine Weiterleitung
ohne eigenes Postfach, tragen Sie stattdessen Gmail ein: `imap.gmail.com`, Port 993, Benutzer
reparatur-bredin@gmail.com. Als Passwort dient dort ein **App-Passwort**
(Google-Konto → Sicherheit → 2-Faktor-Bestätigung → App-Passwörter).

**Ohne Postfach-Zugang oder zum Testen:** Über *Anfragen → Anfrage einfügen* den Text einer Formular-E-Mail
hineinkopieren. Die Anfrage wird genauso geprüft.

Die Anfragen werden nur abgeholt, **solange das Programm läuft**. Beim nächsten Start holt das Tool alles nach,
was in den letzten 60 Tagen eingegangen ist.

## 11. Reparaturaufträge (Tafel) und Kostenvoranschläge

Unter **Verkauf → Reparaturaufträge** sehen Sie alle Aufträge auf einer Tafel mit drei Spalten:
**Offen → In Arbeit → Erledigt**. Die Übersicht zeigt die Anzahl je Spalte.

**Auftrag anlegen** – drei Wege:
- auf der Tafel über **„+ Neuer Auftrag“**. Sie geben Kunde, Status, Gerät, Seriennummer/IMEI, Zubehör, Fehler und
  Notizen ein. Optional verknüpfen Sie gleich einen KVA und laden Fotos hoch. Fotos werden sofort gespeichert. Klappt
  das Anlegen einmal nicht (z. B. Kunde vergessen), bleiben Fotos und Eingaben erhalten.
- aus einer **Anfrage** über „Reparaturauftrag anlegen“. Gerät und Fehlerbeschreibung werden übernommen.
- beim **Kunden** über „+ Reparaturauftrag“ (der Kunde ist dann schon ausgewählt).

**Auftrag öffnen:** Klicken Sie auf eine Karte. Kopf mit Nummer, Status und Eingang, darunter vier Reiter:
- **Auftragsdaten** – alles bearbeitbar, auch Kunde und Status, mit „Speichern“.
- **Kostenvoranschlag** – siehe unten.
- **Fotos** – Kategorie wählen, dann Fotos hineinziehen, „Dateien auswählen“ oder am Handy „Kamera“. Zu jedem Foto
  sehen Sie Upload-Zeit (mit Sekunden), Aufnahmezeit der Kamera, Benutzer und Prüfsumme. **Löschen** geht nur
  mit Begründung: das Foto wird grau markiert, bleibt aber gespeichert. **„Fotodokumentation als PDF“** erzeugt
  ein PDF aller Fotos mit diesen Angaben, z. B. für Versicherung oder Reklamation.
- **Verlauf** – wer wann was gemacht hat (angelegt, Status, KVA, Fotos, Rechnung). Nicht änderbar.

**Kostenvoranschlag (KVA):**
- Noch keiner verknüpft:
  - **„Neuen KVA aus diesem Auftrag erstellen“** – Kunde, Gerät und Fehler sind schon eingetragen.
  - oder unter **„Bestehenden KVA verknüpfen“** einen vorhandenen auswählen. Angezeigt werden freie KVAs des Kunden.
    Sie können nach Nummer, Datum oder Betrag suchen oder „alle Kunden anzeigen“ wählen.
- Verknüpft: Nummer, Datum, Betrag und Status (offen / angenommen / abgelehnt – nach Rückmeldung des Kunden
  einstellen), dazu Öffnen, PDF, Per E-Mail senden und **Verknüpfung lösen**. Der KVA selbst bleibt dabei erhalten.
- Gehört der KVA zu einem anderen Kunden als der Auftrag, erscheint ein gelber Warnhinweis.
- Positionen fügen Sie ein wie bei einer Rechnung. Danach **festschreiben**, dann bekommt er eine Nummer
  (`KV-2026-0001`), und **per E-Mail senden**. Die Gültigkeit beträgt standardmäßig 30 Tage
  (*Einstellungen → Rechnung & Steuer*).
- Die Karten auf der Tafel zeigen **📷 Anzahl** und **„KVA ✓“** bzw. **„kein KVA“**.

**Verschieben:** Ziehen Sie eine Karte mit der Maus in eine andere Spalte.
Ohne Maus, zum Beispiel auf dem Tablet, nutzen Sie die Knöpfe auf der Karte („Starten →“, „Erledigt ✓“, „←“).
Innerhalb einer Spalte können Sie die Reihenfolge ebenfalls per Ziehen ändern.

**Erledigt → Rechnung:** Ziehen Sie einen Auftrag auf **Erledigt**, dann passiert Folgendes:
1. Es entsteht automatisch ein **Rechnungsentwurf**, mit allen Positionen aus dem KVA, dem Kunden, dem Gerät
   und der Seriennummer im Betreff und dem heutigen Tag als Leistungsdatum.
2. Der Entwurf öffnet sich sofort. Sie prüfen ihn (z. B. ob noch ein Teil dazukam) und klicken auf
   **„Festschreiben & Nummer vergeben“**.

Ist **kein KVA verknüpft**, fragt das Programm vorher: *„Kein KVA verknüpft – leeren Rechnungsentwurf erstellen
oder KVA jetzt verknüpfen?“*. „KVA jetzt verknüpfen“ öffnet den Reiter Kostenvoranschlag des Auftrags.

Die Rechnung wird bewusst **nicht ungefragt festgeschrieben**. Eine festgeschriebene Rechnung lässt sich nur noch
stornieren. Ein versehentlicher Zug auf „Erledigt“ soll keine Rechnungsnummer verbrauchen.
Wird ein Auftrag zurück- und wieder auf „Erledigt“ gezogen, entsteht **keine** zweite Rechnung.

Die Spalte „Erledigt“ zeigt die letzten 30 Tage, ältere Aufträge über „alle anzeigen“.

## 12. Verträge, Lizenzen & Garantien (MSP, ESET, Wertgarantie)

Unter **Verkauf → Verträge & Lizenzen** und beim jeweiligen **Kunden** (Abschnitt „Verträge, Lizenzen & Garantien“).

**Neuer Vertrag:** Beim Kunden auf „+ Vertrag / Lizenz“ klicken, eine **Vorlage** wählen (füllt alles vor),
Lizenzschlüssel bzw. Policennummer und ggf. Gerät eintragen, speichern.

| Beispiel | Abrechnung | Ergebnis |
|---|---|---|
| Wertgarantie | nur Dokumentation | keine Rechnung; Ablauf wird überwacht |
| ESET 1/2/3 Jahre | einmal je Laufzeit (12/24/36 Monate) | eine Rechnung zum Beginn; vor Ablauf Erinnerung, Verlängern per Knopf (oder automatisch) |
| MSP-Paket | monatlich | jeden Monat im Voraus, bis zur Kündigung |

**Vertragsarten erweitern:** *Verträge & Lizenzen → Vertragsarten → + Neue Vertragsart* – z. B.
„ESET Internet Security 3 Geräte, 1 Jahr“ mit Preis und Einkauf. Steht danach sofort als Vorlage bereit.

**Abrechnung:** Das Programm prüft täglich, was fällig ist, und erstellt **je Kunde eine Rechnung** mit allen
fälligen Positionen (inkl. Zeitraum und Lizenznummer). Unter *Einstellungen → Verträge* wählen Sie:
- **Automatisch** (eingestellt): festschreiben und per E-Mail an den Kunden (E-Mail-Zugang und Kunden-E-Mail
  nötig; fehlt die Kunden-E-Mail, wird die Rechnung nur festgeschrieben und im Protokoll vermerkt).
- **Entwurf:** Sie prüfen unter *Rechnungen & KVA → Entwürfe* und schreiben selbst fest.

**Kündigen:** Vertrag öffnen → „Kündigen“: Eingangsdatum, **Vertrag endet zum** (Vorschlag: Ende der laufenden
Periode bzw. Mindestlaufzeit), Grund. Bis zu diesem Datum wird noch berechnet, danach nicht mehr.
„Kündigung zurücknehmen“ macht das rückgängig.

**Bestehende Verträge übernehmen:** Beginn wie im Original eintragen und **„Bereits berechnet bis“** setzen
(z. B. Ende des letzten in Lexware berechneten Monats) – sonst würden vergangene Monate nachberechnet.

## 13. Leistungen und Artikel automatisch füllen

- Positionen, die Sie in einem KVA oder einer Rechnung **von Hand** eingeben, landen beim Speichern automatisch in
  *Leistungen & Artikel* – inklusive Beschreibung, Einkaufspreis und Marge. Beim nächsten Mal einfach aus der Liste
  einfügen.
- Für einmalige Sonderpositionen den Haken **„In Leistungen und Artikel speichern“** unter der Position entfernen.
- Gibt es die Bezeichnung schon mit anderem Preis, fragt das Programm: **„Preise im Katalog aktualisieren?“**
- Alte Dokumente: *Leistungen & Artikel → „Aus bisherigen Dokumenten übernehmen“* – Vorschau prüfen, abhaken,
  übernehmen.
- **Beschreibung:** Im Artikel beliebig lang und mehrzeilig (z. B. Anschlüsse, Maße, Kompatibilität). Beim Einfügen
  in ein Dokument wird sie übernommen und kann dort gekürzt werden – der Katalog bleibt unverändert.

## 14. Leihgeräte

Unter **Verkauf → Leihgeräte** verwalten Sie Geräte, die Kunden während einer Reparatur bekommen.

**Gerät anlegen:** „+ Neues Leihgerät“. Tragen Sie Bezeichnung (z. B. „Lenovo ThinkPad T14 #1“), Seriennummer,
Inventarnummer und das Zubehör ein (eins je Zeile, z. B. Netzteil, Tasche, Maus). Dazu kommt der **Zeitwert**, der
bei Verlust oder Totalschaden angesetzt wird, und die Standard-Leihgebühr: kostenlos, pauschal oder pro Tag. Bei „pro
Tag“ können die ersten Tage kostenlos sein. Optional geben Sie eine Kaution an. Fotos des Geräts laden Sie im Reiter
„Fotos“ hoch.

**Ausgeben:** im Reparaturauftrag Reiter **„Leihgerät“** → **„Leihgerät ausgeben“**.
1. Ein verfügbares Gerät wählen. Leihgebühr, Kaution und Zubehör werden vom Gerät übernommen und lassen sich für
   diesen Fall ändern, auch auf „kostenlos (Kulanz)“.
2. Voraussichtliche Rückgabe eintragen und das mitgegebene Zubehör abhaken.
3. Zustand notieren und Fotos machen (am Handy über „Kamera“).
4. „Leihgerät ausgeben“. Danach **„Leihvertrag / Übergabeprotokoll (PDF)“** drucken und vom Kunden unterschreiben
   lassen, oder per E-Mail senden.

Die Leihbedingungen im Vertrag ändern Sie unter *Einstellungen → Leihgeräte*. Lassen Sie diesen Text im Zweifel
einmal rechtlich prüfen.

**Zurücknehmen:** im Auftrag oder in der Leihgeräte-Übersicht **„Leihgerät zurücknehmen“**.
- Zubehör abhaken: was nicht abgehakt ist, gilt als fehlend.
- Zustand wählen und Fotos machen. Die Ausgabe-Fotos stehen zum Vergleich daneben.
- Die Leihgebühr wird berechnet. Beispiel: 5 Tage, 3 frei, 5 € pro Tag = 2 × 5 € = 10 €. Sie können den Betrag vor
  dem Speichern ändern.
- Bei Schaden oder fehlendem Zubehör erscheint der Bereich **Schadensfall**: Beschreibung, Kostenart, Betrag (bei
  Totalschaden mit dem Zeitwert vorbelegt) und Schadensfotos. Mit dem Haken „internen Reparaturauftrag anlegen“
  erscheint die Reparatur des Leihgeräts auf der Tafel. Für interne Aufträge gibt es keine Rechnung; nach „Erledigt“
  ist das Gerät wieder verfügbar.

**Kaution:** Ohne Schaden steht sie auf „zurückzuzahlen“. Klicken Sie nach der Auszahlung auf „… zurückgezahlt“.
Bei einem Schaden wird sie verrechnet. Der Leihvorgang zeigt, was der Kunde noch zahlen muss bzw. was Sie erstatten.

**Abrechnung:** Ziehen Sie den Auftrag auf **Erledigt**, stehen Leihgebühr und Schadenersatz als eigene Positionen im
Rechnungsentwurf. Die Kautionsverrechnung steht als Hinweis darunter. Ist das Gerät dann noch beim Kunden, fragt das
Programm: *„Leihgerät jetzt zurücknehmen oder später separat abrechnen?“*. Bei „später“ erstellen Sie nach der
Rücknahme eine eigene Rechnung über „Abrechnung“ im Leihvorgang.

**Nichts geht verloren:** Ausgabe- und Rückgabeprotokolle, Schadensfälle und die Historie lassen sich nicht ändern
oder löschen. Eine irrtümliche Ausgabe oder ein falscher Schadensfall wird mit Begründung **storniert** und bleibt
markiert sichtbar.

## 15. E-Mail-Historie bei Kunden

Alle E-Mails, die Sie mit einem Kunden austauschen, erscheinen automatisch beim Kunden unter **„E-Mail-Verlauf“**.
Das gilt für Mails aus dem Programm, aus Outlook und vom Handy.

**Einrichten:** *Einstellungen → Anfragen*. Der IMAP-Zugang oben muss funktionieren (z. B. `imap.ionos.de`, Port 143,
STARTTLS, „Verbindung testen“). Darunter im Abschnitt **„E-Mail-Historie bei Kunden“**:
1. „E-Mail-Historie aktivieren“ ankreuzen.
2. **„Ordner abrufen“** und die Ordner ankreuzen: empfangene Mails (meist `INBOX`, ggf. Unterordner) und gesendete
   Mails (bei IONOS meist „Gesendete Objekte“).
3. Festlegen, wie weit der erste Import zurückgehen soll (z. B. 6 Monate).
4. Speichern und unten auf **„Jetzt abgleichen“** klicken. Danach läuft der Abgleich automatisch im Intervall der
   Anfragen, solange das Programm geöffnet ist.

**Was gespeichert wird:** nur Mails, an denen mindestens ein Kunde beteiligt ist (Absender, Empfänger, Cc oder
Antwortadresse). Alles andere wird übersprungen und nicht gespeichert. Hat ein Kunde mehrere Adressen oder
Ansprechpartner, tragen Sie diese beim Kunden unter **„Weitere E-Mail-Adressen“** ein. Das Programm sucht dann sofort im
Postfach nach früheren Mails dieser Adressen. Das passiert auch beim Anlegen eines neuen Kunden.

**Ihr Postfach bleibt unverändert:** Das Programm liest nur. Nichts wird als gelesen markiert, verschoben oder
gelöscht. Anhänge bleiben im Postfach; beim Kunden stehen nur ihre Namen.

**Neu abgleichen:** Wenn Sie den Importzeitraum vergrößern, klicken Sie auf „Alle Ordner neu abgleichen“. Doppelte
Einträge entstehen dabei nicht.

## 16. GoBD: Belege, Gutschrift, Aufbewahrung

**Festschreiben:** Eine Rechnung ist zunächst ein Entwurf ohne Nummer. Beim Festschreiben vergibt das Programm die
nächste fortlaufende Nummer, archiviert PDF und Rechnungsdaten mit Prüfsumme und sperrt den Beleg dauerhaft. Fehlen
Pflichtangaben (z. B. Ihre Steuernummer oder die Anschrift des Kunden), steht das rot oben im Entwurf, und
Festschreiben ist noch nicht möglich. Entwürfe können nur mit Wasserzeichen „ENTWURF“ angesehen und nicht per E-Mail
versendet werden.

**Korrigieren:** Eine festgeschriebene Rechnung lässt sich nicht ändern. Sie haben zwei Möglichkeiten:
- **Stornieren** erzeugt eine Stornorechnung (eigene Nummer, negative Beträge). Danach „Als neue Rechnung kopieren“ und
  die korrigierte Rechnung festschreiben.
- **Gutschrift erstellen** für eine Teil-Erstattung oder einen Preisnachlass. Sie bekommt einen eigenen Nummernkreis
  (GS-…). Beträge geben Sie positiv ein.

**Änderungsprotokoll:** Unten auf den Seiten von Rechnungen, Kunden und Artikeln steht aufklappbar, wer wann welches Feld
von welchem auf welchen Wert geändert hat.

**Kunden löschen:** Unter „Datenschutz“ beim Kunden auf „Löschen …“ klicken. Sie sehen vorher, was gelöscht und was
wegen Aufbewahrungspflicht bis wann behalten wird. Bei Aufbewahrungspflicht werden die Stammdaten anonymisiert.

**Verfahrensdokumentation:** *Einstellungen → Verwaltung & Prüfung → Verfahrensdokumentation*. Ausdrucken, die markierten Stellen ergänzen und mit
dem Steuerberater durchgehen.

## 17. Zahlungen, offene Posten, Bankabgleich und Mahnwesen

**Zahlung erfassen:** In der Rechnung unter „Zahlungen“ auf **„+ Zahlung erfassen“** klicken: Datum, Betrag (der offene
Betrag ist vorbelegt), Zahlungsart. Teilzahlungen gehen genauso. Eine falsch erfasste Zahlung stornieren Sie mit
Begründung; gelöscht wird sie nie.

**Offene Posten:** Menü *Verkauf → Rechnungen*, Reiter *Offene Posten*. Dort sehen Sie, was offen und was überfällig ist, gefiltert nach
Kunde. Beim Kunden stehen offene Beträge und alle Zahlungen.

**Bankabgleich:** Im Online-Banking die Umsätze als CSV exportieren (bei der Sparkasse „CSV-CAMT“) oder als CAMT.053.
Unter *Verkauf → Bankabgleich* einlesen. Zu jedem Eingang schlägt das Programm eine Rechnung vor:
- grün: Rechnungsnummer im Verwendungszweck gefunden
- gelb: nur Betrag (und Name) passen

Prüfen und **„Bestätigen“** klicken. Umsätze ohne Rechnung (z. B. private Eingänge) auf „Ignorieren“ setzen.
Überlappende Auszüge sind kein Problem, nichts wird doppelt übernommen.

**Mahnwesen:** Unter *Verkauf → Mahnwesen* stehen die fälligen Schreiben. Vorher den Kontoauszug einlesen, dann
auswählen und **„Ausgewählte Schreiben erstellen“**. Jedes Schreiben öffnen und **„Per E-Mail senden“** oder ausdrucken
und „per Post versendet“ anklicken. Fristen, Gebühren, Texte und optionale Verzugszinsen stellen Sie unter
*Einstellungen → Mahnwesen* ein. Den aktuellen Basiszinssatz finden Sie bei der Deutschen Bundesbank.

## 18. Annahmeschein, Abholschein und Handy (QR-Code)

**Gerät annehmen:**
1. *Reparaturaufträge → + Neuer Auftrag* öffnen.
2. Gerät, Fehler, Zustand, Zubehör, Kosten-Obergrenze, KVA-Wunsch und Fertigstellung eintragen.
3. Optional den Gerätezugang eintragen.
4. Nach dem Speichern öffnet sich der Reiter **Annahme / Abholung**:
   - **Hier unterschreiben**: Der Kunde unterschreibt am Tablet oder PC.
   - **Am Handy (QR-Code)**: Der Kunde scannt den Code und unterschreibt auf seinem oder Ihrem Handy.
   Der Code gilt 30 Minuten und nur für eine Unterschrift.
5. Danach steht der Schein unter „Unterschriebene Scheine“. Von dort drucken Sie ihn oder senden ihn per E-Mail.

**Ohne digitale Unterschrift:** „Vorschau / Papier zum Unterschreiben“ ausdrucken.

**KVA-Pauschale:** Im Auftrag den **Gerätetyp** wählen. Die Pauschale laut *Einstellungen → Annahme & Abholung →
KVA-Pauschalen* wird vorgeschlagen. Sie lässt sich ändern oder mit „kostenlos“ streichen. Der Hinweistext dazu steht
vor der Unterschrift auf dem Annahmeschein.
- Wird der KVA **angenommen**, entfällt die Pauschale.
- Wird er **abgelehnt**, öffnet sich ein Rechnungsentwurf „Kostenvoranschlag / Fehlerdiagnose – Gerät: …“. Prüfen
  und festschreiben.

**Abholung:** Im selben Reiter den Abholschein unterschreiben lassen. Das Abholdatum und das Garantieende werden
eingetragen. Gespeicherte Zugangsdaten werden endgültig gelöscht. Die Löschung steht im Löschprotokoll, ohne die
Daten selbst.

**Gerätezugang:** Hinterlegte Daten zeigt der Knopf „Gespeicherten Zugang anzeigen“. Jeder Aufruf wird protokolliert.
Wenn der Auftrag erledigt, abgeholt oder storniert (gelöscht) ist, löscht das Programm die Daten automatisch.

**Handy im WLAN freischalten (einmalig):**
1. *Einstellungen → Annahme & Abholung → „Programm im WLAN erreichbar machen“* anhaken.
2. Programm beenden und neu starten.
3. Die Windows-Firewall-Frage nur für private Netzwerke erlauben.

Handy und PC müssen im selben WLAN sein. Passt die angezeigte Adresse nicht, tragen Sie sie in den Einstellungen
selbst ein, z. B. `192.168.178.20:5000`.

## 19. Kundenbenachrichtigung

Bei einem Statuswechsel erscheint oben im Auftrag und auf der Tafel ein Kasten
„✉ Auftrag angenommen“, „✉ Gerät fertig zur Abholung“ usw.:

1. Kasten aufklappen und den Text prüfen. Sie können ihn ändern.
2. **Jetzt senden** schickt die E-Mail. Mit **Diesmal nicht senden** verwerfen Sie den Vorschlag.

Alle Vorschläge und gesendeten Nachrichten finden Sie unter *Verkauf → Benachrichtigungen*. Dort sehen Sie auch, welche
fertigen Geräte noch nicht abgeholt sind.

**Eigene Nachricht:** Im Auftrag unter „Kunde benachrichtigen“ einen Anlass wählen und dann „Vorschau erstellen“.

**Wartet auf Teil:** Den Auftrag auf der Tafel in die Spalte „Wartet auf Teil“ ziehen oder im Auftrag den Status
wählen. Ersatzteil und erwartetes Datum stehen dann auf der Karte.

**Texte und Öffnungszeiten:** Unter *Einstellungen → Benachrichtigungen*. Wollen Sie ohne Vorschau senden, nehmen Sie
den Haken „Vor jedem Versand Vorschau anzeigen“ heraus. Empfohlen ist das nicht.

## 20. Garantie und Garantiefälle

- **Freiwillige Garantie:** Sie beginnt mit der **Abholung**, nicht mit dem Rechnungsdatum. Das Garantieende wird
  bei der Abholung im Auftrag gespeichert. Der Garantietext auf Rechnung und Abholschein ist unter
  *Einstellungen → Annahme & Abholung* änderbar. Er stellt klar, dass die gesetzliche Gewährleistung unberührt bleibt.
- **Standard-Garantie:** *Einstellungen → Annahme & Abholung → Garantie auf Reparaturen* (0 = keine Garantie).
- **Abweichende Garantie:**
  - im Auftrag: „Garantie auf diese Reparatur (Monate)“
  - in der Rechnung je Position: Feld „Garantie … Monate“ (leer = Standard, 0 = ohne Garantie)
- **Gerät wiedererkennen:** Beim Eintippen der Seriennummer/IMEI erscheint ein Hinweis, wenn das Gerät schon einmal
  da war. Er zeigt den Garantiestand und Links zu Auftrag, Fotos und Rechnung.
- **Garantiefall anlegen:** Im Hinweis auf „als Garantiefall zu …“ klicken. Interne Kosten eintragen und speichern.
  Beim Erledigen entsteht keine Rechnung. Im ursprünglichen Auftrag steht unter „Garantie“ die Liste seiner
  Garantiefälle.

## 21. Lager und Inventur

1. **Artikel lagerführend machen:** *Leistungen & Artikel* → Artikel öffnen → „lagerführend“ anhaken, Mindestbestand,
   Lagerort und „Kompatibel mit“ eintragen → Speichern.
2. **Anfangsbestand:** Unten beim Artikel „Zugang“, Menge und Grund „Erstbestand“ eintragen → **Buchen**.
3. **Material für einen Auftrag:** Im Auftrag im Reiter **Material** Artikel und Menge wählen → **Reservieren**.
   Beim Erledigen wird das Material automatisch ausgebucht.
4. **Nachbestellen:** *Lager → Unter Mindestbestand* oder **Bestellvorschlag erstellen**. Den Vorschlag drucken oder
   als CSV öffnen.
5. **Inventur:**
   1. *Lager → Inventur* öffnen, Stichtag wählen, **Inventur anlegen**.
   2. Zählen: am PC eintragen, Zählliste drucken oder **Am Handy zählen** (QR-Code). Zwischendurch speichern geht.
   3. **Inventur abschließen**. Die Differenzen werden gebucht und das Protokoll-PDF wird archiviert.
6. **Lagerwert:** *Lager → Lagerwert*, Stichtag wählen.

## 22. Einkauf: Lieferanten, Bestellungen, Eingangsrechnungen

1. **Lieferant anlegen:** *Einkauf → Lieferanten → + Neuer Lieferant*.
2. **Bezugsquelle beim Artikel:** Artikel öffnen → „Bezugsquellen“ → Lieferant, EK und Artikelnummer eintragen.
   Bei mehreren Lieferanten ist der günstigste markiert.
3. **Bestellen:**
   - *Lager → Bestellvorschlag erstellen*, Mengen prüfen, **Bestellungen anlegen**, oder
   - im Auftrag (Reiter Material): **Teil für diesen Auftrag bestellen**.

   Die Bestellung per E-Mail senden oder nach der Bestellung im Webshop auf **Als bestellt markieren** klicken.
4. **Ware ist da:** Bestellung öffnen, Mengen prüfen, **Wareneingang buchen**.
5. **Eingangsrechnung:** *Einkauf → Eingangsrechnungen → + Erfassen / hochladen* oder **Aus dem Postfach**. Beträge
   eintragen (Netto oder Brutto genügt) und speichern.
6. **Bezahlen:** Kontoauszug im *Bankabgleich* einlesen. Bei der Abbuchung die Eingangsrechnung bestätigen. Ohne
   Kontoauszug erfassen Sie die Zahlung direkt an der Eingangsrechnung.

## 23. E-Rechnung (ZUGFeRD / XRechnung)

- **Firmenkunden** bekommen automatisch ZUGFeRD: Das PDF sieht aus wie immer, enthält aber zusätzlich die
  Rechnungsdaten als XML. Sie müssen nichts weiter tun.
- **Behörden / XRechnung:** Kunden öffnen → *Rechnungsformat: XRechnung* → **Leitweg-ID** eintragen (bekommen Sie von
  der Behörde) → Speichern. Beim E-Mail-Versand werden PDF und XML angehängt.
- **Vor der ersten E-Rechnung:** Unter *Einstellungen → Firmendaten* IBAN, Telefon und E-Mail eintragen.
- **Empfangene E-Rechnung:** Bei *Eingangsrechnungen → Erfassen* nur die Datei wählen und ohne Beträge auf „erfassen“
  klicken. Die Angaben werden ausgelesen, Sie prüfen und speichern. „E-Rechnung lesbar anzeigen“ zeigt den Inhalt
  übersichtlich, auch als PDF.

## 24. Kassenbuch und DATEV-Export

**Kassenbuch:**
1. Einmalig den **Anfangsbestand** buchen, also das Geld, das gerade in der Kasse ist.
2. Jede Bareinnahme und -ausgabe sofort buchen, möglichst mit Foto des Belegs. Wird eine Rechnung bar bezahlt, bei
   „Barzahlung zu Rechnung“ die Rechnung wählen.
3. Abends **Tag abschließen**: Kasse zählen und den Betrag eintragen. Bei einer Differenz die Begründung angeben.
4. Fehler korrigieren Sie mit „korrigieren … → Gegenbuchung“. Löschen geht bewusst nicht.
5. **Bestand würde negativ?** Das Programm prüft jeden Tag ab dem Buchungsdatum, auch bei nachgetragenen Buchungen.
   - Die Meldung nennt den Tag und den Fehlbetrag. Ihre Buchung bleibt vorgemerkt.
   - Mit **„Fehlende Einnahme erfassen“** oder **„Privateinlage buchen“** die Lücke schließen. Datum und Betrag sind
     vorbelegt. Danach wird die vorgemerkte Buchung automatisch nachgeholt.
6. **Privateinlage / Privatentnahme:** Eigenes Geld in die Kasse legen oder entnehmen. Datum, Betrag und Begründung
   angeben. Gebucht wird immer ohne Umsatzsteuer.

**DATEV-Export:**
1. Einmalig *Einstellungen → DATEV* ausfüllen (Daten vom Steuerberater).
2. Monatlich *Buchhaltung → DATEV-Export*: Zeitraum (Standard: Vormonat), Vorschau prüfen,
   **Export erstellen**, ZIP herunterladen und an den Steuerberater geben.

### Fixkosten und Finanzübersicht

**Fixkosten** (*Buchhaltung → Fixkosten → + Neue Fixkosten*):
1. Bezeichnung, Kategorie, Betrag (netto oder brutto), Rhythmus, Fälligkeitstag und Beginn eintragen. Optional: Ende,
   Kündigungsfrist, Empfänger, Vertrag als PDF.
2. **Betrag ändert sich** (z. B. Mieterhöhung): Position öffnen → „Neuer Betrag“ mit „gültig ab“. Der alte Betrag
   bleibt für frühere Monate erhalten.
3. **Bankabgleich:** Bei Abbuchungen erscheint „Fixkosten-Vorschlag …“ → „Als Fixkosten bestätigen“. Fehlende oder
   abweichende Zahlungen sind in der Fixkosten-Liste rot bzw. gelb markiert.
4. Endet ein Vertrag bald oder läuft eine Kündigungsfrist ab, erscheint ein Hinweis, auch in der Glocke.

**Finanzen** (*Buchhaltung → Finanzen*):
- Oben den Zeitraum wählen oder mit ‹ › blättern.
- Umschalter:
  - Einnahmen nach Rechnungsdatum oder nach Zahlungseingang
  - Fixkosten anteilig oder im Fälligkeitsmonat
  - Vergleich mit Vorjahr oder Vorperiode
- **Jede Zahl ist anklickbar** und zeigt die Belege, aus denen sie besteht.
- Export: „PDF“ oder „CSV / Excel“.
- Wichtig: Die Übersicht ist betriebswirtschaftlich, keine EÜR und keine Umsatzsteuer-Voranmeldung.
- Welche Kostenarten als Wareneinsatz zählen, stellen Sie unter *Einstellungen → Einkauf* ein.

## 25. TSE (Technische Sicherheitseinrichtung) – was gilt für Sie?

*Keine Steuerberatung, sondern eine Einordnung zur Vorbereitung auf das Gespräch mit dem Steuerberater.*

- **Was ist die TSE?** Nach § 146a AO und der Kassensicherungsverordnung müssen **elektronische
  Aufzeichnungssysteme mit Kassenfunktion** jede Bargeld-Transaktion über eine zertifizierte TSE absichern. Dazu
  kommen Belegausgabepflicht und Meldepflicht ans Finanzamt (seit 2025 über ELSTER).
- **Hat dieses Programm eine TSE?** Nein. Es ist in erster Linie ein Rechnungs- und Buchhaltungsprogramm. Das
  Kassenbuch ist ein unveränderliches digitales Kassenbuch, aber **keine zertifizierte Registrierkasse**.
- **Ihre Möglichkeiten:**
  1. **Offene Ladenkasse** (Geldkassette ohne elektronische Kasse): keine TSE nötig. Dafür muss jeder Bargeldvorgang
     einzeln aufgezeichnet werden (bei Ihnen über Rechnung bzw. Kassenbuch). Außerdem brauchen Sie täglich einen
     Kassenbericht bzw. Kassensturz, das ist der Tagesabschluss im Programm. Für eine kleine Werkstatt, in der fast
     jeder Barverkauf eine Rechnung bekommt, ist das häufig der passende Weg. **Ob dieses Programm dabei selbst als
     „Aufzeichnungssystem mit Kassenfunktion“ gilt, ist nicht eindeutig. Bitte mit dem Steuerberater klären.**
  2. **Zertifizierte Kasse für Barverkäufe** (z. B. eine App-Kasse mit Cloud-TSE): Barverkäufe laufen dort, die
     Tagessummen werden hier als Einnahme gebucht. Kosten: meist ein monatlicher Betrag.
  3. **Cloud-TSE ins Programm einbauen** (z. B. fiskaly oder Deutsche Fiskal, Programmierschnittstelle vorhanden):
     technisch möglich, aber kostenpflichtig. Dazu kommen Meldung ans Finanzamt, Belegdruck und
     Verfahrensdokumentation. Lohnt sich nur bei vielen Barverkäufen ohne Rechnung.
- **Unabhängig davon:** Kartenzahlungen und Überweisungen sind keine Bargeldvorgänge im Sinne der TSE-Pflicht.

## 26. Datenschutz

- **Löschfristen** einmal prüfen: *Einstellungen → Datenschutz*. Wenn alles passt, „Löschlauf automatisch“
  einschalten.
  - Fotos und Annahme-/Abholscheine: 3 Jahre ab Ende des Abholjahres.
  - Leihprotokolle: 3 Jahre ab Ende des Rückgabejahres bzw. des Abschlusses eines Schadensfalls.
  - Inaktive Kunden: 3 Jahre ab Ende des Jahres des letzten Kontakts.
  - Interessenten: 6 Monate.
- **Vorschau:** *Datenschutz* zeigt, was in den nächsten 30 Tagen gelöscht wird.
  - **Gesperrt** sind Einträge mit laufendem Auftrag, offener Rechnung, offenem Schadensfall oder laufender Garantie.
  - Mit **Zurückstellen** (Begründung, z. B. Streitfall) nehmen Sie einen Eintrag aus dem Löschlauf. Unter
    „Zurückgestellte Löschungen“ heben Sie das wieder auf.
- **Kunde fragt, welche Daten Sie haben (Art. 15):** Kunde öffnen → **Auskunft (Art. 15 DSGVO) herunterladen** → das
  ZIP dem Kunden geben (Frist: 1 Monat).
- **Kunde will gelöscht werden (Art. 17):** Kunde öffnen → **Löschen …** → Haken „Der Kunde hat die Löschung
  verlangt“ → bestätigen. Unter *Datenschutz → Löschprotokolle* steht die **Bestätigung (PDF)** für den Kunden.
- **Verzeichnis der Verarbeitungstätigkeiten:** *Datenschutz → Verzeichnis*. Die Stellen mit [bitte ergänzen]
  ausfüllen, als PDF speichern und aufbewahren.
