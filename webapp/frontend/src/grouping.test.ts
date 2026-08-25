/**
 * Change 120 — buildRenderItems respektiert die Backend-Sortierung.
 *
 * Vorher sortierte die Funktion die Render-Items hart nach created_at desc
 * und verwarf damit jede gewählte Sortierung (Name/Länge/…). Jetzt:
 * - WhatsApp-Gruppen (≥2 Mitglieder) bleiben zusammengefasst
 * - Gruppenblock erscheint an der Position des ERSTEN Mitglieds in der
 *   Eingabe (Backend-Reihenfolge), Mitglieder intern recorded_at asc
 * - Singles behalten ihre Eingabeposition
 */
import { describe, expect, it } from "vitest";

import type { Recording } from "./api";
import { buildRenderItems, type RenderItem } from "./grouping";

/** Minimales Recording für Tests (id ist im API-Typ ein String). */
function mkRec(
  partial: Partial<Recording> & { id: string; original_name: string },
): Recording {
  return {
    uid: `u${partial.id}`,
    stored_path: "p",
    mime: "audio/mpeg",
    size_bytes: 1,
    status: "done",
    backend: "ps-pk-onnx",
    alignment: "done",
    diar_status: "done",
    created_at: "2026-08-01T00:00:00Z",
    updated_at: "2026-08-01T00:00:00Z",
    tags: [],
    ...partial,
  } as Recording;
}

function isSingle(item: RenderItem): item is Extract<RenderItem, { type: "single" }> {
  return item.type === "single";
}

function isGroup(item: RenderItem): item is Extract<RenderItem, { type: "whatsapp-group" }> {
  return item.type === "whatsapp-group";
}

/** ids der Singles (Gruppen → "-1"), in Render-Reihenfolge. */
function renderIds(items: RenderItem[]): string[] {
  return items.map((i) => (isSingle(i) ? i.recording.id : "-1"));
}

/** Beschreibung der Render-Reihenfolge: Dateiname oder "GRUPPE(<batch>)". */
function renderDesc(items: RenderItem[]): string[] {
  return items.map((i) =>
    isGroup(i) ? `GRUPPE(${i.batch_id})` : isSingle(i) ? i.recording.original_name : "?"
  );
}

describe("buildRenderItems — Backend-Reihenfolge", () => {
  it("leere Liste → leer", () => {
    expect(buildRenderItems([])).toEqual([]);
  });

  it("nur Singles → exakt die Eingabereihenfolge (Backend-Sortierung)", () => {
    const a = mkRec({ id: "1", original_name: "alpha.mp3" });
    const b = mkRec({ id: "2", original_name: "bravo.mp3" });
    const c = mkRec({ id: "3", original_name: "charlie.mp3" });
    // Backend hat z. B. nach name asc sortiert — diese Reihenfolge zählt.
    const items = buildRenderItems([b, c, a]);
    expect(items.map((i) => i.type)).toEqual(["single", "single", "single"]);
    expect(renderIds(items)).toEqual(["2", "3", "1"]);
  });

  it("WhatsApp-Gruppe (≥2) erscheint an Position ihres ersten Mitglieds", () => {
    const alpha = mkRec({ id: "1", original_name: "alpha.mp3" });
    const wa1 = mkRec({
      id: "2", original_name: "wa1.mp3", batch_id: "b1", source: "whatsapp",
      recorded_at: "2026-08-03T00:00:00Z", created_at: "2026-08-03T00:00:00Z",
    });
    const wa2 = mkRec({
      id: "3", original_name: "wa2.mp3", batch_id: "b1", source: "whatsapp",
      recorded_at: "2026-08-01T00:00:00Z", created_at: "2026-08-03T00:00:00Z",
    });
    const wa3 = mkRec({
      id: "4", original_name: "wa3.mp3", batch_id: "b1", source: "whatsapp",
      recorded_at: "2026-08-02T00:00:00Z", created_at: "2026-08-03T00:00:00Z",
    });
    const charlie = mkRec({ id: "5", original_name: "charlie.mp3" });

    // Backend hat nach name sortiert: alpha, wa1, wa2, wa3, charlie
    const items = buildRenderItems([alpha, wa1, wa2, wa3, charlie]);
    expect(items.map((i) => i.type)).toEqual(["single", "whatsapp-group", "single"]);
    expect(renderIds(items)).toEqual(["1", "-1", "5"]);

    // Gruppenblock an Position des ersten Mitglieds (wa1)
    const group = items[1];
    expect(isGroup(group)).toBe(true);
    if (!isGroup(group)) return;
    expect(group.batch_id).toBe("b1");
    // Mitglieder intern recorded_at asc: wa2 (01.) → wa3 (02.) → wa1 (03.)
    expect(group.members.map((m) => m.id)).toEqual(["3", "4", "2"]);
  });

  it("Backend-Sortierung nach Name bleibt über die ganze Liste erhalten", () => {
    const alpha = mkRec({ id: "1", original_name: "alpha.mp3", created_at: "2026-08-10T00:00:00Z" });
    const bravo = mkRec({ id: "2", original_name: "bravo.mp3", created_at: "2026-08-09T00:00:00Z" });
    const wa1 = mkRec({
      id: "3", original_name: "wa1.mp3", batch_id: "b1", source: "whatsapp",
      recorded_at: "2026-08-08T00:00:00Z", created_at: "2026-08-08T00:00:00Z",
    });
    const wa2 = mkRec({
      id: "4", original_name: "wa2.mp3", batch_id: "b1", source: "whatsapp",
      recorded_at: "2026-08-07T00:00:00Z", created_at: "2026-08-08T00:00:00Z",
    });
    const zulu = mkRec({ id: "5", original_name: "zulu.mp3", created_at: "2026-08-06T00:00:00Z" });

    // name asc: alpha, bravo, wa1, wa2, zulu — NICHT created_at desc!
    const items = buildRenderItems([alpha, bravo, wa1, wa2, zulu]);
    expect(renderDesc(items)).toEqual(["alpha.mp3", "bravo.mp3", "GRUPPE(b1)", "zulu.mp3"]);
  });

  it("Batch mit nur 1 WhatsApp-Mitglied → kein Gruppen-Item", () => {
    const single = mkRec({
      id: "1", original_name: "wa1.mp3", batch_id: "b1", source: "whatsapp",
    });
    const items = buildRenderItems([single]);
    expect(items.map((i) => i.type)).toEqual(["single"]);
  });

  it("batch_id ohne source=whatsapp → Single", () => {
    const rec = mkRec({ id: "1", original_name: "x.mp3", batch_id: "b1" });
    const items = buildRenderItems([rec, rec]);
    expect(items.map((i) => i.type)).toEqual(["single", "single"]);
  });

  it("Gruppe wird nicht doppelt emittiert (3 Mitglieder, ein Block)", () => {
    const wa1 = mkRec({ id: "1", original_name: "w1.mp3", batch_id: "b1", source: "whatsapp", recorded_at: "2026-08-01T00:00:00Z" });
    const wa2 = mkRec({ id: "2", original_name: "w2.mp3", batch_id: "b1", source: "whatsapp", recorded_at: "2026-08-02T00:00:00Z" });
    const wa3 = mkRec({ id: "3", original_name: "w3.mp3", batch_id: "b1", source: "whatsapp", recorded_at: "2026-08-03T00:00:00Z" });
    const items = buildRenderItems([wa3, wa1, wa2]);
    expect(items.filter((i) => i.type === "whatsapp-group")).toHaveLength(1);
  });
});
