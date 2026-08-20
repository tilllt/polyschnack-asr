/**
 * Change 054 — Sortierung + Tag-Filter der Recording-Liste.
 *
 * Pure Logik (kein Rendering) → direkt testbar.
 */

import type { RecordingSort, RecordingSortDir } from "./api";

/** Aktive Sortierung; null = Default (Date absteigend, wie bisher). */
export type SortState = { key: RecordingSort; dir: RecordingSortDir } | null;

/**
 * Badge-Klick-Zyklus (User-Vorgabe 2026-08-20):
 * 1. Klick auf ein (inaktives) Badge   → absteigend (desc)
 * 2. Klick auf dasselbe Badge          → aufsteigend (asc)
 * 3. Klick auf dasselbe Badge          → zurück zum Default (null)
 */
export function nextSortState(current: SortState, key: RecordingSort): SortState {
  if (!current || current.key !== key) return { key, dir: "desc" };
  if (current.dir === "desc") return { key, dir: "asc" };
  return null;
}

/** Sort-Query für die API (kein aktives Badge → keine Parameter). */
export function sortParams(state: SortState): {
  sort: RecordingSort | null;
  dir: RecordingSortDir | undefined;
} {
  if (!state) return { sort: null, dir: undefined };
  return { sort: state.key, dir: state.dir };
}

/**
 * Tag-Aggregation aus der geladenen Liste (Change 054: Filter zeigt nur
 * Tags mit ≥ 1 Aufnahme, mit Count). Alphabetisch sortiert.
 */
export function aggregateTags(
  recordings: { tags?: string[] }[],
): { tag: string; count: number }[] {
  const m = new Map<string, number>();
  for (const r of recordings) {
    for (const tag of r.tags ?? []) {
      m.set(tag, (m.get(tag) ?? 0) + 1);
    }
  }
  return [...m.entries()]
    .map(([tag, count]) => ({ tag, count }))
    .sort((a, b) => a.tag.localeCompare(b.tag));
}
