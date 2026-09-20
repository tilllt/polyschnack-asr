/**
 * Change 220 (Nutzer-Vorgabe 20.09.2026) — die drei Quellen (Upload, Aufnahme,
 * Download/URL) sind jetzt gleichrangige Kreis-Knöpfe, die URL-Zeile liegt
 * über der Kreis-Reihe, und das Optionen-Panel steht GANZ UNTEN.
 *
 * jsdom rechnet keine CSS-Dateien aus und misst keine Pixel. Geprüft wird
 * deshalb:
 *   (a) die Reihenfolge im DOM — Quellen-Auswahl, Bereich der gewählten
 *       Quelle, dann das Optionen-Panel (nicht davor);
 *   (b) genau drei Quellen-Kreise, jeder mit selbst gezeichnetem Symbol IM
 *       Ring und Kreistext AUF einem Kreis (textPath am eigenen Bogen);
 *   (c) gleiche Größe und gleiche Bauart aller drei Kreise — verglichen
 *       werden die Formklassen der Knöpfe, die Maße der gemeinsamen
 *       Konstanten (SourceCircle.tsx) und die CSS-Regeln (Ringstärke,
 *       Schriftgröße, Drehzeit) sowie das `d` aller drei Bögen;
 *   (d) die URL-Zeile über der Kreis-Reihe: voller Breite, Beispiel-Adresse
 *       als Platzhalter;
 *   (e) die Auswahl schaltet den Bereich darunter wirklich um;
 *   (f) der Aufnahmeknopf enthält das monochrome Mikrofon-Zeichen und die
 *       Gestenhinweise arbeiten unverändert (Kopie + Kreistext am Knopf).
 * Die tatsächliche Optik am Gerät (Kreisform, Drehung, Abstände in Pixel)
 * kann diese Prüfung NICHT abdecken — jsdom zeichnet nicht.
 */
import { fireEvent, render, within } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ToastProvider } from "./Toasts";
import { LocaleProvider } from "../useLocale";
import { UploadZone } from "./UploadZone";
import {
  RECORD_BUTTON_SHAPE,
} from "./RecordGestureHint";
import {
  SOURCE_CIRCLE_ARC,
  SOURCE_CIRCLE_ARC_PATH_D,
  SOURCE_CIRCLE_BORDER,
  SOURCE_CIRCLE_SHAPE,
  SOURCE_CIRCLE_SPIN_CLASS,
  SOURCE_CIRCLE_SPIN_MS,
} from "./SourceCircle";

/* ── Server gibt es in dieser Prüfung nicht ── */
vi.mock("../api", () => ({
  fetchBackendCapabilities: async () => null,
  fetchModelStatus: async () => ({ vad_available: true, diarize_available: true }),
  fetchModelsMatrix: async () => [],
  fetchTemplates: async () => [],
  fetchTargets: async () => [],
  fetchLlmEndpoints: async () => [],
  importFromUrl: async () => ({ uid: "u1", original_name: "probe" }),
  recordFromMic: async () => ({ uid: "u1" }),
  startTranscription: async () => ({}),
  uploadRecording: async () => ({ uid: "u1" }),
  duplicateRecording: async () => ({ uid: "u1" }),
  mergeRecordings: async () => ({ uid: "u1" }),
}));

/* IndexedDB (Offline-Puffer) gibt es in jsdom nicht — der Puffer wird hier
   nicht geprüft, deshalb leer. */
vi.mock("../offlineQueue", () => ({
  loadPendingRecordings: async () => [],
  savePendingRecording: async () => {},
  deletePendingRecording: async () => {},
  pendingToFormData: () => new FormData(),
}));

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

function renderZone() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <LocaleProvider>
        <ToastProvider>
          <UploadZone />
        </ToastProvider>
      </LocaleProvider>
    </QueryClientProvider>
  );
}

/** Steht `spaeter` wirklich NACH `frueher` im DOM? */
function stehtNach(spaeter: HTMLElement, frueher: HTMLElement): boolean {
  return (
    (frueher.compareDocumentPosition(spaeter) & Node.DOCUMENT_POSITION_FOLLOWING) !== 0
  );
}

afterEach(() => {
  // Touch-Simulation der Gesten-Prüfung wieder entfernen.
  delete (window as unknown as Record<string, unknown>).ontouchstart;
});

/* Der Aufnahme-Bereich merkt sich das gewählte Mikrofon in localStorage.
   Die jsdom-Laufzeit dieser Prüfung hat keinen — hier ein kleiner Ersatz,
   damit die Aufnahme-Ansicht überhaupt gerendert werden kann. */
