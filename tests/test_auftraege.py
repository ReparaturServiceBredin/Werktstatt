import re

from rsb import anfragen as anf
from rsb import db as dbm

from conftest import kunde_anlegen, post


def auftrag_anlegen(client, kid, **felder):
    daten = {"kunde_id": kid, "geraet": "Xiaomi 14T Pro", "leistungsart": "Smartphone", "seriennummer": "3567",
             "zubehoer": "Hülle", "fehler": "Display gesprungen"}
    daten.update(felder)
    r = post(client, "/auftraege/neu", **daten)
    return int(re.search(r"/auftraege/(\d+)", r.headers["Location"]).group(1))


def kva_mit_position(client, con, aid, festschreiben=True):
    r = post(client, f"/auftraege/{aid}/kva")
    did = int(re.search(r"/dokumente/(\d+)", r.headers["Location"]).group(1))
    d = con.execute("SELECT * FROM dokumente WHERE id=?", (did,)).fetchone()
    assert d["typ"] == "kva" and "Xiaomi 14T Pro" in d["betreff"]
    client.post(f"/dokumente/{did}", data={
        "csrf": "test-token", "kunde_id": d["kunde_id"], "datum": "", "zahlungsziel_tage": "",
        "betreff": d["betreff"], "einleitung": d["einleitung"], "schlusstext": d["schlusstext"], "hinweise": "",
        "aktion": "festschreiben" if festschreiben else "speichern",
        "p_bezeichnung": ["Displaytausch Xiaomi 14T Pro"], "p_beschreibung": [""], "p_menge": ["1"],
        "p_einheit": ["pauschal"], "p_preis": ["149,00"], "p_teilekosten": ["70,00"], "p_steuersatz": ["19"],
        "p_leistungsart": ["Smartphone"], "p_artikel_id": [""]})
    return did


def test_ablauf_offen_inarbeit_erledigt(client, con):
    kid = kunde_anlegen(client)
    aid = auftrag_anlegen(client, kid)
    a = con.execute("SELECT * FROM auftraege WHERE id=?", (aid,)).fetchone()
    assert a["status"] == "offen" and a["auftragsnr"].startswith("AU-") and a["auftragsnr"].endswith("-0001")

    kva = kva_mit_position(client, con, aid)
    d = con.execute("SELECT * FROM dokumente WHERE id=?", (kva,)).fetchone()
    assert d["status"] == "festgeschrieben" and d["nummer"].startswith("KV-") and d["nummer"].endswith("-0001")
    assert d["summe_brutto"] == 14900 and d["leistungsdatum"] is None

    # per Tafel (fetch) in Arbeit ziehen
    r = client.post(f"/auftraege/{aid}/status", data={"csrf": "test-token", "status": "in_arbeit"},
                    headers={"X-Requested-With": "fetch"})
    assert r.get_json() == {"ok": True, "rechnung_url": None}
    assert con.execute("SELECT begonnen_am FROM auftraege WHERE id=?", (aid,)).fetchone()[0]

    # auf erledigt ziehen -> Rechnungsentwurf mit KVA-Positionen
    r = client.post(f"/auftraege/{aid}/status", data={"csrf": "test-token", "status": "erledigt"},
                    headers={"X-Requested-With": "fetch"})
    url = r.get_json()["rechnung_url"]
    rid = int(url.rsplit("/", 1)[1])
    re_ = con.execute("SELECT * FROM dokumente WHERE id=?", (rid,)).fetchone()
    assert re_["typ"] == "rechnung" and re_["status"] == "entwurf" and re_["summe_brutto"] == 14900
    assert re_["leistungsdatum"]  # Tag der Fertigstellung
    pos = con.execute("SELECT * FROM positionen WHERE dokument_id=?", (rid,)).fetchall()
    assert pos[0]["bezeichnung"] == "Displaytausch Xiaomi 14T Pro" and pos[0]["teilekosten"] == 7000

    # zurück und wieder erledigt -> keine zweite Rechnung
    post(client, f"/auftraege/{aid}/status", status="in_arbeit")
    r = client.post(f"/auftraege/{aid}/status", data={"csrf": "test-token", "status": "erledigt"},
                    headers={"X-Requested-With": "fetch"})
    assert r.get_json()["rechnung_url"] is None
    assert con.execute("SELECT COUNT(*) FROM dokumente WHERE typ='rechnung'").fetchone()[0] == 1


