/**
 * Change 236 — die Listenseite überrennt den Server nicht mehr.
 *
 * Befund 30.09.2026 (KI-Box, Server-Protokoll): Ein Aufruf der Aufnahmenliste
 * mit 116 Aufnahmen erzeugte ~812 Abfragen in 24 Sekunden, weil JEDE Karte
 * sieben serverweite Auskünfte (Modell-Matrix, Backend-Fähigkeiten,
 * Modell-Status, Vorlagen, Format-Vorgaben, Zustellziele, LLM-Adressen) und
 * zusätzlich die Export-Vorlagen selbst holte. Die Box lastete aus (Last 16,
 * Netzwerk-Unterbrechungen 5 % → 17,5 %), der Tab war eine halbe Minute nur
 * mit Abfragen beschäftigt.
 *
 * Diese Prüfung zählt die Abfragen an der NETZWERK-GRENZE (`fetch`) — nicht an
 * einem Mock der API-Schicht. Damit hängt sie nicht daran, über welchen Pfad
 * eine Komponente die Auskunft holt, und sie misst genau das, was der Server
 * damals gespürt hat: die Zahl der Anfragen.
 *
 * Geprüft wird (a) acht Karten → jede Auskunft GENAU EINMAL, und (b) nach dem
 * Leeren des Geteiltenspeichers wird wieder geholt — die Ersparnis ist kein
 * ewiger Zwischenspeicher.
 */
import { beforeEach, describe, expect, test, vi } from "vitest";
import { cleanup, render, waitFor } from "@testing-library/react";
import { LocaleProvider } from "../useLocale";
import { RecordingCard } from "./RecordingCard";
import { forgetSharedConfig } from "../sharedConfig";
import type { Recording } from "../api";

vi.mock("../hooks", () => ({
  useDelete: () => ({ mutate: vi.fn(), isPending: false }),
  useRetranscribe: () => ({ mutate: vi.fn(), isPending: false }),
  useRealign: () => ({ mutate: vi.fn(), isPending: false }),
  useRediarize: () => ({ mutate: vi.fn(), isPending: false }),
  useCancelRecording: () => ({ mutate: vi.fn(), isPending: false }),
  useNearViewport: () => ({ ref: { current: null }, near: false }),
  useRecordingDetail: () => ({ data: undefined, isLoading: false, isFetching: false }),
  detailEnabled: (s: string | undefined) =>
    s === "done" || s === "processing" || s === "queued",
  shouldPollDetail: (s: string | undefined) => s === "processing" || s === "queued",
}));

vi.mock("@tanstack/react-query", () => ({
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
  useQuery: () => ({ data: [], isLoading: false, isError: false, error: null }),
}));

vi.mock("./Toasts", () => ({ useToast: () => ({ toast: vi.fn() }) }));

/* Schwere Kinder: für die Zählung der Anfragen nicht nötig. */
vi.mock("./WaveformPlayer", () => ({ WaveformPlayer: () => null }));
vi.mock("./SegmentList", () => ({ SegmentList: () => null }));
vi.mock("./SegmentSearch", () => ({ SegmentSearch: () => null }));
vi.mock("./FeatureToggles", () => ({
  FeatureToggles: () => null,
  diarSensToMinDurationOff: () => undefined,
}));
vi.mock("./VersionDiff", () => ({ VersionDiff: () => null }));

/** Antworten der serverweiten Auskünfte — Form wie im Betrieb. */
const ANTWORTEN: Record<string, unknown> = {
  "/api/models/matrix": [],
  "/api/backends": { backends: [], default: "", streaming_supported: false, streaming_by_backend: {}, native_punctuation: {} },
  "/api/models/status": {
    vad_available: true,
    diarize_available: true,
    diar_service: "",
    asr_device: "cpu",
    downloading: {},
    download_progress: {},
  },
  "/api/templates": [],
  "/api/targets": [],
  "/api/llm-endpoints": [],
  "/api/formatting/presets": { presets: [] },
  "/api/export-templates": [],
};

let anfragen: string[] = [];

function fetchStub() {
  return vi.fn(async (eingabe: RequestInfo | URL) => {
    const pfad = String(typeof eingabe === "string" ? eingabe : (eingabe as Request).url ?? eingabe);
    anfragen.push(pfad.split("?")[0]);
    const koerper = ANTWORTEN[pfad.split("?")[0]];
    if (koerper === undefined) {
      return new Response(JSON.stringify({ detail: "nicht erwartet" }), {
        status: 404,
        headers: { "Content-Type": "application/json" },
      });
    }
    return new Response(JSON.stringify(koerper), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  }) as unknown as typeof fetch;
}

function makeRec(i: number): Recording {
  return {
    id: String(i),
    uid: `r${i}`,
    original_name: `aufnahme-${i}.wav`,
    mime: "audio/wav",
    size_bytes: 1000,
    duration_s: 10,
    status: "done",
    text: "Hallo",
    error: null,
    processing_ms: null,
    created_at: "2026-08-01T00:00:00Z",
    language: "de",
    segments: null,
    segments_manual: false,
    audio_url: `/api/audio/r${i}`,
    audio_preview_url: null,
    download_url: `/api/download/r${i}`,
    backup_url: `/api/backup/r${i}`,
    batch_id: null,
    recorded_at: null,
    source: null,
    enable_vad: false,
    enable_diarize: false,
    enable_streaming: false,
    enable_noise_reduce: false,
    enable_enhance: "none",
    waveform_peaks: null,
    progress_pct: 0,
    access_level: "owner",
  };
}

function renderKarten(n: number) {
  return render(
    <LocaleProvider>
      {Array.from({ length: n }, (_, i) => (
        <RecordingCard key={i} recording={makeRec(i + 1)} isOidc compact defaultCollapsed />
      ))}
    </LocaleProvider>,
  );
}

function zaehle(pfad: string) {
  return anfragen.filter((p) => p === pfad).length;
}

beforeEach(() => {
  cleanup();
  forgetSharedConfig();
  anfragen = [];
  (globalThis as unknown as { fetch: typeof fetch }).fetch = fetchStub();
});

describe("Change 236 — serverweite Auskünfte werden geteilt", () => {
  test("acht Karten holen jede Auskunft genau einmal", async () => {
    renderKarten(8);

    await waitFor(() => expect(zaehle("/api/templates")).toBe(1));

    for (const pfad of Object.keys(ANTWORTEN)) {
      expect(zaehle(pfad), `${pfad} wurde mehrfach geholt`).toBe(1);
    }
    // Kein Streuschuss auf andere Pfade.
    expect(anzahlUnbekannt()).toBe(0);
  });

  test("die Zahl der Anfragen wächst nicht mit der Kartenzahl", async () => {
    renderKarten(20);
    await waitFor(() => expect(zaehle("/api/backends")).toBe(1));

    // Vorher: 20 Karten × 8 Auskünfte = 160 Anfragen. Jetzt: 8.
    expect(anfragen.length).toBe(8);
  });

  test("nach dem Leeren des Geteiltenspeichers wird wieder geholt", async () => {
    renderKarten(8);
    await waitFor(() => expect(zaehle("/api/templates")).toBe(1));

    cleanup();
    forgetSharedConfig();
    renderKarten(8);

    await waitFor(() => expect(zaehle("/api/templates")).toBe(2));
  });
});

function anzahlUnbekannt(): number {
  return anfragen.filter((p) => !(p in ANTWORTEN)).length;
}
