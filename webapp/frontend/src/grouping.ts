import type { Recording } from "./api";

/* ============================================================
   GROUPING TYPES
   ============================================================ */

export interface WhatsappGroupItem {
  type: "whatsapp-group";
  batch_id: string;
  members: Recording[];
  /** created_at of the newest member (for interleaving sort) */
  sortKey: string;
}

export interface SingleItem {
  type: "single";
  recording: Recording;
  sortKey: string;
}

export type RenderItem = WhatsappGroupItem | SingleItem;

/* ============================================================
   PARTITION + SORT (pure function, easily testable)
   ============================================================ */

/**
 * Partition recordings into WhatsApp groups (batch_id + source=whatsapp, ≥2 members)
 * and singles (everything else).
 *
 * Sort:
 *  - Group members: by recorded_at asc (fallback created_at asc)
 *  - Singles: by created_at desc
 *  - Interleaved final list: by each item's most-recent created_at desc
 */
export function buildRenderItems(recordings: Recording[]): RenderItem[] {
  // 1. Identify WhatsApp groups: batch_id != null, source === "whatsapp", ≥2 members
  const batchMap = new Map<string, Recording[]>();

  for (const rec of recordings) {
    if (rec.batch_id && rec.source === "whatsapp") {
      const existing = batchMap.get(rec.batch_id) ?? [];
      existing.push(rec);
      batchMap.set(rec.batch_id, existing);
    }
  }

  // Keep only batches with ≥ 2 members
  const groupBatchIds = new Set<string>();
  for (const [bid, members] of batchMap.entries()) {
    if (members.length >= 2) groupBatchIds.add(bid);
  }

  // 2. Build groups
  const groups: WhatsappGroupItem[] = [];
  for (const [bid, members] of batchMap.entries()) {
    if (!groupBatchIds.has(bid)) continue;

    // Sort members by recorded_at asc, fallback created_at asc
    const sorted = [...members].sort((a, b) => {
      const ka = a.recorded_at ?? a.created_at;
      const kb = b.recorded_at ?? b.created_at;
      return ka < kb ? -1 : ka > kb ? 1 : 0;
    });

    // sortKey = newest member's created_at
    const initialKey = sorted[0]?.created_at ?? "";
    const sortKey = sorted.reduce(
      (max, r) => (r.created_at > max ? r.created_at : max),
      initialKey
    );

    groups.push({ type: "whatsapp-group", batch_id: bid, members: sorted, sortKey });
  }

  // 3. Singles = all recordings NOT in a qualifying group
  const groupedIds = new Set<string>(
    groups.flatMap((g) => g.members.map((m) => m.id))
  );

  const singles: SingleItem[] = recordings
    .filter((r) => !groupedIds.has(r.id))
    .map((r) => ({
      type: "single" as const,
      recording: r,
      sortKey: r.created_at,
    }));

  // 4. Interleave: combine groups + singles, sort by sortKey desc
  const all: RenderItem[] = [...groups, ...singles];
  all.sort((a, b) => (a.sortKey < b.sortKey ? 1 : a.sortKey > b.sortKey ? -1 : 0));

  return all;
}
