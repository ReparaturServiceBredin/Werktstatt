"""Aufbewahrungsfristen und Löschen von Kunden (GoBD / DSGVO).

Ein Kunde wird vollständig gelöscht, wenn nichts aufbewahrt werden muss. Gibt es aufbewahrungspflichtige
Unterlagen (festgeschriebene Rechnungen, Kostenvoranschläge, Leihprotokolle, Fotodokumentation, versandte
Belege), werden seine Stammdaten anonymisiert: Name und Anschrift stehen dann nur noch in den archivierten
Belegen selbst (unveränderter Inhalt). Alles, was nicht aufbewahrt werden muss, wird gelöscht.
"""
from datetime import date

from . import db as dbm
from .hilfen import datum_de
from .logik import aufbewahren_bis

ANONYM_NAME = "Gelöschter Kunde"
PERSONEN_FELDER = ["firma", "anrede", "vorname", "strasse", "plz", "ort", "email", "telefon", "ust_idnr", "notizen",
                   "email_weitere"]


def _bis(jahr, jahre):
    return f"{int(jahr) + int(jahre)}-12-31"


def pruefen(con, kunde_id, einst=None):
    """Was muss aufbewahrt werden, was darf gelöscht werden? Gibt ein dict für Anzeige und Protokoll zurück."""
    einst = einst or dbm.einstellungen(con)
    briefe = int(einst.get("aufbewahrung_briefe_jahre") or 6)
    behalten, loeschen = [], []
    belege = con.execute("SELECT * FROM dokumente WHERE kunde_id=? AND status<>'entwurf'", (kunde_id,)).fetchall()
    if belege:
        bis = max(aufbewahren_bis(d, einst) for d in belege)
        behalten.append({"was": f"{len(belege)} festgeschriebene(s) Dokument(e) (Rechnungen, Stornos, Gutschriften, "
                                f"Kostenvoranschläge) inkl. Kundendaten im archivierten Beleg", "bis": bis})
    leihen = con.execute("SELECT ausgabe_am FROM leihen WHERE kunde_id=?", (kunde_id,)).fetchall()
    if leihen:
        bis = max(_bis(le["ausgabe_am"][:4], briefe) for le in leihen)
        behalten.append({"was": f"{len(leihen)} Leihvertrag/-verträge mit Übergabe- und Rückgabeprotokoll", "bis": bis})
    fotos = con.execute("SELECT COUNT(*), MAX(COALESCE(a.abgeholt_am, a.erledigt_am, a.eingang_am)) FROM auftrag_fotos f "
                        "JOIN auftraege a ON a.id=f.auftrag_id WHERE a.kunde_id=? AND f.geloescht_am IS NULL",
                        (kunde_id,)).fetchone()
    if fotos[0]:
        jahre = int(einst.get("ds_fotos_jahre") or 0)
        if jahre:  # Löschfrist für Fotos (Datenschutz): ab Ende des Kalenderjahres der Abholung
            bis = date(int(fotos[1][:4]) + jahre + 1, 1, 1).isoformat()
        else:
            bis = _bis(fotos[1][:4], briefe)
        behalten.append({"was": f"{fotos[0]} Foto(s) der Reparaturdokumentation (unveränderbar gespeichert)",
                         "bis": bis})
    mails = con.execute("SELECT COUNT(*), MAX(n.datum) FROM email_nachrichten n JOIN email_kunden k "
                        "ON k.nachricht_id=n.id WHERE k.kunde_id=? AND n.dokument_id IS NOT NULL", (kunde_id,)).fetchone()
    if mails[0]:
        behalten.append({"was": f"{mails[0]} versandte(r) Beleg(e) per E-Mail (Geschäftsbriefe)",
                         "bis": _bis((mails[1] or date.today().isoformat())[:4], briefe)})
    # Was gelöscht wird
    zaehlen = [
        ("Kontaktformular-Anfragen", "SELECT COUNT(*) FROM anfragen WHERE kunde_id=?"),
        ("Dokument-Entwürfe (ohne Nummer)", "SELECT COUNT(*) FROM dokumente WHERE kunde_id=? AND status='entwurf'"),
        ("E-Mails im E-Mail-Verlauf (ohne Belegbezug)",
         "SELECT COUNT(*) FROM email_kunden k JOIN email_nachrichten n ON n.id=k.nachricht_id "
         "WHERE k.kunde_id=? AND n.dokument_id IS NULL"),
        ("Verträge ohne Abrechnung", "SELECT COUNT(*) FROM vertraege v WHERE kunde_id=? AND NOT EXISTS "
                                      "(SELECT 1 FROM vertrag_abrechnungen x WHERE x.vertrag_id=v.id)"),
    ]
    for was, sql in zaehlen:
        n = con.execute(sql, (kunde_id,)).fetchone()[0]
        if n:
            loeschen.append(f"{n} {was}")
    auftraege_frei = len(_auftraege_ohne_bindung(con, kunde_id))
    if auftraege_frei:
        loeschen.append(f"{auftraege_frei} Reparaturauftrag/-aufträge ohne Belege, Fotos oder Leihgeräte")
    return {"anonymisieren": bool(behalten), "behalten": behalten, "loeschen": loeschen,
            "bis": max((b["bis"] for b in behalten), default=None)}