def test_erledigt_ohne_kva_und_reihenfolge(client, con):
    kid = kunde_anlegen(client)
    a1, a2, a3 = (auftrag_anlegen(client, kid) for _ in range(3))
    # a3 vor a1 einsortieren
    client.post(f"/auftraege/{a3}/status", data={"csrf": "test-token", "status": "offen", "vor_id": a1},
                headers={"X-Requested-With": "fetch"})
    reihe = [r[0] for r in con.execute("SELECT id FROM auftraege WHERE status='offen' ORDER BY reihenfolge")]
    assert reihe == [a3, a1, a2]
    # ohne KVA wird erst nachgefragt (Tafel: JSON, Knopf: Weiterleitung zum KVA-Bereich), nichts wird geändert
    r = client.post(f"/auftraege/{a2}/status", data={"csrf": "test-token", "status": "erledigt"},
                    headers={"X-Requested-With": "fetch"})
    assert r.get_json()["kein_kva"] is True
    r = post(client, f"/auftraege/{a2}/status", status="erledigt")
    assert r.headers["Location"].endswith("#kostenvoranschlag")
    assert con.execute("SELECT status FROM auftraege WHERE id=?", (a2,)).fetchone()[0] == "offen"
    # bestätigt „leeren Rechnungsentwurf erstellen“ -> Weiterleitung auf leeren Rechnungsentwurf
    r = post(client, f"/auftraege/{a2}/status", status="erledigt", ohne_kva="1")
    assert "/dokumente/" in r.headers["Location"]
    rid = con.execute("SELECT rechnung_id FROM auftraege WHERE id=?", (a2,)).fetchone()[0]
    assert con.execute("SELECT betreff FROM dokumente WHERE id=?", (rid,)).fetchone()[0].startswith("Reparatur")


def test_kva_in_rechnung_uebernehmen(client, con):
    kid = kunde_anlegen(client)
    aid = auftrag_anlegen(client, kid)
    kva = kva_mit_position(client, con, aid)
    r = post(client, f"/dokumente/{kva}/kopieren")
    rid = int(r.headers["Location"].rsplit("/", 1)[1])
    assert con.execute("SELECT rechnung_id FROM auftraege WHERE id=?", (aid,)).fetchone()[0] == rid
    assert con.execute("SELECT summe_brutto FROM dokumente WHERE id=?", (rid,)).fetchone()[0] == 14900


def test_auftrag_aus_anfrage(client, con, app):
    text = ("Name\nKochendörfer Kai\nTelefon\n+491719879253\nEmail\nkai@t-online.de\nGeraet\nSmartphone / Tablet\n"
            "Nachricht\nDisplay gesprungen Xiaomi 14T Pro")
    anf_id = anf.verarbeiten(con, text, dbm.einstellungen(con), quelle="manuell")
    kid = con.execute("SELECT kunde_id FROM anfragen WHERE id=?", (anf_id,)).fetchone()[0]
    r = post(client, "/auftraege/neu", kunde_id=kid, anfrage_id=anf_id, geraet="Smartphone / Tablet",
             leistungsart="Smartphone", fehler="Display gesprungen Xiaomi 14T Pro")
    aid = int(r.headers["Location"].rsplit("/", 1)[1])
    a = con.execute("SELECT * FROM auftraege WHERE id=?", (aid,)).fetchone()
    assert a["anfrage_id"] == anf_id and a["kunde_id"] == kid
    assert client.get(f"/anfragen/{anf_id}").status_code == 200


def test_loeschen_und_seiten(client, con):
    kid = kunde_anlegen(client)
    aid = auftrag_anlegen(client, kid)
    kva = kva_mit_position(client, con, aid, festschreiben=False)
    for url in ["/auftraege", "/auftraege?alle=1", f"/auftraege/{aid}", f"/dokumente/{kva}", f"/kunden/{kid}", "/",
                "/verkauf/kostenvoranschlaege", "/dokumente/neu?typ=kva"]:
        assert client.get(url, follow_redirects=True).status_code == 200, url
    post(client, f"/auftraege/{aid}/loeschen")
    assert not con.execute("SELECT 1 FROM auftraege WHERE id=?", (aid,)).fetchone()
    assert con.execute("SELECT 1 FROM dokumente WHERE id=?", (kva,)).fetchone()  # KVA bleibt erhalten
    # mit festgeschriebener Rechnung nicht löschbar
    aid2 = auftrag_anlegen(client, kid)
    kva_mit_position(client, con, aid2)
    rid = int(post(client, f"/auftraege/{aid2}/rechnung").headers["Location"].rsplit("/", 1)[1])
    con.execute("UPDATE dokumente SET status='festgeschrieben' WHERE id=?", (rid,))
    post(client, f"/auftraege/{aid2}/loeschen")
    assert con.execute("SELECT 1 FROM auftraege WHERE id=?", (aid2,)).fetchone()
