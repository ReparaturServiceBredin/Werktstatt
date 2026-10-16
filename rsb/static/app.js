// Hilfsfunktionen für Beträge im deutschen Format
function zahl(text) {
  if (text === undefined || text === null) return 0;
  let t = String(text).replace(/[€\s]/g, '');
  if (t.includes(',')) t = t.replace(/\./g, '').replace(',', '.');
  const n = parseFloat(t);
  return isNaN(n) ? 0 : n;
}
function euroText(n) {
  return n.toLocaleString('de-DE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}
function euro(n) { return euroText(n) + ' €'; }

// ---------------------------------------------------------------- Fotos hochladen (Auftrag)
function csrfWert() { const f = document.querySelector('input[name=csrf]'); return f ? f.value : ''; }

document.querySelectorAll('.foto-upload').forEach(box => {
  const zone = box.querySelector('.foto-zone'), info = box.querySelector('.foto-fortschritt');
  async function hochladen(dateien) {
    dateien = [...dateien];
    if (!dateien.length) return;
    const kategorie = box.querySelector('.foto-kategorie').value;
    let fehler = [];
    for (let i = 0; i < dateien.length; i++) {
      info.textContent = `Lade Foto ${i + 1} von ${dateien.length} hoch …`;
      const daten = new FormData();
      daten.append('csrf', csrfWert());
      daten.append('kategorie', kategorie);
      daten.append('upload_token', box.dataset.token || '');
      daten.append('foto', dateien[i], dateien[i].name);
      try {
        const r = await fetch(box.dataset.url, { method: 'POST', body: daten, headers: { 'X-Requested-With': 'fetch' } });
        const j = await r.json().catch(() => ({ ok: false, meldung: r.status === 413 ? 'Datei zu groß' : `Fehler ${r.status}` }));
        (j.dateien || [j]).forEach(e => {
          if (!e.ok) { fehler.push(`${e.datei || dateien[i].name}: ${e.meldung}`); return; }
          const galerie = document.getElementById('galerie-neu');
          if (galerie) galerie.insertAdjacentHTML('beforeend',
            `<div class="foto"><a href="/fotos/${e.id}" target="_blank"><img src="/fotos/${e.id}/vorschau" alt=""></a><div class="info"><b>${kategorie}</b><br>${e.datei}</div></div>`);
        });
      } catch (err) { fehler.push(`${dateien[i].name}: Verbindung fehlgeschlagen`); }
    }
    info.textContent = fehler.length ? 'Nicht gespeichert: ' + fehler.join(' · ') : `${dateien.length} Foto(s) gespeichert.`;
    info.style.color = fehler.length ? 'var(--rot)' : 'var(--gruen)';
    if (box.dataset.neuLaden === '1' && fehler.length < dateien.length) {
      setTimeout(() => { window.location.hash = 'fotos'; window.location.reload(); }, fehler.length ? 2500 : 300);
    }
  }
  box.querySelectorAll('.foto-datei').forEach(inp => inp.addEventListener('change', () => { hochladen(inp.files); inp.value = ''; }));
  zone.addEventListener('dragover', e => { e.preventDefault(); zone.classList.add('ueber'); });
  zone.addEventListener('dragleave', () => zone.classList.remove('ueber'));
  zone.addEventListener('drop', e => { e.preventDefault(); zone.classList.remove('ueber'); hochladen(e.dataTransfer.files); });
});

// ---------------------------------------------------------------- KVA-Auswahl (Auftrag verknüpfen)
document.querySelectorAll('.kva-auswahl').forEach(box => {
  const suche = box.querySelector('.kva-suche'), alle = box.querySelector('.kva-alle');
  const tbody = box.querySelector('tbody');
  const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  let timer = null;
  async function laden() {
    const kunde = box.dataset.kunde || '';
    const p = new URLSearchParams({ kunde_id: kunde, alle: (alle.checked || !kunde) ? '1' : '0', q: suche.value });
    const r = await fetch('/auftraege/kva-auswahl?' + p);
    const liste = r.ok ? await r.json() : [];
    if (!liste.length) {
      tbody.innerHTML = `<tr><td colspan="5" class="klein">Keine freien Kostenvoranschläge gefunden${(kunde && !alle.checked) ? ' (nur dieser Kunde – „alle Kunden anzeigen“ probieren)' : ''}.</td></tr>`;
      return;
    }
    tbody.innerHTML = liste.map(d => `<tr data-id="${d.id}" data-text="${esc(d.nummer + ' · ' + d.datum + ' · ' + d.betrag)}">
      <td><a href="/dokumente/${d.id}" target="_blank">${esc(d.nummer)}</a><div class="klein">${esc(d.betreff)}</div></td>
      <td>${esc(d.datum)}</td><td>${esc(d.kunde)}${(kunde && String(d.kunde_id) !== String(kunde)) ? ' <span class="marke-status st-warnung">anderer Kunde</span>' : ''}</td>
      <td class="zahl">${esc(d.betrag)}</td><td class="zahl"><button type="button" class="zweit klein kva-waehlen">Verknüpfen</button></td></tr>`).join('');
  }
  box.laden = laden;
  suche.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(laden, 250); });
  alle.addEventListener('change', laden);
  tbody.addEventListener('click', e => {
    const knopf = e.target.closest('.kva-waehlen');
    if (!knopf) return;
    const zeile = knopf.closest('tr');
    if (box.dataset.modus === 'verknuepfen') {
      const f = document.createElement('form');
      f.method = 'post'; f.action = box.dataset.ziel;
      f.innerHTML = `<input type="hidden" name="csrf" value="${esc(csrfWert())}"><input type="hidden" name="kva_id" value="${zeile.dataset.id}">`;
      document.body.appendChild(f); f.submit();
    } else {
      document.getElementById('f_kva_id').value = zeile.dataset.id;
      document.getElementById('kva-gewaehlt-text').textContent = zeile.dataset.text;
      document.getElementById('kva-gewaehlt').hidden = false;
      tbody.querySelectorAll('tr').forEach(t => t.classList.toggle('gewaehlt', t === zeile));
    }
  });
  laden();
});

