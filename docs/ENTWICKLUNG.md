# Regeln für Änderungen am Programm

Diese Regeln gelten für jede künftige Änderung. Sie sorgen dafür, dass das Programm unverändert unter Windows
(EXE oder start.bat) läuft und später ohne Umbau auf einem Linux-Server (Docker). `tests/test_regeln.py` prüft die
Regeln bei jedem Testlauf und vor jeder Veröffentlichung automatisch. Ein Verstoß lässt den Build scheitern.

## 1. Keine Windows-spezifischen Pfade oder Bibliotheken

- Pfade immer mit `pathlib.Path` bilden (`ordner / "datei.pdf"`), nie mit festen Laufwerken (`C:\...`) und nie mit
  Backslashes im Code.
- In der Datenbank gespeicherte Dateipfade sind **relativ zum Datenordner** und verwenden `/`
  (`Path(...).relative_to(daten).as_posix()`).
- Windows-Funktionen kommen nur in diesen Modulen vor, mit Ersatz bzw. Abschaltung für andere Systeme:
  - `rsb/fenster.py`: Programmfenster, Symbol neben der Uhr, Ordner öffnen
  - `rsb/update.py`: Selbst-Update der EXE
  Das betrifft z. B. `os.startfile`, `winreg`, `win32…`, `msvcrt` und `ctypes.windll`.
- Drucken nur über PDF bzw. die Druckfunktion des Browsers, keine direkte Druckeransteuerung.

## 2. Alle Daten im Datenordner

- Datenbank, PDFs, Fotos, Uploads, Exporte, Sicherungen, Schlüssel und Protokolldateien liegen im **einen**
  Datenordner (`app.config["DATEN"]`). Den Ort bestimmt `rsb/datenort.py`: fest pro Benutzer bzw. `RSB_DATEN`.
- Nie neben das Programm oder in das aktuelle Arbeitsverzeichnis schreiben.
- Neue Unterordner in die Sicherung aufnehmen (`rsb/backup.py`, `ORDNER_IM_BACKUP`).
- Dateinamen, die aus Eingaben entstehen (Belegnummern usw.), mit `hilfen.sicherer_dateiname()` bilden. Präfixe
  und Nummernformat werden beim Speichern auf unerlaubte Zeichen geprüft.
- Groß- und Kleinschreibung von Dateien und Ordnern muss im Code exakt stimmen; Linux unterscheidet sie.

## 3. Konfiguration über Umgebung bzw. `.env`

- Rechnerabhängige Werte (Datenordner, Host, Port usw.) kommen aus Umgebungsvariablen `RSB_…`, später auch aus einer
  `.env`. Es gibt sinnvolle Standardwerte.
- Passwörter und Schlüssel gehören nie in den Code. Schlüssel liegen in `Daten/geheim`, Zugangsdaten verschlüsselt in
  der Datenbank.
- Debug-Modus ist immer aus. Server ist Waitress, nie `app.run()`.

## 4. Zeitzone und Zeichensatz ausdrücklich

- Zeiten immer ausdrücklich in **Europe/Berlin** (`zoneinfo`), nie in der Zeitzone des Rechners. In Docker wäre das
  UTC.
  - **Übergang:** Bestehende Stellen mit `datetime.now()`/`date.today()` werden im Arbeitspaket „Zeitzone“ umgestellt.
    Bis dahin darf ihre Zahl nicht steigen.
- Textdateien immer mit `encoding="utf-8"` lesen und schreiben, Ausnahme: ausdrücklich verlangte Formate wie der
  DATEV-Export in cp1252.

## 5. Daten erhalten

- Datenbankänderungen nur per Migration (`db.MIGRATIONEN` bzw. neue Tabellen in `schema.sql`). Vorher legt das
  Programm automatisch eine Sicherung an.
- Festgeschriebene Belege, Protokoll und Kassenbuch sind unveränderlich (Trigger). Korrekturen nur per Storno bzw.
  Gegenbuchung.
- Abhängigkeiten mit festen Versionen in `requirements.txt`. Eine neue Version erst nach erfolgreichem Testlauf
  übernehmen.
