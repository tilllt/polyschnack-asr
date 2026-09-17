import { beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { LocaleProvider } from "../useLocale";
import { ToastProvider } from "./Toasts";
import { ExportDialog } from "./ExportDialog";
import type { Recording } from "../api";
import { AssExportError, fetchAssExport, fetchExportPresets, saveBlob } from "../api";

/* Change 193 Frontend: Export-Dialog für animierte ASS-Untertitel.
 *
 * Geprüft werden die Zusagen des Dialogs:
 * - Katalog vom Backend wird gezeigt, „Hervorhebung" ist vorbelegt.
 * - Nur Parameter, die die Vorlage benutzt (`used_params`) — keine
 *   wirkungslosen Regler.
 * - Der Download sendet die geänderten Werte und nur benutzte Parameter.
 * - Serverfehler (409 „keine Wortzeiten") und Warnungen sind SICHTBAR,
 *   nicht still verschluckt.
 * - Kein Render-Knopf, solange `render_available` false ist.
 */

vi.mock("../api", async () => {
  const actual = await vi.importActual<typeof import("../api")>("../api");
  return {
    ...actual,
    fetchExportPresets: vi.fn(),
    fetchAssExport: vi.fn(),
    saveBlob: vi.fn(),
  };
});

const CATALOG = {
  presets: [
    {
      name: "classic",
      title: "Klassisch",
      description: "Klassisch: ganzer Satz unten.",
      description_en: "Classic: whole sentence at the bottom.",
      parameters: { font_size: 48, text_color: "#FFFFFF", words_per_line: 6 },
      used_params: ["font_size", "text_color", "words_per_line"],
    },
    {
      name: "highlight",
      title: "Hervorhebung",
      description: "Hervorhebung: gesprochenes Wort farbig.",
      description_en: "Highlight: the spoken word in colour.",
      parameters: {
        font_size: 56,
        accent_color: "#FFD400",
        text_color: "#FFFFFF",
        words_per_line: 4,
        play_res_x: 1920,
      },
      used_params: ["font_size", "accent_color", "text_color", "words_per_line", "play_res_x"],
    },
  ],
  parameter_specs: {
    font_size: { type: "int", min: 12, max: 300 },
    words_per_line: { type: "int", min: 1, max: 12 },
    text_color: { type: "color" },
    accent_color: { type: "color" },
    dim_color: { type: "color" },
    play_res_x: { type: "int", min: 128, max: 7680 },
  },
  render_available: false,
};

const RECORDING = {
  id: "1",
  uid: "rec-1",
  original_name: "interview.mp3",
  title: "Interview",
  status: "done",
} as unknown as Recording;

function renderDialog() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const onClose = vi.fn();
  const utils = render(
    <QueryClientProvider client={client}>
      <LocaleProvider>
        <ToastProvider>
          <ExportDialog recording={RECORDING} onClose={onClose} />
        </ToastProvider>
      </LocaleProvider>
    </QueryClientProvider>,
  );
  return { onClose, ...utils };
}

beforeEach(() => {
  vi.mocked(fetchExportPresets).mockResolvedValue(CATALOG as never);
  vi.mocked(fetchAssExport).mockReset();
  vi.mocked(saveBlob).mockReset();
});

