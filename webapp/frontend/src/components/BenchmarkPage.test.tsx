import { describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { LocaleProvider } from "../useLocale";
import { AxesMatrix, BenchmarkCategory, BenchmarkPageContent, CategoryQualityChart, ModelFilterChips, PriceComparison, TestSetExplanation, VadResultsTable } from "./BenchmarkPage";
import type { BenchmarkCategory as Cat, BenchmarkMeta, BenchmarkSample, BenchmarkPricing, BenchmarkResults, BenchmarkSamplesResponse } from "../benchmark";

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
    // Change 039: Qualität ist Teil der Kategorie-Blöcke — Kategorie öffnen
    fireEvent.click(screen.getByRole("button", { name: /Akzente/ }));
    expect(screen.getByTestId("cat-bar-akzent-ps-pk-onnx")).toBeTruthy();
    // clean hat 0 Samples: weder als Kategorie-Box noch als Chart
    expect(screen.queryByText(/Hochdeutsch/)).toBeNull();
    // akzent-Samples-Sektion vorhanden (Kategorie-Header-Button mit Anzahl)
    expect(screen.getByRole("button", { name: /Akzente/ })).toBeTruthy();
  });

  test("Modell-Filter oben blendet Modell aus allen Graphen aus", async () => {
    renderPage();
    fireEvent.click(screen.getByRole("button", { name: /Akzente/ }));
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
    fireEvent.click(screen.getByRole("button", { name: /Akzente/ }));
    // Ausgangslage: alle sichtbar, „Alle" aktiv
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

// ── Change 062: VAD-Ergebnis-Tabelle ──────────────────────────────────────

describe("VadResultsTable (Change 062)", () => {
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

  test("zeigt Hinweis, wenn keine VAD-Ergebnisse", () => {
        render(<VadResultsTable vad={null} />);
    expect(screen.getByText(/Noch keine VAD-Ergebnisse/)).toBeTruthy();
  });
});
