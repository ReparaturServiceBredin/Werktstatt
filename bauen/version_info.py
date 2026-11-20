"""Erzeugt die Dateieigenschaften der Windows-EXE (version_info.txt bzw. version_info_reifen.txt).

Aufruf: python bauen/version_info.py            -> Werkstatt Sauter (Version aus rsb/__init__.py)
        python bauen/version_info.py reifen     -> Reifen & Teile (Version aus rsb/variante.py)
Gibt die Versionsnummer aus.
"""
import re
import sys
from pathlib import Path

wurzel = Path(__file__).resolve().parent.parent
variante = (sys.argv[1] if len(sys.argv) > 1 else "sauter").lower()
if variante == "reifen":
    text = (wurzel / "rsb/variante.py").read_text(encoding="utf-8")
    block = text.split('"reifen": {', 1)[1]
    version = re.search(r'"version": "([^"]+)"', block).group(1)
    name, kurz, ziel = "Reifen & Teile", "Reifen-Teile", "version_info_reifen.txt"
else:
    version = re.search(r'VERSION_NUMMER = "([^"]+)"', (wurzel / "rsb/__init__.py").read_text(encoding="utf-8")).group(1)
    name, kurz, ziel = "Werkstatt Sauter", "Werkstatt-Sauter", "version_info.txt"
teile = [int(x) for x in version.split(".")] + [0] * 4
v4 = tuple(teile[:4])
(wurzel / ziel).write_text(f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={v4}, prodvers={v4}, mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0,
                    date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040704b0', [
      StringStruct('CompanyName', 'Reparatur Service Bredin'),
      StringStruct('FileDescription', '{name} – Aufträge, Rechnungen & Buchhaltung'),
      StringStruct('FileVersion', '{version}'),
      StringStruct('InternalName', '{kurz}'),
      StringStruct('OriginalFilename', '{kurz}.exe'),
      StringStruct('ProductName', '{kurz}'),
      StringStruct('ProductVersion', '{version}')])]),
    VarFileInfo([VarStruct('Translation', [0x0407, 1200])])
  ]
)
""", encoding="utf-8")
print(version)
