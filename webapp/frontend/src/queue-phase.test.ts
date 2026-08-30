/**
 * Change 162 — Queue-Phasen-Anzeige für ALLE Job-Kinds.
 *
 * noteToPhaseKey leitet die Phase aus der progress_note ab (Erstes Wort,
 * Präfix-Logik). Die Note trägt seit Change 150/151 Details wie
 * "diarization 42%" oder "asr Chunk 3/8". Der alte Exakt-Vergleich
 * ("=== diarization") scheiterte an "diarization 42%" und die Queue fiel
 * auf kind="transcribe" zurück (Live-Befund 2026-08-30).
 */
import { describe, expect, it } from "vitest";

import { noteToPhaseKey } from "./components/QueueWatcher";

describe("noteToPhaseKey (Change 162)", () => {
  it("diarization mit Prozentwert → rediarize", () => {
    expect(noteToPhaseKey("diarization 42%")).toBe("rediarize");
    expect(noteToPhaseKey("diarization 0%")).toBe("rediarize");
    expect(noteToPhaseKey("diarization")).toBe("rediarize");
  });

  it("asr mit Chunk-Detail → transcribe", () => {
    expect(noteToPhaseKey("asr")).toBe("transcribe");
    expect(noteToPhaseKey("asr Chunk 3/8")).toBe("transcribe");
  });

  it("alignment mit Gruppen-Detail → align", () => {
    expect(noteToPhaseKey("alignment")).toBe("align");
    expect(noteToPhaseKey("alignment 2/5")).toBe("align");
    expect(noteToPhaseKey("alignment Gruppe 2/5")).toBe("align");
  });

  it("Vor-/Nachphasen → transcribe", () => {
    expect(noteToPhaseKey("preparing")).toBe("transcribe");
    expect(noteToPhaseKey("vad")).toBe("transcribe");
    expect(noteToPhaseKey("enhance")).toBe("transcribe");
    expect(noteToPhaseKey("separate")).toBe("transcribe");
    expect(noteToPhaseKey("postprocessing")).toBe("transcribe");
    expect(noteToPhaseKey("finalizing")).toBe("transcribe");
  });

  it("unbekannte Noten → null (Fallback auf job.kind)", () => {
    expect(noteToPhaseKey("Re-Diarize läuft …")).toBeNull();
    expect(noteToPhaseKey("")).toBeNull();
    expect(noteToPhaseKey(null)).toBeNull();
    expect(noteToPhaseKey(undefined)).toBeNull();
  });
});
