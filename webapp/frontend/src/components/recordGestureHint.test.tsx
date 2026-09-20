/**
 * Change 216 (Nutzer-Vorgabe 20.09.2026) — die Gestenhinweise am Aufnahmeknopf
 * liegen als halbtransparente Kopie ÜBER dem Knopf.
 * Change 218 (Nutzer-Vorgabe 20.09.2026) — vier Nachbesserungen (Deckkraft,
 * Weg, gebogener Text, Überblenden).
 * Change 219 (Nutzer-Vorgabe 20.09.2026) — sechs Nachbesserungen, hier geprüft:
 *   (1) ECHTER KREIS statt Ellipse (rx == ry, ein Radius in beiden Achsen);
 *   (2) pro Hinweis GENAU EIN Aus- und EIN Einblenden (kein doppeltes
 *       Aufblenden — die Geste wechselt nicht mehr, während die Kopie
 *       sichtbar ist);
 *   (3) der Text dreht langsam um den Knopf, bei reduzierter Bewegung nicht;
 *   (4) alle vier Hinweise haben dieselbe Deckkraft und Farbe;
 *   (5) der Puls geht ausschließlich nach außen (kein scale < 1);
 *   (6) Ein-/Ausblendzeiten länger als die alten 180 / 220 ms.
 *
 * jsdom rechnet keine CSS-Dateien aus und kann keine Pixel messen. Geprüft
 * wird deshalb dreierlei:
 *   1. die gerenderte Struktur — Knopf und Kopie liegen im selben Rahmen
 *      (`.ps-record-stage`), die Kopie trägt exakt dieselben Größen- und
 *      Formklassen wie der Knopf, der Text steht in einem `<textPath>` in einer
 *      drehenden `<g>`, und beim Wechsel des Hinweises wird der Knopf-DOM-Knoten
 *      NICHT neu aufgebaut (kein key, gleiche Klassen, gleiche Kindreihenfolge);
 *   2. die CSS-Werte in src/index.css — Deckkraft, Füllung, Bewegungsweite
 *      (nur nach außen), Überblendzeiten, Drehung und das Standbild bei
 *      reduzierter Bewegung;
 *   3. die Geometrie des Kreises — aus dem tatsächlich gerenderten `d`-Attribut
 *      gegen die festen Maße der Zone gerechnet (kein Abschneiden, keine
 *      Überlappung mit Knopf oder Zonenrand, Umfang reicht für den längsten
 *      Hinweis).
 * Die Pixel im Browser wurden zusätzlich im echten Browser gemessen.
 */
import { act, render } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import {
  RECORD_ARC,
  RECORD_ARC_PATH_D,
  RECORD_ARC_PATH_ID,
  RECORD_ARC_SPIN_CLASS,
  RECORD_ARC_SPIN_MS,
  RECORD_BUTTON_SHAPE,
  RECORD_GESTURE_TIPS,
  RecordGestureHint,
  TIP_FADE_IN_MS,
  TIP_FADE_OUT_MS,
  gestureTipAt,
} from "./RecordGestureHint";

/** Pfad zu index.css — je nach Laufzeit (Node oder Vitest-Laufzeit). */
function cssPfad(): string {
  const hier = import.meta.url;
  if (hier.startsWith("file:")) {
    return fileURLToPath(new URL("../index.css", hier));
  }
  return "src/index.css";
}

const css = readFileSync(cssPfad(), "utf8");

/** Nachbardatei im selben src-Verzeichnis (z. B. useLocale.ts). */
function quelle(name: string): string {
  return readFileSync(cssPfad().replace(/index\.css$/, name), "utf8");
}

/** Inhalt einer CSS-Regel ohne verschachtelte Blöcke. */
function rule(selector: string): string {
  const start = css.indexOf(selector);
  expect(start, `CSS-Regel „${selector}" fehlt in index.css`).toBeGreaterThan(-1);
  const open = css.indexOf("{", start);
  const close = css.indexOf("}", open);
  return css.slice(open + 1, close);
}

/** Ganzer Block einer Regel MIT verschachtelten Regeln (z. B. @keyframes). */
function block(selector: string): string {
  const start = css.indexOf(selector);
  expect(start, `CSS-Block „${selector}" fehlt in index.css`).toBeGreaterThan(-1);
  const ende = css.indexOf("\n}\n", start);
  expect(ende, `CSS-Block „${selector}" ist nicht geschlossen`).toBeGreaterThan(start);
  return css.slice(start, ende);
}

/** Alle Zahlen hinter einem Merkmal, z. B. translateY(-26px) → [-26]. */
function zahlen(text: string, merkmal: string): number[] {
  const treffer = new RegExp(`${merkmal}\\((-?[\\d.]+)`, "g");
  const werte: number[] = [];
  for (let m = treffer.exec(text); m; m = treffer.exec(text)) werte.push(Number(m[1]));
  return werte;
}

/** Alle Elemente einer Sorte (Name bleibt in Originalschreibweise). */
function tag(wurzel: Element, name: string): Element[] {
  return Array.from(wurzel.getElementsByTagName(name));
}

/** Knopfmitte und Maße aus dem gerenderten `d`-Attribut des Kreises. */
function bogengroesse() {
  const m = /^M (-?[\d.]+) (-?[\d.]+) A ([\d.]+) ([\d.]+) 0 0 1 (-?[\d.]+) (-?[\d.]+)$/.exec(
    RECORD_ARC_PATH_D
  );
  expect(m, `d-Attribut des Kreises unerwartet: ${RECORD_ARC_PATH_D}`).toBeTruthy();
  const [, x1, y1, rx, ry, x2, y2] = m as unknown as string[];
  return {
    x1: Number(x1),
    y1: Number(y1),
    x2: Number(x2),
    y2: Number(y2),
    rx: Number(rx),
    ry: Number(ry),
  };
}

