# shadcn/ui

## What it actually is

shadcn/ui is NOT a component library you `npm install` and import from. It's a CLI that copies
component *source code* directly into your project (Radix UI primitives underneath, styled with
Tailwind, variants managed by `class-variance-authority`). Once copied in, the components are
yours — edit them directly, no fighting an opaque node_modules package for a one-off override.

This matters for how an agent should use it: don't hand-write JSX that imitates shadcn's look.
Run the real CLI inside the target project via `run_command`, then edit the generated files.

## Setup (run inside the project, not this platform's own source)

```
npx shadcn@latest init
```
Answers a short prompt (or accept `components.json` defaults): style (`new-york` is the current
default — tighter, more restrained than the older `default` style; prefer `new-york` for anything
described as "premium" or "minimal"), base color, CSS variables vs. Tailwind utility classes for
theming (CSS variables is the standard choice — makes dark mode and runtime theme switching trivial
without touching component code).

Then add components as needed, one at a time:
```
npx shadcn@latest add button dialog dropdown-menu card
```
Each command writes real `.tsx` files into `components/ui/` — inspect what actually landed before
assuming an API; don't guess prop names from memory of other versions.

## Theming

Colors live as HSL CSS custom properties on `:root` / `.dark` (e.g. `--primary`, `--background`,
`--muted-foreground`), referenced from `tailwind.config` via `hsl(var(--primary))`. To apply a
specific palette (a client's brand, or a restrained accent color from a design brief), edit these
CSS variables directly — never hardcode a hex value inside a copied component; that defeats the
whole point of the token layer and breaks dark-mode automatically.

## Where it fits against the other skills here

shadcn/ui gives you correct, accessible, keyboard-navigable PRIMITIVES (dialog focus-trapping,
combobox ARIA, etc.) essentially for free — real engineering value, not just aesthetics. It does
NOT give you a finished visual identity: out of the box its neutral grays and default spacing read
as competent-but-generic. Pair it with a visual-style skill (apple_design, high_end_agency,
minimalist_editorial) for the actual look, and emil_design_eng / animate for the interaction polish
— shadcn solves "is this accessible and correctly behaved," not "does this feel premium."

## When to reach for it vs. hand-rolled markup

Use it for anything with real interaction complexity where getting the behavior wrong is an actual
bug, not just a style miss: dialogs/sheets, dropdown/select menus, comboboxes, date pickers, toasts,
tooltips, tabs, accordions. For a static display element with no focus management or keyboard
semantics (a stat card, a progress ring, a plain badge), hand-rolled markup styled directly is
simpler and no less correct — don't reach for the CLI just to wrap a `<div>`.
