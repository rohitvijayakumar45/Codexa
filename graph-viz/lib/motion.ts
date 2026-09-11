import type { Transition, Variants } from "framer-motion";

/*
  Codexa's motion system.

  Everything a user can touch is a spring, because a spring animates from wherever the element
  currently IS rather than from a scripted start value — which means it can be grabbed, redirected
  and reversed mid-flight without a visible jump. Fixed-duration easing cannot do that, and this
  product's whole subject is live execution: rounds landing, tasks advancing, plans re-shaping
  while you watch. That is exactly the content that dies under a schedule.

  Two parameters, following Apple's designer-facing spring model rather than mass/stiffness/damping:

    bounce    overshoot. 0 = critically damped, settles without oscillating. Higher = bouncier.
    duration  how quickly it reaches the target. NOT a fixed runtime — a spring has no fixed
              runtime; its settle time emerges from the parameters.

  The rule for when bounce is allowed: only when the gesture itself carried momentum. Overshoot on
  a panel that merely appeared reads as a glitch; overshoot on a node you flicked reads as physics.
*/

/** Route and panel changes. Navigation should feel decisive, never springy. */
export const springPanel: Transition = { type: "spring", bounce: 0, duration: 0.4 };

/** A task advancing, a status flipping. State change, not a physical throw. */
export const springState: Transition = { type: "spring", bounce: 0, duration: 0.3 };

/** Released after a drag. The gesture carried momentum, so the settle may carry it too. */
export const springThrow: Transition = { type: "spring", bounce: 0.2, duration: 0.4 };

/** Sheets, dialogs, the command palette. Enters from its trigger, exits along the same path. */
export const springSheet: Transition = { type: "spring", bounce: 0.15, duration: 0.3 };

/*
  Streaming text is the one place motion is banned outright. Never translate type while it is being
  read — moving a line the eye is tracking is hostile. Opacity only, and fast.
*/
export const fadeIn: Transition = { duration: 0.12, ease: "linear" };

/** Layout reflow for lists that reorder — FLIP handled by Motion's `layout` prop. */
export const springLayout: Transition = { type: "spring", bounce: 0, duration: 0.35 };

/*
  Reveal variants. Parent staggers, children rise. Kept small: 8px, not 24 — a workspace is opened
  dozens of times a day and a big entrance gets old on the third viewing.
*/
export const revealParent: Variants = {
  hidden: {},
  show: { transition: { staggerChildren: 0.05 } },
};

export const revealChild: Variants = {
  hidden: { opacity: 0, y: 8 },
  show: { opacity: 1, y: 0, transition: springPanel },
};

/** Rows entering a live list (a tool call landing, a task starting). */
export const rowEnter: Variants = {
  hidden: { opacity: 0, y: -4 },
  show: { opacity: 1, y: 0, transition: springState },
  exit: { opacity: 0, transition: fadeIn },
};
