/**
 * Change 011 — Fortschritt/ETA/Heartbeat: pure Helfer der RecordingCard.
 *
 * heartbeatState unterscheidet „Job lebt, kein messbarer Fortschritt"
 * (frischer Heartbeat) von „eingefroren/hängend" (alter Heartbeat) —
 * das ist die Grundlage für Puls-Animation und Stall-Warnung.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  activePhaseIndex,
  fmtEtaS,
  fmtSince,
  heartbeatState,
} from "./components/RecordingCard";

describe("heartbeatState (Change 011)", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-08-17T12:00:00Z"));
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  const iso = (s: number) => new Date(1_000 * s).toISOString();

  it("frischer Heartbeat (5 s alt) → fresh, nicht stalled", () => {
    const now = Date.now() / 1000;
    const st = heartbeatState({
      last_heartbeat_at: iso(now - 5),
      phase_started_at: iso(now - 120),
      status: "processing",
    });
    expect(st.fresh).toBe(true);
    expect(st.stalled).toBe(false);
    expect(st.sinceBeat).toBe(5);
    expect(st.sincePhase).toBe(120);
  });

  it("kein Heartbeat → weder fresh noch stalled (Anlauf)", () => {
    const st = heartbeatState({
      last_heartbeat_at: null,
      phase_started_at: null,
      status: "processing",
    });
    expect(st.fresh).toBe(false);
    expect(st.stalled).toBe(false);
    expect(st.sinceBeat).toBe(-1);
  });

  it("alter Heartbeat bei processing → stalled (Hänger erkannt)", () => {
    const now = Date.now() / 1000;
    const st = heartbeatState({
      last_heartbeat_at: iso(now - 60),
      phase_started_at: iso(now - 60),
      status: "processing",
    });
    expect(st.fresh).toBe(false);
    expect(st.stalled).toBe(true);
    expect(st.sinceBeat).toBe(60);
  });

  it("alter Heartbeat bei NICHT-processing → nicht stalled", () => {
    const now = Date.now() / 1000;
    const st = heartbeatState({
      last_heartbeat_at: iso(now - 999),
      phase_started_at: iso(now - 999),
      status: "queued",
    });
    expect(st.stalled).toBe(false);
  });

  it("naiver ISO-String ohne Z (Backend vor Change 081) wird als UTC gelesen → frischer Heartbeat bleibt fresh (Regression: 'seit 120m' in UTC+2)", () => {
    // Systemzeit ist 12:00:00Z; der naive String steht für 11:59:55 UTC
    // (5 s alt) — OHNE Z-Suffix. Vor Change 081 interpretierte JS ihn als
    // Lokalzeit (UTC+2 → 2h Skew → stalled „seit 120m").
    const naive = "2026-08-17T11:59:55";
    const withZ = "2026-08-17T11:59:55Z";
    const stNaive = heartbeatState({
      last_heartbeat_at: naive,
      phase_started_at: null,
      status: "processing",
    });
    const stZ = heartbeatState({
      last_heartbeat_at: withZ,
      phase_started_at: null,
      status: "processing",
    });
    expect(stNaive.sinceBeat).toBe(5);
    expect(stNaive.sinceBeat).toBe(stZ.sinceBeat);
    expect(stNaive.fresh).toBe(true);
    expect(stNaive.stalled).toBe(false);
    expect(fmtSince(stNaive.sinceBeat)).toBe("seit 5s");
  });
});

describe("fmtSince / fmtEtaS (Change 011)", () => {
  it("fmtSince: Sekunden und Minuten", () => {
    expect(fmtSince(3)).toBe("seit 3s");
    expect(fmtSince(59)).toBe("seit 59s");
    expect(fmtSince(60)).toBe("seit 1m 0s");
    expect(fmtSince(185)).toBe("seit 3m 5s");
  });

  it("fmtEtaS: kompakte Warte-ETA", () => {
    expect(fmtEtaS(null)).toBe("");
    expect(fmtEtaS(undefined)).toBe("");
    expect(fmtEtaS(0)).toBe("");
    expect(fmtEtaS(45)).toBe("~45s");
    expect(fmtEtaS(119)).toBe("~119s");
    expect(fmtEtaS(120)).toBe("~2m");
    expect(fmtEtaS(900)).toBe("~15m");
  });
});

describe("activePhaseIndex (Change 035 — Phasen-Chips)", () => {
  it("Noten bestimmen die Phase", () => {
    expect(activePhaseIndex({ progress_note: "preparing" })).toBe(0);
    expect(activePhaseIndex({ progress_note: "vad" })).toBe(0);
    expect(activePhaseIndex({ progress_note: "enhance" })).toBe(0);
    expect(activePhaseIndex({ progress_note: "asr" })).toBe(1);
    expect(activePhaseIndex({ progress_note: "diarization" })).toBe(2);
    expect(activePhaseIndex({ progress_note: "alignment" })).toBe(3);
    expect(activePhaseIndex({ progress_note: "alignment Gruppe 2/5" })).toBe(3);
    expect(activePhaseIndex({ progress_note: "postprocessing" })).toBe(4);
    expect(activePhaseIndex({ progress_note: "finalizing" })).toBe(4);
  });

  it("ohne Note: pct-Fallback (Streaming-ASR, Lücken)", () => {
    expect(activePhaseIndex({ progress_note: null, progress_pct: 1 })).toBe(0);
    expect(activePhaseIndex({ progress_note: null, progress_pct: 20 })).toBe(0);
    expect(activePhaseIndex({ progress_note: null, progress_pct: 50 })).toBe(1);
    expect(activePhaseIndex({ progress_note: null, progress_pct: 80 })).toBe(1);
    expect(activePhaseIndex({ progress_note: null, progress_pct: 94 })).toBe(1);
    expect(activePhaseIndex({ progress_note: null, progress_pct: 95 })).toBe(4);
    expect(activePhaseIndex({ progress_note: null, progress_pct: 99 })).toBe(4);
  });
});
