/** Change 124: SegmentSearch zählt Treffer gegen die Anzeige-Segmente und
 *  delegiert Ersetzen an onReplaceRequest (Yjs-fähiger Schreibpfad). */
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("../api", () => ({ updateSegment: vi.fn() }));

import { SegmentSearch } from "./SegmentSearch";

const segs = [
  { start: 0, end: 2, text: "Hallo Welt", speaker: "SPEAKER_00" },
  { start: 2, end: 4, text: "Zweiter Satz mit Welt", speaker: "SPEAKER_00" },
];

function renderSearch(opts: { onReplaceRequest?: () => void } = {}) {
  return render(
    <SegmentSearch
      segments={segs}
      query="Welt"
      onQueryChange={vi.fn()}
      onNavigateHit={vi.fn()}
      onReplaceRequest={opts.onReplaceRequest}
    />,
  );
}

describe("SegmentSearch (Change 124)", () => {
  it("zählt Treffer gegen die übergebenen (Anzeige-)Segmente", () => {
    renderSearch();
    expect(screen.getByText("2 ×")).toBeTruthy(); // "Welt" in beiden Segmenten
  });

  it("Ersetzen-Klick ruft onReplaceRequest mit query+replace+one", () => {
    const onReplace = vi.fn();
    renderSearch({ onReplaceRequest: onReplace });
    const replaceInput = screen.getByPlaceholderText("Replace…");
    fireEvent.change(replaceInput, { target: { value: "Universum" } });
    fireEvent.click(screen.getByText("Replace"));
    expect(onReplace).toHaveBeenCalledWith({
      one: true,
      query: "Welt",
      replace: "Universum",
    });
  });

  it("All-Klick ruft onReplaceRequest mit one=false", () => {
    const onReplace = vi.fn();
    renderSearch({ onReplaceRequest: onReplace });
    const replaceInput = screen.getByPlaceholderText("Replace…");
    fireEvent.change(replaceInput, { target: { value: "Universum" } });
    fireEvent.click(screen.getByText("All"));
    expect(onReplace).toHaveBeenCalledWith({
      one: false,
      query: "Welt",
      replace: "Universum",
    });
  });
});
