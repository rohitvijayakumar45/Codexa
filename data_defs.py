# Data structures for ATLAS
import json

plates_data = [
    {
        "id": "plate-parthenon",
        "code": "PL. I / ATH-438",
        "era": "Classical Antiquity",
        "category": "Sacred Geometries",
        "title": "The Parthenon: Optical Refinements & Entablature",
        "subtitle": "Iktinos, Kallikrates & Phidias — Acropolis of Athens, 438 BCE",
        "description": "Systematic study of subtle non-linear optical corrections (entasis, stylobate curvature of 65mm, inward inclination of columns by 7cm) designed to counteract perceptual foreshortening and somatic sagging.",
        "dimensions": "Stylobate 30.88m × 69.54m (Ratio 4:9)",
        "modulus": "Golden Ratio Phi 1:1.618",
        "material": "Pentelic Marble & Lead Dowels",
        "svg_key": "parthenon",
        "hotspots": [
            {"x": 110, "y": 160, "label": "Doric Capital Echinus", "desc": "Cushion-like toroid moulding transferring 240 metric tonnes of horizontal entablature load to the fluted shaft."},
            {"x": 400, "y": 55, "label": "Tympanum & Pediment Apex", "desc": "Triangular gable pitched at 13.5 degrees, enclosing the high-relief mythic birth of Athena."},
            {"x": 400, "y": 395, "label": "Stylobate Convex Curvature", "desc": "Calculated 65mm upward rise along the 30.88m facade, preventing the optical illusion of center sagging."},
            {"x": 685, "y": 280, "label": "Corner Column Inward Lean", "desc": "Corner columns are 2.5% thicker and tilted inward by 70mm to resist visual thinning against open sky."}
        ]
    },
    {
        "id": "plate-pantheon",
        "code": "PL. II / ROM-126",
        "era": "Roman Empire",
        "category": "Structural Engineering",
        "title": "The Pantheon: Oculated Monolithic Rotunda",
        "subtitle": "Emperor Hadrian & Apollodorus of Damascus — Rome, 126 CE",
        "description": "An unreinforced pozzolanic concrete dome spanning 43.30m, geometrically enclosing a perfect sphere where interior height equals diameter. Graded aggregate weight from dense travertine to light volcanic pumice.",
        "dimensions": "Span 43.30m (150 Roman Feet), Oculus Ø 8.95m",
        "modulus": "Vitruvian Sphere Ratio 1:1",
        "material": "Roman Pozzolana, Tufa & Pumice Concrete",
        "svg_key": "pantheon",
        "hotspots": [
            {"x": 400, "y": 35, "label": "The Open Oculus (9m)", "desc": "Uncovered cylindrical ring serving as primary structural compression ring and the sole daylight portal."},
            {"x": 400, "y": 195, "label": "Inscribed Celestial Sphere", "desc": "A perfect 43.30m virtual sphere inscribed in the rotunda, unifying terrestrial cylinder with celestial dome."},
            {"x": 180, "y": 300, "label": "Travertine & Tufa Stepped Rings", "desc": "Exterior ring buttresses providing massive hoop tension resistance around the dome haunch."},
            {"x": 595, "y": 310, "label": "Wall Relieving Arches", "desc": "Embedded bipedales brick relieving arches channeling 5,000 tonnes of vault weight directly to 8 massive piers."}
        ]
    },
    {
        "id": "plate-rotonda",
        "code": "PL. III / VIC-1592",
        "era": "High Renaissance",
        "category": "Sacred Geometries",
        "title": "Villa Capra 'La Rotonda': Biaxial Symmetry",
        "subtitle": "Andrea Palladio — Vicenza, Republic of Venice, 1592",
        "description": "The quintessential embodiment of Renaissance harmonic proportion. A square plan oriented 45 degrees to the cardinal points, punctuated by four identical hexastyle Ionic porticos converging upon a central cupola.",
        "dimensions": "Central Hall Ø 11.0m, Exterior Cube 24m × 24m",
        "modulus": "Harmonic Musical Intervals (2:3:4)",
        "material": "Stuccoed Brickwork, Vicenza Stone",
        "svg_key": "rotonda",
        "hotspots": [
            {"x": 400, "y": 95, "label": "Central Hemisphere Cupola", "desc": "First domestic application of a sacral dome, crowning the central salon (Sala Centrale)."},
            {"x": 400, "y": 210, "label": "Hexastyle Ionic Portico", "desc": "Grand temple front with six fluted columns framing sweeping vistas of the Venetian countryside."},
            {"x": 250, "y": 350, "label": "Substructure Vaulted Podium", "desc": "Service baseline housing rustic kitchens, wine cellars, and thermal hypocaust flues."}
        ]
    },
    {
        "id": "plate-notredame",
        "code": "PL. IV / PAR-1163",
        "era": "High Gothic",
        "category": "Structural Engineering",
        "title": "Notre-Dame de Paris: Nave Flying Buttress",
        "subtitle": "Master Jean de Chelles & Pierre de Montreuil — Île de la Cité, Paris, 1163",
        "description": "Double-span external flying arches transmitting high-vault diagonal lateral thrust across outer side-aisles to perimeter buttress towers, freeing walls to become luminous stained-glass lancets.",
        "dimensions": "Clear Nave Height 33.0m, Pier Spacing 7.20m",
        "modulus": "Ad Triangulum Geometric Grid",
        "material": "Lutetian Limestone, Lead Roofing, Oak Timber",
        "svg_key": "notredame",
        "hotspots": [
            {"x": 400, "y": 145, "label": "Sexpartite Ribbed Vault", "desc": "Curved stone ribs focusing 80% of vault deadweight onto pointed corner springers."},
            {"x": 250, "y": 175, "label": "Upper Flying Arch (Flyer)", "desc": "Diverts wind buffeting against high wooden timber roof truss down to exterior buttress."},
            {"x": 640, "y": 165, "label": "Ballast Pinnacle", "desc": "Heavy stone pyramid adding vertical gravitational load to deflect horizontal shear stress downward."}
        ]
    },
    {
        "id": "plate-kahn",
        "code": "PL. V / TEX-1972",
        "era": "Modernist Rationalism",
        "category": "Modernist Tectonics",
        "title": "Kimbell Art Museum: Cycloid Light Vaults",
        "subtitle": "Louis I. Kahn & August E. Komendant — Fort Worth, Texas, 1972",
        "description": "Sixteen post-tensioned reinforced concrete cycloid vaults spanning 30.5m. A narrow continuous longitudinal skylight with micro-perforated curved aluminum reflectors casts silver natural daylight across curved concrete surfaces.",
        "dimensions": "16 Vault Units: 30.5m Length × 6.1m Width × 6.1m Height",
        "modulus": "Cycloid Rolling Circle Formula (x=r(t-sin t), y=r(1-cos t))",
        "material": "Cast-in-Place Architectural Concrete, Roman Travertine",
        "svg_key": "kahn",
        "hotspots": [
            {"x": 245, "y": 105, "label": "Natural Daylight Reflector", "desc": "Winged perforated aluminum fixture splitting harsh Texan sun into pure diffuse silver luminescence."},
            {"x": 240, "y": 160, "label": "Post-Tensioned Cycloid Shell", "desc": "Behaves structurally as a beam rather than an arch, producing zero lateral outward thrust at column tops."},
            {"x": 135, "y": 330, "label": "Travertine Infill Screen", "desc": "Non-structural unpolished travertine infill, clearly articulated with 20mm shadow reveals from concrete frame."}
        ]
    },
    {
        "id": "plate-savoye",
        "code": "PL. VI / POI-1931",
        "era": "Modernist Rationalism",
        "category": "Modernist Tectonics",
        "title": "Villa Savoye: The Five Points of Modernity",
        "subtitle": "Le Corbusier & Pierre Jeanneret — Poissy, France, 1931",
        "description": "Complete spatial realization of the 'Five Points for a New Architecture': Pilotis elevating structure, Flat Roof Garden, Free Plan layout, Horizontal Ribbon Window, and Non-load-bearing Free Facade.",
        "dimensions": "Grid 4.75m × 4.75m, Total Footprint 21.5m × 19.0m",
        "modulus": "Dom-Ino Modular Concrete Frame",
        "material": "Reinforced Concrete, Smooth Stucco, Steel Glazing",
        "svg_key": "savoye",
        "hotspots": [
            {"x": 270, "y": 340, "label": "Pilotis Reinforced Grid", "desc": "Slender cylindrical concrete columns freeing ground plane for automobile circulation and landscape."},
            {"x": 400, "y": 210, "label": "Continuous Ribbon Window", "desc": "Uninterrupted perimeter glazing providing even horizontal light distribution regardless of internal partitions."},
            {"x": 370, "y": 130, "label": "Roof Garden Solarium", "desc": "Restores the green footprint occupied by the building while protecting concrete slab from thermal expansion."}
        ]
    },
    {
        "id": "plate-katsura",
        "code": "PL. VII / KYO-1645",
        "era": "Edo Period",
        "category": "Domestic Typologies",
        "title": "Katsura Imperial Villa: Tatami Matrix",
        "subtitle": "Prince Toshihito & Kobori Enshu — Kyoto, Japan, 1645",
        "description": "Sublime masterpiece of Japanese sukiya-zukuri architecture. Staggered flock-of-geese (Ganko-kei) layout governed by the 1-Ken (1.91m) modular coordinate grid, unifying interior tatami mats with garden vistas.",
        "dimensions": "Modular 1 Ken = 6.3 Shaku (1.91m), Shoin Pavilion 163 tatami",
        "modulus": "Kiwari-jutsu Modular Proportion",
        "material": "Hinoki Cypress, Washi Paper, Bamboo, Cedar Shingles",
        "svg_key": "katsura",
        "hotspots": [
            {"x": 274, "y": 240, "label": "Hinoki Cypress Post (Hashira)", "desc": "Square planed timber columns left completely unvarnished to celebrate the natural grain and scent."},
            {"x": 340, "y": 230, "label": "Sliding Shoji & Fusuma", "desc": "Movable lattice partitions allowing instantaneous spatial reconfiguration from intimate rooms to open pavilions."},
            {"x": 400, "y": 130, "label": "Deep Overhanging Eaves (Noki)", "desc": "Broad pitched eaves casting meditative penumbral shadows while protecting delicate woodwork from rain."}
        ]
    },
    {
        "id": "plate-sancarlo",
        "code": "PL. VIII / ROM-1646",
        "era": "Roman Baroque",
        "category": "Sacred Geometries",
        "title": "San Carlo: Borromini Intersecting Ellipses",
        "subtitle": "Francesco Borromini — Rome, Papal States, 1646",
        "description": "A triumph of non-Euclidean spatial mechanics. An undulating concavo-convex facade concealing an extraordinary interior dome formed by two equilateral triangles joined at their bases to generate an elliptical perimeter.",
        "dimensions": "Dome 25.8m Major Axis × 16.2m Minor Axis",
        "modulus": "Trinitarian Tripartite Harmonic Ellipse",
        "material": "Roman Travertine, Stucco Lustro",
        "svg_key": "sancarlo",
        "hotspots": [
            {"x": 400, "y": 150, "label": "Honeycomb Elliptical Dome", "desc": "Intersecting geometric octagonal, hexagonal, and cross coffers diminishing in scale toward zenith to exaggerate height."},
            {"x": 400, "y": 42, "label": "Lantern with Holy Spirit Dove", "desc": "Dedicated daylight source illuminating the complex geometric coffer relief from directly above."},
            {"x": 400, "y": 280, "label": "Undulating Wave Entablature", "desc": "Continuous dynamic cornice rhythmically alternating between convex swelling and concave recession."}
        ]
    }
]

