/* ============================================================
   TYPES
   ============================================================ */

export type RecordingStatus = "uploaded" | "queued" | "processing" | "done" | "failed";

export interface Segment {
  start: number;
  end: number;
  text: string;
  speaker?: string;
  words?: { word: string; start: number; end: number }[];
}

export interface Recording {
  id: string;
  uid: string;
  original_name: string;
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
  audio_url: string;
  download_url: string;
  batch_id: string | null;
  recorded_at: string | null;
  source: string | null;
  enable_vad: boolean;
  enable_diarize: boolean;
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
  progress_pct: number;
  waveform_peaks: number[] | null;
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
}

export interface ModelStatus {
  vad_available: boolean;
  diarize_available: boolean;
  hf_token: boolean;
  asr_device: string;
  downloading: Record<string, boolean>;
  download_progress: Record<string, string>;
}

export interface UserInfo {
  anonymous?: boolean;
  authenticated?: boolean;
  sub?: string;
  name?: string;
  preferred_username?: string;
  is_admin?: boolean;
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
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res;
}

export async function fetchRecordings(q = ""): Promise<Recording[]> {
  const url = q
    ? `/api/recordings?q=${encodeURIComponent(q)}`
    : "/api/recordings";
  const res = await fetch(url).then(checkOk);
  return res.json() as Promise<Recording[]>;
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
  const res = await fetch(`/api/recordings/${id}/transcribe`, { method: "POST", body: fd }).then(checkOk);
  return res.json() as Promise<Recording>;
}

export async function updateSegment(recordingId: string, segmentIdx: number, text: string):
  Promise<{ segments: Segment[]; text: string }> {
  const res = await fetch(`/api/recordings/${recordingId}/segments/${segmentIdx}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  }).then(checkOk);
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
): Promise<Recording | { duplicate: true; existing_id: string; recording: Recording }> {
  const fd = new FormData();
  fd.append("file", file);
  fd.append("batch_id", batchId);
  fd.append("enable_vad", String(enableVad));
  fd.append("enable_diarize", String(enableDiarize));
  fd.append("enable_streaming", String(enableStreaming));
  fd.append("enable_noise_reduce", String(enableNoiseReduce));
  fd.append("enable_enhance", enableEnhance);

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

export async function importFromUrl(
  url: string,
  enableVad = false,
  enableDiarize = false,
  enableStreaming = false,
  enableNoiseReduce = true,
  enableEnhance = "off",
): Promise<Recording> {
  const fd = new FormData();
  fd.append("url", url);
  fd.append("enable_vad", String(enableVad));
  fd.append("enable_diarize", String(enableDiarize));
  fd.append("enable_streaming", String(enableStreaming));
  fd.append("enable_noise_reduce", String(enableNoiseReduce));
  fd.append("enable_enhance", enableEnhance);
  const res = await fetch("/api/recordings/from-url", { method: "POST", body: fd }).then(checkOk);
  return res.json() as Promise<Recording>;
}

export async function recordFromMic(
  blob: Blob,
  batchId: string,
  enableVad = false,
  enableDiarize = false,
  enableStreaming = false,
  enableNoiseReduce = true,
  enableEnhance = "off",
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
  const res = await fetch("/api/recordings", { method: "POST", body: fd }).then(checkOk);
  return res.json() as Promise<Recording>;
}

export async function deleteRecording(id: string): Promise<void> {
  await fetch(`/api/recordings/${id}`, { method: "DELETE" }).then(checkOk);
}

export async function retranscribeRecording(id: string, opts?: {
  enable_vad?: boolean;
  enable_diarize?: boolean;
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
