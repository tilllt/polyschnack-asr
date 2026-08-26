// ── Change 135: SuiteExplainer (Laien-Erklärung + Profi-Details) ──────────

import { describe, expect, test } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { SuiteExplainer } from "./SuiteExplainer";

describe("SuiteExplainer (Change 135)", () => {
  test("zeigt Laien-Erklärung + 'So liest du die Ergebnisse' für ASR", () => {
    render(<SuiteExplainer suite="asr" />);
    expect(screen.getByText("Was wird hier getestet?")).toBeTruthy();
    expect(screen.getByText(/Spracherkennungs-Modell/)).toBeTruthy();
    expect(screen.getByText(/So liest du die Ergebnisse/)).toBeTruthy();
    // Profi-Details initial zugeklappt
    expect(screen.queryByTestId("explainer-pro-asr")).toBeNull();
  });

  test("alle vier Suiten haben eigene Erklär-Texte", () => {
    for (const suite of ["asr", "vad", "align", "diar"] as const) {
      const { unmount } = render(<SuiteExplainer suite={suite} />);
      expect(screen.getByTestId(`suite-explainer-${suite}`)).toBeTruthy();
      expect(screen.getByText(/Was wird hier getestet\?/)).toBeTruthy();
      unmount();
    }
  });

  test("VAD-Erklärung nennt F1 und FP-Speech für Laien", () => {
    render(<SuiteExplainer suite="vad" />);
    expect(screen.getByText(/Voice Activity Detection/)).toBeTruthy();
    expect(screen.getByText(/fälschlich als Sprache/)).toBeTruthy();
  });

  test("Align-Erklärung erklärt Karaoke-Sync", () => {
    render(<SuiteExplainer suite="align" />);
    expect(screen.getByText(/Karaoke-Sync/)).toBeTruthy();
    expect(screen.getByText(/0-Dauer-Wörter/)).toBeTruthy();
  });

  test("Diar-Erklärung nennt 'Wer spricht wann' + geplante Metriken", () => {
    render(<SuiteExplainer suite="diar" />);
    expect(screen.getByText(/Wer spricht wann\?/)).toBeTruthy();
    // Profi-Details einblenden, um die geplanten Metriken zu prüfen
    fireEvent.click(screen.getByTestId("explainer-toggle-diar"));
    expect(screen.getByText(/Diarization Error Rate/)).toBeTruthy();
  });

  test("Profi-Details sind einblendbar (Toggle)", () => {
    render(<SuiteExplainer suite="asr" />);
    expect(screen.queryByTestId("explainer-pro-asr")).toBeNull();
    fireEvent.click(screen.getByTestId("explainer-toggle-asr"));
    expect(screen.getByTestId("explainer-pro-asr")).toBeTruthy();
    // Technische Inhalte sichtbar: WER, RTF, Modelle
    expect(screen.getByText(/Word Error Rate/)).toBeTruthy();
    expect(screen.getByText(/Real-Time Factor/)).toBeTruthy();
    // Erneuter Klick klappt zu
    fireEvent.click(screen.getByTestId("explainer-toggle-asr"));
    expect(screen.queryByTestId("explainer-pro-asr")).toBeNull();
  });

  test("Profi-Details erwähnen die tatsächlichen Modellnamen", () => {
    render(<SuiteExplainer suite="asr" />);
    fireEvent.click(screen.getByTestId("explainer-toggle-asr"));
    expect(screen.getByText(/ps-pk-onnx/)).toBeTruthy();
    expect(screen.getByText(/crispr-qwen3/)).toBeTruthy();
  });
});
