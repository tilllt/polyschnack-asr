/**
 * Change 222 (Nutzer-Vorgabe 20.09.2026) — Aufbau der Quellen-Bedienung.
 *
 * Klarstellung des Nutzers zum Umbau aus Change 220: Die drei Kreise sollten
 * die Tabs NICHT ersetzen. Jetzt gilt:
 *   · Die Tab-Reihe besteht aus drei NACKTEN Zeichen (kein Kreis, kein Text).
 *   · Der Kreis sitzt IN der Zone seiner Quelle (Upload-Ablegefläche,
 *     Adress-Zone) — in derselben Größe wie der Aufnahmeknopf.
 *   · Die Beschriftung des Kreises steht STILL und gekrümmt am oberen Rand.
 *   · Die Adress-Zeile liegt IN der Adress-Zone; der Formathinweis im Upload
 *     ist entfallen.
 *   · An keinem Text läuft noch eine Animation (Drehung entfallen).
 *
 * jsdom rechnet keine CSS-Dateien aus und misst keine Pixel. Geprüft wird
 * deshalb:
 *   (a) die Reihenfolge im DOM — Quellen-Auswahl, Bereich der gewählten
 *       Quelle, dann das Optionen-Panel (nicht davor);
 *   (b) drei nackte Umschalter-Zeichen in der Reihe (ohne Kreis, ohne Text)
 *       und je ein Kreis mit Zeichen + Kreistext in Upload- und Adress-Zone;
 *   (c) gleiche Größe und gleiche Bauart aller Kreise — verglichen werden die
 *       Formklassen der Knöpfe und die gemeinsamen Konstanten
 *       (SourceCircle.tsx) sowie die CSS-Regeln (Ringstärke, Schriftgröße);
 *   (d) die Adress-Zeile IN der Adress-Zone (voller Breite, Beispiel-Adresse);
 *   (e) die Auswahl schaltet den Bereich darunter wirklich um;
 *   (f) der Aufnahmeknopf enthält das monochrome Mikrofon-Zeichen;
 *   (g) der Kreistext sitzt rund 5 px außerhalb des Rings — in beiden
 *       Knopfgrößen gleich nah;
 *   (h) keine Drehung mehr (kein Dreh-Schlüsselwort in CSS oder Bauteilen).
 * Die tatsächliche Optik am Gerät (Kreisform, Abstände in Pixel) kann diese
 * Prüfung NICHT abdecken — jsdom zeichnet nicht.
 */
