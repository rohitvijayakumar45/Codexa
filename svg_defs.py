# Full generator for index.html
import json

with open("styles.css", "r", encoding="utf-8") as f:
    css_content = f.read()

# Let's define the SVG blueprints
svg_parthenon = """<svg viewBox="0 0 800 450" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <pattern id="hatch-diag" width="8" height="8" patternTransform="rotate(45 0 0)" patternUnits="userSpaceOnUse">
      <line x1="0" y1="0" x2="0" y2="8" stroke="var(--stroke-color, #181716)" stroke-width="0.6" stroke-opacity="0.25"/>
    </pattern>
  </defs>
  <!-- Background subtle grid -->
  <line x1="40" y1="400" x2="760" y2="400" stroke="var(--stroke-color, #181716)" stroke-width="1.5" />
  <line x1="40" y1="410" x2="760" y2="410" stroke="var(--stroke-color, #181716)" stroke-width="0.8" />
  <line x1="40" y1="420" x2="760" y2="420" stroke="var(--stroke-color, #181716)" stroke-width="0.5" />
  
  <!-- Crepidoma / Stylobate with slight optical convex curvature -->
  <path d="M 50,400 Q 400,396 750,400 L 750,420 L 50,420 Z" fill="var(--fill-subtle, rgba(24,23,22,0.03))" stroke="var(--stroke-color, #181716)" stroke-width="1" />
  <path d="M 70,388 Q 400,384 730,388 L 730,400 L 70,400 Z" fill="var(--fill-subtle, rgba(24,23,22,0.03))" stroke="var(--stroke-color, #181716)" stroke-width="1" />
  
  <!-- 8 Doric Columns with slight entasis and inward inclination -->
  <!-- Col 1 -->
  <path d="M 85,388 L 96,170 L 126,170 L 137,388 Z" fill="none" stroke="var(--stroke-color, #181716)" stroke-width="1.2"/>
  <line x1="93" y1="388" x2="101" y2="170" stroke="var(--stroke-color, #181716)" stroke-width="0.5" stroke-dasharray="2,2"/>
  <line x1="107" y1="388" x2="111" y2="170" stroke="var(--stroke-color, #181716)" stroke-width="0.5"/>
  <line x1="121" y1="388" x2="121" y2="170" stroke="var(--stroke-color, #181716)" stroke-width="0.5"/>
  <line x1="129" y1="388" x2="123" y2="170" stroke="var(--stroke-color, #181716)" stroke-width="0.5" stroke-dasharray="2,2"/>
  <!-- Capital 1 -->
  <polygon points="90,170 132,170 138,158 84,158" fill="var(--fill-subtle, rgba(24,23,22,0.03))" stroke="var(--stroke-color, #181716)" stroke-width="1"/>
  <rect x="80" y="148" width="62" height="10" fill="var(--fill-subtle, rgba(24,23,22,0.03))" stroke="var(--stroke-color, #181716)" stroke-width="1"/>

  <!-- Col 2 -->
  <path d="M 165,388 L 174,170 L 204,170 L 213,388 Z" fill="none" stroke="var(--stroke-color, #181716)" stroke-width="1.2"/>
  <!-- Capital 2 -->
  <polygon points="168,170 210,170 216,158 162,158" fill="none" stroke="var(--stroke-color, #181716)" stroke-width="1"/>
  <rect x="158" y="148" width="62" height="10" fill="none" stroke="var(--stroke-color, #181716)" stroke-width="1"/>

  <!-- Col 3 -->
  <path d="M 245,388 L 253,170 L 283,170 L 291,388 Z" fill="none" stroke="var(--stroke-color, #181716)" stroke-width="1.2"/>
  <polygon points="247,170 289,170 295,158 241,158" fill="none" stroke="var(--stroke-color, #181716)" stroke-width="1"/>
  <rect x="237" y="148" width="62" height="10" fill="none" stroke="var(--stroke-color, #181716)" stroke-width="1"/>

  <!-- Col 4 -->
  <path d="M 325,388 L 332,170 L 362,170 L 369,388 Z" fill="none" stroke="var(--stroke-color, #181716)" stroke-width="1.2"/>
  <polygon points="326,170 368,170 374,158 320,158" fill="none" stroke="var(--stroke-color, #181716)" stroke-width="1"/>
  <rect x="316" y="148" width="62" height="10" fill="none" stroke="var(--stroke-color, #181716)" stroke-width="1"/>

  <!-- Col 5 -->
  <path d="M 431,388 L 438,170 L 468,170 L 475,388 Z" fill="none" stroke="var(--stroke-color, #181716)" stroke-width="1.2"/>
  <polygon points="432,170 474,170 480,158 426,158" fill="none" stroke="var(--stroke-color, #181716)" stroke-width="1"/>
  <rect x="422" y="148" width="62" height="10" fill="none" stroke="var(--stroke-color, #181716)" stroke-width="1"/>

  <!-- Col 6 -->
  <path d="M 509,388 L 517,170 L 547,170 L 555,388 Z" fill="none" stroke="var(--stroke-color, #181716)" stroke-width="1.2"/>
  <polygon points="511,170 553,170 559,158 505,158" fill="none" stroke="var(--stroke-color, #181716)" stroke-width="1"/>
  <rect x="501" y="148" width="62" height="10" fill="none" stroke="var(--stroke-color, #181716)" stroke-width="1"/>

  <!-- Col 7 -->
  <path d="M 587,388 L 596,170 L 626,170 L 635,388 Z" fill="none" stroke="var(--stroke-color, #181716)" stroke-width="1.2"/>
  <polygon points="590,170 632,170 638,158 584,158" fill="none" stroke="var(--stroke-color, #181716)" stroke-width="1"/>
  <rect x="580" y="148" width="62" height="10" fill="none" stroke="var(--stroke-color, #181716)" stroke-width="1"/>

  <!-- Col 8 -->
  <path d="M 663,388 L 674,170 L 704,170 L 715,388 Z" fill="none" stroke="var(--stroke-color, #181716)" stroke-width="1.2"/>
  <polygon points="668,170 710,170 716,158 662,158" fill="none" stroke="var(--stroke-color, #181716)" stroke-width="1"/>
  <rect x="658" y="148" width="62" height="10" fill="none" stroke="var(--stroke-color, #181716)" stroke-width="1"/>

  <!-- Architrave -->
  <path d="M 75,148 Q 400,144 725,148 L 725,124 Q 400,120 75,124 Z" fill="var(--fill-subtle, rgba(24,23,22,0.03))" stroke="var(--stroke-color, #181716)" stroke-width="1.2" />
  
  <!-- Frieze (Triglyphs & Metopes) -->
  <path d="M 75,124 Q 400,120 725,124 L 725,92 Q 400,88 75,92 Z" fill="none" stroke="var(--stroke-color, #181716)" stroke-width="1.2" />
  
  <!-- Pediment with Tympanum -->
  <polygon points="70,92 400,24 730,92" fill="url(#hatch-diag)" stroke="var(--stroke-color, #181716)" stroke-width="1.5" />
  <polygon points="85,88 400,28 715,88" fill="none" stroke="var(--stroke-color, #181716)" stroke-width="0.8" />
  
  <!-- Mathematical Axis Lines & Proportional Dimensions -->
  <line x1="400" y1="10" x2="400" y2="435" stroke="var(--accent-color, #B83B26)" stroke-width="0.8" stroke-dasharray="4,4" />
  <text x="408" y="36" font-family="'JetBrains Mono', monospace" font-size="9" fill="var(--accent-color, #B83B26)">AXIS PRIMARIUS (1:1.618)</text>
  
  <line x1="50" y1="400" x2="50" y2="440" stroke="var(--stroke-color, #181716)" stroke-width="0.6"/>
  <line x1="750" y1="400" x2="750" y2="440" stroke="var(--stroke-color, #181716)" stroke-width="0.6"/>
  <line x1="50" y1="435" x2="750" y2="435" stroke="var(--stroke-color, #181716)" stroke-width="0.6" marker-start="url(#dot)" marker-end="url(#dot)"/>
  <text x="360" y="446" font-family="'JetBrains Mono', monospace" font-size="9" fill="var(--stroke-color, #181716)">30.88 METERS (STYLOBATE)</text>
</svg>"""

