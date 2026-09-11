import type { Metadata } from "next";
import { Funnel_Display, Geist, Geist_Mono, Bricolage_Grotesque, Manrope, JetBrains_Mono } from "next/font/google";
import { Providers } from "./providers";
import "./globals.css";

// Blueprint's type stack. Character lives ONLY at display sizes — Funnel Display is tight and
// opinionated, which is what pulls a cool blue-grey engineering ground away from generic
// drafting-office. Everywhere density lives (rails, tables, telemetry, code) the type gets out of
// the way: Geist was drawn for product UI (tall x-height, unambiguous 1lI0O, real tabular figures)
// and Geist Mono is its designed companion, so numbers and code sit coherently with body copy
// instead of looking bolted on. All three are variable, so one file each covers the whole range.
const funnelDisplay = Funnel_Display({
  subsets: ["latin"],
  variable: "--font-funnel",
  display: "swap",
});

const geist = Geist({
  subsets: ["latin"],
  variable: "--font-geist",
  display: "swap",
});

const geistMono = Geist_Mono({
  subsets: ["latin"],
  variable: "--font-geist-mono",
  display: "swap",
});

// Second, hot-swappable type family — the "Aurora" workspace theme. Loaded alongside the default
// pairing (not replacing it) so the theme toggle can flip between them instantly, no reload.
const bricolage = Bricolage_Grotesque({
  subsets: ["latin"],
  weight: ["500", "600", "700", "800"],
  variable: "--font-bricolage",
  display: "swap",
});

const manrope = Manrope({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-manrope",
  display: "swap",
});

const jbMono = JetBrains_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-jbmono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Codexa OS — Engineering Brain",
  description:
    "Live visualization of the Codexa engineering knowledge graph: code, architecture, causal history, and confidence.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html
      lang="en"
      className={`${funnelDisplay.variable} ${geist.variable} ${geistMono.variable} ${bricolage.variable} ${manrope.variable} ${jbMono.variable}`}
    >
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
