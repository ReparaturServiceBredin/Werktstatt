"""Erzeugt version_info.txt (Dateieigenschaften der Windows-EXE) aus rsb/__init__.py."""
import re
from pathlib import Path

wurzel = Path(__file__).resolve().parent.parent
version = re.search(r'VERSION_NUMMER = "([^"]+)"', (wurzel / "rsb/__init__.py").read_text(encoding="utf-8")).group(1)
teile = [int(x) for x in version.split(".")] + [0] * 4
v4 = tuple(teile[:4])
(wurzel / "version_info.txt").write_text(f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={v4}, prodvers={v4}, mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0,
                    date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040704b0', [
      StringStruct('CompanyName', 'Reparatur Service Bredin'),
      StringStruct('FileDescription', 'Werkstatt Sauter – Aufträge, Rechnungen & Buchhaltung'),
      StringStruct('FileVersion', '{version}'),
      StringStruct('InternalName', 'Werkstatt-Sauter'),
      StringStruct('OriginalFilename', 'Werkstatt-Sauter.exe'),
      StringStruct('ProductName', 'Werkstatt-Sauter'),
      StringStruct('ProductVersion', '{version}')])]),
    VarFileInfo([VarStruct('Translation', [0x0407, 1200])])
  ]
)
""", encoding="utf-8")
print(version)