svg_pantheon = """<svg viewBox="0 0 800 450" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <pattern id="hatch-pantheon" width="6" height="6" patternTransform="rotate(30 0 0)" patternUnits="userSpaceOnUse">
      <line x1="0" y1="0" x2="0" y2="6" stroke="var(--stroke-color, #181716)" stroke-width="0.5" stroke-opacity="0.2"/>
    </pattern>
  </defs>
  <!-- Base Ground Level -->
  <line x1="40" y1="410" x2="760" y2="410" stroke="var(--stroke-color, #181716)" stroke-width="1.5" />
  
  <!-- Rotunda Cylindrical Walls (Thickness 6m) -->
  <!-- Left Wall Cross Section -->
  <rect x="140" y="195" width="85" height="215" fill="url(#hatch-pantheon)" stroke="var(--stroke-color, #181716)" stroke-width="1.2" />
  <!-- Left Wall Niches -->
  <path d="M 185,240 A 30,30 0 0,1 225,240 L 225,380 L 185,380 Z" fill="#FFFFFF" stroke="var(--stroke-color, #181716)" stroke-width="0.8"/>
  
  <!-- Right Wall Cross Section -->
  <rect x="575" y="195" width="85" height="215" fill="url(#hatch-pantheon)" stroke="var(--stroke-color, #181716)" stroke-width="1.2" />
  <!-- Right Wall Niches -->
  <path d="M 575,240 A 30,30 0 0,0 615,240 L 615,380 L 575,380 Z" fill="#FFFFFF" stroke="var(--stroke-color, #181716)" stroke-width="0.8"/>
  
  <!-- Hemispherical Dome (Exterior Stepped Rings) -->
  <!-- Exterior Dome Stepped Profile -->
  <path d="M 140,195 L 140,165 L 175,165 L 175,135 L 215,135 L 215,105 L 265,105 L 265,75 L 340,75 L 355,50 L 445,50 L 460,75 L 535,75 L 535,105 L 585,105 L 585,135 L 625,135 L 625,165 L 660,165 L 660,195" fill="none" stroke="var(--stroke-color, #181716)" stroke-width="1.4" />
  
  <!-- Interior Hemisphere Perfect Inscribed Circle (Radius = 175px, Diameter = 350px = 43.3m) -->
  <path d="M 225,195 A 175,175 0 0,1 575,195" fill="none" stroke="var(--stroke-color, #181716)" stroke-width="1.6" />
  <!-- Virtual lower hemisphere -->
  <path d="M 225,195 A 175,175 0 0,0 575,195" fill="none" stroke="var(--accent-color, #B83B26)" stroke-width="0.9" stroke-dasharray="5,5" />
  
  <!-- The Oculus (9m open sky) -->
  <line x1="365" y1="20" x2="435" y2="20" stroke="var(--stroke-color, #181716)" stroke-width="2" />
  <line x1="365" y1="20" x2="365" y2="50" stroke="var(--stroke-color, #181716)" stroke-width="1.2" />
  <line x1="435" y1="20" x2="435" y2="50" stroke="var(--stroke-color, #181716)" stroke-width="1.2" />
  
  <!-- Light Beam from Oculus -->
  <polygon points="365,22 435,22 560,410 420,410" fill="var(--accent-color, #B83B26)" fill-opacity="0.08" stroke="var(--accent-color, #B83B26)" stroke-width="0.5" stroke-dasharray="2,2"/>
  
  <!-- Portico on Left -->
  <polygon points="30,410 30,230 140,230 140,410" fill="none" stroke="var(--stroke-color, #181716)" stroke-width="1" />
  <polygon points="25,230 145,230 85,185" fill="none" stroke="var(--stroke-color, #181716)" stroke-width="1.2" />
  
  <!-- Dimension Lines & Inscribed Sphere Text -->
  <circle cx="400" cy="195" r="4" fill="var(--accent-color, #B83B26)" />
  <text x="410" y="198" font-family="'JetBrains Mono', monospace" font-size="9" fill="var(--accent-color, #B83B26)">GEOMETRIC CENTROID (Ø 43.30m)</text>
  
  <!-- Vitruvian Radius line -->
  <line x1="400" y1="195" x2="523" y2="72" stroke="var(--accent-color, #B83B26)" stroke-width="0.8" stroke-dasharray="3,3" />
  <text x="470" y="125" font-family="'JetBrains Mono', monospace" font-size="8" fill="var(--accent-color, #B83B26)">R = 21.65m</text>
</svg>"""

