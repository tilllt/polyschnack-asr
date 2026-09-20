/**
 * Change 218 (Nutzer-Befund 20.09.2026, wörtlich):
 *   „Die Markierung des aktives Wortes im Timing Modus hat immer noch Ränder
 *    oben und unten. Sollte nur rechts und links haben.
 *    Die Transition von aktivem Wort zu Nachbarn ist unschnell und sollte auch
 *    ease out haben."
 *
 * Warum diese Tests am QUELLTEXT hängen (index.css bzw. WaveformPlayer.tsx) und
 * nicht am gerenderten DOM: jsdom rechnet keine Kaskade und keine Schatten — es
 * kann weder einen Inline-Rahmen gegen eine !important-Regel aufrechnen noch
 * feststellen, ob links/rechts eine Kante gezeichnet wird. Genau dieser
 * Wettstreit war aber die Ursache des zweiten Fehlschlags. Deshalb wird hier die
 * Zusicherung geprüft, die zählt: die Regeln selbst (Wortlaut, !important,
 * Werte) — dieselben Regeln, die nach dem Bau in dist/assets/*.css stehen.
 *
 * Belegte Ursachen (Details in den Kommentaren der Dateien):
 *   1. Der Rahmen oben/unten kam aus unserem eigenen Inline-Stil
 *      (`el.style.border = "2px solid rgba(46,160,67,0.95)"` in
 *      WaveformPlayer.tsx). Inline schlägt jede normale Klassenregel — die
 *      frühere CSS-Gegenmaßnahme (`.ps-timing-region { border: 0 !important }`)
 *      war deshalb ein Wettstreit und zusätzlich nur wirksam, wenn genau diese
 *      Datei ausgeliefert wurde.
 *   2. Der Flächen-Übergang war ebenfalls wirkungslos: WaveSurfer schreibt beim
 *      Erzeugen jeder Region `transition: background-color 0.2s ease` inline ans
 *      Element (RegionsPlugin.initElement) — die Klassenregel (200 ms ease-out)
 *      kam nie zum Zug. Sichtbar war immer 200 ms mit `ease` (schnell los, also
 *      „unschnell").
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { TIMING_COLOR_EASE, TIMING_COLOR_MS, TIMING_MOTION_MS } from "./WaveformPlayer";

/** Pfad zu einer Datei neben diesem Test — je nach Laufzeit (Node oder Vitest). */
function nebenDatei(relativ: string): string {
  const hier = import.meta.url;
  if (hier.startsWith("file:")) {
    return fileURLToPath(new URL(relativ, hier));
  }
  // Vitest lädt Module über eine eigene Laufzeit (keine file:-URL). Dort ist
  // das Arbeitsverzeichnis der Frontend-Ordner (dort liegt vite.config.ts).
  return `src/components/${relativ}`;
}

const CSS = readFileSync(nebenDatei("../index.css"), "utf8");

/** Code ohne Kommentare — geprüft wird, was ausgeführt wird, nicht was im
 *  Kommentar als alter Zustand zitiert ist (der alte Inline-Rahmen steht dort
 *  als Erklärung im Wortlaut). */
