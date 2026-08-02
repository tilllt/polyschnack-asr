/* ============================================================
   SHARE-Tests: Anon-Link-Pfad-Parsing, URL-Bau, Ablauf-Anzeige
   ============================================================ */
import { describe, it, expect } from "vitest";
import { parseSharePath, buildShareUrl, formatExpiry } from "./share.ts";

describe("parseSharePath (/r/:uid)", () => {
  it("parst einen gültigen 32-Zeichen-UID", () => {
    const uid = "0123456789abcdef0123456789abcdef";
    expect(parseSharePath(`/r/${uid}`)).toEqual({ uid });
  });

  it("akzeptiert Großbuchstaben (hex case-insensitive)", () => {
    expect(parseSharePath("/r/0123456789ABCDEF0123456789ABCDEF")).toEqual({
      uid: "0123456789ABCDEF0123456789ABCDEF",
    });
  });

  it("lehnt zu kurze/zu lange UIDs ab", () => {
    expect(parseSharePath("/r/abc")).toBeNull();
    expect(parseSharePath(`/r/${"a".repeat(33)}`)).toBeNull();
  });

  it("lehnt Nicht-/r/-Pfade ab", () => {
    expect(parseSharePath("/settings")).toBeNull();
    expect(parseSharePath("/")).toBeNull();
    expect(parseSharePath("/r/")).toBeNull();
  });
});

describe("buildShareUrl", () => {
  it("baut die Share-URL mit dem aktuellen Origin", () => {
    const origin =
      typeof window !== "undefined"
        ? window.location.origin
        : globalThis.location?.origin ?? "http://localhost";
    const url = buildShareUrl("0123456789abcdef0123456789abcdef");
    expect(url).toBe(`${origin}/r/0123456789abcdef0123456789abcdef`);
  });
});

describe("formatExpiry (Retention-Warnung)", () => {
  const now = new Date("2026-08-02T12:00:00Z").getTime();

  it("zeigt Restminuten bei gültigem Ablauf", () => {
    const exp = new Date(now + 12 * 60000).toISOString();
    expect(formatExpiry(exp, 15, now)).toBe("noch 12 Min.");
  });

  it("rundet auf mindestens 1 Minute", () => {
    const exp = new Date(now + 30 * 1000).toISOString();
    expect(formatExpiry(exp, 15, now)).toBe("noch 1 Min.");
  });

  it("zeigt Stunden bei langer Gültigkeit", () => {
    const exp = new Date(now + 90 * 60000).toISOString();
    expect(formatExpiry(exp, 15, now)).toBe("noch 2 Std.");
  });

  it("meldet 'abgelaufen' bei vergangenem Ablauf", () => {
    const exp = new Date(now - 1000).toISOString();
    expect(formatExpiry(exp, 15, now)).toBe("abgelaufen");
  });

  it("Fallback ohne expires_at: ca. X Minuten", () => {
    expect(formatExpiry(null, 15, now)).toBe("ca. 15 Min.");
  });
});
