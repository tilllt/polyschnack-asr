# Triple Input Modes — Upload, Record & URL

> **For Hermes:** Use subagent-driven-development to implement this plan task-by-task.

**Goal:** Replace the single file-upload zone in Parakeet ASR with three tabbed input modes: (1) Upload (existing), (2) Record (browser Mic with WakeLock), (3) URL (yt-dlp download from YouTube etc.).

**Architecture:** Three tabs in the frontend (`UploadZone.tsx`) switch between `<UploadTab>`, `<RecordTab>`, `<UrlTab>` — all three call the same backend API at the end.  The backend gets one new endpoint `POST /api/recordings/from-url` that runs yt-dlp inside the container and returns a recording.  A `WakeLock` keeps the phone screen on during recording.

**Tech Stack:** React (existing), Web Audio API + MediaRecorder for recording, Screen Wake Lock API, yt-dlp (via pip in webapp Dockerfile), FastAPI (backend).

---

## Task 1: Add yt-dlp via pip to the webapp container

**Objective:** Install yt-dlp in the Docker image so the backend can call it. Using pip gives us a fresher version than apt.

**Files:**
- Modify: `webapp/Dockerfile:27`

**Step 1: Add `uv pip install yt-dlp` after apt-get line**

In `webapp/Dockerfile`, add a pip install line after the apt-get line:
```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
RUN uv pip install --system yt-dlp
```

(The `--system` flag is needed because the uv image uses a system Python by default.)

**Step 2: Commit**

```bash
git add webapp/Dockerfile
git commit -m "feat: add yt-dlp via pip to webapp image"
```

---

## Task 2: Backend — POST /api/recordings/from-url endpoint

**Objective:** Accept a URL (YouTube, podcast RSS, etc.), run yt-dlp to download → convert to 16kHz mono WAV → save as a Recording row.

**Files:**
- Create: `webapp/app/routers/url_import.py`
- Register: `webapp/app/main.py` (import and include_router)

**Step 1: Create `webapp/app/routers/url_import.py`**

```python
"""POST /api/recordings/from-url — download audio from a URL via yt-dlp."""
from __future__ import annotations

import hashlib
import logging
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlmodel import Session, select

from ..config import settings
from ..crud import create_recording
from ..db import get_session
from ..models import Recording
from .recordings import _current_user, _recording_to_dict

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


@router.post("/recordings/from-url", status_code=201)
async def import_from_url(
    request: Request,
    url: str = Form(...),
    enable_vad: bool = Form(False),
    enable_diarize: bool = Form(False),
    enable_streaming: bool = Form(False),
    enable_noise_reduce: bool = Form(True),
    session: Session = Depends(get_session),
) -> Dict[str, Any]:
    """Download audio from *url* via yt-dlp, convert to 16 kHz mono WAV, save."""
    if not url or not url.strip():
        raise HTTPException(status_code=400, detail="no URL provided")

    # Download best audio, extract to WAV
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir) / "audio.%(ext)s"
        out_template = str(tmp)

        try:
            proc = subprocess.run(
                [
                    "yt-dlp",
                    "-x",                     # extract audio
                    "--audio-format", "wav",
                    "--audio-quality", "0",   # best quality
                    "-o", out_template,
                    "--no-playlist",
                    "--print", "filename",    # output actual file path
                    url.strip(),
                ],
                capture_output=True,
                text=True,
                timeout=600,  # 10 min — large downloads
            )
        except subprocess.TimeoutExpired:
            raise HTTPException(status_code=400, detail="URL download timed out (10 min)")
        except FileNotFoundError:
            raise HTTPException(status_code=500, detail="yt-dlp not installed")

        if proc.returncode != 0:
            err = (proc.stderr or "no output")[:500]
            raise HTTPException(status_code=400, detail=f"yt-dlp failed: {err}")

        # yt-dlp --print filename writes the actual output path on stdout
        wav_path_str = proc.stdout.strip().split("\n")[0].strip()
        wav_path = Path(wav_path_str)
        if not wav_path.exists():
            # Fallback: find any .wav in tmpdir
            found = list(Path(tmpdir).glob("*.wav"))
            if not found:
                raise HTTPException(status_code=400, detail="yt-dlp produced no audio file")
            wav_path = found[0]

        audio_data = wav_path.read_bytes()

    if not audio_data:
        raise HTTPException(status_code=400, detail="empty audio downloaded")

    # Duplicate check
    content_hash = hashlib.blake2b(audio_data, digest_size=16).hexdigest()
    existing = session.exec(
        select(Recording).where(Recording.content_hash == content_hash)
    ).first()
    if existing:
        return _recording_to_dict(existing)

    # Persist
    stored = settings.AUDIO_DIR / f"{uuid.uuid4().hex}.wav"
    stored.write_bytes(audio_data)

    est_duration_s = len(audio_data) / 16000  # rough

    rec = create_recording(
        session,
        original_name=f"URL: {url[:80]}",
        stored_path=str(stored),
        mime="audio/wav",
        size_bytes=len(audio_data),
        duration_s=est_duration_s,
        enable_vad=enable_vad,
        enable_diarize=enable_diarize,
        enable_streaming=enable_streaming,
        enable_noise_reduce=enable_noise_reduce,
        content_hash=content_hash,
        user_id=_current_user(request),
    )
    return _recording_to_dict(rec)
```

