"""Automatische Prüfung der Entwickler-Regeln (docs/ENTWICKLUNG.md): plattformunabhängig, Daten im Datenordner,
Zeichensatz ausdrücklich, keine Windows-Bibliotheken außerhalb der dafür vorgesehenen Module."""
import ast
import re
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
QUELLEN = sorted((WURZEL / "rsb").glob("*.py")) + [WURZEL / "start_exe.py"]
WINDOWS_ERLAUBT = {"fenster.py", "update.py"}
# Übergang bis zum Arbeitspaket „Zeitzone“: diese Zahl darf nur sinken, nie steigen.
ZEITZONE_HOECHSTENS = 97


def _baum(datei):
    return ast.parse(datei.read_text(encoding="utf-8"), filename=str(datei))


def _name(fn):
    return fn.id if isinstance(fn, ast.Name) else fn.attr if isinstance(fn, ast.Attribute) else ""


def test_textdateien_mit_encoding():
    fehler = []
    for f in QUELLEN:
        for c in ast.walk(_baum(f)):
            if not isinstance(c, ast.Call):
                continue
            n, kws = _name(c.func), {k.arg for k in c.keywords}
            if n == "open" and isinstance(c.func, ast.Name):
                modus = next((a.value for a in c.args[1:2] if isinstance(a, ast.Constant)), None) or next(
                    (k.value.value for k in c.keywords if k.arg == "mode" and isinstance(k.value, ast.Constant)), "r")
                if "b" not in modus and "encoding" not in kws:
                    fehler.append(f"{f.name}:{c.lineno} open() ohne encoding")
            if n in ("read_text", "write_text") and "encoding" not in kws:
                fehler.append(f"{f.name}:{c.lineno} {n}() ohne encoding")
    assert fehler == []


def test_keine_laufwerkspfade_im_code():
    fehler = []
    for f in QUELLEN:
        baum = _baum(f)
        doku = {id(k.body[0].value) for k in ast.walk(baum) if isinstance(k, (ast.Module, ast.FunctionDef, ast.ClassDef))
                and k.body and isinstance(k.body[0], ast.Expr) and isinstance(k.body[0].value, ast.Constant)}
        for c in ast.walk(baum):
            if isinstance(c, ast.Constant) and isinstance(c.value, str) and id(c) not in doku:
                if re.search(r"(?<![\w%])[A-Za-z]:\\", c.value) or re.match(r"[A-Za-z]:/", c.value):
                    fehler.append(f"{f.name}:{c.lineno} fester Laufwerkspfad {c.value[:40]!r}")
    assert fehler == []


def test_windows_funktionen_nur_gekapselt():
    verboten = {"winreg", "_winreg", "msvcrt", "pywintypes", "win32api", "win32con", "win32gui", "win32print",
                "win32com", "pythoncom"}
    fehler = []
    for f in QUELLEN:
        if f.name in WINDOWS_ERLAUBT:
            continue
        text = f.read_text(encoding="utf-8")
        for c in ast.walk(_baum(f)):
            if isinstance(c, (ast.Import, ast.ImportFrom)):
                for a in c.names:
                    modul = (getattr(c, "module", None) or a.name).split(".")[0]
                    if modul in verboten or a.name.split(".")[0] in verboten:
                        fehler.append(f"{f.name}:{c.lineno} import {modul}")
        for muster in ("os.startfile", "ctypes.windll", "CREATE_NO_WINDOW", "msedge"):
            if muster in text:
                fehler.append(f"{f.name}: {muster}")
    assert fehler == []


def test_daten_nur_im_datenordner():
    fehler = []
    for f in QUELLEN:
        text = f.read_text(encoding="utf-8")
        if re.search(r'PROJEKT\s*/\s*"Daten"|Path\.cwd\(\)|os\.getcwd\(\)', text):
            fehler.append(f.name)
    assert fehler == []


def test_kein_debug_server():
    for f in QUELLEN:
        text = f.read_text(encoding="utf-8")
        assert "app.run(" not in text and "debug=True" not in text, f.name


