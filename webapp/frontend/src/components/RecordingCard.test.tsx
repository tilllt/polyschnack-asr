import { beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { LocaleProvider } from "../useLocale";
import { RecordingCard, resolveAudioUrl } from "./RecordingCard";
import type { Recording } from "../api";
import { updateRecordingTitle } from "../api";

/* Change 014 Frontend: Titel-Inline-Edit, zweite Zeile (original_name),
 * Defekt-Badge. Karte wird kollabiert gerendert (defaultCollapsed) — der
 * Header (Titel/Stift/Badges) ist damit isoliert testbar, ohne Player. */

vi.mock("../api", async () => {
  const actual = await vi.importActual<typeof import("../api")>("../api");
  return {
    ...actual,
    fetchModelsMatrix: vi.fn().mockResolvedValue([]),
    fetchModelStatus: vi
      .fn()
      .mockResolvedValue({
        vad_available: true,
        diarize_available: true,
        diar_service: "",
        asr_device: "cpu",
        downloading: {},
        download_progress: {},
      }),
    fetchTemplates: vi.fn().mockResolvedValue([]),
    fetchTargets: vi.fn().mockResolvedValue([]),
    fetchLlmEndpoints: vi.fn().mockResolvedValue([]),
    fetchExportTemplates: vi.fn().mockResolvedValue([]),
    transcribeRange: vi.fn(),
    startTranscription: vi.fn(),
    fetchShares: vi.fn().mockResolvedValue([]),
    createShare: vi.fn(),
    deleteShare: vi.fn(),
    fetchVersions: vi.fn().mockResolvedValue([]),
    fetchVersionDiff: vi.fn(),
    restoreVersion: vi.fn(),
    toggleAnonLink: vi.fn(),
    replaceSegments: vi.fn(),
    updateRecordingTitle: vi.fn().mockResolvedValue({ uid: "r1", title: "Neuer Titel", original_name: "aufnahme.wav" }),
  };
});

vi.mock("../hooks", () => ({
  useDelete: () => ({ mutate: vi.fn(), isPending: false }),
  useRetranscribe: () => ({ mutate: vi.fn(), isPending: false }),
  useCancelRecording: () => ({ mutate: vi.fn(), isPending: false }),
  useNearViewport: () => ({ ref: { current: null }, near: true }),
}));

vi.mock("@tanstack/react-query", () => ({
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
}));

vi.mock("./Toasts", () => ({
  useToast: () => ({ toast: vi.fn() }),
}));

// Schwere Komponenten, die bei kollabierter Karte nicht gerendert werden:
// WaveformPlayer fängt die Props für URL-Tests ab (audioUrl-Fallback).
vi.mock("./WaveformPlayer", () => ({
  WaveformPlayer: (props: { audioUrl?: string; onLoadError?: () => void }) => {
    (window as unknown as Record<string, unknown>).__wsProps = props;
    return null;
  },
}));
vi.mock("./SegmentList", () => ({ SegmentList: () => null }));
vi.mock("./SegmentSearch", () => ({ SegmentSearch: () => null }));
vi.mock("./FeatureToggles", () => ({
  FeatureToggles: () => null,
  diarSensToMinDurationOff: () => undefined,
}));
vi.mock("./VersionDiff", () => ({ VersionDiff: () => null }));

function makeRec(over: Partial<Recording> = {}): Recording {
  return {
    id: "1",
    uid: "r1",
    original_name: "aufnahme.wav",
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
    audio_url: "/api/audio/r1",
    audio_preview_url: null,
    download_url: "/api/download/r1",
    backup_url: "/api/backup/r1",
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
    ...over,
  };
}

function renderCard(rec: Recording, collapsed = true) {
  return render(
    <LocaleProvider>
      <RecordingCard recording={rec} compact defaultCollapsed={collapsed} />
    </LocaleProvider>,
  );
}

beforeEach(() => {
  vi.mocked(updateRecordingTitle).mockClear();
});

describe("RecordingCard — Change 014 Titel", () => {
  test("Stift (Edit) nur für Owner/Full", () => {
    renderCard(makeRec());
    expect(screen.getByLabelText("Edit title")).toBeTruthy();
  });

  test("kein Stift für Read-Only-Share", () => {
    renderCard(makeRec({ access_level: "read" }));
    expect(screen.queryByLabelText("Edit title")).toBeNull();
  });

  test("Klick auf Stift öffnet Input, Enter speichert", () => {
    renderCard(makeRec());
    fireEvent.click(screen.getByLabelText("Edit title"));
    const input = screen.getByPlaceholderText("Title…");
    fireEvent.change(input, { target: { value: "Neuer Titel" } });
    fireEvent.keyDown(input, { key: "Enter", code: "Enter" });
    expect(updateRecordingTitle).toHaveBeenCalledWith("r1", "Neuer Titel");
  });

  test("unveränderter Draft speichert nicht", () => {
    renderCard(makeRec({ title: "aufnahme.wav" }));
    fireEvent.click(screen.getByLabelText("Edit title"));
    const input = screen.getByPlaceholderText("Title…");
    fireEvent.change(input, { target: { value: "aufnahme.wav" } });
    fireEvent.keyDown(input, { key: "Enter", code: "Enter" });
    expect(updateRecordingTitle).not.toHaveBeenCalled();
  });

  test("Titel statt original_name als Hauptzeile", () => {
    renderCard(makeRec({ title: "Meeting Q3" }));
    expect(screen.getByText("Meeting Q3")).toBeTruthy();
  });

  test("zweite kleine Zeile mit original_name bei abweichendem Titel", () => {
    renderCard(makeRec({ title: "Meeting Q3" }));
    expect(screen.getByText("aufnahme.wav")).toBeTruthy();
    expect(screen.getByTitle(/Original file/)).toBeTruthy();
  });

  test("keine zweite Zeile, wenn Titel == original_name", () => {
    renderCard(makeRec({ title: "aufnahme.wav" }));
    // Nur der Titel-Span trägt den Text — keine zweite Datei-Zeile.
    expect(screen.getAllByText("aufnahme.wav")).toHaveLength(1);
  });
});

describe("RecordingCard — resolveAudioUrl (Fix 2026-08-18)", () => {
  test("nutzt deterministische Preview-URL, wenn audio_preview_url fehlt", () => {
    expect(resolveAudioUrl({ audio_preview_url: null, audio_url: "/api/audio/r1", uid: "r1" }, false))
      .toBe("/api/recordings/r1/audio/preview");
  });

  test("nutzt audio_preview_url, wenn die Preview existiert", () => {
    expect(resolveAudioUrl({ audio_preview_url: "/api/recordings/r1/audio/preview", audio_url: "/api/audio/r1", uid: "r1" }, false))
      .toBe("/api/recordings/r1/audio/preview");
  });

  test("Fallback auf die volle Datei nach previewFailed (einmalig)", () => {
    expect(resolveAudioUrl({ audio_preview_url: null, audio_url: "/api/audio/r1", uid: "r1" }, true))
      .toBe("/api/audio/r1");
  });
});

describe("RecordingCard — Change 014 Defekt-Badge", () => {
  test("Badge bei failed + fehlender Audio-Datei", () => {
    renderCard(
      makeRec({
        status: "failed",
        error: "Audio-Datei fehlt oder ist beschädigt (Datei fehlt)",
      }),
    );
    expect(screen.getByText("Broken")).toBeTruthy();
  });

  test("kein Badge bei failed mit anderem Fehler", () => {
    renderCard(makeRec({ status: "failed", error: "Backend nicht erreichbar" }));
    expect(screen.queryByText("Broken")).toBeNull();
  });

  test("kein Badge bei done", () => {
    renderCard(makeRec());
    expect(screen.queryByText("Broken")).toBeNull();
  });
});
