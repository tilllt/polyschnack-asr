import { describe, it, expect, beforeEach } from "vitest";
import {
  claimExclusivePlayback,
  releaseExclusivePlayback,
  type Playable,
} from "./WaveformPlayer";

/**
 * Audio-Exklusivität (2026-08-15, User-Anforderung):
 * „Stelle sicher, dass immer nur ein Audio spielen kann. Wenn ein neues
 * angeklickt wird, hört eins, was schon spielt, auf."
 *
 * Modul-Singleton in WaveformPlayer.tsx: claimExclusivePlayback pausiert
 * den bisher aktiven Player, releaseExclusivePlayback gibt die Exklusivität
 * frei (pause/finish/unmount).
 */

function makePlayable(): Playable & { paused: boolean } {
  let playing = false;
  const p: Playable & { paused: boolean } = {
    paused: false,
    pause: () => {
      playing = false;
      p.paused = true;
    },
    isPlaying: () => playing,
  };
  (p as unknown as { play: () => void }).play = () => {
    playing = true;
  };
  return p;
}

describe("audio exclusivity", () => {
  beforeEach(() => {
    // Modul-Singleton zwischen Tests zurücksetzen: alle bisherigen Player
    // sind "zerstört" — release mit einem frischen Objekt genügt nicht,
    // daher hier über den Export-Pfad: claim eines Dummy + release.
    // (Das Singleton ist pro Testdatei-Modul frisch, aber Tests teilen es.)
    const dummy: Playable = { pause: () => {}, isPlaying: () => false };
    claimExclusivePlayback(dummy);
    releaseExclusivePlayback(dummy);
  });

  it("startet einen zweiten Player, wird der erste pausiert", () => {
    const a = makePlayable();
    const b = makePlayable();
    (a as unknown as { play: () => void }).play();
    (b as unknown as { play: () => void }).play();

    claimExclusivePlayback(a);
    claimExclusivePlayback(b);

    expect(a.paused).toBe(true); // a wurde gestoppt
    expect(b.paused).toBe(false); // b läuft weiter
  });

  it("pausiert einen gestoppten Player nicht erneut", () => {
    const a = makePlayable();
    const b = makePlayable();
    (a as unknown as { play: () => void }).play();
    claimExclusivePlayback(a);
    a.pause(); // a stoppt von selbst (z.B. Ende erreicht)
    a.paused = false; // Marker zurücksetzen, um "zweites Pausieren" zu sehen

    (b as unknown as { play: () => void }).play();
    claimExclusivePlayback(b);

    // a ist nicht mehr playing → claim pausiert ihn nicht (kein Doppel-Pause)
    expect(a.paused).toBe(false);
    expect(b.paused).toBe(false);
  });

  it("derselbe Player wird nicht gegen sich selbst pausiert", () => {
    const a = makePlayable();
    (a as unknown as { play: () => void }).play();
    claimExclusivePlayback(a);
    claimExclusivePlayback(a);
    expect(a.paused).toBe(false);
  });

  it("release gibt die Exklusivität frei", () => {
    const a = makePlayable();
    (a as unknown as { play: () => void }).play();
    claimExclusivePlayback(a);
    releaseExclusivePlayback(a);

    const b = makePlayable();
    (b as unknown as { play: () => void }).play();
    claimExclusivePlayback(b);
    // a ist bereits released → b pausiert niemanden
    expect(a.paused).toBe(false);
    expect(b.paused).toBe(false);
  });
});
