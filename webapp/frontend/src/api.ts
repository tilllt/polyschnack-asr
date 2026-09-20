/* ============================================================
   TYPES
   ============================================================ */

export type RecordingStatus = "uploaded" | "queued" | "processing" | "done" | "failed";

export interface SegmentWord {
  word: string;
  start: number;
  end: number;
  /** Per-Token-Confidence 0.0-1.0 (CrispASR `probability`) — optional, nur
   *  wenn das Backend sie liefert. Fehlt → keine Färbung. */
  confidence?: number;
  /** Change 137 (Timing-Tab): manuell korrigiert (override=true) — ein
   *  späterer Re-Align überschreibt dieses Wort nicht mehr. */
  override?: boolean;
}

export interface Segment {
  start: number;
  end: number;
  text: string;
  speaker?: string;
  words?: SegmentWord[];
}

export interface Recording {
  id: string;
  uid: string;
  original_name: string;
  /** Change 014: editierbarer Titel (Fallback original_name), via PATCH
   *  /recordings/{uid}/title setzbar — Sidecar spiegelt ihn. */
  title?: string | null;
  /** Change 054: freie Tags (PATCH /recordings/{uid}/tags, write-Zugriff). */
  tags?: string[];
  mime: string;
  size_bytes: number;
  duration_s: number | null;
  status: RecordingStatus;
  text: string | null;
  error: string | null;
  processing_ms: number | null;
  // Change 086: Job-Kosten in Cent (null = nicht bepreist; optional für Fixtures).
  cost_cents?: number | null;
  reserved_cents?: number | null;
  created_at: string;
  language: string | null;
  segments: Segment[] | null;
  /** Change 009: manuelle Segment-Aufteilung aktiv (Anzeige nutzt segments
   *  direkt, keine Auto-Re-Segmentierung nach segMaxDuration). */
  segments_manual: boolean;
  audio_url: string;
  /** Schlanke Playback-Preview (64-kbps-MP3) — null solange nicht generiert. */
  audio_preview_url: string | null;
  download_url: string;
  /** Change 015: Backup-ZIP (Audio + Transkript + Timings + Versionen). */
  backup_url: string;
  batch_id: string | null;
  recorded_at: string | null;
  source: string | null;
  enable_vad: boolean;
  vad_mode?: string;  // Change 114: off|edges|all
  enable_diarize: boolean;
  diarize_num_speakers?: number | null;
  diarize_min_duration_off?: number | null;
  diarize_method?: string | null;
  enable_streaming: boolean;
  enable_noise_reduce: boolean;
  enable_enhance: string;
  separate_backend?: string;
  enable_punctuation?: boolean;
  enable_llm_enhance?: boolean;
  prompt_template_id?: number | null;
  delivery_target_id?: number | null;
  delivery_status?: string | null;
  delivery_error?: string | null;
  access_level?: "owner" | "read" | "write" | "full" | "public" | "none";
  is_anon_shared?: boolean;
  /** Change 067-Fix: Owner hat User-Shares vergeben → Kollaboration möglich. */
  has_shares?: boolean;
  shared_with_me?: boolean;
  retention_minutes?: number;
  shared_at?: string | null;
  progress_pct: number;
  /** Phasen-Hinweis während der Verarbeitung, z. B. "diarization" */
  progress_note?: string | null;
  /** Change 187: neutrale Notiz zum Align-Lauf (z.B. Music-Removal nicht möglich). */
  align_note?: string | null;
  /** Change 045: Status des präzisen Alignments (done|pending|running|skipped). */
  alignment?: string;
  /** Change 011: Beginn der aktuellen Phase (ISO) — "Phase läuft seit Xs". */
  phase_started_at?: string | null;
  /** Change 011: Letzter Aktivitäts-Nachweis (ISO) — Heartbeat-Puls. */
  last_heartbeat_at?: string | null;
  /** Change 082: Job-Beginn (ISO) — Basis für „verarbeitet seit Xs". */
  processing_started_at?: string | null;
  /** Change 082: ETA-Rest in Sekunden (Spanne) aus Dauer × RTF — nur
   *  während processing, None ohne bekannte Rate (Anti-Fake). */
  eta_total_s?: number | null;
  eta_low_s?: number | null;
  eta_high_s?: number | null;
  /** Change 011: Queue-Position (nur status="queued"). */
  queue_position?: number | null;
  /** Change 011: Warte-ETA in Sekunden (nur status="queued"). */
  queue_eta_s?: number | null;
  /** Change 011: Backend-Name (nur status="queued"). */
  queue_backend?: string | null;
  /** Change 183: der aktive Job (eine Quelle der Wahrheit) — die
   *  einheitliche Job-Status-UI liest Status/Phase/pct/Zeiten/Cancel
   *  direkt daraus (statt der abgeleiteten Recording-Felder). */
  job?: JobStatusData | null;
  waveform_peaks: number[] | null;
  /** Change 057: Status der Diarization (done|pending|running|failed|skipped). */
  diar_status?: string;
  /** Change 054: letzte Bearbeitung — Basis fürs Sort-Badge „Last edit"
   *  (Backend sortiert; hier für Tooltip/Anzeige). */
  updated_at?: string | null;
  backend?: string;
}

export interface Stats {
  total: number;
  done: number;
  processing: number;
  uploaded: number;
  failed: number;
  total_audio_s: number;
  total_processing_ms: number;
  total_size_bytes: number;
}

export interface ModelStatus {
  vad_available: boolean;
  diarize_available: boolean;
  diar_service: string;
  asr_device: string;
  downloading: Record<string, boolean>;
  download_progress: Record<string, string>;
}

export interface UserInfo {
  anonymous?: boolean;
  authenticated?: boolean;
  oidc_enabled?: boolean;
  sub?: string;
  name?: string;
  retention_minutes?: number;
  preferred_username?: string;
  email?: string;
  is_admin?: boolean;
  groups?: string[];
}

export interface JobStatusData {
  /** Change 183: normiertes Job-Objekt — identisch im Recording-Response
   *  (r.job) und in der Queue-API (QueueJob) — damit BEIDE Anzeigen
   *  dieselbe <JobStatus>-Komponente rendern können. */
  kind?: string;
  status?: string;
  phase?: string | null;
  pct?: number | null;
  started_at?: string | null;
  phase_started_at?: string | null;
  heartbeat_at?: string | null;
  cancel_requested?: boolean;
  error?: string | null;
}

export interface QueueJob {
  job_id: number;
  position: number;
  status: string;
  backend: string;
  eta_s: number | null;
  is_mine: boolean;
  // Change 156: Phase (transcribe|align|rediarize|peaks|vad) + echter
  // Fortschritt — die Queue-Anzeige zeigt damit, was GENAU läuft.
  kind?: string;
  progress_pct?: number | null;
  progress_note?: string | null;
  /** Change 187: neutrale Notiz zum Align-Lauf (z.B. Music-Removal nicht möglich). */
  align_note?: string | null;
  // Change 183: Job-Row-Felder (eine Quelle der Wahrheit)
  phase?: string | null;
  pct?: number | null;
  phase_started_at?: string | null;
  heartbeat_at?: string | null;
  cancel_requested?: boolean;
  error?: string | null;
}

