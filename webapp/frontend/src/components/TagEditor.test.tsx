/**
 * Change 054 — TagEditor: Anzeige, Add (Enter), Remove (×), Rechte.
 */
import { beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { LocaleProvider } from "../useLocale";
import { TagEditor } from "./TagEditor";
import { updateRecordingTags } from "../api";

vi.mock("../api", async () => {
  const actual = await vi.importActual<typeof import("../api")>("../api");
  return {
    ...actual,
    updateRecordingTags: vi.fn().mockResolvedValue({ uid: "r1", tags: [] }),
  };
});

vi.mock("@tanstack/react-query", () => ({
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
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
});
