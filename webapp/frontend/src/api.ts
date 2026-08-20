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
  mime: string;
  size_bytes: number;
  duration_s: number | null;
  status: RecordingStatus;
  text: string | null;
  error: string | null;
  processing_ms: number | null;
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
  enable_diarize: boolean;
  diarize_num_speakers?: number | null;
  diarize_min_duration_off?: number | null;
  diarize_method?: string | null;
  enable_streaming: boolean;
  enable_noise_reduce: boolean;
  enable_enhance: string;
  enable_punctuation?: boolean;
  enable_llm_enhance?: boolean;
  prompt_template_id?: number | null;
  delivery_target_id?: number | null;
  delivery_status?: string | null;
  delivery_error?: string | null;
  access_level?: "owner" | "read" | "write" | "full" | "public" | "none";
  is_anon_shared?: boolean;
  shared_with_me?: boolean;
  retention_minutes?: number;
  shared_at?: string | null;
  progress_pct: number;
  /** Phasen-Hinweis während der Verarbeitung, z. B. "diarization" */
  progress_note?: string | null;
  /** Change 045: Status des präzisen Alignments (done|pending|running|skipped). */
  alignment?: string;
  /** Change 011: Beginn der aktuellen Phase (ISO) — "Phase läuft seit Xs". */
  phase_started_at?: string | null;
  /** Change 011: Letzter Aktivitäts-Nachweis (ISO) — Heartbeat-Puls. */
  last_heartbeat_at?: string | null;
  /** Change 011: Queue-Position (nur status="queued"). */
  queue_position?: number | null;
  /** Change 011: Warte-ETA in Sekunden (nur status="queued"). */
  queue_eta_s?: number | null;
  /** Change 011: Backend-Name (nur status="queued"). */
  queue_backend?: string | null;
  waveform_peaks: number[] | null;
  /** Letzter Fortschritts-Heartbeat (ISO) — Basis fuer die ETA-Rate. */
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

export interface QueueJob {
  job_id: number;
  position: number;
  status: string;
  backend: string;
  eta_s: number | null;
  is_mine: boolean;
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
    throw new Error(detail ? `${res.status}: ${detail}` : `HTTP ${res.status}`);
  }
  return res;
}

export async function fetchRecordings(q = ""): Promise<Recording[]> {
  const url = q
    ? `/api/recordings?q=${encodeURIComponent(q)}`
    : "/api/recordings";
  const res = await fetch(url).then(checkOk);
  return res.json() as Promise<Recording[]>;
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
): Promise<Recording> {
  const fd = new FormData();
  fd.append("enable_vad", String(enableVad));
  fd.append("enable_diarize", String(enableDiarize));
  fd.append("enable_streaming", String(enableStreaming));
  fd.append("enable_noise_reduce", String(enableNoiseReduce));
  fd.append("enable_enhance", enableEnhance);
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
 *  Preview. */
export async function replaceSegments(
  recordingId: string,
  segments: Segment[],
): Promise<{ segments: Segment[]; text: string; segments_manual: boolean }> {
  const res = await fetch(`/api/recordings/${recordingId}/segments`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ segments }),
  }).then(checkOk);
  return res.json();
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
): Promise<Recording | { duplicate: true; existing_id: string; recording: Recording }> {
  const fd = new FormData();
  fd.append("file", file);
  fd.append("batch_id", batchId);
  fd.append("enable_vad", String(enableVad));
  fd.append("enable_diarize", String(enableDiarize));
  fd.append("enable_streaming", String(enableStreaming));
  fd.append("enable_noise_reduce", String(enableNoiseReduce));
  fd.append("enable_enhance", enableEnhance);
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
): Promise<Recording> {
  const fd = new FormData();
  fd.append("url", url);
  fd.append("enable_vad", String(enableVad));
  fd.append("enable_diarize", String(enableDiarize));
  fd.append("enable_streaming", String(enableStreaming));
  fd.append("enable_noise_reduce", String(enableNoiseReduce));
  fd.append("enable_enhance", enableEnhance);
  if (diarizeNumSpeakers != null) fd.append("diarize_num_speakers", String(diarizeNumSpeakers));
  if (diarizeMinDurationOff != null) fd.append("diarize_min_duration_off", String(diarizeMinDurationOff));
  if (diarizeMethod) fd.append("diarize_method", diarizeMethod);
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