export interface QueueStatus {
  jobs: QueueJob[];
  concurrency: number;
}

export interface AdminService {
  name: string;
  container: string;
  profile: string;
  model: string;
  status: string;
  health: string | null;
  resources: {
    ok: boolean;
    available: Record<string, number | string>;
    missing: Record<string, number>;
    unknown: string[];
    message: string;
  };
  active_jobs: number;
  concurrency: number;
}

export interface AdminConfig {
  default_backend: string;
  effective_backend: string;
  concurrency: number;
  max_queue_len: number;
}

export interface ModelMatrixEntry {
  name: string;
  backend: string;
  model: string;
  type: string;
  status: string;
  /** true=Container läuft, false=gestoppt/nicht angelegt, null=unbekannt (Proxy down) */
  reachable: boolean | null;
  concurrency: number;
  device: string[];
  languages: string[];
  word_timestamps: boolean | string;
  streaming: boolean;
  async_jobs: boolean;
  noise_reduce: boolean;
  vad: string;
  diarization: string;
  enhance: boolean;
  /** Change 138: Backend punktuiert/großschreibt NATIV (CrispASR-Familie,
   *  Whisper) — die UI-Option ist dann ein No-Op und wird ehrlich markiert. */
  native_punctuation?: boolean;
  requires: Record<string, number>;
}

/* ============================================================
   FETCH HELPERS
   ============================================================ */

async function checkOk(res: Response): Promise<Response> {
  if (!res.ok) {
    // Server-Detail-Message durchreichen (z.B. "yt-dlp failed: … 429")
    let detail = "";
    try {
      const body = await res.clone().json();
      if (body && typeof body.detail === "string") detail = body.detail;
    } catch {
      // kein JSON-Body — ignoriere
    }
    // Change 189: Status und Serverstand mitgeben, damit die UI einen
    // Konflikt (409) erkennen und „neu laden" anbieten kann.
    const err = new Error(detail ? `${res.status}: ${detail}` : `HTTP ${res.status}`) as Error & {
      status?: number;
      currentUpdatedAt?: string | null;
    };
    err.status = res.status;
    err.currentUpdatedAt = res.headers.get("X-Current-Updated-At");
    throw err;
  }
  return res;
}

/** Change 054: Sortier-Kriterien der Recording-Liste (Backend-Parameter). */
export type RecordingSort = "date" | "edited" | "name" | "filename" | "length";
export type RecordingSortDir = "asc" | "desc";

export async function fetchRecordings(
  q = "",
  opts: { sort?: RecordingSort | null; dir?: RecordingSortDir; tags?: string[] } = {},
  // Change 059: lite=1 — die Liste liefert nur die Karten-Shell
  // (text/segments/peaks = null); Transkription + Peaks lädt die Karte
  // einzeln über fetchRecording nach.
  lite = true,
  // Change 120: AbortSignal von React Query — abgebrochene Requests
  // (schnelles Umsortieren/Umfiltern) können den Cache nicht mehr
  // überschreiben und belasten das Backend nicht.
  signal?: AbortSignal,
): Promise<Recording[]> {
  const params = new URLSearchParams();
  if (q) params.set("q", q);
  if (opts.sort && opts.dir) {
    params.set("sort", opts.sort);
    params.set("dir", opts.dir);
  }
  for (const tag of opts.tags ?? []) params.append("tag", tag);
  if (lite) params.set("lite", "1");
  const qs = params.toString();
  const res = await fetch(qs ? `/api/recordings?${qs}` : "/api/recordings", {
    signal,
  }).then(checkOk);
  return res.json() as Promise<Recording[]>;
}

/** Change 092: Alle Tags über alle Aufnahmen (Autocomplete-Vorschläge). */
export async function fetchAllTags(): Promise<string[]> {
  const res = await fetch("/api/tags");
  if (!res.ok) throw new Error(`tags: ${res.status}`);
  return res.json() as Promise<string[]>;
}

/** Change 054: Tags einer Aufnahme setzen (Backend dedupt case-insensitiv,
 *  Limits: ≤ 20 Tags, je ≤ 40 Zeichen). */
export async function updateRecordingTags(
  uid: string,
  tags: string[],
): Promise<{ uid: string; tags: string[] }> {
  const res = await fetch(`/api/recordings/${encodeURIComponent(uid)}/tags`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ tags }),
  }).then(checkOk);
  return res.json() as Promise<{ uid: string; tags: string[] }>;
}

/** Change 056: zeitgebundener Kommentar (Annotation) zu einer Transkription. */
export interface Annotation {
  id: number;
  uid: string;
  rec_id: number;
  user_id: number | null;
  user_name: string | null;
  /** Change 056: sub des Autors (Frontend-Autor-Check für Edit/Delete). */
  user_sub: string | null;
  segment_idx: number;
  char_start: number;
  char_end: number;
  start_s: number;
  end_s: number;
  body: string;
  parent_id: number | null;
  created_at: string | null;
  updated_at: string | null;
}

/** Change 155 (Timing-Zoom): progressive Peaks — feinere Auflösung für
 *  den Wort-Zoom (?length=N). Wird vom Browser-Cache bedient
 *  (Cache-Control: public, max-age=86400 — Peaks sind deterministisch). */
export async function fetchPeaks(rid: string, length: number): Promise<number[]> {
  const res = await fetch(
    `/api/recordings/${encodeURIComponent(rid)}/peaks?length=${length}`,
  ).then(checkOk);
  const body = (await res.json()) as { peaks: number[] };
  return body.peaks;
}

/** Change 199: binäres Envelope aus dem Sidecar (uint8, ein Byte pro Bin).
 *
 *  `level="res"` lädt das residente Level komplett (≤ 2 MB) für WaveSurfer,
 *  `level="hi"` ein Byte-Fenster des Detail-Envelopes (1000 Bins/s, per Range
 *  → ein 1-s-Fenster sind ~1 KB). Zur Anfragezeit läuft serverseitig kein
 *  ffmpeg; die Dateien entstehen beim Import.
 *
 *  Wirft nicht bei fehlendem Sidecar — der Aufrufer fällt dann auf das
 *  2000er-JSON zurück (Altaufnahmen ohne Nachlauf). */
export async function fetchPeaksBinary(
  rid: string,
  level: "res" | "hi",
  range?: { start: number; end: number },
): Promise<Uint8Array> {
  const headers: Record<string, string> = {};
  if (range) headers["Range"] = `bytes=${range.start}-${range.end}`;
  const res = await fetch(
    `/api/recordings/${encodeURIComponent(rid)}/peaks.bin?level=${level}`,
    { headers },
  ).then(checkOk);
  return new Uint8Array(await res.arrayBuffer());
}

/** Change 199: uint8-Envelope in die Form bringen, die WaveSurfer erwartet
 *  (float in [0, 1]). Ein Byte pro Bin, 255 = Vollausschlag. */