typologies_data = [
    {"code": "TYP-01", "name": "Hypostyle Hall", "archetype": "Columnar Trabeated Forest", "era": "Classical Antiquity", "system": "Post & Lintel", "material": "Sandstone & Granite", "span": "3.5m - 6.0m", "efficiency": "Moderate", "desc": "Densely packed grid of monumental columns supporting heavy stone architrave lintels, creating a rhythm of compressed spatial shadows."},
    {"code": "TYP-02", "name": "Pendentive Dome", "archetype": "Spherical Transition Vault", "era": "Byzantine / Renaissance", "system": "Curved Shell", "material": "Brick & Hydraulic Lime", "span": "31.0m - 42.0m", "efficiency": "High", "desc": "Spherical triangular masonry infills resolving the geometrical collision between a circular dome drum and a square four-pier bay."},
    {"code": "TYP-03", "name": "Flying Buttress", "archetype": "Exoskeletal Vector Arc", "era": "High Gothic", "system": "Compressive Thrust", "material": "Ashlar Limestone", "span": "12.0m - 18.0m", "efficiency": "Very High", "desc": "Inclined exterior masonry flyer channeling internal ceiling thrust away from delicate curtain walls onto massive ground towers."},
    {"code": "TYP-04", "name": "Catenary Arch", "archetype": "Pure Inverted Hanging Chain", "era": "Modern / Catalan", "system": "Pure Compression", "material": "Thin Brick Tile & Mortar", "span": "15.0m - 40.0m", "efficiency": "Maximum (No Bending)", "desc": "The curve formed by a hanging flexible chain under uniform gravity, inverted to yield a structural vault devoid of tensile stress."},
    {"code": "TYP-05", "name": "Hyperbolic Paraboloid", "archetype": "Doubly-Ruled Saddle Shell", "era": "Mid-Century Modern", "system": "Membrane Shear", "material": "Thin-shell Reinforced Concrete", "span": "20.0m - 50.0m", "efficiency": "Maximum", "desc": "Saddle-shaped anti-clastic surface generated purely from straight intersecting line segments, combining extreme stiffness with 40mm thickness."},
    {"code": "TYP-06", "name": "Pilotis Grid & Free Plan", "archetype": "Elevated Reinforced Frame", "era": "Modernist Rationalism", "system": "Point-Load Frame", "material": "Reinforced Concrete & Steel", "span": "6.0m - 9.0m", "efficiency": "High", "desc": "Replacement of load-bearing perimeter walls with structural columns, freeing both the ground landscape and internal partitions."},
    {"code": "TYP-07", "name": "Cycloid Post-Tensioned Vault", "archetype": "Parabolic Light Shell", "era": "Modernist Rationalism", "system": "Pre-stressed Shell", "material": "Post-Tensioned Concrete", "span": "30.5m", "efficiency": "Very High", "desc": "Continuous cycloidal curvature functioning as a self-supporting beam without horizontal outward thrust at column supports."},
    {"code": "TYP-08", "name": "Diagrid Exoskeleton", "archetype": "Triangulated Spatial Cage", "era": "Contemporary High-Tech", "system": "Spatial Truss", "material": "Structural Steel Tubulars", "span": "45.0m+", "efficiency": "Maximum", "desc": "Perimeter network of intersecting diagonal steel beams carrying both vertical gravity loads and lateral wind/seismic shear loads."},
    {"code": "TYP-09", "name": "Muqarnas Corbel Vault", "archetype": "Fractal Stalactite Tier", "era": "Islamic Golden Age", "system": "Corbelled Squinch", "material": "Plaster, Brick & Glazed Ceramic", "span": "8.0m - 22.0m", "efficiency": "High", "desc": "3D cellular corbelled niche arrays bridging rectangular walls to hemispherical domes through geometric subdivision."},
    {"code": "TYP-10", "name": "Tholos Monopteros", "archetype": "Circular Peripteral Temple", "era": "Classical Antiquity", "system": "Peristyle Colonnade", "material": "Pentelic & Parian Marble", "span": "Ø 7.0m - 14.0m", "efficiency": "Moderate", "desc": "Cylindrical cella enclosed within a concentric ring of fluted columns with conical or hemispherical stone roofing."},
    {"code": "TYP-11", "name": "Cantilever Truss Arm", "archetype": "Overhanging Moment Beam", "era": "Industrial / Modern", "system": "Tension-Compression Pair", "material": "Wrought Iron & Cast Steel", "span": "15.0m - 60.0m", "efficiency": "High", "desc": "Rigid structural element anchored at only one end, projecting horizontally into space to support suspended spans."},
    {"code": "TYP-12", "name": "Geodesic Sphere Hexad", "archetype": "Polyhedral Icosahedral Shell", "era": "Late Modernist", "system": "3D Space Frame", "material": "Extruded Aluminum & ETFE", "span": "30.0m - 120.0m", "efficiency": "Maximum", "desc": "Triangular facets distributed along great circles of a sphere, distributing stresses omnidirectionally with minimal structural mass."}
]