def _auftraege_ohne_bindung(con, kunde_id):
    return [r["id"] for r in con.execute(
        "SELECT a.id FROM auftraege a WHERE a.kunde_id=? "
        "AND NOT EXISTS (SELECT 1 FROM dokumente d WHERE d.id IN (a.kva_id, a.rechnung_id) AND d.status<>'entwurf') "
        "AND NOT EXISTS (SELECT 1 FROM auftrag_fotos f WHERE f.auftrag_id=a.id) "
        "AND NOT EXISTS (SELECT 1 FROM leihen l WHERE l.auftrag_id=a.id)", (kunde_id,)).fetchall()]


def kunde_loeschen(con, kunde_id):
    """Löscht den Kunden – oder anonymisiert ihn, wenn Aufbewahrungspflichten bestehen. Muss in einer
    Transaktion laufen. Gibt den Prüfbericht zurück (für Meldung und Protokoll)."""
    from .auftraege import verlauf
    bericht = pruefen(con, kunde_id)
    # E-Mail-Verlauf: Mails ohne Belegbezug entfernen, versandte Belege bleiben (Geschäftsbriefe)
    con.execute("DELETE FROM email_kunden WHERE kunde_id=? AND nachricht_id IN "
                "(SELECT id FROM email_nachrichten WHERE dokument_id IS NULL)", (kunde_id,))
    con.execute("DELETE FROM email_nachrichten WHERE id NOT IN (SELECT nachricht_id FROM email_kunden)")
    # Entwürfe
    for d in con.execute("SELECT id FROM dokumente WHERE kunde_id=? AND status='entwurf'", (kunde_id,)).fetchall():
        con.execute("UPDATE auftraege SET kva_id=NULL WHERE kva_id=?", (d["id"],))
        con.execute("UPDATE auftraege SET rechnung_id=NULL WHERE rechnung_id=?", (d["id"],))
        con.execute("UPDATE leihen SET rechnung_id=NULL WHERE rechnung_id=?", (d["id"],))
        con.execute("UPDATE schadensfaelle SET rechnung_id=NULL WHERE rechnung_id=?", (d["id"],))
        con.execute("DELETE FROM positionen WHERE dokument_id=?", (d["id"],))
        con.execute("DELETE FROM dokumente WHERE id=?", (d["id"],))
    con.execute("DELETE FROM anfragen WHERE kunde_id=?", (kunde_id,))
    con.execute("DELETE FROM vertraege WHERE kunde_id=? AND id NOT IN (SELECT vertrag_id FROM vertrag_abrechnungen)",
                (kunde_id,))
    for aid in _auftraege_ohne_bindung(con, kunde_id):
        nr = con.execute("SELECT auftragsnr FROM auftraege WHERE id=?", (aid,)).fetchone()[0]
        verlauf(con, aid, "Auftrag gelöscht", nr)
        con.execute("DELETE FROM auftraege WHERE id=?", (aid,))
    if not bericht["anonymisieren"]:
        con.execute("DELETE FROM email_kunden WHERE kunde_id=?", (kunde_id,))
        con.execute("DELETE FROM email_nachrichten WHERE id NOT IN (SELECT nachricht_id FROM email_kunden)")
        con.execute("DELETE FROM kunden WHERE id=?", (kunde_id,))
        dbm.ereignis_erfassen(con, "kunde", kunde_id, "gelöscht", "vollständig gelöscht (keine Aufbewahrungspflicht)")
        dbm.protokollieren("kunde_geloescht", "kunde", kunde_id, {"geloescht": bericht["loeschen"]}, con=con)
        return bericht
    # Anonymisieren: Stammdaten leeren; die Belege selbst behalten ihren Inhalt (Name/Anschrift) unverändert
    k = con.execute("SELECT * FROM kunden WHERE id=?", (kunde_id,)).fetchone()
    con.execute(f"UPDATE kunden SET {', '.join(f'{f}=NULL' for f in PERSONEN_FELDER)}, nachname=?, archiviert=1, "
                "interessent=0, anonymisiert_am=?, geaendert_am=? WHERE id=?",
                (ANONYM_NAME, dbm.jetzt_berlin(), dbm.jetzt(), kunde_id))
    con.execute("UPDATE auftraege SET notizen=NULL WHERE kunde_id=?", (kunde_id,))
    dbm.ereignis_erfassen(con, "kunde", kunde_id, "anonymisiert",
                          f"{k['kundennr']}: Stammdaten anonymisiert, Aufbewahrung bis {datum_de(bericht['bis'])}")
    dbm.protokollieren("kunde_anonymisiert", "kunde", kunde_id,
                       {"kundennr": k["kundennr"], "behalten": bericht["behalten"], "geloescht": bericht["loeschen"]},
                       con=con)
    return bericht