export function envelopeToPeaks(bytes: Uint8Array): number[] {
  const out = new Array<number>(bytes.length);
  for (let i = 0; i < bytes.length; i += 1) out[i] = bytes[i] / 255;
  return out;
}

/** Change 056: Annotationen einer Aufnahme laden (flach, nach Zeit sortiert). */
export async function fetchAnnotations(rid: string): Promise<Annotation[]> {
  const res = await fetch(`/api/recordings/${encodeURIComponent(rid)}/annotations`).then(checkOk);
  return res.json() as Promise<Annotation[]>;
}

/** Change 056: neue Top-Level-Annotation (write). */
export async function createAnnotation(
  rid: string,
  a: { segment_idx: number; char_start: number; char_end: number; body: string },
): Promise<Annotation> {
  const res = await fetch(`/api/recordings/${encodeURIComponent(rid)}/annotations`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(a),
  }).then(checkOk);
  return res.json() as Promise<Annotation>;
}

/** Change 056: Antwort auf eine Top-Level-Annotation (write). */
export async function replyToAnnotation(aid: number, body: string): Promise<Annotation> {
  const res = await fetch(`/api/annotations/${aid}/replies`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ body }),
  }).then(checkOk);
  return res.json() as Promise<Annotation>;
}

/** Change 056: Body editieren (Autor/Admin). */
export async function updateAnnotation(aid: number, body: string): Promise<Annotation> {
  const res = await fetch(`/api/annotations/${aid}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ body }),
  }).then(checkOk);
  return res.json() as Promise<Annotation>;
}

/** Change 056: Annotation + Antworten löschen (Autor/Admin). */
export async function deleteAnnotation(aid: number): Promise<{ deleted: number; replies_deleted: number }> {
  const res = await fetch(`/api/annotations/${aid}`, {
    method: "DELETE",
  }).then(checkOk);
  return res.json() as Promise<{ deleted: number; replies_deleted: number }>;
}

/** Change 015: verfügbare Export-Templates (Name + Endung) für das Dropdown. */
export interface ExportTemplate {
  name: string;
  extension: string;
}

export async function fetchExportTemplates(): Promise<ExportTemplate[]> {
  const res = await fetch("/api/export-templates").then(checkOk);
  const data = (await res.json()) as { templates?: ExportTemplate[] };
  return data.templates ?? [];
}

/* ---------------------------------------------------------------------------
 * Change 193: ASS-Untertitel-Export (animierte Captions fürs Video).
 * ------------------------------------------------------------------------- */

/** Parameter-Typ laut Backend-Schema (steuert das Bedienelement im Dialog). */
export interface ExportParamSpec {
  type: "int" | "str" | "bool" | "color" | "enum";
  min?: number;
  max?: number;
  values?: string[];
  max_len?: number;
}

export interface ExportPreset {
  name: string;
  title: string;
  description: string;
  description_en?: string;
  description_pt?: string;
  /** Effektive Defaults (globale Defaults + Preset-Überschreibungen). */
  parameters: Record<string, number | string | boolean>;
  /** Nur die Parameter, die diese Vorlage wirklich benutzt. */
  used_params: string[];
}

export interface ExportCatalog {
  presets: ExportPreset[];
  parameter_specs: Record<string, ExportParamSpec>;
  /** false = kein Render-Dienst aktiv (nur ASS-Download). */
  render_available: boolean;
  /** Formate, die der Render-Dienst wirklich kann (nichts geraten). */
  render_formats?: RenderFormat[];
  render_status?: string;
  /** Grund, wenn der Dienst fehlt — wird im Dialog angezeigt. */
  render_note?: string;
}

export async function fetchExportPresets(): Promise<ExportCatalog> {
  const res = await fetch("/api/export/presets").then(checkOk);
  return (await res.json()) as ExportCatalog;
}

/** Fehler mit maschinenlesbarem Code aus dem Backend (409/400/404/503). */
export class AssExportError extends Error {
  code: string;
  hint: string;

  constructor(code: string, hint: string, message?: string) {
    super(message ?? code);
    this.name = "AssExportError";
    this.code = code;
    this.hint = hint;
  }
}

export interface AssExportResult {
  blob: Blob;
  /** Die angefragte API-URL (Preset + Parameter) — für den nativen Download. */
  url: string;
  filename: string;
  preset: string;
  words: number;
  lines: number;
  timing: string;
  warnings: string[];
}

/** Dateiname aus dem Content-Disposition-Header (Fallback: <uid>.ass). */
function filenameFromDisposition(header: string | null, fallback: string): string {
  const m = header?.match(/filename="([^"]+)"/);
  return m ? m[1] : fallback;
}

/**
 * Holt die .ass-Datei als Blob (bewusst per fetch statt <a href>): nur so
 * sind Fehlerstatus (409 „keine Wortzeiten") und die Hinweis-Header
 * (Timing real/mixed, Warnungen) im Dialog sichtbar.
 */
export async function fetchAssExport(
  uid: string,
  preset: string,
  params: Record<string, number | string | boolean>,
): Promise<AssExportResult> {
  const qs = new URLSearchParams({ preset, params: JSON.stringify(params) });
  const url = `/api/recordings/${uid}/export/ass?${qs.toString()}`;
  const res = await fetch(url);
  if (!res.ok) {
    let code = "unknown_error";
    let hint = "";
    let detail = "";
    try {
      const body = await res.json();
      const d = body?.detail;
      if (typeof d === "string") {
        detail = d;
      } else if (d && typeof d === "object") {
        code = d.error ?? code;
        hint = d.hint ?? "";
        detail = d.detail ?? "";
      }
    } catch {
      /* kein JSON-Body */
    }
    throw new AssExportError(code, hint, detail || `HTTP ${res.status}`);
  }
  const blob = await res.blob();
  const warnings = (res.headers.get("X-Polyschnack-Warnings") ?? "")
    .split(",")
    .map((w) => w.trim())
    .filter(Boolean);
  return {
    blob,
    url,
    filename: filenameFromDisposition(
      res.headers.get("Content-Disposition"),
      `${uid}.ass`,
    ),
    preset: res.headers.get("X-Polyschnack-Preset") ?? preset,
    words: Number(res.headers.get("X-Polyschnack-Words") ?? 0),
    lines: Number(res.headers.get("X-Polyschnack-Lines") ?? 0),
    timing: res.headers.get("X-Polyschnack-Timing") ?? "real",
    warnings,
  };
}

/**
 * Datei über die API-URL herunterladen — der Weg, den die übrigen Exporte
 * (TXT/SRT/AUD) schon immer nutzen: der Browser holt die Datei selbst, der
 * Server schickt `Content-Disposition: attachment`.
 *
 * Warum nicht der Blob aus `saveBlob`: ein programmatisch geklickter Anker auf
 * eine `blob:`-URL wird von manchen Browsern (iOS/Safari, PWA-/WebView-Modus,
 * harte Download-Einstellungen) still verworfen. Beobachtet am ASS-Export: der
 * Server lieferte 200 auf `/export/ass`, beim Nutzer kam trotzdem keine Datei an
 * (belegt im Traefik-Zugriffsprotokoll). Erst das Erzeugen der Datei nach dem
 * Laden ist fragil — der Blob wird deshalb nicht mehr zum Speichern benutzt.
 */
export function downloadUrl(url: string, filename: string): void {
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.rel = "noopener";
  a.style.display = "none";
  document.body.appendChild(a);
  a.click();
  // Aufräumen verzögert: sofortiges Entfernen ist in Chromium unproblematisch
  // (gegen einen echten Server geprüft, Datei kommt an), aber ältere Engines
  // brechen einen Download ab, dessen auslösendes Element schon weg ist.
  setTimeout(() => a.remove(), 60_000);
}

/** Blob als Datei speichern (Object-URL wird danach wieder freigegeben). */
export function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 4000);
}

export async function fetchStats(): Promise<Stats> {
  const res = await fetch("/api/stats").then(checkOk);
  return res.json() as Promise<Stats>;
}

export async function fetchModelStatus(): Promise<ModelStatus> {
  const res = await fetch("/api/models/status").then(checkOk);
  return res.json() as Promise<ModelStatus>;
}

export async function fetchMe(): Promise<UserInfo> {
  const res = await fetch("/auth/me").then(checkOk);
  return res.json() as Promise<UserInfo>;
}

export async function triggerDownload(model: "vad" | "diarize"): Promise<{ status: string; message: string }> {
  const res = await fetch(`/api/models/${model}/download`, { method: "POST" }).then(checkOk);
  return res.json() as Promise<{ status: string; message: string }>;
}

export async function transcribeRange(id: string, startSec: number, endSec: number): Promise<Recording> {
  const params = new URLSearchParams({ start_sec: String(startSec), end_sec: String(endSec) });
  const res = await fetch(`/api/recordings/${id}/transcribe-range?${params}`, { method: "POST" }).then(checkOk);
  return res.json() as Promise<Recording>;
}

export async function startTranscription(
  id: string,
  enableVad = false,
  enableDiarize = false,
  enableStreaming = false,
  enableNoiseReduce = true,
  enableEnhance = "off",
  backend = "",
  enablePunctuation = false,
  enableLlmEnhance = false,
  promptTemplateId?: number,
  deliveryTargetId?: number,
  llmEndpointId?: number,
  diarizeNumSpeakers?: number,
  diarizeMinDurationOff?: number,
  diarizeMethod?: string,
  separateBackend = "none",
  vadMode = "off",  // Change 114: off|edges|all
): Promise<Recording> {
  const fd = new FormData();
  fd.append("enable_vad", String(enableVad));
  fd.append("vad_mode", vadMode);  // Change 114
  fd.append("enable_diarize", String(enableDiarize));
  fd.append("enable_streaming", String(enableStreaming));
  fd.append("enable_noise_reduce", String(enableNoiseReduce));
  fd.append("enable_enhance", enableEnhance);
  fd.append("separate_backend", separateBackend);
  fd.append("backend", backend);
  fd.append("enable_punctuation", String(enablePunctuation));
  fd.append("enable_llm_enhance", String(enableLlmEnhance));
  if (promptTemplateId !== undefined) fd.append("prompt_template_id", String(promptTemplateId));
  if (deliveryTargetId !== undefined) fd.append("delivery_target_id", String(deliveryTargetId));
  if (llmEndpointId !== undefined) fd.append("llm_endpoint_id", String(llmEndpointId));
  if (diarizeNumSpeakers !== undefined) fd.append("diarize_num_speakers", String(diarizeNumSpeakers));
  if (diarizeMinDurationOff !== undefined) fd.append("diarize_min_duration_off", String(diarizeMinDurationOff));
  if (diarizeMethod !== undefined) fd.append("diarize_method", diarizeMethod);
  const res = await fetch(`/api/recordings/${id}/transcribe`, { method: "POST", body: fd }).then(checkOk);
  return res.json() as Promise<Recording>;
}

/** Feature 2026-08-16: Text- und/oder Sprecher-Update eines einzelnen Segments.
 *  `speaker` setzt die Sprecher-Zuordnung NUR für dieses Segment (Dropdown);
 *  `text` baut die Wort-Timestamps neu. Beide optional, mindestens eines. */
export async function updateSegment(
  recordingId: string,
  segmentIdx: number,
  text?: string,
  speaker?: string,
): Promise<{ segments: Segment[]; text: string }> {
  const body: Record<string, string> = {};
  if (text !== undefined) body.text = text;
  if (speaker !== undefined) body.speaker = speaker;
  const res = await fetch(`/api/recordings/${recordingId}/segments/${segmentIdx}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }).then(checkOk);
  return res.json();
}