svg_rotonda = """<svg viewBox="0 0 800 450" xmlns="http://www.w3.org/2000/svg">
  <!-- Villa Rotonda: 4-fold Biaxial Symmetry and Central Dome -->
  <line x1="40" y1="410" x2="760" y2="410" stroke="var(--stroke-color, #181716)" stroke-width="1.5" />
  
  <!-- Podium Stairs (Substructure) -->
  <rect x="220" y="320" width="360" height="90" fill="var(--fill-subtle, rgba(24,23,22,0.02))" stroke="var(--stroke-color, #181716)" stroke-width="1.2" />
  <line x1="280" y1="340" x2="520" y2="340" stroke="var(--stroke-color, #181716)" stroke-width="0.6"/>
  <line x1="280" y1="360" x2="520" y2="360" stroke="var(--stroke-color, #181716)" stroke-width="0.6"/>
  <line x1="280" y1="380" x2="520" y2="380" stroke="var(--stroke-color, #181716)" stroke-width="0.6"/>
  
  <!-- Piano Nobile Block -->
  <rect x="240" y="180" width="320" height="140" fill="#FFFFFF" stroke="var(--stroke-color, #181716)" stroke-width="1.4" />
  
  <!-- Portico Ionic Columns (Hexastyle) -->
  <rect x="290" y="210" width="220" height="110" fill="var(--fill-subtle, rgba(24,23,22,0.02))" stroke="var(--stroke-color, #181716)" stroke-width="1" />
  <!-- Ionic Capitals & Columns -->
  <line x1="305" y1="210" x2="305" y2="320" stroke="var(--stroke-color, #181716)" stroke-width="1.5"/>
  <line x1="345" y1="210" x2="345" y2="320" stroke="var(--stroke-color, #181716)" stroke-width="1.5"/>
  <line x1="385" y1="210" x2="385" y2="320" stroke="var(--stroke-color, #181716)" stroke-width="1.5"/>
  <line x1="415" y1="210" x2="415" y2="320" stroke="var(--stroke-color, #181716)" stroke-width="1.5"/>
  <line x1="455" y1="210" x2="455" y2="320" stroke="var(--stroke-color, #181716)" stroke-width="1.5"/>
  <line x1="495" y1="210" x2="495" y2="320" stroke="var(--stroke-color, #181716)" stroke-width="1.5"/>
  
  <!-- Portico Pediment with Statues -->
  <polygon points="280,210 400,140 520,210" fill="#FFFFFF" stroke="var(--stroke-color, #181716)" stroke-width="1.4" />
  
  <!-- Central Cupola (Drum & Hemisphere Dome) -->
  <rect x="340" y="125" width="120" height="55" fill="#FFFFFF" stroke="var(--stroke-color, #181716)" stroke-width="1.2" />
  <path d="M 345,125 A 55,55 0 0,1 455,125 Z" fill="var(--fill-subtle, rgba(24,23,22,0.04))" stroke="var(--stroke-color, #181716)" stroke-width="1.4" />
  <circle cx="400" cy="70" r="6" fill="#FFFFFF" stroke="var(--stroke-color, #181716)" stroke-width="1" />
  
  <!-- Biaxial Harmonic Proportions -->
  <line x1="400" y1="20" x2="400" y2="430" stroke="var(--accent-color, #B83B26)" stroke-width="0.75" stroke-dasharray="4,4"/>
  <line x1="160" y1="250" x2="640" y2="250" stroke="var(--accent-color, #B83B26)" stroke-width="0.75" stroke-dasharray="4,4"/>
  
  <text x="410" y="45" font-family="'JetBrains Mono', monospace" font-size="9" fill="var(--accent-color, #B83B26)">PALLADIAN SYMMETRY AXIS</text>
  <text x="250" y="245" font-family="'JetBrains Mono', monospace" font-size="8" fill="var(--accent-color, #B83B26)">HARMONIC RATIO 12:12:6</text>
</svg>"""

