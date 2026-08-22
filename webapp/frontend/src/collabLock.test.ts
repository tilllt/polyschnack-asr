/** Change 084: Kollaborations-Lock — editorsFromStates (pure). */
import { describe, expect, it } from "vitest";

import { editorsFromStates } from "./collabLock";

const withUser = (name: string, editing: boolean | number) => ({
  user: { name },
  editing,
});

describe("editorsFromStates (Change 084)", () => {
  it("fremder Editor mit Segment-Index → editLock { index, name } + activeEditors", () => {
    const states = new Map<number, unknown>([
      [1, withUser("Anna", 2)],
      [2, withUser("Ich", false)],
    ]);
    const res = editorsFromStates(states, 2);
    expect(res.activeEditors).toEqual(["Anna"]);
    expect(res.editLock).toEqual({ index: 2, name: "Anna" });
  });

  it("eigener Client wird ausgeschlossen (auch mit editing-Index)", () => {
    const states = new Map<number, unknown>([[7, withUser("Ich", 3)]]);
    const res = editorsFromStates(states, 7);
    expect(res.activeEditors).toEqual([]);
    expect(res.editLock).toBeNull();
  });

  it("editing=false/undefined zählt nicht (bloßes Öffnen der Seite)", () => {
    const states = new Map<number, unknown>([
      [1, withUser("Anna", false)],
      [2, { user: { name: "Ben" } }], // kein editing-Feld
    ]);
    const res = editorsFromStates(states, 9);
    expect(res.activeEditors).toEqual([]);
    expect(res.editLock).toBeNull();
  });

  it("mehrere fremde Editoren → erster gewinnt fürs Lock, alle in activeEditors", () => {
    const states = new Map<number, unknown>([
      [1, withUser("Anna", 0)],
      [2, withUser("Ben", 4)],
    ]);
    const res = editorsFromStates(states, 9);
    expect(res.activeEditors).toEqual(["Anna", "Ben"]);
    expect(res.editLock).toEqual({ index: 0, name: "Anna" });
  });

  it("Record-ähnliche States (Object statt Map) funktionieren", () => {
    const states: Record<number, unknown> = {
      1: withUser("Anna", 1),
      2: withUser("Ich", false),
    };
    const res = editorsFromStates(states, 2);
    expect(res.editLock).toEqual({ index: 1, name: "Anna" });
  });

  it("Editor ohne Namen blockt kein Lock und taucht nicht auf", () => {
    const states = new Map<number, unknown>([
      [1, { user: {}, editing: 0 }],
      [2, withUser("Anna", 3)],
    ]);
    const res = editorsFromStates(states, 9);
    expect(res.activeEditors).toEqual(["Anna"]);
    expect(res.editLock).toEqual({ index: 3, name: "Anna" });
  });
});
