# PyInstaller-Bauplan für Reifen-Teile.exe (Variante „Reifen & Teile“, eine einzige Datei)
# Bauen:  python bauen/version_info.py reifen && pyinstaller Reifen-Teile.spec   -> dist/Reifen-Teile(.exe)
from PyInstaller.utils.hooks import collect_all

datas = [
    ("rsb/templates", "rsb/templates"),
    ("rsb/static", "rsb/static"),
    ("rsb/schema.sql", "rsb"),
    ("docs/AENDERUNGEN.md", "docs"),
    ("docs/AENDERUNGEN_REIFEN.md", "docs"),
]
binaries = []
hiddenimports = ["waitress", "pystray._win32"]
# tzdata: deutsche Zeitzone; facturx/drafthorse: XSD-, Schematron- und XMP-Dateien der E-Rechnung
for paket in ("reportlab", "tzdata", "facturx", "drafthorse", "pypdf", "lxml", "stdnum", "iso4217"):
    d, b, h = collect_all(paket)
    datas += d
    binaries += b
    hiddenimports += h

a = Analysis(
    ["start_exe_reifen.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "pytest", "playwright", "aiosmtpd"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="Reifen-Teile",
    console=False,         # kein schwarzes Fenster; Bedienung über das Symbol neben der Uhr
    icon="rsb/static/bilder/programm_reifen.ico",
    upx=False,
    version="version_info_reifen.txt" if __import__("os").path.exists("version_info_reifen.txt") else None,
)
