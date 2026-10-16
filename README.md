# Werkstatt Sauter – Aufträge, Rechnungen & Buchhaltung

Auftrags-, Rechnungs- und Buchhaltungsprogramm für die **Kfz-Werkstatt Sauter**.
Es läuft lokal auf dem Windows-PC, die Bedienung erfolgt im Browser, und es entstehen **keine laufenden Kosten**.

**Schwerpunkt:** Aufträge als Tafel (offen / in Arbeit / wartet auf Teil / erledigt) mit Fahrzeugdaten
(Kennzeichen, FIN, km-Stand, HU), mehreren Leistungen je Auftrag (Ölwechsel, Fehlerspeicher, Reifenwechsel,
Montage, Auswuchten …) und einer **Checkliste zum Abhaken** je Leistung. Dazu Annahmeschein mit Unterschrift,
Kostenvoranschlag, automatischer Rechnungsentwurf, Rechnungen als PDF mit GiroCode, Mahnwesen, Lager, Einkauf,
Bankabgleich, Kassenbuch, Fixkosten, Finanzübersicht, DATEV-Export, Datenschutz und tägliches Backup.

| Dokument | Inhalt |
|---|---|
| [docs/AENDERUNGEN.md](docs/AENDERUNGEN.md) | **Versionsprotokoll**: alle Versionen mit Neuerungen, Änderungen und Fehlerbehebungen (auch im Programm: Klick auf die Versionsnummer) |
| [docs/ANLEITUNG.md](docs/ANLEITUNG.md) | Bedienung: Rechnung schreiben, Layout & Textbausteine ändern, Backup & Wiederherstellung |
| [docs/RECHT_UND_GOBD.md](docs/RECHT_UND_GOBD.md) | Pflichtangaben, E-Rechnung, Aufbewahrung, GoBD – und ehrlich: wo die Grenzen liegen |

---

## Installation unter Windows 11 (2 Minuten)

1. Ordner anlegen, z. B. **`C:\Werkstatt-Sauter`**. Bitte nicht unter „Programme“ und nicht in OneDrive,
   denn das Programm muss dort seine Daten und Updates speichern dürfen.
