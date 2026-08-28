/**
 * Change 120 — Debounce-Hook + AbortSignal-Durchreichung.
 *
 * - useDebouncedValue: schnelle Änderungen (Badge-Klicks) bündeln die
 *   Query-Requests, ohne das UI-Feedback zu verzögern.
 * - fetchRecordings reicht ein AbortSignal an fetch weiter (React Query
 *   bricht damit überholte Requests ab).
 */
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { fetchRecordings } from "./api";
import { useDebouncedValue, detailEnabled, shouldPollDetail } from "./hooks";

describe("useDebouncedValue", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("liefert sofort den Initialwert", () => {
    const { result } = renderHook(() => useDebouncedValue("date", 250));
    expect(result.current).toBe("date");
  });

  it("übernimmt neue Werte erst nach der Verzögerung", () => {
    const { result, rerender } = renderHook(
      ({ v }: { v: string }) => useDebouncedValue(v, 250),
      { initialProps: { v: "date" } },
    );

    rerender({ v: "name" });
    expect(result.current).toBe("date"); // noch debounced

    act(() => {
      vi.advanceTimersByTime(249);
    });
    expect(result.current).toBe("date");

    act(() => {
      vi.advanceTimersByTime(1);
    });
    expect(result.current).toBe("name");
  });

  it("bündelt mehrere schnelle Änderungen (nur der letzte Wert gewinnt)", () => {
    const { result, rerender } = renderHook(
      ({ v }: { v: string }) => useDebouncedValue(v, 250),
      { initialProps: { v: "date" } },
    );

    rerender({ v: "name" });
    rerender({ v: "filename" });
    rerender({ v: "length" });
    expect(result.current).toBe("date");

    act(() => {
      vi.advanceTimersByTime(250);
    });
    expect(result.current).toBe("length");
  });
});

describe("fetchRecordings — AbortSignal", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("reicht das Signal an fetch weiter (sort + dir + tag im Query)", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify([]), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const controller = new AbortController();
    await fetchRecordings("", { sort: "name", dir: "asc", tags: ["arbeit"] }, true, controller.signal);

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("sort=name");
    expect(url).toContain("dir=asc");
    expect(url).toContain("tag=arbeit");
    expect(init.signal).toBe(controller.signal);
  });

  it("abgebrochenes Signal → fetch wirft AbortError", async () => {
    const fetchMock = vi.fn().mockRejectedValue(new DOMException("Aborted", "AbortError"));
    vi.stubGlobal("fetch", fetchMock);

    const controller = new AbortController();
    controller.abort();
    await expect(
      fetchRecordings("", {}, true, controller.signal),
    ).rejects.toMatchObject({ name: "AbortError" });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});

describe("detailEnabled / shouldPollDetail (Change 138)", () => {
  it("detailEnabled: queued/processing/done aktiv, uploaded/failed/undefined nicht", () => {
    expect(detailEnabled("queued")).toBe(true);
    expect(detailEnabled("processing")).toBe(true);
    expect(detailEnabled("done")).toBe(true);
    expect(detailEnabled("uploaded")).toBe(false);
    expect(detailEnabled("failed")).toBe(false);
    expect(detailEnabled(undefined)).toBe(false);
  });

  it("shouldPollDetail: nur queued/processing pollen (done/uploaded/failed nicht)", () => {
    expect(shouldPollDetail("queued")).toBe(true);
    expect(shouldPollDetail("processing")).toBe(true);
    expect(shouldPollDetail("done")).toBe(false);
    expect(shouldPollDetail("uploaded")).toBe(false);
    expect(shouldPollDetail("failed")).toBe(false);
    expect(shouldPollDetail(undefined)).toBe(false);
  });
});
