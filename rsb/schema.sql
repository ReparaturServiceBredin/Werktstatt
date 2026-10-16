-- Datenbankschema Reparatur Service Bredin
-- Beträge werden immer in CENT (ganze Zahlen) gespeichert, damit keine Rundungsfehler entstehen.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS einstellungen (
    schluessel TEXT PRIMARY KEY,
    wert       TEXT
);

CREATE TABLE IF NOT EXISTS kunden (
    id               INTEGER PRIMARY KEY,
    kundennr         TEXT UNIQUE NOT NULL,
    typ              TEXT NOT NULL DEFAULT 'privat' CHECK (typ IN ('privat', 'firma')),
    firma            TEXT,
    anrede           TEXT,
    vorname          TEXT,
    nachname         TEXT,
    strasse          TEXT,
    plz              TEXT,
    ort              TEXT,
    land             TEXT DEFAULT 'Deutschland',
    email            TEXT,
    telefon          TEXT,
    ust_idnr         TEXT,
    zahlungsziel_tage INTEGER,
    notizen          TEXT,
    email_weitere    TEXT,            -- weitere Adressen / Ansprechpartner (eine je Zeile) für die E-Mail-Historie
    interessent      INTEGER NOT NULL DEFAULT 0,
    quelle           TEXT,
    archiviert       INTEGER NOT NULL DEFAULT 0,
    anonymisiert_am  TEXT,
    e_rechnung       TEXT,            -- auto / pdf / zugferd / xrechnung
    leitweg_id       TEXT,            -- Käuferreferenz für XRechnung (Behörden)            -- gesetzt, wenn der Kunde auf Wunsch gelöscht, wegen Aufbewahrungspflicht aber anonymisiert wurde
    erstellt_am      TEXT NOT NULL,
    geaendert_am     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS artikel (
    id                INTEGER PRIMARY KEY,
    artikelnr         TEXT,
    name              TEXT NOT NULL,
    beschreibung      TEXT,
    leistungsart      TEXT,
    typ               TEXT NOT NULL DEFAULT 'leistung' CHECK (typ IN ('leistung', 'material')),
    einheit           TEXT DEFAULT 'Stk.',
    preis             INTEGER NOT NULL DEFAULT 0,   -- Verkaufspreis (netto) in Cent
    teilekosten       INTEGER NOT NULL DEFAULT 0,   -- Einkauf/Teilekosten in Cent
    aufschlag_prozent REAL,
    steuersatz        REAL NOT NULL DEFAULT 19,
    ek_unbekannt      INTEGER NOT NULL DEFAULT 0,   -- 1 = Einkaufspreis nicht bekannt -> keine Marge anzeigen
    garantie_monate   INTEGER,                      -- Garantie-Vorschlag für Rechnungspositionen
    -- Lager (0.16.0): Bestand nur über lagerbewegungen ändern (bestand = Zwischenspeicher)
    lagerfuehrend     INTEGER NOT NULL DEFAULT 0,
    bestand           REAL NOT NULL DEFAULT 0,
    mindestbestand    REAL,
    lagerort          TEXT,
    ean               TEXT,
    herstellernr      TEXT,
    kompatibilitaet   TEXT,                         -- z. B. „iPhone 13, iPhone 13 Pro“ (durchsuchbar)
    aktiv             INTEGER NOT NULL DEFAULT 1,
    erstellt_am       TEXT NOT NULL,
    geaendert_am      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS textbausteine (
    id          INTEGER PRIMARY KEY,
    kategorie   TEXT NOT NULL,       -- einleitung, schluss, hinweis, email_betreff, email_text
    dokumenttyp TEXT NOT NULL DEFAULT 'alle',
    name        TEXT NOT NULL,
    text        TEXT NOT NULL,
    standard    INTEGER NOT NULL DEFAULT 0
);

-- Fortlaufende Nummernkreise (je Präfix und Jahr)
CREATE TABLE IF NOT EXISTS nummernkreise (
    praefix       TEXT NOT NULL,
    jahr          INTEGER NOT NULL,
    letzte_nummer INTEGER NOT NULL DEFAULT 0,
    format        TEXT NOT NULL DEFAULT '{praefix}-{jahr}-{nummer:04d}',
    PRIMARY KEY (praefix, jahr)
);

CREATE TABLE IF NOT EXISTS dokumente (
    id               INTEGER PRIMARY KEY,
    typ              TEXT NOT NULL,   -- rechnung, storno (weitere Typen folgen in Etappe 2)
    status           TEXT NOT NULL DEFAULT 'entwurf' CHECK (status IN ('entwurf', 'festgeschrieben', 'storniert')),
    nummer           TEXT UNIQUE,
    kunde_id         INTEGER REFERENCES kunden(id),
    datum            TEXT NOT NULL,
    leistungsdatum   TEXT,
    leistungsdatum_bis TEXT,
    zahlungsziel_tage INTEGER,
    faellig_am       TEXT,
    betreff          TEXT,
    einleitung       TEXT,
    schlusstext      TEXT,
    hinweise         TEXT,
    steuer_modus     TEXT NOT NULL DEFAULT 'kleinunternehmer',
    bezug_id         INTEGER REFERENCES dokumente(id),
    summe_netto      INTEGER NOT NULL DEFAULT 0,
    summe_steuer     INTEGER NOT NULL DEFAULT 0,
    summe_brutto     INTEGER NOT NULL DEFAULT 0,
    snapshot_json    TEXT,
    pdf_pfad         TEXT,
    pdf_sha256       TEXT,
    festgeschrieben_am TEXT,
    storniert_durch  INTEGER REFERENCES dokumente(id),
    versendet_am     TEXT,
    bezahlt_betrag   INTEGER NOT NULL DEFAULT 0,
    kva_status       TEXT,            -- nur Kostenvoranschlag: offen / angenommen / abgelehnt
    snapshot_sha256  TEXT,
    e_format         TEXT,            -- pdf / zugferd / xrechnung (beim Festschreiben)
    xml_pfad         TEXT,            -- archivierte E-Rechnungs-XML
    xml_sha256       TEXT,            -- Prüfsumme der beim Festschreiben archivierten Rechnungsdaten (JSON)
    erstellt_am      TEXT NOT NULL,
    geaendert_am     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS positionen (
    id            INTEGER PRIMARY KEY,
    dokument_id   INTEGER NOT NULL REFERENCES dokumente(id),
    pos           INTEGER NOT NULL,
    artikel_id    INTEGER REFERENCES artikel(id),
    bezeichnung   TEXT NOT NULL,
    beschreibung  TEXT,
    menge         REAL NOT NULL DEFAULT 1,
    einheit       TEXT,
    einzelpreis   INTEGER NOT NULL DEFAULT 0,   -- Cent, netto
    teilekosten   INTEGER NOT NULL DEFAULT 0,   -- Cent je Einheit (für Margenauswertung)
    steuersatz    REAL NOT NULL DEFAULT 0,
    leistungsart  TEXT,
    garantie_monate INTEGER                      -- abweichende Garantie für diese Position (leer = Standard)
);

-- Versandprotokoll für E-Mails
CREATE TABLE IF NOT EXISTS versandprotokoll (
    id             INTEGER PRIMARY KEY,
    dokument_id    INTEGER REFERENCES dokumente(id),
    zeitpunkt      TEXT NOT NULL,
    empfaenger     TEXT NOT NULL,
    bcc            TEXT,
    betreff        TEXT,
    text           TEXT,
    anhang_name    TEXT,
    anhang_sha256  TEXT,
    status         TEXT NOT NULL,   -- gesendet / fehler
    fehlermeldung  TEXT,
    ablage         TEXT             -- Kopie im IMAP-Gesendet-Ordner: abgelegt / fehler: … / leer = nicht aktiv
);

-- Änderungsprotokoll (nur anhängen, mit Hash-Kette gegen unbemerkte Manipulation)
CREATE TABLE IF NOT EXISTS protokoll (
    id          INTEGER PRIMARY KEY,
    zeitpunkt   TEXT NOT NULL,
    benutzer    TEXT,
    aktion      TEXT NOT NULL,
    objekt      TEXT,
    objekt_id   INTEGER,
    details     TEXT,
    hash_vorher TEXT NOT NULL,
    hash        TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_dok_kunde ON dokumente(kunde_id);
CREATE INDEX IF NOT EXISTS ix_pos_dok ON positionen(dokument_id);

-- ------------------------------------------------------------------
-- Schutzregeln (Trigger): festgeschriebene Dokumente sind unveränderbar
-- ------------------------------------------------------------------

DROP TRIGGER IF EXISTS dok_schutz_update;
CREATE TRIGGER dok_schutz_update
BEFORE UPDATE ON dokumente
WHEN OLD.status <> 'entwurf' AND (
       NEW.status = 'entwurf'
    OR NEW.typ IS NOT OLD.typ
    OR NEW.nummer IS NOT OLD.nummer
    OR NEW.kunde_id IS NOT OLD.kunde_id
    OR NEW.datum IS NOT OLD.datum
    OR NEW.leistungsdatum IS NOT OLD.leistungsdatum
    OR NEW.leistungsdatum_bis IS NOT OLD.leistungsdatum_bis
    OR NEW.faellig_am IS NOT OLD.faellig_am
    OR NEW.betreff IS NOT OLD.betreff
    OR NEW.einleitung IS NOT OLD.einleitung
    OR NEW.schlusstext IS NOT OLD.schlusstext
    OR NEW.hinweise IS NOT OLD.hinweise
    OR NEW.steuer_modus IS NOT OLD.steuer_modus
    OR NEW.bezug_id IS NOT OLD.bezug_id
    OR NEW.summe_netto IS NOT OLD.summe_netto
    OR NEW.summe_steuer IS NOT OLD.summe_steuer
    OR NEW.summe_brutto IS NOT OLD.summe_brutto
    OR NEW.snapshot_json IS NOT OLD.snapshot_json
    OR NEW.pdf_pfad IS NOT OLD.pdf_pfad
    OR NEW.pdf_sha256 IS NOT OLD.pdf_sha256
    OR NEW.festgeschrieben_am IS NOT OLD.festgeschrieben_am
    OR NEW.snapshot_sha256 IS NOT OLD.snapshot_sha256
    OR NEW.e_format IS NOT OLD.e_format
    OR NEW.xml_pfad IS NOT OLD.xml_pfad
    OR NEW.xml_sha256 IS NOT OLD.xml_sha256
    OR NEW.zahlungsziel_tage IS NOT OLD.zahlungsziel_tage
    OR (OLD.storniert_durch IS NOT NULL AND NEW.storniert_durch IS NOT OLD.storniert_durch)
)
BEGIN
    SELECT RAISE(ABORT, 'Festgeschriebene Dokumente können nicht geändert werden. Bitte Storno oder Gutschrift verwenden.');
END;

CREATE TRIGGER IF NOT EXISTS dok_schutz_delete
BEFORE DELETE ON dokumente
WHEN OLD.status <> 'entwurf' OR OLD.nummer IS NOT NULL
BEGIN
    SELECT RAISE(ABORT, 'Festgeschriebene Dokumente können nicht gelöscht werden.');
END;

CREATE TRIGGER IF NOT EXISTS pos_schutz_insert
BEFORE INSERT ON positionen
WHEN (SELECT status FROM dokumente WHERE id = NEW.dokument_id) <> 'entwurf'
BEGIN
    SELECT RAISE(ABORT, 'Positionen festgeschriebener Dokumente können nicht geändert werden.');
END;

CREATE TRIGGER IF NOT EXISTS pos_schutz_update
BEFORE UPDATE ON positionen
WHEN (SELECT status FROM dokumente WHERE id = OLD.dokument_id) <> 'entwurf'
BEGIN
    SELECT RAISE(ABORT, 'Positionen festgeschriebener Dokumente können nicht geändert werden.');
END;

CREATE TRIGGER IF NOT EXISTS pos_schutz_delete
BEFORE DELETE ON positionen
WHEN (SELECT status FROM dokumente WHERE id = OLD.dokument_id) <> 'entwurf'
BEGIN
    SELECT RAISE(ABORT, 'Positionen festgeschriebener Dokumente können nicht gelöscht werden.');
END;

CREATE TRIGGER IF NOT EXISTS nummernkreis_schutz
BEFORE UPDATE ON nummernkreise
WHEN NEW.letzte_nummer < OLD.letzte_nummer
BEGIN
    SELECT RAISE(ABORT, 'Nummernkreise können nicht zurückgesetzt werden.');
END;

CREATE TRIGGER IF NOT EXISTS nummernkreis_schutz_delete
BEFORE DELETE ON nummernkreise
BEGIN
    SELECT RAISE(ABORT, 'Nummernkreise können nicht gelöscht werden.');
END;

CREATE TRIGGER IF NOT EXISTS protokoll_schutz_update
BEFORE UPDATE ON protokoll
BEGIN
    SELECT RAISE(ABORT, 'Das Protokoll kann nicht geändert werden.');
END;

CREATE TRIGGER IF NOT EXISTS protokoll_schutz_delete
BEFORE DELETE ON protokoll
BEGIN
    SELECT RAISE(ABORT, 'Das Protokoll kann nicht gelöscht werden.');
END;

CREATE TRIGGER IF NOT EXISTS versand_schutz_update
BEFORE UPDATE ON versandprotokoll
BEGIN
    SELECT RAISE(ABORT, 'Das Versandprotokoll kann nicht geändert werden.');
END;

CREATE TRIGGER IF NOT EXISTS versand_schutz_delete
BEFORE DELETE ON versandprotokoll
BEGIN
    SELECT RAISE(ABORT, 'Das Versandprotokoll kann nicht gelöscht werden.');
END;

-- Anfragen aus dem Kontaktformular (per E-Mail abgeholt oder manuell eingefügt)
CREATE TABLE IF NOT EXISTS anfragen (
    id           INTEGER PRIMARY KEY,
    eingang_am   TEXT NOT NULL,
    quelle       TEXT NOT NULL DEFAULT 'email',   -- email / manuell
    message_id   TEXT UNIQUE,
    absender     TEXT,
    betreff      TEXT,
    name         TEXT,
    vorname      TEXT,
    nachname     TEXT,
    telefon      TEXT,
    email        TEXT,
    geraet       TEXT,
    nachricht    TEXT,
    felder_json  TEXT,
    rohtext      TEXT,
    spam_punkte  INTEGER NOT NULL DEFAULT 0,
    gruende_json TEXT,
    einstufung   TEXT NOT NULL,                   -- echt / unsicher / spam
    status       TEXT NOT NULL DEFAULT 'neu',     -- neu / kunde_angelegt / zugeordnet / verworfen
    kunde_id     INTEGER REFERENCES kunden(id) ON DELETE SET NULL,
    bearbeitet_am TEXT
);
CREATE INDEX IF NOT EXISTS ix_anfragen_status ON anfragen(status, einstufung);

-- Reparaturaufträge (Tafel: offen -> in Arbeit -> erledigt)
CREATE TABLE IF NOT EXISTS auftraege (
    id              INTEGER PRIMARY KEY,
    auftragsnr      TEXT UNIQUE NOT NULL,
    kunde_id        INTEGER NOT NULL REFERENCES kunden(id),
    anfrage_id      INTEGER REFERENCES anfragen(id) ON DELETE SET NULL,
    status          TEXT NOT NULL DEFAULT 'offen' CHECK (status IN ('offen', 'in_arbeit', 'erledigt')),
    geraet          TEXT,
    leistungsart    TEXT,
    seriennummer    TEXT,
    zubehoer        TEXT,
    fehler          TEXT,
    notizen         TEXT,
    kva_id          INTEGER REFERENCES dokumente(id),
    rechnung_id     INTEGER REFERENCES dokumente(id),
    reihenfolge     REAL NOT NULL DEFAULT 0,
    eingang_am      TEXT NOT NULL,
    begonnen_am     TEXT,
    erledigt_am     TEXT,
    erstellt_am     TEXT NOT NULL,
    geaendert_am    TEXT NOT NULL,
    -- Annahme (0.13.0)
    zustand_eingang TEXT,
    kosten_obergrenze INTEGER,          -- Cent brutto: bis zu diesem Betrag ohne Rückfrage reparieren
    kva_gewuenscht  INTEGER NOT NULL DEFAULT 0,
    kva_gebuehr     INTEGER,            -- Cent brutto: Gebühr, falls der KVA abgelehnt wird
    fertig_bis      TEXT,               -- voraussichtliche Fertigstellung
    zugang_art      TEXT,               -- pin / passwort / muster / telefonisch / keiner
    zugang_geheim   TEXT,               -- verschlüsselt (Fernet), wird nach Abschluss gelöscht
    zugang_geloescht_am TEXT,
    abgeholt_am     TEXT,
    garantie_ende   TEXT,               -- freiwillige Garantie: Ende (gespeichert bei Abholung)
    geraetetyp      TEXT,               -- für die KVA-Pauschale (Einstellungen: Gebühr je Gerätetyp)
    -- Warten auf Ersatzteil (Spalte „Wartet auf Teil“ auf der Tafel; Status bleibt in_arbeit)
    wartet_teil_seit TEXT,
    teil_info       TEXT,
    teil_erwartet   TEXT,
    -- Garantie (0.15.0)
    auftragsart     TEXT NOT NULL DEFAULT 'reparatur',   -- reparatur / garantie
    garantie_bezug_id INTEGER REFERENCES auftraege(id),  -- Garantiefall: ursprünglicher Auftrag
    garantie_monate INTEGER,                             -- leer = Standard aus den Einstellungen
    interne_kosten  INTEGER,                             -- Cent, z. B. Teile/Arbeitszeit eines Garantiefalls
    interne_kosten_notiz TEXT,
    -- Fahrzeug (Werkstatt Sauter): geraet = Marke/Modell, seriennummer = FIN, geraetetyp = Fahrzeugart
    kennzeichen     TEXT,
    km_stand        INTEGER,
    erstzulassung   TEXT,
    hu_bis          TEXT                -- nächste HU/TÜV (Monat, JJJJ-MM)
);
CREATE INDEX IF NOT EXISTS ix_auftraege_status ON auftraege(status);

-- Vertragsarten (frei erweiterbar): z. B. Wertgarantie, ESET-Lizenz, MSP-Paket
CREATE TABLE IF NOT EXISTS vertragsarten (
    id                    INTEGER PRIMARY KEY,
    name                  TEXT NOT NULL,
    kategorie             TEXT NOT NULL DEFAULT 'Sonstiges',
    beschreibung          TEXT,
    abrechnung            TEXT NOT NULL DEFAULT 'monatlich',   -- keine / monatlich / vierteljaehrlich / halbjaehrlich / jaehrlich / laufzeit
    laufzeit_monate       INTEGER,                             -- leer = unbefristet
    mindestlaufzeit_monate INTEGER,
    preis                 INTEGER NOT NULL DEFAULT 0,          -- Cent je Abrechnung (bei "laufzeit": für die ganze Laufzeit)
    einkauf               INTEGER NOT NULL DEFAULT 0,          -- Cent Einkauf je Abrechnung (für die Marge)
    auto_verlaengern      INTEGER NOT NULL DEFAULT 0,
    aktiv                 INTEGER NOT NULL DEFAULT 1,
    erstellt_am           TEXT NOT NULL
);

-- Verträge / Lizenzen / Garantien beim Kunden
CREATE TABLE IF NOT EXISTS vertraege (
    id                    INTEGER PRIMARY KEY,
    kunde_id              INTEGER NOT NULL REFERENCES kunden(id),
    vertragsart_id        INTEGER REFERENCES vertragsarten(id) ON DELETE SET NULL,
    bezeichnung           TEXT NOT NULL,
    kategorie             TEXT NOT NULL DEFAULT 'Sonstiges',
    abrechnung            TEXT NOT NULL DEFAULT 'monatlich',
    beginn                TEXT NOT NULL,
    laufzeit_monate       INTEGER,
    mindestlaufzeit_monate INTEGER,
    ende                  TEXT,                                -- Ende der aktuellen Laufzeit (bei befristeten Lizenzen)
    auto_verlaengern      INTEGER NOT NULL DEFAULT 0,
    preis                 INTEGER NOT NULL DEFAULT 0,
    einkauf               INTEGER NOT NULL DEFAULT 0,
    anzahl                REAL NOT NULL DEFAULT 1,
    vertragsnummer        TEXT,                                -- Vertrags-/Policen-/Lizenznummer, Lizenzschlüssel
    geraet                TEXT,                                -- Gerät / Seriennummer (z. B. bei Wertgarantie)
    notizen               TEXT,
    status                TEXT NOT NULL DEFAULT 'aktiv' CHECK (status IN ('aktiv', 'gekuendigt')),
    gekuendigt_am         TEXT,
    kuendigung_zum        TEXT,
    kuendigungsgrund      TEXT,
    abgerechnet_bis       TEXT,                                -- bis hier schon anderweitig berechnet (z. B. Lexware)
    erstellt_am           TEXT NOT NULL,
    geaendert_am          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_vertraege_kunde ON vertraege(kunde_id);

-- Welche Zeiträume eines Vertrags schon abgerechnet sind (verhindert doppelte Rechnungen)
CREATE TABLE IF NOT EXISTS vertrag_abrechnungen (
    id           INTEGER PRIMARY KEY,
    vertrag_id   INTEGER NOT NULL REFERENCES vertraege(id) ON DELETE CASCADE,
    dokument_id  INTEGER NOT NULL REFERENCES dokumente(id) ON DELETE CASCADE,
    von          TEXT NOT NULL,
    bis          TEXT NOT NULL,
    betrag       INTEGER NOT NULL,
    UNIQUE (vertrag_id, von)
);

-- Fotodokumentation zu Reparaturaufträgen: Originale bleiben unverändert, Löschen nur als Markierung mit Grund
CREATE TABLE IF NOT EXISTS auftrag_fotos (
    id             INTEGER PRIMARY KEY,
    auftrag_id     INTEGER REFERENCES auftraege(id),   -- leer = beim Anlegen hochgeladen, noch nicht zugeordnet
    upload_token   TEXT,                               -- Zuordnung von Fotos aus „+ Neuer Auftrag“
    kategorie      TEXT NOT NULL,
    dateiname      TEXT NOT NULL,                      -- ursprünglicher Dateiname
    pfad           TEXT NOT NULL,                      -- relativ zum Datenordner
    mime           TEXT,
    groesse        INTEGER NOT NULL,
    sha256         TEXT NOT NULL,
    exif_zeit      TEXT,                               -- Aufnahmezeit laut Kamera (EXIF), falls vorhanden
    hochgeladen_am TEXT NOT NULL,                      -- Server-Zeit Europe/Berlin mit Sekunden
    benutzer       TEXT,
    geloescht_am   TEXT,
    geloescht_von  TEXT,
    loeschgrund    TEXT,
    leihgeraet_id  INTEGER,                            -- Fotos eines Leihgeräts (Stammdaten, Ausgabe, Rückgabe)
    leihe_id       INTEGER,
    schadensfall_id INTEGER
);
CREATE INDEX IF NOT EXISTS ix_fotos_auftrag ON auftrag_fotos(auftrag_id);
CREATE INDEX IF NOT EXISTS ix_fotos_token ON auftrag_fotos(upload_token);

-- Zuordnungen (Auftrag, Leihgerät, Leihe, Schadensfall) dürfen nur einmalig von leer auf einen Wert gesetzt werden
DROP TRIGGER IF EXISTS foto_schutz_update;
CREATE TRIGGER foto_schutz_update
BEFORE UPDATE ON auftrag_fotos
WHEN NEW.id IS NOT OLD.id OR NEW.kategorie IS NOT OLD.kategorie OR NEW.dateiname IS NOT OLD.dateiname
  OR NEW.pfad IS NOT OLD.pfad OR NEW.groesse IS NOT OLD.groesse OR NEW.sha256 IS NOT OLD.sha256
  OR NEW.exif_zeit IS NOT OLD.exif_zeit OR NEW.hochgeladen_am IS NOT OLD.hochgeladen_am
  OR NEW.benutzer IS NOT OLD.benutzer OR NEW.mime IS NOT OLD.mime
  OR (OLD.auftrag_id IS NOT NULL AND NEW.auftrag_id IS NOT OLD.auftrag_id)
  OR (OLD.leihgeraet_id IS NOT NULL AND NEW.leihgeraet_id IS NOT OLD.leihgeraet_id)
  OR (OLD.leihe_id IS NOT NULL AND NEW.leihe_id IS NOT OLD.leihe_id)
  OR (OLD.schadensfall_id IS NOT NULL AND NEW.schadensfall_id IS NOT OLD.schadensfall_id)
  OR (OLD.geloescht_am IS NOT NULL AND (NEW.geloescht_am IS NOT OLD.geloescht_am
      OR NEW.geloescht_von IS NOT OLD.geloescht_von OR NEW.loeschgrund IS NOT OLD.loeschgrund))
BEGIN
    SELECT RAISE(ABORT, 'Fotos können nicht verändert werden (nur einmalig zuordnen oder als gelöscht markieren).');
END;

CREATE TRIGGER IF NOT EXISTS foto_schutz_delete
BEFORE DELETE ON auftrag_fotos
BEGIN
    SELECT RAISE(ABORT, 'Fotos können nicht gelöscht werden – bitte mit Begründung als gelöscht markieren.');
END;

-- Verlauf je Reparaturauftrag (nur anhängen)
CREATE TABLE IF NOT EXISTS auftrag_verlauf (
    id          INTEGER PRIMARY KEY,
    auftrag_id  INTEGER NOT NULL,
    zeitpunkt   TEXT NOT NULL,
    benutzer    TEXT,
    ereignis    TEXT NOT NULL,
    details     TEXT
);
CREATE INDEX IF NOT EXISTS ix_verlauf_auftrag ON auftrag_verlauf(auftrag_id);

CREATE TRIGGER IF NOT EXISTS verlauf_schutz_update
BEFORE UPDATE ON auftrag_verlauf
BEGIN
    SELECT RAISE(ABORT, 'Der Verlauf kann nicht geändert werden.');
END;

CREATE TRIGGER IF NOT EXISTS verlauf_schutz_delete
BEFORE DELETE ON auftrag_verlauf
BEGIN
    SELECT RAISE(ABORT, 'Der Verlauf kann nicht gelöscht werden.');
END;

-- ====================================================================== Leihgeräte
CREATE TABLE IF NOT EXISTS leihgeraete (
    id                INTEGER PRIMARY KEY,
    bezeichnung       TEXT NOT NULL,                  -- z. B. „Lenovo ThinkPad T14 #1“
    geraetetyp        TEXT,
    hersteller        TEXT,
    modell            TEXT,
    seriennummer      TEXT,
    inventarnr        TEXT,
    zubehoer          TEXT NOT NULL DEFAULT '[]',     -- JSON-Liste: Standardzubehör
    zustand           TEXT,                           -- Zustand / Bemerkungen
    anschaffung_am    TEXT,
    anschaffungswert  INTEGER NOT NULL DEFAULT 0,     -- Cent
    zeitwert          INTEGER NOT NULL DEFAULT 0,     -- Cent, für Schadensfälle
    gebuehr_art       TEXT NOT NULL DEFAULT 'kostenlos' CHECK (gebuehr_art IN ('kostenlos', 'pauschal', 'tag')),
    gebuehr_betrag    INTEGER NOT NULL DEFAULT 0,     -- Cent (pauschal oder je Tag)
    frei_tage         INTEGER NOT NULL DEFAULT 0,     -- nur bei „pro Tag“: so viele Tage kostenlos
    kaution           INTEGER NOT NULL DEFAULT 0,     -- Cent, 0 = keine
    status            TEXT NOT NULL DEFAULT 'verfuegbar'
                      CHECK (status IN ('verfuegbar', 'verliehen', 'defekt', 'ausgemustert')),
    erstellt_am       TEXT NOT NULL,
    geaendert_am      TEXT NOT NULL
);

CREATE TRIGGER IF NOT EXISTS leihgeraet_schutz_delete
BEFORE DELETE ON leihgeraete
BEGIN
    SELECT RAISE(ABORT, 'Leihgeräte können nicht gelöscht werden – bitte auf „Ausgemustert“ setzen.');
END;

-- Eine Leihe = Ausgabe eines Leihgeräts an einen Kunden zu einem Reparaturauftrag (Leihvertrag)
CREATE TABLE IF NOT EXISTS leihen (
    id                 INTEGER PRIMARY KEY,
    leihnr             TEXT UNIQUE NOT NULL,          -- LV-2026-0001
    geraet_id          INTEGER NOT NULL REFERENCES leihgeraete(id),
    auftrag_id         INTEGER REFERENCES auftraege(id) ON DELETE SET NULL,
    auftragsnr         TEXT,                          -- bleibt lesbar, auch falls der Auftrag gelöscht würde
    kunde_id           INTEGER NOT NULL REFERENCES kunden(id),
    -- Ausgabe
    ausgabe_am         TEXT NOT NULL,                 -- Europe/Berlin mit Sekunden
    rueckgabe_geplant  TEXT,                          -- Datum
    zubehoer_ausgabe   TEXT NOT NULL DEFAULT '[]',    -- JSON-Liste: mitgegeben
    zustand_ausgabe    TEXT,
    gebuehr_art        TEXT NOT NULL CHECK (gebuehr_art IN ('kostenlos', 'kulanz', 'pauschal', 'tag')),
    gebuehr_betrag     INTEGER NOT NULL DEFAULT 0,
    frei_tage          INTEGER NOT NULL DEFAULT 0,
    kaution_erhalten   INTEGER NOT NULL DEFAULT 0,
    kaution_betrag     INTEGER NOT NULL DEFAULT 0,
    kaution_zahlart    TEXT,
    ausgegeben_von     TEXT,
    erfasst_am         TEXT NOT NULL,                 -- Server-Zeit der Erfassung
    -- Rückgabe
    rueckgabe_am       TEXT,
    zubehoer_rueckgabe TEXT,                          -- JSON-Liste: zurückgekommen
    zustand_rueckgabe  TEXT CHECK (zustand_rueckgabe IS NULL OR zustand_rueckgabe IN ('einwandfrei', 'schaden')),
    rueckgabe_notiz    TEXT,
    zurueckgenommen_von TEXT,
    rueckgabe_erfasst_am TEXT,
    tage               INTEGER,                       -- berechnete Leihtage
    gebuehr_berechnet  INTEGER,                       -- Cent, nach Prüfung übernommen
    gebuehr_text       TEXT,
    -- Kaution: keine / gehalten / zurueckzuzahlen / zurueckgezahlt / verrechnet
    kaution_status     TEXT NOT NULL DEFAULT 'keine',
    kaution_erledigt_am TEXT,
    -- Abrechnung
    separat_abrechnen  INTEGER NOT NULL DEFAULT 0,
    rechnung_id        INTEGER REFERENCES dokumente(id),
    -- Markierung statt Löschen
    storniert_am       TEXT,
    storniert_von      TEXT,
    protokoll_geloescht_am TEXT,          -- Datenschutz: Protokollinhalte nach Ablauf der Löschfrist entfernt
    storno_grund       TEXT
);
CREATE INDEX IF NOT EXISTS ix_leihen_geraet ON leihen(geraet_id);
CREATE INDEX IF NOT EXISTS ix_leihen_auftrag ON leihen(auftrag_id);
CREATE INDEX IF NOT EXISTS ix_leihen_kunde ON leihen(kunde_id);

-- Gezielte Freigabe für den Datenschutz-Löschlauf (nach Ablauf der Löschfrist): nur für die hier eingetragene Zeile
-- heben die Schutzregeln von Leihprotokollen und Annahme-/Abholscheinen ihre Sperre auf.
CREATE TABLE IF NOT EXISTS loeschfreigaben (
    tabelle  TEXT NOT NULL,
    zeile_id INTEGER NOT NULL,
    PRIMARY KEY (tabelle, zeile_id)
);

DROP TRIGGER IF EXISTS leihe_schutz_update;
CREATE TRIGGER leihe_schutz_update
BEFORE UPDATE ON leihen
WHEN NOT EXISTS (SELECT 1 FROM loeschfreigaben WHERE tabelle='leihen' AND zeile_id=OLD.id) AND (
     NEW.leihnr IS NOT OLD.leihnr OR NEW.geraet_id IS NOT OLD.geraet_id OR NEW.kunde_id IS NOT OLD.kunde_id
  OR NEW.ausgabe_am IS NOT OLD.ausgabe_am OR NEW.zubehoer_ausgabe IS NOT OLD.zubehoer_ausgabe
  OR NEW.zustand_ausgabe IS NOT OLD.zustand_ausgabe OR NEW.erfasst_am IS NOT OLD.erfasst_am
  OR NEW.kaution_betrag IS NOT OLD.kaution_betrag OR NEW.kaution_erhalten IS NOT OLD.kaution_erhalten
  OR (OLD.rueckgabe_am IS NOT NULL AND (NEW.rueckgabe_am IS NOT OLD.rueckgabe_am
      OR NEW.zustand_rueckgabe IS NOT OLD.zustand_rueckgabe OR NEW.zubehoer_rueckgabe IS NOT OLD.zubehoer_rueckgabe
      OR NEW.rueckgabe_notiz IS NOT OLD.rueckgabe_notiz))
  OR (OLD.storniert_am IS NOT NULL AND (NEW.storniert_am IS NOT OLD.storniert_am OR NEW.storno_grund IS NOT OLD.storno_grund)))
BEGIN
    SELECT RAISE(ABORT, 'Ausgabe- und Rückgabeprotokolle können nicht nachträglich geändert werden.');
END;

CREATE TRIGGER IF NOT EXISTS leihe_schutz_delete
BEFORE DELETE ON leihen
BEGIN
    SELECT RAISE(ABORT, 'Leihvorgänge können nicht gelöscht werden – bitte mit Begründung stornieren.');
END;

CREATE TABLE IF NOT EXISTS schadensfaelle (
    id                  INTEGER PRIMARY KEY,
    leihe_id            INTEGER NOT NULL REFERENCES leihen(id),
    geraet_id           INTEGER NOT NULL REFERENCES leihgeraete(id),
    beschreibung        TEXT NOT NULL,
    kostenart           TEXT NOT NULL CHECK (kostenart IN ('reparatur', 'zubehoer', 'totalschaden')),
    betrag              INTEGER NOT NULL DEFAULT 0,   -- Cent
    erstellt_am         TEXT NOT NULL,
    benutzer            TEXT,
    interner_auftrag_id INTEGER REFERENCES auftraege(id) ON DELETE SET NULL,
    rechnung_id         INTEGER REFERENCES dokumente(id),
    storniert_am        TEXT,
    storniert_von       TEXT,
    storno_grund        TEXT
);
CREATE INDEX IF NOT EXISTS ix_schaden_leihe ON schadensfaelle(leihe_id);

CREATE TRIGGER IF NOT EXISTS schaden_schutz_update
BEFORE UPDATE ON schadensfaelle
WHEN NEW.leihe_id IS NOT OLD.leihe_id OR NEW.geraet_id IS NOT OLD.geraet_id
  OR NEW.beschreibung IS NOT OLD.beschreibung OR NEW.kostenart IS NOT OLD.kostenart OR NEW.betrag IS NOT OLD.betrag
  OR NEW.erstellt_am IS NOT OLD.erstellt_am OR NEW.benutzer IS NOT OLD.benutzer
  OR (OLD.storniert_am IS NOT NULL AND (NEW.storniert_am IS NOT OLD.storniert_am OR NEW.storno_grund IS NOT OLD.storno_grund))
BEGIN
    SELECT RAISE(ABORT, 'Schadensfälle können nicht geändert werden – bei Fehlern stornieren und neu anlegen.');
END;

CREATE TRIGGER IF NOT EXISTS schaden_schutz_delete
BEFORE DELETE ON schadensfaelle
BEGIN
    SELECT RAISE(ABORT, 'Schadensfälle können nicht gelöscht werden – bitte mit Begründung stornieren.');
END;

-- Historie je Leihgerät (nur anhängen)
CREATE TABLE IF NOT EXISTS leihgeraet_verlauf (
    id          INTEGER PRIMARY KEY,
    geraet_id   INTEGER NOT NULL,
    zeitpunkt   TEXT NOT NULL,
    benutzer    TEXT,
    ereignis    TEXT NOT NULL,
    details     TEXT
);
CREATE INDEX IF NOT EXISTS ix_lgverlauf_geraet ON leihgeraet_verlauf(geraet_id);

CREATE TRIGGER IF NOT EXISTS lgverlauf_schutz_update
BEFORE UPDATE ON leihgeraet_verlauf
BEGIN
    SELECT RAISE(ABORT, 'Die Historie kann nicht geändert werden.');
END;

CREATE TRIGGER IF NOT EXISTS lgverlauf_schutz_delete
BEFORE DELETE ON leihgeraet_verlauf
BEGIN
    SELECT RAISE(ABORT, 'Die Historie kann nicht gelöscht werden.');
END;

-- ====================================================================== E-Mail-Historie je Kunde
-- Nur Mails mit mindestens einem Kundentreffer werden gespeichert (alle anderen werden übersprungen).
CREATE TABLE IF NOT EXISTS email_nachrichten (
    id            INTEGER PRIMARY KEY,
    message_id    TEXT UNIQUE NOT NULL,             -- verhindert Duplikate (mehrere Ordner, selbst versendet)
    richtung      TEXT NOT NULL CHECK (richtung IN ('gesendet', 'empfangen')),
    datum         TEXT,                             -- laut Date-Kopf, deutsche Zeit
    von           TEXT,
    an            TEXT,
    cc            TEXT,
    betreff       TEXT,
    text          TEXT,                             -- lesbarer Text der Mail (HTML wird in Text umgewandelt)
    anhaenge      TEXT,                             -- JSON-Liste: Name und Größe (Inhalte werden nicht gespeichert)
    quelle        TEXT NOT NULL DEFAULT 'imap',     -- imap / programm (beim Versand aus dem Programm)
    ordner        TEXT,                             -- erster IMAP-Fundort
    imap_uid      INTEGER,
    dokument_id   INTEGER REFERENCES dokumente(id) ON DELETE SET NULL,
    anfrage_id    INTEGER,
    erfasst_am    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_email_datum ON email_nachrichten(datum);

CREATE TABLE IF NOT EXISTS email_kunden (
    nachricht_id  INTEGER NOT NULL REFERENCES email_nachrichten(id) ON DELETE CASCADE,
    kunde_id      INTEGER NOT NULL REFERENCES kunden(id) ON DELETE CASCADE,
    adresse       TEXT,                             -- über welche Adresse zugeordnet
    PRIMARY KEY (nachricht_id, kunde_id)
);
CREATE INDEX IF NOT EXISTS ix_email_kunden_kunde ON email_kunden(kunde_id);

-- Stand des inkrementellen Abrufs je IMAP-Ordner
CREATE TABLE IF NOT EXISTS imap_ordner_status (
    ordner          TEXT PRIMARY KEY,
    uidvalidity     INTEGER,
    letzte_uid      INTEGER NOT NULL DEFAULT 0,
    aktualisiert_am TEXT
);

-- ====================================================================== Änderungsprotokoll (feldgenau, GoBD)
-- Wer hat wann welches Feld von welchem alten auf welchen neuen Wert geändert – nur anhängen.
CREATE TABLE IF NOT EXISTS feldaenderungen (
    id          INTEGER PRIMARY KEY,
    zeitpunkt   TEXT NOT NULL,                      -- Europe/Berlin mit Sekunden
    benutzer    TEXT,
    objekt      TEXT NOT NULL,                      -- dokument / kunde / artikel
    objekt_id   INTEGER NOT NULL,
    aktion      TEXT NOT NULL,                      -- angelegt / geaendert / festgeschrieben / storniert / geloescht …
    feld        TEXT,
    alt         TEXT,
    neu         TEXT
);
CREATE INDEX IF NOT EXISTS ix_feldaenderungen_objekt ON feldaenderungen(objekt, objekt_id);

CREATE TRIGGER IF NOT EXISTS feldaenderungen_schutz_update
BEFORE UPDATE ON feldaenderungen
BEGIN
    SELECT RAISE(ABORT, 'Das Änderungsprotokoll kann nicht geändert werden.');
END;

CREATE TRIGGER IF NOT EXISTS feldaenderungen_schutz_delete
BEFORE DELETE ON feldaenderungen
BEGIN
    SELECT RAISE(ABORT, 'Das Änderungsprotokoll kann nicht gelöscht werden.');
END;

-- ====================================================================== Zahlungen, Bankabgleich, Mahnwesen
-- Zahlungseingänge zu Rechnungen. Nicht löschbar, nur mit Begründung stornierbar.
CREATE TABLE IF NOT EXISTS zahlungen (
    id             INTEGER PRIMARY KEY,
    dokument_id    INTEGER NOT NULL REFERENCES dokumente(id),
    datum          TEXT NOT NULL,                     -- Tag des Zahlungseingangs
    betrag         INTEGER NOT NULL,                  -- Cent; negativ = Erstattung an den Kunden
    zahlart        TEXT NOT NULL CHECK (zahlart IN ('ueberweisung', 'bar', 'karte', 'paypal', 'verrechnung')),
    notiz          TEXT,
    bank_umsatz_id INTEGER,
    erfasst_am     TEXT NOT NULL,                     -- Europe/Berlin mit Sekunden
    benutzer       TEXT,
    storniert_am   TEXT,
    storniert_von  TEXT,
    storno_grund   TEXT
);
CREATE INDEX IF NOT EXISTS ix_zahlungen_dok ON zahlungen(dokument_id);

CREATE TRIGGER IF NOT EXISTS zahlung_schutz_update
BEFORE UPDATE ON zahlungen
WHEN NEW.dokument_id IS NOT OLD.dokument_id OR NEW.datum IS NOT OLD.datum OR NEW.betrag IS NOT OLD.betrag
  OR NEW.zahlart IS NOT OLD.zahlart OR NEW.notiz IS NOT OLD.notiz OR NEW.bank_umsatz_id IS NOT OLD.bank_umsatz_id
  OR NEW.erfasst_am IS NOT OLD.erfasst_am OR NEW.benutzer IS NOT OLD.benutzer
  OR (OLD.storniert_am IS NOT NULL AND (NEW.storniert_am IS NOT OLD.storniert_am OR NEW.storno_grund IS NOT OLD.storno_grund))
BEGIN
    SELECT RAISE(ABORT, 'Zahlungen können nicht geändert werden – bitte mit Begründung stornieren und neu erfassen.');
END;

CREATE TRIGGER IF NOT EXISTS zahlung_schutz_delete
BEFORE DELETE ON zahlungen
BEGIN
    SELECT RAISE(ABORT, 'Zahlungen können nicht gelöscht werden – bitte mit Begründung stornieren.');
END;

-- Importierte Kontoauszüge (CSV / CAMT.053)
CREATE TABLE IF NOT EXISTS bank_importe (
    id            INTEGER PRIMARY KEY,
    dateiname     TEXT,
    format        TEXT,
    sha256        TEXT NOT NULL,
    importiert_am TEXT NOT NULL,
    benutzer      TEXT,
    anzahl        INTEGER NOT NULL DEFAULT 0,      -- neue Umsätze
    doppelt       INTEGER NOT NULL DEFAULT 0       -- bereits bekannte Umsätze (übersprungen)
);

CREATE TABLE IF NOT EXISTS bank_umsaetze (
    id                 INTEGER PRIMARY KEY,
    import_id          INTEGER NOT NULL REFERENCES bank_importe(id),
    kennung            TEXT UNIQUE NOT NULL,      -- verhindert doppelte Umsätze bei überlappenden Auszügen
    buchungstag        TEXT NOT NULL,
    valuta             TEXT,
    betrag             INTEGER NOT NULL,          -- Cent; positiv = Eingang, negativ = Ausgang
    name               TEXT,
    iban               TEXT,
    verwendungszweck   TEXT,
    status             TEXT NOT NULL DEFAULT 'offen' CHECK (status IN ('offen', 'zugeordnet', 'ignoriert')),
    zahlung_id         INTEGER REFERENCES zahlungen(id),
    er_zahlung_id      INTEGER,                   -- Ausgang: Zahlung auf eine Eingangsrechnung
    bearbeitet_am      TEXT,
    bearbeitet_von     TEXT,
    fixkosten_id       INTEGER,                   -- Ausgang: Abbuchung einer Fixkosten-Position
    fixkosten_monat    TEXT                       -- zu welcher Fälligkeit (JJJJ-MM)
);
CREATE INDEX IF NOT EXISTS ix_bank_status ON bank_umsaetze(status);

CREATE TRIGGER IF NOT EXISTS bank_umsatz_schutz_update
BEFORE UPDATE ON bank_umsaetze
WHEN NEW.kennung IS NOT OLD.kennung OR NEW.buchungstag IS NOT OLD.buchungstag OR NEW.betrag IS NOT OLD.betrag
  OR NEW.verwendungszweck IS NOT OLD.verwendungszweck OR NEW.name IS NOT OLD.name OR NEW.iban IS NOT OLD.iban
BEGIN
    SELECT RAISE(ABORT, 'Importierte Bankumsätze können nicht geändert werden.');
END;

CREATE TRIGGER IF NOT EXISTS bank_umsatz_schutz_delete
BEFORE DELETE ON bank_umsaetze
BEGIN
    SELECT RAISE(ABORT, 'Importierte Bankumsätze können nicht gelöscht werden.');
END;

-- Zahlungserinnerungen und Mahnungen (Stufe 0 = Zahlungserinnerung, 1 = 1. Mahnung, 2 = 2. Mahnung)
CREATE TABLE IF NOT EXISTS mahnungen (
    id              INTEGER PRIMARY KEY,
    dokument_id     INTEGER NOT NULL REFERENCES dokumente(id),
    stufe           INTEGER NOT NULL CHECK (stufe IN (0, 1, 2)),
    nummer          TEXT UNIQUE NOT NULL,
    datum           TEXT NOT NULL,
    frist_bis       TEXT NOT NULL,
    offen_rechnung  INTEGER NOT NULL,               -- offener Rechnungsbetrag zum Mahnzeitpunkt (Cent)
    gebuehr         INTEGER NOT NULL DEFAULT 0,     -- Gebühr dieser Mahnung
    gebuehren_vorher INTEGER NOT NULL DEFAULT 0,    -- noch offene Gebühren früherer Mahnungen
    zinsen          INTEGER NOT NULL DEFAULT 0,     -- Verzugszinsen bis zum Mahndatum
    gesamt          INTEGER NOT NULL,
    snapshot_json   TEXT NOT NULL,
    pdf_pfad        TEXT NOT NULL,
    pdf_sha256      TEXT NOT NULL,
    snapshot_sha256 TEXT NOT NULL,
    erstellt_am     TEXT NOT NULL,
    benutzer        TEXT,
    versendet_am    TEXT,
    versandart      TEXT,                           -- email / pdf (gedruckt)
    erledigt_am     TEXT                            -- z. B. Gebühren erlassen
);
CREATE INDEX IF NOT EXISTS ix_mahnungen_dok ON mahnungen(dokument_id);

CREATE TRIGGER IF NOT EXISTS mahnung_schutz_update
BEFORE UPDATE ON mahnungen
WHEN NEW.dokument_id IS NOT OLD.dokument_id OR NEW.stufe IS NOT OLD.stufe OR NEW.nummer IS NOT OLD.nummer
  OR NEW.datum IS NOT OLD.datum OR NEW.frist_bis IS NOT OLD.frist_bis OR NEW.offen_rechnung IS NOT OLD.offen_rechnung
  OR NEW.gebuehr IS NOT OLD.gebuehr OR NEW.gebuehren_vorher IS NOT OLD.gebuehren_vorher OR NEW.zinsen IS NOT OLD.zinsen
  OR NEW.gesamt IS NOT OLD.gesamt OR NEW.snapshot_json IS NOT OLD.snapshot_json OR NEW.pdf_pfad IS NOT OLD.pdf_pfad
  OR NEW.pdf_sha256 IS NOT OLD.pdf_sha256 OR NEW.snapshot_sha256 IS NOT OLD.snapshot_sha256
  OR NEW.erstellt_am IS NOT OLD.erstellt_am
BEGIN
    SELECT RAISE(ABORT, 'Mahnungen sind archiviert und können nicht geändert werden.');
END;

CREATE TRIGGER IF NOT EXISTS mahnung_schutz_delete
BEFORE DELETE ON mahnungen
BEGIN
    SELECT RAISE(ABORT, 'Mahnungen sind archiviert und können nicht gelöscht werden.');
END;

-- Annahme- und Abholscheine mit digitaler Unterschrift (unveränderlich archiviert)
CREATE TABLE IF NOT EXISTS auftrag_belege (
    id                 INTEGER PRIMARY KEY,
    auftrag_id         INTEGER NOT NULL REFERENCES auftraege(id),
    art                TEXT NOT NULL CHECK (art IN ('annahme', 'abholung')),
    nummer             TEXT NOT NULL UNIQUE,      -- z. B. AU-2026-0001-AN1
    unterzeichner      TEXT,
    unterschrieben_am  TEXT NOT NULL,             -- Serverzeit Europe/Berlin mit Sekunden
    unterschrift_sha256 TEXT NOT NULL,
    quelle             TEXT,                      -- PC/Tablet oder Handy (QR-Code)
    ip                 TEXT,
    pdf_datei          TEXT NOT NULL,
    pdf_sha256         TEXT NOT NULL,
    snapshot           TEXT NOT NULL,             -- JSON der unterschriebenen Angaben
    benutzer           TEXT,
    erstellt_am        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_auftrag_belege ON auftrag_belege(auftrag_id);
CREATE TRIGGER IF NOT EXISTS auftrag_beleg_schutz_update BEFORE UPDATE ON auftrag_belege
BEGIN
    SELECT RAISE(ABORT, 'Unterschriebene Annahme-/Abholscheine dürfen nicht geändert werden.');
END;
DROP TRIGGER IF EXISTS auftrag_beleg_schutz_delete;
CREATE TRIGGER auftrag_beleg_schutz_delete BEFORE DELETE ON auftrag_belege
WHEN NOT EXISTS (SELECT 1 FROM loeschfreigaben WHERE tabelle='auftrag_belege' AND zeile_id=OLD.id)
BEGIN
    SELECT RAISE(ABORT, 'Unterschriebene Annahme-/Abholscheine dürfen nicht gelöscht werden.');
END;

-- Zeitlich begrenzte Zugänge für das Handy (QR-Code): Fotos aufnehmen oder unterschreiben
CREATE TABLE IF NOT EXISTS mobil_zugaenge (
    token        TEXT PRIMARY KEY,
    auftrag_id   INTEGER NOT NULL REFERENCES auftraege(id) ON DELETE CASCADE,
    zweck        TEXT NOT NULL CHECK (zweck IN ('fotos', 'annahme', 'abholung')),
    erstellt_am  TEXT NOT NULL,
    gueltig_bis  TEXT NOT NULL,
    benutzer     TEXT,
    benutzt_am   TEXT
);

-- Kundenbenachrichtigungen (Vorschlag → gesendet / nicht gesendet); gesendete Mails stehen zusätzlich im Versandprotokoll
CREATE TABLE IF NOT EXISTS benachrichtigungen (
    id          INTEGER PRIMARY KEY,
    auftrag_id  INTEGER NOT NULL REFERENCES auftraege(id) ON DELETE CASCADE,
    kunde_id    INTEGER NOT NULL REFERENCES kunden(id),
    anlass      TEXT NOT NULL,
    stufe       INTEGER,                 -- Erinnerung: nach wie vielen Tagen
    kanal       TEXT NOT NULL DEFAULT 'email',
    an          TEXT,
    betreff     TEXT,
    text        TEXT,
    status      TEXT NOT NULL DEFAULT 'offen' CHECK (status IN ('offen', 'gesendet', 'verworfen', 'fehler')),
    hinweis     TEXT,
    erstellt_am TEXT NOT NULL,
    erledigt_am TEXT,
    benutzer    TEXT,
    gelesen_am  TEXT                     -- in der Glocke als gelesen markiert
);
CREATE INDEX IF NOT EXISTS ix_benachrichtigungen ON benachrichtigungen(auftrag_id, status);

-- Lagerbewegungen (unveränderlich): Zugang / Abgang / Korrektur / Inventur
CREATE TABLE IF NOT EXISTS lagerbewegungen (
    id             INTEGER PRIMARY KEY,
    artikel_id     INTEGER NOT NULL REFERENCES artikel(id),
    art            TEXT NOT NULL CHECK (art IN ('zugang', 'abgang', 'korrektur', 'inventur')),
    menge          REAL NOT NULL,                 -- mit Vorzeichen
    bestand_danach REAL NOT NULL,
    grund          TEXT NOT NULL,
    auftrag_id     INTEGER REFERENCES auftraege(id),
    dokument_id    INTEGER REFERENCES dokumente(id),
    inventur_id    INTEGER,
    ek             INTEGER,                       -- Einkaufspreis je Einheit (Cent) zum Buchungszeitpunkt
    zeitpunkt      TEXT NOT NULL,
    benutzer       TEXT
);
CREATE INDEX IF NOT EXISTS ix_lagerbewegungen ON lagerbewegungen(artikel_id, zeitpunkt);
CREATE TRIGGER IF NOT EXISTS lagerbewegung_schutz_update BEFORE UPDATE ON lagerbewegungen
BEGIN
    SELECT RAISE(ABORT, 'Lagerbewegungen dürfen nicht geändert werden – bitte eine Korrekturbuchung erfassen.');
END;
CREATE TRIGGER IF NOT EXISTS lagerbewegung_schutz_delete BEFORE DELETE ON lagerbewegungen
BEGIN
    SELECT RAISE(ABORT, 'Lagerbewegungen dürfen nicht gelöscht werden – bitte eine Korrekturbuchung erfassen.');
END;

-- Material zum Auftrag (Reservierung → beim Erledigen ausgebucht)
CREATE TABLE IF NOT EXISTS lager_reservierungen (
    id          INTEGER PRIMARY KEY,
    artikel_id  INTEGER NOT NULL REFERENCES artikel(id),
    auftrag_id  INTEGER NOT NULL REFERENCES auftraege(id),
    menge       REAL NOT NULL,
    status      TEXT NOT NULL DEFAULT 'reserviert'
                CHECK (status IN ('reserviert', 'ausgebucht', 'storniert', 'zurueckgebucht')),
    quelle      TEXT,
    bewegung_id INTEGER REFERENCES lagerbewegungen(id),
    storno_grund TEXT,
    erstellt_am TEXT NOT NULL,
    erledigt_am TEXT,
    benutzer    TEXT
);
CREATE INDEX IF NOT EXISTS ix_lager_reservierungen ON lager_reservierungen(auftrag_id);
CREATE INDEX IF NOT EXISTS ix_lager_reservierungen_art ON lager_reservierungen(artikel_id, status);

-- Inventur
CREATE TABLE IF NOT EXISTS inventuren (
    id               INTEGER PRIMARY KEY,
    stichtag         TEXT NOT NULL,
    bezeichnung      TEXT,
    status           TEXT NOT NULL DEFAULT 'offen' CHECK (status IN ('offen', 'abgeschlossen')),
    erstellt_am      TEXT NOT NULL,
    benutzer         TEXT,
    abgeschlossen_am TEXT,
    abgeschlossen_von TEXT,
    lagerwert        INTEGER,
    differenzen      INTEGER,
    pdf_datei        TEXT,
    pdf_sha256       TEXT
);
CREATE TABLE IF NOT EXISTS inventur_positionen (
    id           INTEGER PRIMARY KEY,
    inventur_id  INTEGER NOT NULL REFERENCES inventuren(id),
    artikel_id   INTEGER NOT NULL REFERENCES artikel(id),
    soll         REAL NOT NULL,
    ist          REAL,
    ek           INTEGER,
    gezaehlt_am  TEXT,
    gezaehlt_von TEXT,
    UNIQUE (inventur_id, artikel_id)
);
CREATE TRIGGER IF NOT EXISTS inventur_schutz BEFORE UPDATE ON inventur_positionen
WHEN (SELECT status FROM inventuren WHERE id=OLD.inventur_id)='abgeschlossen'
BEGIN
    SELECT RAISE(ABORT, 'Abgeschlossene Inventuren dürfen nicht geändert werden.');
END;
CREATE TRIGGER IF NOT EXISTS inventur_kopf_schutz BEFORE UPDATE ON inventuren
WHEN OLD.status='abgeschlossen'
BEGIN
    SELECT RAISE(ABORT, 'Abgeschlossene Inventuren dürfen nicht geändert werden.');
END;
CREATE TABLE IF NOT EXISTS inventur_zugaenge (
    token       TEXT PRIMARY KEY,
    inventur_id INTEGER NOT NULL REFERENCES inventuren(id),
    gueltig_bis TEXT NOT NULL,
    erstellt_am TEXT NOT NULL
);

-- Lieferanten (0.17.0)
CREATE TABLE IF NOT EXISTS lieferanten (
    id                  INTEGER PRIMARY KEY,
    name                TEXT NOT NULL,
    ansprechpartner     TEXT,
    email               TEXT,
    telefon             TEXT,
    strasse             TEXT,
    plz                 TEXT,
    ort                 TEXT,
    land                TEXT,
    ust_idnr            TEXT,
    iban                TEXT,
    kundennr_bei        TEXT,               -- meine Kundennummer beim Lieferanten
    webshop             TEXT,
    zahlungsbedingungen TEXT,
    zahlungsziel_tage   INTEGER,
    lieferzeit_tage     INTEGER,
    kreditornr          TEXT,               -- für den DATEV-Export
    notizen             TEXT,
    aktiv               INTEGER NOT NULL DEFAULT 1,
    erstellt_am         TEXT NOT NULL,
    geaendert_am        TEXT NOT NULL
);

-- Bezugsquellen je Artikel (mehrere Lieferanten mit eigenem EK)
CREATE TABLE IF NOT EXISTS artikel_lieferanten (
    id              INTEGER PRIMARY KEY,
    artikel_id      INTEGER NOT NULL REFERENCES artikel(id),
    lieferant_id    INTEGER NOT NULL REFERENCES lieferanten(id),
    ek              INTEGER,                  -- Cent netto je Einheit
    lieferanten_artnr TEXT,
    garantie_monate INTEGER,                  -- Gewährleistung/Garantie des Lieferanten auf das Teil
    geaendert_am    TEXT NOT NULL,
    UNIQUE (artikel_id, lieferant_id)
);

-- Bestellungen bei Lieferanten
CREATE TABLE IF NOT EXISTS bestellungen (
    id           INTEGER PRIMARY KEY,
    nummer       TEXT UNIQUE NOT NULL,       -- BE-2026-0001
    lieferant_id INTEGER NOT NULL REFERENCES lieferanten(id),
    status       TEXT NOT NULL DEFAULT 'entwurf'
                 CHECK (status IN ('entwurf', 'bestellt', 'teilweise', 'geliefert', 'storniert')),
    bestellt_am  TEXT,
    erwartet_am  TEXT,
    notiz        TEXT,
    versendet_an TEXT,
    erstellt_am  TEXT NOT NULL,
    benutzer     TEXT,
    storno_grund TEXT
);
CREATE TABLE IF NOT EXISTS bestell_positionen (
    id            INTEGER PRIMARY KEY,
    bestellung_id INTEGER NOT NULL REFERENCES bestellungen(id),
    artikel_id    INTEGER REFERENCES artikel(id),
    bezeichnung   TEXT NOT NULL,
    lieferanten_artnr TEXT,
    menge         REAL NOT NULL,
    geliefert     REAL NOT NULL DEFAULT 0,
    ek            INTEGER,
    auftrag_id    INTEGER REFERENCES auftraege(id)    -- „Teil für diesen Auftrag bestellen“
);
CREATE INDEX IF NOT EXISTS ix_bestell_pos ON bestell_positionen(bestellung_id);
CREATE INDEX IF NOT EXISTS ix_bestell_pos_auftrag ON bestell_positionen(auftrag_id);

-- Wareneingänge (Historie je Position; der Lagerzugang steht zusätzlich in lagerbewegungen)
CREATE TABLE IF NOT EXISTS wareneingaenge (
    id            INTEGER PRIMARY KEY,
    bestellung_id INTEGER NOT NULL REFERENCES bestellungen(id),
    position_id   INTEGER NOT NULL REFERENCES bestell_positionen(id),
    artikel_id    INTEGER REFERENCES artikel(id),
    lieferant_id  INTEGER REFERENCES lieferanten(id),
    menge         REAL NOT NULL,
    ek            INTEGER,
    lieferschein  TEXT,
    garantie_bis  TEXT,                     -- Lieferantengarantie für diese Lieferung
    bewegung_id   INTEGER REFERENCES lagerbewegungen(id),
    zeitpunkt     TEXT NOT NULL,
    benutzer      TEXT
);
CREATE TRIGGER IF NOT EXISTS wareneingang_schutz_update BEFORE UPDATE ON wareneingaenge
BEGIN
    SELECT RAISE(ABORT, 'Wareneingänge dürfen nicht geändert werden.');
END;
CREATE TRIGGER IF NOT EXISTS wareneingang_schutz_delete BEFORE DELETE ON wareneingaenge
BEGIN
    SELECT RAISE(ABORT, 'Wareneingänge dürfen nicht gelöscht werden.');
END;

-- Eingangsrechnungen (Belege der Lieferanten); Originaldatei unveränderlich (SHA-256)
CREATE TABLE IF NOT EXISTS eingangsrechnungen (
    id            INTEGER PRIMARY KEY,
    lfd_nr        TEXT UNIQUE NOT NULL,      -- eigene laufende Belegnummer ER-2026-0001
    lieferant_id  INTEGER REFERENCES lieferanten(id),
    lieferant_name TEXT,                     -- falls (noch) kein Lieferant angelegt ist
    nummer        TEXT,                      -- Rechnungsnummer des Lieferanten
    datum         TEXT NOT NULL,
    faellig_am    TEXT,
    netto         INTEGER NOT NULL DEFAULT 0,
    steuer        INTEGER NOT NULL DEFAULT 0,
    brutto        INTEGER NOT NULL DEFAULT 0,
    steuersatz    REAL,
    kostenart     TEXT,
    bestellung_id INTEGER REFERENCES bestellungen(id),
    beschreibung  TEXT,
    status        TEXT NOT NULL DEFAULT 'offen' CHECK (status IN ('offen', 'bezahlt', 'storniert')),
    datei         TEXT,
    datei_name    TEXT,
    datei_sha256  TEXT,
    quelle        TEXT,                      -- Upload / Postfach / E-Rechnung
    message_id    TEXT,                      -- aus dem Postfach übernommen (gegen Doppelte)
    e_daten       TEXT,                      -- ausgelesene E-Rechnung (Business-Terms als JSON)
    erfasst_am    TEXT NOT NULL,
    benutzer      TEXT,
    storniert_am  TEXT,
    storno_grund  TEXT,
    exportiert_am TEXT,                      -- DATEV-Export (Ausbaustufe 9)
    fixkosten_id  INTEGER                    -- gehört zu einer Fixkosten-Position (zählt in Finanzen dort)
);
CREATE INDEX IF NOT EXISTS ix_er_status ON eingangsrechnungen(status, faellig_am);
CREATE TRIGGER IF NOT EXISTS er_datei_schutz BEFORE UPDATE ON eingangsrechnungen
WHEN OLD.datei_sha256 IS NOT NULL AND (NEW.datei_sha256 IS NOT OLD.datei_sha256 OR NEW.datei IS NOT OLD.datei)
BEGIN
    SELECT RAISE(ABORT, 'Die Originaldatei einer Eingangsrechnung darf nicht ausgetauscht werden.');
END;
CREATE TRIGGER IF NOT EXISTS er_schutz_delete BEFORE DELETE ON eingangsrechnungen
BEGIN
    SELECT RAISE(ABORT, 'Eingangsrechnungen dürfen nicht gelöscht werden – bitte stornieren.');
END;

-- Zahlungen auf Eingangsrechnungen (Ausgänge)
CREATE TABLE IF NOT EXISTS er_zahlungen (
    id                INTEGER PRIMARY KEY,
    eingangsrechnung_id INTEGER NOT NULL REFERENCES eingangsrechnungen(id),
    datum             TEXT NOT NULL,
    betrag            INTEGER NOT NULL,
    zahlart           TEXT NOT NULL,
    notiz             TEXT,
    bank_umsatz_id    INTEGER REFERENCES bank_umsaetze(id),
    erfasst_am        TEXT NOT NULL,
    benutzer          TEXT,
    storniert_am      TEXT,
    storno_grund      TEXT
);
CREATE TRIGGER IF NOT EXISTS er_zahlung_schutz BEFORE UPDATE ON er_zahlungen
WHEN NEW.betrag IS NOT OLD.betrag OR NEW.datum IS NOT OLD.datum OR NEW.eingangsrechnung_id IS NOT OLD.eingangsrechnung_id
BEGIN
    SELECT RAISE(ABORT, 'Zahlungen können nicht geändert, nur storniert werden.');
END;
CREATE TRIGGER IF NOT EXISTS er_zahlung_schutz_delete BEFORE DELETE ON er_zahlungen
BEGIN
    SELECT RAISE(ABORT, 'Zahlungen können nicht gelöscht, nur storniert werden.');
END;

-- Kassenbuch (0.19.0): fortlaufend nummeriert, unveränderlich; Korrektur nur per Gegenbuchung
CREATE TABLE IF NOT EXISTS kassenbuch (
    id              INTEGER PRIMARY KEY,
    lfd_nr          INTEGER UNIQUE NOT NULL,
    datum           TEXT NOT NULL,
    art             TEXT NOT NULL,
    betrag          INTEGER NOT NULL,          -- Cent; + Eingang, − Ausgang
    steuersatz      REAL,
    kostenart       TEXT,                      -- bei Ausgaben (für den DATEV-Export)
    text            TEXT NOT NULL,
    dokument_id     INTEGER REFERENCES dokumente(id),
    zahlung_id      INTEGER REFERENCES zahlungen(id),
    er_zahlung_id   INTEGER REFERENCES er_zahlungen(id),
    beleg_datei     TEXT,
    beleg_sha256    TEXT,
    beleg_name      TEXT,
    gegenbuchung_zu INTEGER REFERENCES kassenbuch(id),
    erfasst_am      TEXT NOT NULL,
    benutzer        TEXT
);
CREATE INDEX IF NOT EXISTS ix_kassenbuch_datum ON kassenbuch(datum);
CREATE TRIGGER IF NOT EXISTS kassenbuch_schutz_update BEFORE UPDATE ON kassenbuch
BEGIN
    SELECT RAISE(ABORT, 'Kassenbuchungen dürfen nicht geändert werden – bitte eine Gegenbuchung erfassen.');
END;
CREATE TRIGGER IF NOT EXISTS kassenbuch_schutz_delete BEFORE DELETE ON kassenbuch
BEGIN
    SELECT RAISE(ABORT, 'Kassenbuchungen dürfen nicht gelöscht werden – bitte eine Gegenbuchung erfassen.');
END;

CREATE TABLE IF NOT EXISTS kassen_abschluesse (
    id          INTEGER PRIMARY KEY,
    datum       TEXT UNIQUE NOT NULL,
    soll        INTEGER NOT NULL,
    ist         INTEGER NOT NULL,
    differenz   INTEGER NOT NULL,
    begruendung TEXT,
    zaehlung    TEXT,                       -- Zählprotokoll (Scheine/Münzen) als JSON
    erstellt_am TEXT NOT NULL,
    benutzer    TEXT
);
CREATE TRIGGER IF NOT EXISTS kassen_abschluss_schutz_update BEFORE UPDATE ON kassen_abschluesse
BEGIN
    SELECT RAISE(ABORT, 'Tagesabschlüsse dürfen nicht geändert werden.');
END;
CREATE TRIGGER IF NOT EXISTS kassen_abschluss_schutz_delete BEFORE DELETE ON kassen_abschluesse
BEGIN
    SELECT RAISE(ABORT, 'Tagesabschlüsse dürfen nicht gelöscht werden.');
END;

-- DATEV-Export: Protokoll und exportierte Buchungen (gegen doppelten Export)
CREATE TABLE IF NOT EXISTS datev_exporte (
    id          INTEGER PRIMARY KEY,
    von         TEXT NOT NULL,
    bis         TEXT NOT NULL,
    anzahl      INTEGER NOT NULL,
    summe       INTEGER NOT NULL,
    datei       TEXT NOT NULL,
    sha256      TEXT NOT NULL,
    erneut      INTEGER NOT NULL DEFAULT 0,  -- 1 = bereits exportierte Buchungen erneut ausgegeben
    erstellt_am TEXT NOT NULL,
    benutzer    TEXT
);
CREATE TABLE IF NOT EXISTS datev_posten (
    quelle      TEXT NOT NULL,              -- dokument / zahlung / eingangsrechnung / er_zahlung / kasse
    quelle_id   INTEGER NOT NULL,
    export_id   INTEGER NOT NULL REFERENCES datev_exporte(id),
    PRIMARY KEY (quelle, quelle_id)
);
CREATE TRIGGER IF NOT EXISTS datev_export_schutz BEFORE DELETE ON datev_exporte
BEGIN
    SELECT RAISE(ABORT, 'Das Exportprotokoll darf nicht gelöscht werden.');
END;

-- Löschprotokolle (DSGVO): was gelöscht, was behalten und bis wann (unveränderlich)
CREATE TABLE IF NOT EXISTS loeschprotokolle (
    id          INTEGER PRIMARY KEY,
    zeitpunkt   TEXT NOT NULL,
    benutzer    TEXT,
    anlass      TEXT NOT NULL,
    betroffen   TEXT,
    geloescht   TEXT NOT NULL,             -- JSON-Liste
    behalten    TEXT NOT NULL,             -- JSON-Liste [{was, bis}]
    bis         TEXT,
    frist       TEXT                       -- angewandte Löschfrist (z. B. „Fotos: 3 Jahre ab Ende des Abholjahres“)
);
CREATE TRIGGER IF NOT EXISTS loeschprotokoll_schutz_update BEFORE UPDATE ON loeschprotokolle
BEGIN
    SELECT RAISE(ABORT, 'Löschprotokolle dürfen nicht geändert werden.');
END;
CREATE TRIGGER IF NOT EXISTS loeschprotokoll_schutz_delete BEFORE DELETE ON loeschprotokolle
BEGIN
    SELECT RAISE(ABORT, 'Löschprotokolle dürfen nicht gelöscht werden.');
END;

-- Zurückgestellte Löschungen (z. B. laufender Streitfall) – bis zur Aufhebung bzw. bis zum Datum
CREATE TABLE IF NOT EXISTS loesch_zurueckstellungen (
    id           INTEGER PRIMARY KEY,
    art          TEXT NOT NULL,            -- kunde / interessent / auftrag / leihe
    objekt_id    INTEGER NOT NULL,
    grund        TEXT NOT NULL,
    bis          TEXT,
    erstellt_am  TEXT NOT NULL,
    benutzer     TEXT,
    aufgehoben_am TEXT
);
CREATE INDEX IF NOT EXISTS ix_loesch_zurueck ON loesch_zurueckstellungen(art, objekt_id);

-- Fixkosten (0.24.0): wiederkehrende Ausgaben; Beträge mit „gültig ab“ (nie überschrieben, Verlauf bleibt)
CREATE TABLE IF NOT EXISTS fixkosten (
    id                 INTEGER PRIMARY KEY,
    bezeichnung        TEXT NOT NULL,
    kategorie          TEXT,
    rhythmus           TEXT NOT NULL DEFAULT 'monatlich'
                       CHECK (rhythmus IN ('monatlich', 'vierteljaehrlich', 'halbjaehrlich', 'jaehrlich')),
    faellig_tag        INTEGER NOT NULL DEFAULT 1,       -- Tag im Monat (31 = Monatsende)
    beginn             TEXT NOT NULL,                    -- erste Fälligkeit frühestens an diesem Tag
    ende               TEXT,                             -- Vertragsende (optional)
    kuendigung_wert    INTEGER,                          -- Kündigungsfrist, z. B. 3
    kuendigung_einheit TEXT CHECK (kuendigung_einheit IS NULL OR kuendigung_einheit IN ('tage', 'wochen', 'monate')),
    zahlungsart        TEXT NOT NULL DEFAULT 'lastschrift',
    empfaenger         TEXT,
    lieferant_id       INTEGER REFERENCES lieferanten(id),
    bank_suchbegriff   TEXT,                             -- optional: Text im Kontoauszug (Name, IBAN, Mandat)
    notiz              TEXT,
    datei              TEXT,                             -- Vertrags-PDF (relativ zum Datenordner)
    datei_name         TEXT,
    datei_sha256       TEXT,
    erstellt_am        TEXT NOT NULL,
    geaendert_am       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fixkosten_betraege (
    id            INTEGER PRIMARY KEY,
    fixkosten_id  INTEGER NOT NULL REFERENCES fixkosten(id),
    gueltig_ab    TEXT NOT NULL,
    netto         INTEGER NOT NULL,                      -- Cent je Fälligkeit
    steuersatz    REAL NOT NULL DEFAULT 0,
    brutto        INTEGER NOT NULL,
    notiz         TEXT,
    erfasst_am    TEXT NOT NULL,
    benutzer      TEXT,
    UNIQUE (fixkosten_id, gueltig_ab)
);
CREATE TRIGGER IF NOT EXISTS fixkosten_betrag_schutz BEFORE UPDATE ON fixkosten_betraege
BEGIN
    SELECT RAISE(ABORT, 'Fixkosten-Beträge werden nicht überschrieben – bitte einen neuen Betrag mit „gültig ab“ erfassen.');
END;

-- Gelesene Hinweise in der Glocke (z. B. „Kündigungsfrist endet bald“)
CREATE TABLE IF NOT EXISTS hinweise_gelesen (
    schluessel  TEXT PRIMARY KEY,
    gelesen_am  TEXT NOT NULL
);

-- Checkliste je Auftrag: Arbeitsschritte zum Abhaken (Vorlagen je Leistung in den Einstellungen)
CREATE TABLE IF NOT EXISTS auftrag_checkliste (
    id          INTEGER PRIMARY KEY,
    auftrag_id  INTEGER NOT NULL REFERENCES auftraege(id) ON DELETE CASCADE,
    leistung    TEXT,                   -- aus welcher Vorlage (leer = von Hand ergänzt)
    text        TEXT NOT NULL,
    position    INTEGER NOT NULL DEFAULT 0,
    erledigt_am TEXT,
    erledigt_von TEXT
);
CREATE INDEX IF NOT EXISTS ix_checkliste_auftrag ON auftrag_checkliste(auftrag_id, position);
