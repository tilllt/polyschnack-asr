import { describe, it, expect } from "vitest";
import {
  resolveBackend,
  LARGE_FILE_THRESHOLD_S,
} from "./WaveformPlayer";

/**
 * Change 049: Streaming-Playback für sehr lange Aufnahmen.
 * WebAudio dekodiert die komplette Datei in den RAM (~560 MB PCM bei
 * 4h52min) → Mobilgeräte schaffen das nicht. Ab der Schwelle wird auf das
 * MediaElement-Backend (Streaming per Range-Request) umgeschaltet.
 * Change 112 (2026-08-23): Schwelle 2 h → 30 min (Android-OOM-Befund:
 * 95-min-Aufnahme = ~180 MB PCM-Voll-Dekode pro Karte im WebAudio-Pfad).
 */
describe("resolveBackend (Change 049 + 112)", () => {
  it("kurze Aufnahmen nutzen WebAudio (Karaoke-Präzision)", () => {
    expect(resolveBackend(null)).toBe("WebAudio");
    expect(resolveBackend(undefined)).toBe("WebAudio");
    expect(resolveBackend(0)).toBe("WebAudio");
    expect(resolveBackend(120)).toBe("WebAudio"); // 2 min
    expect(resolveBackend(1700)).toBe("WebAudio"); // knapp unter 30 min
  });

  it("lange Aufnahmen streamen über MediaElement (kein Voll-Dekode)", () => {
    expect(resolveBackend(5710)).toBe("MediaElement"); // 95 min (Android-Befund 23.08.)
    expect(resolveBackend(3599)).toBe("MediaElement"); // 1 h
    expect(resolveBackend(17570)).toBe("MediaElement"); // 4h52min (049-Befund)
    expect(resolveBackend(11182)).toBe("MediaElement"); // 3 h
    expect(resolveBackend(LARGE_FILE_THRESHOLD_S + 1)).toBe("MediaElement");
  });

  it("Grenze: exakt 30 min bleibt WebAudio (nur oberhalb streamt)", () => {
    expect(resolveBackend(LARGE_FILE_THRESHOLD_S)).toBe("WebAudio");
    expect(resolveBackend(LARGE_FILE_THRESHOLD_S - 1)).toBe("WebAudio");
  });
});
