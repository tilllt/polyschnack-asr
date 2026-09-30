/**
 * Change 236 — serverweite Konfiguration wird EINMAL je Seite geladen.
 *
 * Befund (KI-Box, 30.09.2026, gemessen im Server-Protokoll): Die Liste baut
 * jede Aufnahme als eigene Karte auf. Jede Karte holte für sich sieben
 * serverweite Auskünfte (Modell-Matrix, Backend-Fähigkeiten, Modell-Status,
 * Vorlagen, Format-Vorgaben, Zustellziele, LLM-Adressen), die für alle Karten
 * identisch sind, plus je Karte die Export-Vorlagen. Bei 116 Aufnahmen feuerte
 * ein Seitenaufruf damit ~812 Abfragen in 24 s (Spitze 111/s). Folgen: Last
 * der Box bis 16 (normal 1–4), Netzwerk-Unterbrechungen 5 % → 17,5 %, der Tab
 * war eine halbe Minute nur mit Abfragen beschäftigt („Seite hängt").
 *
 * Lösung: `once()` teilt eine laufende oder frisch abgeschlossene Abfrage
 * zwischen allen Aufrufern. Alle Karten, die im selben Moment aufbauen,
 * bekommen dieselbe Zusage — aus ~812 Abfragen werden 7.
 *
 * Bewusst schlicht gehalten (kein Umbau der Karten auf einen Daten-Cache):
 * Die Karten behalten ihre Zustandsfelder und ihr Vorgehen, getauscht wird nur
 * die Quelle. Ein Ablauf von 30 s hält die Auskünfte frisch genug (sie wurden
 * bisher ohnehin nur beim Aufbau der Karte gelesen).
 *
 * Fehler werden NICHT gemerkt: schlägt eine Abfrage fehl, versucht es der
 * nächste Aufruf erneut — die Karten haben eigene Rückfallwerte.
 */
import {
  fetchBackendCapabilities,
  fetchExportTemplates,
  fetchFormatPresets,
  fetchLlmEndpoints,
  fetchModelsMatrix,
  fetchModelStatus,
  fetchTargets,
  fetchTemplates,
} from "./api";

/** Wie lange eine einmal geholte Auskunft für weitere Karten gilt. */
export const SHARED_CONFIG_TTL_MS = 30_000;

interface Slot {
  startedAt: number;
  value: Promise<unknown>;
}

const slots = new Map<string, Slot>();

/**
 * Führt `load` höchstens einmal je Schlüssel und Ablaufzeit aus und gibt allen
 * Aufrufern dieselbe Zusage zurück.
 */
export function once<T>(key: string, load: () => Promise<T>, ttlMs: number = SHARED_CONFIG_TTL_MS): Promise<T> {
  const now = Date.now();
  const hit = slots.get(key);
  if (hit && now - hit.startedAt < ttlMs) return hit.value as Promise<T>;

  const value: Promise<T> = load().catch((err) => {
    // Kein Fehler-Gedächtnis: sonst bliebe eine kaputte Abfrage bis zu 30 s
    // bestehen und alle folgenden Karten erbten den Fehler.
    if (slots.get(key)?.value === value) slots.delete(key);
    throw err;
  });
  slots.set(key, { startedAt: now, value });
  return value;
}

/** Geteiltenspeicher leeren (Tests, erzwungene Neuladung). */
export function forgetSharedConfig(prefix?: string): void {
  if (!prefix) {
    slots.clear();
    return;
  }
  for (const key of [...slots.keys()]) {
    if (key.startsWith(prefix)) slots.delete(key);
  }
}

/** Nur für Prüfungen: welche Schlüssel liegen gerade im Geteiltenspeicher? */
export function sharedConfigKeys(): string[] {
  return [...slots.keys()];
}

/** Die serverweiten Auskünfte, die jede Aufnahmekarte braucht. */
export const sharedConfig = {
  modelsMatrix: () => once("models-matrix", fetchModelsMatrix),
  backendCapabilities: () => once("backend-capabilities", fetchBackendCapabilities),
  modelStatus: () => once("model-status", fetchModelStatus),
  templates: () => once("templates", fetchTemplates),
  formatPresets: () => once("format-presets", fetchFormatPresets),
  targets: () => once("targets", fetchTargets),
  llmEndpoints: () => once("llm-endpoints", fetchLlmEndpoints),
  exportTemplates: () => once("export-templates", fetchExportTemplates),
};