const TSX_CODE = readFileSync(nebenDatei("WaveformPlayer.tsx"), "utf8")
  .replace(/\/\*[\s\S]*?\*\//g, "")
  .replace(/^\s*\/\/.*$/gm, "");

// ── Mini-CSS-Parser (nur was hier gebraucht wird) ───────────────────────
interface Rule {
  selectors: string[];
  body: string;
  media: string | null;
}

function parse(cssText: string, media: string | null, out: Rule[]): Rule[] {
  let i = 0;
  while (i < cssText.length) {
    const open = cssText.indexOf("{", i);
    if (open < 0) break;
    const prelude = cssText.slice(i, open).trim();
    let depth = 0;
    let end = open;
    for (; end < cssText.length; end += 1) {
      if (cssText[end] === "{") depth += 1;
      else if (cssText[end] === "}") {
        depth -= 1;
        if (depth === 0) break;
      }
    }
    const body = cssText.slice(open + 1, end);
    if (prelude.startsWith("@")) parse(body, prelude, out);
    else if (prelude) {
      out.push({ selectors: prelude.split(",").map((s) => s.trim()), body, media });
    }
    i = end + 1;
  }
  return out;
}

const OHNE_KOMMENTARE = CSS.replace(/\/\*[\s\S]*?\*\//g, "");
const RULES = parse(OHNE_KOMMENTARE, null, []);

/** Alle Deklarationen (property → value) aller Regeln, deren Selektor passt. */
function decls(sel: string, opts: { media?: string | null } = {}) {
  const treffer: Array<{ selector: string; prop: string; value: string; media: string | null }> = [];
  for (const r of RULES) {
    if (opts.media !== undefined && r.media !== opts.media) continue;
    for (const s of r.selectors) {
      if (s !== sel) continue;
      for (const d of r.body.split(";")) {
        const t = d.trim();
        if (!t) continue;
        const idx = t.indexOf(":");
        if (idx < 0) continue;
        treffer.push({
          selector: s,
          prop: t.slice(0, idx).trim().toLowerCase(),
          value: t.slice(idx + 1).trim(),
          media: r.media,
        });
      }
    }
  }
  return treffer;
}

/** Schatten einer box-shadow-Deklaration, an Kommas AUSSERHALB von Klammern. */
function schatten(value: string): string[] {
  const teile: string[] = [];
  let tiefe = 0;
  let cur = "";
  for (const ch of value) {
    if (ch === "(") tiefe += 1;
    if (ch === ")") tiefe -= 1;
    if (ch === "," && tiefe === 0) {
      teile.push(cur.trim());
      cur = "";
      continue;
    }
    cur += ch;
  }
  if (cur.trim()) teile.push(cur.trim());
  return teile;
}

/** Längen-Token eines Schattens, in Reihenfolge: x, y, blur, spread. */
function offsets(shadow: string): number[] {
  const ohneInset = shadow.replace(/\binset\b/gi, " ");
  // rgba(...)/#hex/var(...) darf nicht als Länge zählen → alles ab dem Farbteil weg.
  const farbe = ohneInset.search(/rgba?\(|#|var\(/);
  const kopf = farbe >= 0 ? ohneInset.slice(0, farbe) : ohneInset;
  const kopfZahlen = kopf.match(/-?\d*\.?\d+(px)?/g) ?? [];
  return kopfZahlen.map((z) => parseFloat(z));
}

describe("Change 218 — Markierung: Kanten nur links/rechts, oben/unten keine", () => {
  const regionRules = RULES.filter((r) => r.selectors.some((s) => s.startsWith(".ps-timing-region")));

  it("die Fläche bekommt oben und unten ausdrücklich keine Kante (mit !important)", () => {
    const top = decls(".ps-timing-region").filter((d) => d.prop === "border-top");
    const bottom = decls(".ps-timing-region").filter((d) => d.prop === "border-bottom");
    expect(top.length).toBeGreaterThan(0);
    expect(bottom.length).toBeGreaterThan(0);
    // !important ist Pflicht: nur so schlägt die Regel einen Inline-Rahmen.
    for (const d of [...top, ...bottom]) {
      expect(d.value).toMatch(/^0\s*(px)?\s*!important$/);
    }
  });

  it("KEINE Regel gibt der Fläche eine waagerechte Kante (weder Longhand noch Shorthand)", () => {
    for (const r of regionRules) {
      for (const d of r.body.split(";")) {
        const t = d.trim().toLowerCase();
        if (!t) continue;
        const idx = t.indexOf(":");
        if (idx < 0) continue;
        const prop = t.slice(0, idx).trim();
        const value = t.slice(idx + 1).trim();
        if (prop === "border-top" || prop === "border-bottom") {
          expect(value, `${r.selectors.join(",")} → ${t}`).toMatch(/^0\s*(px)?(\s*!important)?$/);
        }
        if (prop === "border") {
          // Ein Shorthand mit Breite wäre wieder ein Ring — verboten.
          expect(value, `${r.selectors.join(",")} → ${t}`).toMatch(
            /^(0|none|0\s*(px)?)(\s*!important)?$/,
          );
        }
      }
    }
  });

  it("die seitlichen Kanten der aktiven Fläche liegen nur links/rechts (inset-Schatten, y=0)", () => {
    const shadows = decls(".ps-timing-region-active").filter((d) => d.prop === "box-shadow");
    expect(shadows.length).toBeGreaterThan(0);
    const alle = shadows.flatMap((d) => schatten(d.value));
    expect(alle.length).toBeGreaterThanOrEqual(2); // eine Kante links, eine rechts
    for (const s of alle) {
      expect(s, `Schatten ohne inset: ${s}`).toMatch(/\binset\b/);
      const [x, y] = offsets(s);
      expect(x === 0 && y === 0, `Schatten ohne Seitenversatz: ${s}`).toBe(false);
      // waagerechte Kante wäre y != 0 → ausdrücklich ausgeschlossen
      expect(y, `Schatten mit Kantenversatz nach oben/unten: ${s}`).toBe(0);
    }
  });

  it("auch die Nachbarflächen: Kanten-Regeln lassen links/rechts frei", () => {
    // Die gestrichelten Seitenkanten setzt der Code inline (`borderLeft/Right`,
    // siehe WaveformPlayer.tsx). Waagerecht darf auch hier nichts stehen.
    const nb = decls(".ps-timing-region-neighbor");
    for (const d of nb) {
      if (d.prop === "border-top" || d.prop === "border-bottom" || d.prop === "border") {
        expect(d.value, `.ps-timing-region-neighbor → ${d.prop}: ${d.value}`).toMatch(
          /^(0|none|0\s*(px)?)(\s*!important)?$/,
        );
      }
    }
    // Es gibt KEINE Regel mehr, die pauschal alle vier Kanten abschaltet
    // (das war Change 211 und schnitt die gewollten Seitenkanten mit ab).
    expect(OHNE_KOMMENTARE).not.toMatch(/\.ps-timing-region\s*\{[^}]*\bborder:\s*0\s*!important/);
  });

  it("WaveformPlayer setzt keinen vierkantigen Rahmen mehr (Ursache oben/unten)", () => {
    // Kein Inline-`border` mit Breite/Stil — egal an welchem Element.
    expect(TSX_CODE).not.toMatch(/style\.border\s*=\s*"[^"]*(?:px\s+(?:solid|dashed))/);
    expect(TSX_CODE).toMatch(/el\.style\.border\s*=\s*"none"/);
    expect(TSX_CODE).toMatch(/el\.style\.borderTop\s*=\s*"none"/);
    expect(TSX_CODE).toMatch(/el\.style\.borderBottom\s*=\s*"none"/);
    // Nachbar: Seitenkanten ausdrücklich, oben/unten ausdrücklich nicht.
    expect(TSX_CODE).toMatch(/nbEl\.style\.borderTop\s*=\s*"none"/);
    expect(TSX_CODE).toMatch(/nbEl\.style\.borderBottom\s*=\s*"none"/);
    expect(TSX_CODE).toMatch(/nbEl\.style\.borderLeft\s*=\s*"1px dashed/);
    expect(TSX_CODE).toMatch(/nbEl\.style\.borderRight\s*=\s*"1px dashed/);
  });
});

describe("Change 218 — Übergang aktives Wort ↔ Nachbar: länger und Ease-out", () => {
  const zahlen = (v: string) => (v.match(/-?\d*\.?\d+/g) ?? []).map(Number);

  it("Dauer ist größer als die alten 200 ms und als die Gleitfahrt (260 ms)", () => {
    expect(TIMING_COLOR_MS).toBeGreaterThan(200);
    expect(TIMING_COLOR_MS).toBeGreaterThan(TIMING_MOTION_MS);
  });

  it("Flächen-Regel: Dauer und Kurve wie im Code, mit !important (Inline-Übergang der Bibliothek)", () => {
    const t = decls(".ps-timing-region-active", { media: null }).filter(
      (d) => d.prop === "transition",
    );
    expect(t.length).toBeGreaterThan(0);
    for (const d of t) {
      expect(d.value).toContain(`${TIMING_COLOR_MS}ms`);
      expect(d.value).toMatch(/background-color/);
      expect(d.value.endsWith("!important")).toBe(true);
      const bezier = d.value.match(/cubic-bezier\(([^)]*)\)/);
      expect(bezier, d.value).toBeTruthy();
      const [x1, y1] = zahlen(bezier![1]);
      // Ease-out: der Weg läuft früh, das Ende läuft weich aus (y1 > x1).
      expect(y1, d.value).toBeGreaterThan(x1);
    }
    // Dieselbe Kurve steht auch als Konstante im Code (Wortgleichheit geprüft).
    expect(TIMING_COLOR_EASE).toContain("cubic-bezier");
    expect(t[0].value).toContain(TIMING_COLOR_EASE);
  });

  it("Nachbarfläche hat dieselbe Dauer/Kurve", () => {
    const t = decls(".ps-timing-region-neighbor", { media: null }).filter(
      (d) => d.prop === "transition",
    );
    expect(t.length).toBeGreaterThan(0);
    expect(t[0].value).toContain(`${TIMING_COLOR_MS}ms`);
    expect(t[0].value).toContain(TIMING_COLOR_EASE);
  });

  it("Wortbeschriftungen laufen mit denselben Zahlen", () => {
    for (const sel of [".ps-timing-word-active", ".ps-timing-word-neighbor"]) {
      const t = decls(sel).filter((d) => d.prop === "transition" && d.media === null);
      expect(t.length, sel).toBeGreaterThan(0);
      expect(t[0].value).toContain(`${TIMING_COLOR_MS}ms`);
      expect(t[0].value).toContain(TIMING_COLOR_EASE);
      expect(t[0].value).toMatch(/color/);
    }
  });

  it("reduzierte Bewegung: kein Übergang — und zwar !important (sonst verliert die Regel)", () => {
    const media = RULES.filter((r) => r.media?.includes("prefers-reduced-motion"));
    const treffer = media.filter((r) =>
      r.selectors.some((s) => s.startsWith(".ps-timing-region") || s.startsWith(".ps-timing-word")),
    );
    expect(treffer.length).toBeGreaterThan(0);
    const body = treffer.map((r) => r.body).join(";");
    expect(body).toMatch(/transition:\s*none\s*!important/);
  });
});

// ── Change 219 (Nutzer-Vorgabe 20.09.2026) ─────────────────────────────
// „Markierungen nur von oben bis zur Hälfte der Timeline" + „Die seitlichen
// Start/end Marker können über die ganze Höhe gehen."
//
// Warum zusätzlich zum DOM-Test (WaveformPlayer.markHeight.test.tsx) auch hier
// der Quelltext geprüft wird: das RegionsPlugin setzt `height`/`top` INLINE
// (regions.js: initElement 100 %, addResizeHandles 100 %). jsdom rechnet keine
// Kaskade — ob eine !important-Regel den Inline-Stil wirklich schlägt, ist nur
// am Regelwerk selbst und am ausgelieferten CSS prüfbar (genau der Mechanismus,
// an dem Change 211 gescheitert ist).
describe("Change 219 — halbe Höhe (Flächen) und volle Höhe (seitliche Kanten)", () => {
  const DETAIL_TSX = readFileSync(nebenDatei("DetailWaveformLayer.tsx"), "utf8");

  it("CSS: die Fläche ist 50 % hoch und klebt oben — mit !important (gegen Inline)", () => {
    const h = decls(".ps-mark-half").filter((d) => d.prop === "height");
    const top = decls(".ps-mark-half").filter((d) => d.prop === "top");
    expect(h.length).toBeGreaterThan(0);
    expect(top.length).toBeGreaterThan(0);
    expect(h.some((d) => d.value === "50% !important")).toBe(true);
    expect(top.some((d) => d.value === "0 !important" || d.value === "0px !important")).toBe(true);
  });

  it("CSS: seitliche Kanten 200 % — auch über den part-Selektor (Handles tragen keine Klassen)", () => {
    for (const sel of [
      '.ps-mark-half [part~="region-handle-left"]',
      '.ps-mark-half [part~="region-handle-right"]',
      '[part~="region-handle-left"]',
      '[part~="region-handle-right"]',
    ]) {
      const h = decls(sel).filter((d) => d.prop === "height");
      expect(h.length, sel).toBeGreaterThan(0);
      expect(h.some((d) => d.value === "200% !important"), sel).toBe(true);
    }
  });

  it("Code: setzt dieselben Werte INLINE beim Erzeugen der Region", () => {
    // Konstanten + Helfer im Quelltext …
    expect(TSX_CODE).toMatch(/TIMING_MARK_HEIGHT\s*=\s*"50%"/);
    expect(TSX_CODE).toMatch(/TIMING_HANDLE_HEIGHT\s*=\s*"200%"/);
    expect(TSX_CODE).toMatch(/el\.style\.height\s*=\s*TIMING_MARK_HEIGHT/);
    expect(TSX_CODE).toMatch(/h\.style\.height\s*=\s*TIMING_HANDLE_HEIGHT/);
    // … und für JEDE Flächen-Erzeugung aufgerufen: aktives Wort, Nachbarn,
    // Crop-Auswahl (Reihenfolge im Code: applyMarkGeometry(el)/(nbEl)/(cEl)).
    const aufrufe = TSX_CODE.match(/applyMarkGeometry\(/g) ?? [];
    expect(aufrufe.length).toBeGreaterThanOrEqual(4); // 1 Deklaration + 3 Aufrufe
    expect(TSX_CODE).toMatch(/applyMarkGeometry\(el\)/);
    expect(TSX_CODE).toMatch(/applyMarkGeometry\(nbEl\)/);
    expect(TSX_CODE).toMatch(/applyMarkGeometry\(cEl\)/);
  });

  it("die obere Hälfte fängt Zeigerereignisse ab, die untere NICHT", () => {
    // Die Fläche selbst bleibt greifbar (Ziehen an den Kanten/der Fläche) …
    const pe = decls(".ps-mark-half").filter((d) => d.prop === "pointer-events");
    expect(pe.some((d) => d.value === "auto")).toBe(true);
    // … aber NICHTS darf dort blockieren: kein touch-action am Element, keine
    // Regel im Stylesheet, die das Wischen/Scrollen abfängt.
    expect(OHNE_KOMMENTARE).not.toMatch(/touch-action\s*:\s*none/);
    expect(TSX_CODE).not.toMatch(/touchAction/);
    // Der Detail-Overlay (liegt über der ganzen Wellenform) ist durchlässig —
    // sonst wäre die untere Hälfte trotz halber Markierungsfläche verdeckt.
    expect(DETAIL_TSX).toMatch(/pointer-events-none/);
  });

  it("die Fläche ist nicht mehr 100 % hoch (der alte Zustand ist belegt weg)", () => {
    // Weder über die Klasse noch über eine Höhen-Regel an .ps-timing-region.
    const h = decls(".ps-timing-region").filter((d) => d.prop === "height");
    for (const d of h) expect(d.value).not.toContain("100%");
    expect(OHNE_KOMMENTARE).not.toMatch(/\.ps-mark-half\s*\{[^}]*height\s*:\s*100%/);
  });
});