/** Bogenlänge einer Ellipse zwischen zwei Winkeln (Bogenmaß) — Zahlenintegral. */
function bogenlaenge(rx: number, ry: number, von: number, bis: number, n = 4000): number {
  const f = (t: number) => Math.sqrt(rx * rx * Math.sin(t) ** 2 + ry * ry * Math.cos(t) ** 2);
  let summe = 0;
  for (let i = 0; i < n; i++) {
    const t1 = von + ((bis - von) * i) / n;
    const t2 = von + ((bis - von) * (i + 1)) / n;
    summe += ((f(t1) + f(t2)) / 2) * ((bis - von) / n);
  }
  return summe;
}

/** Feste Maße der Zone aus index.css — die kleinste Stufe ist die engste. */
function zonenmasse() {
  const hoehe = Number(/--ps-zone-h:\s*(\d+)px/.exec(css)?.[1]);
  const innenabstand = Number(/\.ps-zone\s*\{[^}]*?padding:\s*(\d+)px/.exec(css)?.[1]);
  const rand = Number(/\.ps-zone\s*\{[^}]*?border:\s*(\d+)px/.exec(css)?.[1]);
  expect(hoehe).toBeGreaterThan(0);
  expect(innenabstand).toBeGreaterThan(0);
  expect(rand).toBeGreaterThan(0);
  return { hoehe, innenabstand, rand };
}

/**
 * Längster Hinweistext aller Sprachen, direkt aus dem Textkatalog gelesen —
 * so hängt die Umfangsprüfung nicht an einer abgeschriebenen Zahl.
 */
function laengsterHinweis(): { text: string; zeichen: number } {
  const katalog = quelle("useLocale.ts");
  const treffer = Array.from(
    katalog.matchAll(/gesture_(?:lock_up|stop_down|hold|release_pause):\s*"([^"]+)"/g)
  ).map((m) => m[1]);
  expect(treffer.length, "Hinweistexte im Katalog nicht gefunden").toBeGreaterThanOrEqual(12);
  const text = treffer.reduce((a, b) => (b.length > a.length ? b : a));
  return { text, zeichen: text.length };
}

/** Knopfgröße der kleinsten Stufe in px (w-16 h-16) bzw. ab 640 px (w-20 h-20). */
const KNOPF_MOBIL = 64;
const KNOPF_AB_640 = 80;
/** Mittlere Zeichenbreite in em — Erfahrungswert der bisherigen Rechnung (185 px/35). */
const ZEICHENBREITE_EM = 0.53;

/**
 * Bildet den echten Aufbau nach: der Knopf liegt im Fluss, die Kopie absolut
 * darüber. Die Knopfklassen kommen aus derselben Konstante wie im echten Code.
 */
function renderBuehne(tipIdx: number, label = "nach oben wischen: Aufnahme sperren") {
  const baum = (idx: number, text: string) => (
    <div className="ps-tab-body">
      <div className="ps-record-stage" data-testid="record-stage">
        <button
          type="button"
          data-testid="record-button"
          className={`ps-record-btn ${RECORD_BUTTON_SHAPE} bg-accent`}
        />
        <RecordGestureHint tipIdx={idx} label={text} />
      </div>
    </div>
  );
  const utils = render(baum(tipIdx, label));
  return { ...utils, neu: (idx: number, text: string) => utils.rerender(baum(idx, text)) };
}

/** Bereiche im CSS, die für „reduzierte Bewegung" gelten. */
function reduzierteBewegungBlock(): string {
  const start = css.indexOf(
    "@media (prefers-reduced-motion: reduce)",
    css.indexOf(".ps-record-ghost {")
  );
  expect(start).toBeGreaterThan(-1);
  const ende = css.indexOf("\n}\n", start);
  expect(ende).toBeGreaterThan(start);
  return css.slice(start, ende);
}

