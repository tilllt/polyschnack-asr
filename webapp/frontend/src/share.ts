/* ============================================================
   SHARE — Anon-Link-URL-Helfer
   ============================================================ */

export interface ShareLinkInfo {
  uid: string;
  retentionMinutes: number;
  expiresAt: string | null;
}

/**
 * Parst den /r/:uid-Pfad → { uid } oder null.
 * Der uid ist ein 32-Zeichen-Hex (uuid4().hex) — wir akzeptieren
 * nur exakt dieses Format, damit keine beliebigen Pfade als Share
 * interpretiert werden.
 */
export function parseSharePath(path: string): { uid: string } | null {
  const m = /^\/r\/([0-9a-f]{32})$/i.exec(path);
  if (!m) return null;
  return { uid: m[1] };
}

/** Baut die Share-URL für einen UID (aktueller Origin). */
export function buildShareUrl(uid: string): string {
  const origin =
    typeof window !== "undefined"
      ? window.location.origin
      : globalThis.location?.origin ?? "http://localhost";
  return `${origin}/r/${uid}`;
}

/**
 * Formatiert die Ablaufzeit als menschenlesbaren Countdown/Hinweis.
 * z.B. "noch 12 Minuten gültig" — auf Deutsch (App-Sprache).
 */
export function formatExpiry(
  expiresAt: string | null,
  retentionMinutes: number,
  now: number = Date.now(),
): string {
  if (!expiresAt) {
    return `ca. ${retentionMinutes} Min.`;
  }
  const ms = new Date(expiresAt).getTime() - now;
  if (ms <= 0) return "abgelaufen";
  const mins = Math.max(1, Math.round(ms / 60000));
  if (mins >= 60) {
    const h = Math.round(mins / 60);
    return `noch ${h} Std.`;
  }
  return `noch ${mins} Min.`;
}