// ---------------------------------------------------------------- Reiter (#hash)
function reiterInit(standard) {
  function zeigen() {
    const name = (location.hash || '#' + standard).slice(1);
    const gueltig = document.querySelector(`[data-bereich="${name}"]`) ? name : standard;
    document.querySelectorAll('[data-bereich]').forEach(s => s.hidden = s.dataset.bereich !== gueltig);
    document.querySelectorAll('[data-reiter]').forEach(r => r.classList.toggle('aktiv', r.dataset.reiter === gueltig));
  }
  window.addEventListener('hashchange', zeigen);
  zeigen();
}

// ---------------------------------------------------------------- Gerätezugang (Auftrag)
document.querySelectorAll('.zugang-art').forEach(auswahl => {
  const form = auswahl.closest('form'), feld = form.querySelector('.zugang-feld');
  if (!feld) return;
  const eingabe = feld.querySelector('input[name=zugang_wert]'), muster = feld.querySelector('.muster');
  function anpassen() {
    feld.hidden = !['pin', 'passwort', 'muster'].includes(auswahl.value);
    muster.hidden = auswahl.value !== 'muster';
  }
  auswahl.addEventListener('change', anpassen); anpassen();
  feld.querySelector('.zugang-zeigen-eingabe').addEventListener('click', () => {
    eingabe.type = eingabe.type === 'password' ? 'text' : 'password';
  });
  muster.querySelectorAll('[data-punkt]').forEach(b => b.addEventListener('click', () => {
    const teile = eingabe.value ? eingabe.value.split('-') : [];
    if (teile.includes(b.dataset.punkt)) return;
    teile.push(b.dataset.punkt); eingabe.value = teile.join('-'); eingabe.type = 'text';
    b.classList.add('gewaehlt');
  }));
  muster.querySelector('.muster-neu').addEventListener('click', () => {
    eingabe.value = ''; muster.querySelectorAll('[data-punkt]').forEach(b => b.classList.remove('gewaehlt'));
  });
  const anzeigen = feld.querySelector('.zugang-anzeigen');
  if (anzeigen) anzeigen.addEventListener('click', async () => {
    if (!confirm('Zugangsdaten anzeigen? Der Zugriff wird im Verlauf des Auftrags vermerkt.')) return;
    const daten = new FormData(); daten.append('csrf', csrfWert());
    const r = await fetch(anzeigen.dataset.url, { method: 'POST', body: daten });
    const j = r.ok ? await r.json() : { wert: '' };
    feld.querySelector('.zugang-ausgabe').textContent = j.wert || '(nicht lesbar)';
  });
});