/** Change 137: manuelle Wort-Timing-Korrektur (Timing-Tab). Setzt
 *  start/end GENAU EINES Wortes (+ override=true); `override: false` ohne
 *  start/end entfernt das Override-Flag (Reset). Response = komplette
 *  Segmentliste (wie updateSegment). */
export async function updateWordTiming(
  recordingId: string,
  segmentIdx: number,
  wordIdx: number,
  body: { start?: number; end?: number; override?: boolean; shrink_neighbors?: boolean },
): Promise<{ segments: Segment[]; text: string }> {
  const res = await fetch(
    `/api/recordings/${recordingId}/segments/${segmentIdx}/words/${wordIdx}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
  ).then(checkOk);
  return res.json();
}

/** Change 014: Titel einer Aufnahme umbenennen (Owner/Admin). Schreibt DB +
 *  Sidecar (best-effort) im Backend; Response trägt den neuen Stand. */
export async function updateRecordingTitle(
  recordingId: string,
  title: string,
  signal?: AbortSignal,
): Promise<{ uid: string; title: string; original_name: string }> {
  const res = await fetch(`/api/recordings/${recordingId}/title`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
    signal,
  }).then(checkOk);
  return res.json();
}

/** Feature 2026-08-15: komplette Segmentliste persistieren (Re-Segmentierung
 *  / verschobene Grenzen) — Export nutzt danach dieselben Segmente wie die
 *  Preview. Change 068: createVersion=false (Autosave) → nur DB-Write ohne
 *  TranscriptVersion; die Version entsteht beim Verlassen des Edit-Mode. */
/**
 * Change 189: `expectedUpdatedAt` ist der Stand, den der Client geladen hat.
 * Passt er nicht mehr, antwortet der Server 409 (`stale_write`) und schreibt
 * nichts — der Aufrufer muss den Konflikt sichtbar machen statt blind erneut
 * zu senden.
 */
export async function replaceSegments(
  recordingId: string,
  segments: Segment[],
  createVersion = true,
  expectedUpdatedAt?: string | null,
): Promise<{
  segments: Segment[];
  text: string;
  segments_manual: boolean;
  updated_at?: string;
  /** Change 217: false = der Inhalt war identisch, es wurde NICHTS geschrieben
   *  (kein Fehler, aber auch kein Speichererfolg). */
  changed?: boolean;
  /** Change 217: true nur, wenn wirklich eine neue Version entstanden ist. */
  version_created?: boolean;
}> {
  const qs = createVersion ? "" : "?create_version=false";
  const body: Record<string, unknown> = { segments };
  if (expectedUpdatedAt) body.expected_updated_at = expectedUpdatedAt;
  const res = await fetch(`/api/recordings/${recordingId}/segments${qs}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }).then(checkOk);
  return res.json();
}

