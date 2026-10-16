"""Phase 4: Kundenbenachrichtigung bei Statuswechseln, Vorschau, Abhol-Erinnerungen, SMS-Schnittstelle."""
import smtplib
from datetime import date, timedelta

import pytest

from rsb import benachrichtigung as ben
from rsb import db as dbm
from rsb import sms
from rsb.sicherheit import verschluesseln

from conftest import kunde_anlegen, post
from test_annahme import auftrag_mit_annahme, unterschreiben
from test_auftraege import kva_mit_position


@pytest.fixture
def smtp(app, con, monkeypatch):
    class Smtp:
        gesendet = []

        def __init__(self, *a, **k):
            pass
        starttls = login = quit = lambda self, *a, **k: None

        def send_message(self, msg):
            Smtp.gesendet.append(msg)
    monkeypatch.setattr(smtplib, "SMTP", Smtp)
    with app.app_context(), dbm.Transaktion(con):
        dbm.einstellungen_speichern({"smtp_host": "smtp.ionos.de", "smtp_port": 587, "smtp_benutzer": "ich@x.de",
                                     "smtp_passwort_enc": verschluesseln("x")}, con)
    return Smtp


def offene(con, aid=None):
    return con.execute("SELECT * FROM benachrichtigungen WHERE status='offen'" + (f" AND auftrag_id={aid}" if aid
                                                                                   else "")).fetchall()


def test_angenommen_vorschau_senden(client, con, smtp):
    kid = kunde_anlegen(client)
    aid = auftrag_mit_annahme(client, kid, fertig_bis="2026-10-20")
    b = offene(con, aid)
    assert len(b) == 1 and b[0]["anlass"] == "angenommen" and b[0]["an"] == "anna@example.com"
    assert "Sehr geehrte Frau Müller" in b[0]["text"] and "iPhone 13" in b[0]["text"] and "20.10.2026" in b[0]["text"]
    assert not smtp.gesendet  # ohne Freigabe nichts gesendet
    seite = client.get(f"/auftraege/{aid}").get_data(as_text=True)
    assert "Diesmal nicht senden" in seite and "Auftrag angenommen" in seite
    r = post(client, f"/benachrichtigungen/{b[0]['id']}/senden", an="anna@example.com", betreff="Geänderter Betreff",
             text="Hallo", weiter=f"/auftraege/{aid}")
    assert r.headers["Location"].endswith(f"/auftraege/{aid}")
    assert len(smtp.gesendet) == 1 and smtp.gesendet[0]["Subject"] == "Geänderter Betreff"
    b = con.execute("SELECT * FROM benachrichtigungen WHERE id=?", (b[0]["id"],)).fetchone()
    assert b["status"] == "gesendet" and b["text"] == "Hallo"
    assert con.execute("SELECT 1 FROM auftrag_verlauf WHERE auftrag_id=? AND ereignis LIKE 'Kunde benachrichtigt%'",
                       (aid,)).fetchone()
    assert con.execute("SELECT 1 FROM versandprotokoll WHERE betreff='Geänderter Betreff'").fetchone()
    # erneutes Senden derselben Benachrichtigung geht nicht
    post(client, f"/benachrichtigungen/{b['id']}/senden", an="anna@example.com")
    assert len(smtp.gesendet) == 1


def test_diesmal_nicht_senden_und_kein_doppelter_vorschlag(client, con, smtp):
    kid = kunde_anlegen(client)
    aid = auftrag_mit_annahme(client, kid)
    bid = offene(con, aid)[0]["id"]
    post(client, f"/benachrichtigungen/{bid}/verwerfen")
    assert con.execute("SELECT status FROM benachrichtigungen WHERE id=?", (bid,)).fetchone()[0] == "verworfen"
    # Fertig → Vorschlag mit Rechnungsbetrag; zurück und wieder fertig → kein zweiter Vorschlag
    post(client, f"/auftraege/{aid}/status", status="erledigt", ohne_kva="1")
    assert [b["anlass"] for b in offene(con, aid)] == ["fertig"]
    post(client, f"/auftraege/{aid}/status", status="in_arbeit")
    post(client, f"/auftraege/{aid}/status", status="erledigt", ohne_kva="1")
    assert len(offene(con, aid)) == 1
    assert not smtp.gesendet


def test_wartet_auf_teil_spalte(client, con, smtp):
    kid = kunde_anlegen(client)
    aid = auftrag_mit_annahme(client, kid)
    post(client, f"/auftraege/{aid}", kunde_id=kid, status="in_arbeit", geraet="iPhone 13", annahme_felder="1",
         zugang_art="pin", teil_info="Akku bei Lieferant X", teil_erwartet="2026-10-25")
    post(client, f"/auftraege/{aid}/status", status="wartet_teil")
    a = con.execute("SELECT * FROM auftraege WHERE id=?", (aid,)).fetchone()
    assert a["status"] == "in_arbeit" and a["wartet_teil_seit"]
    assert "wartet_teil" in [b["anlass"] for b in offene(con, aid)]
    tafel = client.get("/auftraege").get_data(as_text=True)
    assert "Wartet auf Teil" in tafel and "Akku bei Lieferant X" in tafel and "25.10.2026" in tafel
    assert f'data-id="{aid}" data-status="wartet_teil"' in tafel
    post(client, f"/auftraege/{aid}/status", status="in_arbeit")
    assert con.execute("SELECT wartet_teil_seit FROM auftraege WHERE id=?", (aid,)).fetchone()[0] is None


