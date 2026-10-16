# Vorgaben, Technik und Fahrplan

## Ihre Antworten (Zusammenfassung)

| Thema | Festlegung |
|---|---|
| Rechnungsnummern | `RE-2026-0001`, neue Reihe (kein Übernehmen aus Lexware). Pro Jahr beginnt die Zählung neu. |
| Zahlungsziel | Privatkunden 14 Tage, Firmenkunden 30 Tage (pro Kunde abweichend einstellbar) |
| Mahnwesen | 2 Stufen, 3,95 € Mahngebühr je Mahnung (Einstellungen vorhanden, Funktion in Etappe 3) |
| Anzahlung | per Überweisung, Standard 50 % des Auftragsvolumens, im Einzelfall änderbar (Etappe 2) |
| Zahlungsarten | Überweisung (mit QR-Code/GiroCode) oder bar bei Abholung, kein PayPal |
| Layout | Logo vorhanden, Rest frei gestaltet: Blau `#1C54A3` und Grau `#5D6670` aus dem Logo, Schrift Montserrat (wie im Logo) |
| Textbausteine | Sie schicken Ihre Texte noch. Bis dahin sind Beispieltexte hinterlegt, die Sie selbst ändern können. |
| Buchhaltung | kein Steuerberater, Erklärung selbst über ELSTER → Die EÜR-Auswertung (Etappe 4) wird nach den Zeilen der **Anlage EÜR** aufgebaut, damit Sie die Werte direkt übertragen können. |
| Rechner | Windows 11, ein Benutzer |
| Backup | zusätzlich auf ein NAS (Pfad in den Einstellungen) |
| Kontakt auf Dokumenten | www.reparatur-bredin.de, kontakt@reparatur-bredin.de |

## Technik-Entscheidung

| Baustein | Wahl | Begründung |
|---|---|---|
| Sprache | Python 3 | Verbreitet, kostenlos, unter Windows per Doppelklick installierbar |
| Oberfläche | Flask + eigene schlichte Seiten (kein Internet nötig) | Bedienung im gewohnten Browser, einfach zu erweitern |
| Webserver | Waitress | Stabil unter Windows, keine Konfiguration nötig |
| Datenbank | SQLite | Eine Datei, kein Server, sehr zuverlässig; Schutzregeln direkt in der Datenbank |
| PDF | ReportLab | Läuft unter Windows ohne Zusatzprogramme (anders als HTML-zu-PDF-Werkzeuge, die GTK benötigen); präzises A4/DIN-5008-Layout |
| QR-Code | in ReportLab enthalten | GiroCode nach EPC-Standard |
| E-Mail | Python-Standardbibliothek (smtplib) | Ihr eigener Zugang, keine Drittanbieter |
| Verschlüsselung | cryptography (Fernet/AES) | Bewährte Bibliothek |

Hinweis: Im ersten Vorschlag hatte ich WeasyPrint genannt. Ich habe mich für **ReportLab** entschieden,
weil WeasyPrint unter Windows zusätzliche Systembibliotheken braucht. Das widerspricht dem Ziel
„Installation in wenigen Schritten“.

## Etappen

| Etappe | Inhalt | Stand |
|---|---|---|
| **1** | Kunden, Leistungen/Artikel mit Teilekosten und Marge, Rechnung als PDF mit Logo und GiroCode, Druck, E-Mail-Versand mit Vorlagen und Protokoll, Storno, unveränderbare Nummern, Login, Textbausteine, Layout-Einstellungen, tägliches Backup inkl. NAS, Datenprüfung | ✅ fertig |
| **1b** | Anfragen aus dem Kontaktformular: Abruf per IMAP, Spam-/Unsinn-Erkennung, automatisches Anlegen als Interessent, Dubletten-Erkennung, Löschvorschläge | ✅ fertig |
| **1c** | Reparaturaufträge als Tafel (offen / in Arbeit / erledigt, Ziehen & Ablegen), Kostenvoranschlag (KV-Nummern, PDF, E-Mail), automatischer Rechnungsentwurf bei „erledigt“ | ✅ fertig |
| **1d** | Verträge & Lizenzen (Wertgarantie, ESET, MSP), wiederkehrende Rechnungen, Kündigung, Verlängerung | ✅ fertig |
| 3a | Bankumsätze (N26-CSV) importieren, Zahlungen per Rechnungsnummer zuordnen, Freigabe bzw. später automatisch | als Nächstes (wartet auf CSV-Beispiel) |
| 2 | Auftragsbestätigung, Anzahlungsrechnung (50 % Standard), Schlussrechnung mit Abzug der Anzahlung, Gutschrift; optional ZUGFeRD | geplant |
| 3 | Zahlungseingänge (teilweise/vollständig, bar/Überweisung), Status offen/teilweise/bezahlt/überfällig, Zahlungserinnerung und 2 Mahnstufen mit 3,95 € Gebühr | geplant |
| 4 | Einnahmen/Ausgaben mit Belegen (Foto/PDF/E-Rechnung), Kategorien nach Anlage EÜR, EÜR-Auswertung, Monats-/Jahresübersicht, Umsatz pro Leistungsart, offene Posten | geplant |
| 5 | CSV-/PDF-Export, CSV-Import von Kunden, Wiederherstellung per Knopfdruck, Löschfristen-Assistent, Vorlage Verfahrensdokumentation | geplant |
| 6 | Anbindung an das Anfrage-Tool (Formular → Kunde + Kostenvoranschlag → Anzahlung → Teilebestellung) | geplant |