import { fireEvent, render, within } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ToastProvider } from "./Toasts";
import { LocaleProvider } from "../useLocale";
import { UploadZone } from "./UploadZone";
import { RECORD_BUTTON_SHAPE } from "./RecordGestureHint";
import {
  SOURCE_CIRCLE_ARC,
  SOURCE_CIRCLE_ARC_BOTTOM_PATH_D,
  SOURCE_CIRCLE_ARC_BOTTOM_R,
  SOURCE_CIRCLE_ARC_PATH_D,
  SOURCE_CIRCLE_BORDER,
  SOURCE_CIRCLE_SHAPE,
  sourceArcPathD,
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

describe("Change 222 — nackte Quellen-Zeichen, Kreise in den Zonen", () => {
  test("(a) das Optionen-Panel steht im DOM NACH den Quellen und dem Bereich darunter", () => {
    const { getByTestId } = renderZone();
    const quellen = getByTestId("source-row");
    const bereich = getByTestId("area-upload");
    const optionen = getByTestId("options-panel");

    expect(stehtNach(optionen, quellen)).toBe(true);
    expect(stehtNach(optionen, bereich)).toBe(true);
    // … und NICHT darüber: das Panel liegt nach den Quellen, die Quellen nicht
    // nach dem Panel.
    expect(stehtNach(quellen, optionen)).toBe(false);
    expect(stehtNach(bereich, optionen)).toBe(false);
  });

  test("(b) die Tab-Reihe trägt drei NACKTE Zeichen — Kreis und Text stehen in der Zone", () => {
    const { getByTestId } = renderZone();
    const reihe = getByTestId("source-row");
    const zeichen = Array.from(reihe.querySelectorAll<HTMLElement>(".ps-src-tab"));
    expect(zeichen).toHaveLength(3);
    expect(zeichen.map((k) => k.getAttribute("data-ps-source"))).toEqual([
      "upload",
      "record",
      "download",
    ]);

    for (const zeichenEl of zeichen) {
      const art = zeichenEl.getAttribute("data-ps-source")!;
      const knopf = zeichenEl.querySelector<HTMLButtonElement>("button.ps-src-tab-btn")!;
      expect(knopf, `${art}: Umschalter-Knopf fehlt`).toBeTruthy();
      // Zeichen vorhanden …
      expect(knopf.querySelector(`svg[data-ps-icon="${art}"]`), `${art}: Zeichen fehlt`).toBeTruthy();
      // … aber KEIN Kreis und KEIN Kreistext in der Reihe (Change 222).
      expect(knopf.className, `${art}: Umschalter darf kein Kreis sein`).not.toContain("rounded-full");
      expect(zeichenEl.querySelector(".ps-src-arc"), `${art}: Text gehört nicht in die Reihe`).toBeNull();
      // Kein wirkungsloser Knopf: der Name steckt in aria-label und title.
      expect(knopf.getAttribute("aria-label")).toBeTruthy();
      expect(knopf.getAttribute("title")).toBe(knopf.getAttribute("aria-label"));
    }

    // Die Kreise mit Beschriftung stehen in ihren Zonen: Upload-Ablegefläche …
    const uploadZone = getByTestId("area-upload");
    const uploadKreis = within(uploadZone).getByTestId("upload-button");
    expect(uploadKreis.querySelector('svg[data-ps-icon="upload"]')).toBeTruthy();
    const uploadText = uploadZone.querySelector(".ps-src-arc-text textPath")!;
    expect(uploadText).toBeTruthy();
    expect(uploadText.getAttribute("href")).toBe("#ps-source-arc-upload");
    expect(uploadText.getAttribute("startOffset")).toBe("50%");
    expect((uploadText.textContent ?? "").trim()).toBe("Upload");
    // … und Adress-Zone.
    fireEvent.click(within(getByTestId("source-download")).getByRole("button"));
    const urlZone = getByTestId("area-url");
    const downloadKreis = within(urlZone).getByTestId("download-button");
    expect(downloadKreis.querySelector('svg[data-ps-icon="download"]')).toBeTruthy();
    const downloadText = urlZone.querySelector(".ps-src-arc-text textPath")!;
    expect((downloadText.textContent ?? "").trim()).toBe("Download");
    expect(downloadText.getAttribute("href")).toBe("#ps-source-arc-download");
  });

  test("(c) alle Kreise sind gleich groß und gleich gebaut wie der Aufnahmeknopf", () => {
    const { getByTestId } = renderZone();
    // Upload-Kreis
    const uploadKreis = getByTestId("upload-button");
    fireEvent.click(within(getByTestId("source-download")).getByRole("button"));
    const downloadKreis = getByTestId("download-button");
    fireEvent.click(within(getByTestId("source-record")).getByRole("button"));
    const recordKreis = getByTestId("record-button");

    const formklassen = [uploadKreis, downloadKreis, recordKreis].map((k) =>
      Array.from(k.classList)
        .filter((c) => /^(sm:)?(w-|h-|rounded-)/.test(c))
        .sort()
        .join(" ")
    );
    // Eine Bauart für alle drei — dieselbe Klasse wie der Aufnahmeknopf.
    expect(new Set(formklassen).size).toBe(1);
    expect(formklassen[0]).toBe(SOURCE_CIRCLE_SHAPE.split(" ").sort().join(" "));
    expect(RECORD_BUTTON_SHAPE.split(" ").sort().join(" ")).toBe(formklassen[0]);

    // Eine einzige Ring-Regel für alle: gleiche Stärke, Outline (kein Füllkörper).
    const ring = rule(".ps-src-btn {");
    expect(ring).toContain(`border: ${SOURCE_CIRCLE_BORDER}px solid`);
    expect(ring).toContain("background: transparent");

    // Gleicher Kreistext: genau eine Regel mit der Schriftgröße.
    expect(css.match(/\.ps-src-arc-text \{/g) ?? []).toHaveLength(1);
    expect(rule(".ps-src-arc-text {")).toContain(
      `font-size: ${SOURCE_CIRCLE_ARC.fontSize}px`
    );

    // Gleicher Bogen: EINE Geometrie-Konstante (ein Radius, oberer Halbkreis).
    const boegen = [
      getByTestId("source-row").ownerDocument.querySelectorAll(
        '.ps-src-arc-svg defs path[id^="ps-source-arc-"]'
      ),
    ].flatMap((liste) => Array.from(liste).map((p) => p.getAttribute("d")));
    // (nach dem Umschalten steht nur ein Kreis im DOM — deshalb hier prüfen,
    // dass ALLE gefundenen Bögen dieselbe Geometrie tragen.)
    for (const d of boegen) expect(d).toBe(SOURCE_CIRCLE_ARC_PATH_D);
    expect(SOURCE_CIRCLE_ARC_PATH_D).toContain(
      `A ${SOURCE_CIRCLE_ARC.r} ${SOURCE_CIRCLE_ARC.r} 0 0 1`
    );
  });

  test("(c2) der gewählte Umschalter ist nicht nur an der Farbe zu erkennen", () => {
    const { getByTestId } = renderZone();
    const upload = getByTestId("source-upload");
    const knopf = within(upload).getByRole("button");
    expect(knopf.getAttribute("aria-pressed")).toBe("true");
    expect(upload.getAttribute("data-ps-selected")).toBe("true");
    expect(knopf.className).toContain("ps-src-on");
    // Zweite, nicht-farbliche Kennzeichnung: der Strich unter dem Zeichen.
    expect(rule(".ps-src-tab-btn.ps-src-on::after {")).toContain("height: 2px");
    // Und der gewählte Tab ist der einzige mit dieser Klasse.
    const reihe = getByTestId("source-row");
    expect(reihe.querySelectorAll(".ps-src-tab-btn.ps-src-on")).toHaveLength(1);
  });

  test("(d) die Adress-Zeile steht IN der Adress-Zone und trägt den Beispiel-Platzhalter", () => {
    const { getByTestId } = renderZone();
    fireEvent.click(within(getByTestId("source-download")).getByRole("button"));

    const zone = getByTestId("area-url");
    const zeile = within(zone).getByTestId("url-line");
    // Die Zeile liegt WIRKLICH in der Zone (nicht mehr darüber, Change 222).
    expect(zone.contains(zeile)).toBe(true);
    // … und steht über dem Kreis, der den Import startet.
    const kreis = within(zone).getByTestId("download-button");
    expect(stehtNach(kreis, zeile)).toBe(true);

    const eingabe = within(zeile).getByTestId("url-input") as HTMLInputElement;
    expect(eingabe.getAttribute("placeholder")).toMatch(
      /^https:\/\/youtube\.com\/watch\?v=/
    );
    expect(eingabe.className).toContain("ps-url-input");
    // Die Zeile nimmt die Breite der Zone ein (kein Überlaufen am Zonenrand).
    const zeilenRegel = rule(".ps-zone-url .ps-url-row {");
    expect(zeilenRegel).toContain("width: 100%");
    expect(rule(".ps-url-input {")).toContain("width: 100%");
  });

  test("(d2) der Formathinweis im Upload ist entfallen", () => {
    const { getByTestId } = renderZone();
    const zone = getByTestId("area-upload");
    expect(zone.querySelector(".ps-zone-note")).toBeNull();
    // Der Hinweis-Text selbst steht nicht mehr im DOM.
    expect(zone.textContent ?? "").not.toMatch(/MP3|M4A|MP4|WEBM|OGG/);
    // Titel und Mehrfach-Hinweis bleiben — die Fläche erklärt sich weiter.
    expect(zone.querySelector(".ps-zone-title")).toBeTruthy();
    expect(zone.querySelector(".ps-zone-hint")).toBeTruthy();
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

    // Die Gestenhinweise arbeiten weiter: Kopie + Kreistext am Knopf.
    const kopie = getByTestId("record-ghost");
    const text = getByTestId("record-tip");
    expect(kopie.className).toContain(RECORD_BUTTON_SHAPE);
    expect(kopie.querySelector(".ps-record-ghost-ring")).toBeTruthy();
    expect(text.querySelector("textPath")).toBeTruthy();
    expect((text.querySelector("textPath")!.textContent ?? "").length).toBeGreaterThan(0);
  });

  test("(g) der Kreistext sitzt rund 5 px außerhalb des Rings — in jeder Knopfgröße", () => {
    // Nutzer-Vorgabe 20.09.2026: „Texte entlang des Pfades näher am Kreis ca.
    // 5px Abstand."
    // Knopfgrößen aus SOURCE_CIRCLE_SHAPE: 64 px (w-16) bzw. 80 px (sm:w-20).
    // Der Ring ist ein border (border-box) — seine AUSSENkante liegt damit
    // genau auf der Knopfkante, also bei 32 px bzw. 40 px.
    const ringAussenMobil = 64 / 2;
    const ringAussenDesktop = 80 / 2;
    const skalaDesktop = 80 / 64; // = 1,25: die Zeichenfläche wächst mit
    const unterlaenge = 2.4;      // „p" in „Upload" bei 10 px Schrift

    // Die Schrift läuft auf dem Kreis mit dem Radius r (Grundlinie).
    const abstandMobil = SOURCE_CIRCLE_ARC.r - ringAussenMobil;
    const abstandDesktop = SOURCE_CIRCLE_ARC.r * skalaDesktop - ringAussenDesktop;

    // „ca. 5 px": zwischen 3,5 und 6,5 px — vorher waren es 14 px (mobil) bzw.
    // 6 px (Desktop, r = 46).
    for (const [lage, abstand] of [
      ["mobil", abstandMobil],
      ["Desktop", abstandDesktop],
    ] as const) {
      expect(abstand, `Textabstand ${lage}`).toBeGreaterThanOrEqual(3.5);
      expect(abstand, `Textabstand ${lage}`).toBeLessThanOrEqual(6.5);
    }
    // Beide Stufen liegen praktisch gleich weit weg (Unterschied unter 1,5 px).
    expect(Math.abs(abstandDesktop - abstandMobil)).toBeLessThan(1.5);
    // … und die Schrift liegt nie IM Ring: auch die Unterlänge („p" in
    // „Upload") bleibt außerhalb der Ringaußenkante.
    expect(abstandMobil - unterlaenge, "Unterlänge bleibt außerhalb (mobil)").toBeGreaterThan(0);
    expect(abstandDesktop - unterlaenge * skalaDesktop,
      "Unterlänge bleibt außerhalb (Desktop)").toBeGreaterThan(0);

    // Damit das auch auf dem Gerät gilt, MUSS die Zeichenfläche mit dem Knopf
    // wachsen: Prozentwerte relativ zur Knopfgröße, KEINE festen px und KEINE
    // zusätzliche Medienabfrage (die erste 640-px-Abfrage ist die der Zonen,
    // zone.test.tsx verlangt sie VOR der Zonenhöhe).
    const flaeche = rule(".ps-src-arc {");
    expect(flaeche, "Breite prozentual zur Knopfgröße").toContain("218.75%");
    expect(flaeche, "Höhe prozentual zur Knopfgröße").toContain("81.25%");
    expect(flaeche, "keine feste Breite in px").not.toMatch(/width:\s*\d+px/);
    expect(flaeche, "keine feste Höhe in px").not.toMatch(/height:\s*\d+px/);
    // Die Prozentwerte müssen die Zeichenfläche der SVG genau treffen
    // (140/64 : 52/64), sonst verzerrt der Text.
    expect(218.75 / 81.25).toBeCloseTo((140 / 64) / (52 / 64), 3);
    expect(SOURCE_CIRCLE_ARC.width / SOURCE_CIRCLE_ARC.height).toBeCloseTo(140 / 52, 6);

    // Der Bezugsrahmen ist der Kreis in der Zone — die Zeichenfläche muss
    // deshalb an DIESEM Element hängen (nicht an der Tab-Reihe).
    expect(rule(".ps-zone-circle {")).toContain("position: relative");
  });

  test("(h) an keinem Text läuft noch eine Animation (Drehung entfallen)", () => {
    // Nutzer-Vorgabe 20.09.2026: „Generell lassen wir die Animation der Texte
    // sein, die ist zu unruhig."
    // (Kommentare werden ausgeblendet: sie NENNEN die alten Namen, damit die
    // Entfernung nachvollziehbar bleibt.)
    const cssOhne = css.replace(/\/\*[\s\S]*?\*\//g, "");
    expect(cssOhne).not.toContain("ps-src-arc-spin");
    expect(cssOhne).not.toContain("ps-record-arc-spin");
    expect(cssOhne).not.toContain("@keyframes ps-src-spin");
    expect(cssOhne).not.toContain("@keyframes ps-record-spin");
    expect(cssOhne).not.toMatch(/\.ps-src-arc-text[^{]*\{[^}]*animation/);
    expect(cssOhne).not.toMatch(/\.ps-record-arc-text[^{]*\{[^}]*animation/);

    // Auch die Bauteile drehen nichts mehr: weder die Gruppe noch die Konstante.
    const { getByTestId } = renderZone();
    const uploadZone = getByTestId("area-upload");
    expect(uploadZone.querySelector("g.ps-src-arc-spin")).toBeNull();
    expect(uploadZone.querySelector(".ps-src-arc svg > g")).toBeNull();
    // Der Text hängt direkt unter der Zeichenfläche.
    expect(uploadZone.querySelector(".ps-src-arc svg > text")).toBeTruthy();

    // Und die Luft für den Kreistext steht in der Zone (sonst schneidet
    // `overflow: hidden` die Schrift ab).
    expect(rule(".ps-zone-stack {")).toContain("padding-top: var(--ps-arc-reserve)");
    expect(rule(":root {")).toContain("--ps-arc-reserve: 20px");
  });

  test("(i) die Beschriftung des Download-Kreises steht UNTER dem Kreis — der Kreis bleibt stehen", () => {
    // Change 223 (Nutzer-Vorgaben 20.09.2026):
    //   „Beim Download Button entferne die extra Erklärung, mit dem Beispieltext
    //    in der textarea und dem mit Download beschrifteten Button erklärt sich
    //    die Funktion. Mache die Button Beschreibung unten an den Kreis."
    //   „Achte darauf das alle Kreise an der gleichen Position bleiben."
    const { getByTestId } = renderZone();
    fireEvent.click(within(getByTestId("source-download")).getByRole("button"));

    const kreis = getByTestId("download-button");
    const beschriftung = kreis.parentElement!.querySelector(".ps-src-arc");
    expect(beschriftung, "keine Beschriftung am Download-Kreis").toBeTruthy();
    expect(beschriftung!.className, "untere Lage").toContain("ps-src-arc--bottom");

    // Unterer Bogen: gleicher Radius wie oben, umgekehrte Laufrichtung (sweep 0)
    // — dadurch steht die Schrift aufrecht unter dem Kreis.
    const pfad = beschriftung!.querySelector("path")!;
    expect(pfad.getAttribute("d")).toBe(SOURCE_CIRCLE_ARC_BOTTOM_PATH_D);
    expect(pfad.getAttribute("d")).toContain(
      `A ${SOURCE_CIRCLE_ARC_BOTTOM_R} ${SOURCE_CIRCLE_ARC_BOTTOM_R} 0 0 0`
    );
    // Change 224 (Nutzer: „Die ‚download' Beschriftung des Buttons hat einen
    // anderen Abstand als ‚Upload' und die UI Hints."): Unten braucht der Bogen
    // einen größeren Radius, weil dort die GROSSBUCHSTABEN zur Kreismitte
    // zeigen (oben sind es die Unterlängen). Mit demselben Radius saß „Download"
    // sichtbar im Ring — im Browser gemessen 13,66 px Überlappung gegen 2,59 px
    // oben. Prüfgröße ist der Abstand der Tinte zur Kreismitte, in px:
    const kapitalhoehe = 7.2;   // „D" bei 10 px Schrift in der Zeichenfläche
    const unterlaenge = 2.4;    // „p" in „Upload" bei 10 px Schrift
    const tinteOben = SOURCE_CIRCLE_ARC.r - unterlaenge;
    const tinteUnten = SOURCE_CIRCLE_ARC_BOTTOM_R - kapitalhoehe;
    expect(
      Math.abs(tinteUnten - tinteOben),
      `Tinte unten ${tinteUnten} px gegen oben ${tinteOben} px`
    ).toBeLessThan(5);
    expect(SOURCE_CIRCLE_ARC_BOTTOM_R, "unterer Bogen weiter außen")
      .toBeGreaterThan(SOURCE_CIRCLE_ARC.r);
    expect(sourceArcPathD("bottom")).not.toBe(sourceArcPathD("top"));
    expect(sourceArcPathD("top")).toBe(SOURCE_CIRCLE_ARC_PATH_D);

    // Die Lage ist ABSOLUT — sie kann den Kreis nicht verschieben (deshalb
    // bleiben alle Kreise an derselben Position).
    expect(rule(".ps-src-arc {")).toContain("position: absolute");
    expect(rule(".ps-src-arc--bottom {")).toContain("top: 50%");
    expect(rule(".ps-src-arc--bottom {")).toContain("bottom: auto");

    // Die Erklärzeile der Adress-Zone ist entfallen („erklärt sich die Funktion").
    const adressZone = document.querySelector(".ps-zone-url")!;
    expect(adressZone.querySelector(".ps-zone-hint"), "Erklärzeile noch da").toBeNull();
    expect(adressZone.textContent).not.toContain("Adresse oben eintragen");
    // Der Beispiel-Platzhalter in der Eingabe bleibt (er erklärt die Eingabe).
    expect(getByTestId("url-input").getAttribute("placeholder")).toContain("youtube.com");
    // … und der Kreis bleibt trotzdem, wo er war: der frei gewordene Platz steht
    // als Abstand unten im Stapel (Nutzer: „Achte darauf das alle Kreise an der
    // gleichen Position bleiben"). Ohne ihn rutschte der Kreis ~10 px tiefer
    // (im Browser gemessen: 120,11 → 130,06 px).
    expect(rule(".ps-zone-url .ps-zone-stack {")).toContain("padding-bottom: 20px");
  });
});
