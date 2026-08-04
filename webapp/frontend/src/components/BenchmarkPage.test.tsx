import { describe, expect, test, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { AxesMatrix, BenchmarkCategory, PriceComparison, TestSetExplanation } from "./BenchmarkPage";
import type { BenchmarkCategory as Cat, BenchmarkMeta, BenchmarkSample, BenchmarkPricing } from "../benchmark";

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
    <BenchmarkCategory
      cat={CAT}
      samples={SAMPLES}
      open={open}
      onToggle={onToggle}
      showText
      admin={false}
      previewUrl={(id) => `/api/benchmark/preview/${id}`}
      audioUrl={(id) => `/api/benchmark/audio/${id}`}
    />,
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
      />,
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