**Step 2: Register router in `webapp/app/main.py`**

Find the line that imports and includes `recordings` router, and add:
```python
from .routers import url_import
app.include_router(url_import.router)
```

**Step 3: Commit**

```bash
git add webapp/app/routers/url_import.py webapp/app/main.py
git commit -m "feat: add POST /api/recordings/from-url endpoint"
```

---

## Task 3: Frontend — Add `recordFromMic` and `importFromUrl` API functions

**Objective:** Add two new API helpers alongside the existing `uploadRecording`.

**Files:**
- Modify: `webapp/frontend/src/api.ts`

**Step 1: Add `importFromUrl()`**

```typescript
export async function importFromUrl(
  url: string,
  enableVad = false,
  enableDiarize = false,
  enableStreaming = false,
  enableNoiseReduce = true,
): Promise<Recording> {
  const fd = new FormData();
  fd.append("url", url);
  fd.append("enable_vad", String(enableVad));
  fd.append("enable_diarize", String(enableDiarize));
  fd.append("enable_streaming", String(enableStreaming));
  fd.append("enable_noise_reduce", String(enableNoiseReduce));
  const res = await fetch("/api/recordings/from-url", { method: "POST", body: fd }).then(checkOk);
  return res.json() as Promise<Recording>;
}
```

**Step 2: Add `recordFromMic()`**

Filename is `.webm` (or `.mp4` on iOS), NOT `.wav` — the backend's `_convert_to_wav_if_needed` will convert it.

```typescript
export async function recordFromMic(
  blob: Blob,
  batchId: string,
  enableVad = false,
  enableDiarize = false,
  enableStreaming = false,
  enableNoiseReduce = true,
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
  const res = await fetch("/api/recordings", { method: "POST", body: fd }).then(checkOk);
  return res.json() as Promise<Recording>;
}
```

**Step 3: Commit**

```bash
git add webapp/frontend/src/api.ts
git commit -m "feat: add importFromUrl and recordFromMic API helpers"
```

---

## Task 4: Frontend — 3-tab layout in UploadZone

**Objective:** Convert the single upload zone into a tabbed component with three tabs: Upload, Record, URL.  Each tab is a sub-component; all share the same toggle row at the bottom.

**Files:**
- Modify: `webapp/frontend/src/components/UploadZone.tsx`
- Modify: `webapp/frontend/src/useLocale.ts` (new i18n keys)

**Step 1: Add i18n keys**

In `useLocale.ts`, add these keys to each language object:

```typescript
tab_upload: "Upload",
tab_record: "Record",
tab_url: "URL",
rec_btn: "Start Recording",
rec_wakelock: "Screen stays on",
url_placeholder: "https://youtube.com/watch?v=…",
url_download: "Download & transcribe",
```

**Step 2: Rewrite `UploadZone.tsx`**

Replace the `<div>` upload zone body with a tab bar + conditional content:

```tsx
const [inputMode, setInputMode] = useState<"upload" | "record" | "url">("upload");

// Tab bar (above the content area)
<div className="flex gap-0 border-b border-border mb-4">
  <TabButton active={inputMode === "upload"} onClick={() => setInputMode("upload")}>
    📤 {t("tab_upload")}
  </TabButton>
  <TabButton active={inputMode === "record"} onClick={() => setInputMode("record")}>
    🎤 {t("tab_record")}
  </TabButton>
  <TabButton active={inputMode === "url"} onClick={() => setInputMode("url")}>
    🔗 {t("tab_url")}
  </TabButton>
</div>

{inputMode === "upload" && <UploadTab ... />}
{inputMode === "record" && <RecordTab ... />}
{inputMode === "url" && <UrlTab ... />}
```

`TabButton`:
```tsx
function TabButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      className={`px-4 py-2 text-[13px] font-semibold border-b-2 transition-colors ${
        active
          ? "border-accent text-accent"
          : "border-transparent text-muted hover:text-txt"
      }`}
    >
      {children}
    </button>
  );
}
```

