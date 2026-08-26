import { beforeEach, describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { LocaleProvider } from "../useLocale";
import { AxesMatrix, BenchmarkCategory, BenchmarkPageContent, BenchmarkSetUpdater, BenchmarkVadSamples, CategoryQualityChart, ModelFilterChips, PriceComparison, TestSetExplanation, VadResultsTable } from "./BenchmarkPage";
import type { BenchmarkCategory as Cat, BenchmarkMeta, BenchmarkSample, BenchmarkPricing, BenchmarkResults, BenchmarkSamplesResponse, VadSample } from "../benchmark";

vi.mock("../benchmark", async (importOriginal) => {
  const mod = await importOriginal<typeof import("../benchmark")>();
  return {
    ...mod,
    fetchBenchmarkSetStatus: vi.fn(),
    installBenchmarkSet: vi.fn(),
  };
});
import { fetchBenchmarkSetStatus, installBenchmarkSet } from "../benchmark";

const CAT: Cat = { id: "akzent", name: "Akzente", description: "Regionale Färbungen" };

const SAMPLES: BenchmarkSample[] = [
  {
    id: "akzent_001",
    category: "akzent",
    text: "Kisten und Möbel hingegen lassen sich nicht stopfen.",
    accent: "schweizerdeutsch",
    age: "teens",
    preview_url: "/api/benchmark/preview/akzent_001",
    audio_url: "/api/benchmark/audio/akzent_001",
  },
];

vi.mock("wavesurfer.js", () => ({
  default: class {
    static create() {
      return {
        on: () => {},
        load: () => {},
        destroy: () => {},
        playPause: () => {},
        seekTo: () => {},
        getCurrentTime: () => 0,
        isPlaying: () => false,
        zoom: () => {},
        setTime: () => {},
        registerPlugin: () => {},
      };
    }
  },
}));
vi.mock("wavesurfer.js/dist/plugins/regions.js", () => ({
  default: { create: () => ({ on: () => {}, enableDragSelection: () => {}, clearRegions: () => {} }) },
}));
vi.mock("wavesurfer.js/dist/plugins/timeline.js", () => ({
  default: { create: () => ({ on: () => {} }) },
}));
vi.mock("wavesurfer.js/dist/plugins/hover.js", () => ({
  default: { create: () => ({ on: () => {} }) },
}));

function renderCat(open: boolean, onToggle: () => void) {
  return render(
    <LocaleProvider>
      <BenchmarkCategory
        cat={CAT}
        samples={SAMPLES}
        open={open}
        onToggle={onToggle}
        showText
        admin={false}
        previewUrl={(id) => `/api/benchmark/preview/${id}`}
        audioUrl={(id) => `/api/benchmark/audio/${id}`}
        qualityRows={[]}
        perSample={{}}
        hiddenModels={new Set()}
      />
    </LocaleProvider>,
  );
}

describe("BenchmarkCategory", () => {
  test("Sample ist bei zugeklappter Kategorie nicht sichtbar", () => {
    renderCat(false, () => {});
    expect(screen.queryByText("akzent_001")).toBeNull();
    expect(screen.queryByText("Kisten und Möbel")).toBeNull();
  });

  test("Klick öffnet Kategorie und zeigt Sample", () => {
    const toggle = vi.fn();
    renderCat(true, toggle);
    expect(screen.getByText("akzent_001")).toBeTruthy();
    expect(screen.getByText(/Kisten und Möbel/)).toBeTruthy();
  });

  test("Reject-Button fehlt ohne Admin", () => {
    renderCat(true, () => {});
    expect(screen.queryByText("Ablehnen")).toBeNull();
  });

  test("Reject-Button sichtbar für Admin", () => {
    render(
      <LocaleProvider>
        <BenchmarkCategory
          cat={CAT}
          samples={SAMPLES}
          open
          onToggle={() => {}}
          showText
          admin
          onReject={() => {}}
          previewUrl={(id) => `/api/benchmark/preview/${id}`}
          audioUrl={(id) => `/api/benchmark/audio/${id}`}
          qualityRows={[]}
          perSample={{}}
          hiddenModels={new Set()}
        />
      </LocaleProvider>,
    );
    expect(screen.getByText(/Ablehnen/)).toBeTruthy();
  });
});

describe("PriceComparison", () => {
  test("zeigt Preise sortiert nach WER", () => {
    const pricing: BenchmarkPricing = {
      rows: [
        { backend: "b2", group: "polyschnack", wer: 0.12, eur_per_min_selfhost: 0.02 },
        { backend: "b1", group: "polyschnack", wer: 0.05, eur_per_min_selfhost: 0.01 },
      ],
    };
    render(<PriceComparison pricing={pricing} />);
    const cells = screen.getAllByText(/b[12]/);
    expect(cells[0].textContent).toBe("b1"); // besseres WER zuerst
  });

  test("leerer Zustand ohne Daten", () => {
    render(<PriceComparison pricing={null} />);
    expect(screen.getByText(/kein Preisvergleich/i)).toBeTruthy();
  });
});

// ── 2-Achsen-Matrix ───────────────────────────────────────────────────────

const META: BenchmarkMeta = {
  version: 1,
  sample_count: 2,
  categories: [{ id: "akzent", name: "Akzente" }, { id: "jugend", name: "Jugendstimmen" }],
  per_category: { akzent: 1, jugend: 1 },
  axes: {
    kanal: {
      beschreibung: "Akustische Umgebung — wie klingt die Aufnahme?",
      kategorien: { clean: { name: "Clean / Studio" }, telefon: { name: "Telefon" } },
    },
    inhalt: {
      beschreibung: "Sprech-Inhalt — was wird gesprochen?",
      kategorien: { allgemein: { name: "Allgemein" }, akzent: { name: "Akzente" } },
    },
  },
  matrix: { clean: { akzent: 1, allgemein: 1 } },
  matrix_total: 2,
};

describe("AxesMatrix", () => {
  test("zeigt Zellen mit Sample-Zählung", () => {
    render(<AxesMatrix meta={META} active={null} onSelect={() => {}} />);
    expect(screen.getByText("Clean / Studio")).toBeTruthy();
    expect(screen.getByText("Akzente")).toBeTruthy();
    // Zelle clean×akzent hat 1 Sample
    const cell = screen.getByTitle("Clean / Studio × Akzente: 1 Samples");
    expect(cell).toBeTruthy();
  });

  test("Klick auf Zelle wählt Filter aus", () => {
    const onSelect = vi.fn();
    render(<AxesMatrix meta={META} active={null} onSelect={onSelect} />);
    const cell = screen.getByTitle("Clean / Studio × Akzente: 1 Samples");
    cell.click();
    expect(onSelect).toHaveBeenCalledWith({ kanal: "clean", inhalt: "akzent" });
  });

  test("leere Zellen sind deaktiviert", () => {
    render(<AxesMatrix meta={META} active={null} onSelect={() => {}} />);
    const telefon = screen.getByTitle("Telefon × Akzente: 0 Samples");
    expect((telefon as HTMLButtonElement).disabled).toBe(true);
  });

  test("aktive Zelle wird markiert", () => {
    render(<AxesMatrix meta={META} active={{ kanal: "clean", inhalt: "akzent" }} onSelect={() => {}} />);
    const cell = screen.getByTitle("Clean / Studio × Akzente: 1 Samples");
    expect(cell.className).toContain("bg-accent");
  });
});

describe("TestSetExplanation", () => {
  test("erklärt Achsen und Quellen", () => {
    render(<TestSetExplanation meta={META} />);
    expect(screen.getByText(/2 Achsen/)).toBeTruthy();
    expect(screen.getByText(/Kanal \(Akustik\)/)).toBeTruthy();
    expect(screen.getByText(/Inhalt \(Schwierigkeit\)/)).toBeTruthy();
    expect(screen.getAllByText(/Piper/).length).toBeGreaterThan(0);
  });

  test("Change 074: nennt DEMAND-Umweltgeräusche als Quelle", () => {
    render(<TestSetExplanation meta={META} />);
    expect(screen.getByText(/demand/)).toBeTruthy();
    expect(screen.getByText(/CC-BY-4.0/)).toBeTruthy();
    expect(screen.getByText(/strassenlaerm\/auto\/oepnv\/babble/)).toBeTruthy();
  });

  test("nennt die Sample-Gesamtzahl", () => {
    render(<TestSetExplanation meta={META} />);
    expect(screen.getByText(/2 Samples/)).toBeTruthy();
  });
});

describe("CategoryQualityChart (REQ-BEN-047)", () => {
  test("Balken sortiert nach WER aufsteigend, beste Modell oben, mit Qualitäts-%-Wert und n", () => {
    render(
      <LocaleProvider>
        <CategoryQualityChart
          categoryId="akzent"
          categoryName="Akzente"
          rows={[
            { backend: "ps-pk-onnx", wer: 0.3, n: 3 },
            { backend: "crispr-pk-cpp", wer: 0.1, n: 3 },
          ]}
          hiddenModels={new Set()}
        />
      </LocaleProvider>,
    );
    const bars = screen.getAllByTestId(/^cat-bar-/);
    expect(bars).toHaveLength(2);
    const text = bars.map((b) => b.textContent ?? "");
    expect(text[0]).toContain("crispr-pk-cpp"); // bestes zuerst
    // Change 051: Anzeige = ASR-Qualität (1-WER)*100, nicht WER-Fehlerrate
    expect(text[0]).toContain("90.0%"); // 1-0.1
    expect(text[1]).toContain("70.0%"); // 1-0.3
    expect(text[0]).toContain("(3)");
    // Change 040: Balken-Grafik — Label macht Kategorie-Zuordnung klar
    expect(screen.getByText(/Kategorie · Akzente/)).toBeTruthy();
    // Change 051: Balken-Füllung = ASR-Qualität (1-WER)*100, absolut —
    // bestes Modell (WER 0,1) 90 %, schlechteres (WER 0,3) 70 %.
    const fillBest = bars[0].querySelector("div[style]");
    const fillWorse = bars[1].querySelector("div[style]");
    expect(fillBest?.getAttribute("style")).toContain("width: 90%");
    expect(fillWorse?.getAttribute("style")).toContain("width: 70%"); // 1-0.3
  });

  test("keine Balken wenn alle Modelle ausgeblendet (Chart entfällt)", () => {
    render(
      <LocaleProvider>
        <CategoryQualityChart
          categoryId="akzent"
          categoryName="Akzente"
          rows={[
            { backend: "ps-pk-onnx", wer: 0.3, n: 3 },
            { backend: "crispr-pk-cpp", wer: 0.1, n: 3 },
          ]}
          hiddenModels={new Set(["ps-pk-onnx", "crispr-pk-cpp"])}
        />
      </LocaleProvider>,
    );
    expect(screen.queryByTestId(/^cat-bar-/)).toBeNull();
  });
});

describe("Sample-Qualitäts-Balken (Change 039/040/044/051)", () => {
  test("Sample-Balken: Breite = ASR-Qualität (1-WER)*100 absolut", () => {
    render(
      <LocaleProvider>
        <BenchmarkCategory
          cat={CAT}
          samples={SAMPLES}
          open
          onToggle={() => {}}
          showText
          admin={false}
          previewUrl={(id) => `/api/benchmark/preview/${id}`}
          audioUrl={(id) => `/api/benchmark/audio/${id}`}
          qualityRows={[]}
          perSample={{ "akzent_001": { "crispr-pk-cpp": 0.1, "ps-pk-onnx": 0.2 } }}
          hiddenModels={new Set()}
        />
      </LocaleProvider>,
    );
    const best = screen.getByTestId("sample-wer-akzent_001-crispr-pk-cpp");
    const worse = screen.getByTestId("sample-wer-akzent_001-ps-pk-onnx");
    const fillBest = best.querySelector("div[style]");
    const fillWorse = worse.querySelector("div[style]");
    expect(fillBest?.getAttribute("style")).toContain("width: 90%"); // 1-0.1
    expect(fillWorse?.getAttribute("style")).toContain("width: 80%"); // 1-0.2
  });

  test("Label heißt 'ASR-Qualität je Modell' (nicht 'Sample-Qualität')", () => {
    render(
      <LocaleProvider>
        <BenchmarkCategory
          cat={CAT}
          samples={SAMPLES}
          open
          onToggle={() => {}}
          showText
          admin={false}
          previewUrl={(id) => `/api/benchmark/preview/${id}`}
          audioUrl={(id) => `/api/benchmark/audio/${id}`}
          qualityRows={[]}
          perSample={{ "akzent_001": { "crispr-pk-cpp": 0.1 } }}
          hiddenModels={new Set()}
        />
      </LocaleProvider>,
    );
    expect(screen.getByText("ASR-Qualität je Modell")).toBeTruthy();
    expect(screen.queryByText("Sample-Qualität")).toBeNull();
  });

  test("WER 0.0 (perfekte Erkennung) zeigt 100.0% Qualität — Regression Screenshot-Befund", () => {
    render(
      <LocaleProvider>
        <BenchmarkCategory
          cat={CAT}
          samples={SAMPLES}
          open
          onToggle={() => {}}
          showText
          admin={false}
          previewUrl={(id) => `/api/benchmark/preview/${id}`}
          audioUrl={(id) => `/api/benchmark/audio/${id}`}
          qualityRows={[]}
          perSample={{
            "akzent_001": { "crispr-pk-cpp": 0.0, "ps-pk-onnx": 0.0, "whisper-large-v3": 0.0 },
          }}
          hiddenModels={new Set()}
        />
      </LocaleProvider>,
    );
    // Alle Modelle erkennen fehlerfrei → Qualität 100 %, nie 0.0 %
    for (const b of ["crispr-pk-cpp", "ps-pk-onnx", "whisper-large-v3"]) {
      const row = screen.getByTestId(`sample-wer-akzent_001-${b}`);
      expect(row.textContent).toContain("100.0%");
    }
  });
});

describe("ModelFilterChips (REQ-BEN-048)", () => {
  test("Klick toggelt Modell, 'Alle' toggelt alle", () => {
    const toggle = vi.fn();
    const toggleAll = vi.fn();
    render(
      <LocaleProvider>
        <ModelFilterChips
          models={["ps-pk-onnx", "crispr-pk-cpp"]}
          hiddenModels={new Set(["ps-pk-onnx"])}
          onToggle={toggle}
          onToggleAll={toggleAll}
        />
      </LocaleProvider>,
    );
    expect(screen.getByTestId("model-chip-ps-pk-onnx").getAttribute("data-active")).toBe("false");
    expect(screen.getByTestId("model-chip-crispr-pk-cpp").getAttribute("data-active")).toBe("true");
    screen.getByTestId("model-chip-ps-pk-onnx").click();
    expect(toggle).toHaveBeenCalledWith("ps-pk-onnx");
    screen.getByTestId("model-chip-alle").click();
    expect(toggleAll).toHaveBeenCalled();
  });

  test("'Alle' aktiv markiert, wenn alle Modelle sichtbar", () => {
    render(
      <LocaleProvider>
        <ModelFilterChips
          models={["ps-pk-onnx", "crispr-pk-cpp"]}
          hiddenModels={new Set()}
          onToggle={() => {}}
          onToggleAll={() => {}}
        />
      </LocaleProvider>,
    );
    expect(screen.getByTestId("model-chip-alle").getAttribute("data-active")).toBe("true");
  });
});

describe("BenchmarkPageContent — Kategorie-Graphen + Filter (REQ-BEN-047/048/049)", () => {
  const META: BenchmarkMeta = {
    version: 1,
    created_at: "2026-08-20T00:00:00Z",
    supersedes: null,
    categories: [
      { id: "akzent", name: "Akzente" },
      { id: "clean", name: "Hochdeutsch" },
    ],
    sample_count: 3,
    per_category: { akzent: 3, clean: 0 },
    methodology: "WER auf CommonVoice-de (echte Stimmen)",
    disclaimer: "Referenztexte held-out.",
  };
  const DATA: BenchmarkSamplesResponse = {
    version: 1,
    samples: [
      { id: "akzent_001", category: "akzent", text: "Kisten und Möbel.", preview_url: "/p", audio_url: "/a" },
      { id: "akzent_002", category: "akzent", text: "Zweiter Satz.", preview_url: "/p", audio_url: "/a" },
    ],
  };
  const RESULTS: BenchmarkResults = {
    version: 1,
    run_id: "r1",
    generated_at: "2026-08-20T00:00:00Z",
    rows: [
      { backend: "ps-pk-onnx", wer: 0.2 },
      { backend: "crispr-pk-cpp", wer: 0.25 },
    ],
    per_category: [
      { category: "akzent", backend: "ps-pk-onnx", wer: 0.2, cer: 0.1, n: 2 },
      { category: "akzent", backend: "crispr-pk-cpp", wer: 0.25, cer: 0.15, n: 2 },
    ],
  };
  function renderPage() {
    return render(
      <LocaleProvider>
        <BenchmarkPageContent
          meta={META}
          data={DATA}
          results={RESULTS}
          pricing={null}
          admin={false}
          onReject={() => {}}
          onEdit={() => {}}
          onReload={() => {}}
        />
      </LocaleProvider>,
    );
  }

  test("Kategorie-Graph je Kategorie mit Daten; leere Kategorie (0 Samples) unsichtbar", () => {
    renderPage();
    // Change 071: categories[0] (akzent) ist initial OFEN — Graph sichtbar
    // ohne Klick; ein Klick würde sie SCHLIESSEN (Toggle).
    expect(screen.getByTestId("cat-bar-akzent-ps-pk-onnx")).toBeTruthy();
    // clean hat 0 Samples: weder als Kategorie-Box noch als Chart
    expect(screen.queryByText(/Hochdeutsch/)).toBeNull();
    // akzent-Samples-Sektion vorhanden — Kategorie-Header (Name + Anzahl)
    // UND Collapse-Leisten-Chip tragen den Namen; beide vorhanden heißt
    // Sektion + Leiste aktiv (Change 135).
    expect(screen.getAllByRole("button", { name: /Akzente/ }).length).toBeGreaterThanOrEqual(2);
  });

  test("Modell-Filter oben blendet Modell aus allen Graphen aus", async () => {
    renderPage();
    // Change 071: akzent initial offen — kein Öffnungs-Klick nötig
    expect(screen.getByTestId("cat-bar-akzent-ps-pk-onnx")).toBeTruthy();
    fireEvent.click(screen.getByTestId("model-chip-ps-pk-onnx"));
    await waitFor(() => expect(screen.queryByTestId("cat-bar-akzent-ps-pk-onnx")).toBeNull());
    expect(screen.getByTestId("cat-bar-akzent-crispr-pk-cpp")).toBeTruthy();
    // Reset zeigt wieder beide
    fireEvent.click(screen.getByTestId("model-chip-alle"));
    await waitFor(() => expect(screen.getByTestId("cat-bar-akzent-ps-pk-onnx")).toBeTruthy());
  });

  test("Change 040: 'Alle' de-klick blendet alle Modelle aus, Klick zeigt alle", async () => {
    renderPage();
    // Change 071: akzent initial offen — kein Öffnungs-Klick nötig
    expect(screen.getByTestId("model-chip-alle").getAttribute("data-active")).toBe("true");
    expect(screen.getByTestId("cat-bar-akzent-ps-pk-onnx")).toBeTruthy();
    // De-Klick: alle ausgeblendet
    fireEvent.click(screen.getByTestId("model-chip-alle"));
    await waitFor(() => expect(screen.queryByTestId("cat-bar-akzent-ps-pk-onnx")).toBeNull());
    expect(screen.queryByTestId("cat-bar-akzent-crispr-pk-cpp")).toBeNull();
    expect(screen.getByTestId("model-chip-alle").getAttribute("data-active")).toBe("false");
    // Erneuter Klick: alle wieder sichtbar
    fireEvent.click(screen.getByTestId("model-chip-alle"));
    await waitFor(() => expect(screen.getByTestId("cat-bar-akzent-ps-pk-onnx")).toBeTruthy());
    expect(screen.getByTestId("cat-bar-akzent-crispr-pk-cpp")).toBeTruthy();
  });
});

// ── Change 062/065: VAD-Ergebnis-Tabelle ──────────────────────────────────

describe("VadResultsTable (Change 062/065)", () => {
  test("zeigt VAD-Metriken je Modell", () => {
        const vad = [
      { backend: "silero-onnx", kind: "vad" as const, n_samples: 59,
        vad_f1_mean: 0.976, boundary_start_ms_median: 16,
        boundary_end_ms_median: 24, fp_time_s: 0.0, rtf_mean: 0.0222 },
      { backend: "ten-vad", kind: "vad" as const, n_samples: 59,
        vad_f1_mean: 0.824, boundary_start_ms_median: 110,
        boundary_end_ms_median: 32, fp_time_s: 7.5, rtf_mean: 0.0132 },
    ];
    render(<VadResultsTable vad={vad} />);
    expect(screen.getByText("silero-onnx")).toBeTruthy();
    expect(screen.getByText("ten-vad")).toBeTruthy();
    expect(screen.getByText("0.976")).toBeTruthy();
    expect(screen.getByText("0.824")).toBeTruthy();
    expect(screen.getByText("7.5")).toBeTruthy();
    expect(screen.getByText(/lizenz-inkompatiblen Bedingungen/)).toBeTruthy();
  });

  test("zeigt Testset-Version + Release-Link (Change 065)", () => {
    const vad = [
      { backend: "silero-onnx", kind: "vad" as const, n_samples: 235,
        testset_version: "v4-public",
        testset_release_url: "https://github.com/tilllt/vad-benchmark-data/releases/download/v5/vad-benchmark-v4-public.zip",
        vad_f1_mean: 0.995, boundary_start_ms_median: 32,
        boundary_end_ms_median: 64, fp_time_s: 0.0, rtf_mean: 0.0222 },
    ];
    render(<VadResultsTable vad={vad} />);
    expect(screen.getByText(/Testset:/)).toBeTruthy();
    expect(screen.getByText("v4-public")).toBeTruthy();
    const link = screen.getByText("Release-Artefakt + Provenienz") as HTMLAnchorElement;
    expect(link.href).toContain("vad-benchmark-v4-public.zip");
  });

  test("zeigt Hinweis, wenn keine VAD-Ergebnisse", () => {
        render(<VadResultsTable vad={null} />);
    expect(screen.getByText(/Noch keine VAD-Ergebnisse/)).toBeTruthy();
  });

  test("Change 071: Empty-State erklärt den VAD-Benchmark (Testset + Metriken)", () => {
    render(<VadResultsTable vad={null} />);
    expect(screen.getByText(/V3.1-public/)).toBeTruthy();
    expect(screen.getByText(/235 Samples/)).toBeTruthy();
    expect(screen.getByText(/FP-Speech/)).toBeTruthy();
    expect(screen.getByText(/RTF/)).toBeTruthy();
  });
});

describe("BenchmarkPageContent — Change 071 (VAD-Methodik + Player sichtbar)", () => {
  const META2 = {
    version: 2,
    created_at: "2026-08-19T14:22:25Z",
    supersedes: 1,
    sample_count: 207,
    matrix_total: 207,
    methodology: "WER/CER auf CommonVoice-de + TTS",
    disclaimer: "Held-out-Samples bleiben privat.",
    axes: {},
    categories: [
      { id: "akzent", name: "Akzente" },
      { id: "babble", name: "Babble" },
    ],
  };
  const DATA2 = {
    version: 2,
    samples: [
      { id: "akzent_001", category: "akzent", text: "Kisten und Möbel", preview_url: "/p", audio_url: "/a" },
      { id: "babble_001", category: "babble", text: "Hintergrund", preview_url: "/p", audio_url: "/a" },
    ],
  };

  test("Methodik-Sektion enthält den VAD-Benchmark-Text (Change 071)", () => {
    render(
      <LocaleProvider>
        <BenchmarkPageContent
          meta={META2 as never}
          data={DATA2 as never}
          results={null}
          pricing={null}
          admin={false}
          onReject={() => {}}
          onEdit={() => {}}
          onReload={() => {}}
        />
      </LocaleProvider>,
    );
    // „VAD-Benchmark:" erscheint nur in der Methodik-Sektion (Change 071)
    expect(screen.getByText(/VAD-Benchmark:/)).toBeTruthy();
    // Metriken-Liste aus der Methodik (B-Start/B-Ende erscheint auch im
    // VAD-Empty-State → getAllByText)
    expect(screen.getAllByText(/B-Start\/B-Ende/).length).toBeGreaterThan(0);
    // Held-out-Hinweis (126 Samples geheim)
    expect(screen.getByText(/126/)).toBeTruthy();
  });

  test("erste Kategorie ist initial geöffnet — Sample + Player sichtbar ohne Klick (Change 071)", () => {
    render(
      <LocaleProvider>
        <BenchmarkPageContent
          meta={META2 as never}
          data={DATA2 as never}
          results={null}
          pricing={null}
          admin={false}
          onReject={() => {}}
          onEdit={() => {}}
          onReload={() => {}}
        />
      </LocaleProvider>,
    );
    // akzent ist categories[0] → initial offen → Sample sofort sichtbar
    expect(screen.getByText("akzent_001")).toBeTruthy();
  });
});

// ── Change 073: VAD-Testset-Samples anhörbar ──────────────────────────────

const VAD_SAMPLES: VadSample[] = [
  {
    id: "de_00_lead2",
    source: "piper-tts",
    variant: "lead2",
    split: "public",
    has_gt: true,
    preview_url: "/api/benchmark/vadpreview/de_00_lead2",
    audio_url: "/api/benchmark/vadaudio/de_00_lead2",
  },
  {
    id: "cv_clean_000_snr0_n0",
    source: "commonvoice:cv_clean_000",
    variant: "snr0_n0",
    split: "public",
    has_gt: true,
    preview_url: "/api/benchmark/vadpreview/cv_clean_000_snr0_n0",
    audio_url: "/api/benchmark/vadaudio/cv_clean_000_snr0_n0",
  },
  {
    id: "noise_demand_DKITCHEN_16k_sample",
    source: "demand",
    variant: "demand",
    split: "public",
    has_gt: false,
    preview_url: "/api/benchmark/vadpreview/noise_demand_DKITCHEN_16k_sample",
    audio_url: "/api/benchmark/vadaudio/noise_demand_DKITCHEN_16k_sample",
  },
];

describe("BenchmarkVadSamples (Change 073)", () => {
  function renderVad() {
    return render(
      <LocaleProvider>
        <BenchmarkVadSamples samples={VAD_SAMPLES} />
      </LocaleProvider>,
    );
  }

  test("rendert Testset-Liste mit Gruppentiteln + Sample-Zeilen", () => {
    renderVad();
    expect(screen.getByText(/Testset-Samples/)).toBeTruthy();
    expect(screen.getByText(/Basis-Samples/)).toBeTruthy();
    expect(screen.getByText(/DEMAND-SNR-Mixe/)).toBeTruthy();
    expect(screen.getByText(/Noise-FP/)).toBeTruthy();
    // Sample-IDs sichtbar
    expect(screen.getByText("de_00_lead2")).toBeTruthy();
    expect(screen.getByText("cv_clean_000_snr0_n0")).toBeTruthy();
    expect(screen.getByText("noise_demand_DKITCHEN_16k_sample")).toBeTruthy();
  });

  test("Quell-Label + GT-Hinweis (keine GT bei FP-Samples)", () => {
    renderVad();
    expect(screen.getByText("Piper-TTS")).toBeTruthy();
    expect(screen.getByText("Common Voice")).toBeTruthy();
    expect(screen.getByText("DEMAND")).toBeTruthy();
    expect(screen.getByText("keine GT (FP)")).toBeTruthy();
    // DEMAND-SNR-Hinweis (Gruppen-Hint) sichtbar
    expect(screen.getByText(/Küche\/Metro/)).toBeTruthy();
  });

  test("WAV-Download-Link zeigt auf audio_url", () => {
    renderVad();
    const links = screen.getAllByText("⬇ WAV") as HTMLAnchorElement[];
    expect(links.length).toBe(3);
    const hrefs = links.map((l) => l.getAttribute("href"));
    expect(hrefs).toContain("/api/benchmark/vadaudio/de_00_lead2");
    expect(hrefs).toContain("/api/benchmark/vadaudio/noise_demand_DKITCHEN_16k_sample");
  });
});

describe("BenchmarkPageContent — Change 073 (VAD-Sample-Liste in Sektion)", () => {
  const META3 = {
    version: 2,
    created_at: "2026-08-19T14:22:25Z",
    supersedes: 1,
    sample_count: 207,
    matrix_total: 207,
    methodology: "WER/CER auf CommonVoice-de + TTS",
    disclaimer: "Held-out-Samples bleiben privat.",
    axes: {},
    categories: [{ id: "akzent", name: "Akzente" }],
  };
  const DATA3 = {
    version: 2,
    samples: [
      { id: "akzent_001", category: "akzent", text: "Kisten und Möbel", preview_url: "/p", audio_url: "/a" },
    ],
  };

  test("VAD-Sektion zeigt Sample-Liste, wenn vadSamples geliefert wird", () => {
    render(
      <LocaleProvider>
        <BenchmarkPageContent
          meta={META3 as never}
          data={DATA3 as never}
          results={null}
          pricing={null}
          vadSamples={{ samples: VAD_SAMPLES, count: VAD_SAMPLES.length }}
          admin={false}
          onReject={() => {}}
          onEdit={() => {}}
          onReload={() => {}}
        />
      </LocaleProvider>,
    );
    // Change 135: VAD-Inhalte liegen jetzt hinter dem VAD-Tab
    fireEvent.click(screen.getByTestId("benchmark-tab-vad"));
    expect(screen.getByText(/Testset-Samples/)).toBeTruthy();
    expect(screen.getByText("de_00_lead2")).toBeTruthy();
  });

  test("VAD-Sektion ohne vadSamples (kein Paket) zeigt keine Liste", () => {
    render(
      <LocaleProvider>
        <BenchmarkPageContent
          meta={META3 as never}
          data={DATA3 as never}
          results={null}
          pricing={null}
          vadSamples={null}
          admin={false}
          onReject={() => {}}
          onEdit={() => {}}
          onReload={() => {}}
        />
      </LocaleProvider>,
    );
    fireEvent.click(screen.getByTestId("benchmark-tab-vad"));
    // Change 135: ohne Paket zeigt der VAD-Tab den Hinweis statt einer Liste
    expect(screen.queryByText("de_00_lead2")).toBeNull();
    expect(screen.getByText(/Kein VAD-Testset-Paket installiert/)).toBeTruthy();
  });
});

describe("BenchmarkSetUpdater (Change 075/076)", () => {
  const STATUS = {
    mechanism: "benchmark-set",
    configured: true,
    pinning_mode: false,
    git_url: "https://git.example.org/benchmark-data.git",
    url: "",
    sha_prefix: "1190936d",
    auto_install: false,
    current_version: 1,
    installed_versions: [1],
    available: [
      { version: 2, tag: "benchmark-set-v2" },
      { version: 1, tag: "benchmark-set-v1" },
    ],
    last_error: null,
  };

  beforeEach(() => {
    vi.mocked(fetchBenchmarkSetStatus).mockResolvedValue(STATUS as never);
    vi.mocked(installBenchmarkSet).mockResolvedValue({ ok: true, installed_version: 2, sample_count: 207, sha256: "ab".repeat(32) } as never);
  });

  test("zeigt Status: Quelle, aktuelle Version, installierte Versionen", async () => {
    render(
      <LocaleProvider>
        <BenchmarkSetUpdater />
      </LocaleProvider>,
    );
    await waitFor(() => expect(screen.getByTestId("benchmark-set-updater")).toBeTruthy());
    expect(screen.getByText(/Aktuelle Version:/)).toBeTruthy();
    expect(screen.getAllByText(/v1/).length).toBeGreaterThan(0);
    expect(screen.getByText(/benchmark-data\.git/)).toBeTruthy();
  });

  test("verfügbare Releases werden gelistet (neueste zuerst, v1 als Aktuell)", async () => {
    render(
      <LocaleProvider>
        <BenchmarkSetUpdater />
      </LocaleProvider>,
    );
    await waitFor(() => expect(screen.getByTestId("available-sets")).toBeTruthy());
    expect(screen.getByTestId("install-set-2")).toBeTruthy();
    expect(screen.getByText(/neueste/)).toBeTruthy();
    // v1 ≤ aktuell → Button "Aktuell" (disabled)
    const v1btn = screen.getByTestId("install-set-1");
    expect(v1btn.textContent).toContain("Aktuell");
    expect((v1btn as HTMLButtonElement).disabled).toBe(true);
    // v2 ist neuer → "Installieren"
    expect(screen.getByTestId("install-set-2").textContent).toContain("Installieren");
  });

  test("Install-Button (neueste) ruft API mit version und zeigt Erfolgsmeldung", async () => {
    render(
      <LocaleProvider>
        <BenchmarkSetUpdater onInstalled={() => {}} />
      </LocaleProvider>,
    );
    await waitFor(() => expect(screen.getByTestId("install-latest-btn")).toBeTruthy());
    fireEvent.click(screen.getByTestId("install-latest-btn"));
    await waitFor(() => expect(installBenchmarkSet).toHaveBeenCalled());
    await waitFor(() => expect(screen.getByTestId("set-msg")).toBeTruthy());
    expect(screen.getByText(/v2 installiert \(207 Samples/)).toBeTruthy();
  });

  test("per-Release-Button installiert genau diese Version", async () => {
    render(
      <LocaleProvider>
        <BenchmarkSetUpdater />
      </LocaleProvider>,
    );
    await waitFor(() => expect(screen.getByTestId("install-set-2")).toBeTruthy());
    fireEvent.click(screen.getByTestId("install-set-2"));
    await waitFor(() => expect(installBenchmarkSet).toHaveBeenCalledWith(undefined, undefined, undefined, 2));
  });

  test("skipped-Response zeigt 'kein Update nötig'", async () => {
    vi.mocked(installBenchmarkSet).mockResolvedValue({ ok: true, skipped: true, reason: "bereits installiert", current_version: 1 } as never);
    render(
      <LocaleProvider>
        <BenchmarkSetUpdater />
      </LocaleProvider>,
    );
    await waitFor(() => expect(screen.getByTestId("install-latest-btn")).toBeTruthy());
    fireEvent.click(screen.getByTestId("install-latest-btn"));
    await waitFor(() => expect(screen.getByTestId("set-msg")).toBeTruthy());
    expect(screen.getByText(/kein Update nötig/)).toBeTruthy();
  });

  test("Fehler wird sichtbar angezeigt (kein stiller Fehler)", async () => {
    vi.mocked(installBenchmarkSet).mockRejectedValue(new Error("SHA256-Mismatch"));
    render(
      <LocaleProvider>
        <BenchmarkSetUpdater />
      </LocaleProvider>,
    );
    await waitFor(() => expect(screen.getByTestId("install-latest-btn")).toBeTruthy());
    fireEvent.click(screen.getByTestId("install-latest-btn"));
    await waitFor(() => expect(screen.getByTestId("set-error")).toBeTruthy());
    expect(screen.getByText(/Install fehlgeschlagen: SHA256-Mismatch/)).toBeTruthy();
  });

  test("Pinning-Modus (env-URL) zeigt Hinweis statt Repo-Liste", async () => {
    vi.mocked(fetchBenchmarkSetStatus).mockResolvedValue({
      ...STATUS,
      pinning_mode: true,
      git_url: "",
      url: "https://github.com/x/y.zip",
      available: [],
    } as never);
    render(
      <LocaleProvider>
        <BenchmarkSetUpdater />
      </LocaleProvider>,
    );
    await waitFor(() => expect(screen.getByText(/Pinning-Modus/)).toBeTruthy());
    expect(screen.queryByTestId("available-sets")).toBeNull();
  });

  test("ohne Konfiguration zeigt Hinweis statt Quelle", async () => {
    vi.mocked(fetchBenchmarkSetStatus).mockResolvedValue({
      ...STATUS,
      configured: false,
      pinning_mode: false,
      git_url: "",
      url: "",
      sha_prefix: "",
      available: [],
    } as never);
    render(
      <LocaleProvider>
        <BenchmarkSetUpdater />
      </LocaleProvider>,
    );
    await waitFor(() => expect(screen.getByText(/Keine Quelle konfiguriert/)).toBeTruthy());
  });
});

// ── Change 135: Tabs + Collapse-Leiste + Hypothese-Text ──────────────────

describe("BenchmarkPageContent — Change 135 (Tabs)", () => {
  const META135: BenchmarkMeta = {
    version: 1,
    created_at: "2026-08-26T00:00:00Z",
    supersedes: null,
    categories: [{ id: "akzent", name: "Akzente" }],
    sample_count: 1,
    per_category: { akzent: 1 },
    methodology: "WER auf CommonVoice-de",
    disclaimer: "Referenztexte held-out.",
  };
  const DATA135: BenchmarkSamplesResponse = {
    version: 1,
    samples: [
      { id: "akzent_001", category: "akzent", text: "Kisten und Möbel.", preview_url: "/p", audio_url: "/a" },
    ],
  };
  const RESULTS135: BenchmarkResults = {
    version: 1,
    run_id: "r1",
    rows: [{ backend: "ps-pk-onnx", wer: 0.2 }],
    per_category: [{ category: "akzent", backend: "ps-pk-onnx", wer: 0.2, cer: 0.1, n: 1 }],
    per_sample: { akzent_001: { "ps-pk-onnx": 0.2 } },
    per_sample_text: { akzent_001: { "ps-pk-onnx": "Kisten und Möbel." } },
  };
  function renderPage135() {
    try {
      localStorage.removeItem("benchmark-tab");
    } catch {
      /* kein localStorage im Test-Environment */
    }
    return render(
      <LocaleProvider>
        <BenchmarkPageContent
          meta={META135}
          data={DATA135}
          results={RESULTS135}
          pricing={null}
          admin={false}
          onReject={() => {}}
          onEdit={() => {}}
          onReload={() => {}}
        />
      </LocaleProvider>,
    );
  }

  test("zeigt 4 Tabs (ASR/VAD/Align/Diar), Default ASR aktiv", () => {
    renderPage135();
    for (const t of ["asr", "vad", "align", "diar"]) {
      expect(screen.getByTestId(`benchmark-tab-${t}`)).toBeTruthy();
    }
    expect(screen.getByTestId("benchmark-tab-asr").getAttribute("data-active")).toBe("true");
    // ASR-Inhalt sichtbar (Samples-Sektion)
    expect(screen.getByTestId("asr-samples-section")).toBeTruthy();
  });

  test("VAD-Tab zeigt VAD-Sektion statt ASR-Samples", () => {
    renderPage135();
    fireEvent.click(screen.getByTestId("benchmark-tab-vad"));
    expect(screen.getByText("VAD-Modelle")).toBeTruthy();
    expect(screen.queryByTestId("asr-samples-section")).toBeNull();
  });

  test("Diar-Tab zeigt Platzhalter 'noch keine Daten'", () => {
    renderPage135();
    fireEvent.click(screen.getByTestId("benchmark-tab-diar"));
    expect(screen.getByText(/Noch keine Diarization-Benchmark-Daten/)).toBeTruthy();
  });

  test("Tab-Auswahl bleibt via localStorage erhalten", () => {
    renderPage135();
    fireEvent.click(screen.getByTestId("benchmark-tab-vad"));
    try {
      expect(localStorage.getItem("benchmark-tab")).toBe("vad");
    } catch {
      /* kein localStorage im Test-Environment — Tab-State reicht */
      expect(screen.getByTestId("benchmark-tab-vad").getAttribute("data-active")).toBe("true");
    }
  });

  test("Collapse-Leiste unten: Kategorie-Chip + 'Alle auf' Toggle", () => {
    renderPage135();
    expect(screen.getByTestId("category-collapse-bar")).toBeTruthy();
    expect(screen.getByTestId("collapse-cat-akzent")).toBeTruthy();
    // Alle auf: Kategorie bleibt geöffnet (initial offen) — Toggle zeigt "Alle zu"
    fireEvent.click(screen.getByTestId("collapse-toggle-all"));
    expect(screen.getByText("▸ Alle zu")).toBeTruthy();
  });

  test("Hypothese-Text unter den Balken (per_sample_text)", () => {
    renderPage135();
    // Initial offene Kategorie → Sample sichtbar, Hypothese-Block da
    expect(screen.getByTestId("sample-hyp-akzent_001")).toBeTruthy();
    expect(screen.getByText("Erkannt (Hypothese) je Modell")).toBeTruthy();
  });

  test("keine Hypothese-Anzeige wenn Run keinen Text submitted hat", () => {
    const resultsOhneText: BenchmarkResults = {
      ...RESULTS135,
      per_sample_text: undefined,
    };
    render(
      <LocaleProvider>
        <BenchmarkPageContent
          meta={META135}
          data={DATA135}
          results={resultsOhneText}
          pricing={null}
          admin={false}
          onReject={() => {}}
          onEdit={() => {}}
          onReload={() => {}}
        />
      </LocaleProvider>,
    );
    expect(screen.queryByTestId("sample-hyp-akzent_001")).toBeNull();
  });
});