// ---------------------------------------------------------------- Unterschriftsfeld (Canvas, Maus/Finger/Stift)
// Die Striche werden als Punktlisten gemerkt und bei jeder Größenänderung (z. B. Handy drehen) neu gezeichnet.
document.querySelectorAll('.unterschrift').forEach(box => {
  const canvas = box.querySelector('canvas'), ctx = canvas.getContext('2d');
  const feld = box.querySelector('input[name=unterschrift]'), form = box.closest('form');
  let striche = [], aktuell = null, breite = 0;
  function zeichnen() {
    const r = canvas.getBoundingClientRect(), v = window.devicePixelRatio || 1;
    if (!r.width) return;
    canvas.width = Math.round(r.width * v); canvas.height = Math.round(r.height * v);
    ctx.setTransform(v, 0, 0, v, 0, 0);
    ctx.lineWidth = 2.4; ctx.lineCap = 'round'; ctx.lineJoin = 'round';
    ctx.strokeStyle = ctx.fillStyle = '#0b1f4d';
    const f = breite ? r.width / breite : 1;   // Striche an neue Breite anpassen
    striche.forEach(s => {
      ctx.beginPath();
      if (s.length === 1) { ctx.arc(s[0][0] * f, s[0][1] * f, 1.2, 0, Math.PI * 2); ctx.fill(); return; }
      s.forEach(([x, y], i) => i ? ctx.lineTo(x * f, y * f) : ctx.moveTo(x * f, y * f));
      ctx.stroke();
    });
    if (breite && f !== 1) { striche = striche.map(s => s.map(([x, y]) => [x * f, y * f])); }
    breite = r.width;
    box.classList.toggle('hat-unterschrift', striche.length > 0);
  }
  function punkt(e) { const r = canvas.getBoundingClientRect(); return [e.clientX - r.left, e.clientY - r.top]; }
  canvas.addEventListener('pointerdown', e => {
    e.preventDefault();
    try { canvas.setPointerCapture(e.pointerId); } catch (err) {}
    aktuell = [punkt(e)]; striche.push(aktuell); zeichnen();
  });
  canvas.addEventListener('pointermove', e => {
    if (!aktuell) return;
    e.preventDefault();
    const p = punkt(e), l = aktuell[aktuell.length - 1];
    ctx.beginPath(); ctx.moveTo(l[0], l[1]); ctx.lineTo(p[0], p[1]); ctx.stroke();
    aktuell.push(p);
  });
  ['pointerup', 'pointercancel'].forEach(t => canvas.addEventListener(t, () => { aktuell = null; zeichnen(); }));
  box.querySelector('.unterschrift-loeschen').addEventListener('click', () => { striche = []; zeichnen(); });
  window.addEventListener('resize', zeichnen); zeichnen();
  form.addEventListener('submit', e => {
    if (!striche.length) { e.preventDefault(); alert('Bitte im Feld unterschreiben.'); return; }
    zeichnen(); feld.value = canvas.toDataURL('image/png');
    form.querySelectorAll('button[type=submit], button:not([type])').forEach(b => { b.disabled = true; b.textContent = 'Wird gespeichert …'; });
  });
});

// ---------------------------------------------------------------- Gerät schon bekannt? (SN/IMEI) + Garantiefall
(function () {
  const sn = document.getElementById('f_sn'), box = document.getElementById('sn-hinweis');
  const art = document.getElementById('f_auftragsart'), bezug = document.getElementById('f_garantie_bezug');
  if (!sn || !box) return;
  const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  function artAnpassen() {
    document.querySelectorAll('.nur-garantie').forEach(e => e.hidden = art.value !== 'garantie');
  }
  if (art) { art.addEventListener('change', artAnpassen); artAnpassen(); }
  let timer = null;
  async function pruefen() {
    const wert = sn.value.trim();
    if (wert.replace(/[\s\-\/.]/g, '').length < 4) { box.hidden = true; return; }
    const r = await fetch('/auftraege/geraet-pruefen?' + new URLSearchParams({ sn: wert, ohne: sn.dataset.ohne || '' }));
    const liste = r.ok ? await r.json() : [];
    if (!liste.length) { box.hidden = true; return; }
    const garantie = liste.some(v => v.laeuft);
    box.innerHTML = `<div class="meldung ${garantie ? 'warnung' : 'info'}" style="margin:0"><b>Dieses Gerät war schon ${liste.length}× hier${garantie ? ' – Garantie läuft noch!' : ''}</b>` +
      liste.map(v => `<div style="margin-top:4px">· <a href="${v.url}" target="_blank">${esc(v.auftragsnr)}</a> vom ${esc(v.eingang)} · ${esc(v.kunde)} · ${esc(v.fehler || v.geraet)}
        · Garantie: <b>${esc(v.garantie)}</b>${v.fotos ? ` · <a href="${v.url}#fotos" target="_blank">${v.fotos} Foto(s)</a>` : ''}${v.rechnung_url ? ` · <a href="${v.rechnung_url}" target="_blank">Rechnung ${esc(v.rechnung)}</a>` : ''}
        ${art ? `<button type="button" class="zweit klein als-garantie" data-id="${v.id}" data-nr="${esc(v.auftragsnr)}">als Garantiefall zu ${esc(v.auftragsnr)}</button>` : ''}</div>`).join('') + '</div>';
    box.hidden = false;
    box.querySelectorAll('.als-garantie').forEach(b => b.addEventListener('click', () => {
      art.value = 'garantie'; bezug.value = b.dataset.id; artAnpassen();
      document.getElementById('garantie-bezug-text').textContent = `Garantiefall zum Auftrag ${b.dataset.nr} – keine Rechnung beim Erledigen.`;
    }));
  }
  sn.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(pruefen, 400); });
  pruefen();
})();

// ---------------------------------------------------------------- KVA-Pauschale nach Gerätetyp vorschlagen
(function () {
  const typ = document.getElementById('f_geraetetyp'), betrag = document.getElementById('f_kva_gebuehr');
  const frei = document.getElementById('f_kva_kostenlos');
  if (!typ || !betrag) return;
  let selbst = !!betrag.value;   // einmal von Hand geändert → nicht mehr überschreiben
  betrag.addEventListener('input', () => { selbst = !!betrag.value; });
  typ.addEventListener('change', () => {
    const o = typ.selectedOptions[0];
    if (!selbst && o && o.dataset.cent) betrag.value = euroText(parseInt(o.dataset.cent) / 100);
  });
  if (frei) {
    const sperren = () => { betrag.disabled = frei.checked; };
    frei.addEventListener('change', sperren); sperren();
  }
})();
