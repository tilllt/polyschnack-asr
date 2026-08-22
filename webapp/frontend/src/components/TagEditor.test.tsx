/**
 * Change 054 — TagEditor: Anzeige, Add (Enter), Remove (×), Rechte.
 * Change 092 — Autocomplete: Vorschlagsliste existierender Tags.
 */
import { beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { LocaleProvider } from "../useLocale";
import { TagEditor } from "./TagEditor";
import { updateRecordingTags } from "../api";

const { mockAllTags } = vi.hoisted(() => ({
  mockAllTags: { value: [] as string[] },
}));

vi.mock("../api", async () => {
  const actual = await vi.importActual<typeof import("../api")>("../api");
  return {
    ...actual,
    updateRecordingTags: vi.fn().mockResolvedValue({ uid: "r1", tags: [] }),
  };
});

vi.mock("@tanstack/react-query", () => ({
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
  useQuery: () => ({ data: mockAllTags.value, isLoading: false }),
}));

vi.mock("./Toasts", () => ({
  useToast: () => ({ toast: vi.fn() }),
}));

function renderEditor(props: Partial<Parameters<typeof TagEditor>[0]> = {}) {
  return render(
    <LocaleProvider>
      <TagEditor uid="r1" tags={["walzen", "review"]} canEdit={true} {...props} />
    </LocaleProvider>,
  );
}

describe("TagEditor", () => {
  beforeEach(() => {
    vi.mocked(updateRecordingTags).mockClear();
    mockAllTags.value = ["walzen", "review", "schellack", "archiv"];
  });

  test("zeigt Tags als Chips", () => {
    renderEditor();
    expect(screen.getByText("#walzen")).toBeTruthy();
    expect(screen.getByText("#review")).toBeTruthy();
  });

  test("ohne Schreibrecht: Chips ohne Entfernen-Button", () => {
    renderEditor({ canEdit: false });
    expect(screen.getByText("#walzen")).toBeTruthy();
    // Kein Eingabefeld + kein ×-Button (aria-label tag_remove)
    expect(screen.queryByLabelText("Remove tag")).toBeNull();
  });

  test("ohne Tags und ohne Recht: nichts rendern", () => {
    const { container } = renderEditor({ tags: [], canEdit: false });
    expect(container.querySelector('[data-testid="tag-editor"]')).toBeNull();
  });

  test("Enter fügt Tag hinzu → PATCH mit erweiterter Liste", () => {
    renderEditor();
    const input = screen.getByPlaceholderText("Add tag…");
    fireEvent.change(input, { target: { value: "schellack" } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(updateRecordingTags).toHaveBeenCalledWith("r1", [
      "walzen",
      "review",
      "schellack",
    ]);
  });

  test("Duplikat (case-insensitiv) → kein API-Call", () => {
    renderEditor();
    const input = screen.getByPlaceholderText("Add tag…");
    fireEvent.change(input, { target: { value: "WALZEN" } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(updateRecordingTags).not.toHaveBeenCalled();
  });

  test("× entfernt Tag → PATCH ohne das Tag", () => {
    renderEditor();
    // aria-label ist „Remove tag #<tag>" (Screenreader: welches Tag)
    const remove = screen.getAllByLabelText(/Remove tag/);
    fireEvent.click(remove[0]); // walzen
    expect(updateRecordingTags).toHaveBeenCalledWith("r1", ["review"]);
  });

  test("Fokus ins Feld öffnet Vorschlagsliste — nur nicht vergebene Tags (Change 092)", () => {
    renderEditor();
    const input = screen.getByPlaceholderText("Add tag…");
    fireEvent.focus(input);
    const suggestions = screen.getByTestId("tag-suggestions");
    expect(suggestions.textContent).toContain("#schellack");
    expect(suggestions.textContent).toContain("#archiv");
    // Bereits vergebene Tags (walzen, review) erscheinen nicht
    expect(suggestions.textContent).not.toContain("#walzen");
    expect(suggestions.textContent).not.toContain("#review");
  });

  test("Klick auf Vorschlag übernimmt den Tag → PATCH (Change 092)", () => {
    renderEditor();
    const input = screen.getByPlaceholderText("Add tag…");
    fireEvent.focus(input);
    fireEvent.click(screen.getByText("#schellack"));
    expect(updateRecordingTags).toHaveBeenCalledWith("r1", [
      "walzen",
      "review",
      "schellack",
    ]);
  });

  test("Tippen filtert die Vorschlagsliste (Change 092)", () => {
    renderEditor();
    const input = screen.getByPlaceholderText("Add tag…");
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: "sch" } });
    const suggestions = screen.getByTestId("tag-suggestions");
    expect(suggestions.textContent).toContain("#schellack");
    expect(suggestions.textContent).not.toContain("#archiv");
  });

  test("Enter mit Highlight übernimmt den Vorschlag statt des Tipptexts (Change 092)", () => {
    renderEditor();
    const input = screen.getByPlaceholderText("Add tag…");
    fireEvent.focus(input);
    fireEvent.keyDown(input, { key: "ArrowDown" }); // Highlight auf #archiv
    fireEvent.keyDown(input, { key: "Enter" });
    expect(updateRecordingTags).toHaveBeenCalledWith("r1", [
      "walzen",
      "review",
      "archiv",
    ]);
  });

  test("Escape schließt die Vorschlagsliste (Change 092)", () => {
    renderEditor();
    const input = screen.getByPlaceholderText("Add tag…");
    fireEvent.focus(input);
    expect(screen.queryByTestId("tag-suggestions")).toBeTruthy();
    fireEvent.keyDown(input, { key: "Escape" });
    expect(screen.queryByTestId("tag-suggestions")).toBeNull();
  });
});