/** Change 189: 409 = „zwischenzeitlich geändert"; Aufrufer laden neu. */
export function isStaleWriteError(err: unknown): boolean {
  return !!err && typeof err === "object" && (err as { status?: number }).status === 409;
}

export interface SpeakerRenameResult {
  segments: Segment[];
  text: string;
  renamed: number;
}

export async function renameSpeaker(
  recordingId: string,
  fromSpeaker: string,
  toSpeaker: string,
): Promise<SpeakerRenameResult> {
  const res = await fetch(`/api/recordings/${recordingId}/speaker-rename`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ from_speaker: fromSpeaker, to_speaker: toSpeaker }),
  }).then(checkOk);
  return res.json();
}

export interface AnonLinkResult {
  share_token: boolean;
  shared_at: string | null;
  retention_minutes: number;
  expires_at: string | null;
}

export async function toggleAnonLink(
  recordingId: string,
  enabled: boolean,
): Promise<AnonLinkResult> {
  const res = await fetch(`/api/recordings/${recordingId}/anon-link`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ enabled }),
  }).then(checkOk);
  return res.json();
}

export async function fetchRecording(rid: string): Promise<Recording> {
  const res = await fetch(`/api/recordings/${rid}`).then(checkOk);
  return res.json();
}

export async function uploadRecording(
  file: File,
  batchId: string,
  enableVad = false,
  enableDiarize = false,
  enableStreaming = false,
  enableNoiseReduce = true,
  enableEnhance = "off",
  force = false,
  onProgress?: (pct: number) => void,
  diarizeNumSpeakers?: number,
  diarizeMinDurationOff?: number,
  diarizeMethod?: string,
  separateBackend = "none",
): Promise<Recording | { duplicate: true; existing_id: string; recording: Recording }> {
  const fd = new FormData();
  fd.append("file", file);
  fd.append("batch_id", batchId);
  fd.append("enable_vad", String(enableVad));
  fd.append("enable_diarize", String(enableDiarize));
  fd.append("enable_streaming", String(enableStreaming));
  fd.append("enable_noise_reduce", String(enableNoiseReduce));
  fd.append("enable_enhance", enableEnhance);
  fd.append("separate_backend", separateBackend);
  // Diarization-Tuning (Import-Toggles, 2026-08-14): Backend-Endpoint
  // akzeptiert die Felder, das Frontend schickte sie vorher nie.
  if (diarizeNumSpeakers != null) fd.append("diarize_num_speakers", String(diarizeNumSpeakers));
  if (diarizeMinDurationOff != null) fd.append("diarize_min_duration_off", String(diarizeMinDurationOff));
  if (diarizeMethod) fd.append("diarize_method", diarizeMethod);

  const url = force ? `/api/recordings?force=true` : "/api/recordings";
  if (!onProgress) {
    const res = await fetch(url, { method: "POST", body: fd }).then(checkOk);
    return res.json() as Promise<Recording>;
  }

  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", url);
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) onProgress(Math.round((e.loaded / e.total) * 100));
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(JSON.parse(xhr.responseText));
      } else {
        reject(new Error(`upload failed: ${xhr.status}`));
      }
    };
    xhr.onerror = () => reject(new Error("network error"));
    xhr.send(fd);
  });
}

/**
 * „Upload again" im Duplikat-Dialog: legt eine NEUE Aufnahme aus der bereits
 * vorhandenen Datei an, ohne sie erneut übers Netz zu übertragen (bei
 * 300+-MB-Dateien blieb der Dialog sonst minutenlang bei 100%).
 */
export async function duplicateRecording(rid: string): Promise<Recording> {
  const res = await fetch(`/api/recordings/${rid}/duplicate`, { method: "POST" }).then(checkOk);
  return res.json() as Promise<Recording>;
}

/**
 * Mehrere Aufnahmen zu EINER Datei zusammenführen (ffmpeg concat, Server).
 * Die Einzel-Aufnahmen werden dabei gelöscht — übrig bleibt das gemergte
 * Recording in der angegebenen Reihenfolge.
 */
export async function mergeRecordings(uids: string[], batchId?: string): Promise<Recording> {
  const res = await fetch("/api/recordings/merge", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ uids, batch_id: batchId ?? null }),
  }).then(checkOk);
  return res.json() as Promise<Recording>;
}

export async function importFromUrl(
  url: string,
  enableVad = false,
  enableDiarize = false,
  enableStreaming = false,
  enableNoiseReduce = true,
  enableEnhance = "off",
  diarizeNumSpeakers?: number,
  diarizeMinDurationOff?: number,
  diarizeMethod?: string,
  // Change 080: optionale Anmeldedaten für private/geschützte Videos.
  username?: string,
  password?: string,
  // Vimeo-Stil: Passwort pro Video (--video-password), unabhängig von
  // Account-Login.
  videoPassword?: string,
  cookiesFile?: File | null,
  separateBackend = "none",
  vadMode = "off",  // Change 114: off|edges|all
): Promise<Recording> {
  const fd = new FormData();
  fd.append("url", url);
  fd.append("enable_vad", String(enableVad));
  fd.append("vad_mode", vadMode);  // Change 114
  fd.append("enable_diarize", String(enableDiarize));
  fd.append("enable_streaming", String(enableStreaming));
  fd.append("enable_noise_reduce", String(enableNoiseReduce));
  fd.append("enable_enhance", enableEnhance);
  fd.append("separate_backend", separateBackend);
  if (diarizeNumSpeakers != null) fd.append("diarize_num_speakers", String(diarizeNumSpeakers));
  if (diarizeMinDurationOff != null) fd.append("diarize_min_duration_off", String(diarizeMinDurationOff));
  if (diarizeMethod) fd.append("diarize_method", diarizeMethod);
  // Change 080: Felder NUR bei gesetztem Wert senden (leere Strings würden
  // serverseitig als „halbe Anmeldung" mit 422 abgelehnt). Das Passwort
  // bleibt reiner Request-State — es wird nirgends persistiert.
  if (username) fd.append("username", username);
  if (password) fd.append("password", password);
  if (videoPassword) fd.append("video_password", videoPassword);
  if (cookiesFile) fd.append("cookies", cookiesFile, cookiesFile.name);
  // Kein endloses „Lädt herunter…" ohne Rückmeldung: Server-seitig läuft
  // yt-dlp max. 10 min, aber der User soll nach 5 min einen klaren
  // Timeout-Fehler sehen statt eines hängenden Spinners.
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 300_000);
  try {
    const res = await fetch("/api/recordings/from-url", {
      method: "POST",
      body: fd,
      signal: controller.signal,
    }).then(checkOk);
    return res.json() as Promise<Recording>;
  } catch (e) {
    if ((e as Error)?.name === "AbortError") {
      throw new Error("Download timed out after 5 minutes — please try again");
    }
    throw e;
  } finally {
    clearTimeout(timer);
  }
}

