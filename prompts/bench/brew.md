Build a single self-contained HTML page called BREW: a small reference for fourteen ways to make coffee.

One file, `index.html`. No dependencies except Google Fonts.

Content: fourteen real brewing methods — pour-over, French press, moka pot, AeroPress, cold brew, espresso, and so on. Each needs a name, an origin (country and rough decade), a grind size, a brew time, a coffee-to-water ratio, and two sentences on what it tastes like and who it suits. Invent plausible specifics where you need to; no placeholder text and no "Method 1".

Three behaviours the page must actually have:

1. Filtering by grind size — coarse, medium, fine — that hides the methods that do not match and moves the remaining ones into their new positions. A count updates as it changes.
2. Clicking a method opens its full record, and closing returns to the list without losing the current filter.
3. A brew-time sort that reorders the list, with the order reversing on a second click.

All three must work when clicked, not merely exist in the markup. Every interactive element needs a visible focus ring and a hover state, and the page must honour prefers-reduced-motion.

Choose the design direction yourself — typography, colour, density, motion, the lot. Commit to one and carry it through the whole page rather than mixing several. Whatever you choose, the result should look like someone decided it on purpose.

When the page is written, run it, look at it, and fix what is actually broken or unfinished. Then look once more.