materials_data = [
    {
        "id": "mat-pozzolana",
        "name": "Roman Pozzolanic Concrete (Opus Caementicium)",
        "origin": "Pozzuoli / Bay of Naples, Italy",
        "density": "2,200 kg/m³",
        "compressive": "25 - 35 MPa",
        "carbon": "75 kg CO₂/tonne (Ultra Low)",
        "lifespan": "2,000+ Years",
        "formula": "Lime (CaO) + Volcanic Ash (SiO₂/Al₂O₃) + Seawater",
        "tactility": "Warm pitted stone with aggregate inclusions of tufa, brick shards, and porous volcanic pumice.",
        "description": "Self-healing volcanic hydraulic cement that reacts over millennia with penetrating moisture to precipitate crystalline stratlingite, actively strengthening the matrix against fracture."
    },
    {
        "id": "mat-travertine",
        "name": "Tivoli Roman Travertine (Lapis Tiburtinus)",
        "origin": "Tivoli Quarries, Lazio, Italy",
        "density": "2,450 kg/m³",
        "compressive": "60 - 90 MPa",
        "carbon": "32 kg CO₂/tonne (Quarried)",
        "lifespan": "1,000+ Years",
        "formula": "Calcium Carbonate CaCO₃ (Sedimentary Limestone)",
        "tactility": "Creamy ivory to honey-gold striated grain with organic longitudinal voids and matte honed surface.",
        "description": "Precipitated around thermal sulfur springs; beloved from the Roman Colosseum to Louis Kahn's Kimbell Art Museum for its warmth, light refraction, and enduring dignified patina."
    },
    {
        "id": "mat-corten",
        "name": "Weathering Corten Steel (ASTM A588)",
        "origin": "Industrial Metallurgy",
        "density": "7,850 kg/m³",
        "compressive": "485 - 620 MPa (Tensile)",
        "carbon": "1,850 kg CO₂/tonne",
        "lifespan": "120+ Years",
        "formula": "Fe + Cu + Cr + Ni + P Alloy",
        "tactility": "Velvety granular rust oxide layer developing from fiery orange-ochre into deep velvety chocolate bronze.",
        "description": "Copper-chromium alloy steel which eliminates painting by generating a stable, continuous, self-regenerating oxide passivation layer under natural atmospheric wetting cycles."
    },
    {
        "id": "mat-hinoki",
        "name": "Hand-Hewn Hinoki Cypress (Chamaecyparis obtusa)",
        "origin": "Kiso Valley, Nagano, Japan",
        "density": "450 kg/m³",
        "compressive": "40 MPa (Parallel to Grain)",
        "carbon": "-800 kg CO₂/tonne (Carbon Negative)",
        "lifespan": "1,000+ Years (Horyu-ji Pagoda)",
        "formula": "Cellulose + Lignin + Hinokitiol Phytoalexins",
        "tactility": "Silken, straight grain with lustrous pearlescent sheen and soothing cedar aromatic terpenes.",
        "description": "The sacred timber of Japanese imperial shrines. Exceptional dimensional stability and natural insect/fungal immunity; plane-cut with yariganna spear planes to seal fiber ends."
    },
    {
        "id": "mat-glulam",
        "name": "Mass Structural Glulam & CLT",
        "origin": "Alpine Forestry",
        "density": "480 - 550 kg/m³",
        "compressive": "28 - 42 MPa",
        "carbon": "-650 kg CO₂/tonne (Sequestered)",
        "lifespan": "100+ Years",
        "formula": "Laminated European Spruce / Douglas Fir + Melamine Adhesive",
        "tactility": "Warm linear grain with structural finger joints, sanded matte finish with breathable bio-wax seal.",
        "description": "High-performance engineered timber formed by parallel-bonding structural finger-jointed timber laminations, offering steel-equivalent strength-to-weight with carbon sequestration."
    },
    {
        "id": "mat-marble",
        "name": "Pentelic & Carrara White Marble",
        "origin": "Mount Pentelikon, Greece & Carrara, Tuscany",
        "density": "2,700 kg/m³",
        "compressive": "110 - 140 MPa",
        "carbon": "45 kg CO₂/tonne",
        "lifespan": "2,500+ Years",
        "formula": "Metamorphic Calcite CaCO₃ (99% Pure)",
        "tactility": "Translucent fine-grained crystalline matrix scattering incident light up to 4mm beneath the surface.",
        "description": "Metamorphic limestone containing microscopic trace iron inclusions that oxidize over centuries under Athenian sunlight to acquire the warm, legendary honey-golden patina."
    }
]

print("Data definitions ready.")
