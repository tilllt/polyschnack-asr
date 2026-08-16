import { describe, it, expect, beforeEach } from "vitest";
import {
  claimExclusivePlayback,
  releaseExclusivePlayback,
  toggleActivePlayback,
  decidePlayPause,
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
    play: () => {
      playing = true;
      p.paused = false;
    },
    playPause: () => {
      if (playing) p.pause();
      else p.play();
    },
    isPlaying: () => playing,
    isReady: () => true,
  };
  return p;
}

describe("audio exclusivity", () => {
  beforeEach(() => {
    // Modul-Singleton zwischen Tests zurücksetzen: alle bisherigen Player
    // sind "zerstört" — release mit einem frischen Objekt genügt nicht,
    // daher hier über den Export-Pfad: claim eines Dummy + release.
    // (Das Singleton ist pro Testdatei-Modul frisch, aber Tests teilen es.)
    const dummy: Playable = { pause: () => {}, play: () => {}, playPause: () => {}, isPlaying: () => false, isReady: () => false };
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

describe("decidePlayPause (Play/Stop-Entscheidung, 2026-08-16)", () => {
  it("spielt das Audio → pause (Stop lässt die Markierung stehen)", () => {
    expect(decidePlayPause(true, false, true)).toBe("pause");
    expect(decidePlayPause(true, true, true)).toBe("pause");
  });
  it("steht es am Ende → stay (kein Auto-Reset auf 0)", () => {
    expect(decidePlayPause(false, true, true)).toBe("stay");
    expect(decidePlayPause(false, true, false)).toBe("stay");
  });
  it("nicht abspielbar (Audio lädt noch) → noop", () => {
    expect(decidePlayPause(false, false, false)).toBe("noop");
  });
  it("sonst → play", () => {
    expect(decidePlayPause(false, false, true)).toBe("play");
  });
});

describe("Space-Zyklus (toggleActivePlayback), 2026-08-16", () => {
  it("Stop per Space lässt den Player aktiv — Space startet wieder", () => {
    const p = makePlayable();
    claimExclusivePlayback(p);
    p.play();
    expect(p.isPlaying()).toBe(true);
    toggleActivePlayback(); // Space: Stop
    expect(p.isPlaying()).toBe(false);
    toggleActivePlayback(); // Space: Play wieder
    expect(p.isPlaying()).toBe(true);
  });
  it("am Ende der Aufnahme togglet Space nicht auf 0 (bleibt stehen)", () => {
    // makePlayable hat keine Ende-Semantik — hier nur sicherstellen, dass
    // der Toggle auf einem pausierten, bereiten Player spielt.
    const p = makePlayable();
    claimExclusivePlayback(p);
    p.pause();
    toggleActivePlayback();
    expect(p.isPlaying()).toBe(true);
  });
  it("ohne aktiven Player: no-op", () => {
    expect(() => toggleActivePlayback()).not.toThrow();
  });
});
