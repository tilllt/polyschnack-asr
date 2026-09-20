/**
 * Change 216 (Nutzer-Vorgabe 20.09.2026) — die Gestenhinweise am Aufnahmeknopf
 * liegen als halbtransparente Kopie ÜBER dem Knopf.
 *
 * jsdom rechnet keine CSS-Dateien aus und kann keine Pixel messen. Geprüft
 * wird deshalb zweierlei:
 *   1. die gerenderte Struktur — Knopf und Kopie liegen im selben Rahmen
 *      (`.ps-record-stage`), die Kopie trägt exakt dieselben Größen- und
 *      Formklassen wie der Knopf, und beim Wechsel des Hinweises wird der
 *      Knopf-DOM-Knoten NICHT neu aufgebaut (kein key, gleiche Klassen,
 *      gleiche Kindreihenfolge) — genau das war der gemeldete Fehler;
 *   2. die CSS-Werte in src/index.css — die Kopie ist absolut positioniert
 *      (inset: 0 = exakt die Knopffläche), halbtransparent (0,55), nimmt keine
 *      Klicks an (pointer-events: none) und bewegt sich nur über `transform`,
 *      also ohne Einfluss auf das Layout.
 * Die tatsächlichen Pixel wurden zusätzlich im echten Browser gemessen.
 */
import { render } from "@testing-library/react";
import { describe, expect, test } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import {
  RECORD_BUTTON_SHAPE,
  RECORD_GESTURE_TIPS,
  RecordGestureHint,
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

/** Inhalt einer CSS-Regel (grob, reicht für die hier gesetzten Regeln). */
function rule(selector: string): string {
  const start = css.indexOf(selector);
  expect(start, `CSS-Regel „${selector}" fehlt in index.css`).toBeGreaterThan(-1);
  const open = css.indexOf("{", start);
  const close = css.indexOf("}", open);
  return css.slice(open + 1, close);
}

/**
 * Bildet den echten Aufbau nach: der Knopf liegt im Fluss, die Kopie absolut
 * darüber. Die Knopfklassen kommen aus derselben Konstante wie im echten Code.
 */
function renderBuehne(tipIdx: number, label = "nach oben wischen: Aufnahme sperren") {
  return render(
    <div className="ps-tab-body">
      <div className="ps-record-stage" data-testid="record-stage">
        <button
          type="button"
          data-testid="record-button"
          className={`ps-record-btn ${RECORD_BUTTON_SHAPE} bg-accent`}
        />
        <RecordGestureHint tipIdx={tipIdx} label={label} />
      </div>
    </div>
  );
}

describe("Change 216 — Gestenhinweise als halbtransparente Knopfkopie", () => {
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
    expect(ghost).toContain("opacity: 0.55");
    expect(ghost).toContain("pointer-events: none");
    expect(ghost).toContain("z-index: 1");
    // Der Rahmen ist genau so groß wie der Knopf: nur der Knopf liegt im Fluss.
    expect(rule(".ps-record-stage {")).toContain("position: relative");
    expect(rule(".ps-record-tip {")).toContain("position: absolute");
  });

  test("der Knopf bleibt beim Hinweiswechsel derselbe DOM-Knoten", () => {
    const { getByTestId, rerender } = renderBuehne(0);
    const knopfVorher = getByTestId("record-button");
    const stage = getByTestId("record-stage");
    const kopieVorher = getByTestId("record-ghost");
    const textVorher = getByTestId("record-tip");
    const klassenVorher = knopfVorher.className;
    const kinderVorher = stage.children.length;
    const reihenfolgeVorher = Array.from(stage.children).map((k) => k.getAttribute("data-testid"));

    rerender(
      <div className="ps-tab-body">
        <div className="ps-record-stage" data-testid="record-stage">
          <button
            type="button"
            data-testid="record-button"
            className={`ps-record-btn ${RECORD_BUTTON_SHAPE} bg-accent`}
          />
          <RecordGestureHint tipIdx={2} label="halten: aufnehmen" />
        </div>
      </div>
    );

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
    // Der Hinweis selbst wechselt — aber ohne key-Wechsel, also ohne Sprung.
    expect(textVorher.textContent).toBe("halten: aufnehmen");
    expect(getByTestId("record-ghost").getAttribute("data-ps-gesture")).toBe("hold");
  });

  test("die Kopie bewegt sich nur über transform (kein Layout-Einfluss)", () => {
    const kopie = rule(".ps-record-ghost {");
    expect(kopie).not.toContain("margin");
    expect(kopie).not.toContain("top:");
    for (const name of ["ps-ghost-up", "ps-ghost-down", "ps-ghost-sink", "ps-ghost-rise"]) {
      const keyframes = rule(`@keyframes ${name} {`);
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

  test("alle vier Hinweise stehen in der Reihenfolge der Gesten bereit", () => {
    expect(RECORD_GESTURE_TIPS.map((t) => t.kind)).toEqual(["lock", "stop", "hold", "release"]);
    expect(RECORD_GESTURE_TIPS.map((t) => t.key)).toEqual([
      "gesture_lock_up",
      "gesture_stop_down",
      "gesture_hold",
      "gesture_release_pause",
    ]);
    for (let i = 0; i < RECORD_GESTURE_TIPS.length; i++) {
      const { unmount, getByTestId } = renderBuehne(i);
      expect(getByTestId("record-ghost").getAttribute("data-ps-gesture")).toBe(
        RECORD_GESTURE_TIPS[i].kind
      );
      unmount();
    }
    // Auch außerhalb des Bereichs bleibt der Hinweis gültig (kein Absturz).
    expect(gestureTipAt(-1).kind).toBe("release");
    expect(gestureTipAt(7).kind).toBe("release");
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
    const start = css.indexOf("@media (prefers-reduced-motion: reduce)", css.indexOf(".ps-record-ghost {"));
    expect(start).toBeGreaterThan(-1);
    const block = css.slice(start, css.indexOf("\n}\n", css.indexOf("ps-ghost-sink", start)));
    expect(block).toContain(".ps-record-ghost");
    expect(block).toContain("animation: none !important");
    // Standbild je Hinweis: die jeweilige Stellung bleibt sichtbar.
    expect(block).toContain("translateY(-9px)");
    expect(block).toContain("translateY(4px)");
    expect(block).toContain("scale(0.88)");
    expect(block).toContain("scale(1.04)");
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