svg_kahn = """<svg viewBox="0 0 800 450" xmlns="http://www.w3.org/2000/svg">
  <!-- Kimbell Art Museum: Louis Kahn Cycloid Vault & Reflected Light Slot -->
  <line x1="40" y1="410" x2="760" y2="410" stroke="var(--stroke-color, #181716)" stroke-width="1.5" />
  
  <!-- Reinforced Concrete Columns (Square 60x60cm) -->
  <rect x="120" y="240" width="30" height="170" fill="var(--fill-subtle, rgba(24,23,22,0.04))" stroke="var(--stroke-color, #181716)" stroke-width="1.2"/>
  <rect x="370" y="240" width="30" height="170" fill="var(--fill-subtle, rgba(24,23,22,0.04))" stroke="var(--stroke-color, #181716)" stroke-width="1.2"/>
  <rect x="620" y="240" width="30" height="170" fill="var(--fill-subtle, rgba(24,23,22,0.04))" stroke="var(--stroke-color, #181716)" stroke-width="1.2"/>
  
  <!-- Left Cycloid Vault (Post-tensioned curved shell span 30m) -->
  <!-- Mathematical Cycloid curve -->
  <path d="M 120,240 C 130,120 220,90 240,90 C 260,90 350,120 370,240" fill="none" stroke="var(--stroke-color, #181716)" stroke-width="2"/>
  <path d="M 130,240 C 140,130 225,102 240,102 C 255,102 340,130 360,240" fill="none" stroke="var(--stroke-color, #181716)" stroke-width="1"/>
  
  <!-- Central Skylight & Winged Aluminum Reflector (Left) -->
  <rect x="235" y="85" width="20" height="8" fill="#FFFFFF" stroke="var(--stroke-color, #181716)" stroke-width="1"/>
  <path d="M 220,115 Q 245,125 270,115" fill="none" stroke="var(--accent-color, #B83B26)" stroke-width="1.5"/>
  <!-- Reflected Daylight rays -->
  <line x1="245" y1="90" x2="230" y2="115" stroke="var(--accent-color, #B83B26)" stroke-width="0.75" stroke-dasharray="2,2"/>
  <line x1="230" y1="115" x2="160" y2="180" stroke="var(--accent-color, #B83B26)" stroke-width="0.75" stroke-dasharray="2,2"/>
  <line x1="260" y1="115" x2="330" y2="180" stroke="var(--accent-color, #B83B26)" stroke-width="0.75" stroke-dasharray="2,2"/>
  
  <!-- Right Cycloid Vault -->
  <path d="M 370,240 C 380,120 470,90 490,90 C 510,90 600,120 620,240" fill="none" stroke="var(--stroke-color, #181716)" stroke-width="2"/>
  <path d="M 380,240 C 390,130 475,102 490,102 C 505,102 590,130 610,240" fill="none" stroke="var(--stroke-color, #181716)" stroke-width="1"/>
  
  <!-- Central Skylight & Reflector (Right) -->
  <rect x="485" y="85" width="20" height="8" fill="#FFFFFF" stroke="var(--stroke-color, #181716)" stroke-width="1"/>
  <path d="M 470,115 Q 495,125 520,115" fill="none" stroke="var(--accent-color, #B83B26)" stroke-width="1.5"/>
  
  <!-- Travertine Infills & Glazed Slots -->
  <rect x="150" y="280" width="220" height="130" fill="var(--fill-subtle, rgba(24,23,22,0.02))" stroke="var(--stroke-color, #181716)" stroke-width="0.8"/>
  <line x1="150" y1="340" x2="370" y2="340" stroke="var(--stroke-color, #181716)" stroke-width="0.5" stroke-dasharray="4,4"/>
  
  <text x="175" y="75" font-family="'JetBrains Mono', monospace" font-size="9" fill="var(--accent-color, #B83B26)">CYCLOID CURVATURE (NO LATERAL THRUST)</text>
  <text x="180" y="320" font-family="'JetBrains Mono', monospace" font-size="8" fill="var(--ink-tertiary)">TRAVERTINE CLADDING</text>
</svg>"""

