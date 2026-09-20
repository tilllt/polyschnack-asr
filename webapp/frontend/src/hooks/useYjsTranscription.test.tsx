/** Change 207: Der Autosave darf nicht in eine Schleife laufen.
 *
 * Befund aus der Produktion (19.09.2026): für EINE Aufnahme 1090 abgewiesene
 * Speicherungen, 675 davon in 7 Sekunden, und **keine einzige erfolgreiche** —
 * die Bearbeitung des Nutzers kam nie in der Datenbank an.
 *
 * Ursache: `save` hing mit seiner Identität an `saving`, der Provider-Effekt
 * hängt an `save`. Jeder Speicherversuch (Erfolg wie Fehler) baute damit den
 * Yjs-Provider und die WebSocket-Verbindung neu auf und löste den nächsten
 * Autosave aus.
 *
 * Change 216 (Nutzer-Befund 20.09.2026): Der Toast „Not saved yet — one
 * segment is empty" erschien beim LADEN der Seite, ohne jede Interaktion.
 * Grund: Der Zusammenarbeits-Raum liefert beim Verbinden seinen Stand (hier
 * ein Altbestand aus leeren Segmenten), dieser Doc-Update-Termin plante den
 * Autosave, und der Sonderfall „alle Segmente leer" meldete `empty_text`.
 * Festschreibung: Die Ladephase schreibt und meldet NIE; ein vorgefundener
 * Leerstand wird verworfen und der Serverstand angezeigt. Ein leeres Segment
 * unter mehreren fällt weiterhin still aus der Liste (Change 213). Meldungen
 * nennen Aufnahme und Segment (Aufbereitung siehe SegmentList).
 */
