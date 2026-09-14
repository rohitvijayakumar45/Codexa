app_js_code = r'''
// ATLAS Application JavaScript
// State, Rendering, and Interaction Layer

// --- Utilities ---
const $ = (s, root = document) => root.querySelector(s);
const $$ = (s, root = document) => Array.from(root.querySelectorAll(s));
const svgNS = "http://www.w3.org/2000/svg";

const PLATES = PLATES_DATA;
const TYPOLOGIES = TYPOLOGIES_DATA;
const MATERIALS = MATERIALS_DATA;
const SVG_BLUEPRINTS = SVG_DEFS;

// --- Application State ---
const state = {
  view: 'folio',
  activePlateId: 'plate-parthenon',
  activePlate: null,
  bookmarkedPlates: [],
  typologyFilters: { era: 'all', system: 'all', search: '' },
  compareA: 'plate-parthenon',
  compareB: 'plate-kahn',
  inkMode: 'bone',
  showGrid: true,
  showPins: true,
  userNotes: '',
  customPins: [],
  panZoom: { x: 0, y: 0, scale: 1 },
  notesSynced: false
};

// --- Toast system ---
const toastContainer = document.getElementById('toast-container');
function showToast(message, sub) {
  const el = document.createElement('div');
  el.className = 'toast-msg';
  el.innerHTML = `${message}${sub ? ' <span style="opacity:0.6">' + sub + '</span>' : ''}`;
  toastContainer.appendChild(el);
  setTimeout(() => {
    el.style.transition = 'opacity 300ms, transform 300ms';
    el.style.opacity = '0';
    el.style.transform = 'translateY(6px)';
    setTimeout(() => el.remove(), 320);
  }, 2600);
}

// --- Audio (subtle paper/click sounds) ---
let audioCtx = null;
function ensureAudio() {
  if (!audioCtx) {
    try {
      audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    } catch (e) { audioCtx = null; }
  }
  return audioCtx;
}
function playClick(freq = 2200, dur = 0.03, gain = 0.05) {
  const ctx = ensureAudio();
  if (!ctx) return;
  const osc = ctx.createOscillator();
  const g = ctx.createGain();
  osc.type = 'triangle';
  osc.frequency.value = freq;
  g.gain.setValueAtTime(gain, ctx.currentTime);
  g.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + dur);
  osc.connect(g).connect(ctx.destination);
  osc.start();
  osc.stop(ctx.currentTime + dur + 0.02);
}
function playChime() {
  const ctx = ensureAudio();
  if (!ctx) return;
  const freqs = [261.6, 392.0, 523.3];
  freqs.forEach((f, i) => {
    const osc = ctx.createOscillator();
    const g = ctx.createGain();
    osc.type = 'sine';
    osc.frequency.value = f;
    const t = ctx.currentTime + i * 0.07;
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(0.06, t + 0.02);
    g.gain.exponentialRampToValueAtTime(0.0001, t + 0.9);
    osc.connect(g).connect(ctx.destination);
    osc.start(t);
    osc.stop(t + 1.0);
  });
}

// --- localStorage persistence ---
const LS_KEY = 'atlas-state-v1';
function saveState() {
  try {
    localStorage.setItem(LS_KEY, JSON.stringify({
      bookmarked: state.bookmarkedPlates,
      notes: state.userNotes,
      pins: state.customPins,
      compare: [state.compareA, state.compareB],
      ink: state.inkMode
    }));
  } catch (e) {}
}
function loadState() {
  try {
    const raw = localStorage.getItem(LS_KEY);
    if (!raw) return;
    const s = JSON.parse(raw);
    if (s.bookmarked) state.bookmarkedPlates = s.bookmarked;
    if (s.notes) state.userNotes = s.notes;
    if (s.pins) state.customPins = s.pins;
    if (s.compare) { state.compareA = s.compare[0]; state.compareB = s.compare[1]; }
    if (s.ink) state.inkMode = s.ink;
  } catch (e) {}
}

// --- Plate SVG library ---
function getPlateSVG(key) {
  return SVG_BLUEPRINTS[key] || SVG_BLUEPRINTS['parthenon'];
}

// --- RENDER: Folio sidebar list ---
function renderFolioList() {
  const listEl = $('#plate-list');
  const search = state.plateSearch || '';
  const cats = {};
  PLATES.forEach(p => {
    if (search && !(p.title + p.subtitle + p.category + p.code).toLowerCase().includes(search.toLowerCase())) return;
    if (!cats[p.category]) cats[p.category] = [];
    cats[p.category].push(p);
  });
  let html = '';
  Object.keys(cats).sort().forEach(cat => {
    html += `<div class="plate-item-group-title">${cat}</div>`;
    cats[cat].forEach(p => {
      const active = p.id === state.activePlateId;
      const marked = state.bookmarkedPlates.includes(p.id);
      html += `
      <div class="plate-item ${active ? 'active' : ''}" data-plate="${p.id}" tabindex="0" role="button">
        <div class="plate-item-top">
          <span class="plate-item-code">${p.code}${marked ? ' ★' : ''}</span>
          <span class="plate-item-era">${p.era}</span>
        </div>
        <div class="plate-item-title">${p.title.split(':')[0]}</div>
        <div class="plate-item-desc">${p.subtitle.split('—')[0].trim()}</div>
      </div>`;
    });
  });
  if (!html) html = `<div style="padding:40px 20px;text-align:center;color:var(--ink-muted);font-family:var(--font-serif);font-style:italic;">No plates match the current search.</div>`;
  listEl.innerHTML = html;
  $$('.plate-item', listEl).forEach(el => {
    el.addEventListener('click', () => selectPlate(el.dataset.plate));
    el.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); selectPlate(el.dataset.plate); }});
  });
}

// --- RENDER: Plate canvas ---
function renderPlate() {
  const p = PLATES.find(x => x.id === state.activePlateId);
  if (!p) return;
  state.activePlate = p;
  $('#plate-code').textContent = p.code;
  $('#plate-title').textContent = p.title;
  $('#plate-subtitle').textContent = p.subtitle;
  $('#plate-dim').textContent = p.dimensions;
  $('#plate-modulus').textContent = p.modulus;
  $('#plate-material').textContent = p.material;
  $('#plate-era-badge').textContent = p.era;
  $('#plate-desc-full').textContent = p.description;

  // SVG inject
  const svgWrap = $('#plate-svg');
  svgWrap.innerHTML = getPlateSVG(p.svg_key);
  // Apply ink class
  const frame = $('#plate-frame');
  frame.className = `plate-frame ink-mode-${state.inkMode}`;

  // Datum pins
  const pinsWrap = $('#datum-pins');
  pinsWrap.innerHTML = '';
  if (state.showPins) {
    p.hotspots.forEach(h => {
      const pin = document.createElement('button');
      pin.className = 'datum-pin';
      pin.style.left = h.x + 'px';
      pin.style.top = h.y + 'px';
      pin.innerHTML = `<span class="pin-letter">◆</span>
        <div class="datum-tooltip">
          <strong>${h.label}</strong>
          ${h.desc}
        </div>`;
      pin.addEventListener('click', (e) => {
        e.stopPropagation();
        playClick(3200);
      });
      pinsWrap.appendChild(pin);
    });
    (state.customPins.filter(c => c.plateId === p.id) || []).forEach(c => {
      const pin = document.createElement('button');
      pin.className = 'datum-pin custom-pin';
      pin.style.left = c.x + 'px';
      pin.style.top = c.y + 'px';
      pin.innerHTML = `<span class="pin-letter">+</span>
        <div class="datum-tooltip"><strong>Datum Mark</strong>Custom researcher annotation at ${c.x.toFixed(0)}, ${c.y.toFixed(0)}</div>`;
      pin.addEventListener('click', (e) => {
        e.stopPropagation();
        playClick(2800);
      });
      pinsWrap.appendChild(pin);
    });
  }

  // Grid overlay
  const gridEl = $('#grid-overlay');
  if (state.showGrid) {
    gridEl.style.backgroundImage = 'linear-gradient(rgba(24,23,22,0.045) 1px, transparent 1px), linear-gradient(90deg, rgba(24,23,22,0.045) 1px, transparent 1px)';
    gridEl.style.backgroundSize = '28px 28px';
  } else {
    gridEl.style.backgroundImage = 'none';
  }

  // Bookmark button state
  const bbtn = $('#bookmark-btn');
  const isMarked = state.bookmarkedPlates.includes(p.id);
  bbtn.classList.toggle('active', isMarked);
  bbtn.innerHTML = isMarked ? '★ Bookmarked' : '☆ Bookmark Plate';

  renderFolioList();
}

function selectPlate(id) {
  state.activePlateId = id;
  state.panZoom = { x: 0, y: 0, scale: 1 };
  applyTransform();
  renderPlate();
  playClick(2400, 0.02, 0.03);
  showToast('PLATE LOADED', `Folio ${PLATES.find(x=>x.id===id).code}`);
}

// --- Pan & Zoom ---
function applyTransform() {
  const stage = $('#canvas-stage');
  if (stage) stage.style.transform = `translate(${state.panZoom.x}px, ${state.panZoom.y}px) scale(${state.panZoom.scale})`;
  const zl = $('#zoom-level-indicator');
  if (zl) zl.textContent = `×${state.panZoom.scale.toFixed(2)}`;
}

// --- Typology Matrix ---
function renderTypologies() {
  const f = state.typologyFilters;
  let items = TYPOLOGIES.filter(t => {
    if (f.era !== 'all' && t.era !== f.era) return false;
    if (f.system !== 'all' && t.system !== f.system) return false;
    if (f.search && !(t.name + t.archetype + t.desc).toLowerCase().includes(f.search.toLowerCase())) return false;
    return true;
  });
  const grid = $('#typology-grid');
  if (items.length === 0) {
    grid.innerHTML = `<div class="empty-state"><div class="empty-title">No typologies found</div><div class="empty-sub">Adjust era, system, or search to widen the net.</div></div>`;
    return;
  }
  grid.innerHTML = items.map(t => `
    <div class="typology-card" data-code="${t.code}" tabindex="0">
      <div class="typology-card-top">
        <span class="typology-code">${t.code}</span>
        <span class="typology-era">${t.era}</span>
      </div>
      <div class="typology-title">${t.name}</span>
      <div class="typology-archetype">${t.archetype}</div>
      <div class="typology-desc">${t.desc}</div>
      <div class="typology-metrics">
        <div class="typology-metric-item">SPAN <span>${t.span}</span></div>
        
        <div class="typology-metric-item">SYSTEM <span>${t.system}</span></div>
        <div class="typology-metric-item">EFFICIENCY <span>${t.efficiency}</span></div>
      </div>
    </div>`).join('');
  $$('.typology-card').forEach(el => {
    el.addEventListener('click', () => {
      openDrawer(el.dataset.code);
      playClick(2900);
    });
    el.addEventListener('keydown', (e) => { if (e.key === 'Enter') { openDrawer(el.dataset.code); }});
  });
}

// --- Materials view ---
function renderMaterials() {
  const grid = $('#materials-grid');
  grid.innerHTML = MATERIALS.map((m, i) => `
    <div class="material-card" tabindex="0" data-mat="${m.id}">
      <div class="material-swatch-box" style="${m.swatchStyle}"></div>
      <div class="mat-header">
        <span class="mat-code">MAT-${String(i+1).padStart(2,'0')}</span>
        <span class="mat-carbon ${m.carbon.includes('-') ? 'carbon-negative' : ''}">${m.carbon}</span>
      </div>
      <div class="mat-name">${m.name}</div>
      <div class="mat-origin serif">${m.origin}</div>
      <div class="mat-desc">${m.description}</div>
      <div class="mat-specs">
        <div><label>DENSITY</label><span>${m.density}</span></div>
        <div><label>STRENGTH</label><span>${m.compressive}</span></div>
        <div><label>LIFESPAN</label><span>${m.lifespan}</span></div>
      </div>
    </div>`).join('');
  $$('.material-card').forEach(el => {
    el.addEventListener('click', () => {
      openDrawer(null, el.dataset.mat);
      playClick(2600);
    });
  });
}

// --- Comparative view ---
function renderComparison() {
  const a = PLATES.find(x => x.id === state.compareA);
  const b = PLATES.find(x => x.id === state.compareB);
  $('#compare-a-name').textContent = a.title;
  $('#compare-b-name').textContent = b.title;
  $('#compare-a-code').textContent = a.code;
  $('#compare-b-code').textContent = b.code;
  $('#compare-svg-a').innerHTML = getPlateSVG(a.svg_key);
  $('#compare-svg-b').innerHTML = getPlateSVG(b.svg_key);
  $('#compare-svg-a').firstChild && $('#compare-svg-a').firstChild.setAttribute('viewBox', '60 20 680 400');
  $('#compare-svg-b').firstChild && $('#compare-svg-b').firstChild.setAttribute('viewBox', '60 20 680 400');
  const rows = [
    ['ERA', a.era, b.era],
    ['MATERIAL SYSTEM', a.material, b.material],
    ['MODULUS', a.modulus, b.modulus],
    ['DIMENSIONS', a.dimensions, b.dimensions]
  ];
  $('#compare-metrics').innerHTML = rows.map(r => `
    <tr>
      <td class="metric-name">${r[0]}</td>
      <td class="metric-val">${r[1]}</td>
      <td class="metric-val">${r[2]}</td>
    </tr>`).join('');

  // Synthesis text
  const yr = /(\d{3,4})/.exec(a.subtitle + b.subtitle);
  $('#compare-synthesis').innerHTML = `<strong>${a.title.split(':')[0]}</strong> and <strong>${b.title.split(':')[0]}</strong> represent divergent answers to the same structural problem: how to enclose volume with minimal material at maximum dignity. Where the first relies on ${a.material.split(',')[0].toLowerCase()} resolved through ${a.modulus.toLowerCase()}, the latter deploys ${b.material.split(',')[0].toLowerCase()} governed by ${b.modulus.toLowerCase()}. The caliper reveals that neither approach is superior; each is a local optimum of its era's material intelligence.`;
}

// --- Drawer ---
function openDrawer(typCode, matId) {
  const drawer = $('#inspector-drawer');
  const body = $('#drawer-body');
  if (typCode) {
    const t = TYPOLOGIES.find(x => x.code === typCode);
    body.innerHTML = `
      <div class="drawer-tag">TYPOLOGY MONOGRAPH</div>
      <h2 class="drawer-title">${t.name}</h2>
      <div class="drawer-sub">${t.archetype}</div>
      <div class="drawer-section">
        <div class="drawer-label">STRUCTURAL PRINCIPLE</div>
        <p>${t.desc}</p>
      </div>
      <div class="drawer-section">
        <div class="drawer-label">FULL LEDGER</div>
        <div class="drawer-table">
          <div><span>Era</span><b>${t.era}</b></div>
          <div><span>System</span><b>${t.system}</b></div>
          <div><span>Material</span><b>${t.material}</b></div>
          <div><span>Span Range</span><b>${t.span}</b></div>
          <div><span>Efficiency</span><b>${t.efficiency}</b></div>
        </div>
      </div>
      <div class="drawer-quote">"Architecture is the learned game, correct and magnificent, of forms assembled in the light."</div>
      <div class="drawer-quote-author">— Le Corbusier</div>`;
  } else if (matId) {
    const m = MATERIALS.find(x => x.id === matId);
    body.innerHTML = `
      <div class="drawer-tag">MATERIAL ASSAY</div>
      <h2 class="drawer-title">${m.name}</h2>
      <div class="drawer-sub">${m.origin}</div>
      <div class="drawer-section">
        <div class="drawer-label">TACTILITY</div>
        <p>${m.tactility}</p>
      </div>
      <div class="drawer-section">
        <div class="drawer-label">DESCRIPTION</div>
        <p>${m.description}</p>
      </div>
      <div class="drawer-section">
        <div class="drawer-label">FULL LEDGER</div>
        <div class="drawer-table">
          <div><span>Density</span><b>${m.density}</b></div>
          <div><span>Strength</span><b>${m.compressive}</b></div>
          <div><span>Carbon</span><b>${m.carbon}</b></div>
          <div><span>Lifespan</span><b>${m.lifespan}</span></div>
          <div><span>Formula</span><b>${m.formula}</b></div>
        </div>
      </div>`;
  }
  drawer.classList.add('open');
  playClick(1800, 0.04, 0.04);
}
function closeDrawer() {
  $('#inspector-drawer').classList.remove('open');
}

// --- Omni palette ---
const omniIndex = [];
function buildOmniIndex() {
  PLATES.forEach(p => omniIndex.push({ type: 'Plate', title: p.title, sub: p.code, action: () => { setView('folio'); setTimeout(()=>selectPlate(p.id), 50); } }));
  TYPOLOGIES.forEach(t => omniIndex.push({ type: 'Typology', title: t.name, sub: t.code, action: () => { setView('matrix'); setTimeout(()=>openDrawer(t.code), 50); } }));
  MATERIALS.forEach((m, i) => omniIndex.push({ type: 'Material', title: m.name, sub: `MAT-${String(i+1).padStart(2,'0')}`, action: () => { setView('materials'); setTimeout(()=>openDrawer(null, m.id), 50); } }));
  const views = [['folio', 'Folio Plates'], ['matrix', 'Typology Lexicon'], ['compare', 'Caliper Studio'], ['exegesis', 'Exegesis Journal'], ['materials', 'Material Assays']];
  views.forEach(v => omniIndex.push({ type: 'View', title: 'Go to ' + v[1], sub: 'Navigation', action: () => setView(v[0]) }));
  omniIndex.push({ type: 'Action', title: 'Toggle Proportional Caliper', sub: 'C', action: () => toggleCaliper() });
  omniIndex.push({ type: 'Folio', title: 'Open the Incunabula Atlas', sub: 'about:blank', action: () => {} });
}
let omniSelected = 0;
function openOmni() {
  $('#omni-backdrop').classList.add('open');
  const input = $('#omni-input');
  input.value = '';
  input.focus();
  renderOmni('');
  playClick(3400);
}
function closeOmni() {
  $('#omni-backdrop').classList.remove('open');
}
function renderOmni(query) {
  const list = $('#omni-results');
  const q = query.trim().toLowerCase();
  const results = (q ? omniIndex.filter(i => (i.title + i.sub).toLowerCase().includes(q)) : omniIndex).slice(0, 9);
  omniSelected = 0;
  if (results.length === 0) {
    list.innerHTML = `<div class="omni-empty">No results for "${query}"</div>`;
    return;
  }
  list.innerHTML = results.map((r, i) => `
    <div class="omni-item ${i === 0 ? 'selected' : ''}" data-idx="${omniIndex.indexOf(r)}">
      <div class="omni-item-left">
        <div class="omni-item-title">${r.title}</div>
        <div class="omni-item-sub">${r.sub}</div>
      </div>
      <span class="omni-item-badge">${r.type}</span>
    </div>`).join('');
  $$('.omni-item').forEach(el => {
    el.addEventListener('click', () => {
      const item = omniIndex[parseInt(el.dataset.idx)];
      closeOmni();
      item.action();
    });
  });
}

// --- Caliper ---
function toggleCaliper() {
  const w = $('#caliper-window');
  if (w.classList.contains('open')) {
    w.classList.remove('open');
  } else {
    w.classList.add('open');
    playChime();
  }
}

// --- View switching ---
const VIEW_NAMES = { folio: 'Folio Plates', matrix: 'Typology Lexicon', compare: 'Caliper Studio', exegesis: 'Exegesis Journal', materials: 'Material Assays' };
function setView(v) {
  state.view = v;
  $$('.view-pane').forEach(p => p.classList.remove('active'));
  $(`#view-${v}`).classList.add('active');
  $$('.nav-btn').forEach(b => b.classList.toggle('active', b.dataset.view === v));
  $('#view-title').textContent = VIEW_NAMES[v];
  $('#breadcrumb-view').textContent = VIEW_NAMES[v];
  playClick(2000, 0.025, 0.035);
  if (v === 'matrix') renderTypologies();
  if (v === 'materials') renderMaterials();
  if (v === 'compare') renderComparison();
}

// --- Clock ---
function tickClock() {
  const now = new Date();
  const months = ['IAN', 'FEB', 'MAR', 'APR', 'MAI', 'IUN', 'IUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC'];
  $('#clock-date').textContent = `${now.getDate()} ${months[now.getMonth()]} ${now.getFullYear()}`;
  const roman = toRoman(now.getHours()) + ':' + String(now.getMinutes()).padStart(2, '0');
  $('#clock-time').textContent = roman;
}
function toRoman(n) {
  if (n === 0) return 'N';
  const map = [[10,'X'],[9,'IX'],[5,'V'],[4,'IV'],[1,'I']];
  let out = '';
  map.forEach(([val, sym]) => { while (n >= val) { out += sym; n -= val; } });
  return out;
}

// --- INIT ---
function init() {
  loadState();
  buildOmniIndex();
  renderFolioList();
  renderPlate();
  renderTypologies();
  renderMaterials();
  renderComparison();
  tickClock();
  setInterval(tickClock, 30000);

  // Nav buttons
  $$('.nav-btn').forEach(b => b.addEventListener('click', () => setView(b.dataset.view)));

  // Plate search
  $('#folio-search').addEventListener('input', (e) => { state.plateSearch = e.target.value; renderFolioList(); });

  // Bookmark
  $('#bookmark-btn').addEventListener('click', () => {
    const id = state.activePlateId;
    const idx = state.bookmarkedPlates.indexOf(id);
    if (idx >= 0) { state.bookmarkedPlates.splice(idx, 1); showToast('BOOKMARK REMOVED'); }
    else { state.bookmarkedPlates.push(id); showToast('PLATE BOOKMARKED', 'Saved to working folio'); }
    saveState();
    renderPlate();
  });

  // Toolbars
  $$('.tool-btn[data-ink]').forEach(b => b.addEventListener('click', () => {
    state.inkMode = b.dataset.ink;
    $$('.tool-btn[data-ink]').forEach(x => x.classList.toggle('active', x === b));
    renderPlate();
    showToast('INK SCHEME', b.dataset.ink.toUpperCase());
  }));
  $('#grid-toggle').addEventListener('click', (e) => {
    state.showGrid = !state.showGrid;
    e.currentTarget.classList.toggle('active', state.showGrid);
    renderPlate();
  });
  $('#pin-toggle').addEventListener('click', (e) => {
    state.showPins = !state.showPins;
    e.currentTarget.classList.toggle('active', state.showPins);
    renderPlate();
  });

  // Zoom controls
  $('#zoom-in').addEventListener('click', () => { state.panZoom.scale = Math.min(3, state.panZoom.scale * 1.25); applyTransform(); playClick(2500); });
  $('#zoom-out').addEventListener('click', () => { state.panZoom.scale = Math.max(0.4, state.panZoom.scale / 1.25); applyTransform(); playClick(2100); });
  $('#zoom-reset').addEventListener('click', () => { state.panZoom = { x: 0, y: 0, scale: 1 }; applyTransform(); showToast('VIEW RESET'); });

  // Pan (mouse drag)
  const viewport = $('#canvas-viewport');
  let isDragging = false, dragStart = { x: 0, y: 0 }, panStart = { x: 0, y: 0 };
  viewport.addEventListener('mousedown', (e) => {
    if (e.target.closest('.datum-pin') || e.target.closest('.canvas-floating-controls')) return;
    isDragging = true;
    dragStart = { x: e.clientX, y: e.clientY };
    panStart = { ...state.panZoom };
    viewport.classList.add('dragging');
  });
  window.addEventListener('mousemove', (e) => {
    if (!isDragging) return;
    state.panZoom.x = panStart.x + (e.clientX - dragStart.x);
    state.panZoom.y = panStart.y + (e.clientY - dragStart.y);
    applyTransform();
  });
  window.addEventListener('mouseup', () => { isDragging = false; viewport.classList.remove('dragging'); });

  // Alt+Click to drop custom datum
  viewport.addEventListener('click', (e) => {
    if (!e.altKey) return;
    const rect = viewport.getBoundingClientRect();
    const stageRect = $('#plate-frame').getBoundingClientRect();
    const x = ((e.clientX - stageRect.left) / stageRect.width) * 900;
    const y = ((e.clientY - stageRect.top) / stageRect.height) * 660;
    state.customPins.push({ plateId: state.activePlateId, x: x * (900 / stageRect.width), y: y * (660 / stageRect.height) });
    saveState();
    renderPlate();
    playClick(3600);
    showToast('DATUM PLACED', `x:${Math.round(x)} y:${Math.round(y)}`);
  });

  // Typology filters
  $('#filter-era').addEventListener('change', e => { state.typologyFilters.era = e.target.value; renderTypologies(); });
  $('#filter-system').addEventListener('change', e => { state.typologyFilters.system = e.target.value; renderTypologies(); });
  $('#filter-search').addEventListener('input', e => { state.typologyFilters.search = e.target.value; renderTypologies(); });

  // Compare selects
  $('#compare-select-a').addEventListener('change', e => { state.compareA = e.target.value; renderComparison(); playClick(2300); });
  $('#compare-select-b').addEventListener('change', e => { state.compareB = e.target.value; renderComparison(); playClick(2300); });

  // Notes
  const notesEl = $('#notes-textarea');
  notesEl.value = state.userNotes;
  notesEl.addEventListener('input', () => {
    state.userNotes = notesEl.value;
    saveState();
    $('#notes-status').textContent = 'Saved';
    setTimeout(() => { $('#notes-status').textContent = 'Autosaved'; }, 800);
  });

  // Drawer
  $('#drawer-close').addEventListener('click', closeDrawer);

  // Omni
  $('#omni-backdrop').addEventListener('click', (e) => { if (e.target.id === 'omni-backdrop') closeOmni(); });
  $('#omni-input').addEventListener('input', (e) => renderOmni(e.target.value));
  $('#omni-input').addEventListener('keydown', (e) => {
    const items = $$('.omni-item');
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      omniSelected = Math.min(items.length - 1, omniSelected + 1);
      items.forEach((it, i) => it.classList.toggle('selected', i === omniSelected));
      items[omniSelected].scrollIntoView({ block: 'nearest' });
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      omniSelected = Math.max(0, omniSelected - 1);
      items.forEach((it, i) => it.classList.toggle('selected', i === omniSelected));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      const sel = items[omniSelected];
      if (sel) { const item = omniIndex[parseInt(sel.dataset.idx)]; closeOmni(); item.action(); }
    }
  });
  $('#cmd-k-btn').addEventListener('click', openOmni);

  // Caliper
  $('#caliper-toggle-btn').addEventListener('click', toggleCaliper);
  $('#caliper-close').addEventListener('click', toggleCaliper);

  // View switching keyboard shortcuts
  window.addEventListener('keydown', (e) => {
    if (e.metaKey || e.ctrlKey) {
      if (e.key === 'k' || e.key === 'K') { e.preventDefault(); openOmni(); }
      return;
    }
    const tag = (e.target.tagName || '').toLowerCase();
    if (tag === 'input' || tag === 'textarea' || tag === 'select') return;
    if (e.key === '1') setView('folio');
    else if (e.key === '2') setView('matrix');
    else if (e.key === '3') setView('compare');
    else if (e.key === '4') setView('exegesis');
    else if (e.key === '5') setView('materials');
    else if (e.key === 'c' || e.key === 'C') toggleCaliper();
    else if (e.key === 'Escape') { closeDrawer(); closeOmni(); }
  });

  // Export SVG
  $('#export-btn').addEventListener('click', () => {
    const svg = $('#plate-svg').innerHTML;
    const blob = new Blob([svg], { type: 'image/svg+xml' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${state.activePlate.code.replace(/[^\w-]/g, '_')}.svg`;
    a.click();
    URL.revokeObjectURL(url);
    showToast('PLATE EXPORTED', 'Vector SVG');
  });

  // Caliper slider live readout
  const caliperSlider = $('#caliper-range');
  caliperSlider.addEventListener('input', () => {
    const v = parseFloat(caliperSlider.value);
    const phi = 1.6180339887;
    const ratio = (v / phi).toFixed(3);
    $('#caliper-readout-main').textContent = v.toFixed(3);
    $('#caliper-ratio-val').textContent = `1 : ${ratio}`;
    const deviation = Math.abs(v - phi) / phi * 100;
    const badge = $('#caliper-ratio-badge');
    if (deviation < 1.5) { badge.textContent = 'φ CONGRUENT'; badge.className = 'caliper-ratio-badge congruent'; playChime(); }
    else if (deviation < 8) { badge.textContent = 'NEAR-HARMONIC'; badge.className = 'caliper-ratio-badge near'; }
    else { badge.textContent = 'DISSONANT'; badge.className = 'caliper-ratio-badge dissonant'; }
  });

  // Draggable caliper window
  const caliperWin = $('#caliper-window');
  const caliperHeader = $('#caliper-header');
  let cx = 0, cy = 0, cw = false;
  caliperHeader.addEventListener('mousedown', (e) => {
    cw = true;
    const rect = caliperWin.getBoundingClientRect();
    cx = e.clientX - rect.left;
    cy = e.clientY - rect.top;
    e.preventDefault();
  });
  window.addEventListener('mousemove', (e) => {
    if (!cw) return;
    caliperWin.style.left = (e.clientX - cx) + 'px';
    caliperWin.style.top = (e.clientY - cy) + 'px';
    caliperWin.style.bottom = 'auto';
  });
  window.addEventListener('mouseup', () => { cw = false; });

  // Print
  $('#print-btn').addEventListener('click', () => { showToast('COMPILING FOLIO', 'Preparing print');
    setTimeout(() => window.print(), 400);
  });

  console.log('ATLAS initialized.');
}

document.addEventListener('DOMContentLoaded', init);

'''

print('app_js.py ready.')
