/** Change 207: Der Autosave darf nicht in eine Schleife laufen.
 *
 * Befund aus der Produktion (19.09.2026): für EINE Aufnahme 1090 abgewiesene
 * Speicherungen, 675 davon in 7 Sekunden, und **keine einzige erfolgreiche** —
 * die Bearbeitung des Nutzers kam nie in der Datenbank an.
 *
 * Ursache: `save` hing mit seiner Identität an `saving`, der Provider-Effekt
 * hängt an `save`. Jeder Speicherversuch (Erfolg wie Fehler) baute damit den
 * Yjs-Provider und die WebSocket-Verbindung neu auf und löste den nächsten
 * Autosave aus. Dazu wurde ein Stand mit leerem Segment gesendet, den der
 * Server ablehnt, und der Fehler still geschluckt.
 *
 * Festschreibung hier:
 *  1. Der Provider wird genau EINMAL aufgebaut — auch bei Speicherversuchen.
 *  2. Ein Stand mit leerem Segment wird nicht gesendet (kein 400-Hämmern),
 *     sondern sichtbar gemeldet.
 *  3. Ein gefüllter Stand wird genau einmal gespeichert.
 */
import { act, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const providerInstances: unknown[] = [];

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
    constructor() {
      providerInstances.push(this);
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

function Harness({ onSaveError }: { onSaveError: (reason: string) => void }) {
  const { setSegmentText } = useYjsTranscription(
    "rec1",
    [{ text: "hallo" }],
    undefined,
    true,
    null,
    onSaveError,
  );
  return (
    <div>
      <button onClick={() => setSegmentText(0, "")}>leeren</button>
      <button onClick={() => setSegmentText(0, "neuer text")}>tippen</button>
    </div>
  );
}

describe("useYjsTranscription — Autosave-Schleife (Change 207)", () => {
  beforeEach(() => {
    providerInstances.length = 0;
    replaceSegments.mockClear();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("baut den Provider nur einmal auf", () => {
    render(<Harness onSaveError={() => {}} />);
    expect(providerInstances).toHaveLength(1);
  });

  it("sendet keinen Stand mit leerem Segment und meldet es sichtbar", async () => {
    vi.useFakeTimers();
    const meldungen: string[] = [];
    const { getByText } = render(<Harness onSaveError={(r) => meldungen.push(r)} />);

    await act(async () => {
      getByText("leeren").click();
      await vi.advanceTimersByTimeAsync(8000);
    });

    expect(replaceSegments).not.toHaveBeenCalled();
    expect(meldungen).toContain("empty_text");
    expect(providerInstances).toHaveLength(1);
  });

  it("speichert einen gefüllten Stand genau einmal — ohne Neuverbindung", async () => {
    vi.useFakeTimers();
    const { getByText } = render(<Harness onSaveError={() => {}} />);

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
    const { getByText } = render(<Harness onSaveError={() => {}} />);

    await act(async () => {
      getByText("tippen").click();
      await vi.advanceTimersByTimeAsync(8000);
    });

    // Ein Versuch, dann Backoff: in 8 s darf es nicht dutzendfach feuern.
    expect(replaceSegments.mock.calls.length).toBeLessThanOrEqual(3);
  });
});
