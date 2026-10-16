"""Suche in den Einstellungen: liest Abschnitte (Überschriften) und Felder (Beschriftungen) aus dem gerenderten HTML.

Anker: „feld-<name>“ für ein Eingabefeld, „abschnitt-<n>“ für die n-te Überschrift eines Bereichs. Dieselben Anker
vergibt navigation.js auf der Einstellungsseite.
"""
import re
import unicodedata
from html.parser import HTMLParser


class _Leser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.treffer, self.abschnitt, self.h2_nr = [], "", 0
        self._in_h2 = self._in_label = False
        self._text, self._label_feld, self._offenes_label, self._gesehen = "", None, "", set()

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "h2":
            self._in_h2, self._text = True, ""
        elif tag == "label":
            self._in_label, self._text, self._label_feld = True, "", None
        elif tag in ("input", "select", "textarea"):
            name, typ = a.get("name"), (a.get("type") or "").lower()
            if not name or name == "csrf" or typ in ("hidden", "submit", "button", "file"):
                return
            if self._in_label:
                self._label_feld = name  # <label class="check"><input …> Text</label>
            elif self._offenes_label:
                self._neu(self._offenes_label, name)
                self._offenes_label = ""

    def handle_endtag(self, tag):
        if tag == "h2" and self._in_h2:
            self._in_h2 = False
            self.h2_nr += 1
            self.abschnitt = _sauber(self._text)
            if self.abschnitt:
                self.treffer.append({"abschnitt": self.abschnitt, "feld": "", "titel": self.abschnitt,
                                     "anker": f"abschnitt-{self.h2_nr}"})
        elif tag == "label" and self._in_label:
            self._in_label = False
            text = _sauber(self._text)
            if self._label_feld:
                self._neu(text, self._label_feld)
            else:
                self._offenes_label = text

    def handle_data(self, data):
        if self._in_h2 or self._in_label:
            self._text += data

    def _neu(self, text, name):
        if not text or name in self._gesehen:
            return
        self._gesehen.add(name)
        self.treffer.append({"abschnitt": self.abschnitt, "feld": name, "titel": text, "anker": f"feld-{name}"})


def _sauber(text):
    return re.sub(r"\s+", " ", text or "").strip(" :")


def felder_lesen(html):
    leser = _Leser()
    leser.feed(html)
    return leser.treffer


def normal(text):
    """Kleinschreibung, ohne Akzente, ä→ae usw. – damit „Loeschfrist“ auch „Löschfrist“ findet."""
    t = (text or "").lower().replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    return "".join(c for c in unicodedata.normalize("NFKD", t) if not unicodedata.combining(c))


def passt(q, eintrag, *felder):
    woerter = normal(q).split()
    if not woerter:
        return False
    heu = normal(" ".join(str(eintrag.get(k) or "") for k in (felder or ("titel", "abschnitt", "bereich_titel",
                                                                         "feld"))))
    return all(w in heu for w in woerter)
