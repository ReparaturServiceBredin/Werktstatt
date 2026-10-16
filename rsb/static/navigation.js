// Navigation: Seitenleiste, Kopfzeile (Neu, Glocke, Hell/Dunkel), Schnellsuche (Strg+K), Einstellungsseite
(function () {
  'use strict';
  const $ = (s, w) => (w || document).querySelector(s);
  const $$ = (s, w) => [...(w || document).querySelectorAll(s)];
  const csrf = () => ($('meta[name=csrf]') || {}).content || '';
  const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const symbolUrl = (($('link[rel=stylesheet][href*="style.css"]') || {}).href || '/static/style.css').replace(/style\.css.*/, 'symbole.svg');
  const symbol = n => `<svg class="ic" aria-hidden="true"><use href="${symbolUrl}#i-${n}"></use></svg>`;
  const body = document.body;
  const schmalesFenster = () => matchMedia('(max-width: 900px)').matches;

  function merken(daten) {
    fetch('/oberflaeche', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRF': csrf() },
      body: JSON.stringify(daten) }).catch(() => {});
  }

  // ------------------------------------------------------------ Seitenleiste: Gruppen ein-/ausklappen
  $$('.nav-gruppe .gruppe-kopf').forEach(k => k.addEventListener('click', () => {
    if (body.classList.contains('nav-schmal') && !schmalesFenster()) return;
    const g = k.closest('.nav-gruppe');
    const zu = g.classList.toggle('zu');
    k.setAttribute('aria-expanded', zu ? 'false' : 'true');
    merken({ zu: $$('.nav-gruppe.zu').map(x => x.dataset.gruppe) });
  }));

  // schmale Seitenleiste (nur Symbole)
  const einklappen = $('#nav-einklappen');
  function einklappenText() {
    const schmal = body.classList.contains('nav-schmal');
    einklappen.setAttribute('aria-pressed', schmal ? 'true' : 'false');
    einklappen.dataset.titel = schmal ? 'Seitenleiste ausklappen' : 'Seitenleiste einklappen';
    $('.nav-text', einklappen).textContent = 'Seitenleiste einklappen';
  }
  if (einklappen) {
    einklappenText();
    einklappen.addEventListener('click', () => {
      body.classList.toggle('nav-schmal');
      einklappenText();
      tooltipAus();
      merken({ schmal: body.classList.contains('nav-schmal') });
    });
  }

  // Tooltips mit dem Namen, wenn die Seitenleiste schmal ist
  const tooltip = $('#nav-tooltip');
  function tooltipAus() { if (tooltip) tooltip.hidden = true; }
  $$('.seitenleiste .nav-punkt').forEach(p => {
    const zeigen = () => {
      if (!body.classList.contains('nav-schmal') || schmalesFenster() || !tooltip) return;
      const z = $('.zaehler', p);
      tooltip.textContent = p.dataset.titel + (z ? ` (${z.textContent.trim()})` : '');
      const r = p.getBoundingClientRect();
      tooltip.hidden = false;
      tooltip.style.left = (r.right + 10) + 'px';
      tooltip.style.top = (r.top + r.height / 2 - tooltip.offsetHeight / 2) + 'px';
    };
    p.addEventListener('mouseenter', zeigen); p.addEventListener('focus', zeigen);
    p.addEventListener('mouseleave', tooltipAus); p.addEventListener('blur', tooltipAus);
    if (body.classList.contains('nav-schmal')) p.setAttribute('aria-label', p.dataset.titel);
  });
  const navListe = $('.nav');
  if (navListe) navListe.addEventListener('scroll', tooltipAus);

  // Handy: Seitenleiste als ausklappbares Menü
  const navAuf = $('#nav-oeffnen'), schleier = $('#nav-schleier');
  function mobilNav(offen) {
    body.classList.toggle('nav-offen', offen);
    if (schleier) schleier.hidden = !offen;
    if (navAuf) navAuf.setAttribute('aria-expanded', offen ? 'true' : 'false');
    if (offen) { const a = $('.seitenleiste .nav-punkt.aktiv') || $('.seitenleiste .nav-punkt'); if (a) a.focus(); }
  }
  if (navAuf) navAuf.addEventListener('click', () => mobilNav(!body.classList.contains('nav-offen')));
  if (schleier) schleier.addEventListener('click', () => mobilNav(false));
  window.addEventListener('resize', () => { if (!schmalesFenster() && body.classList.contains('nav-offen')) mobilNav(false); });

  // ------------------------------------------------------------ Menüs in der Kopfzeile (+ Neu, Glocke)
  function menueZu(ausser) {
    $$('.menue').forEach(m => {
      if (m === ausser) return;
      const l = $('.menue-liste', m), k = $('.menue-knopf', m);
      if (l) l.hidden = true;
      if (k) k.setAttribute('aria-expanded', 'false');
    });
  }
  $$('.menue').forEach(m => {
    const k = $('.menue-knopf', m), l = $('.menue-liste', m);
    k.addEventListener('click', e => {
      e.stopPropagation();
      menueZu(m);
      l.hidden = !l.hidden;
      k.setAttribute('aria-expanded', l.hidden ? 'false' : 'true');
      if (!l.hidden) { const erstes = $('a', l); if (erstes && m.id === 'neu-menue') erstes.focus(); }
    });
    l.addEventListener('click', e => e.stopPropagation());
    l.addEventListener('keydown', e => {
      if (!['ArrowDown', 'ArrowUp'].includes(e.key)) return;
      const links = $$('a', l), i = links.indexOf(document.activeElement);
      e.preventDefault();
      (links[(i + (e.key === 'ArrowDown' ? 1 : -1) + links.length) % links.length] || links[0]).focus();
    });
  });
  document.addEventListener('click', () => menueZu());

  // Glocke: „Alle als gelesen“ ohne Neuladen
  const alleGelesen = $('.glocke-alle');
  if (alleGelesen) alleGelesen.addEventListener('submit', e => {
    e.preventDefault();
    fetch(alleGelesen.action, { method: 'POST', body: new FormData(alleGelesen), headers: { 'X-Requested-With': 'fetch' } })
      .then(r => { if (!r.ok) throw new Error(); $$('.glocke-eintrag.neu').forEach(x => x.classList.remove('neu'));
        const z = $('.glocke-zahl'); if (z) z.remove(); alleGelesen.remove(); })
      .catch(() => alleGelesen.submit());
  });

  // ------------------------------------------------------------ Hell / Dunkel
  const design = $('#design-wechseln');
  if (design) design.addEventListener('click', () => {
    const d = document.documentElement;
    const neu = d.dataset.theme === 'dunkel' ? 'hell' : 'dunkel';
    d.dataset.theme = neu; d.dataset.design = neu;
    merken({ design: neu });
  });
  matchMedia('(prefers-color-scheme: dark)').addEventListener('change', e => {
    const d = document.documentElement;
    if (d.dataset.design === 'auto') d.dataset.theme = e.matches ? 'dunkel' : 'hell';
  });

  // ------------------------------------------------------------ Schnellsuche (Strg+K)
  const dlg = $('#schnellsuche'), feld = $('#ss-feld'), liste = $('#ss-liste');
  let auswahl = -1, anfrage = 0, timer = null, gezeigt = null, laufend = null;
  function eintraege() { return $$('.ss-eintrag', liste); }
  function waehlen(i) {
    const e = eintraege();
    if (!e.length) { auswahl = -1; return; }
    auswahl = (i + e.length) % e.length;
    e.forEach((x, n) => { x.classList.toggle('gewaehlt', n === auswahl); x.setAttribute('aria-selected', n === auswahl); });
    e[auswahl].scrollIntoView({ block: 'nearest' });
    feld.setAttribute('aria-activedescendant', e[auswahl].id);
  }
  function zeichnen(gruppen, q) {
    let n = 0;
    liste.innerHTML = gruppen.length ? gruppen.map(g => `<div class="ss-art">${esc(g.art)}</div>` + g.eintraege.map(e =>
      `<a class="ss-eintrag" role="option" id="ss-${n++}" href="${esc(e.url)}">${symbol(e.symbol || 'arrow-right')}` +
      `<span><span class="ss-titel">${esc(e.titel)}</span>${e.unter ? `<span class="ss-unter">${esc(e.unter)}</span>` : ''}</span>` +
      `<span class="ss-enter">${symbol('corner-down-left')}</span></a>`).join('')).join('')
      : `<div class="ss-leer">Nichts gefunden für „${esc(q)}“.</div>`;
    eintraege().forEach((x, i) => x.addEventListener('mousemove', () => { if (auswahl !== i) waehlen(i); }));
    waehlen(0);
  }
  function suchen() {
    const q = feld.value.trim(), nr = ++anfrage;
    clearTimeout(timer);
    laufend = fetch('/suche.json?q=' + encodeURIComponent(q), { headers: { 'X-Requested-With': 'fetch' } })
      .then(r => r.json())
      .then(daten => { if (nr === anfrage) { zeichnen(daten, q); gezeigt = q; } })
      .catch(() => { if (nr === anfrage) liste.innerHTML = '<div class="ss-leer">Suche gerade nicht möglich.</div>'; });
    return laufend;
  }
  function suchOeffnen() {
    if (!dlg) return;
    menueZu();
    if (!dlg.open) dlg.showModal();
    feld.select();
    suchen();
  }
  if (dlg) {
    $('#such-oeffnen').addEventListener('click', suchOeffnen);
    feld.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(suchen, 120); });
    feld.addEventListener('keydown', e => {
      if (e.key === 'ArrowDown') { e.preventDefault(); waehlen(auswahl + 1); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); waehlen(auswahl - 1); }
      else if (e.key === 'Escape') { e.preventDefault(); dlg.close(); }
      else if (e.key === 'Enter') {
        e.preventDefault();
        // Enter vor dem Eintreffen der Ergebnisse: erst die aktuelle Eingabe suchen, dann öffnen
        const fertig = gezeigt === feld.value.trim() ? Promise.resolve() : suchen();
        fertig.then(() => {
          const z = eintraege()[auswahl];
          if (z) { dlg.close(); window.location.href = z.href; }
        });
      }
    });
    dlg.addEventListener('click', e => { if (e.target === dlg) dlg.close(); });
  }
  document.addEventListener('keydown', e => {
    if ((e.ctrlKey || e.metaKey) && !e.altKey && e.key.toLowerCase() === 'k') { e.preventDefault(); suchOeffnen(); }
    else if (e.key === 'Escape') { menueZu(); if (body.classList.contains('nav-offen')) mobilNav(false); }
  });

  // ------------------------------------------------------------ Einstellungen
  const inhalt = $('.einst-inhalt');
  if (!inhalt) return;

  // Anker wie im Suchindex: abschnitt-<n> für Überschriften, feld-<name> für Felder
  $$('h2', inhalt).forEach((h, i) => { if (!h.id) h.id = 'abschnitt-' + (i + 1); else h.dataset.anker = 'abschnitt-' + (i + 1); });
  $$('input[name], select[name], textarea[name]', inhalt).forEach(f => {
    if (f.type === 'hidden' || f.name === 'csrf') return;
    const zelle = f.closest('.felder > div') || f.closest('label') || f;
    if (!zelle.id && !$('#feld-' + CSS.escape(f.name))) zelle.id = 'feld-' + f.name;
  });

  // Speichern-Leiste unten fixiert + ungespeicherte Änderungen
  let geaendert = false, sendet = false;
  const einstForms = $$('form.karte', inhalt).filter(f => (f.getAttribute('method') || '').toLowerCase() === 'post' && !f.getAttribute('action'));
  einstForms.forEach(f => {
    const kinder = [...f.children];
    const knopfZeile = kinder.reverse().find(k => (k.tagName === 'BUTTON' && !k.type.match(/button/)) ||
      (k.classList.contains('leiste') && [...k.children].some(b => b.tagName === 'BUTTON')));
    if (knopfZeile) {
      const leiste = document.createElement('div');
      leiste.className = 'speicherleiste';
      const vorher = knopfZeile.previousElementSibling;
      if (vorher && vorher.tagName === 'BR') vorher.remove();
      f.appendChild(leiste);
      if (knopfZeile.classList.contains('leiste')) [...knopfZeile.children].forEach(c => leiste.appendChild(c)), knopfZeile.remove();
      else leiste.appendChild(knopfZeile);
      leiste.insertAdjacentHTML('beforeend', '<span class="ungespeichert">● Ungespeicherte Änderungen</span>');
    }
    const markieren = () => { geaendert = true; f.classList.add('geaendert'); };
    f.addEventListener('input', markieren);
    f.addEventListener('change', markieren);
    f.addEventListener('submit', () => { sendet = true; });
  });
  window.addEventListener('beforeunload', e => {
    if (geaendert && !sendet) { e.preventDefault(); e.returnValue = ''; }
  });

  // Lange Seiten: Abschnitte (Überschriften) einklappbar
  $$('.karte', inhalt).forEach(k => {
    const h2s = [...k.children].filter(c => c.tagName === 'H2');
    if (h2s.length < 2) return;
    h2s.forEach(h => {
      const abschnitt = document.createElement('section'), innen = document.createElement('div'), huelle = document.createElement('div');
      abschnitt.className = 'abschnitt'; huelle.className = 'abschnitt-inhalt';
      let el = h.nextElementSibling;
      const sammeln = [];
      while (el && el.tagName !== 'H2' && !el.classList.contains('speicherleiste') && !(el.tagName === 'BR' && el.nextElementSibling && el.nextElementSibling.tagName === 'H2')) {
        sammeln.push(el); el = el.nextElementSibling;
      }
      if (el && el.tagName === 'BR') el.remove();
      const knopf = document.createElement('button');
      knopf.type = 'button'; knopf.className = 'abschnitt-kopf'; knopf.setAttribute('aria-expanded', 'true');
      knopf.innerHTML = symbol('chevron-down').replace('class="ic"', 'class="ic pfeil"') + `<span>${h.innerHTML}</span>`;
      k.insertBefore(abschnitt, h);
      const anker = h.id; h.remove();
      knopf.id = anker;
      if (h.dataset.anker) knopf.dataset.anker = h.dataset.anker;
      abschnitt.append(knopf, huelle); huelle.appendChild(innen);
      sammeln.forEach(s => innen.appendChild(s));
      knopf.addEventListener('click', () => {
        const zu = abschnitt.classList.toggle('zu');
        knopf.setAttribute('aria-expanded', zu ? 'false' : 'true');
      });
    });
  });

  // Sprung zu Abschnitt/Feld (#feld-…, #abschnitt-…) und kurz hervorheben
  function springen() {
    const id = decodeURIComponent(location.hash.slice(1));
    if (!id) return;
    const ziel = document.getElementById(id) || $(`[data-anker="${CSS.escape(id)}"]`);
    if (!ziel) return;
    const abschnitt = ziel.closest('.abschnitt.zu');
    if (abschnitt) { abschnitt.classList.remove('zu'); $('.abschnitt-kopf', abschnitt).setAttribute('aria-expanded', 'true'); }
    setTimeout(() => {
      ziel.scrollIntoView({ block: 'center', behavior: 'smooth' });
      ziel.classList.remove('hervorheben'); void ziel.offsetWidth; ziel.classList.add('hervorheben');
      const f = $('input:not([type=hidden]), select, textarea', ziel) || (ziel.matches('input, select, textarea') ? ziel : null);
      if (f) f.focus({ preventScroll: true });
    }, 60);
  }
  window.addEventListener('hashchange', springen);
  springen();

  // Handy: Unternavigation auf- und zuklappen
  const einstNavKnopf = $('.einst-nav-knopf');
  if (einstNavKnopf) einstNavKnopf.addEventListener('click', () => {
    const nav = einstNavKnopf.closest('.einst-nav');
    einstNavKnopf.setAttribute('aria-expanded', nav.classList.toggle('offen') ? 'true' : 'false');
  });

  // Suche in den Einstellungen
  const suche = $('#einst-suche'), treffer = $('#einst-treffer');
  if (!suche) return;
  let gewaehlt = -1, nrE = 0, timerE = null;
  function trefferWaehlen(i) {
    const a = $$('a', treffer);
    if (!a.length) return;
    gewaehlt = (i + a.length) % a.length;
    a.forEach((x, n) => x.classList.toggle('gewaehlt', n === gewaehlt));
    a[gewaehlt].scrollIntoView({ block: 'nearest' });
  }
  async function einstSuchen() {
    const q = suche.value.trim(), nr = ++nrE;
    if (!q) { treffer.hidden = true; return; }
    const r = await fetch('/einstellungen/suche.json?q=' + encodeURIComponent(q));
    const daten = await r.json();
    if (nr !== nrE) return;
    treffer.innerHTML = daten.length ? daten.map(t => `<a href="${esc(t.url)}">${esc(t.titel)}<span class="klein">${esc(
      [t.bereich_titel, t.abschnitt].filter(x => x && x !== t.titel).join(' › '))}</span></a>`).join('')
      : '<div class="klein" style="padding:8px">Keine passende Einstellung.</div>';
    treffer.hidden = false;
    gewaehlt = -1; trefferWaehlen(0);
  }
  suche.addEventListener('input', () => { clearTimeout(timerE); timerE = setTimeout(einstSuchen, 120); });
  suche.addEventListener('keydown', e => {
    if (e.key === 'ArrowDown') { e.preventDefault(); trefferWaehlen(gewaehlt + 1); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); trefferWaehlen(gewaehlt - 1); }
    else if (e.key === 'Enter') { e.preventDefault(); const a = $$('a', treffer)[gewaehlt]; if (a) a.click(); }
    else if (e.key === 'Escape') { treffer.hidden = true; }
  });
  treffer.addEventListener('click', e => {
    const a = e.target.closest('a');
    if (!a) return;
    const url = new URL(a.href);
    treffer.hidden = true;
    if (url.pathname === location.pathname) {  // gleicher Bereich: nur springen
      e.preventDefault();
      if (location.hash === url.hash) springen(); else location.hash = url.hash;
    }
  });
  document.addEventListener('click', e => { if (!e.target.closest('.einst-suche')) treffer.hidden = true; });
  document.addEventListener('keydown', e => {
    if (e.key === '/' && !e.target.closest('input, textarea, select, [contenteditable]')) { e.preventDefault(); suche.focus(); }
  });
})();
