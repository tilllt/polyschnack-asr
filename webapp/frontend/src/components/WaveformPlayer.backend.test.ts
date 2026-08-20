import { describe, it, expect } from "vitest";
import {
  resolveBackend,
  LARGE_FILE_THRESHOLD_S,
} from "./WaveformPlayer";

/**
 * Change 049: Streaming-Playback für sehr lange Aufnahmen.
 * WebAudio dekodiert die komplette Datei in den RAM (~560 MB PCM bei
 * 4h52min) → Mobilgeräte schaffen das nicht. Ab 2 h Dauer wird auf das
 * MediaElement-Backend (Streaming per Range-Request) umgeschaltet.
 */
describe("resolveBackend (Change 049)", () => {
  it("kurze Aufnahmen nutzen WebAudio (Karaoke-Präzision)", () => {
    expect(resolveBackend(null)).toBe("WebAudio");
    expect(resolveBackend(undefined)).toBe("WebAudio");
    expect(resolveBackend(0)).toBe("WebAudio");
    expect(resolveBackend(120)).toBe("WebAudio"); // 2 min
    expect(resolveBackend(3599)).toBe("WebAudio"); // knapp unter 1 h
  });

  it("sehr lange Aufnahmen streamen über MediaElement", () => {
    expect(resolveBackend(17570)).toBe("MediaElement"); // 4h52min (Befund)
    expect(resolveBackend(11182)).toBe("MediaElement"); // 3 h
    expect(resolveBackend(LARGE_FILE_THRESHOLD_S + 1)).toBe("MediaElement");
  });

  it("Grenze: exakt 2 h bleibt WebAudio (nur oberhalb streamt)", () => {
    expect(resolveBackend(LARGE_FILE_THRESHOLD_S)).toBe("WebAudio");
    expect(resolveBackend(LARGE_FILE_THRESHOLD_S - 1)).toBe("WebAudio");
  });
});
