/**
 * Change 216 (Nutzer-Vorgabe 20.09.2026) — die Gestenhinweise am Aufnahmeknopf
 * liegen als halbtransparente Kopie ÜBER dem Knopf.
 * Change 218 (Nutzer-Vorgabe 20.09.2026) — vier Nachbesserungen:
 *   1. Kopie weniger transparent (0,55 → 0,85), beide Zustände bleiben
 *      unterscheidbar (Flächenfüllung nur 0,16, Hinweisfarbe in Rand + Symbol);
 *   2. größerer Weg (hoch 12 → 26 px, runter 4 → 18 px, Senken 0,86 → 0,72,
 *      Heben 1,06 → 1,12);
 *   3. Hinweistext als gebogener Text auf einem SVG-Pfad um den Knopf;
 *   4. Aus-/Einblenden zwischen den Hinweisen, bei prefers-reduced-motion
 *      sofortiger Wechsel.
 *
 * jsdom rechnet keine CSS-Dateien aus und kann keine Pixel messen. Geprüft
 * wird deshalb dreierlei:
 *   1. die gerenderte Struktur — Knopf und Kopie liegen im selben Rahmen
 *      (`.ps-record-stage`), die Kopie trägt exakt dieselben Größen- und
 *      Formklassen wie der Knopf, der Text steht in einem `<textPath>`, und
 *      beim Wechsel des Hinweises wird der Knopf-DOM-Knoten NICHT neu
 *      aufgebaut (kein key, gleiche Klassen, gleiche Kindreihenfolge) — genau
 *      das war der gemeldete Fehler;
 *   2. die CSS-Werte in src/index.css — Deckkraft, Füllung, Bewegungsweite,
 *      Überblenden und das Standbild bei reduzierter Bewegung;
 *   3. die Geometrie des Bogens — aus dem tatsächlich gerenderten `d`-Attribut
 *      gegen die festen Maße der Zone gerechnet (kein Abschneiden, keine
 *      Überlappung mit Knopf oder Zonenrand).
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
  RECORD_BUTTON_SHAPE,
  RECORD_GESTURE_TIPS,
  RecordGestureHint,
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

/** Knopfmitte und Maße aus dem gerenderten `d`-Attribut des Bogens. */
function bogengroesse() {
  const m = /^M (-?[\d.]+) (-?[\d.]+) A ([\d.]+) ([\d.]+) 0 0 1 (-?[\d.]+) (-?[\d.]+)$/.exec(
    RECORD_ARC_PATH_D
  );
  expect(m, `d-Attribut des Bogens unerwartet: ${RECORD_ARC_PATH_D}`).toBeTruthy();
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

/** Knopfgröße der kleinsten Stufe in px (w-16 h-16) bzw. ab 640 px (w-20 h-20). */
const KNOPF_MOBIL = 64;
const KNOPF_AB_640 = 80;

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

/** Stellt window.matchMedia nach jedem Test wieder her. */
const matchMediaOriginal = window.matchMedia;
afterEach(() => {
  window.matchMedia = matchMediaOriginal;
  vi.useRealTimers();
});

describe("Change 216/218 — Gestenhinweise als halbtransparente Knopfkopie", () => {
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

    // Unterscheidbar bleiben beide: der Rand trägt die Hinweisfarbe, und die
    // vier Hinweise haben unterschiedliche Randfarben.
    const randfarben = new Set(
      [".ps-ghost-lock {", ".ps-ghost-stop {", ".ps-ghost-sink {", ".ps-ghost-rise {"].map(
        (sel) => /--ps-ghost-line:\s*([^;]+);/.exec(rule(sel))?.[1].trim() ?? ""
      )
    );
    expect(randfarben.has("")).toBe(false);
    expect(randfarben.size).toBeGreaterThanOrEqual(3);
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
    // Die Geste wechselt sofort (die Kopie bleibt stehen), der Text erst nach
    // dem Ausblenden — in beiden Fällen ohne key-Wechsel, also ohne Sprung.
    expect(getByTestId("record-ghost").getAttribute("data-ps-gesture")).toBe("hold");
    expect(textVorher.textContent).toBe("nach oben wischen: Aufnahme sperren");
    act(() => {
      vi.advanceTimersByTime(TIP_FADE_OUT_MS + 1);
    });
    expect(getByTestId("record-tip").textContent).toBe("halten: aufnehmen");
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

  test("die Kopie wandert beim Wischen deutlich weiter als der alte Wert", () => {
    // Alt (Change 216): hoch 12 px, runter 4 px, Senken 0,86, Heben 1,06.
    const hoch = Math.max(...zahlen(block("@keyframes ps-ghost-up {"), "translateY").map(Math.abs));
    const runter = Math.max(
      ...zahlen(block("@keyframes ps-ghost-down {"), "translateY").map(Math.abs)
    );
    expect(hoch, "Wischweg nach oben in px").toBeGreaterThan(12);
    expect(hoch).toBeGreaterThanOrEqual(20);
    expect(runter, "Wischweg nach unten in px").toBeGreaterThan(4);
    expect(runter).toBeGreaterThanOrEqual(12);

    const senken = zahlen(block("@keyframes ps-ghost-sink {"), "scale");
    const heben = zahlen(block("@keyframes ps-ghost-rise {"), "scale");
    expect(Math.min(...senken), "Senken (Halten)").toBeLessThanOrEqual(0.78); // alt 0,86
    expect(Math.max(...heben), "Heben (Loslassen)").toBeGreaterThanOrEqual(1.1); // alt 1,06

    // Der Stand bei reduzierter Bewegung zieht mit: die Stellung des Standbilds
    // ist ebenfalls weiter als vorher (alt 9 px bzw. 4 px).
    const standbild = reduzierteBewegungBlock();
    const standWege = zahlen(standbild, "translateY").map(Math.abs);
    expect(Math.max(...standWege)).toBeGreaterThanOrEqual(14);
    expect(Math.min(...zahlen(standbild, "scale"))).toBeLessThanOrEqual(0.78);

    // Grenze der Zone: Die Kopie darf mit ihrem Weg die Innenkante der
    // kleinsten Zone nicht überschreiten — sonst schneidet `overflow: hidden`
    // sie ab. Innenkante = halbe Zone − halber Knopf.
    const { hoehe, innenabstand, rand } = zonenmasse();
    const luft = (hoehe - 2 * rand - 2 * innenabstand) / 2 - KNOPF_MOBIL / 2;
    expect(hoch).toBeLessThanOrEqual(luft);
    expect(runter).toBeLessThanOrEqual(luft);
  });

  test("alle vier Hinweise wechseln zyklisch in der Reihenfolge der Gesten", () => {
    expect(RECORD_GESTURE_TIPS.map((t) => t.kind)).toEqual(["lock", "stop", "hold", "release"]);
    expect(RECORD_GESTURE_TIPS.map((t) => t.key)).toEqual([
      "gesture_lock_up",
      "gesture_stop_down",
      "gesture_hold",
      "gesture_release_pause",
    ]);
    // Zwei volle Umdrehungen: der Hinweis folgt dem Zähler lückenlos und
    // fängt danach wieder von vorn an (genauso zählt der Tab hoch).
    const { getByTestId, neu } = renderBuehne(0);
    for (let i = 0; i < 8; i++) {
      neu(i, `Hinweis ${i}`);
      expect(getByTestId("record-ghost").getAttribute("data-ps-gesture")).toBe(
        RECORD_GESTURE_TIPS[i % 4].kind
      );
    }
    for (let i = 0; i < RECORD_GESTURE_TIPS.length; i++) {
      expect(gestureTipAt(i).kind).toBe(RECORD_GESTURE_TIPS[i].kind);
    }
    // Auch außerhalb des Bereichs bleibt der Hinweis gültig (kein Absturz).
    expect(gestureTipAt(-1).kind).toBe("release");
    expect(gestureTipAt(7).kind).toBe("release");
  });

  test("der Hinweistext läuft wirklich auf einem textPath um den Knopf", () => {
    const { getByTestId } = renderBuehne(0, "swipe up to lock recording");
    const tip = getByTestId("record-tip");
    const svg = tag(tip, "svg")[0];
    expect(svg, "kein SVG im Hinweis").toBeTruthy();

    // Bauart wie im css-tricks-Rezept: <defs><path id=…> + <text><textPath href=…>.
    const pfade = tag(svg, "path");
    const bogen = pfade.find((p) => p.getAttribute("id") === RECORD_ARC_PATH_ID);
    expect(bogen, `kein Pfad mit id="${RECORD_ARC_PATH_ID}"`).toBeTruthy();
    expect(bogen!.getAttribute("d")).toBe(RECORD_ARC_PATH_D);
    expect(bogen!.getAttribute("d")).toContain("A"); // Ellipsenbogen, keine Gerade
    expect(bogen!.parentElement?.tagName.toLowerCase()).toBe("defs");

    const textPath = tag(svg, "textPath")[0];
    expect(textPath, "kein textPath im Hinweis").toBeTruthy();
    expect(textPath.getAttribute("href")).toBe(`#${RECORD_ARC_PATH_ID}`);
    expect(textPath.getAttribute("startOffset")).toBe("50%");
    expect(textPath.textContent).toBe("swipe up to lock recording");
    // Der Text sitzt mittig auf dem Bogen — links und rechts bleibt Luft.
    expect(textPath.parentElement?.getAttribute("text-anchor")).toBe("middle");

    // Kein gerader Textblock mehr: der Text des Hinweises steht ausschließlich
    // im textPath, im Kasten liegt nur das SVG.
    expect(tip.textContent).toBe("swipe up to lock recording");
    expect(Array.from(tip.children).map((k) => k.tagName.toLowerCase())).toEqual(["svg"]);
    expect(tip.childNodes.length).toBe(1);
  });

  test("der Bogen passt in die feste Zone und überlappt den Knopf nicht", () => {
    const { x1, x2, rx, ry, y1, y2 } = bogengroesse();
    const { hoehe, innenabstand, rand } = zonenmasse();
    const schrift = RECORD_ARC.fontSize;
    const versal = schrift * 0.8; // Höhe der Buchstaben über der Grundlinie

    // Die Zeichenfläche sitzt mit ihrer unteren Kante auf der Knopfmitte —
    // nur so gilt RECORD_ARC.cy als Knopfmittelpunkt für alle Knopfgrößen.
    const tipCss = rule(".ps-record-tip {");
    expect(tipCss).toContain("bottom: 50%");
    expect(tipCss).toContain(`width: ${RECORD_ARC.width}px`);
    expect(tipCss).toContain(`height: ${RECORD_ARC.height}px`);
    expect(y1).toBeCloseTo(y2, 3); // linkes und rechtes Ende auf gleicher Höhe

    // 1. Überlappt der Bogen den Knopf? Ab 640 px ist der Knopf 80 px breit
    //    (Radius 40) — der Bogen liegt außen, mit Luft.
    expect(ry).toBeGreaterThanOrEqual(KNOPF_AB_640 / 2 + 2);

    // 2. Bleibt der Text in der Zone? Die Schnittkante von `overflow: hidden`
    //    ist die Innenkante des Randes (Zonenhöhe − 2 × Rand), halbiert.
    const schnittkante = (hoehe - 2 * rand) / 2;
    const oberkante = ry + versal; // höchster Punkt des Textes über der Knopfmitte
    expect(oberkante).toBeLessThanOrEqual(schnittkante - 2);
    // Auch die ganze Zeichenfläche liegt innerhalb — nichts wird abgeschnitten.
    expect(RECORD_ARC.height).toBeLessThanOrEqual(schnittkante);

    // 3. Bleibt der Text innerhalb der Breite der Zone? Engster Fall: 320 px
    //    Fenster, 12 px Seitenabstand der Seite, Innenabstand und Rand der Zone.
    const halbeBreiteMax = (320 - 2 * 12 - 2 * innenabstand - 2 * rand) / 2;
    const halbeBreite = x2 - RECORD_ARC.cx + versal;
    expect(halbeBreite).toBeLessThanOrEqual(halbeBreiteMax);
    expect(x1).toBeLessThan(RECORD_ARC.cx);
    expect(x2).toBeGreaterThan(RECORD_ARC.cx);
    // Symmetrisch um die Knopfmitte — der Bogen sitzt gerade über dem Knopf.
    expect(RECORD_ARC.cx - x1).toBeCloseTo(x2 - RECORD_ARC.cx, 3);

    // 4. Wird der Text abgeschnitten? Der Bogen muss länger sein als der
    //    längste Hinweis. Längste Fassung: „nach oben wischen: Aufnahme
    //    sperren" (35 Zeichen) — bei 10 px Schriftgröße rund 185 px.
    const winkel = Math.acos((x2 - x1) / 2 / rx);
    const laenge = bogenlaenge(rx, ry, winkel, Math.PI - winkel);
    expect(laenge, `Bogenlänge in px: ${Math.round(laenge)}`).toBeGreaterThanOrEqual(200);

    // Schriftgröße im CSS und im Bauteil müssen übereinstimmen.
    expect(rule(".ps-record-arc-text {")).toContain(`font-size: ${schrift}px`);
  });

  test("zwischen den Hinweisen wird über- und eingeblendet, nicht hart umgeschaltet", () => {
    vi.useFakeTimers();
    const { getByTestId, neu } = renderBuehne(0, "erster Hinweis");
    expect(getByTestId("record-tip").classList.contains("ps-record-hint-out")).toBe(false);

    neu(1, "zweiter Hinweis");

    // Erst blendet der alte Hinweis aus (Kopie und Text zusammen) …
    const tip = getByTestId("record-tip");
    expect(tip.classList.contains("ps-record-hint-out")).toBe(true);
    expect(tip.textContent).toBe("erster Hinweis");
    expect(getByTestId("record-ghost").classList.contains("ps-record-hint-out")).toBe(true);
    expect(tip.getAttribute("data-ps-hint-visible")).toBe("0");

    // … dann steht der neue Text und blendet ein.
    act(() => {
      vi.advanceTimersByTime(TIP_FADE_OUT_MS);
    });
    expect(getByTestId("record-tip").textContent).toBe("zweiter Hinweis");
    expect(getByTestId("record-tip").classList.contains("ps-record-hint-out")).toBe(false);
    expect(getByTestId("record-tip").getAttribute("data-ps-hint-visible")).toBe("1");
    // Der Knoten bleibt derselbe — kein Neuaufbau, kein Sprung.
    expect(getByTestId("record-tip")).toBe(tip);

    // Die Zeiten und Übergänge stehen im CSS.
    const aus = rule(".ps-record-hint-out {");
    expect(aus).toContain("opacity: 0");
    expect(aus).toContain("transition-duration: 180ms");
    expect(aus).toContain("ease-in");
    expect(TIP_FADE_OUT_MS).toBe(180);
    expect(rule(".ps-record-tip {")).toContain("transition: opacity 220ms ease-out");
    expect(rule(".ps-record-ghost {")).toContain("transition: opacity");
  });

  test("bei reduzierter Bewegung gibt es kein Überblenden", () => {
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

    const { getByTestId, neu } = renderBuehne(0, "alt");
    neu(3, "neu");

    // Sofortiger Wechsel: kein Ausblenden, keine Zwischenstufe.
    const tip = getByTestId("record-tip");
    expect(tip.textContent).toBe("neu");
    expect(tip.classList.contains("ps-record-hint-out")).toBe(false);
    expect(tip.getAttribute("data-ps-hint-visible")).toBe("1");
    expect(getByTestId("record-ghost").classList.contains("ps-record-hint-out")).toBe(false);

    // Und im CSS ist der Übergang für diesen Fall abgeschaltet.
    const ohneBewegung = reduzierteBewegungBlock();
    expect(ohneBewegung).toContain(".ps-record-tip");
    expect(ohneBewegung).toContain(".ps-record-hint-out");
    expect(ohneBewegung).toContain("transition: none");
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
    expect(rule(".ps-record-arc-text {")).toContain("fill: #d2e8cd");
    // Kein currentColor auch im Bauteil selbst (Kommentare zählen nicht).
    const quelle = readFileSync(
      cssPfad().replace(/index\.css$/, "components/RecordGestureHint.tsx"),
      "utf8"
    );
    const ohneKommentare = quelle
      .split("\n")
      .filter((z) => !/^\s*(\*|\/\*|\/\/)/.test(z))
      .join("\n");
    expect(ohneKommentare.includes("currentColor")).toBe(false);
  });

  test("bei reduzierter Bewegung steht ein Standbild des Hinweises", () => {
    const ohneBewegung = reduzierteBewegungBlock();
    expect(ohneBewegung).toContain(".ps-record-ghost");
    expect(ohneBewegung).toContain("animation: none !important");
    // Standbild je Hinweis: die jeweilige Stellung bleibt sichtbar und ist
    // ebenfalls weiter als vorher (Change 218 statt 9/4/0,88/1,04).
    expect(ohneBewegung).toContain("translateY(-20px)");
    expect(ohneBewegung).toContain("translateY(14px)");
    expect(ohneBewegung).toContain("scale(0.78)");
    expect(ohneBewegung).toContain("scale(1.10)");
  });

  test("der echte Aufnahme-Knopf benutzt dieselbe Kopie und keinen Hinweisblock", () => {
    const quelle = readFileSync(
      cssPfad().replace(/index\.css$/, "components/UploadZone.tsx"),
      "utf8"
    );
    expect(quelle).toContain("<RecordGestureHint");
    expect(quelle).toContain("${RECORD_BUTTON_SHAPE}");
    expect(quelle).toContain('className="ps-record-stage"');
    // Die frühere, ausdrücklich verworfene Lösung darf nicht zurückkommen.
    // (Erwähnungen im Kommentar zählen nicht — geprüft werden echte Regeln.)
    expect(/\.ps-tips\s*[,{]/.test(css)).toBe(false);
    expect(/\.ps-tips-/.test(css)).toBe(false);
    expect(/\.ps-zone-row\s*[,{]/.test(css)).toBe(false);
    expect(quelle.includes("ps-tips")).toBe(false);
    expect(quelle.includes("usageTips")).toBe(false);
  });
});