def test_kva_benachrichtigung(client, con, smtp):
    kid = kunde_anlegen(client)
    with dbm.Transaktion(con):
        dbm.einstellungen_speichern({"ben_kva_aktiv": True, "ben_angenommen_aktiv": False}, con)
    aid = auftrag_mit_annahme(client, kid, geraet="Xiaomi 14T Pro")
    kva_mit_position(client, con, aid)
    b = offene(con, aid)
    assert [x["anlass"] for x in b] == ["kva"] and "149,00 €" in b[0]["text"]


def test_vorschau_aus_sendet_sofort(client, con, smtp):
    with dbm.Transaktion(con):
        dbm.einstellungen_speichern({"benachrichtigung_vorschau": False}, con)
    kid = kunde_anlegen(client)
    aid = auftrag_mit_annahme(client, kid)
    assert len(smtp.gesendet) == 1 and not offene(con, aid)
    # ohne E-Mail-Adresse: Fehler, bleibt sichtbar
    kid2 = kunde_anlegen(client, email="", vorname="Otto")
    aid2 = auftrag_mit_annahme(client, kid2)
    b = con.execute("SELECT * FROM benachrichtigungen WHERE auftrag_id=?", (aid2,)).fetchone()
    assert b["status"] == "fehler" and "E-Mail-Adresse" in b["hinweis"]


def test_abhol_erinnerung(client, con, smtp, app):
    kid = kunde_anlegen(client)
    aid = auftrag_mit_annahme(client, kid)
    post(client, f"/auftraege/{aid}/status", status="erledigt", ohne_kva="1")
    vor = (date.today() - timedelta(days=15)).isoformat() + "T10:00:00"
    con.execute("UPDATE auftraege SET erledigt_am=? WHERE id=?", (vor, aid))
    with app.app_context(), dbm.Transaktion(con):
        assert ben.erinnerungen_pruefen(con) == 1
        assert ben.erinnerungen_pruefen(con) == 0  # nicht doppelt
    b = con.execute("SELECT * FROM benachrichtigungen WHERE anlass='erinnerung'").fetchone()
    assert b["stufe"] == 14
    assert "noch nicht abgeholt" in client.get("/benachrichtigungen").get_data(as_text=True)
    # Abholschein → offene Erinnerung erledigt sich, Gerät gilt als abgeholt
    unterschreiben(client, aid, art="abholung")
    assert con.execute("SELECT status FROM benachrichtigungen WHERE id=?", (b["id"],)).fetchone()[0] == "verworfen"
    with app.app_context(), dbm.Transaktion(con):
        con.execute("UPDATE auftraege SET erledigt_am=? WHERE id=?",
                    ((date.today() - timedelta(days=40)).isoformat() + "T10:00:00", aid))
        assert ben.erinnerungen_pruefen(con) == 0


def test_abgeholt_ohne_schein(client, con, smtp):
    kid = kunde_anlegen(client)
    aid = auftrag_mit_annahme(client, kid)
    post(client, f"/auftraege/{aid}/status", status="erledigt", ohne_kva="1")
    post(client, f"/auftraege/{aid}/abgeholt")
    a = con.execute("SELECT * FROM auftraege WHERE id=?", (aid,)).fetchone()
    assert a["abgeholt_am"] and a["zugang_geheim"] is None


def test_manuell_und_einstellungen(client, con, smtp):
    kid = kunde_anlegen(client)
    aid = auftrag_mit_annahme(client, kid)
    post(client, f"/auftraege/{aid}/benachrichtigen", anlass="fertig")
    assert "fertig" in [b["anlass"] for b in offene(con, aid)]
    daten = {f"ben_{a}_{t}": "x" for a in ben.ANLAESSE for t in ("betreff", "text")}
    daten.update(ben_fertig_text="Hallo {Kundenname}, {Gerät} ist fertig. {Öffnungszeiten}", oeffnungszeiten="Mo 9-12",
                 erinnerung_tage="5, 10", benachrichtigung_kanal="email", ben_fertig_aktiv="1")
    post(client, "/einstellungen/benachrichtigung", **daten)
    e = dbm.einstellungen(con)
    assert e["erinnerung_tage"] == "5, 10" and e["ben_fertig_aktiv"] and not e["ben_angenommen_aktiv"]
    assert e["benachrichtigung_vorschau"] is False  # Haken nicht gesetzt
    with dbm.Transaktion(con):
        dbm.einstellungen_speichern({"benachrichtigung_vorschau": True}, con)
    client.get("/benachrichtigungen")
    b = [b for b in offene(con, aid) if b["anlass"] == "fertig"][0]
    assert b["text"] == "Hallo Anna Müller, iPhone 13 ist fertig. Mo 9-12"  # aktuelle Vorlage beim Anzeigen


def test_sms_schnittstelle(client, con):
    assert sms.nummer_normal("0151 234 5678") == "+491512345678"
    with pytest.raises(sms.SmsFehler):
        sms.nummer_normal("123")
    with pytest.raises(sms.SmsFehler):
        sms.senden({"sms_anbieter": ""}, "0151 2345678", "x")
    gesendet = []

    class Test(sms.SmsAnbieter):
        def senden(self, nummer, text):
            gesendet.append((nummer, text))
    sms.ANBIETER["test"] = Test
    try:
        with dbm.Transaktion(con):
            dbm.einstellungen_speichern({"benachrichtigung_kanal": "sms", "sms_anbieter": "test"}, con)
        kid = kunde_anlegen(client, telefon="0151 2345678")
        aid = auftrag_mit_annahme(client, kid)
        b = offene(con, aid)[0]
        assert b["kanal"] == "sms" and b["an"] == "0151 2345678"
        post(client, f"/benachrichtigungen/{b['id']}/senden", an=b["an"], betreff="", text="Kurz")
        assert gesendet == [("+491512345678", "Kurz")]
    finally:
        sms.ANBIETER.pop("test")