import * as Y from "yjs";
import { act, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const providerInstances: unknown[] = [];
/** Die Y.Docs, mit denen der Hook die Provider gebaut hat — damit lässt sich
 *  der Stand eines Zusammenarbeits-Raums beim Laden simulieren. */
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
      providerInstances.push(this);
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

const replaceSegments = vi.fn(async () => ({
  segments: [],
  text: "",
  segments_manual: true,
}));

vi.mock("../api", () => ({
  replaceSegments: (...args: unknown[]) => replaceSegments(...(args as [])),
}));

import { useYjsTranscription } from "./useYjsTranscription";

interface Meldung {
  reason: string;
  idx?: number;
}

function Harness({
  segments,
  onSaveError,
  onRemote,
}: {
  segments: { text: string }[];
  onSaveError: (reason: string, detail?: { segmentIndex?: number }) => void;
  onRemote?: (texts: string[]) => void;
}) {
  const { setSegmentText, setEditingActive } = useYjsTranscription(
    "rec1",
    segments,
    onRemote,
    true,
    null,
    onSaveError,
  );
  return (
    <div>
      {segments.map((_s, i) => (
        <button
          key={i}
          onClick={() => {
            // Wie in der Oberfläche: Segment zum Bearbeiten öffnen, dann leeren.
            setEditingActive(i);
            setSegmentText(i, "");
          }}
        >
          {`leeren ${i}`}
        </button>
      ))}
      <button
        onClick={() => {
          setEditingActive(0);
          setSegmentText(0, "neuer text");
        }}
      >
        tippen
      </button>
    </div>
  );
}

describe("useYjsTranscription — Autosave (Change 207) und Ladephase (Change 216)", () => {
  beforeEach(() => {
    providerInstances.length = 0;
    providerDocs.length = 0;
    replaceSegments.mockClear();
    replaceSegments.mockImplementation(async () => ({
      segments: [],
      text: "",
      segments_manual: true,
    }));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("baut den Provider nur einmal auf", () => {
    render(<Harness segments={[{ text: "hallo" }]} onSaveError={() => {}} />);
    expect(providerInstances).toHaveLength(1);
  });

  it("Laden der Seite erzeugt keine Meldung und keinen Speichervorgang", async () => {
    vi.useFakeTimers();
    const meldungen: Meldung[] = [];
    render(
      <Harness
        segments={[{ text: "hallo" }, { text: "welt" }]}
        onSaveError={(r, d) => meldungen.push({ reason: r, idx: d?.segmentIndex })}
      />,
    );

    await act(async () => {
      await vi.advanceTimersByTimeAsync(8000);
    });

    expect(meldungen).toEqual([]);
    expect(replaceSegments).not.toHaveBeenCalled();
    expect(providerInstances).toHaveLength(1);
  });

  it("Leerstand aus dem Raum beim Laden: nicht gespeichert, keine Meldung, Serverstand angezeigt", async () => {
    vi.useFakeTimers();
    const meldungen: Meldung[] = [];
    const angezeigt: string[][] = [];
    render(
      <Harness
        segments={[{ text: "hallo" }, { text: "welt" }]}
        onSaveError={(r, d) => meldungen.push({ reason: r, idx: d?.segmentIndex })}
        onRemote={(texts) => angezeigt.push(texts)}
      />,
    );

    const doc = providerDocs[0];
    await act(async () => {
      // Der Raum meldet beim Verbinden seinen Stand: hier ein Altbestand,
      // in dem ALLE Segmente leer sind.
      const map = doc.getMap<Y.Text>("segments");
      doc.transact(() => {
        map.set("0", new Y.Text(""));
        map.set("1", new Y.Text(""));
      });
      await vi.advanceTimersByTimeAsync(8000);
    });

    // Kein Toast beim Laden, kein Schreiben des Leerstands.
    expect(meldungen).toEqual([]);
    expect(replaceSegments).not.toHaveBeenCalled();
    // Stattdessen steht der Serverstand im Dokument und in der Anzeige.
    const map = doc.getMap<Y.Text>("segments");
    expect([map.get("0")?.toString(), map.get("1")?.toString()]).toEqual([
      "hallo",
      "welt",
    ]);
    expect(angezeigt[angezeigt.length - 1]).toEqual(["hallo", "welt"]);
  });

  it("ein leeres Segment unter mehreren erzeugt keine Meldung (Change 213 bleibt)", async () => {
    vi.useFakeTimers();
    const meldungen: Meldung[] = [];
    const { getByText } = render(
      <Harness
        segments={[{ text: "a" }, { text: "b" }, { text: "c" }]}
        onSaveError={(r, d) => meldungen.push({ reason: r, idx: d?.segmentIndex })}
      />,
    );

    await act(async () => {
      getByText("leeren 1").click();
      await vi.advanceTimersByTimeAsync(8000);
    });

    expect(meldungen).toEqual([]);
    expect(replaceSegments).toHaveBeenCalledTimes(1);
    const [, segmente] = replaceSegments.mock.calls[0] as unknown as [
      string,
      { text: string }[],
    ];
    // Das leere Segment fällt heraus, die anderen bleiben.
    expect(segmente.map((s) => s.text)).toEqual(["a", "c"]);
  });

  it("alle Segmente geleert (Nutzeraktion): nichts gespeichert, Meldung nennt das Segment", async () => {
    vi.useFakeTimers();
    const meldungen: Meldung[] = [];
    const { getByText } = render(
      <Harness
        segments={[{ text: "hallo" }]}
        onSaveError={(r, d) => meldungen.push({ reason: r, idx: d?.segmentIndex })}
      />,
    );

    await act(async () => {
      getByText("leeren 0").click();
      await vi.advanceTimersByTimeAsync(8000);
    });

    expect(replaceSegments).not.toHaveBeenCalled();
    expect(meldungen).toHaveLength(1);
    expect(meldungen[0].reason).toBe("empty_text");
    // Die Oberfläche kann damit „Aufnahme, Segment N" nennen.
    expect(meldungen[0].idx).toBe(0);
    expect(providerInstances).toHaveLength(1);
  });

  it("speichert einen gefüllten Stand genau einmal — ohne Neuverbindung", async () => {
    vi.useFakeTimers();
    const { getByText } = render(
      <Harness segments={[{ text: "hallo" }]} onSaveError={() => {}} />,
    );

    await act(async () => {
      getByText("tippen").click();
      await vi.advanceTimersByTimeAsync(8000);
    });

    expect(replaceSegments).toHaveBeenCalledTimes(1);
    const [rid, segmente] = replaceSegments.mock.calls[0] as unknown as [string, { text: string }[]];
    expect(rid).toBe("rec1");
    expect(segmente[0].text).toBe("neuer text");
    expect(providerInstances).toHaveLength(1);
  });

  it("hämmert nach einem Fehlversuch nicht im Sekundentakt weiter", async () => {
    vi.useFakeTimers();
    replaceSegments.mockImplementation(async () => {
      throw new Error("kaputt");
    });
    const { getByText } = render(
      <Harness segments={[{ text: "hallo" }]} onSaveError={() => {}} />,
    );

    await act(async () => {
      getByText("tippen").click();
      await vi.advanceTimersByTimeAsync(8000);
    });

    // Ein Versuch, dann Backoff: in 8 s darf es nicht dutzendfach feuern.
    expect(replaceSegments.mock.calls.length).toBeLessThanOrEqual(3);
  });
});