def test_zeitzone_nicht_mehr_stellen_als_bisher():
    anzahl = sum(len(re.findall(r"datetime\.now\(\)|date\.today\(\)|'localtime'", f.read_text(encoding="utf-8")))
                 for f in QUELLEN)
    assert anzahl <= ZEITZONE_HOECHSTENS, (
        f"{anzahl} Stellen mit Rechner-Zeitzone (höchstens {ZEITZONE_HOECHSTENS}) – bitte Europe/Berlin verwenden")


def test_feste_versionen():
    for datei in ("requirements.txt", "requirements-dev.txt"):
        for zeile in (WURZEL / datei).read_text(encoding="utf-8").splitlines():
            zeile = zeile.split("#")[0].strip()
            if zeile and not zeile.startswith("-r"):
                assert re.match(r"^[A-Za-z0-9_.\-]+==[0-9][\w.]*(\s*;.*)?$", zeile), f"{datei}: {zeile}"


def test_gespeicherte_dateipfade_werden_geprueft(client, con, app):
    from rsb import logik
    assert logik.pfad_problem("dokumente/2026/RE-2026-0001.pdf") is None
    assert "Backslashes" in logik.pfad_problem("dokumente\\2026\\RE.pdf")
    assert "absolut" in logik.pfad_problem("C:/Users/x/Daten/fotos/a.jpg")
    assert "absolut" in logik.pfad_problem("/home/x/a.jpg")
    assert "heraus" in logik.pfad_problem("../geheim/schluessel.key")
    assert logik.dateipfade_pruefen(con, app.config["DATEN"]) == []
    con.execute("INSERT INTO kassenbuch (lfd_nr, datum, art, betrag, text, beleg_datei, erfasst_am) "
                "VALUES (1, '2026-01-01', 'anfangsbestand', 100, 'Test', 'belege\\kasse\\x.pdf', '2026-01-01T10:00:00')")
    fehler = logik.dateipfade_pruefen(con, app.config["DATEN"])
    assert len(fehler) == 1 and "Kassenbeleg" in fehler[0]
    assert "Gespeicherte Dateipfade" in client.get("/pruefung").get_data(as_text=True)


def test_sicherer_dateiname_und_praefix_pruefung(client, con):
    from rsb import db as dbm
    from rsb.hilfen import sicherer_dateiname
    assert sicherer_dateiname("RE-2026-0001") == "RE-2026-0001"
    assert sicherer_dateiname('RE/2026:1*"') == "RE_2026_1__"
    assert sicherer_dateiname("") == "datei"
    from conftest import post
    alt = dbm.einstellungen(con)["praefix_rechnung"]
    r = post(client, "/einstellungen/rechnung", **{k: str(v) for k, v in dbm.einstellungen(con).items()
                                                   if k in ("steuer_modus", "regel_steuersatz",
                                                            "kleinunternehmer_hinweis", "zahlungsziel_privat",
                                                            "zahlungsziel_firma", "zahlungsarten_text",
                                                            "kva_gueltig_tage", "anzahlung_prozent", "nummern_format",
                                                            "praefix_gutschrift", "praefix_angebot", "praefix_kunde",
                                                            "leistungsarten", "aufbewahrung_belege_jahre",
                                                            "aufbewahrung_briefe_jahre")}, praefix_rechnung="RE/X")
    assert r.status_code == 302 and dbm.einstellungen(con)["praefix_rechnung"] == alt
    r = post(client, "/einstellungen/rechnung", **{k: str(v) for k, v in dbm.einstellungen(con).items()
                                                   if k in ("steuer_modus", "regel_steuersatz", "zahlungsziel_privat",
                                                            "zahlungsziel_firma", "kva_gueltig_tage",
                                                            "anzahlung_prozent", "praefix_rechnung",
                                                            "praefix_gutschrift", "praefix_angebot", "praefix_kunde",
                                                            "aufbewahrung_belege_jahre", "aufbewahrung_briefe_jahre")},
             nummern_format="{praefix}/{jahr}/{nummer:04d}")
    assert dbm.einstellungen(con)["nummern_format"] == "{praefix}-{jahr}-{nummer:04d}"  # „/“ im Ergebnis abgelehnt
