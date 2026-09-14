html_template = r'''
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ATLAS — The Architectural &amp; Cultural Cartography System</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Cinzel:wght@400;500;600;700;900&family=JetBrains+Mono:ital,wght@0,300;0,400;0,500;0,700;1,400&family=Newsreader:ital,opsz,wght@0,6..72,300;0,6..72,400;0,6..72,500;0,6..72,600;1,6..72,300;1,6..72,400;1,6..72,600&family=Plus+Jakarta+Sans:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>
__CSS__
</style>
</head>
<body>
<!-- ================= MASTHEAD ================= -->
<header class="masthead">
  <div class="masthead-top">
    <div class="masthead-top-left">
      <span class="masthead-badge sanguine"><span class="pulse-dot"></span> PLATE XIV ACTIVE</span>
      <span class="masthead-badge">EPOCH: 438 BCE — 1972 CE</span>
      <span class="masthead-badge">COORD: 41.8902° N, 12.4922° E</span>
    </div>
    <div class="masthead-top-right">
      <span class="masthead-badge" id="clock-date">— — ——</span>
      <span class="masthead-badge" id="clock-time">—:—</span>
    </div>
  </div>
  <div class="masthead-main">
    <div class="brand-section" id="brand-home">
      <div class="brand-title">ATLAS</div>
      <div class="brand-subtitle">The Architectural &amp; Cultural Cartography System</div>
    </div>
    <nav class="view-nav" aria-label="Primary views">
      <button class="nav-btn active" data-view="folio"><span class="nav-ico">▲</span> Folio Plates <span class="key-hint">1</span></button>
      <button class="nav-btn" data-view="matrix"><span class="nav-ico">◈</span> Typology Lexicon <span class="key-hint">2</Other-hint></button>
      <button class="nav-btn" data-view="compare"><span class="nav-ico">⇔</span> Caliper Studio <span class="key-hint">3</span></button>
      <button class="nav-btn" data-view="exegesis"><span class="nav-ico">❦</span> Exegesis <span class="key-hint">4</span></button>
      <button class="nav-btn" data-view="materials"><span class="nav-ico">▤</span> Material Assays <span class="key-hint">5</span></button>
    </nav>
    <div class="masthead-actions">
      <button class="action-btn" id="caliper-toggle-btn" title="Toggle Proportional Caliper (C)">⌖ Caliper</button>
      <button class="action-btn" id="cmd-k-btn" title="Command Palette (Ctrl+K)">⌘ Search</button>
      <button class="action-btn icon-only" id="print-btn" title="Compile Folio (Print)">⎙</button>
    </div>
  </div>
</header>

<div class="app-container">
  <!-- VIEW 1: FOLIO -->
  <section class="view-pane active" id="view-folio">
    <div class="folio-layout">
      <aside class="folio-sidebar">
        <div class="folio-sidebar-header">
          <div class="folio-sidebar-title">PLATE REGISTER</div>
          <div class="folio-sidebar-sub">Twelve architectural studies spanning 2,400 years</div>
        </div>
        <div class="folio-search-wrap">
          <input id="folio-search" class="folio-search-input" type="text" placeholder="Search plates, folios, keywords…" />
        </div>
        <div class="folio-plate-list" id="plate-list"></div>
      </aside>
      <main class="folio-main">
        <div class="canvas-toolbar">
          <div class="toolbar-group">
            <span class="toolbar-label">VIEW</span>
            <button class="tool-btn active" data-canvas="fit">FIT</button>
            <button class="tool-btn" data-canvas="1:1">1:1</button>
            <button class="tool-btn" data-canvas="detail">DETAIL</button>
          </div>
          <div class="toolbar-group">
            <span class="toolbar-label">OVERLAYS</span>
            <button class="tool-btn active" id="grid-toggle">GRID</button>
            <button class="tool-btn active" id="pin-toggle">PINS</button>
            <button class="tool-btn" data-canvas="hatch">HATCH</button>
          </div>
          <div class="toolbar-group">
            <span class="toolbar-label">INK</span>
            <button class="tool-btn active" data-ink="bone"><span class="ink-dot ink-bone"></span> Bone Black</button>
            <button class="tool-btn" data-ink="sanguine"><span class="ink-dot ink-sanguine"></span> Sanguine</button>
            <button class="tool-btn" data-ink="sepia"><span class="ink-dot ink-sepia"></span> Iron Gall</button>
            <button class="tool-btn" data-ink="cyanotype"><span class="ink-dot ink-cyanotype"></span> Cyanotype</button>
          </div>
          <div class="toolbar-group">
            <button class="action-btn" id="bookmark-btn">☆ Bookmark Plate</button>
            <button class="action-btn" id="export-btn">↓ Export SVG</button>
          </div>
        </div>
        <div class="canvas-viewport" id="canvas-viewport">
          <div class="canvas-stage" id="canvas-stage">
            <article class="plate-frame" id="plate-frame">
              <div class="plate-header">
                <div class="plate-title-group">
                  <h2 id="plate-title">—</h2>
                  <p id="plate-subtitle">—</p>
                </div>
                <div class="plate-meta-group">
                  <div id="plate-code">PL. —</div>
                  <div id="plate-era-badge" class="era-badge">—</div>
                </div>
              </div>
              <div class="plate-svg-container">
                <div class="plate-svg" id="plate-svg" style="width:100%;height:100%"></div>
                <div class="grid-overlay" id="grid-overlay"></div>
                <div class="datum-pins" id="datum-pins"></div>
              </div>
              <div class="plate-footer">
                <div class="plate-footer-left">
                  <span id="plate-dim">—</span>
                  <span id="plate-modulus">—</span>
                  <span id="plate-material">—</span>
                </div>
              </div>
              <div class="plate-desc-row" id="plate-desc-full">—</div>
            </article>
          </div>
          <div class="canvas-floating-controls">
            <button class="floating-btn" id="zoom-out">−</button>
            <span class="zoom-indicator" id="zoom-level-indicator">×1.00</span>
            <button class="floating-btn" id="zoom-in">+</button>
            <button class="floating-btn" id="zoom-reset">⌂</button>
          </div>
        </div>
      </main>
    </div>
  </section>

  <!-- VIEW 2: MATRIX -->
  <section class="view-pane" id="view-matrix">
    <div class="matrix-container">
      <header class="matrix-header">
        <div class="matrix-title">
          <h1>Lexicon of Structural Typologies</h1>
          <p>A synoptic catalogue of load-bearing intelligences across six millennia.</p>
        </div>
        <div class="matrix-meta mono">12 ENTRIES · 5 ERAS · 4 MATERIAL CLASSES</div>
      </header>
      <div class="filter-bar">
        <div class="filter-group">
          <label class="filter-label">ERA</label>
          <select class="filter-select" id="filter-era">
            <option value="all">All Eras</option>
            <option>Classical Antiquity</option>
            <option>Byzantine / Renaissance</option>
            <option>High Gothic</option>
            <option>Modern / Catalan</option>
            <option>Modernist Rationalism</option>
            <option>Mid-Century Modern</option>
            <option>Contemporary High-Tech</option>
            <option>Islamic Golden Age</option>
            <option>Edo Period</option>
            <option>Roman Baroque</option>
            <option>Late Modernist</option>
            <option>Industrial / Modern</option>
            <option>Roman Empire</option>
            <option>High Renaissance</option>
          </select>
        </div>
        <div class="filter-group">
          <label class="filter-label">SYSTEM</label>
          <select class="filter-select" id="filter-system">
            <option value="all">All Systems</option>
            <option>Post &amp; Lintel</option>
            <option>Curved Shell</option>
            <option>Compressive Thrust</option>
            <option>Pure Compression</option>
            <option>Membrane Shear</option>
            <option>Point-Load Frame</option>
            <option>Pre-stressed Shell</option>
            <option>Spatial Truss</option>
            <option>Corbelled Squinch</option>
            <option>Peristyle Colonnade</option>
            <option>Tension-Compression Pair</option>
            <option>3D Space Frame</option>
          </select>
        </div>
        <input class="filter-search-input" id="filter-search" placeholder="Filter by name, archetype, principle…" />
      </div>
      <div class="matrix-grid" id="typology-grid"></div>
    </div>
  </section>

  <!-- VIEW 3: COMPARE -->
  <section class="view-pane" id="view-compare">
    <div class="comparative-container">
      <header class="matrix-header">
        <div class="matrix-title">
          <h1>Comparative Caliper Studio</h1>
          <p>Juxtapose any two plates to expose the structural dialectic.</p>
        </div>
        <div class="matrix-meta mono">SYNCED CALIPERS · Δ-RATIO ENGINE</div>
      </header>
      <div class="comparative-grid">
        <div class="compare-card">
          <div class="compare-select-wrap">
            <select class="compare-select" id="compare-select-a"></select>
          </div>
          <div class="compare-drawing-box" id="compare-svg-a"></div>
          <div class="compare-meta-row">
            <span class="compare-code mono" id="compare-a-code">—</span>
          </div>
        </div>
        <div class="compare-card">
          <div class="compare-select-wrap">
            <select class="compare-select" id="compare-select-b"></select>
          </div>
          <div class="compare-drawing-box" id="compare-svg-b"></div>
          <div class="compare-meta-row">
            <span class="compare-code mono" id="compare-b-code">—</span>
          </div>
        </div>
      </div>
      <div class="comparative-metrics-wrap">
        <table class="ledger-table" id="compare-metrics"></table>
      </div>
      <div class="comparative-dialectic-summary">
        <div class="comparative-dialectic-title">SYNTHESIS — THE STRUCTURAL DIALECTIC</div>
        <div class="comparative-dialectic-text" id="compare-synthesis">—</div>
      </div>
    </div>
  </section>

  <!-- VIEW 4: EXEGESIS -->
  <section class="view-pane" id="view-exegesis">
    <div class="exegesis-layout">
      <aside class="exegesis-toc">
        <div class="toc-title">CONTENTS</div>
        <a class="toc-link active" href="#sec-1">I. — Proportion as Natural Law</a>
        <a class="toc-link" href="#sec-2">II. — The Vitruvian Triad</a>
        <a class="toc-link" href="#sec-3">III. — Light as Structural Material</a>
        <a class="toc-link" href="#sec-4">IV. — Tectonic Truth &amp; Honesty</a>
        <a class="toc-link" href="#sec-5">V. — Synthesis: The ATLAS Method</a>
      </aside>
      <article class="exegesis-article">
        <header class="article-header">
          <div class="article-category">DISSERTATION · FOLIO IV</div>
          <h1 class="article-title">On Proportion, Gravity, and Light: An Exegesis of the Architectural Mind</h1>
          <div class="article-author">Compiled by the ATLAS Commission, Office of the Surveyor-General · MMXXIV</div>
        </header>
        <div class="article-body">
          <p class="lead">Architecture is not about space, but about the <em>inhabitation of time</em>. Every building is a bet placed against gravity, and every proportion is a wager that the human eye will find resonance in the intervals we choose.</p>
          <p id="sec-1">Long before the drawing board, proportion governed the world. Phyllotaxis in sunflowers, the nautilus shell, the branching of rivers — all adhere to the golden section with an insistence that borders on the theological. When Iktinos set out the stylobate of the Parthenon at a 4:9 ratio — column diameter to interaxial spacing, facade to flank — he was not decorating. He was aligning a man-made object with the deep mathematics of the natural world, ensuring the temple would feel <em>inevitable</em> rather than designed.</p>
          <div class="article-interactive-widget" id="widget-phi">
            <div class="widget-title">INTERACTIVE FIGURE — THE GOLDEN RECTANGLE CONSTRUCTION</div>
            <svg viewBox="0 0 800 300" class="widget-svg">
              <rect x="40" y="60" width="323.6" height="200" fill="none" stroke="var(--stroke-color, #181716)" stroke-width="1.5"/>
              <rect x="40" y="60" width="123.6" height="200" fill="rgba(184,59,38,0.05)" stroke="var(--stroke-color, #181716)" stroke-width="1"/>
              <rect x="163.6" y="60" width="200" height="123.6" fill="none" stroke="var(--stroke-color, #181716)" stroke-width="1"/>
              <path d="M 40,60 A 50,50 0 0,1 90,110" fill="none" stroke="var(--accent-color, #B83B26)" stroke-width="1.5"/>
              <circle cx="65" cy="85" r="1.5" fill="var(--accent-color, #B83B26)"/>
              <text x="50" y="50" font-family="'JetBrains Mono', monospace" font-size="10" fill="var(--ink-tertiary)">1</text>
              <text x="190" y="50" font-family="'JetBrains Mono', monospace" font-size="10" fill="var(--ink-tertiary)">φ − 1 = 0.618…</text>
              <text x="700" y="50" font-family="'JetBrains Mono', monospace" font-size="10" fill="var(--ink-tertiary)">φ = 1.618…</text>
              <text x="70" y="280" font-family="'JetBrains Mono', monospace" font-size="10" fill="var(--accent-color, #B83B26)">QUARTER-ARC SUBDIVISION</text>
              <text x="330" y="280" font-family="'JetBrains Mono', monospace" font-size="10" fill="var(--ink-tertiary)">LOGARITHMIC SPIRAL APPROXIMATION</text>
            </svg>
          </div>
          <p id="sec-2">Vitruvius, writing in the first century BCE, codified the triad — <strong>firmitas, utilitas, venustas</strong>: strength, utility, beauty. Yet the triad is not a checklist but a tension. The Pantheon resolves it: a 43.3-meter sphere of pozzolanic concrete where structure <em>is</em> the aesthetic, where the oculus is both the primary compression ring and the sole ornament. Nothing is added; everything works.</p>
          <p id="sec-3">Kahn's cycloid vaults at Fort Worth extend this logic into the modern century. The vault is a "shell-beam" carrying its own thrust; the light that enters through the slot at the crown is redirected by a curved aluminum reflector so that no painting is ever struck by direct sun. The result is silver light — the most flattering light in the history of art display — and it arrives through a structural necessity: the slot exists because the vault requires it.</p>
          <div class="article-interactive-widget">
            <div class="widget-title">INTERACTIVE FIGURE — SPAN-TO-DEPTH ACROSS HISTORY</div>
            <svg viewBox="0 0 800 260" class="widget-svg">
              <line x1="60" y1="220" x2="740" y2="220" stroke="var(--stroke-color, #181716)" stroke-width="1.5"/>
              <line x1="60" y1="30" x2="60" y2="220" stroke="var(--stroke-color, #181716)" stroke-width="1.5"/>
              <polyline points="60,210 110,195 170,180 240,160 320,130 410,95 500,70 590,50 740,25" fill="none" stroke="var(--accent-color, #B83B26)" stroke-width="1.8"/>
              <circle cx="110" cy="195" r="4" fill="#fff" stroke="var(--stroke-color, #181716)" stroke-width="1"/>
              <circle cx="240" cy="160" r="4" fill="#fff" stroke="var(--stroke-colo, #181716)" stroke-width="1"/>
              <circle cx="410" cy="95" r="4" fill="#fff" stroke="var(--stroke-color, #181716)" stroke-width="1"/>
              <circle cx="590" cy="50" r="4" fill="#fff" stroke="var(--stroke-color, #181716)" stroke-key-hint2="1"/>
              <text x="80" y="205" font-family="'JetBrains Mono', monospace" font-size="9" fill="var(--ink-tertiary)">HYPPOSTYLE 3.5m</text>
              <text x="250" y="150" font-family="'JetBrains Mono', monospace" font-size="9" fill="var(--ink-tertiary)">GOTHIC NAVE 12m</text>
              <text x="420" y="85" font-family="'JetBrains Mono', monospace" font-size="9" fill="var(--ink-tertiary)">PANTHEON 43m</text>
              <text x="600" y="45" font-family="'JetBrains Mono', monospace" font-size="9" fill="var(--ink-tertiary)">GEODESIC 120m</text>
            </svg>
          </div>
          <p id="sec-4">Ruskin demanded "truth" in materials: no hidden iron, no pretend marble. The Gothic masters achieved honesty through necessity — the flying buttress <em>must</em> be outside because the thrust must go somewhere. Modernity's sin was not the machine but the lie: stucco pretending to be stone, drop ceilings concealing ducts. The best of the modern — Katsura's exposed hinoki frame, Corbusier's pilotis declared plainly — returns to the Gothic condition where every element earns its visibility.</p>
          <p id="sec-5">ATLAS is a method, not a museum. The caliper does not judge; it measures. When two plates are juxtaposed, the instrument reveals not which is superior but <em>which problem each is solving</em>. The Parthenon answers the problem of perception; the Pantheon answers the problem of enclosure; Savoye answers the problem of the machine; Katsura answers the problem of impermanence. Together they form a grammar — and this journal is its syntax.</p>
        </div>
      </article>
      <aside class="marginalia-sidebar">
        <div class="marginalia-box">
          <strong>MARGIN NOTE 14b</strong>
          The 4:9 ratio recurs: stylobate plan, column spacing, facade width. Nine is four squared... no, twice four plus one. The Pythagorean tetractys: 1+2+3+4 = 10. Sacred.
        </div>
        <div class="marginalia-box">
          <strong>MARGIN NOTE 27a</strong>
          <em>Kahn's reflector</em> is the most overlooked element in 20th c. architecture. A bent piece of aluminum, yet it decides the entire section.
        </div>
        <div class="notes-block">
          <div class="widget-title" style="margin-top:24px">RESEARCHER NOTES</div>
          <textarea class="user-notes-textarea" id="notes-textarea" placeholder="Your annotations are saved locally to this device…"></textarea>
          <div class="notes-status-row"><span class="mono" id="notes-status">Autosaved</span></div>
        </div>
      </aside>
    </div>
  </section>

  <!-- VIEW 5: MATERIALS -->
  <section class="view-pane" id="view-materials">
    <div class="materials-container">
      <header class="matrix-header">
        <div class="matrix-title">
          <h1>Tectonic Material Assays</h1>
          <p>Six substances, six temperaments: from volcanic ash to sequestered timber.</p>
        </div>
        <div class="matrix-meta mono">6 ASSAYS · DENSITY / STRENGTH / CARBON</div>
      </header>
      <div class="materials-grid" id="materials-grid"></div>
    </div>
  </section>
</div>

<!-- ============ INSPECTOR DRAWER ============ -->
<aside class="inspector-drawer" id="inspector-drawer" aria-hidden="true">
  <div class="drawer-header">
    <span class="drawer-header-title mono">INSPECTOR · MONOGRAPH</span>
    <button class="drawer-close" id="drawer-close" aria-label="Close inspector">✕ Close</button>
  </div>
  <div class="drawer-body" id="drawer-body"></div>
</aside>

<!-- ============ CALIPER TOOL ============ -->
<div class="caliper-tool-window" id="caliper-window">
  <div class="caliper-tool-header" id="caliper-header">
    <span>⌖ PROPORTIONAL CALIPER</span>
    <button class="caliper-close" id="caliper-close" aria-label="Close caliper">✕</button>
  </div>
  <div class="caliper-tool-body">
    <div class="caliper-readout">
      <span class="caliper-readout-main" id="caliper-readout-main">1.618</span>
      <span class="caliper-ratio-badge congruent" id="caliper-ratio-badge">φ CONGRUENT</span>
    </div>
    <div class="caliper-ratio-line mono" id="caliper-ratio-val">1 : 1.000</div>
    <div class="caliper-slider-wrap">
      <label><span>MODULE A</span><span>MODULE B</span></label>
      <input type="range" id="caliper-range" class="caliper-range" min="0.5" max="3" step="0.001" value="1.618" />
    </div>
    <div class="caliper-scale mono">
      <div class="caliper-scale-row"><span>PERFECT FIFTH</span><span>1.500</span></div>
      <div class="caliper-scale-row"><span>GOLDEN φ</span><span>1.618</span></div>
      <div class="caliper-scale-row"><span>MINOR 6th</span><span>1.600</span></div>
    </div>
  </div>
</div>

<!-- ============ OMNI PALETTE ============ -->
<div class="omni-modal-backdrop" id="omni-backdrop">
  <div class="omni-dialog" role="dialog" aria-modal="true">
    <div class="omni-input-row">
      <span class="omni-icon">⌕</span>
      <input class="omni-input" id="omni-input" placeholder="Search plates, typologies, materials, actions…" autocomplete="off" />
      <span class="omni-kbd mono">ESC</span>
    </div>
    <div class="omni-results-list" id="omni-results"></div>
    <div class="omni-footer">
      <span class="mono">↑↓ navigate</span>
      <span class="mono">↵ select</span>
      <span class="mono">ESC dismiss</span>
    </div>
  </div>
</div>

<div class="toast-container" id="toast-container"></div>

<script>
__JS_DATA__
__JS__
</script>
</body>
</html>

'''

print('html_template.py ready.')
