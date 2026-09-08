Build a single self-contained HTML page called TIDEPOOL: a field guide to twelve rock-pool creatures.

Keep it small and finish it. One file, `index.html`, roughly 300–500 lines. No external dependencies except Google Fonts.

Content: twelve real creatures — anemone, hermit crab, blenny, limpet, and so on — each with a common name, a Latin binomial, a depth range in centimetres, a tide-zone label, and two sentences of description. Invent plausible specifics; no placeholder text, no "Creature 1".

Design: a light, calm, field-notebook feel. Warm paper background, ink-dark text, one restrained accent. A serif for names and body, a small-caps or monospace treatment for the data (depths, zones, binomials). Hairline rules rather than boxes. Generous whitespace.

Two behaviours the page must actually have:

1. Filtering by tide zone that reorganises the list — clicking a zone hides the creatures that do not belong and the remaining ones move into their new positions. A count updates.
2. Clicking a creature opens a detail view showing its full record, and closing it returns to the list.

Both must work when clicked, not merely exist in the markup. Give every interactive element a visible focus ring and a hover state, and honour prefers-reduced-motion.

When the page is written, run it and look at it. Fix anything that is broken or obviously unfinished, then check it once more.