2. **[Werkstatt-Sauter.exe herunterladen](https://github.com/ReparaturServiceBredin/Werktstatt/releases/latest/download/Werkstatt-Sauter.exe)**
   und in diesen Ordner legen.
3. Doppelklick auf **Werkstatt-Sauter.exe**.
   - Beim allerersten Start meldet Windows evtl. „Der Computer wurde durch Windows geschützt“, weil die Datei
     nicht kostenpflichtig signiert ist. Dann auf *Weitere Informationen → Trotzdem ausführen* klicken.
     Das passiert nur einmal, Updates lädt das Programm selbst.
   - Die Buchhaltung öffnet sich als **eigenes Programmfenster**. Das Programm läuft im Hintergrund weiter,
     erkennbar am **Symbol unten rechts neben der Uhr** (ggf. unter dem Pfeil `^`).
     Klick auf das Symbol öffnet das Fenster wieder, Rechtsklick → **Beenden** schließt das Programm ganz.
4. Unter *Einstellungen → Firmendaten* Anschrift, Steuernummer und Bankverbindung eintragen.
   Ein Passwort ist nicht nötig. Bei Bedarf schalten Sie es unter *Einstellungen → Passwortschutz* ein.

**Tipps:**
- Rechtsklick auf die EXE → *Senden an → Desktop (Verknüpfung erstellen)*.
- **Mit Windows starten:** `Win + R`, `shell:startup` eingeben und dort eine Verknüpfung zur EXE ablegen.
- Ein Doppelklick auf die EXE, während das Programm schon läuft, öffnet einfach wieder das Fenster.
- Lieber als Tab im normalen Browser? *Einstellungen → Programm & Updates → Programmfenster*.
- Meldungen des Programms stehen in `programm.log` im Datenordner.

### Updates – automatisch

Das Programm fragt beim Start und alle 6 Stunden nach einer neuen Version. Gibt es eine, passiert Folgendes:
- Beim **nächsten Start** wird sie automatisch installiert. Vorher erstellt das Programm ein Backup,
  danach startet es neu. Abschalten können Sie das unter *Einstellungen → Programm & Updates*.
- Oder Sie klicken in der Oberfläche auf **„Jetzt aktualisieren“**, sobald der Hinweis erscheint.

Ihre Daten bleiben dabei unverändert. Neue Datenbankfelder ergänzt das Programm selbst.
Jede neue Version wird vor der Veröffentlichung automatisch getestet. Die Datei wird beim Herunterladen
mit einer Prüfsumme kontrolliert.

### Umstieg von der bisherigen Installation (start.bat)

Nichts zu tun: EXE und start.bat benutzen denselben festen Datenordner (siehe unten). Bisherige Datenordner übernimmt
das Programm beim ersten Start selbst.

Die alte Variante mit `installieren.bat` / `start.bat` funktioniert weiterhin, bekommt aber keine automatischen
Updates.

## Ihre Daten – ein einziger, fester Ordner

Seit Version 0.23 liegen alle Daten an **einem festen Ort**, egal von wo Sie das Programm starten (Desktop, Downloads,
start.bat):

- Windows: `%LOCALAPPDATA%\Werkstatt-Sauter\Daten` (z. B. `C:\Users\Name\AppData\Local\Werkstatt-Sauter\Daten`).
  Dieser Ordner wird nicht von OneDrive synchronisiert.
- Öffnen: Rechtsklick auf das Programmsymbol neben der Uhr → **Daten-Ordner öffnen**. Der Pfad steht auch unter
  *Einstellungen → Backup*.
- Beim ersten Start übernimmt das Programm den bisherigen Ordner `Daten` (neben der EXE bzw. in Desktop, Downloads,
  Dokumente, OneDrive) mit den meisten Daten. Es **kopiert** ihn, prüft Datensätze und Dateien und lässt den alten
  Ordner mit einer Notiz liegen. Weitere gefundene Ordner zeigt es an; sie lassen sich unter
  *Einstellungen → Backup → Sicherung wiederherstellen* einspielen.
- Für Docker oder Sonderfälle lässt sich der Ort mit der Umgebungsvariable `RSB_DATEN` festlegen.

```
Daten\
  werkstatt.db      Datenbank (Kunden, Artikel, Rechnungen, Protokoll)
  dokumente\2026\     archivierte Original-PDFs aller festgeschriebenen Rechnungen
  belege\             (ab Etappe 4) Belege zu Ausgaben
  bilder\             Ihr hochgeladenes Logo
  backups\            automatische Backups (ZIP)
  geheim\             Schlüssel für das verschlüsselte E-Mail-Passwort – nicht weitergeben
```

Backups, Wiederherstellung und NAS-Kopie: siehe [docs/ANLEITUNG.md](docs/ANLEITUNG.md#backup-und-wiederherstellung).

## Technik (kurz)

Regeln für Änderungen am Programm: [docs/ENTWICKLUNG.md](docs/ENTWICKLUNG.md).


Python 3 · Flask (Weboberfläche) · Waitress (lokaler Webserver) · SQLite (Datenbank in einer Datei) ·
ReportLab (PDF) · cryptography (Verschlüsselung) · PyInstaller (EXE) – alles Open Source und kostenlos.
Die Windows-EXE baut GitHub Actions bei jeder neuen Versionsnummer automatisch, testet sie und veröffentlicht
sie unter *Releases* (`.github/workflows/release.yml`). Neue Version veröffentlichen: `VERSION_NUMMER` in
`rsb/__init__.py` erhöhen und einen Abschnitt in `docs/AENDERUNGEN.md` ergänzen.
Das Programm ist nur vom eigenen PC aus erreichbar (`127.0.0.1`).

## Für Entwickler

```bash
python -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest              # automatische Tests
RSB_DATEN=Testdaten .venv/bin/python -m rsb.beispieldaten   # Beispieldaten in separatem Ordner
RSB_DATEN=Testdaten .venv/bin/python -m rsb                 # starten
```
Umgebungsvariablen: `RSB_DATEN` (Datenordner), `RSB_HOST`, `RSB_PORT`, `RSB_KEIN_BROWSER=1`.

## So sieht es aus

| Rechnung schreiben (mit Marge je Position) | Fertige Rechnung (PDF) |
|---|---|
| ![Rechnung bearbeiten](docs/bilder/rechnung_bearbeiten.png) | ![Beispielrechnung](docs/bilder/beispielrechnung.png) |
| **Layout-Einstellungen mit Vorschau** | **Festgeschrieben & versendet** |
| ![Layout](docs/bilder/layout.png) | ![Versendet](docs/bilder/rechnung_versendet.png) |

Beispiel-PDF: [docs/Beispielrechnung_RE-2026-0001.pdf](docs/Beispielrechnung_RE-2026-0001.pdf) (mit Beispieldaten).
