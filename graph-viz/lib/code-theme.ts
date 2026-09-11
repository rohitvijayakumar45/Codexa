import type { ThemeRegistration } from "shiki";

/*
  Codexa's code view theme.

  The whole thing follows from one decision: BLUE IS NOT A SYNTAX COLOR. Blue is the agent.

  Every blue mark in the code view means Codexa touched this — the attribution stripe, the streaming
  caret, the selection, the blast-radius rail. Standard themes spend their brightest hue on keywords
  or function names; here that hue answers the question you actually have when you open a file after
  a 120-round job (what is mine and what is the agent's?) before you read a single token.

  That constraint forces a reduced palette, which is the right outcome anyway: four hues, with
  functions and classes carrying WEIGHT instead of a fifth and sixth color. Rainbow themes encode
  language grammar you already know; this one spends its color on the thing you don't.

    violet  keywords, control flow, imports   — the language itself
    green   strings and literal text          — your content
    rust    numbers, booleans, constants      — same family as the reasoning signal, because
                                                thresholds and budgets are what you scan for
    muted   comments                          — upright, never italic: this codebase runs
                                                twelve-line comment blocks and italics punish them
*/

const LIGHT = {
  bg: "#fbfcfe",
  ink: "#1b2430",
  mute: "#8592a3",
  violet: "#7a3fb5",
  green: "#12705a",
  rust: "#a8551f",
  danger: "#b3261e",
};

/*
  Noir's code grounds. Two constraints shape these values beyond simply "lighter versions of the
  light theme":

  1. Claret is spoken for. It is the theme's signal, which in the code view means agent authorship,
     so no syntax token may be red or pink — that would put "the agent wrote this" and "this is a
     string" in the same family. The four hues shift away from red accordingly.
  2. A near-neutral black leaves nowhere to hide low-chroma tokens, so each hue is pushed slightly
     brighter than its Blueprint counterpart to clear the ground without any of them halating.
*/
const DARK = {
  bg: "#0c0c0d",
  ink: "#e4e1db",
  mute: "#6f6f76",
  violet: "#b79bf5",
  green: "#63c9a4",
  rust: "#d9a94a",
  danger: "#f0603a",
};

function build(name: string, type: "light" | "dark", c: typeof LIGHT): ThemeRegistration {
  return {
    name,
    type,
    colors: {
      "editor.background": c.bg,
      "editor.foreground": c.ink,
    },
    settings: [
      { settings: { background: c.bg, foreground: c.ink } },

      // comments — muted, and explicitly upright
      {
        scope: ["comment", "punctuation.definition.comment", "string.comment"],
        settings: { foreground: c.mute, fontStyle: "" },
      },

      // the language itself
      {
        scope: [
          "keyword",
          "storage",
          "storage.type",
          "storage.modifier",
          "keyword.control",
          "keyword.operator.new",
          "keyword.operator.expression",
          "keyword.operator.logical",
          "constant.language",
          "variable.language",
          "entity.name.tag",
          "punctuation.definition.keyword",
        ],
        settings: { foreground: c.violet },
      },

      // your content
      {
        scope: ["string", "string.quoted", "string.template", "punctuation.definition.string", "meta.attribute-selector"],
        settings: { foreground: c.green },
      },

      // the values you scan for
      {
        scope: ["constant.numeric", "constant.character", "constant.other", "support.constant"],
        settings: { foreground: c.rust },
      },

      // names get weight, not hue — this is what keeps the palette at four colors
      {
        scope: [
          "entity.name.function",
          "support.function",
          "meta.function-call.generic",
          "entity.name.class",
          "entity.name.type",
          "support.class",
          "support.type",
        ],
        settings: { foreground: c.ink, fontStyle: "bold" },
      },

      // everything structural recedes
      {
        scope: ["punctuation", "meta.brace", "keyword.operator", "meta.delimiter"],
        settings: { foreground: c.mute },
      },

      // identifiers sit at the base ink, which is most of the file
      {
        scope: ["variable", "variable.other", "meta.definition.variable", "entity.name.namespace"],
        settings: { foreground: c.ink },
      },

      { scope: ["invalid", "invalid.illegal"], settings: { foreground: c.danger } },
    ],
  };
}

export const codexaLight = build("codexa-blueprint", "light", LIGHT);
export const codexaDark = build("codexa-noir", "dark", DARK);