describe("ExportDialog", () => {
  test("zeigt alle Vorlagen und belegt Hervorhebung vor", async () => {
    renderDialog();
    expect(screen.getByText("Loading templates…")).toBeTruthy();

    const classic = await screen.findByTestId("preset-classic");
    const highlight = screen.getByTestId("preset-highlight");
    expect(classic).toBeTruthy();
    expect(highlight.getAttribute("aria-pressed")).toBe("true");
    expect(classic.getAttribute("aria-pressed")).toBe("false");
    // Beschreibung in der UI-Sprache (Standard ist Englisch).
    expect(screen.getByText(/the spoken word in colour/i)).toBeTruthy();
  });

  test("zeigt nur Parameter, die die Vorlage benutzt", async () => {
    renderDialog();
    // highlight benutzt accent_color → Regler da.
    expect(await screen.findByTestId("param-accent_color")).toBeTruthy();

    // classic benutzt es nicht → kein Regler, kein Fund im DOM.
    fireEvent.click(screen.getByTestId("preset-classic"));
    await waitFor(() => {
      expect(screen.queryByTestId("param-accent_color")).toBeNull();
    });
    expect(screen.getByTestId("param-font_size")).toBeTruthy();
    // dim_color steht in KEINER Vorlage → nirgends sichtbar.
    expect(screen.queryByTestId("param-dim_color")).toBeNull();
  });

  test("weitere Optionen sind eingeklappt und kommen auf Klick", async () => {
    renderDialog();
    await screen.findByTestId("preset-highlight");
    expect(screen.queryByTestId("param-play_res_x")).toBeNull();

    fireEvent.click(screen.getByTestId("export-advanced-toggle"));
    expect(await screen.findByTestId("param-play_res_x")).toBeTruthy();
  });

  test("sendet geänderte Werte und nur benutzte Parameter", async () => {
    vi.mocked(fetchAssExport).mockResolvedValue({
      blob: new Blob(["ass"]),
      filename: "interview.ass",
      preset: "classic",
      words: 12,
      lines: 3,
      timing: "real",
      warnings: [],
    });
    renderDialog();
    await screen.findByTestId("preset-highlight");

    fireEvent.click(screen.getByTestId("preset-classic"));
    const slider = (await screen.findByTestId("param-font_size")).querySelector(
      "input[type=range]",
    ) as HTMLInputElement;
    fireEvent.change(slider, { target: { value: "77" } });

    fireEvent.click(screen.getByTestId("ass-export-download"));

    await waitFor(() => expect(fetchAssExport).toHaveBeenCalledTimes(1));
    const [uid, preset, params] = vi.mocked(fetchAssExport).mock.calls[0];
    expect(uid).toBe("rec-1");
    expect(preset).toBe("classic");
    expect(params).toMatchObject({ font_size: 77, text_color: "#FFFFFF", words_per_line: 6 });
    // Nicht benutzte Parameter werden nicht mitgeschickt (kein Blindflug).
    expect(Object.keys(params)).not.toContain("accent_color");
    expect(Object.keys(params)).not.toContain("dim_color");

    await waitFor(() => expect(saveBlob).toHaveBeenCalled());
    expect(vi.mocked(saveBlob).mock.calls[0][1]).toBe("interview.ass");
  });

  test("macht einen Serverfehler sichtbar (409 keine Wortzeiten)", async () => {
    vi.mocked(fetchAssExport).mockRejectedValue(
      new AssExportError("no_word_timestamps", "", "no word timings"),
    );
    renderDialog();
    await screen.findByTestId("preset-highlight");

    fireEvent.click(screen.getByTestId("ass-export-download"));

    const box = await screen.findByTestId("ass-export-error");
    expect(box.textContent).toMatch(/word timestamps/i);
    expect(vi.mocked(saveBlob)).not.toHaveBeenCalled();
  });

  test("meldet unbekannte Fehlercodes ehrlich statt leer", async () => {
    vi.mocked(fetchAssExport).mockRejectedValue(
      new AssExportError("neuer_code", "Zusatzhinweis"),
    );
    renderDialog();
    await screen.findByTestId("preset-highlight");
    fireEvent.click(screen.getByTestId("ass-export-download"));

    const box = await screen.findByTestId("ass-export-error");
    expect(box.textContent).toContain("neuer_code");
    expect(box.textContent).toContain("Zusatzhinweis");
  });

  test("zeigt Warnungen aus dem Export (Wortzeiten mechanisch verteilt)", async () => {
    vi.mocked(fetchAssExport).mockResolvedValue({
      blob: new Blob(["ass"]),
      filename: "interview.ass",
      preset: "highlight",
      words: 40,
      lines: 9,
      timing: "mixed",
      warnings: ["uniform_timing"],
    });
    renderDialog();
    await screen.findByTestId("preset-highlight");

    fireEvent.click(screen.getByTestId("ass-export-download"));
    const warn = await screen.findByTestId("ass-export-warning");
    expect(warn.textContent).toMatch(/mechanically distributed/i);
  });

  test("nennt Wörter- und Zeilenzahl nach erfolgreichem Export", async () => {
    vi.mocked(fetchAssExport).mockResolvedValue({
      blob: new Blob(["ass"]),
      filename: "interview.ass",
      preset: "highlight",
      words: 40,
      lines: 9,
      timing: "real",
      warnings: [],
    });
    renderDialog();
    await screen.findByTestId("preset-highlight");
    fireEvent.click(screen.getByTestId("ass-export-download"));

    const info = await screen.findByTestId("ass-export-result");
    expect(info.textContent).toContain("40");
    expect(info.textContent).toContain("9");
  });

  test("zeigt keinen Render-Knopf, sondern den Hinweis zum Selbst-Brennen", async () => {
    renderDialog();
    await screen.findByTestId("preset-highlight");
    expect(screen.queryByText(/render video/i)).toBeNull();
    expect(screen.getByText(/burned in with ffmpeg/i)).toBeTruthy();
  });

  test("Escape schließt den Dialog", async () => {
    const { onClose } = renderDialog();
    await screen.findByTestId("preset-highlight");
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  test("Klick auf den Hintergrund schließt, Klick in den Dialog nicht", async () => {
    const { onClose } = renderDialog();
    const dialog = await screen.findByTestId("export-dialog");
    fireEvent.click(dialog.firstElementChild as Element);
    expect(onClose).not.toHaveBeenCalled();
    fireEvent.click(dialog);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  test("meldet einen kaputten Katalog sichtbar", async () => {
    vi.mocked(fetchExportPresets).mockRejectedValue(new Error("HTTP 500"));
    renderDialog();
    expect(await screen.findByText(/could not load the templates/i)).toBeTruthy();
  });
});
