import { beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { LocaleProvider } from "../useLocale";
import { RecordingCard, resolveAudioUrl } from "./RecordingCard";
import type { Recording } from "../api";
import { updateRecordingTitle, toggleAnonLink } from "../api";
import { useRealign, useRecordingDetail } from "../hooks";

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
  useRealign: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useRediarize: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useCancelRecording: () => ({ mutate: vi.fn(), isPending: false }),
  useNearViewport: () => ({ ref: { current: null }, near: true }),
  useRecordingDetail: vi.fn(() => ({ data: undefined, isLoading: false, isFetching: false })),
}));

vi.mock("@tanstack/react-query", () => ({
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
  // Change 056: Annotationen-Query (und ["me"] in AnnotationThreads) —
  // leerer Daten-Stand; die Card rendert dann den Empty-State.
  useQuery: vi.fn(() => ({ data: [], isLoading: false, isError: false, error: null })),
}));

const toastMock = vi.hoisted(() => ({ toast: vi.fn() }));

vi.mock("./Toasts", () => ({
  useToast: () => ({ toast: toastMock.toast }),
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
  toastMock.toast.mockClear();
  vi.mocked(toggleAnonLink).mockReset();
  vi.mocked(toggleAnonLink).mockResolvedValue({
    share_token: "t123",
    retention_minutes: 60,
    expires_at: null,
  } as never);
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
    expect(updateRecordingTitle).toHaveBeenCalledWith(
      "r1", "Neuer Titel", expect.any(AbortSignal),
    );
  });

  test("hängender Save blockiert den Exit nicht (Fix 2026-08-18)", () => {
    // Request, der NIE zurückkommt — vorher blieb der Edit-Mode gefangen
    // (Lock-Guard verschluckte Klick/Enter/Blur), jetzt schließt er immer.
    vi.mocked(updateRecordingTitle).mockReturnValue(new Promise(() => {}));
    renderCard(makeRec());
    fireEvent.click(screen.getByLabelText("Edit title"));
    const input = screen.getByPlaceholderText("Title…");
    fireEvent.change(input, { target: { value: "Neuer Titel" } });
    fireEvent.keyDown(input, { key: "Enter", code: "Enter" }); // Save startet (hängt)
    fireEvent.keyDown(input, { key: "Enter", code: "Enter" }); // erneuter Exit-Versuch
    expect(screen.queryByPlaceholderText("Title…")).toBeNull();
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

describe("RecordingCard — Change 116 Aktions-Tabs (Re-Align/Re-Diarize)", () => {
  test("Aktions-Tab 'New word timestamps' aktiv bei done + Schreibzugriff", () => {
    renderCard(makeRec(), false); // expandiert → Aktionsleiste sichtbar
    const tab = screen.getByTestId("act-alg") as HTMLButtonElement;
    expect(tab).toBeTruthy();
    expect(tab.disabled).toBe(false);
  });

  test("Aktions-Tab 'New word timestamps' fehlt bei Read-Only-Share", () => {
    renderCard(makeRec({ access_level: "read" }), false);
    // Read-Only: keine Aktionsleiste (kein Schreibzugriff → nichts startbar).
    expect(screen.queryByTestId("act-alg")).toBeNull();
  });

  test("Start mit Aktion 'New word timestamps' startet die Re-Align-Mutation", async () => {
    const hooks = vi.hoisted(() => ({ realignMutate: vi.fn() }));
    hooks.realignMutate.mockImplementation((_id: string, opts: unknown) => {
      if (opts && typeof opts === "object" && "onSuccess" in opts) {
        (opts as { onSuccess?: () => void }).onSuccess?.();
      }
    });
    vi.mocked(useRealign).mockReturnValue({ mutate: hooks.realignMutate as never, isPending: false } as never);
    renderCard(makeRec(), false); // expandiert → Aktionsleiste sichtbar
    screen.getByTestId("act-alg").click();
    // Auf den Re-Render warten (Tab aktiv), sonst greift der Start-Klick
    // den alten Handler mit action="tr".
    await waitFor(() => expect(screen.getByTestId("act-alg").className).toContain("border-b-accent"));
    screen.getByText("Start").click();
    await waitFor(() => expect(hooks.realignMutate).toHaveBeenCalled());
  });

  test("Change 113/116: Music-Removal-Option 'Musik entfernen' im Options-Panel", async () => {
    renderCard(makeRec(), false);
    screen.getByText("Options").click(); // Options-Panel aufklappen
    await waitFor(() => {
      const select = document.querySelector('[data-opt="separate"] select') as HTMLSelectElement | null;
      expect(select).toBeTruthy();
      expect(Array.from(select!.options).map((o) => o.value)).toEqual([
        "none",
        "htdemucs",
        "mel-band-roformer",
      ]);
    });
  });

  test("Change 113/116: Re-Align sendet gewähltes separate_backend", async () => {
    const hooks113 = vi.hoisted(() => ({ realignMutate113: vi.fn() }));
    hooks113.realignMutate113.mockImplementation((_id: string, opts: unknown) => {
      if (opts && typeof opts === "object" && "onSuccess" in opts) {
        (opts as { onSuccess?: () => void }).onSuccess?.();
      }
    });
    vi.mocked(useRealign).mockReturnValue({ mutate: hooks113.realignMutate113 as never, isPending: false } as never);
    renderCard(makeRec(), false);
    screen.getByText("Options").click();
    await waitFor(() => {
      expect(document.querySelector('[data-opt="separate"] select')).toBeTruthy();
    });
    fireEvent.change(document.querySelector('[data-opt="separate"] select') as HTMLSelectElement, {
      target: { value: "htdemucs" },
    });
    screen.getByTestId("act-alg").click();
    await waitFor(() => expect(screen.getByTestId("act-alg").className).toContain("border-b-accent"));
    screen.getByText("Start").click();
    await waitFor(() => {
      expect(hooks113.realignMutate113).toHaveBeenCalledWith(
        expect.objectContaining({
          id: "r1",
          opts: { separate_backend: "htdemucs" },
        }),
        expect.anything(),
      );
    });
  });

  test("Change 101: alignment=skipped zeigt sichtbaren Hinweis (keine stille done-Lüge)", () => {
    renderCard(
      makeRec({
        status: "done",
        alignment: "skipped",
        error: "Re-Align ohne Effekt: Aligner nicht erreichbar",
      }),
      false,
    );
    const hint = screen.getByTestId("bg-align-skipped-r1");
    expect(hint).toBeTruthy();
    expect(hint.getAttribute("title")).toContain("Aligner nicht erreichbar");
  });

  test("Change 115: bg-align zeigt Live-Details (Gruppe + RTF statt statischem Text)", () => {
    renderCard(
      makeRec({
        status: "done",
        alignment: "running",
        progress_note: "alignment Gruppe 3/12 — aktiv seit 42s — CLI 45%",
        last_heartbeat_at: new Date(Date.now() - 42_000).toISOString(),
      }),
      false,
    );
    const hint = screen.getByTestId("bg-align-r1");
    expect(hint.textContent).toContain("Gruppe 3/12");
    expect(hint.textContent).toContain("CLI 45%");
    expect(hint.textContent).not.toContain("läuft im Hintergrund");
  });

  test("Change 115: bg-diar zeigt Heartbeat-Zeit (läuft seit)", () => {
    renderCard(
      makeRec({
        status: "done",
        diar_status: "running",
        last_heartbeat_at: new Date(Date.now() - 42_000).toISOString(),
      }),
      false,
    );
    const hint = screen.getByTestId("bg-diar-r1");
    expect(hint.textContent).toContain("42s"); // „läuft seit 42s" (sprachunabhängig)
  });
});

describe("RecordingCard — Change 058 Popover/Dropdown-Konsistenz", () => {
  test("Share-Dropdown schließt bei Klick außerhalb (mousedown)", () => {
    renderCard(makeRec(), false); // expandiert → Actions-Zeile sichtbar
    fireEvent.click(screen.getByRole("button", { name: "🔗 Teilen" }));
    expect(screen.getByText("Noch nicht geteilt.")).toBeTruthy();
    fireEvent.mouseDown(document.body);
    expect(screen.queryByText("Noch nicht geteilt.")).toBeNull();
  });

  test("Share-Dropdown schließt mit Escape", () => {
    renderCard(makeRec(), false);
    fireEvent.click(screen.getByRole("button", { name: "🔗 Teilen" }));
    expect(screen.getByText("Noch nicht geteilt.")).toBeTruthy();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByText("Noch nicht geteilt.")).toBeNull();
  });

  test("Anon-Link-Generierung kopiert automatisch in die Zwischenablage + Toast", async () => {
    const writeMock = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText: writeMock },
      configurable: true,
    });
    renderCard(makeRec(), false);
    fireEvent.click(screen.getByRole("button", { name: "🔗 Teilen" }));
    // Toggle-Button im Dropdown (aria-label "Anonymer Link" — der sichtbare
    // Text "Teilen" kollidiert mit dem Submit-Button der User-Share-Zeile)
    fireEvent.click(screen.getByRole("button", { name: "Anonymer Link" }));
    await waitFor(() =>
      expect(writeMock).toHaveBeenCalledWith(expect.stringContaining("/r/r1")),
    );
    expect(toastMock.toast).toHaveBeenCalledWith(
      "Anonymous link created and copied to clipboard",
      "ok",
    );
  });
});