svg_savoye = """<svg viewBox="0 0 800 450" xmlns="http://www.w3.org/2000/svg">
  <!-- Villa Savoye: Le Corbusier 5 Points of Architecture -->
  <line x1="40" y1="410" x2="760" y2="410" stroke="var(--stroke-color, #181716)" stroke-width="1.5" />
  
  <!-- Point 1: Pilotis (Reinforced Concrete Grid Columns) -->
  <line x1="140" y1="280" x2="140" y2="410" stroke="var(--stroke-color, #181716)" stroke-width="3"/>
  <line x1="270" y1="280" x2="270" y2="410" stroke="var(--stroke-color, #181716)" stroke-width="3"/>
  <line x1="400" y1="280" x2="400" y2="410" stroke="var(--stroke-color, #181716)" stroke-width="3"/>
  <line x1="530" y1="280" x2="530" y2="410" stroke="var(--stroke-color, #181716)" stroke-width="3"/>
  <line x1="660" y1="280" x2="660" y2="410" stroke="var(--stroke-color, #181716)" stroke-width="3"/>
  
  <!-- Ground Floor Curved Glazed Base (Turning radius for 1927 Citroën) -->
  <path d="M 200,410 C 200,320 270,300 400,300 L 600,300 L 600,410 Z" fill="var(--fill-subtle, rgba(24,23,22,0.03))" stroke="var(--stroke-color, #181716)" stroke-width="1.2"/>
  
  <!-- Point 2 & 3: Free Facade & Raised Piano Nobile Box -->
  <rect x="110" y="160" width="580" height="120" fill="#FFFFFF" stroke="var(--stroke-color, #181716)" stroke-width="1.5"/>
  
  <!-- Point 4: Ribbon Window (Fenêtre en longueur) continuous horizontal band -->
  <rect x="110" y="195" width="580" height="35" fill="var(--fill-subtle, rgba(38,84,124,0.08))" stroke="var(--stroke-color, #181716)" stroke-width="1"/>
  <line x1="160" y1="195" x2="160" y2="230" stroke="var(--stroke-color, #181716)" stroke-width="0.6"/>
  <line x1="240" y1="195" x2="240" y2="230" stroke="var(--stroke-color, #181716)" stroke-width="0.6"/>
  <line x1="320" y1="195" x2="320" y2="230" stroke="var(--stroke-color, #181716)" stroke-width="0.6"/>
  <line x1="400" y1="195" x2="400" y2="230" stroke="var(--stroke-color, #181716)" stroke-width="0.6"/>
  <line x1="480" y1="195" x2="480" y2="230" stroke="var(--stroke-color, #181716)" stroke-width="0.6"/>
  <line x1="560" y1="195" x2="560" y2="230" stroke="var(--stroke-color, #181716)" stroke-width="0.6"/>
  <line x1="640" y1="195" x2="640" y2="230" stroke="var(--stroke-color, #181716)" stroke-width="0.6"/>
  
  <!-- Point 5: Roof Garden & Solarium Sculptural Screen -->
  <path d="M 280,160 C 280,110 320,100 370,100 C 420,100 450,130 500,130 L 500,160" fill="none" stroke="var(--stroke-color, #181716)" stroke-width="1.4"/>
  <circle cx="370" cy="120" r="10" fill="none" stroke="var(--stroke-color, #181716)" stroke-width="0.8"/>
  
  <text x="120" y="145" font-family="'JetBrains Mono', monospace" font-size="9" fill="var(--accent-color, #B83B26)">CINQ POINTS DE L'ARCHITECTURE MODERNE (1929)</text>
  <text x="145" y="360" font-family="'JetBrains Mono', monospace" font-size="8" fill="var(--ink-tertiary)">PILOTIS GRID: 4.75m x 4.75m</text>
</svg>"""

