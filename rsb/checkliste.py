"""Checkliste je Auftrag: Arbeitsschritte zum Abhaken.

Die Vorlagen stehen in den Einstellungen (Annahme & Abholung) als Text, je Leistung ein Block:

    [Ölwechsel]
    Motoröl abgelassen
    Ölfilter gewechselt

Beim Anlegen bzw. Ändern eines Auftrags werden für jede gewählte Leistung die Schritte der Vorlage ergänzt.
Abgehakte Schritte bleiben immer erhalten; eigene Schritte lassen sich pro Auftrag hinzufügen.
"""
from . import db as dbm
from .hilfen import EingabeFehler



def vorlagen(einst):
    """{Leistung: [Schritt, …]} aus dem Einstellungstext."""
    erg, aktuell = {}, None
    for zeile in (einst.get("checklisten") or "").splitlines():
        z = zeile.strip()
        if z.startswith("[") and z.endswith("]"):
            aktuell = z[1:-1].strip()
            erg.setdefault(aktuell, [])
        elif z and aktuell:
            erg[aktuell].append(z)
    return erg


def leistungen(text):
    """Leistungen eines Auftrags (gespeichert mit Komma getrennt)."""
    return [x.strip() for x in (text or "").split(",") if x.strip()]


def liste(con, auftrag_id):
    return con.execute("SELECT * FROM auftrag_checkliste WHERE auftrag_id=? ORDER BY position, id",
                       (auftrag_id,)).fetchall()


def stand(con, auftrag_id):
    """(erledigt, gesamt)"""
    r = con.execute("SELECT COUNT(erledigt_am), COUNT(*) FROM auftrag_checkliste WHERE auftrag_id=?",
                    (auftrag_id,)).fetchone()
    return r[0], r[1]


def _naechste_position(con, auftrag_id):
    return (con.execute("SELECT MAX(position) FROM auftrag_checkliste WHERE auftrag_id=?",
                        (auftrag_id,)).fetchone()[0] or 0) + 1


def ergaenzen(con, auftrag_id, leistungsart, einst):
    """Schritte der Vorlagen für neu gewählte Leistungen anhängen. Gibt die Anzahl neuer Schritte zurück.

    Schritte einer abgewählten Leistung, die noch nicht abgehakt sind, werden entfernt; abgehakte bleiben.
    """
    gewaehlt = leistungen(leistungsart)
    vorhanden = {r["leistung"] for r in con.execute(
        "SELECT DISTINCT leistung FROM auftrag_checkliste WHERE auftrag_id=? AND leistung IS NOT NULL", (auftrag_id,))}
    for alt in vorhanden - set(gewaehlt):
        con.execute("DELETE FROM auftrag_checkliste WHERE auftrag_id=? AND leistung=? AND erledigt_am IS NULL",
                    (auftrag_id, alt))
    v = vorlagen(einst)
    neu = 0
    pos = _naechste_position(con, auftrag_id)
    for l in gewaehlt:
        if l in vorhanden:
            continue
        for schritt in v.get(l, []):
            con.execute("INSERT INTO auftrag_checkliste (auftrag_id, leistung, text, position) VALUES (?,?,?,?)",
                        (auftrag_id, l, schritt, pos))
            pos += 1
            neu += 1
    return neu


def _schritt(con, auftrag_id, cid):
    r = con.execute("SELECT * FROM auftrag_checkliste WHERE id=? AND auftrag_id=?", (cid, auftrag_id)).fetchone()
    if not r:
        raise EingabeFehler("Dieser Schritt wurde nicht gefunden.")
    return r


def abhaken(con, auftrag_id, cid, erledigt):
    from .auftraege import verlauf
    r = _schritt(con, auftrag_id, cid)
    if bool(r["erledigt_am"]) == bool(erledigt):
        return
    if erledigt:
        con.execute("UPDATE auftrag_checkliste SET erledigt_am=?, erledigt_von=? WHERE id=?",
                    (dbm.jetzt_berlin(), dbm.aktueller_benutzer(), cid))
        verlauf(con, auftrag_id, "Checkliste: erledigt", r["text"])
    else:
        con.execute("UPDATE auftrag_checkliste SET erledigt_am=NULL, erledigt_von=NULL WHERE id=?", (cid,))
        verlauf(con, auftrag_id, "Checkliste: wieder offen", r["text"])


def hinzufuegen(con, auftrag_id, text):
    text = " ".join((text or "").split())
    if not text:
        raise EingabeFehler("Bitte einen Arbeitsschritt eingeben.")
    con.execute("INSERT INTO auftrag_checkliste (auftrag_id, leistung, text, position) VALUES (?,?,?,?)",
                (auftrag_id, None, text[:300], _naechste_position(con, auftrag_id)))


def entfernen(con, auftrag_id, cid):
    r = _schritt(con, auftrag_id, cid)
    if r["erledigt_am"]:
        raise EingabeFehler("Abgehakte Schritte bleiben als Nachweis erhalten. Bitte zuerst den Haken entfernen.")
    con.execute("DELETE FROM auftrag_checkliste WHERE id=?", (cid,))
