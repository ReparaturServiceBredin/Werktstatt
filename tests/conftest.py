import re

import pytest

from rsb import create_app
from rsb import db as dbm


VOLLSTAENDIGE_FIRMA = {"inhaber": "Dennis Bredin", "firma_name": "Reparatur Service Bredin", "strasse": "Hauptstraße 1",
                       "plz": "74219", "ort": "Möckmühl", "steuernummer": "65001/12345",
                       "iban": "DE02120300000000202051", "email": "kontakt@reparatur-bredin.de", "telefon": "06298 123"}


@pytest.fixture
def app(tmp_path):
    app = create_app(tmp_path / "Daten", testing=True)
    con = dbm.verbinden(app.config["DB_PFAD"])
    with dbm.Transaktion(con):  # Pflichtangaben für Rechnungen (§ 14 UStG) – wie bei einer eingerichteten Firma
        dbm.einstellungen_speichern(VOLLSTAENDIGE_FIRMA, con)
    con.close()
    return app


@pytest.fixture
def client(app):
    c = app.test_client()
    c.post("/einrichten", data={"passwort": "geheim123", "passwort2": "geheim123"})
    with c.session_transaction() as s:
        s["csrf"] = "test-token"
    return c


@pytest.fixture
def con(app):
    con = dbm.verbinden(app.config["DB_PFAD"])
    yield con
    con.close()


def post(client, url, **data):
    data.setdefault("csrf", "test-token")
    return client.post(url, data=data, follow_redirects=False)


def kunde_anlegen(client, **felder):
    daten = {"typ": "privat", "anrede": "Frau", "vorname": "Anna", "nachname": "Müller", "strasse": "Hauptstraße 5",
             "plz": "74219", "ort": "Möckmühl", "land": "Deutschland", "email": "anna@example.com"}
    daten.update(felder)
    r = post(client, "/kunden/neu", **daten)
    return int(re.search(r"/kunden/(\d+)", r.headers["Location"]).group(1))


def rechnung_anlegen(client, kunde_id, positionen=(("Akkutausch", "79,00", "1"),), festschreiben=False, **extra):
    r = client.get(f"/dokumente/neu?kunde_id={kunde_id}")
    did = int(re.search(r"/dokumente/(\d+)", r.headers["Location"]).group(1))
    data = {
        "csrf": "test-token", "kunde_id": kunde_id, "datum": extra.get("datum", ""),
        "leistungsdatum": extra.get("leistungsdatum", "2026-01-02"), "leistungsdatum_bis": "",
        "zahlungsziel_tage": "", "betreff": extra.get("betreff", "Reparatur"), "einleitung": "{anrede_brief}",
        "schlusstext": "Bitte zahlen bis {faellig_am}, Nr. {nummer}, Betrag {betrag}.", "hinweise": "",
        "aktion": "festschreiben" if festschreiben else "speichern",
        "p_bezeichnung": [p[0] for p in positionen], "p_beschreibung": ["" for _ in positionen],
        "p_menge": [p[2] for p in positionen], "p_einheit": ["Stk." for _ in positionen],
        "p_preis": [p[1] for p in positionen], "p_teilekosten": ["10,00" for _ in positionen],
        "p_steuersatz": ["19" for _ in positionen], "p_leistungsart": ["Smartphone" for _ in positionen],
        "p_artikel_id": ["" for _ in positionen],
    }
    client.post(f"/dokumente/{did}", data=data)
    return did