svg_notredame = """<svg viewBox="0 0 800 450" xmlns="http://www.w3.org/2000/svg">
  <!-- Notre-Dame de Paris: Flying Buttress Vector Equilibrium -->
  <line x1="40" y1="410" x2="760" y2="410" stroke="var(--stroke-color, #181716)" stroke-width="1.5" />
  
  <!-- Central High Nave (33m Vault) -->
  <rect x="310" y="120" width="180" height="290" fill="none" stroke="var(--stroke-color, #181716)" stroke-width="1.2"/>
  
  <!-- Ribbed Quadripartite Vault Profile -->
  <path d="M 310,180 Q 400,110 490,180" fill="none" stroke="var(--stroke-color, #181716)" stroke-width="1.8"/>
  <path d="M 310,180 Q 400,140 490,180" fill="none" stroke="var(--stroke-color, #181716)" stroke-width="0.8"/>
  
  <!-- Clerestory Lancet Windows -->
  <path d="M 360,260 A 20,40 0 0,1 400,260 L 400,200 A 20,40 0 0,0 360,200 Z" fill="var(--fill-subtle, rgba(38,84,124,0.06))" stroke="var(--stroke-color, #181716)" stroke-width="0.8"/>
  <path d="M 400,260 A 20,40 0 0,1 440,260 L 440,200 A 20,40 0 0,0 400,200 Z" fill="var(--fill-subtle, rgba(38,84,124,0.06))" stroke="var(--stroke-color, #181716)" stroke-width="0.8"/>
  
  <!-- Exterior Massive Buttress Piers (Left & Right) -->
  <rect x="130" y="200" width="60" height="210" fill="var(--fill-subtle, rgba(24,23,22,0.03))" stroke="var(--stroke-color, #181716)" stroke-width="1.4"/>
  <!-- Pinnacle for vertical load ballast -->
  <polygon points="130,200 160,130 190,200" fill="none" stroke="var(--stroke-color, #181716)" stroke-width="1.2"/>
  
  <rect x="610" y="200" width="60" height="210" fill="var(--fill-subtle, rgba(24,23,22,0.03))" stroke="var(--stroke-color, #181716)" stroke-width="1.4"/>
  <polygon points="610,200 640,130 670,200" fill="none" stroke="var(--stroke-color, #181716)" stroke-width="1.2"/>
  
  <!-- Flying Arches (Flyers transferring lateral wind/vault thrust) -->
  <!-- Left Fly 1 (Upper) -->
  <path d="M 190,190 Q 250,140 310,160" fill="none" stroke="var(--stroke-color, #181716)" stroke-width="2"/>
  <!-- Left Fly 2 (Lower) -->
  <path d="M 190,250 Q 250,210 310,230" fill="none" stroke="var(--stroke-color, #181716)" stroke-width="1.8"/>
  
  <!-- Right Fly 1 (Upper) -->
  <path d="M 610,190 Q 550,140 490,160" fill="none" stroke="var(--stroke-color, #181716)" stroke-width="2"/>
  <!-- Right Fly 2 (Lower) -->
  <path d="M 610,250 Q 550,210 490,230" fill="none" stroke="var(--stroke-color, #181716)" stroke-width="1.8"/>
  
  <!-- Thrust Vector Arrows -->
  <line x1="310" y1="180" x2="210" y2="235" stroke="var(--accent-color, #B83B26)" stroke-width="1" stroke-dasharray="3,3"/>
  <text x="215" y="275" font-family="'JetBrains Mono', monospace" font-size="8" fill="var(--accent-color, #B83B26)">RESULTANT THRUST VECTOR</text>
  <text x="355" y="95" font-family="'JetBrains Mono', monospace" font-size="9" fill="var(--accent-color, #B83B26)">GOTHIC DIAGONAL EQUILIBRIUM</text>
</svg>"""

