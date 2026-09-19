/** Change 208: Abbruch-Bedingung der Wortspanne (Timing-Modus).
 *
 * Der Player spielt im Timing-Modus nur die Wortspanne und hält am Ende an.
 * Die Bedingung ist pur gehalten (ohne WaveSurfer), damit sie hier prüfbar ist.
 */
import { describe, expect, it } from "vitest";

import { rangeFinished } from "./WaveformPlayer";

describe("rangeFinished (Change 208)", () => {
  const range = { start: 1.2, end: 1.9 };

  it("noch nicht am Ende → läuft weiter", () => {
    expect(rangeFinished(1.2, range)).toBe(false);
    expect(rangeFinished(1.5, range)).toBe(false);
  });

  it("am Ende oder danach → anhalten", () => {
    expect(rangeFinished(1.9, range)).toBe(true);
    expect(rangeFinished(2.4, range)).toBe(true);
  });

  it("ohne angeforderte Spanne nie abbrechen (normales Playback)", () => {
    expect(rangeFinished(0, null)).toBe(false);
    expect(rangeFinished(999, null)).toBe(false);
  });
});
