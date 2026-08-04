import { describe, expect, test, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { BenchmarkCategory, PriceComparison } from "./BenchmarkPage";
import type { BenchmarkCategory as Cat, BenchmarkSample, BenchmarkPricing } from "../benchmark";

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