/** Schaltet window.matchMedia auf „reduzierte Bewegung" um. */
function reduzierteBewegungAn(): void {
  window.matchMedia = ((frage: string) => ({
    matches: frage.includes("reduced-motion"),
    media: frage,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia;
}

/** Stellt window.matchMedia nach jedem Test wieder her. */
const matchMediaOriginal = window.matchMedia;
afterEach(() => {
  window.matchMedia = matchMediaOriginal;
  vi.useRealTimers();
});

describe("Change 216/218/219 — Gestenhinweise als halbtransparente Knopfkopie", () => {
  test("die Kopie hat dieselbe Größe und Form wie der Knopf", () => {
    const { getByTestId } = renderBuehne(0);
    const knopf = getByTestId("record-button");
    const kopie = getByTestId("record-ghost");
    // Alle Größen-/Formklassen des Knopfes stehen auch auf der Kopie.
    for (const token of RECORD_BUTTON_SHAPE.split(" ")) {
      expect(kopie.classList.contains(token), `Klasse ${token} fehlt`).toBe(true);
      expect(knopf.classList.contains(token)).toBe(true);
    }
    // Kreisform zusätzlich aus dem CSS (unabhängig von Tailwind).
    expect(rule(".ps-record-ghost {")).toContain("border-radius: 999px");
  });

  test("die Kopie liegt im selben Rahmen wie der Knopf, direkt nach ihm", () => {
    const { getByTestId } = renderBuehne(0);
    const stage = getByTestId("record-stage");
    const knopf = getByTestId("record-button");
    const kopie = getByTestId("record-ghost");
    const hinweis = getByTestId("record-tip");
    expect(knopf.parentElement).toBe(stage);
    expect(kopie.parentElement).toBe(stage);
    expect(hinweis.parentElement).toBe(stage);
    // Der Knopf ist das erste Element — die Kopie kann ihn nicht verdrängen.
    expect(stage.firstElementChild).toBe(knopf);
  });

  test("die Kopie ist absolut positioniert, halbtransparent und ohne Klicks", () => {
    const ghost = rule(".ps-record-ghost {");
    expect(ghost).toContain("position: absolute");
    expect(ghost).toContain("inset: 0");
    expect(ghost).toContain("opacity: 0.85");
    expect(ghost).toContain("pointer-events: none");
    expect(ghost).toContain("z-index: 1");
    // Der Rahmen ist genau so groß wie der Knopf: nur der Knopf liegt im Fluss.
    expect(rule(".ps-record-stage {")).toContain("position: relative");
    expect(rule(".ps-record-tip {")).toContain("position: absolute");
    // Die Zone behält ihre feste Höhe (Regel aus Change 215) — der Kreis darf
    // über den Knopf hinausreichen, aber nichts als Höhengeber wirken.
    expect(rule(".ps-record-tip {")).toContain("height: 68px");
    expect(rule(".ps-record-tip {")).not.toContain("height: auto");
  });

  test("die Kopie ist sichtbarer als vorher, verdeckt den Knopf aber nicht", () => {
    // Vorher 0,55 (Change 216) — jetzt deutlich mehr, aber nicht 1: sonst
    // wäre der echte Knopf darunter nicht mehr zu sehen.
    const deckkraft = Number(/opacity:\s*([\d.]+)/.exec(rule(".ps-record-ghost {"))?.[1]);
    expect(deckkraft).toBeGreaterThan(0.55);
    expect(deckkraft).toBeGreaterThanOrEqual(0.8);
    expect(deckkraft).toBeLessThan(1);

    // Die Fläche der Kopie bleibt schwach gefüllt: der Knopf scheint durch.
    const flaechenRegeln = [
      ".ps-record-ghost {",
      ".ps-ghost-lock {",
      ".ps-ghost-stop {",
      ".ps-ghost-sink {",
      ".ps-ghost-rise {",
    ];
    let gefunden = 0;
    for (const sel of flaechenRegeln) {
      const alphas = Array.from(rule(sel).matchAll(/rgba\(\s*\d+,\s*\d+,\s*\d+,\s*([\d.]+)\s*\)/g)).map(
        (m) => Number(m[1])
      );
      gefunden += alphas.length;
      for (const a of alphas) expect(a, `${sel} füllt zu stark`).toBeLessThan(0.3);
    }
    expect(gefunden, "keine Füllfarben gefunden — Test prüft nichts").toBeGreaterThanOrEqual(5);
  });

  test("(Punkt 4) alle vier Hinweise sind gleich sichtbar — Text und Kopie", () => {
    const gesten = [".ps-ghost-lock {", ".ps-ghost-stop {", ".ps-ghost-sink {", ".ps-ghost-rise {"];

    // Der Text hat genau EINE Quelle für Farbe, Deckkraft und Schriftgröße.
    expect(
      css.split(".ps-record-arc-text {").length - 1,
      "mehr als eine Regel für den Hinweistext"
    ).toBe(1);
    const text = rule(".ps-record-arc-text {");
    expect(text).toContain("font-size: 9px");
    expect(text).toContain("opacity: 1");
    const textFarbe = /fill:\s*([^;]+);/.exec(text)?.[1].trim();
    expect(textFarbe).toBe("var(--ps-hint-ink, #d2e8cd)");
    // … und diese Farbe wird genau einmal gesetzt, nicht je Geste.
    expect(css.split("--ps-hint-ink:").length - 1, "Farbe je Geste definiert").toBe(1);
    for (const sel of gesten) {
      expect(rule(sel), `${sel} übersteuert den Hinweistext`).not.toContain("--ps-hint-ink");
      expect(rule(sel), `${sel} übersteuert die Deckkraft`).not.toContain("opacity");
    }
    // Keine gestenabhängige Regel für den Text (auch keine Schriftgröße).
    expect(/\.ps-ghost-\w+[^{]*\.ps-record-arc-text/.test(css)).toBe(false);

    // Die vier Kopien haben dieselbe Deckkraft der Fläche (0,16) — keine
    // Geste ist schwächer gefüllt als die andere.
    const fuellAlphas = new Set(
      gesten.map((sel) => /--ps-ghost-fill:\s*rgba\([^)]*,\s*([\d.]+)\s*\)/.exec(rule(sel))?.[1])
    );
    expect(fuellAlphas.has(undefined)).toBe(false);
    expect(fuellAlphas.size, `Flächendeckkraft je Geste: ${[...fuellAlphas].join(", ")}`).toBe(1);
    expect([...fuellAlphas][0]).toBe("0.16");
  });

  test("der Knopf bleibt beim Hinweiswechsel derselbe DOM-Knoten", () => {
    vi.useFakeTimers();
    const { getByTestId, neu } = renderBuehne(0);
    const knopfVorher = getByTestId("record-button");
    const stageVorher = getByTestId("record-stage");
    const kopieVorher = getByTestId("record-ghost");
    const textVorher = getByTestId("record-tip");
    const klassenVorher = knopfVorher.className;
    const kinderVorher = stageVorher.children.length;
    const reihenfolgeVorher = Array.from(stageVorher.children).map((k) =>
      k.getAttribute("data-testid")
    );

    neu(2, "halten: aufnehmen");

    // Kein Neuaufbau: Knopf, Kopie und Textknoten bleiben dieselben Objekte.
    expect(getByTestId("record-button")).toBe(knopfVorher);
    expect(getByTestId("record-ghost")).toBe(kopieVorher);
    expect(getByTestId("record-tip")).toBe(textVorher);
    // Gleiche Klassen (also gleiche Größe/Position) und gleiche Reihenfolge.
    expect(getByTestId("record-button").className).toBe(klassenVorher);
    expect(getByTestId("record-stage").children.length).toBe(kinderVorher);
    expect(
      Array.from(getByTestId("record-stage").children).map((k) => k.getAttribute("data-testid"))
    ).toEqual(reihenfolgeVorher);
    // Während des Ausblendens bleibt der ALTE Hinweis stehen — Text UND Geste
    // (Change 219, Punkt 2: die Kopie bewegt sich nicht, während man sie sieht).
    expect(getByTestId("record-ghost").getAttribute("data-ps-gesture")).toBe("lock");
    expect(textVorher.textContent).toBe("nach oben wischen: Aufnahme sperren");
    act(() => {
      vi.advanceTimersByTime(TIP_FADE_OUT_MS + 1);
    });
    // Danach wechseln beide gemeinsam.
    expect(getByTestId("record-tip").textContent).toBe("halten: aufnehmen");
    expect(getByTestId("record-ghost").getAttribute("data-ps-gesture")).toBe("hold");
  });

  test("die Kopie bewegt sich nur über transform (kein Layout-Einfluss)", () => {
    const kopie = rule(".ps-record-ghost {");
    expect(kopie).not.toContain("margin");
    expect(kopie).not.toContain("top:");
    for (const name of ["ps-ghost-up", "ps-ghost-down", "ps-ghost-sink", "ps-ghost-rise"]) {
      const keyframes = block(`@keyframes ${name} {`);
      expect(keyframes).toContain("transform");
      // Nur transform/opacity — nichts, was das Layout verschieben kann.
      expect(keyframes).not.toContain("width");
      expect(keyframes).not.toContain("height");
      expect(keyframes).not.toContain("margin");
    }
    // Alle vier Bewegungen hängen an genau einer Hinweisklasse.
    expect(rule(".ps-ghost-lock {")).toContain("animation: ps-ghost-up");
    expect(rule(".ps-ghost-stop {")).toContain("animation: ps-ghost-down");
    expect(rule(".ps-ghost-sink {")).toContain("animation: ps-ghost-sink");
    expect(rule(".ps-ghost-rise {")).toContain("animation: ps-ghost-rise");
    // Pulsierender Ring beim Aufnehmen.
    expect(css).toContain(".ps-ghost-sink .ps-record-ghost-ring { animation: ps-ghost-ring");
  });

  test("(Punkt 5) der Puls geht ausschließlich nach außen, nie nach innen", () => {
    // Kein einziger scale-Wert unter 1 — in keiner Animation und keinem
    // Standbild. Vorher: Senken 0,72, Heben ab 0,82, Ring ab 0,92.
    const bloecke: Array<[string, number[]]> = [
      ["@keyframes ps-ghost-sink {", zahlen(block("@keyframes ps-ghost-sink {"), "scale")],
      ["@keyframes ps-ghost-rise {", zahlen(block("@keyframes ps-ghost-rise {"), "scale")],
      ["@keyframes ps-ghost-ring {", zahlen(block("@keyframes ps-ghost-ring {"), "scale")],
    ];
    for (const [name, werte] of bloecke) {
      expect(werte.length, `${name} hat keinen scale-Wert`).toBeGreaterThan(0);
      expect(Math.min(...werte), `${name} zieht nach innen`).toBeGreaterThanOrEqual(1);
    }
    // Nach außen heißt: über 1 hinaus.
    expect(Math.max(...bloecke[0][1]), "Senken (Halten)").toBeGreaterThan(1.1);
    expect(Math.max(...bloecke[1][1]), "Heben (Loslassen)").toBeGreaterThan(1.15);
    expect(Math.max(...bloecke[2][1]), "Ring").toBeGreaterThan(1.2);

    // Auch das Standbild bei reduzierter Bewegung bleibt draußen.
    const standbild = reduzierteBewegungBlock();
    const stands = zahlen(standbild, "scale");
    expect(stands.length).toBeGreaterThanOrEqual(2);
    expect(Math.min(...stands)).toBeGreaterThanOrEqual(1);

    // Und die Kopie bleibt trotz Puls innerhalb des Textkreises: sonst läge
    // sie unter dem Text.
    const groessterPuls = Math.max(
      ...[...bloecke[0][1], ...bloecke[1][1], ...bloecke[2][1]].filter((v) => v > 0)
    );
    expect(groessterPuls * (KNOPF_AB_640 / 2)).toBeLessThan(RECORD_ARC.r);
  });

  test("(Punkt 5) die Wischwege hoch/runter bleiben unverändert", () => {
    // Change 218: hoch 26 px, runter 18 px — unverändert gültig.
    const hoch = Math.max(...zahlen(block("@keyframes ps-ghost-up {"), "translateY").map(Math.abs));
    const runter = Math.max(
      ...zahlen(block("@keyframes ps-ghost-down {"), "translateY").map(Math.abs)
    );
    expect(hoch, "Wischweg nach oben in px").toBe(26);
    expect(runter, "Wischweg nach unten in px").toBe(18);

    // Grenze der Zone: Die Kopie darf mit ihrem Weg die Innenkante der
    // kleinsten Zone nicht überschreiten — sonst schneidet `overflow: hidden`
    // sie ab. Innenkante = halbe Zone − halber Knopf.
    const { hoehe, innenabstand, rand } = zonenmasse();
    const luft = (hoehe - 2 * rand - 2 * innenabstand) / 2 - KNOPF_MOBIL / 2;
    expect(hoch).toBeLessThanOrEqual(luft);
    expect(runter).toBeLessThanOrEqual(luft);
  });

  test("(Punkt 2) pro Hinweis genau EIN Aus- und EIN Einblenden", () => {
    vi.useFakeTimers();
    const { getByTestId, neu } = renderBuehne(0, "erster Hinweis");
    const tip = () => getByTestId("record-tip");
    const ghost = () => getByTestId("record-ghost");
    /** Ein Zustandsbild: Phase | Text | Geste der Kopie. */
    const stand = () =>
      `${tip().getAttribute("data-ps-hint-phase")}|${tip().textContent}|${ghost().getAttribute(
        "data-ps-gesture"
      )}`;

    const spur: string[] = [stand()];
    const messen = (schritte: number, ms: number) => {
      for (let i = 0; i < schritte; i++) {
        act(() => {
          vi.advanceTimersByTime(ms);
        });
        spur.push(stand());
      }
    };

    expect(spur[0]).toBe("in|erster Hinweis|lock");

    neu(1, "zweiter Hinweis");
    spur.push(stand());
    // Fein genug abtasten, um jeden Phasenwechsel einzeln zu sehen.
    messen(70, 20); // 1400 ms — mehr als der ganze Wechsel
    const wechsel = spur.filter((s, i) => i === 0 || s !== spur[i - 1]);
    expect(wechsel).toEqual([
      "in|erster Hinweis|lock",
      "out|erster Hinweis|lock",
      "in|zweiter Hinweis|stop",
    ]);

    // Und es bleibt dabei: kein zweites Aufblenden später im Zyklus.
    messen(100, 20); // weitere 2000 ms
    const spaeter = spur.filter((s, i) => i === 0 || s !== spur[i - 1]);
    expect(spaeter).toEqual(wechsel);

    // Dasselbe für den nächsten Hinweis, diesmal mit einem Wechsel MITTEN im
    // Ausblenden: es bleibt trotzdem bei einem Aus- und einem Einblenden.
    const spur2: string[] = [stand()];
    neu(2, "dritter Hinweis");
    spur2.push(stand());
    act(() => {
      vi.advanceTimersByTime(Math.round(TIP_FADE_OUT_MS / 3));
    });
    spur2.push(stand());
    neu(3, "vierter Hinweis"); // mitten im Ausblenden
    spur2.push(stand());
    for (let i = 0; i < 70; i++) {
      act(() => {
        vi.advanceTimersByTime(20);
      });
      spur2.push(stand());
    }
    const wechsel2 = spur2.filter((s, i) => i === 0 || s !== spur2[i - 1]);
    expect(wechsel2, `Ablauf: ${wechsel2.join(" → ")}`).toEqual([
      "in|zweiter Hinweis|stop",
      "out|zweiter Hinweis|stop",
      "in|vierter Hinweis|release",
    ]);
  });

  test("(Nachtrag) Kreis und Text blenden GEMEINSAM ein und aus — nie getrennt", () => {
    // 1. Im CSS: EINE Klasse für beide, dieselbe Dauer für beide.
    const aus = rule(".ps-record-hint-out {");
    for (const sel of [".ps-record-ghost {", ".ps-record-tip {"]) {
      const dauer = /transition:\s*opacity\s*(\d+)ms/.exec(rule(sel))?.[1];
      expect(dauer, `${sel} hat keine Deckkraft-Dauer`).toBeTruthy();
      expect(dauer, `${sel} blende anders lang als die gemeinsame Einheit`).toBe(
        String(TIP_FADE_IN_MS)
      );
    }
    expect(aus).toContain("opacity: 0"); // eine gemeinsame Ausblendregel
    expect(aus).toContain(`${TIP_FADE_OUT_MS}ms`);
    // Der Text darf keinen eigenen Übergang haben.
    expect(rule(".ps-record-arc-text {")).not.toContain("transition");
    expect(rule(".ps-record-arc {")).not.toContain("transition");
    // Der Ring sitzt IN der Kopie und fällt damit mit ihrer Deckkraft mit.
    expect(css).toContain(".ps-record-ghost-ring {");
    expect(css).toContain(".ps-ghost-sink .ps-record-ghost-ring { animation: ps-ghost-ring");

    // 2. Im DOM: über einen ganzen Wechsel hinweg sind Kopie (Kreis) und Text
    //    IMMER im selben Zustand — kein Bild, in dem nur eines von beiden
    //    sichtbar ist.
    vi.useFakeTimers();
    const { getByTestId, neu } = renderBuehne(0, "erster");
    const kreis = () => getByTestId("record-ghost");
    const text = () => getByTestId("record-tip");

    const paare: string[] = [];
    /** Ein Zustandsbild: Ausblendklasse von Kreis/Text, Phase, Sichtbarkeit. */
    const bild = () =>
      `${kreis().classList.contains("ps-record-hint-out") ? "aus" : "an"}/` +
      `${text().classList.contains("ps-record-hint-out") ? "aus" : "an"}` +
      `/${kreis().getAttribute("data-ps-hint-phase")}/${text().getAttribute("data-ps-hint-phase")}` +
      `/${kreis().getAttribute("data-ps-hint-visible")}/${text().getAttribute("data-ps-hint-visible")}`;
    const messen = (n: number) => {
      for (let i = 0; i < n; i++) {
        act(() => {
          vi.advanceTimersByTime(20);
        });
        paare.push(bild());
      }
    };
    messen(80); // 1600 ms — mehr als der ganze Wechsel
    neu(1, "zweiter");
    paare.push(bild());
    messen(80);

    for (const p of paare) {
      // Kopie und Text tragen denselben Ausblendzustand und dieselbe Phase.
      expect(p === "an/an" || p === "aus/aus" || p === "an/an/in/in/1/1" || p === "aus/aus/out/out/0/0",
        `getrennter Zustand: ${p}`
      ).toBe(true);
    }
    // Beide Zustände kamen wirklich vor (sonst prüft der Test nichts).
    expect(paare.some((p) => p.startsWith("aus/aus"))).toBe(true);
    expect(paare.some((p) => p.startsWith("an/an"))).toBe(true);
    // Es gibt genau EIN Fenster, in dem beides zugleich unsichtbar ist —
    // davor und danach ist beides sichtbar.
    const sichtbar = paare.map((p) => !p.startsWith("aus/aus"));
    const bloecke = sichtbar.filter((v, i) => i === 0 || v !== sichtbar[i - 1]);
    expect(bloecke, `Ablauf: ${paare.filter((p, i) => i === 0 || p !== paare[i - 1]).join(" → ")}`)
      .toEqual([true, false, true]);
  });

  test("alle vier Hinweise wechseln zyklisch in der Reihenfolge der Gesten", () => {
    vi.useFakeTimers();
    expect(RECORD_GESTURE_TIPS.map((t) => t.kind)).toEqual(["lock", "stop", "hold", "release"]);
    expect(RECORD_GESTURE_TIPS.map((t) => t.key)).toEqual([
      "gesture_lock_up",
      "gesture_stop_down",
      "gesture_hold",
      "gesture_release_pause",
    ]);
    // Zwei volle Umdrehungen: der Hinweis folgt dem Zähler lückenlos.
    const { getByTestId, neu } = renderBuehne(0);
    for (let i = 0; i < 8; i++) {
      neu(i, `Hinweis ${i}`);
      act(() => {
        vi.advanceTimersByTime(TIP_FADE_OUT_MS + 1);
      });
      expect(getByTestId("record-ghost").getAttribute("data-ps-gesture")).toBe(
        RECORD_GESTURE_TIPS[i % 4].kind
      );
      expect(getByTestId("record-tip").textContent).toBe(`Hinweis ${i}`);
    }
    for (let i = 0; i < RECORD_GESTURE_TIPS.length; i++) {
      expect(gestureTipAt(i).kind).toBe(RECORD_GESTURE_TIPS[i].kind);
    }
    // Auch außerhalb des Bereichs bleibt der Hinweis gültig (kein Absturz).
    expect(gestureTipAt(-1).kind).toBe("release");
    expect(gestureTipAt(7).kind).toBe("release");
  });

  test("(Punkt 1/3) der Hinweistext läuft auf einem Kreis in einer drehenden Gruppe", () => {
    const { getByTestId } = renderBuehne(0, "swipe up to lock recording");
    const tip = getByTestId("record-tip");
    const svg = tag(tip, "svg")[0];
    expect(svg, "kein SVG im Hinweis").toBeTruthy();

    // Bauart wie im css-tricks-Rezept: <defs><path id=…> + <text><textPath href=…>.
    const pfade = tag(svg, "path");
    const bogen = pfade.find((p) => p.getAttribute("id") === RECORD_ARC_PATH_ID);
    expect(bogen, `kein Pfad mit id="${RECORD_ARC_PATH_ID}"`).toBeTruthy();
    expect(bogen!.getAttribute("d")).toBe(RECORD_ARC_PATH_D);
    expect(bogen!.getAttribute("d")).toContain("A"); // Kreisbogen, keine Gerade
    expect(bogen!.parentElement?.tagName.toLowerCase()).toBe("defs");

    // Der Text hängt in der Gruppe, die sich dreht.
    const textPath = tag(svg, "textPath")[0];
    expect(textPath, "kein textPath im Hinweis").toBeTruthy();
    expect(textPath.getAttribute("href")).toBe(`#${RECORD_ARC_PATH_ID}`);
    expect(textPath.getAttribute("startOffset")).toBe("50%");
    expect(textPath.textContent).toBe("swipe up to lock recording");
    expect(textPath.parentElement?.getAttribute("text-anchor")).toBe("middle");

    const gruppe = textPath.closest("g");
    expect(gruppe, "der Text hängt in keiner <g>").toBeTruthy();
    expect(gruppe!.getAttribute("class")).toBe(RECORD_ARC_SPIN_CLASS);
    expect(gruppe!.parentElement?.tagName.toLowerCase()).toBe("svg");
    expect(textPath.parentElement?.parentElement).toBe(gruppe);

    // Kein gerader Textblock mehr: im Kasten liegt nur das SVG.
    expect(tip.textContent).toBe("swipe up to lock recording");
    expect(Array.from(tip.children).map((k) => k.tagName.toLowerCase())).toEqual(["svg"]);
    expect(tip.childNodes.length).toBe(1);
  });

  test("(Punkt 1) der Bogen ist ein echter Kreis und passt in die feste Zone", () => {
    const { x1, x2, rx, ry, y1, y2 } = bogengroesse();
    const { hoehe, innenabstand, rand } = zonenmasse();
    const schrift = RECORD_ARC.fontSize;
    const versal = schrift * 0.8; // Höhe der Buchstaben über der Grundlinie

    // Echter Kreis: EIN Radius in beiden Achsen, und kein ellipse-Element.
    expect(rx, "rx != ry — das wäre wieder eine Ellipse").toBe(ry);
    expect(rx).toBe(RECORD_ARC.r);
    const bauteil = quelle("components/RecordGestureHint.tsx");
    expect(bauteil.includes("<ellipse")).toBe(false);
    expect(bauteil.includes("ry=")).toBe(false);

    // Die Zeichenfläche sitzt mit ihrer unteren Kante auf der Knopfmitte —
    // nur so gilt RECORD_ARC.cy als Knopfmittelpunkt für alle Knopfgrößen.
    const tipCss = rule(".ps-record-tip {");
    expect(tipCss).toContain("bottom: 50%");
    expect(tipCss).toContain(`width: ${RECORD_ARC.width}px`);
    expect(tipCss).toContain(`height: ${RECORD_ARC.height}px`);
    expect(y1).toBeCloseTo(y2, 3); // linkes und rechtes Ende auf gleicher Höhe
    expect(y1).toBe(RECORD_ARC.cy);

    // 1. Der Kreis liegt außen um den Knopf: ab 640 px ist der Knopf 80 px
    //    breit (Radius 40) — der Kreis läuft mit Luft darum herum.
    expect(rx).toBeGreaterThanOrEqual(KNOPF_AB_640 / 2 + 2);
    //    Und zwar außerhalb des größten Pulses der Kopie (Punkt 5).
    expect(rx).toBeGreaterThan(1.22 * (KNOPF_AB_640 / 2));

    // 2. Bleibt der Text in der Zone? Die Schnittkante von `overflow: hidden`
    //    ist die Innenkante des Randes (Zonenhöhe − 2 × Rand), halbiert. Das
    //    gilt oben UND unten — der Text wandert beim Drehen um den ganzen
    //    Kreis.
    const schnittkante = (hoehe - 2 * rand) / 2;
    const oberkante = ry + versal; // höchster Punkt des Textes über der Knopfmitte
    expect(oberkante).toBeLessThanOrEqual(schnittkante - 2);
    expect(RECORD_ARC.height).toBeLessThanOrEqual(schnittkante);

    // 3. Bleibt der Text innerhalb der Breite der Zone? Engster Fall: 320 px
    //    Fenster, 12 px Seitenabstand der Seite, Innenabstand und Rand der Zone.
    const halbeBreiteMax = (320 - 2 * 12 - 2 * innenabstand - 2 * rand) / 2;
    const halbeBreite = x2 - RECORD_ARC.cx + versal;
    expect(halbeBreite).toBeLessThanOrEqual(halbeBreiteMax);
    expect(x1).toBeLessThan(RECORD_ARC.cx);
    expect(x2).toBeGreaterThan(RECORD_ARC.cx);
    // Symmetrisch um die Knopfmitte — der Kreis sitzt gerade um den Knopf.
    expect(RECORD_ARC.cx - x1).toBeCloseTo(x2 - RECORD_ARC.cx, 3);

    // 4. Wird der Text abgeschnitten? Der Halbkreis muss länger sein als der
    //    längste Hinweis aller Sprachen (Punkt 1).
    const { text, zeichen } = laengsterHinweis();
    const winkel = Math.acos((x2 - x1) / 2 / rx);
    const laenge = bogenlaenge(rx, ry, winkel, Math.PI - winkel);
    const textbreite = zeichen * ZEICHENBREITE_EM * schrift;
    expect(
      laenge,
      `Umfang ${Math.round(laenge)} px für „${text}" (${zeichen} Zeichen ≈ ${Math.round(textbreite)} px)`
    ).toBeGreaterThanOrEqual(textbreite * 1.1);

    // Schriftgröße im CSS und im Bauteil müssen übereinstimmen.
    expect(rule(".ps-record-arc-text {")).toContain(`font-size: ${schrift}px`);
  });

  test("(Punkt 3) die Drehung ist langsam, ruhig und bei reduzierter Bewegung aus", () => {
    const spin = rule(".ps-record-arc-spin {");
    expect(spin).toContain(`animation: ps-record-spin ${RECORD_ARC_SPIN_MS}ms linear infinite`);
    expect(RECORD_ARC_SPIN_MS, "zu schnell").toBeGreaterThanOrEqual(20000);
    expect(RECORD_ARC_SPIN_MS, "unmerklich langsam").toBeLessThanOrEqual(60000);
    // Gedreht wird um den Kreismittelpunkt, in Zeichenflächen-Einheiten.
    expect(spin).toContain("transform-box: view-box");
    expect(spin).toContain(`transform-origin: ${RECORD_ARC.cx}px ${RECORD_ARC.cy}px`);
    // Eine volle, gleichmäßige Umdrehung — kein Springen, kein Flackern.
    const keyframes = block("@keyframes ps-record-spin {");
    expect(keyframes).toContain("rotate(0deg)");
    expect(keyframes).toContain("rotate(360deg)");
    expect(keyframes).not.toContain("linear"); // linear steht in der Regel, nicht im Verlauf

    // Bei reduzierter Bewegung steht der Text still.
    const ohne = reduzierteBewegungBlock();
    expect(ohne).toContain(".ps-record-arc-spin");
    expect(/\.ps-record-arc-spin\s*\{[^}]*animation:\s*none/.test(ohne)).toBe(true);
  });

  test("(Punkt 6) Ein- und Ausblenden dauern länger als vorher", () => {
    const aus = rule(".ps-record-hint-out {");
    expect(aus).toContain("opacity: 0");
    expect(aus).toContain(`transition-duration: ${TIP_FADE_OUT_MS}ms`);
    expect(aus).toContain("ease-in");
    expect(TIP_FADE_OUT_MS, "alt waren 180 ms").toBeGreaterThan(180);

    const ein = rule(".ps-record-tip {");
    expect(ein).toContain(`transition: opacity ${TIP_FADE_IN_MS}ms ease-out`);
    expect(TIP_FADE_IN_MS, "alt waren 220 ms").toBeGreaterThan(220);
    // Deutlich länger, nicht nur ein paar Millisekunden: mindestens 1,5-fach.
    expect(TIP_FADE_OUT_MS).toBeGreaterThanOrEqual(180 * 1.5);
    expect(TIP_FADE_IN_MS).toBeGreaterThanOrEqual(220 * 1.5);

    // Kopie und Text blenden GLEICH lang — sonst wären es zwei Vorgänge.
    const ghostUebergang = /transition:\s*opacity\s*(\d+)ms/.exec(rule(".ps-record-ghost {"))?.[1];
    const tipUebergang = /transition:\s*opacity\s*(\d+)ms/.exec(ein)?.[1];
    expect(ghostUebergang).toBe(tipUebergang);
    expect(Number(ghostUebergang)).toBe(TIP_FADE_IN_MS);
  });

  test("bei reduzierter Bewegung gibt es kein Überblenden", () => {
    reduzierteBewegungAn();

    const { getByTestId, neu } = renderBuehne(0, "alt");
    neu(3, "neu");

    // Sofortiger Wechsel: kein Ausblenden, keine Zwischenstufe — Text und
    // Geste wechseln im selben Moment.
    const tip = getByTestId("record-tip");
    expect(tip.textContent).toBe("neu");
    expect(tip.classList.contains("ps-record-hint-out")).toBe(false);
    expect(tip.getAttribute("data-ps-hint-visible")).toBe("1");
    expect(tip.getAttribute("data-ps-hint-phase")).toBe("in");
    expect(getByTestId("record-ghost").classList.contains("ps-record-hint-out")).toBe(false);
    expect(getByTestId("record-ghost").getAttribute("data-ps-gesture")).toBe("release");

    // Und im CSS ist der Übergang für diesen Fall abgeschaltet.
    const ohneBewegung = reduzierteBewegungBlock();
    expect(ohneBewegung).toContain(".ps-record-tip");
    expect(ohneBewegung).toContain(".ps-record-hint-out");
    expect(ohneBewegung).toContain("transition: none");
  });

  test("(Punkt 5) bei reduzierter Bewegung steht ein Standbild — nur nach außen", () => {
    const ohneBewegung = reduzierteBewegungBlock();
    expect(ohneBewegung).toContain(".ps-record-ghost");
    expect(ohneBewegung).toContain("animation: none !important");
    // Standbild je Hinweis, alle Werte außen (Change 219 statt 9/4/0,88/1,04).
    expect(ohneBewegung).toContain("translateY(-20px)");
    expect(ohneBewegung).toContain("translateY(14px)");
    expect(ohneBewegung).toContain("scale(1.16)");
    expect(ohneBewegung).toContain("scale(1.22)");
    expect(ohneBewegung.includes("scale(0.")).toBe(false);
  });

  test("die Farben kommen aus der eigenen Palette, kein currentColor", () => {
    let farben = "";
    for (let i = 0; i < RECORD_GESTURE_TIPS.length; i++) {
      const { container, unmount } = renderBuehne(i);
      farben += container.querySelector("[data-testid='record-ghost'] svg")?.outerHTML ?? "";
      unmount();
    }
    expect(farben).toContain("var(--ps-accent, #2ea043)");
    expect(farben).toContain("var(--ps-err, #f85149)");
    expect(farben).toContain("#d99e2b");
    expect(farben.includes("currentColor")).toBe(false);
    // Die Farben der Kopie stehen ebenfalls in der Palette.
    expect(rule(".ps-ghost-lock {")).toContain("var(--ps-accent, #2ea043)");
    expect(rule(".ps-ghost-stop {")).toContain("var(--ps-err, #f85149)");
    expect(rule(".ps-ghost-rise {")).toContain("#d99e2b");
    // Der Hinweistext bleibt in der bisherigen Farbe (keine neue Farbe).
    expect(rule(".ps-record-tip {")).toContain("--ps-hint-ink: #d2e8cd");
    // Kein currentColor auch im Bauteil selbst (Kommentare zählen nicht).
    const bauteil = quelle("components/RecordGestureHint.tsx");
    const ohneKommentare = bauteil
      .split("\n")
      .filter((z) => !/^\s*(\*|\/\*|\/\/)/.test(z))
      .join("\n");
    expect(ohneKommentare.includes("currentColor")).toBe(false);
  });

  test("der echte Aufnahme-Knopf benutzt dieselbe Kopie und keinen Hinweisblock", () => {
    const bauteil = quelle("components/UploadZone.tsx");
    expect(bauteil).toContain("<RecordGestureHint");
    expect(bauteil).toContain("${RECORD_BUTTON_SHAPE}");
    expect(bauteil).toContain('className="ps-record-stage"');
    // Die frühere, ausdrücklich verworfene Lösung darf nicht zurückkommen.
    // (Erwähnungen im Kommentar zählen nicht — geprüft werden echte Regeln.)
    expect(/\.ps-tips\s*[,{]/.test(css)).toBe(false);
    expect(/\.ps-tips-/.test(css)).toBe(false);
    expect(/\.ps-zone-row\s*[,{]/.test(css)).toBe(false);
    expect(bauteil.includes("ps-tips")).toBe(false);
    expect(bauteil.includes("usageTips")).toBe(false);
  });
});
