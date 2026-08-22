/* ============================================================
   FORMAT HELPERS
   ============================================================ */

export function fmtBytes(b: number | null | undefined): string {
  if (b == null) return "—";
  return b > 1e6 ? (b / 1e6).toFixed(1) + " MB" : Math.round(b / 1e3) + " KB";
}

/** Duration in seconds → mm:ss (for segment timestamps) */
export function fmtTimecode(s: number): string {
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
}

/** Duration in seconds → "Xm Ys" or "X.Xs" (for card meta) */
export function fmtDurSec(s: number | null | undefined): string {
  if (s == null || isNaN(s)) return "—";
  const m = Math.floor(s / 60);
  const sec = Math.round(s % 60);
  return m > 0 ? `${m}m ${sec}s` : `${s.toFixed(1)}s`;
}

/** Large duration (stats header) → "Xh Ym" / "Xm Ys" / "Xs" */
export function fmtTotalDur(sec: number | null | undefined): string {
  if (sec == null || isNaN(sec)) return "—";
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = Math.round(sec % 60);
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

/** Processing milliseconds → "1.2s" or "320ms" */
export function fmtMs(ms: number | null | undefined): string {
  if (ms == null) return "";
  return ms >= 1000 ? (ms / 1000).toFixed(1) + "s" : Math.round(ms) + "ms";
}

/** ISO string → UTC epoch ms. Naive Strings (ohne Z/Offset, z.B. Backend
 *  vor Change 081) werden als UTC interpretiert — nie als Lokalzeit. */
export function parseUtcMs(iso: string): number {
  const hasOffset = /(Z|[+-]\d{2}:\d{2})$/.test(iso);
  return new Date(hasOffset ? iso : iso + "Z").getTime();
}

/** ISO string → locale date/time pt-BR */
export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    return new Date(parseUtcMs(iso)).toLocaleString("pt-BR", {
      dateStyle: "short",
      timeStyle: "short",
    });
  } catch {
    return iso;
  }
}

/** ISO string → HH:MM for WhatsApp group time range display */
export function fmtHHMM(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    return new Date(parseUtcMs(iso)).toLocaleTimeString("pt-BR", {
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return "—";
  }
}

/**
 * Mid-Ellipsis: kürzt lange Namen VON INNEN, z. B. "TILL...METZ" —
 * Anfang und Ende bleiben erkennbar, die Gesamtlänge ist stabil
 * (maxLen inkl. "...").
 */
export function abbreviateMid(name: string, maxLen = 16): string {
  if (name.length <= maxLen) return name;
  const budget = Math.max(6, maxLen - 3); // Platz für "..."
  const headLen = Math.ceil(budget / 2);
  const tailLen = budget - headLen;
  return `${name.slice(0, headLen)}...${name.slice(-tailLen)}`;
}
