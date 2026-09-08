# Single-HTML Benchmark Prompt

Paste the block below into Codexa. Tuned against a real observed failure: an open-ended
"you decide the product" brief sent GLM into three complete product redesigns across 48 minutes
and 39,655 reasoning tokens without writing a single file. The commitment clause in STEP 1 and the
"first write_file by your third tool call" rule are the forcing functions that prevent that.

---

Build a single, self-contained HTML file: a polished, classical, light-themed interactive page.

## STEP 1 — COMMIT (do this first, and only once)

In your FIRST response, state in **three sentences**: the product concept, its signature
interaction, and its typographic pairing. Then build that.

Do not evaluate alternative concepts. Do not revisit this decision later. If a better idea occurs
to you mid-build, write it in a comment at the bottom of the file and keep building the committed
one. A good concept executed completely beats a better concept abandoned.

Pick something with real structure to explore — an archive, a catalogue, a register, a field
guide, an almanac, a collection. Invent realistic content: 18–30 entries with genuine-sounding
names, dates, attributions and one-paragraph descriptions. No lorem ipsum, no "Item 1".

## STEP 2 — DESIGN SYSTEM (decide once, apply everywhere)

**Typography — serif-led.** Pick ONE pairing and commit:
- EB Garamond + IBM Plex Mono
- Newsreader + JetBrains Mono
- Spectral + IBM Plex Mono

Load from Google Fonts with a real fallback stack (`Georgia, serif` / `ui-monospace, monospace`).
Serif carries the identity: names, headings, body. Mono carries data: numbers, labels, coordinates,
timestamps — uppercase, `letter-spacing: 0.14em`, 9–11px. Enable `font-feature-settings: "kern","liga"`
and oldstyle figures in body text where the face supports it.

**Colour — light, classical, restrained.**
- Paper `#F4F1EA`, raised surface `#FBFAF5`, white `#FFFFFF` for mounted elements
- Ink `#211E1A`, charcoal `#4B463F`, stone `#7A7468`, faint `#A29B8C`
- Hairlines `#DDD8CB` — hairlines do the structural work, not borders and boxes
- ONE accent, used for under 8% of the interface: a deep rubric red `#983A2C`
- No gradients beyond a barely-perceptible paper wash. No glassmorphism. No dark mode.

**Space and shadow.** Generous whitespace. Shadows only on genuinely floating things (drawer,
palette, toast) and always soft and layered. Everything else earns separation through rules and
space.

## STEP 3 — MOTION (this is where the quality shows)

Easing `cubic-bezier(0.16, 1, 0.3, 1)` throughout. 120ms micro / 260ms standard / 560ms spatial.
Animate `transform` and `opacity` only, except where a physical size change is the point.

Required, all of them:

1. **Scroll reveals** — `IntersectionObserver`, elements rise 12px and fade in, staggered 40ms by
   index, fired once. Never re-animate on scroll-back.
2. **SVG draw-in** — inline SVG line art that inks itself via `stroke-dasharray`/`stroke-dashoffset`.
   Set `pathLength="1"` on every path so you need no JS length measurement, then animate
   `stroke-dashoffset: 1 → 0` with a per-path delay.
3. **Smooth in-page navigation** — `scroll-behavior: smooth` plus `scroll-margin-top` on targets so
   headings never land under a sticky header.
4. **A detail panel** that slides in with the page content subtly receding behind a blurred veil.
5. **Hover micro-interactions** — an underline growing left-to-right, a numeral shifting to the
   accent colour, an arrow fading in. Gate them behind `@media (hover: hover)`.
6. **One signature transition** the whole page is built around — a layout morph, a continuously
   transforming view, a scrubber that redraws content as it moves. Make it the reason someone
   remembers the page.
7. **`prefers-reduced-motion: reduce`** disables all of it. Non-negotiable.

## STEP 4 — SUBSTANCE

Not a landing page. A working environment:
- Filter or sort the collection, with counts that update
- Open an entry into a detail view with real depth
- A keyboard command palette (⌘K / Ctrl+K) with fuzzy search and arrow-key navigation
- Real states: loading, empty (with a way out), error (with retry), selected, focused
- Keyboard support throughout, and a visible `:focus-visible` ring
- Responsive: recompose the layout at small widths, do not merely stack columns

## STEP 5 — PROCESS AND TOOLS (follow this order)

1. `list_directory` — confirm the repo state.
2. `get_design_guidance` — load it before writing any UI code.
3. `write_file` — **write the complete first version by your third tool call.** One file,
   `index.html`. Do not write it in fragments held together by sentinel comments; that pattern
   breaks when the conversation is compacted. Aim for a strong, complete ~900–1400 lines rather
   than a sprawling 4,000 you never finish.
4. `start_dev_server`, then `screenshot` — look at what you actually built.
5. `browser_console` — confirm zero errors.
6. `edit_file` — refine in targeted passes. Screenshot again after each.
7. Repeat 4–6 at 1440px, 834px and 390px until nothing looks accidental.

If a section is large and mechanical, `delegate_build` it with a spec that names your exact token
names, class prefixes and fonts — do not deliberate over whether to delegate, just decide in one
sentence and move.

## STEP 6 — DONE MEANS

- `screenshot` taken and reviewed at all three widths
- Zero console errors
- Every interaction works when clicked, not merely present in the markup
- Reduced-motion verified
- You looked at the result and fixed what looked cheap, misaligned or unfinished

## AVOID

Neon, cyberpunk, dark-first styling, generic SaaS blue, endless rounded cards, glassmorphism,
template sidebars, meaningless charts, decorative motion with no purpose, stock component-library
looks, emoji as icons, `border-radius` over 16px, and any text that reads as placeholder.

## THE BAR

Not "does this look nice." It is: **could this pass as the work of a small studio that cares
enormously about typography and motion?** Push until very little looks accidental — but ship a
complete, working page first, then refine. An unfinished masterpiece scores zero.