svg_katsura = """<svg viewBox="0 0 800 450" xmlns="http://www.w3.org/2000/svg">
  <!-- Katsura Imperial Villa: Modular Tatami & Post-and-Beam Coordination -->
  <line x1="40" y1="410" x2="760" y2="410" stroke="var(--stroke-color, #181716)" stroke-width="1.5" />
  
  <!-- Wooden Foundation Pilings & Stones -->
  <circle cx="160" cy="380" r="14" fill="none" stroke="var(--stroke-color, #181716)" stroke-width="1.2"/>
  <circle cx="280" cy="380" r="14" fill="none" stroke="var(--stroke-color, #181716)" stroke-width="1.2"/>
  <circle cx="400" cy="380" r="14" fill="none" stroke="var(--stroke-color, #181716)" stroke-width="1.2"/>
  <circle cx="520" cy="380" r="14" fill="none" stroke="var(--stroke-color, #181716)" stroke-width="1.2"/>
  <circle cx="640" cy="380" r="14" fill="none" stroke="var(--stroke-color, #181716)" stroke-width="1.2"/>
  
  <!-- Hinoki Cypress Posts (Hashira) -->
  <rect x="154" y="160" width="12" height="220" fill="var(--fill-subtle, rgba(138,100,54,0.08))" stroke="var(--stroke-color, #181716)" stroke-width="1.2"/>
  <rect x="274" y="160" width="12" height="220" fill="var(--fill-subtle, rgba(138,100,54,0.08))" stroke="var(--stroke-color, #181716)" stroke-width="1.2"/>
  <rect x="394" y="160" width="12" height="220" fill="var(--fill-subtle, rgba(138,100,54,0.08))" stroke="var(--stroke-color, #181716)" stroke-width="1.2"/>
  <rect x="514" y="160" width="12" height="220" fill="var(--fill-subtle, rgba(138,100,54,0.08))" stroke="var(--stroke-color, #181716)" stroke-width="1.2"/>
  <rect x="634" y="160" width="12" height="220" fill="var(--fill-subtle, rgba(138,100,54,0.08))" stroke="var(--stroke-color, #181716)" stroke-width="1.2"/>
  
  <!-- Raised Veranda (Engawa) & Tatami Grid Plane -->
  <rect x="120" y="320" width="560" height="20" fill="none" stroke="var(--stroke-color, #181716)" stroke-width="1.2"/>
  
  <!-- Sliding Shoji Screens with fine wooden lattice -->
  <rect x="166" y="180" width="108" height="140" fill="#FFFFFF" stroke="var(--stroke-color, #181716)" stroke-width="0.8"/>
  <line x1="202" y1="180" x2="202" y2="320" stroke="var(--stroke-color, #181716)" stroke-width="0.5"/>
  <line x1="238" y1="180" x2="238" y2="320" stroke="var(--stroke-color, #181716)" stroke-width="0.5"/>
  <line x1="166" y1="215" x2="274" y2="215" stroke="var(--stroke-color, #181716)" stroke-width="0.5"/>
  <line x1="166" y1="250" x2="274" y2="250" stroke="var(--stroke-color, #181716)" stroke-width="0.5"/>
  <line x1="166" y1="285" x2="274" y2="285" stroke="var(--stroke-color, #181716)" stroke-width="0.5"/>
  
  <rect x="286" y="180" width="108" height="140" fill="#FFFFFF" stroke="var(--stroke-color, #181716)" stroke-width="0.8"/>
  
  <!-- Gently pitched Ir Moya Overhanging Roof with Deep Eaves (Noki) -->
  <path d="M 80,170 Q 400,135 720,170 L 680,130 Q 400,95 120,130 Z" fill="var(--fill-subtle, rgba(24,23,22,0.04))" stroke="var(--stroke-color, #181716)" stroke-width="1.5"/>
  
  <text x="140" y="90" font-family="'JetBrains Mono', monospace" font-size="9" fill="var(--accent-color, #B83B26)">KIWARI-JUTSU PROPORTIONAL SYSTEM (1 KEN = 1.91m)</text>
  <text x="430" y="280" font-family="'JetBrains Mono', monospace" font-size="8" fill="var(--ink-tertiary)">SHIN-KABE EXPOSED TIMBER FRAME</text>
</svg>"""

