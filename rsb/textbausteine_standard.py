"""Mitgelieferte Textbausteine. Sie werden beim ersten Start in die Datenbank kopiert
und sind danach unter Einstellungen → Textbausteine frei änderbar.

Platzhalter in geschweiften Klammern werden automatisch ersetzt, z. B. {nummer} oder {faellig_am}.
"""

STANDARD_TEXTBAUSTEINE = [
    {
        "kategorie": "einleitung", "dokumenttyp": "rechnung", "standard": 1,
        "name": "Rechnung – Standard",
        "text": "{anrede_brief}\n\nvielen Dank für Ihren Auftrag. Für die ausgeführten Arbeiten berechne ich Ihnen:",
    },
    {
        "kategorie": "schluss", "dokumenttyp": "rechnung", "standard": 1,
        "name": "Rechnung – Zahlung",
        "text": "Bitte überweisen Sie den Betrag von {betrag} bis zum {faellig_am} unter Angabe der "
                "Rechnungsnummer {nummer} auf das unten genannte Konto. Barzahlung bei Abholung ist ebenfalls möglich.\n\n"
                "Mit freundlichen Grüßen\n{inhaber}",
    },
    {
        "kategorie": "schluss", "dokumenttyp": "rechnung", "standard": 0,
        "name": "Rechnung – bereits bar bezahlt",
        "text": "Der Rechnungsbetrag wurde am {datum} in bar bezahlt. Vielen Dank!\n\nMit freundlichen Grüßen\n{inhaber}",
    },
    {
        "kategorie": "hinweis", "dokumenttyp": "alle", "standard": 0,
        "name": "Datensicherung (Beispieltext)",
        "text": "Bitte sichern Sie vor jeder Reparatur Ihre Daten. Für Datenverlust kann keine Haftung übernommen werden.",
    },
    {
        "kategorie": "hinweis", "dokumenttyp": "alle", "standard": 0,
        "name": "Gewährleistung (Beispieltext – bitte prüfen lassen)",
        "text": "Es gelten die gesetzlichen Gewährleistungsrechte.",
    },
    {
        "kategorie": "einleitung", "dokumenttyp": "storno", "standard": 1,
        "name": "Stornorechnung – Standard",
        "text": "{anrede_brief}\n\nhiermit storniere ich die Rechnung {bezug_nummer} vom {bezug_datum} vollständig.",
    },
    {
        "kategorie": "schluss", "dokumenttyp": "storno", "standard": 1,
        "name": "Stornorechnung – Schluss",
        "text": "Bereits gezahlte Beträge werden erstattet bzw. verrechnet.\n\nMit freundlichen Grüßen\n{inhaber}",
    },
    {
        "kategorie": "email_betreff", "dokumenttyp": "rechnung", "standard": 1,
        "name": "E-Mail Rechnung – Betreff",
        "text": "Ihre Rechnung {nummer} – {firma_name}",
    },
    {
        "kategorie": "email_text", "dokumenttyp": "rechnung", "standard": 1,
        "name": "E-Mail Rechnung – Text",
        "text": "{anrede_brief}\n\nanbei erhalten Sie Ihre Rechnung {nummer} vom {datum} über {betrag} als PDF.\n"
                "Bitte begleichen Sie den Betrag bis zum {faellig_am}.\n\n"
                "Bei Fragen erreichen Sie mich gerne per E-Mail oder telefonisch.\n\n"
                "Mit freundlichen Grüßen\n{inhaber}\n{firma_name}\n{firma_telefon}\n{firma_web}",
    },
    {
        "kategorie": "einleitung", "dokumenttyp": "kva", "standard": 1,
        "name": "Kostenvoranschlag – Standard",
        "text": "{anrede_brief}\n\nvielen Dank für Ihre Anfrage. Für die Reparatur Ihres Geräts erstelle ich Ihnen "
                "folgenden Kostenvoranschlag:",
    },
    {
        "kategorie": "schluss", "dokumenttyp": "kva", "standard": 1,
        "name": "Kostenvoranschlag – Schluss (Beispieltext)",
        "text": "Dieser Kostenvoranschlag ist gültig bis zum {gueltig_bis}. Sollten sich während der Reparatur "
                "Mehrkosten ergeben, melde ich mich vorher bei Ihnen.\n\nWenn Sie einverstanden sind, geben Sie mir "
                "bitte kurz per E-Mail oder telefonisch Bescheid.\n\nMit freundlichen Grüßen\n{inhaber}",
    },
    {
        "kategorie": "email_betreff", "dokumenttyp": "kva", "standard": 1,
        "name": "E-Mail Kostenvoranschlag – Betreff",
        "text": "Ihr Kostenvoranschlag {nummer} – {firma_name}",
    },
    {
        "kategorie": "email_text", "dokumenttyp": "kva", "standard": 1,
        "name": "E-Mail Kostenvoranschlag – Text",
        "text": "{anrede_brief}\n\nanbei erhalten Sie den Kostenvoranschlag {nummer} über {betrag} für die Reparatur "
                "Ihres Geräts.\nBitte geben Sie mir kurz Bescheid, ob ich die Reparatur durchführen soll.\n\n"
                "Mit freundlichen Grüßen\n{inhaber}\n{firma_name}\n{firma_telefon}\n{firma_web}",
    },
    {
        "kategorie": "email_betreff", "dokumenttyp": "storno", "standard": 1,
        "name": "E-Mail Storno – Betreff",
        "text": "Stornorechnung {nummer} – {firma_name}",
    },
    {
        "kategorie": "email_text", "dokumenttyp": "storno", "standard": 1,
        "name": "E-Mail Storno – Text",
        "text": "{anrede_brief}\n\nanbei erhalten Sie die Stornorechnung {nummer} zur Rechnung {bezug_nummer}.\n\n"
                "Mit freundlichen Grüßen\n{inhaber}\n{firma_name}",
    },
    {
        "kategorie": "einleitung", "dokumenttyp": "gutschrift", "standard": 1,
        "name": "Gutschrift – Standard",
        "text": "{anrede_brief}\n\nzur Rechnung {bezug_nummer} vom {bezug_datum} schreibe ich Ihnen folgenden Betrag gut:",
    },
    {
        "kategorie": "schluss", "dokumenttyp": "gutschrift", "standard": 1,
        "name": "Gutschrift – Schluss",
        "text": "Der Betrag von {betrag} wird Ihnen erstattet bzw. mit offenen Beträgen verrechnet.\n\n"
                "Mit freundlichen Grüßen\n{inhaber}",
    },
    {
        "kategorie": "email_betreff", "dokumenttyp": "gutschrift", "standard": 1,
        "name": "E-Mail Gutschrift – Betreff",
        "text": "Gutschrift {nummer} – {firma_name}",
    },
    {
        "kategorie": "email_text", "dokumenttyp": "gutschrift", "standard": 1,
        "name": "E-Mail Gutschrift – Text",
        "text": "{anrede_brief}\n\nanbei erhalten Sie die Gutschrift {nummer} zur Rechnung {bezug_nummer}.\n\n"
                "Mit freundlichen Grüßen\n{inhaber}\n{firma_name}",
    },
]

PLATZHALTER_HILFE = [
    ("{anrede_brief}", "Briefanrede, z. B. „Sehr geehrte Frau Müller,“"),
    ("{kunde_name}", "Name bzw. Firma des Kunden"),
    ("{kundennr}", "Kundennummer"),
    ("{nummer}", "Dokumentnummer, z. B. RE-2026-0001"),
    ("{datum}", "Dokumentdatum"),
    ("{faellig_am}", "Fälligkeitsdatum"),
    ("{gueltig_bis}", "Gültig bis (Kostenvoranschlag)"),
    ("{zahlungsziel_tage}", "Zahlungsziel in Tagen"),
    ("{betrag}", "Gesamtbetrag, z. B. 89,00 €"),
    ("{bezug_nummer}", "Nummer der ursprünglichen Rechnung (bei Storno)"),
    ("{bezug_datum}", "Datum der ursprünglichen Rechnung (bei Storno)"),
    ("{firma_name}", "Ihr Firmenname"),
    ("{inhaber}", "Ihr Name"),
    ("{firma_telefon}", "Ihre Telefonnummer"),
    ("{firma_web}", "Ihre Internetseite"),
]
