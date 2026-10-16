"""Zeigt das Versionsprotokoll (docs/AENDERUNGEN.md) im Programm an."""
import re
import sys
from html import escape
from pathlib import Path


def protokoll_datei():
    basis = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return basis / "docs" / "AENDERUNGEN.md"


def _inline(text):
    t = escape(text)
    t = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r'<a href="\2" target="_blank" rel="noopener">\1</a>', t)
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"\*(.+?)\*", r"<i>\1</i>", t)
    t = re.sub(r"`(.+?)`", r"<code>\1</code>", t)
    return t


def als_html(markdown):
    """Kleiner Markdown-Umsetzer für Überschriften, Listen, Tabellen und Absätze."""
    html, liste, tabelle, absatz = [], [], [], []

    def leeren():
        if absatz:
            html.append("<p>" + " ".join(_inline(z) for z in absatz) + "</p>")
            absatz.clear()
        if liste:
            html.append("<ul>" + "".join(liste) + "</ul>")
            liste.clear()
        if tabelle:
            kopf, *zeilen = [z for z in tabelle if not re.match(r"^\|[\s\-|:]+\|$", z)]
            zellen = lambda z: [c.strip() for c in z.strip("|").split("|")]  # noqa: E731
            html.append('<table class="liste"><tr>' + "".join(f"<th>{_inline(c)}</th>" for c in zellen(kopf)) + "</tr>"
                        + "".join("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in zellen(z)) + "</tr>"
                                  for z in zeilen) + "</table>")
            tabelle.clear()

    for zeile in markdown.splitlines():
        z = zeile.rstrip()
        if z.startswith("|"):
            if absatz or liste:
                leeren()
            tabelle.append(z)
            continue
        if tabelle:
            leeren()
        if not z.strip():
            leeren()
        elif z.strip() == "---":
            leeren()
            html.append("<hr>")
        elif m := re.match(r"^(#{1,4})\s+(.*)", z):
            leeren()
            ebene = len(m.group(1))
            anker = ""
            if ebene == 2 and (v := re.match(r"(\d+\.\d+\.\d+)", m.group(2))):
                anker = f' id="v{v.group(1)}"'
            html.append(f"<h{ebene + 1}{anker}>{_inline(m.group(2))}</h{ebene + 1}>")
        elif m := re.match(r"^(\s*)- (.*)", z):
            if absatz:
                leeren()
            klasse = ' class="unter"' if len(m.group(1)) >= 2 else ""
            liste.append(f"<li{klasse}>{_inline(m.group(2))}</li>")
        elif liste and zeile.startswith("  "):
            liste[-1] = liste[-1][:-5] + " " + _inline(z.strip()) + "</li>"
        else:
            absatz.append(z.strip())
    leeren()
    return "\n".join(html)


def protokoll_html():
    datei = protokoll_datei()
    if not datei.is_file():
        return "<p>Versionsprotokoll nicht gefunden.</p>"
    return als_html(datei.read_text(encoding="utf-8"))