export async function recordFromMic(
  blob: Blob,
  batchId: string,
  enableVad = false,
  enableDiarize = false,
  enableStreaming = false,
  enableNoiseReduce = true,
  enableEnhance = "off",
  onProgress?: (pct: number) => void,
  separateBackend = "none",
): Promise<Recording> {
  const ext = blob.type.includes("mp4") ? ".mp4" : ".webm";
  const fd = new FormData();
  const file = new File([blob], `recording_${Date.now()}${ext}`, { type: blob.type });
  fd.append("file", file);
  fd.append("batch_id", batchId);
  fd.append("enable_vad", String(enableVad));
  fd.append("enable_diarize", String(enableDiarize));
  fd.append("enable_streaming", String(enableStreaming));
  fd.append("enable_noise_reduce", String(enableNoiseReduce));
  fd.append("enable_enhance", enableEnhance);
  fd.append("separate_backend", separateBackend);
  const url = "/api/recordings";
  if (!onProgress) {
    const res = await fetch(url, { method: "POST", body: fd }).then(checkOk);
    return res.json() as Promise<Recording>;
  }
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", url);
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) onProgress(Math.round((e.loaded / e.total) * 100));
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(JSON.parse(xhr.responseText));
      } else {
        reject(new Error(`upload failed: ${xhr.status}`));
      }
    };
    xhr.onerror = () => reject(new Error("network error"));
    xhr.send(fd);
  });
}

export async function deleteRecording(id: string): Promise<void> {
  await fetch(`/api/recordings/${id}`, { method: "DELETE" }).then(checkOk);
}

export async function retranscribeRecording(id: string, opts?: {
  enable_vad?: boolean;
  enable_diarize?: boolean;
  diarize_num_speakers?: number;
  diarize_min_duration_off?: number;
  diarize_method?: string;
  enable_streaming?: boolean;
  enable_noise_reduce?: boolean;
  enable_enhance?: string;
  separate_backend?: string;
  vad_mode?: string;  // Change 114: off|edges|all
  backend?: string;
  enable_punctuation?: boolean;
  enable_llm_enhance?: boolean;
  prompt_template_id?: number;
  delivery_target_id?: number;
}): Promise<Recording> {
  const res = await fetch(`/api/recordings/${id}/retranscribe`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(opts ?? {}),
  }).then(checkOk);
  return res.json() as Promise<Recording>;
}

/** Laufende/wartende Transkription abbrechen (2026-08-15):
 *  POST /api/recordings/{rid}/cancel — queued → uploaded,
 *  processing → Worker stoppt nach aktueller Phase (Status failed). */
export async function cancelRecording(id: string): Promise<{ cancelled: boolean }> {
  const res = await fetch(`/api/recordings/${id}/cancel`, {
    method: "POST",
  }).then(checkOk);
  return res.json() as Promise<{ cancelled: boolean }>;
}

/** Change 046: Re-Alignment auf dem aktuellen (korrigierten) Text.
 *  POST /api/recordings/{rid}/realign — startet den Hintergrund-Worker,
 *  Antwort {id, alignment: "pending"}. Change 113: separates
 *  Music-Removal (separate_backend) wird als Form-Feld mitgesendet. */
export async function realignRecording(
  id: string,
  opts?: { separate_backend?: string },
): Promise<{ id: string; alignment: string }> {
  const fd = new FormData();
  fd.append("separate_backend", opts?.separate_backend ?? "none");
  const res = await fetch(`/api/recordings/${id}/realign`, {
    method: "POST",
    body: fd,
  }).then(checkOk);
  return res.json() as Promise<{ id: string; alignment: string }>;
}

/** Change 057: Re-Diarize — Sprecher-Zuordnung neu berechnen (NUR die
 *  speaker-Felder; Text/Wörter/Zeiten bleiben unangetastet). Läuft im
 *  Hintergrund, Antwort {id, diar_status: "pending"}.
 *  Change 116: optionale Diar-Optionen (numSpeakers, minDurationOff,
 *  method) als Form-Felder — übersteuern die gespeicherten Run-Settings. */
export async function rediarizeRecording(
  id: string,
  opts?: { numSpeakers?: string; minDurationOff?: string; method?: string },
): Promise<{ id: string; diar_status: string }> {
  const fd = new FormData();
  if (opts?.numSpeakers) fd.append("num_speakers", opts.numSpeakers);
  if (opts?.minDurationOff) fd.append("min_duration_off", opts.minDurationOff);
  if (opts?.method) fd.append("method", opts.method);
  const res = await fetch(`/api/recordings/${id}/rediarize`, {
    method: "POST",
    body: fd,
  }).then(checkOk);
  return res.json() as Promise<{ id: string; diar_status: string }>;
}

/* ============================================================
   QUEUE (Task 7)
   ============================================================ */

export async function fetchQueue(): Promise<QueueStatus> {
  const res = await fetch("/api/queue").then(checkOk);
  return res.json() as Promise<QueueStatus>;
}

export async function cancelQueueJob(jobId: number): Promise<void> {
  await fetch(`/api/queue/${jobId}`, { method: "DELETE" }).then(checkOk);
}

/* ============================================================
   ADMIN (Task 8)
   ============================================================ */

export async function fetchAdminServices(): Promise<AdminService[]> {
  const res = await fetch("/api/admin/services").then(checkOk);
  return res.json() as Promise<AdminService[]>;
}

export async function adminServiceAction(name: string, action: "start" | "stop" | "restart"): Promise<{ status: string }> {
  const res = await fetch(`/api/admin/services/${name}/${action}`, { method: "POST" });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const j = await res.json();
      if (j?.detail?.message) detail = j.detail.message;
      else if (typeof j?.detail === "string") detail = j.detail;
    } catch { /* keep HTTP status */ }
    throw new Error(detail);
  }
  return res.json() as Promise<{ status: string }>;
}

export async function fetchAdminConfig(): Promise<AdminConfig> {
  const res = await fetch("/api/admin/config").then(checkOk);
  return res.json() as Promise<AdminConfig>;
}

export interface VacuumResult {
  ok: boolean;
  before_bytes: number;
  after_bytes: number;
  freed_bytes: number;
}

/** SQLite-VACUUM manuell triggern (nur Admin) — gibt gelöschten Platz physisch frei. */
export async function adminVacuum(): Promise<VacuumResult> {
  const res = await fetch("/api/admin/vacuum", { method: "POST" }).then(checkOk);
  return res.json() as Promise<VacuumResult>;
}

