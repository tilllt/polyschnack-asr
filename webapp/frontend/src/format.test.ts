import { describe, expect, it } from "vitest";
import { abbreviateMid, fmtBytes, fmtTimecode } from "./format";

describe("abbreviateMid", () => {
  it("lässt kurze Namen unverändert", () => {
    expect(abbreviateMid("Anna")).toBe("Anna");
    expect(abbreviateMid("TILLMETZ", 14)).toBe("TILLMETZ");
  });

  it("kürzt lange Namen von innen (Anfang + Ende bleiben)", () => {
    const out = abbreviateMid("TILLMETZ123456789", 14);
    expect(out.length).toBeLessThanOrEqual(14);
    expect(out.startsWith("TILL")).toBe(true);
    expect(out.endsWith("6789")).toBe(true);
    expect(out).toContain("...");
  });

  it("Beispiel des Users: TILL...METZ-Muster", () => {
    const out = abbreviateMid("TILLMETZMAXMUSTERMANN", 14);
    expect(out).toMatch(/^TILL.../);
    expect(out).toMatch(/...\w+$/);
    expect(out.length).toBeLessThanOrEqual(14);
  });

  it("lange Namen werden stabil kurz (maxLen-Garantie)", () => {
    const long = "X".repeat(200);
    const out = abbreviateMid(long, 16);
    expect(out.length).toBe(16);
    expect(out.startsWith("XXXX")).toBe(true);
    expect(out.endsWith("XXXX")).toBe(true);
  });

  it("Grenzfälle: Leerstring, exakt maxLen", () => {
    expect(abbreviateMid("", 14)).toBe("");
    const exactly = "abcdefghijklmn"; // 14 Zeichen
    expect(abbreviateMid(exactly, 14)).toBe(exactly);
  });
});

describe("fmt-Helfer", () => {
  it("fmtBytes", () => {
    expect(fmtBytes(null)).toBe("—");
    expect(fmtBytes(1500)).toBe("2 KB");
    expect(fmtBytes(2.5e6)).toBe("2.5 MB");
  });

  it("fmtTimecode", () => {
    expect(fmtTimecode(0)).toBe("00:00");
    expect(fmtTimecode(65)).toBe("01:05");
  });
});
