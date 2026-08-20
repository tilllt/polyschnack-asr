import { describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { LocaleProvider } from "../useLocale";
import { AxesMatrix, BenchmarkCategory, BenchmarkPageContent, CategoryQualityChart, ModelFilterChips, PriceComparison, TestSetExplanation } from "./BenchmarkPage";
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
  test("Balken sortiert nach WER aufsteigend, beste Modell oben, mit %-Wert und n", () => {
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
    expect(text[0]).toContain("10.0%");
    expect(text[1]).toContain("30.0%");
    expect(text[0]).toContain("(3)");
    // Change 040: Balken-Grafik — Label macht Kategorie-Zuordnung klar
    expect(screen.getByText(/Kategorie · Akzente/)).toBeTruthy();
    // Balken-Füllung hat Breite und WER-Farbe (grafische Repräsentation)
    const fill = bars[0].querySelector("div[style]");
    expect(fill).toBeTruthy();
    expect(fill?.getAttribute("style")).toContain("width:");
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
