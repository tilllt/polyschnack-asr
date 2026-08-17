/**
 * Change 2026-08-17: Playback-Speed (x0.5/x1/x2) und Karaoke-Sync.
 *
 * Kernaussage: Die Karaoke-Markierung hängt an der AUDIO-Position
 * (getCurrentTime), nicht an einem Timer — deshalb skaliert sie
 * automatisch korrekt mit jeder Playback-Rate. Das wird hier als
 * Architektur-Regel getestet: activeWordIndex bekommt die Position,
 * keinen Speed-Faktor.
 */
import { describe, expect, it } from "vitest";

import { activeWordIndex, KARAOKE_LEAD_S } from "./karaoke";

describe("Karaoke folgt der Audio-Position (speed-unabhängig)", () => {
  const words = [
    { word: "hallo", start: 10.0, end: 10.5 },
    { word: "welt", start: 10.5, end: 11.0 },
    { word: "test", start: 11.0, end: 11.6 },
  ];

  it("activeWordIndex nutzt die Position direkt — kein Speed-Faktor nötig", () => {
    // Dieselbe Position ergibt dasselbe Wort, egal ob der Player mit
    // x0.5, x1 oder x2 abspielt (die Position im Audio ist absolut).
    const rates = [0.5, 1, 2] as const;
    for (const _rate of rates) {
      // Position 10.4 liegt in "hallo" — unabhängig von der Rate.
      expect(activeWordIndex(words, 10.4, 0)).toBe(0);
      // Position 10.75 liegt in "welt".
      expect(activeWordIndex(words, 10.75, 0)).toBe(1);
    }
  });

  it("Lead ist in Audio-Sekunden — bleibt bei jeder Rate konstant", () => {
    // KARAOKE_LEAD_S = 0.15: Wort wird 150ms VOR dem Start aktiv.
    // Bei x2 läuft die Position doppelt so schnell, aber der Vorlauf
    // ist eine feste Audio-Zeit — die Markierung erscheint weiterhin
    // exakt 150ms vor dem Wortstart im Audio.
    expect(KARAOKE_LEAD_S).toBeCloseTo(0.15, 5);
    // t = 9.9 + 0.15 = 10.05 >= 10.0 → Wort 0 aktiv (Lead greift)
    expect(activeWordIndex(words, 9.9)).toBe(0);
    // t = 9.8 + 0.15 = 9.95 < 10.0 → noch nichts aktiv
    expect(activeWordIndex(words, 9.8)).toBe(-1);
  });

  it("getPlaybackRate-Architektur: Rate ist reine Player-Sache", () => {
    // Die Rate beeinflusst NUR, wie schnell die Position wächst —
    // nicht, wie die Position in Wörter übersetzt wird.
    // (Struktur-Test: kein Speed-Parameter in der Signatur.)
    const fn = activeWordIndex.toString();
    expect(fn).not.toContain("rate");
  });
});
