/* ============================================================
   TYPES
   ============================================================ */

export type RecordingStatus = "processing" | "done" | "failed";

export interface Segment {
  start: number;
  end: number;
  text: string;
  speaker?: string;
}

export interface Recording {
  id: number;
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
}

export interface Stats {
  total: number;
  done: number;
  processing: number;
  failed: number;
  total_audio_s: number;
  total_processing_ms: number;
}

export interface ModelStatus {
  vad_available: boolean;
  diarize_available: boolean;
  hf_token: boolean;
  downloading: Record<string, boolean>;
  download_progress: Record<string, string>;
}

export interface UserInfo {
  anonymous?: boolean;
  authenticated?: boolean;
  sub?: string;
  name?: string;
  preferred_username?: string;
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

export async function uploadRecording(
  file: File,
  batchId: string,
  enableVad = false,
  enableDiarize = false,
): Promise<Recording> {
  const fd = new FormData();
  fd.append("file", file);
  fd.append("batch_id", batchId);
  fd.append("enable_vad", String(enableVad));
  fd.append("enable_diarize", String(enableDiarize));
  const res = await fetch("/api/recordings", {
    method: "POST",
    body: fd,
  }).then(checkOk);
  return res.json() as Promise<Recording>;
}

export async function deleteRecording(id: number): Promise<void> {
  await fetch(`/api/recordings/${id}`, { method: "DELETE" }).then(checkOk);
}

export async function retranscribeRecording(id: number): Promise<Recording> {
  const res = await fetch(`/api/recordings/${id}/retranscribe`, {
    method: "POST",
  }).then(checkOk);
  return res.json() as Promise<Recording>;
}
