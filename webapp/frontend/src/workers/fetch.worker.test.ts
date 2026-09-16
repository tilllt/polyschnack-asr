import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

/**
 * Change 198 — Invariante: ein vorzeitig beendeter Stream darf NIE als
 * vollständige Datei weitergehen.
 *
 * Belegt am Produktionsfall (98-min-Aufnahme, 46,9 MB Preview): brach die
 * Verbindung ab, meldete der Reader `done` und der abgeschnittene Puffer
 * wurde ohne Prüfung weitergereicht. `decodeAudioData` dekodiert eine
 * abgeschnittene Datei LAUTLOS zu einem kürzeren Audio (gemessen im Browser:
 * 3 MB von 47 MB → 1021 s statt 5868 s, `decode_fehler: null`) — WaveSurfer
 * zeichnete eine korrupte Welle ohne jede Fehlermeldung.
 */

type Posted = { type: string; reason?: string; arrayBuffer?: ArrayBuffer };

function fakeResp(opts: {
  chunks: Uint8Array[];
  contentLength: number;
  encoding?: string;
}) {
  let i = 0;
  return {
    ok: true,
    headers: {
      get: (k: string) => {
        const key = k.toLowerCase();
        if (key === "content-length") return String(opts.contentLength);
        if (key === "content-encoding") return opts.encoding ?? "identity";
        return null;
      },
    },
    body: {
      getReader: () => ({
        read: async () =>
          i < opts.chunks.length
            ? { done: false, value: opts.chunks[i++] }
            : { done: true, value: undefined },
      }),
    },
  };
}

let posted: Posted[] = [];

async function runWorker(resp: unknown) {
  (globalThis as Record<string, unknown>).fetch = vi.fn(async () => resp);
  // Worker-Modul importieren → registriert self.onmessage
  await import("./fetch.worker");
  const handler = (globalThis as Record<string, unknown>).onmessage as (
    e: { data: { url: string } },
  ) => Promise<void>;
  await handler({ data: { url: "/api/recordings/x/audio/preview" } });
  // Mikrotasks abarbeiten (decodeToWav + postMessage)
  await new Promise((r) => setTimeout(r, 0));
}

beforeEach(() => {
  vi.resetModules();
  posted = [];
  (globalThis as Record<string, unknown>).postMessage = (m: Posted) => {
    posted.push(m);
  };
  // jsdom hat kein OfflineAudioContext → decodeToWav gibt null zurück und
  // der rohe Puffer geht zurück (genau der Fall, der die Korruption auslöste).
});

afterEach(() => {
  delete (globalThis as Record<string, unknown>).postMessage;
  delete (globalThis as Record<string, unknown>).onmessage;
});

describe("Change 198: Download-Länge wird validiert", () => {
  it("vollständiger Download: kein Fehler, Puffer geht weiter", async () => {
    await runWorker(
      fakeResp({
        chunks: [new Uint8Array(500), new Uint8Array(500)],
        contentLength: 1000,
      }),
    );

    expect(posted.some((m) => m.type === "error")).toBe(false);
    const done = posted.find((m) => m.type === "done");
    expect(done).toBeDefined();
    expect(done?.arrayBuffer?.byteLength).toBe(1000);
  });

  it("abgeschnittener Download: FEHLER statt stiller Korruption", async () => {
    // 300 von 1000 Bytes — die Verbindung ist vorzeitig abgerissen.
    await runWorker(
      fakeResp({
        chunks: [new Uint8Array(300)],
        contentLength: 1000,
      }),
    );

    const err = posted.find((m) => m.type === "error");
    expect(err).toBeDefined();
    expect(err?.reason).toContain("unvollstaendig");
    expect(err?.reason).toContain("300");
    expect(err?.reason).toContain("1000");
    // Der unvollständige Puffer darf NICHT als Ergebnis durchgehen.
    expect(posted.some((m) => m.type === "done")).toBe(false);
  });

  it("gzip-Response: kein Fehlalarm (content-length ist komprimiert)", async () => {
    // Dekodierter Stream ist GRÖSSER als content-length → nicht als
    // unvollständig werten, sonst bricht jeder gzip-Download ab.
    await runWorker(
      fakeResp({
        chunks: [new Uint8Array(2000)],
        contentLength: 1000,
        encoding: "gzip",
      }),
    );

    expect(posted.some((m) => m.type === "error")).toBe(false);
    expect(posted.some((m) => m.type === "done")).toBe(true);
  });
});