const speicher = new Map<string, string>();
Object.defineProperty(window, "localStorage", {
  configurable: true,
  value: {
    getItem: (k: string) => speicher.get(k) ?? null,
    setItem: (k: string, v: string) => void speicher.set(k, String(v)),
    removeItem: (k: string) => void speicher.delete(k),
    clear: () => speicher.clear(),
  },
});

describe("Change 220 — Quellen-Kreise, URL-Zeile, Optionen unten", () => {
  test("(a) das Optionen-Panel steht im DOM NACH den Quellen und dem Bereich darunter", () => {
    const { getByTestId } = renderZone();
    const quellen = getByTestId("sources");
    const bereich = getByTestId("area-upload");
    const optionen = getByTestId("options-panel");

    expect(stehtNach(optionen, quellen)).toBe(true);
    expect(stehtNach(optionen, bereich)).toBe(true);
    // … und NICHT darüber: das Panel liegt nach den Quellen, die Quellen nicht
    // nach dem Panel.
    expect(stehtNach(quellen, optionen)).toBe(false);
    expect(stehtNach(bereich, optionen)).toBe(false);
  });

  test("(b) genau drei Quellen-Kreise mit Symbol im Ring und Kreistext auf einem Kreis", () => {
    const { getByTestId } = renderZone();
    const reihe = getByTestId("source-row");
    const kreise = Array.from(reihe.querySelectorAll<HTMLElement>(".ps-src"));
    expect(kreise).toHaveLength(3);
    expect(kreise.map((k) => k.getAttribute("data-ps-source"))).toEqual([
      "upload",
      "record",
      "download",
    ]);

    const namen: string[] = [];
    for (const kreis of kreise) {
      const art = kreis.getAttribute("data-ps-source")!;
      const knopf = kreis.querySelector<HTMLButtonElement>("button.ps-src-btn")!;
      expect(knopf).toBeTruthy();
      // Symbol IM Kreis (selbst gezeichnet, Inline-SVG, monochrom).
      const symbol = knopf.querySelector(`svg[data-ps-icon="${art}"]`);
      expect(symbol, `${art}: Symbol im Ring fehlt`).toBeTruthy();
      // Kreistext AUF einem Kreis: defs/path + textPath, in einer drehenden Gruppe.
      const gruppe = kreis.querySelector(`g.${SOURCE_CIRCLE_SPIN_CLASS}`);
      expect(gruppe, `${art}: drehende Gruppe fehlt`).toBeTruthy();
      const text = kreis.querySelector(".ps-src-arc-text textPath");
      expect(text, `${art}: Kreistext fehlt`).toBeTruthy();
      expect(text!.getAttribute("href")).toBe(`#ps-source-arc-${art}`);
      expect(text!.getAttribute("startOffset")).toBe("50%");
      namen.push((text!.textContent ?? "").trim());
    }
    // Der Kreistext benennt die Quelle (in allen drei Sprachen gleich bzw.
    // übersetzt — hier der englische Standardsatz).
    expect(namen.sort()).toEqual(["Download", "Record", "Upload"]);
  });

  test("(c) alle drei Kreise sind gleich groß und gleich gebaut", () => {
    const { getByTestId } = renderZone();
    const reihe = getByTestId("source-row");
    const knoepfe = Array.from(reihe.querySelectorAll<HTMLButtonElement>("button.ps-src-btn"));
    expect(knoepfe).toHaveLength(3);

    // Dieselben Größen-/Formklassen — ohne Sonderfall für einen der Kreise.
    const formklassen = knoepfe.map((k) =>
      Array.from(k.classList)
        .filter((c) => /^(sm:)?(w-|h-|rounded-)/.test(c))
        .sort()
        .join(" ")
    );
    expect(new Set(formklassen).size).toBe(1);
    expect(formklassen[0]).toBe(
      SOURCE_CIRCLE_SHAPE.split(" ").sort().join(" ")
    );

    // Eine einzige Ring-Regel für alle: gleiche Stärke, Outline (kein Füllkörper).
    const ring = rule(".ps-src-btn {");
    expect(ring).toContain(`border: ${SOURCE_CIRCLE_BORDER}px solid`);
    expect(ring).toContain("background: transparent");
    // Die gewählte Variante ändert NUR die Linienart und die Farbe, keine Stärke.
    const gewaehlt = rule(".ps-src-btn.ps-src-on {");
    expect(gewaehlt).toContain("border-style: solid");
    expect(gewaehlt).not.toContain("border-width");

    // Gleicher Kreistext: genau eine Regel mit der Schriftgröße.
    expect(css.match(/\.ps-src-arc-text \{/g) ?? []).toHaveLength(1);
    expect(rule(".ps-src-arc-text {")).toContain(
      `font-size: ${SOURCE_CIRCLE_ARC.fontSize}px`
    );

    // Gleiche Drehung: eine Gruppe, eine Drehzahl, Drehpunkt = Kreismittelpunkt.
    const spin = rule(".ps-src-arc-spin {");
    expect(spin).toContain(`animation: ps-src-spin ${SOURCE_CIRCLE_SPIN_MS}ms linear infinite`);
    expect(spin).toContain(
      `transform-origin: ${SOURCE_CIRCLE_ARC.cx}px ${SOURCE_CIRCLE_ARC.cy}px`
    );
    expect(css).toContain("@keyframes ps-src-spin");

    // Gleicher Bogen: alle drei Pfade tragen dieselbe Geometrie (ein Radius).
    const boegen = Array.from(reihe.querySelectorAll(".ps-src-arc-svg defs path")).map((p) =>
      p.getAttribute("d")
    );
    expect(boegen).toHaveLength(3);
    expect(new Set(boegen).size).toBe(1);
    expect(boegen[0]).toBe(SOURCE_CIRCLE_ARC_PATH_D);
    // Der Bogen ist ein echter Kreis (beide Radien gleich).
    expect(boegen[0]).toContain(
      `A ${SOURCE_CIRCLE_ARC.r} ${SOURCE_CIRCLE_ARC.r} 0 0 1`
    );
  });

  test("(c2) der gewählte Kreis ist nicht nur an der Farbe zu erkennen", () => {
    const { getByTestId } = renderZone();
    const upload = getByTestId("source-upload");
    const knopf = within(upload).getByRole("button");
    expect(knopf.getAttribute("aria-pressed")).toBe("true");
    expect(upload.getAttribute("data-ps-selected")).toBe("true");
    expect(knopf.className).toContain("ps-src-on");
    // Innenring als zweite, nicht-farbliche Kennzeichnung.
    expect(rule(".ps-src-btn.ps-src-on::after {")).toContain("border-radius: 999px");
  });

  test("(d) der Download-Kreis hat die URL-Zeile mit Beispiel-Platzhalter über sich", () => {
    const { getByTestId } = renderZone();
    const zeile = getByTestId("url-line");
    const downloadKreis = getByTestId("source-download");
    const reihe = getByTestId("source-row");

    expect(stehtNach(downloadKreis, zeile)).toBe(true);
    expect(stehtNach(reihe, zeile)).toBe(true);

    const eingabe = within(zeile).getByTestId("url-input") as HTMLInputElement;
    // Beispieltext einer YouTube-Adresse als Platzhalter.
    expect(eingabe.getAttribute("placeholder")).toMatch(
      /^https:\/\/youtube\.com\/watch\?v=/
    );
    // Über die volle Breite des Containers.
    expect(rule(".ps-url-row {")).toContain("width: 100%");
    expect(rule(".ps-url-input {")).toContain("width: 100%");
    expect(eingabe.className).toContain("ps-url-input");
  });

  test("(e) die Auswahl schaltet den Bereich darunter wirklich um", () => {
    const { getByTestId, queryByTestId } = renderZone();

    // Start: Upload gewählt → nur der Upload-Bereich steht da.
    expect(queryByTestId("area-upload")).toBeTruthy();
    expect(queryByTestId("area-record")).toBeNull();
    expect(queryByTestId("area-url")).toBeNull();

    // Aufnahme wählen
    fireEvent.click(within(getByTestId("source-record")).getByRole("button"));
    expect(queryByTestId("area-record")).toBeTruthy();
    expect(queryByTestId("area-upload")).toBeNull();
    expect(getByTestId("source-record").getAttribute("data-ps-selected")).toBe("true");
    expect(getByTestId("source-upload").getAttribute("data-ps-selected")).toBe("false");

    // Download (URL) wählen
    fireEvent.click(within(getByTestId("source-download")).getByRole("button"));
    expect(queryByTestId("area-url")).toBeTruthy();
    expect(queryByTestId("area-record")).toBeNull();
    expect(getByTestId("source-download").getAttribute("data-ps-selected")).toBe("true");

    // Zurück zu Upload
    fireEvent.click(within(getByTestId("source-upload")).getByRole("button"));
    expect(queryByTestId("area-upload")).toBeTruthy();
    expect(queryByTestId("area-url")).toBeNull();
  });

  test("(f) der Aufnahmeknopf trägt das monochrome Mikrofon und die Gestenhinweise", () => {
    // Touch-Gerät: nur dort gibt es die Wischgesten und damit die Hinweise.
    Object.defineProperty(window, "ontouchstart", { value: null, configurable: true });
    const { getByTestId } = renderZone();
    fireEvent.click(within(getByTestId("source-record")).getByRole("button"));

    const knopf = getByTestId("record-button");
    // Der BESTEHENDE Aufnahmeknopf (gleiche Formklassen), nicht neu gebaut.
    expect(knopf.className).toContain(RECORD_BUTTON_SHAPE);
    // … mit monochromem Mikrofon-Symbol (Striche, eine Farbe = currentColor).
    const mikro = knopf.querySelector('svg[data-ps-icon="record"]');
    expect(mikro).toBeTruthy();
    expect(mikro!.querySelectorAll("path").length).toBeGreaterThan(0);
    expect(mikro!.innerHTML).toContain("currentColor");

    // Die Gestenhinweise arbeiten unverändert: Kopie + Kreistext am Knopf.
    const kopie = getByTestId("record-ghost");
    const text = getByTestId("record-tip");
    expect(kopie.className).toContain(RECORD_BUTTON_SHAPE);
    expect(kopie.querySelector(".ps-record-ghost-ring")).toBeTruthy();
    expect(text.querySelector("textPath")).toBeTruthy();
    expect((text.querySelector("textPath")!.textContent ?? "").length).toBeGreaterThan(0);
  });

  test("(g) der Kreistext sitzt NAH am Ring — und in jeder Knopfgröße gleich nah", () => {
    // Nutzer-Vorgabe 20.09.2026: „die drehende Schrift um die Buttons soll ganz
    // nah an den Kreisen sein, nicht so weit entfernt."
    // Knopfgrößen aus SOURCE_CIRCLE_SHAPE: 64 px (w-16) bzw. 80 px (sm:w-20) —
    // Außenkante des 2 px starken Rings also 34 px bzw. 42 px.
    const ringAussenMobil = 64 / 2 + SOURCE_CIRCLE_BORDER / 2;
    const ringAussenDesktop = 80 / 2 + SOURCE_CIRCLE_BORDER / 2;

    // Die Schrift läuft auf dem Kreis mit dem Radius r (Grundlinie).
    const abstandMobil = SOURCE_CIRCLE_ARC.r - ringAussenMobil;
    const abstandDesktop = SOURCE_CIRCLE_ARC.r * 1.25 - ringAussenDesktop;

    // NAH heißt hier: höchstens 6 px — vorher waren es 14 px (mobil).
    expect(abstandMobil, "Textabstand mobil").toBeLessThanOrEqual(6);
    expect(abstandDesktop, "Textabstand Desktop").toBeLessThanOrEqual(6);
    // … und nie im Ring (sonst läge die Schrift über der Ringlinie).
    expect(abstandMobil, "Text darf den Ring nicht berühren").toBeGreaterThan(0);
    expect(abstandDesktop, "Text darf den Ring nicht berühren").toBeGreaterThan(0);
    // Beide Stufen liegen gleich nah (Unterschied unter 2 px).
    expect(Math.abs(abstandDesktop - abstandMobil)).toBeLessThan(2);

    // Damit das auch auf dem Gerät gilt, MUSS die Zeichenfläche mit dem Knopf
    // wachsen: Prozentwerte relativ zur Knopfgröße, KEINE festen px und KEINE
    // zusätzliche Medienabfrage (die Werte gelten für beide Stufen, das
    // Verhältnis 140/52 zur Zeichenfläche bleibt erhalten).
    const flaeche = rule(".ps-src-arc {");
    expect(flaeche, "Breite prozentual zur Knopfgröße").toContain("218.75%");
    expect(flaeche, "Höhe prozentual zur Knopfgröße").toContain("81.25%");
    expect(flaeche, "keine feste Breite in px").not.toMatch(/width:\s*\d+px/);
    expect(flaeche, "keine feste Höhe in px").not.toMatch(/height:\s*\d+px/);
    // Die Prozentwerte müssen die Zeichenfläche der SVG genau treffen:
    // 218,75 % / 81,25 % = 140 / 52 (sonst verzerrt der Text oder rutscht).
    const verhaeltnisCss = (140 / 64) / (52 / 64);
    const verhaeltnisWerte = 218.75 / 81.25;
    expect(verhaeltnisWerte).toBeCloseTo(verhaeltnisCss, 3);
    // Und die Zeichenfläche selbst (viewBox) bleibt das Seitenverhältnis 140/52.
    expect(SOURCE_CIRCLE_ARC.width / SOURCE_CIRCLE_ARC.height).toBeCloseTo(140 / 52, 6);
  });
});
