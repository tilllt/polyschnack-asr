/* ============================================================
   TYPES
   ============================================================ */

export type RecordingStatus = "uploaded" | "processing" | "done" | "failed";

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
  enable_streaming: boolean;
  progress_pct: number;
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

export async function transcribeRange(id: number, startSec: number, endSec: number): Promise<Recording> {
  const params = new URLSearchParams({ start_sec: String(startSec), end_sec: String(endSec) });
  const res = await fetch(`/api/recordings/${id}/transcribe-range?${params}`, { method: "POST" }).then(checkOk);
  return res.json() as Promise<Recording>;
}

export async function startTranscription(id: number): Promise<Recording> {
  const res = await fetch(`/api/recordings/${id}/transcribe`, { method: "POST" }).then(checkOk);
  return res.json() as Promise<Recording>;
}

export async function uploadRecording(
  file: File,
  batchId: string,
  enableVad = false,
  enableDiarize = false,
  enableStreaming = false,
  onProgress?: (pct: number) => void,
): Promise<Recording> {
  const fd = new FormData();
  fd.append("file", file);
  fd.append("batch_id", batchId);
  fd.append("enable_vad", String(enableVad));
  fd.append("enable_diarize", String(enableDiarize));
  fd.append("enable_streaming", String(enableStreaming));

  // Use XHR for progress tracking; fall back to fetch if unavailable
  if (!onProgress) {
    const res = await fetch("/api/recordings", { method: "POST", body: fd }).then(checkOk);
    return res.json() as Promise<Recording>;
  }

  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/recordings");
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) onProgress(Math.round((e.loaded / e.total) * 100));
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(JSON.parse(xhr.responseText) as Recording);
      } else {
        reject(new Error(`upload failed: ${xhr.status}`));
      }
    };
    xhr.onerror = () => reject(new Error("network error"));
    xhr.send(fd);
  });
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
