import sqlite3

import pytest

from rsb import db as dbm
from rsb.hilfen import EingabeFehler, cent_aus_text, euro, platzhalter_ersetzen
from rsb.logik import summen_berechnen
from rsb.pdf import girocode_daten


def test_geldbetraege():
    assert cent_aus_text("1.234,56") == 123456
    assert cent_aus_text("89") == 8900
    assert cent_aus_text("89,5 €") == 8950
    assert cent_aus_text("12.5") == 1250
    assert cent_aus_text("") == 0
    with pytest.raises(EingabeFehler):
        cent_aus_text("abc")
    assert euro(123456) == "1.234,56 €"
    assert euro(-500) == "-5,00 €"


def test_summen_kleinunternehmer_und_regel():
    pos = [{"menge": 2, "einzelpreis": 990, "steuersatz": 19}, {"menge": 1, "einzelpreis": 8900, "steuersatz": 19},
           {"menge": 1, "einzelpreis": 1000, "steuersatz": 7}]
    ku = summen_berechnen(pos, "kleinunternehmer")
    assert ku == {"netto": 11880, "steuer": 0, "brutto": 11880, "gruppen": []}
    regel = summen_berechnen(pos, "regel")
    assert regel["steuer"] == 70 + round(10880 * 0.19)
    assert regel["brutto"] == regel["netto"] + regel["steuer"]
    assert [g["satz"] for g in regel["gruppen"]] == [7, 19]


def test_platzhalter():
    assert platzhalter_ersetzen("Nr. {nummer} {unbekannt}", {"nummer": "RE-1"}) == "Nr. RE-1 {unbekannt}"


def test_girocode_format():
    daten = girocode_daten("Dennis Bredin", "DE02 1203 0000 0000 2020 51", "BYLADEM1001", 18780, "RE-2026-0001")
    zeilen = daten.split("\n")
    assert zeilen[:4] == ["BCD", "002", "1", "SCT"]
    assert zeilen[6] == "DE02120300000000202051"
    assert zeilen[7] == "EUR187.80"
    assert zeilen[10] == "RE-2026-0001"


def test_protokoll_kette_erkennt_manipulation(app, con):
    dbm.protokollieren("a", con=con)
    dbm.protokollieren("b", con=con)
    assert dbm.protokoll_pruefen(con) == []
    with pytest.raises(sqlite3.DatabaseError):
        con.execute("UPDATE protokoll SET aktion='x' WHERE id=1")
    with pytest.raises(sqlite3.DatabaseError):
        con.execute("DELETE FROM protokoll")
    # Jemand umgeht die Schutzregel (z. B. mit einem externen Werkzeug):
    con.execute("DROP TRIGGER protokoll_schutz_update")
    con.execute("UPDATE protokoll SET details='manipuliert' WHERE id=1")
    assert dbm.protokoll_pruefen(con)


def test_ohne_passwort_direkt_offen(app):
    c = app.test_client()
    assert c.get("/kunden").status_code == 200          # Standard: kein Passwort
    assert c.get("/login").status_code == 302           # Anmeldeseite leitet weiter
    assert c.get("/einrichten").status_code == 302


def test_passwortschutz_einschalten(client, app):
    r = client.post("/einstellungen/passwort", data={"csrf": "test-token", "aktion": "an",
                                                    "neu": "geheim123", "neu2": "geheim123"})
    assert r.status_code == 302
    c2 = app.test_client()
    assert "/login" in c2.get("/kunden").headers["Location"]
    assert c2.post("/login", data={"passwort": "falsch"}).status_code == 200
    assert c2.post("/login", data={"passwort": "geheim123"}).status_code == 302
    assert c2.get("/kunden").status_code == 200
    # wieder ausschalten
    with c2.session_transaction() as s:
        s["csrf"] = "t2"
    c2.post("/einstellungen/passwort", data={"csrf": "t2", "aktion": "aus"})
    assert app.test_client().get("/kunden").status_code == 200


def test_csrf_schutz(client):
    r = client.post("/kunden/neu", data={"nachname": "X", "csrf": "falsch"})
    assert r.status_code == 400