describe("RecordingCard — Change 059 Lite-Shell/Nachladen", () => {
  beforeEach(() => {
    vi.mocked(useRecordingDetail).mockReset();
    vi.mocked(useRecordingDetail).mockReturnValue({
      data: undefined,
      isLoading: false,
      isFetching: false,
    } as never);
  });

  test("aufgeklappte Karte lädt den Detail-Datensatz und zeigt Loading-Hinweis", () => {
    vi.mocked(useRecordingDetail).mockReturnValue({
      data: undefined,
      isLoading: true,
      isFetching: true,
    } as never);
    renderCard(makeRec(), false); // expandiert
    expect(useRecordingDetail).toHaveBeenCalledWith("r1", true);
    expect(screen.getByText(/Loading transcript/)).toBeTruthy();
  });

  test("kollabierte Karte lädt kein Detail (enabled=false)", () => {
    renderCard(makeRec(), true); // kollabiert
    expect(useRecordingDetail).toHaveBeenCalledWith("r1", false);
    expect(screen.queryByText(/Loading transcript/)).toBeNull();
  });

  test("geladene Detail-Transkription ersetzt den Listen-Stand", () => {
    const full = makeRec({ text: "Aus dem Detail" });
    vi.mocked(useRecordingDetail).mockReturnValue({
      data: full,
      isLoading: false,
      isFetching: false,
    } as never);
    renderCard(makeRec({ text: "Aus der Liste" }), false);
    expect(screen.getByText("Aus dem Detail")).toBeTruthy();
    expect(screen.queryByText("Aus der Liste")).toBeNull();
  });
});