svg_sancarlo = """<svg viewBox="0 0 800 450" xmlns="http://www.w3.org/2000/svg">
  <!-- San Carlo alle Quattro Fontane: Borromini Intersecting Ellipses & Dynamic Curvature -->
  <line x1="40" y1="410" x2="760" y2="410" stroke="var(--stroke-color, #181716)" stroke-width="1.5" />
  
  <!-- Undulating Wave Facade (Concave - Convex - Concave) -->
  <path d="M 160,390 C 220,360 280,415 400,415 C 520,415 580,360 640,390" fill="none" stroke="var(--stroke-color, #181716)" stroke-width="2"/>
  
  <!-- Entablature Band with Undulation -->
  <path d="M 160,250 C 220,220 280,275 400,275 C 520,275 580,220 640,250" fill="none" stroke="var(--stroke-color, #181716)" stroke-width="2"/>
  
  <!-- Complex Oval / Elliptical Dome Cross-Section -->
  <!-- Primary Geometric Ellipse -->
  <ellipse cx="400" cy="150" rx="190" ry="110" fill="none" stroke="var(--accent-color, #B83B26)" stroke-width="1.2" stroke-dasharray="4,4"/>
  
  <!-- Inscribed Borromini Triangles -->
  <polygon points="400,40 235,205 565,205" fill="none" stroke="var(--accent-color, #B83B26)" stroke-width="0.8" stroke-dasharray="2,2"/>
  <polygon points="400,260 235,95 565,95" fill="none" stroke="var(--accent-color, #B83B26)" stroke-width="0.8" stroke-dasharray="2,2"/>
  
  <!-- Honeycomb Octagonal Coffers in Dome -->
  <circle cx="400" cy="150" r="18" fill="none" stroke="var(--stroke-color, #181716)" stroke-width="1"/>
  <circle cx="340" cy="150" r="14" fill="none" stroke="var(--stroke-color, #181716)" stroke-width="0.8"/>
  <circle cx="460" cy="150" r="14" fill="none" stroke="var(--stroke-color, #181716)" stroke-width="0.8"/>
  <circle cx="400" cy="100" r="14" fill="none" stroke="var(--stroke-color, #181716)" stroke-width="0.8"/>
  <circle cx="400" cy="200" r="14" fill="none" stroke="var(--stroke-color, #181716)" stroke-width="0.8"/>
  
  <!-- Lantern at the Zenith with Trinitarian Symbol -->
  <polygon points="400,30 385,55 415,55" fill="#FFFFFF" stroke="var(--stroke-color, #181716)" stroke-width="1.2"/>
  
  <text x="210" y="30" font-family="'JetBrains Mono', monospace" font-size="9" fill="var(--accent-color, #B83B26)">GEOMETRIA ELLITTICA TRINITARIA (BORROMINI 1646)</text>
  <text x="230" y="430" font-family="'JetBrains Mono', monospace" font-size="8" fill="var(--ink-tertiary)">CONCAVO-CONVEXA RHYTHM</text>
</svg>"""

print("SVG blueprints prepared successfully.")