export async function putAdminConfig(defaultBackend: string): Promise<{ default_backend: string }> {
  const res = await fetch("/api/admin/config", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ default_backend: defaultBackend }),
  }).then(checkOk);
  return res.json() as Promise<{ default_backend: string }>;
}

export async function resetAdminConfig(): Promise<{ default_backend: string }> {
  const res = await fetch("/api/admin/config/backend", { method: "DELETE" }).then(checkOk);
  return res.json() as Promise<{ default_backend: string }>;
}

export interface EnvSetting {
  name: string;
  key: string;
  value: string;
  source: "env";
}

export async function fetchEnvSettings(): Promise<EnvSetting[]> {
  const res = await fetch("/api/admin/env-settings").then(checkOk);
  const data = (await res.json()) as { settings: EnvSetting[] };
  return data.settings;
}

export async function fetchModelsMatrix(): Promise<ModelMatrixEntry[]> {
  const res = await fetch("/api/models/matrix").then(checkOk);
  return res.json() as Promise<ModelMatrixEntry[]>;
}

/**
 * Backend-Fähigkeiten für das Optionen-Panel (Change 212).
 *
 * Einzige Quelle für alles, was vom Backend abhängt: Live-Erkennung
 * (``streaming_*``) und native Satzzeichen/Großschreibung
 * (``native_punctuation``). Die Werte kommen aus den Adapter-Capabilities —
 * im Frontend wird nichts davon hartkodiert. Schlüssel ``""`` = Server-Default.
 */
export interface BackendCapabilities {
  /** Backends, die der Server als aktiv führt (status active). */
  backends: string[];
  /** Effektives Backend ohne explizite Wahl (auch der Schlüssel ""). */
  default: string;
  /** Live-Erkennung des Server-Defaults. */
  streaming_supported: boolean;
  /** Live-Erkennung je Backend-Name ("" = Server-Default). */
  streaming_by_backend: Record<string, boolean>;
  /** Native Satzzeichen/Großschreibung je Backend-Name ("" = Server-Default). */
  native_punctuation: Record<string, boolean>;
}

export async function fetchBackendCapabilities(): Promise<BackendCapabilities> {
  const res = await fetch("/api/backends").then(checkOk);
  return res.json() as Promise<BackendCapabilities>;
}

/* ============================================================
   Post-Processing (Teil D): Prompt-Templates + Delivery-Targets
   ============================================================ */

export interface PromptTemplate {
  template_id: number;
  name: string;
  prompt: string;
}

export interface DeliveryTargetItem {
  target_id: number;
  name: string;
  kind: "email" | "webdav";
  config: Record<string, string>;
}

export async function fetchTemplates(): Promise<PromptTemplate[]> {
  const res = await fetch("/api/templates").then(checkOk);
  return res.json() as Promise<PromptTemplate[]>;
}

export async function createTemplate(name: string, prompt: string): Promise<PromptTemplate> {
  const res = await fetch("/api/templates", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, prompt }),
  }).then(checkOk);
  return res.json() as Promise<PromptTemplate>;
}

