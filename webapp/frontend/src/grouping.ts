import type { Recording } from "./api";

/* ============================================================
   GROUPING TYPES
   ============================================================ */

export interface WhatsappGroupItem {
  type: "whatsapp-group";
  batch_id: string;
  members: Recording[];
  /** created_at of the first member (für Anzeige/Kompatibilität; wird
   *  NICHT mehr zum Sortieren benutzt — Change 120). */
  sortKey: string;
}

export interface SingleItem {
  type: "single";
  recording: Recording;
  sortKey: string;
}

export type RenderItem = WhatsappGroupItem | SingleItem;

/* ============================================================
   PARTITION + GROUP (pure function, easily testable)
   ============================================================ */

/**
 * Partition recordings into WhatsApp groups (batch_id + source=whatsapp, ≥2 members)
 * and singles (everything else).
 *
 * Change 120: Die REIHENFOLGE der Render-Items folgt der Eingabe (das
 * Backend hat bereits nach der gewählten Sortierung sortiert — date/
 * edited/name/filename/length). Wir sortieren hier NICHT mehr nach
 * created_at um; nur die WhatsApp-Zusammenfassung bleibt:
 *  - Gruppenblock erscheint an der Position des ERSTEN Mitglieds
 *  - Gruppen-Mitglieder intern nach recorded_at asc (Chat-Chronologie)
 *  - Singles behalten ihre Eingabeposition
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

  // 2. Build groups: members recorded_at asc (fallback created_at asc),
  //    sortKey = created_at des ersten Mitglieds (nur für Kompatibilität).
  const groups = new Map<string, WhatsappGroupItem>();
  for (const [bid, members] of batchMap.entries()) {
    if (!groupBatchIds.has(bid)) continue;

    const sorted = [...members].sort((a, b) => {
      const ka = a.recorded_at ?? a.created_at;
      const kb = b.recorded_at ?? b.created_at;
      return ka < kb ? -1 : ka > kb ? 1 : 0;
    });

    groups.set(bid, {
      type: "whatsapp-group",
      batch_id: bid,
      members: sorted,
      sortKey: sorted[0]?.created_at ?? "",
    });
  }

  const groupedIds = new Set<string>(
    [...groups.values()].flatMap((g) => g.members.map((m) => m.id))
  );

  // 3. Ein Durchgang durch die Eingabereihenfolge: Singles behalten ihre
  //    Position, jede Gruppe erscheint an der Position ihres ersten
  //    Mitglieds (einmal).
  const out: RenderItem[] = [];
  const emittedGroups = new Set<string>();

  for (const rec of recordings) {
    if (!rec.batch_id || !groups.has(rec.batch_id)) {
      if (!groupedIds.has(rec.id)) {
        out.push({ type: "single", recording: rec, sortKey: rec.created_at });
      }
      continue;
    }
    if (emittedGroups.has(rec.batch_id)) continue;
    emittedGroups.add(rec.batch_id);
    out.push(groups.get(rec.batch_id)!);
  }

  return out;
}
