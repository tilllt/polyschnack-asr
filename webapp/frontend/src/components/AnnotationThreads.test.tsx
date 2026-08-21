/**
 * Change 056 — AnnotationThreads: Threads, Markdown, Mentions, Antworten,
 * Autor-Rechte (Edit/Delete), Playback-Highlight, Zeitfenster-Chip.
 */
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { LocaleProvider } from "../useLocale";
import type { Annotation } from "../api";

vi.mock("../api", () => ({
  fetchMe: vi.fn(),
  replyToAnnotation: vi.fn(),
  updateAnnotation: vi.fn(),
  deleteAnnotation: vi.fn(),
}));

vi.mock("./Toasts", () => ({ useToast: () => ({ toast: vi.fn() }) }));

// react-query: ["me"]-Query für den Autor-Check; Invalidate nur protokolliert.
const invalidate = vi.fn();
vi.mock("@tanstack/react-query", () => ({
  useQueryClient: () => ({ invalidateQueries: invalidate }),
  useQuery: vi.fn(() => ({ data: { sub: "u1", name: "Anna" } })),
}));

import { AnnotationThreads } from "./AnnotationThreads";
import { fetchMe, replyToAnnotation, updateAnnotation, deleteAnnotation } from "../api";

function ann(over: Partial<Annotation>): Annotation {
  return {
    id: 1,
    uid: "a1",
    rec_id: 1,
    user_id: 1,
    user_name: "Anna",
    user_sub: "u1",
    segment_idx: 0,
    char_start: 0,
    char_end: 5,
    start_s: 10,
    end_s: 12,
    body: "schwer verständlich",
    parent_id: null,
    created_at: "2026-08-20T10:00:00Z",
    updated_at: "2026-08-20T10:00:00Z",
    ...over,
  };
}

function renderThreads(annotations: Annotation[], opts: { canEdit?: boolean; activeId?: number | null; onSeek?: (t: number) => void } = {}) {
  return render(
    <LocaleProvider>
      <AnnotationThreads
        rid="r1"
        annotations={annotations}
        canEdit={opts.canEdit ?? true}
        activeId={opts.activeId ?? null}
        onSeek={opts.onSeek}
      />
    </LocaleProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(fetchMe).mockResolvedValue({ sub: "u1", name: "Anna", authenticated: true });
  vi.mocked(replyToAnnotation).mockResolvedValue(ann({ id: 2, body: "Antwort" }));
  vi.mocked(updateAnnotation).mockResolvedValue(ann({ body: "geändert" }));
  vi.mocked(deleteAnnotation).mockResolvedValue({ deleted: 1, replies_deleted: 0 });
});

describe("AnnotationThreads (Change 056)", () => {
  it("rendert Top-Level-Annotation und eingerückte Antworten", () => {
    renderThreads([
      ann({}),
      ann({ id: 2, uid: "a2", user_name: "Ben", user_sub: "u2", body: "Antwort", parent_id: 1 }),
    ]);
    expect(screen.getByText("schwer verständlich")).toBeTruthy();
    expect(screen.getByText("Antwort")).toBeTruthy();
    expect(screen.getAllByText("Anna").length).toBeGreaterThan(0);
  });

  it("rendert Markdown (strong) sicher", () => {
    renderThreads([ann({ body: "sehr **wichtig**" })]);
    expect(screen.getByText("wichtig").tagName).toBe("STRONG");
  });

  it("rendert NICHTS ohne Annotationen (Change 067-Fix: kein Empty-State-Hinweis)", () => {
    const { container } = renderThreads([]);
    expect(container.textContent).toBe("");
  });

  it("Zeitfenster-Chip ruft onSeek mit start_s", () => {
    const onSeek = vi.fn();
    renderThreads([ann({})], { onSeek });
    fireEvent.click(screen.getByTitle("Jump to position"));
    expect(onSeek).toHaveBeenCalledWith(10);
  });

  it("Mention @name → Chip; Klick belegt das Antwort-Formular", () => {
    renderThreads([ann({ body: "@ben kannst du helfen?" })]);
    const chip = screen.getByText("@ben");
    expect(chip.tagName).toBe("BUTTON");
    fireEvent.click(chip);
    const ta = screen.getByPlaceholderText(/Reply…/);
    expect((ta as HTMLTextAreaElement).value).toContain("@ben ");
  });

  it("Reply sendet und invalidiert", async () => {
    renderThreads([ann({})]);
    fireEvent.change(screen.getByPlaceholderText(/Reply…/), {
      target: { value: "meine Antwort" },
    });
    fireEvent.click(screen.getByText("Reply"));
    await waitFor(() => {
      expect(replyToAnnotation).toHaveBeenCalledWith(1, "meine Antwort");
      expect(invalidate).toHaveBeenCalled();
    });
  });

  it("Edit/Delete nur für den Autor (sub-Vergleich)", () => {
    // fetchMe liefert sub "u1" → nur die eigene Annotation hat Buttons
    renderThreads([
      ann({ id: 1, user_sub: "u1" }),
      ann({ id: 3, uid: "a3", user_name: "Carla", user_sub: "u3", parent_id: 1, body: "fremd" }),
    ]);
    // eigene: 1 Edit + 1 Delete
    expect(screen.getAllByLabelText("Edit").length).toBe(1);
    expect(screen.getAllByLabelText("Delete").length).toBe(1);
  });

  it("activeId (Playback-Fenster) highlightet den Thread", () => {
    renderThreads([ann({ id: 5, start_s: 30, end_s: 32 })], { activeId: 5 });
    const el = screen.getByText("schwer verständlich").closest("[data-active]") as HTMLElement;
    expect(el.dataset.active).toBe("1");
  });

  it("Delete ruft deleteAnnotation und invalidiert", async () => {
    renderThreads([ann({})]);
    fireEvent.click(screen.getByLabelText("Delete"));
    await waitFor(() => {
      expect(deleteAnnotation).toHaveBeenCalledWith(1);
      expect(invalidate).toHaveBeenCalled();
    });
  });
});
