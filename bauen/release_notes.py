"""Schreibt die Änderungen der aktuellen Version aus docs/AENDERUNGEN.md nach release_notes.md."""
import re
import sys
from pathlib import Path

wurzel = Path(__file__).resolve().parent.parent
version = sys.argv[1]
text = (wurzel / "docs/AENDERUNGEN.md").read_text(encoding="utf-8")
treffer = re.search(rf"^## {re.escape(version)}\b.*?$(.*?)(?=^## |\Z)", text, re.M | re.S)
notes = treffer.group(1).strip().rstrip("-").strip() if treffer else f"Version {version}"
(wurzel / "release_notes.md").write_text(notes + "\n", encoding="utf-8")
print(f"Release-Hinweise geschrieben ({len(notes)} Zeichen)")