export async function updateTemplate(templateId: number, patch: { name?: string; prompt?: string }): Promise<PromptTemplate> {
  const res = await fetch(`/api/templates/${templateId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  }).then(checkOk);
  return res.json() as Promise<PromptTemplate>;
}

export async function deleteTemplate(templateId: number): Promise<void> {
  await fetch(`/api/templates/${templateId}`, { method: "DELETE" }).then(checkOk);
}

export async function fetchTargets(): Promise<DeliveryTargetItem[]> {
  const res = await fetch("/api/targets").then(checkOk);
  return res.json() as Promise<DeliveryTargetItem[]>;
}

export async function createTarget(name: string, kind: "email" | "webdav", config: Record<string, string>): Promise<DeliveryTargetItem> {
  const res = await fetch("/api/targets", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, kind, config }),
  }).then(checkOk);
  return res.json() as Promise<DeliveryTargetItem>;
}

export async function deleteTarget(targetId: number): Promise<void> {
  await fetch(`/api/targets/${targetId}`, { method: "DELETE" }).then(checkOk);
}

/* ============================================================
   BYOK (Teil E): eigene LLM-Endpunkte
   ============================================================ */

export interface LlmEndpoint {
  endpoint_id: number;
  name: string;
  base_url: string;
  model: string;
}

export async function fetchLlmEndpoints(): Promise<LlmEndpoint[]> {
  const res = await fetch("/api/llm-endpoints").then(checkOk);
  return res.json() as Promise<LlmEndpoint[]>;
}

export async function createLlmEndpoint(body: { name: string; base_url: string; api_key: string; model?: string }): Promise<LlmEndpoint> {
  const res = await fetch("/api/llm-endpoints", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }).then(checkOk);
  return res.json() as Promise<LlmEndpoint>;
}

export async function deleteLlmEndpoint(endpointId: number): Promise<void> {
  await fetch(`/api/llm-endpoints/${endpointId}`, { method: "DELETE" }).then(checkOk);
}

/* ============================================================
   Shares (Teil A)
   ============================================================ */

export interface ShareItem {
  share_id: number;
  user: number;
  user_name: string | null;
  level: "read" | "write" | "full";
  created_at: string;
}

export async function fetchShares(recUid: string): Promise<ShareItem[]> {
  const res = await fetch(`/api/recordings/${recUid}/shares`).then(checkOk);
  return res.json() as Promise<ShareItem[]>;
}

export async function createShare(recUid: string, user: string, level: "read" | "write" | "full"): Promise<{ share_id: number }> {
  const res = await fetch(`/api/recordings/${recUid}/shares`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user, level }),
  }).then(checkOk);
  return res.json() as Promise<{ share_id: number }>;
}

export async function deleteShare(recUid: string, shareId: number): Promise<void> {
  await fetch(`/api/recordings/${recUid}/shares/${shareId}`, { method: "DELETE" }).then(checkOk);
}

/* ============================================================
   Versionen (Teil A)
   ============================================================ */

export interface VersionItem {
  version_no: number;
  kind: string;
  backend: string | null;
  language: string | null;
  created_at: string;
  /** Change 163: Neustart (transcribe/retranscribe/restore) = vollständig
   *  neue Basis ohne Diff zur Vorgängerin. */
  restart?: boolean;
}

export async function fetchVersions(recUid: string): Promise<VersionItem[]> {
  const res = await fetch(`/api/recordings/${recUid}/versions`).then(checkOk);
  return res.json() as Promise<VersionItem[]>;
}

export async function fetchVersionDiff(recUid: string, vNo: number, from?: number): Promise<{ from: number | null; to: number; diff: unknown[] }> {
  const q = from !== undefined ? `?frm=${from}` : "";
  const res = await fetch(`/api/recordings/${recUid}/versions/${vNo}/diff${q}`).then(checkOk);
  return res.json() as Promise<{ from: number | null; to: number; diff: unknown[] }>;
}

export async function restoreVersion(recUid: string, vNo: number): Promise<{ restored: number }> {
  const res = await fetch(`/api/recordings/${recUid}/versions/${vNo}/restore`, { method: "POST" }).then(checkOk);
  return res.json() as Promise<{ restored: number }>;
}

/* ============================================================
   API-Keys (programmatische Nutzung)
   ============================================================ */

export interface ApiKeyItem {
  key_id: number;
  name: string;
  description: string | null;
  level: "read" | "write" | "full";
  expires_at: string | null;
  expired: boolean;
  created_at: string;
  last_used_at: string | null;
}

export interface ApiKeyCreated extends ApiKeyItem {
  token: string; // nur beim Erstellen sichtbar
}

export async function fetchApiKeys(): Promise<ApiKeyItem[]> {
  const res = await fetch("/api/keys").then(checkOk);
  return res.json() as Promise<ApiKeyItem[]>;
}

export async function createApiKey(body: {
  name: string;
  description?: string;
  level: "read" | "write" | "full";
  expires_at?: string | null; // ISO oder null → Default 1 Jahr
}): Promise<ApiKeyCreated> {
  const res = await fetch("/api/keys", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }).then(checkOk);
  return res.json() as Promise<ApiKeyCreated>;
}

export async function deleteApiKey(keyId: number): Promise<void> {
  await fetch(`/api/keys/${keyId}`, { method: "DELETE" }).then(checkOk);
}

/* ============================================================
   CREDITS & MONETARISIERUNG (Change 086)
   ============================================================ */

export interface MyCredits {
  credits_cents: number;
  tier: string;
  balance_eur: number;
  entries: CreditLedgerEntry[];
}

export interface CreditLedgerEntry {
  id: number;
  user_id: number | null;
  delta_cents: number;
  reason: string;
  ref_id: number | null;
  created_at: string | null;
  created_by?: number | null;
}

export interface AdminCreditUser {
  user_id: number;
  name: string | null;
  tier: string;
  credits_cents: number;
  spent_cents: number;
}

export interface CostingSummary {
  topup_cents: number;
  cost_cents: number;
  net_cents: number;
  priced_jobs: number;
}

/** Eigener Kontostand + letzte Buchungen (eingeloggt). */
export async function fetchMyCredits(): Promise<MyCredits> {
  const res = await fetch("/api/account/credits").then(checkOk);
  return res.json() as Promise<MyCredits>;
}

/** Admin: alle User mit Guthaben/Tier/Verbrauch. */
export async function fetchAdminCreditUsers(): Promise<AdminCreditUser[]> {
  const res = await fetch("/api/admin/credits/users").then(checkOk);
  return res.json() as Promise<AdminCreditUser[]>;
}

/** Admin: virtuelles Guthaben erhöhen. */
export async function adminTopup(userId: number, amountCents: number, reason = "topup"): Promise<{ ok: boolean; credits_cents: number | null }> {
  const res = await fetch("/api/admin/credits/topup", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_id: userId, amount_cents: amountCents, reason }),
  }).then(checkOk);
  return res.json() as Promise<{ ok: boolean; credits_cents: number | null }>;
}

/** Admin: Tier setzen (free|paid|test). */
export async function adminSetTier(userId: number, tier: string): Promise<{ ok: boolean; tier: string }> {
  const res = await fetch("/api/admin/credits/tier", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_id: userId, tier }),
  }).then(checkOk);
  return res.json() as Promise<{ ok: boolean; tier: string }>;
}

/** Admin: Journal (letzte Buchungen, optional je User). */
export async function fetchAdminLedger(userId?: number, limit = 100): Promise<CreditLedgerEntry[]> {
  const q = new URLSearchParams();
  if (userId !== undefined) q.set("user_id", String(userId));
  q.set("limit", String(limit));
  const res = await fetch(`/api/admin/credits/ledger?${q}`).then(checkOk);
  return res.json() as Promise<CreditLedgerEntry[]>;
}

/** Admin: Einnahmen vs. Instanzkosten. */
export async function fetchCostingSummary(): Promise<CostingSummary> {
  const res = await fetch("/api/admin/costing/summary").then(checkOk);
  return res.json() as Promise<CostingSummary>;
}

/** Cent → „1,23 €" (User-sichtbar). */
export function formatCents(cents: number | null | undefined): string {
  if (cents === null || cents === undefined) return "–";
  return (cents / 100).toLocaleString("de-DE", {
    style: "currency",
    currency: "EUR",
  });
}

/* --------------------------------------------------------------------------
 * Change 200 — Video-Export über den optionalen Render-Dienst (ps-render)
 * ------------------------------------------------------------------------ */

export interface RenderFormat {
  id: string;
  label: string;
  ext: string;
  mime: string;
  alpha: boolean;
  note: string;
}

export interface RenderJob {
  id: string;
  format: string;
  state: "queued" | "running" | "done" | "failed" | "canceled";
  /** 0…1 aus ffmpeg — 0 heißt „noch nichts gerechnet", nicht „gleich fertig". */
  progress: number;
  filename: string;
  size_bytes: number;
  error: string;
}

export interface RenderStartResult extends RenderJob {
  duration_s: number;
  width: number;
  height: number;
  format_label: string;
  audio: boolean;
}

/** Fehlerkörper der Export-Endpunkte in eine AssExportError übersetzen. */
async function exportFailure(res: Response): Promise<AssExportError> {
  let code = "unknown_error";
  let hint = "";
  let detail = "";
  try {
    const body = await res.json();
    const d = body?.detail;
    if (typeof d === "string") {
      detail = d;
    } else if (d && typeof d === "object") {
      code = d.error ?? code;
      hint = d.hint ?? "";
      detail = d.detail ?? "";
    }
  } catch {
    /* kein JSON-Body */
  }
  return new AssExportError(code, hint, detail || `HTTP ${res.status}`);
}

export async function startRender(
  uid: string,
  body: {
    preset: string;
    params: Record<string, number | string | boolean>;
    format: string;
    fps?: number;
    width?: number;
    height?: number;
    background?: string;
    crf?: number;
    include_audio?: boolean;
  },
): Promise<RenderStartResult> {
  const res = await fetch(`/api/recordings/${uid}/export`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mode: "render", ...body }),
  });
  if (!res.ok) throw await exportFailure(res);
  return (await res.json()) as RenderStartResult;
}

export async function fetchRenderJob(uid: string, jobId: string): Promise<RenderJob> {
  const res = await fetch(`/api/recordings/${uid}/export/jobs/${jobId}`);
  if (!res.ok) throw await exportFailure(res);
  return (await res.json()) as RenderJob;
}

export async function cancelRenderJob(uid: string, jobId: string): Promise<RenderJob> {
  const res = await fetch(`/api/recordings/${uid}/export/jobs/${jobId}`, { method: "DELETE" });
  if (!res.ok) throw await exportFailure(res);
  return (await res.json()) as RenderJob;
}

/** Download-URL der fertigen Datei — Anker darauf, kein Blob (s. downloadUrl). */
export function renderFileUrl(uid: string, jobId: string): string {
  return `/api/recordings/${uid}/export/jobs/${jobId}/file`;
}
