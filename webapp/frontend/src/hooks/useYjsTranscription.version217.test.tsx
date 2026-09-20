/**
 * Change 217: Versionsflut stoppen — eine Version nur bei echtem
 * Inhaltsunterschied (Fingerabdruck, NICHT Zeitstempel).
 *
 * Belegter Befund: Aufnahme mit 323 Versionen, viele inhaltsgleich, teils
 * 16 s auseinander; in 1089 Versionen genau EINE mit leerem Segment. Ursache:
 * der Server legte bei jedem Schreiben mit ``create_version=true``
 * bedingungslos eine Version an, und die Clients sendeten denselben Stand
 * mehrfach (Autosave, Edit-Mode-Ende, Grenz-Drag, Undo/Redo).
 *
 * Hier geprüft wird die CLIENT-Seite:
 * - Der Client benutzt denselben Inhalts-Begriff wie der Server (Segmenttexte
 *   in Reihenfolge, getrimmt wie ``rec.text = " ".join(text.strip())``).
 * - Derselbe Inhalt wird nicht zweimal gesendet (genau EINE Version).
 * - Meldet der Server ``changed: false`` (nichts geschrieben, keine Version),
 *   ist das KEIN Fehler (keine Meldung) — aber auch kein Speichererfolg:
 *   ``save`` liefert dann ``false``.
 */
import * as Y from "yjs";
import { act, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const providerDocs: Y.Doc[] = [];

vi.mock("y-websocket", () => {
  class FakeProvider {
    wsconnected = true;
    awareness = {
      clientID: 1,
      getStates: () => new Map(),
      on: () => {},
      off: () => {},
      setLocalStateField: () => {},
    };
    constructor(_url: string, _room: string, doc: Y.Doc) {
      providerDocs.push(doc);
    }
    on() {}
    off() {}
    connect() {}
    disconnect() {}
    destroy() {}
  }
  return { WebsocketProvider: FakeProvider };
});

/** Antwort-Flag des Servers („hat wirklich geschrieben"). */
let serverChanged = true;

const replaceSegments = vi.fn(async (_rid: string, segs: { text: string }[]) => ({
  segments: segs,
  text: segs.map((s) => s.text).join(" "),
  segments_manual: true,
  changed: serverChanged,
  version_created: serverChanged,
}));

vi.mock("../api", () => ({
  replaceSegments: (...args: unknown[]) =>
    replaceSegments(...(args as [string, { text: string }[]])),
}));

import { textsFingerprint, useYjsTranscription } from "./useYjsTranscription";

const ergebnisse: boolean[] = [];

function Harness({
  segments,
  onSaveError,
}: {
  segments: { text: string }[];
  onSaveError?: (reason: string) => void;
}) {
  const { setSegmentText, setEditingActive, save } = useYjsTranscription(
    "rec1",
    segments,
    undefined,
    true,
    null,
    onSaveError,
  );
  return (
    <div>
      <button
        onClick={() => {
          setEditingActive(0);
          setSegmentText(0, "neuer text");
        }}
      >
        tippen
      </button>
      <button onClick={() => setEditingActive(null)}>ende</button>
      <button onClick={() => void save(true).then((ok) => ergebnisse.push(ok))}>
        speichern
      </button>
    </div>
  );
}

describe("Change 217 — Inhalts-Fingerabdruck statt Zeitstempel", () => {
  beforeEach(() => {
    providerDocs.length = 0;
    ergebnisse.length = 0;
    serverChanged = true;
    replaceSegments.mockClear();
    replaceSegments.mockImplementation(async (_rid: string, segs: { text: string }[]) => ({
      segments: segs,
      text: segs.map((s) => s.text).join(" "),
      segments_manual: true,
      changed: serverChanged,
      version_created: serverChanged,
    }));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("Fingerabdruck: Reihenfolge zählt, Außen-Leerzeichen nicht", () => {
    expect(textsFingerprint(["a", "b"])).toBe(textsFingerprint([" a ", "b "]));
    expect(textsFingerprint(["a", "b"])).not.toBe(textsFingerprint(["b", "a"]));
    expect(textsFingerprint(["a", "b"])).not.toBe(textsFingerprint(["a b"]));
  });

  it("gleicher Inhalt zweimal speichern → genau EIN Schreibvorgang", async () => {
    vi.useFakeTimers();
    const { getByText, unmount } = render(
      <Harness segments={[{ text: "hallo" }, { text: "welt" }]} />,
    );

    await act(async () => {
      getByText("tippen").click();
      getByText("ende").click(); // Edit-Mode verlassen → genau EINE Version
      await vi.advanceTimersByTimeAsync(8000); // Autosave + Unmount-Flush
    });
    expect(replaceSegments).toHaveBeenCalledTimes(1);
    const [, , withVersion] = replaceSegments.mock.calls[0] as unknown as [
      string,
      unknown,
      boolean,
    ];
    expect(withVersion).toBe(true);

    await act(async () => {
      unmount(); // Verlassen der Seite flusht noch einmal — inhaltlich gleich
      await vi.advanceTimersByTimeAsync(8000);
    });
    expect(replaceSegments).toHaveBeenCalledTimes(1);
  });

  it("Server meldet identischen Inhalt: keine Meldung, aber kein Erfolg", async () => {
    vi.useFakeTimers();
    serverChanged = false; // nichts geschrieben, keine Version
    const meldungen: string[] = [];
    const { getByText } = render(
      <Harness
        segments={[{ text: "hallo" }, { text: "welt" }]}
        onSaveError={(r) => meldungen.push(r)}
      />,
    );

    await act(async () => {
      getByText("tippen").click();
      getByText("speichern").click();
      await vi.advanceTimersByTimeAsync(8000);
    });

    expect(replaceSegments).toHaveBeenCalledTimes(1);
    expect(meldungen).toEqual([]); // kein Fehler
    expect(ergebnisse).toEqual([false]); // aber auch nicht „gespeichert"
  });

  it("leeres Segment unter mehreren (Change 213) ändert die Dedupe nicht", async () => {
    vi.useFakeTimers();
    const meldungen: string[] = [];
    const { getByText } = render(
      <Harness
        segments={[{ text: "a" }, { text: "b" }, { text: "c" }]}
        onSaveError={(r) => meldungen.push(r)}
      />,
    );

    await act(async () => {
      getByText("tippen").click();
      await vi.advanceTimersByTimeAsync(8000);
    });

    expect(meldungen).toEqual([]);
    expect(replaceSegments).toHaveBeenCalledTimes(1);
    const [, segmente] = replaceSegments.mock.calls[0] as unknown as [
      string,
      { text: string }[],
    ];
    expect(segmente.map((s) => s.text)).toEqual(["neuer text", "b", "c"]);
  });
});
