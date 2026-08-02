import type { ModelMatrixEntry } from "./api";

/**
 * Welche Backends in der Auswahl erscheinen:
 * - Admin: alle aktiven (Backend auto-startet nicht laufende beim Transcribe)
 * - Anon: nur laufende (reachable === true; null = Proxy down → nur Default bleibt)
 */
export function filterAvailableBackends(
  matrix: ModelMatrixEntry[],
  isAdmin: boolean,
): string[] {
  return matrix
    .filter((m) => m.status === "active")
    .filter((m) => isAdmin || m.reachable === true)
    .map((m) => m.name);
}
