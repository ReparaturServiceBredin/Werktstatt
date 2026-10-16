# PyInstaller-Bauplan für Werkstatt-Sauter.exe (eine einzige Datei)
# Bauen:  pyinstaller Werkstatt-Sauter.spec   -> dist/Werkstatt-Sauter(.exe)
from PyInstaller.utils.hooks import collect_all

datas = [
    ("rsb/templates", "rsb/templates"),
    ("rsb/static", "rsb/static"),
    ("rsb/schema.sql", "rsb"),
    ("docs/AENDERUNGEN.md", "docs"),
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
    ["start_exe.py"],
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
    name="Werkstatt-Sauter",
    console=False,         # kein schwarzes Fenster; Bedienung über das Symbol neben der Uhr
    icon="rsb/static/bilder/programm.ico",
    upx=False,
    version="version_info.txt" if __import__("os").path.exists("version_info.txt") else None,
)