Move the existing drag-zone into `<UploadTab>` function (same code, same state — just lives in UploadZone).

**Step 3: Commit**

```bash
git add webapp/frontend/src/components/UploadZone.tsx webapp/frontend/src/useLocale.ts
git commit -m "feat: 3-tab layout for upload input modes"
```

---

## Task 5: Frontend — RecordTab with WakeLock

**Objective:** Implement the Record tab that captures microphone audio with MediaRecorder and keeps the screen awake.

**Files:**
- Modify: `webapp/frontend/src/components/UploadZone.tsx`

**Step 1: Create `RecordTab` component**

Key details:
- **MIME fallback:** Use `audio/webm` on Chrome/Firefox, `audio/mp4` on iOS Safari
- **WakeLock:** Request `navigator.wakeLock.request("screen")` on start, release on stop
- **Duration timer:** `setInterval` every second
- **Filename:** Derived from blob's actual MIME type (`.webm` or `.mp4`)

```tsx
function RecordTab({ ... }) {
  const [recording, setRecording] = useState(false);
  const [mediaRecorder, setMediaRecorder] = useState<MediaRecorder | null>(null);
  const [wakelock, setWakelock] = useState<WakeLockSentinel | null>(null);
  const [duration, setDuration] = useState(0);
  const timerRef = useRef<number>(0);

  async function acquireWakeLock() {
    try {
      const wl = await navigator.wakeLock.request("screen");
      setWakelock(wl);
      wl.addEventListener("release", () => setWakelock(null));
    } catch {}
  }

  function releaseWakeLock() {
    wakelock?.release().catch(() => {});
    setWakelock(null);
  }

  function getBestMime(): string {
    if (MediaRecorder.isTypeSupported("audio/webm")) return "audio/webm";
    if (MediaRecorder.isTypeSupported("audio/mp4")) return "audio/mp4";
    return "";  // browser default
  }

  async function startRecording() {
    acquireWakeLock();
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const mimeType = getBestMime();
    const mr = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream);
    const chunks: BlobPart[] = [];
    mr.ondataavailable = (e) => chunks.push(e.data);
    mr.onstop = async () => {
      releaseWakeLock();
      clearInterval(timerRef.current);
      setDuration(0);
      stream.getTracks().forEach((t) => t.stop());
      const blob = new Blob(chunks, { type: mimeType || "audio/webm" });
      setIsUploading(true);
      try {
        await recordFromMic(blob, batchId, vadOn, diarizeOn, livePreview, noiseReduce);
        await qc.invalidateQueries({ queryKey: ["recordings"] });
        toast("Recording uploaded", "ok");
      } catch (e) {
        toast(`Upload failed: ${(e as Error).message}`, "err");
      } finally {
        setIsUploading(false);
      }
    };
    mr.start(1000);
    setMediaRecorder(mr);
    setRecording(true);
    timerRef.current = window.setInterval(() => setDuration((d) => d + 1), 1000);
  }

  function stopRecording() {
    mediaRecorder?.stop();
    setRecording(false);
    setMediaRecorder(null);
  }

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      clearInterval(timerRef.current);
      releaseWakeLock();
    };
  }, []);

  const fmt = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;

  return (
    <div className="flex flex-col items-center gap-4 py-6">
      <button
        onClick={recording ? stopRecording : startRecording}
        disabled={isUploading}
        className={`w-20 h-20 rounded-full text-2xl flex items-center justify-center transition-all
          ${recording
            ? "bg-err text-white shadow-lg animate-pulse"
            : "bg-accent text-white hover:bg-accent/90"
          }
          ${isUploading ? "opacity-50" : ""}
        `}
      >
        {recording ? "⏹" : "🎤"}
      </button>
      <div className="text-[28px] font-mono tabular-nums">{fmt(duration)}</div>
      {wakelock && (
        <div className="text-[11px] text-muted2 flex items-center gap-1">
          <span>🔒</span> {t("rec_wakelock")}
        </div>
      )}
      <div className="text-[12px] text-muted">{t("rec_btn")}</div>
    </div>
  );
}
```

**Step 2: Commit**

```bash
git add webapp/frontend/src/components/UploadZone.tsx
git commit -m "feat: RecordTab with mic capture, MIME fallback and screen WakeLock"
```

---

## Task 6: Frontend — UrlTab

**Objective:** Implement the URL tab where the user pastes a URL and clicks "Download & transcribe".

**Files:**
- Modify: `webapp/frontend/src/components/UploadZone.tsx`

**Step 1: Create `UrlTab` component**

