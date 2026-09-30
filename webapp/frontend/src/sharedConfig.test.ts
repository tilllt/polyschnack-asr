/**
 * Change 236 — geteilte Serverauskünfte (src/sharedConfig.ts).
 *
 * Warum es diese Schicht gibt: Am 30.09.2026 feuerte ein Aufruf der
 * Aufnahmenliste bei 116 Aufnahmen ~812 Abfragen in 24 s, weil jede Karte
 * sieben serverweite Auskünfte selbst holte (Gemessenes siehe Change 236,
 * status.md). Geprüft wird hier die Eigenschaft, auf die sich die Karten
 * verlassen: gleiche Auskunft + gleicher Zeitraum = EINE Abfrage.
 */
import { describe, expect, test, vi } from "vitest";
import {
  SHARED_CONFIG_TTL_MS,
  forgetSharedConfig,
  once,
  sharedConfigKeys,
} from "./sharedConfig";

describe("Change 236 — einmal je Seite statt einmal je Karte", () => {
  test("gleichzeitiger Aufruf mehrerer Karten ergibt EINE Abfrage", async () => {
    let calls = 0;
    const load = () =>
      new Promise<number>((resolve) => {
        calls += 1;
        setTimeout(() => resolve(116), 5);
      });

    const [a, b, c] = await Promise.all([
      once("gleichzeitig", load),
      once("gleichzeitig", load),
      once("gleichzeitig", load),
    ]);

    expect(calls).toBe(1);
    expect([a, b, c]).toEqual([116, 116, 116]);
  });

  test("innerhalb der Ablaufzeit kommt die geholte Auskunft zurück", async () => {
    let calls = 0;
    const load = async () => {
      calls += 1;
      return calls;
    };

    const erste = await once("ablauf-innen", load, 1000);
    const zweite = await once("ablauf-innen", load, 1000);

    expect(calls).toBe(1);
    expect(erste).toBe(1);
    expect(zweite).toBe(1);
  });

  test("nach dem Ablauf wird wieder geholt (kein eingefrorener Stand)", async () => {
    let calls = 0;
    const load = async () => {
      calls += 1;
      return calls;
    };

    expect(await once("ablauf-aussen", load, 0)).toBe(1);
    expect(await once("ablauf-aussen", load, 0)).toBe(2);
  });

  test("Fehler werden nicht gemerkt — der nächste Aufruf versucht es erneut", async () => {
    let calls = 0;
    const load = async () => {
      calls += 1;
      if (calls === 1) throw new Error("Netz weg");
      return "ok";
    };

    await expect(once("fehler", load)).rejects.toThrow("Netz weg");
    expect(sharedConfigKeys()).not.toContain("fehler");
    await expect(once("fehler", load)).resolves.toBe("ok");
    expect(calls).toBe(2);
  });

  test("forgetSharedConfig leert gezielt nach Vorsilbe", async () => {
    const load = async () => 1;
    await once("templates", load);
    await once("targets", load);

    forgetSharedConfig("templates");

    expect(sharedConfigKeys()).toContain("targets");
    expect(sharedConfigKeys()).not.toContain("templates");
  });

  test("die Ablaufzeit ist gesetzt (nicht 0, nicht unendlich)", () => {
    expect(SHARED_CONFIG_TTL_MS).toBeGreaterThanOrEqual(1000);
    expect(SHARED_CONFIG_TTL_MS).toBeLessThanOrEqual(10 * 60_000);
  });

  test("zwei verschiedene Auskünfte bleiben getrennt", async () => {
    const a = vi.fn(async () => "matrix");
    const b = vi.fn(async () => "vorlagen");

    expect(await once("matrix", a)).toBe("matrix");
    expect(await once("vorlagen", b)).toBe("vorlagen");
    expect(await once("matrix", a)).toBe("matrix");

    expect(a).toHaveBeenCalledTimes(1);
    expect(b).toHaveBeenCalledTimes(1);
  });
});
