# Frontend Redesign Prompt — copy/paste into a fresh Claude design session

---

Redesign the visual language of an existing product. **Keep every layout, route, component structure, and piece of functionality exactly as-is** — this is a pure re-skin: color, typography, motion, texture, iconography, and micro-interactions only. Do not add, remove, or rearrange any screen, panel, or feature.

## What the product is

Codexa OS — an engineering-intelligence platform for software teams. A FastAPI backend maintains a live knowledge graph of a codebase (files, functions, call graph, dependencies); a Next.js/React frontend lets engineers explore it. The signature feature is a live 3D force-directed graph of the codebase, and a "blast radius" feature that computes what breaks downstream before letting an AI agent make a change — this is the product's core trust mechanic and should feel like the most important, most confidence-inspiring surface in the app, not a buried utility screen.

Pages/surfaces (all keep their current layout): a centered chat home with a composer and conversation history sidebar; a full-screen 3D knowledge graph with a search box and legend; an agent network view; a repository health-score view with metric breakdowns and written analysis; an in-app code viewer with file tree and syntax highlighting; a time-machine view that scrubs the graph's history on a slider; an architecture diagram view with trend metrics; a documentation view. Standard app shell: a left icon rail for navigation, page headers with an eyebrow/title pattern.

Stack constraints (design within these, don't fight them): Next.js App Router, Tailwind CSS v4, Framer Motion for animation, `@react-three/fiber` for the 3D graph, Shiki for code syntax highlighting.

## What to move away from

The current design is a warm-neutral, light, glassmorphism-adjacent look: off-white paper background, near-black ink text, a single muted teal accent reserved only for "live/active" state, a small amount of muted gold, Space Grotesk for display type paired with IBM Plex Sans for body and IBM Plex Mono for numerals/status lines, soft rounded cards, subtle shadows, curved bezier edges in the graph. It's clean but safe — commit to a genuinely different direction, not a palette swap of the same bones.

## What "best possible" means here

- **Avoid generic AI-generated SaaS aesthetics**: no default purple-to-blue gradients, no generic glassmorphism-for-its-own-sake, no Inter/system-font-and-call-it-done, no interchangeable rounded-card-grid-with-soft-shadow template look. If it could be any AI startup's landing page, it's wrong.
- **Pick one real point of view and commit to it** — don't hedge between three directions. Consider (and pick, don't blend) something like: a precise technical/blueprint aesthetic (grid-driven, monospace-forward, engineering-instrument feel — think oscilloscope/flight-deck, not "dark mode #4"); or a confident editorial-print aesthetic (strong type contrast, deliberate whitespace, ink-on-paper feel pushed further than the current attempt); or a raw terminal/systems aesthetic (CRT-adjacent, high-contrast, monospace-dominant, restrained color used only as signal). Whatever direction is chosen, it should feel inevitable for a tool whose whole premise is "you can trust what this graph tells you," not decorative.
- **The 3D graph and the blast-radius risk gate are the two moments that should feel unmistakably signature** — describe specific treatment for both (how nodes/edges render and animate, how the risk card reveals itself and communicates severity) rather than leaving them as generic instances of the general system.
- **Motion should have a point of view, not just "add transitions everywhere."** Specify actual easing curves, durations, and a rationale (e.g., "state changes settle with a slight overshoot to feel alive," or "everything is linear and mechanical to reinforce the instrument-panel feel" — pick one, don't default to material-design-standard easing without a reason).
- **Typography pairing should be deliberate**, not "one geometric sans for headings, one humanist sans for body" (the current safe default). Justify the pairing against the product's personality.
- **Color discipline**: this app currently reserves its one accent color exclusively for "live/active/selected" state so it stays meaningful. Keep that discipline (or replace it with an equally deliberate rule) — don't let color become decorative noise across a data-dense interface.

## What to deliver

1. A short statement of the chosen direction and why it fits an engineering-trust product (2-4 sentences, not a mood-board essay).
2. A concrete design system: color tokens with their usage rules (as CSS custom properties), the type system (families, weights, scale, pairing rationale), spacing/radius/shadow tokens, and the motion system (named easing curves + durations + when each is used).
3. Specific treatment notes for: the 3D graph (node/edge rendering, color encoding, hover/select states), the blast-radius risk card (how it reveals risk level and severity), the chat interface (message bubbles, the "thinking" state), and the left navigation rail.
4. Enough detail that a developer could implement it directly in Tailwind v4 + Framer Motion without further design decisions being needed.

Do not write implementation code yet — first present the direction and system for review.