```tsx
function UrlTab({ ... }) {
  const [url, setUrl] = useState("");
  const [isDownloading, setIsDownloading] = useState(false);

  async function handleSubmit() {
    if (!url.trim() || isDownloading) return;
    setIsDownloading(true);
    try {
      const result = await importFromUrl(url.trim(), vadOn, diarizeOn, livePreview, noiseReduce);
      toast(`Imported${result.original_name ? ": " + result.original_name : ""}`, "ok");
      await qc.invalidateQueries({ queryKey: ["recordings"] });
      await qc.invalidateQueries({ queryKey: ["stats"] });
      setUrl("");
    } catch (e) {
      toast(`Import failed: ${(e as Error).message}`, "err");
    } finally {
      setIsDownloading(false);
    }
  }

  return (
    <div className="flex flex-col items-center gap-3 py-6">
      <div className="text-[12px] text-muted">{t("url_placeholder")}</div>
      <div className="flex gap-2 w-full max-w-[500px]">
        <input
          type="url"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://youtube.com/watch?v=…"
          className="flex-1 bg-panel border border-border2 rounded-sm px-3 py-2 text-[13px] text-txt outline-none focus:border-accent"
          onKeyDown={(e) => { if (e.key === "Enter") handleSubmit(); }}
        />
        <button
          onClick={handleSubmit}
          disabled={isDownloading || !url.trim()}
          className="btn-accent text-[13px] px-4 py-2 rounded-sm whitespace-nowrap"
        >
          {isDownloading ? "⏳" : "🔗"} {t("url_download")}
        </button>
      </div>
    </div>
  );
}
```

**Step 2: Commit**

```bash
git add webapp/frontend/src/components/UploadZone.tsx
git commit -m "feat: UrlTab with yt-dlp backend integration"
```

---

## Task 7: i18n — Add all new translation strings

**Objective:** Ensure all new UI strings exist in English, German and Portuguese.

**Files:**
- Modify: `webapp/frontend/src/useLocale.ts`

**Step 1: Add keys for each language**

```typescript
// German:
tab_upload: "Hochladen",
tab_record: "Aufnehmen",
tab_url: "URL",
rec_btn: "Aufnahme starten",
rec_wakelock: "Bildschirm bleibt an",
url_placeholder: "https://youtube.com/watch?v=…",
url_download: "Herunterladen & transkribieren",

// English:
tab_upload: "Upload",
tab_record: "Record",
tab_url: "URL",
rec_btn: "Start Recording",
rec_wakelock: "Screen stays on",
url_placeholder: "https://youtube.com/watch?v=…",
url_download: "Download & transcribe",

// Portuguese (pt-BR):
tab_upload: "Upload",
tab_record: "Gravar",
tab_url: "URL",
rec_btn: "Iniciar gravação",
rec_wakelock: "Tela permanece ligada",
url_placeholder: "https://youtube.com/watch?v=…",
url_download: "Baixar & transcrever",
```

**Step 2: Commit**

```bash
git add webapp/frontend/src/useLocale.ts
git commit -m "feat: i18n strings for record and URL tabs"
```

---

## Key Changes from v1

| Punkt | v1 (alt) | v2 (neu) |
|-------|----------|----------|
| yt-dlp Install | `apt-get install yt-dlp` | `uv pip install --system yt-dlp` — kleiner, aktueller |
| MediaRecorder MIME | Fest `audio/webm` | `getBestMime()` mit Fallback `audio/webm` → `audio/mp4` → Browser-Default |
| Blob-Filename | `recording_*.wav` | `recording_*.webm` oder `recording_*.mp4` (korrekt) |
| URL-Import | Synchron (blockiert Request) | Synchron v1 — OK, BackgroundJob später falls nötig |

## Verification

1. **CI passes** — push all commits, verify pipeline succeeds
2. **Upload tab** — drag/drop and file picker work as before
3. **Record tab** — tap tab → mic permission → big red button → stop → upload → appears in list
4. **URL tab** — paste YouTube URL → click Download → recording appears
5. **WakeLock** — recording on phone keeps display on (🔒 indicator visible)
6. **iOS compatibility** — MediaRecorder falls back to `audio/mp4`, upload → ffmpeg converts → works
7. **Retention** — public (anonymous) recordings auto-purged after 60 min

## Files Changed

| File | Action |
|------|--------|
| `webapp/Dockerfile` | Modify — add `uv pip install yt-dlp` |
| `webapp/app/routers/url_import.py` | **Create** — new endpoint |
| `webapp/app/main.py` | Modify — register router |
| `webapp/frontend/src/api.ts` | Modify — add `importFromUrl`, `recordFromMic` |
| `webapp/frontend/src/components/UploadZone.tsx` | Modify — 3-tab layout + RecordTab + UrlTab |
| `webapp/frontend/src/useLocale.ts` | Modify — i18n keys |
