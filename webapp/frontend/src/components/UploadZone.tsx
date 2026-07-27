import { useEffect, useRef, useState } from "react";
import { Mic } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { fetchModelStatus, triggerDownload, uploadRecording, importFromUrl, recordFromMic, type ModelStatus } from "../api";
import { useToast } from "./Toasts";
import { useT } from "../useLocale";
import WaveSurfer from "wavesurfer.js";
import RecordPlugin from "wavesurfer.js/dist/plugins/record.js";

export function UploadZone() {
  const [inputMode, setInputMode] = useState<"upload" | "record" | "url">("upload");
  const [recording, setRecording] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const fileRef = useRef<HTMLInputElement>(null);
  const { toast } = useToast();
  const { t } = useT();
  const qc = useQueryClient();

  // — Model toggles (shared by all tabs) —
  const [vadOn, setVadOn] = useState(false);
  const [diarizeOn, setDiarizeOn] = useState(false);
  const [livePreview, setLivePreview] = useState(false);
  const [noiseReduce, setNoiseReduce] = useState(true);
  const [dupPrompt, setDupPrompt] = useState<{ file: File; batchId: string } | null>(null);
  const [modelStatus, setModelStatus] = useState<ModelStatus | null>(null);

  useEffect(() => {
    fetchModelStatus()
      .then(setModelStatus)
      .catch(() => {});
  }, []);

  function toggleVad() {
    setVadOn((v) => {
      const next = !v;
      if (next && !modelStatus?.vad_available) {
        triggerDownload("vad").catch(() => {});
      }
      return next;
    });
  }

  function toggleDiarize() {
    if (!modelStatus?.hf_token) return;
    setDiarizeOn((d) => {
      const next = !d;
      if (next && !modelStatus?.diarize_available) {
        triggerDownload("diarize").catch(() => {});
      }
      return next;
    });
  }

  // — Upload logic (same as before) —
  async function handleFiles(files: FileList | File[]) {
    const items = Array.from(files);
    if (!items.length) return;

    setIsUploading(true);
    setUploadProgress(0);
    const batchId = crypto.randomUUID();
    const totalSize = items.reduce((s, f) => s + f.size, 0);
    let uploadedBytes = 0;

    const results = await Promise.allSettled(
      items.map((f) =>
        uploadRecording(f, batchId, vadOn, diarizeOn, livePreview, noiseReduce, false, (pct) => {
          const fileBytes = (f.size * pct) / 100;
          setUploadProgress(Math.round(((uploadedBytes + fileBytes) / totalSize) * 100));
        }).then((r) => {
          if (r && typeof r === "object" && "duplicate" in r && r.duplicate) {
            setDupPrompt({ file: f, batchId });
            return null;
          }
          uploadedBytes += f.size;
          setUploadProgress(Math.round((uploadedBytes / totalSize) * 100));
          return r;
        })
      )
    );

    const succeeded = results.filter((r) => r.status === "fulfilled").length;
    const errors = results
      .map((r, i) =>
        r.status === "rejected"
          ? `${items[i]?.name ?? "file"}: ${(r.reason as Error).message}`
          : null
      )
      .filter((e): e is string => e !== null);

    if (succeeded > 0) {
      toast(`${succeeded} ${t("recordings")}`, "ok");
    }
    errors.forEach((msg) => toast(msg, "err"));

    await qc.invalidateQueries({ queryKey: ["recordings"] });
    await qc.invalidateQueries({ queryKey: ["stats"] });

    setIsUploading(false);
  }

  async function handleForceUpload(file: File, batchId: string) {
    setIsUploading(true);
    try {
      await uploadRecording(file, batchId, vadOn, diarizeOn, livePreview, true, true);
      toast("Uploaded (forced)", "ok");
      await qc.invalidateQueries({ queryKey: ["recordings"] });
    } catch (e) {
      toast(`Upload failed: ${(e as Error).message}`, "err");
    } finally {
      setIsUploading(false);
    }
  }

  // — Drag/drop handlers (for UploadTab) —
  function handleClick() {
    if (isUploading) return;
    fileRef.current?.click();
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter" || e.key === " ") fileRef.current?.click();
  }

  function handleDragOver(e: React.DragEvent) {
    e.preventDefault();
    setIsDragging(true);
  }

  function handleDragLeave(e: React.DragEvent) {
    if (!e.currentTarget.contains(e.relatedTarget as Node)) {
      setIsDragging(false);
    }
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files.length) void handleFiles(e.dataTransfer.files);
  }

  function handleInputChange(e: React.ChangeEvent<HTMLInputElement>) {
    if (e.target.files?.length) {
      void handleFiles(e.target.files);
      e.target.value = "";
    }
  }

  const active = isDragging || isUploading;

  return (
    <div className="flex flex-col gap-4">
      {/* Tab bar */}
      <div className="flex gap-0 border-b border-border">
        <TabButton active={inputMode === "upload"} disabled={recording} onClick={() => setInputMode("upload")}>
          📤 {t("tab_upload")}
        </TabButton>
        <TabButton active={inputMode === "record"} disabled={recording} onClick={() => setInputMode("record")}>
          🎤 {t("tab_record")}
        </TabButton>
        <TabButton active={inputMode === "url"} disabled={recording} onClick={() => setInputMode("url")}>
          🔗 {t("tab_url")}
        </TabButton>
      </div>

      {/* Tab content */}
      {inputMode === "upload" && (
        <UploadTab
          isUploading={isUploading}
          isDragging={isDragging}
          uploadProgress={uploadProgress}
          active={active}
          handleClick={handleClick}
          handleKeyDown={handleKeyDown}
          handleDragOver={handleDragOver}
          handleDragLeave={handleDragLeave}
          handleDrop={handleDrop}
          handleInputChange={handleInputChange}
          fileRef={fileRef}
          t={t}
        />
      )}
      {inputMode === "record" && (
        <RecordTab
          setIsUploading={setIsUploading}
          onRecordingChange={setRecording}
          toast={toast}
          qc={qc}
          t={t}
          vadOn={vadOn} diarizeOn={diarizeOn}
          livePreview={livePreview} noiseReduce={noiseReduce}
        />
      )}
      {inputMode === "url" && (
        <UrlTab
          toast={toast}
          qc={qc}
          t={t}
          vadOn={vadOn} diarizeOn={diarizeOn}
          livePreview={livePreview} noiseReduce={noiseReduce}
        />
      )}

      {/* Duplicate file prompt */}
      {dupPrompt && (
        <div className="bg-[rgba(248,81,73,.08)] border border-err/30 rounded-sm px-4 py-3 text-[13px] flex items-center gap-3">
          <span className="text-muted flex-1">
            <strong>{dupPrompt.file.name}</strong> already exists.
          </span>
          <button
            onClick={async () => {
              const f = dupPrompt.file;
              setDupPrompt(null);
              await handleForceUpload(f, dupPrompt.batchId);
            }}
            className="btn-ghost-sm text-err text-[12px]"
          >
            Upload again
          </button>
          <button
            onClick={() => setDupPrompt(null)}
            className="btn-ghost-sm text-[12px]"
          >
            Skip
          </button>
        </div>
      )}

      {/* Toggle switches (shared by all tabs) */}
      <div className="flex items-center justify-center gap-6 flex-wrap">
        <ToggleSwitch
          label="VAD (Silence trim)"
          enabled={vadOn}
          available={modelStatus?.vad_available ?? false}
          disabled={recording}
          onChange={toggleVad}
        />
        <ToggleSwitch
          label="Speaker Diarization"
          enabled={diarizeOn}
          available={modelStatus?.diarize_available ?? false}
          noToken={modelStatus !== null && !modelStatus.hf_token}
          disabled={recording || (modelStatus !== null && !modelStatus.hf_token)}
          onChange={toggleDiarize}
        />
        <ToggleSwitch
          label="Live Preview"
          enabled={livePreview}
          available={true}
          disabled={recording}
          onChange={() => setLivePreview((v) => !v)}
        />
        <ToggleSwitch
          label="Noise Reduction"
          enabled={noiseReduce}
          available={true}
          disabled={recording}
          onChange={() => setNoiseReduce((v) => !v)}
        />
        {modelStatus && (
          <span
            className={[
              "inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-[3px] rounded-full",
              modelStatus.asr_device === "cuda"
                ? "bg-[rgba(59,130,246,.12)] text-accent"
                : modelStatus.asr_device === "cpu"
                ? "bg-[rgba(234,179,8,.12)] text-[#eab308]"
                : "bg-[rgba(248,81,73,.1)] text-err",
            ].join(" ")}
            title={`ASR inference: ${modelStatus.asr_device}`}
          >
            {modelStatus.asr_device === "cuda" ? "⚡ GPU" :
             modelStatus.asr_device === "cpu" ? "💻 CPU" : "❓"}
          </span>
        )}
      </div>
    </div>
  );
}

// ── Tab button ──

function TabButton({ active, disabled, onClick, children }: { active: boolean; disabled?: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`px-4 py-2 text-[13px] font-semibold border-b-2 transition-colors ${
        active
          ? "border-accent text-accent"
          : "border-transparent text-muted hover:text-txt"
      } ${disabled ? "opacity-40 pointer-events-none" : ""}`}
    >
      {children}
    </button>
  );
}

// ── Upload tab ──

function UploadTab({ isUploading, uploadProgress, active, handleClick, handleKeyDown, handleDragOver, handleDragLeave, handleDrop, handleInputChange, fileRef, t }: any) {
  return (
    <div
      role="button"
      tabIndex={0}
      aria-label={t("drag_zone")}
      onClick={handleClick}
      onKeyDown={handleKeyDown}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      className={`
        border-2 border-dashed rounded-card
        px-6 py-9 text-center cursor-pointer
        select-none transition-all duration-200
        bg-panel
        ${
          active
            ? "border-accent bg-[rgba(91,140,255,0.06)] text-txt"
            : "border-border2 text-muted hover:border-accent hover:bg-[rgba(91,140,255,0.06)] hover:text-txt"
        }
      `}
    >
      <div className="text-[32px] mb-2 leading-none">
        {isUploading ? (
          <div className="flex flex-col items-center gap-2">
            <span className="text-[18px]">⏳</span>
            <div className="w-[200px] h-2 bg-border rounded-full overflow-hidden">
              <div
                className="h-full bg-accent rounded-full transition-all duration-300"
                style={{ width: `${uploadProgress}%` }}
              />
            </div>
            <span className="text-[11px] text-muted2">{uploadProgress}%</span>
          </div>
        ) : (
          <Mic size={32} className="mx-auto text-muted" />
        )}
      </div>
      <div className="font-semibold text-[15px] text-txt">
        {isUploading ? t("uploading") : t("drag_here")}
      </div>
      <div className="text-[12.5px] mt-1 text-muted">
        {t("multi_files")}
      </div>
      <div className="mt-[10px] text-[11px] text-muted2 tracking-[.03em]">
        MP3 · WAV · OGG / OPUS · M4A · FLAC · WEBM
      </div>
      <input
        ref={fileRef}
        type="file"
        accept="audio/*"
        multiple
        className="hidden"
        onChange={handleInputChange}
      />
    </div>
  );
}

// ── Record tab ──

function RecordTab({ setIsUploading, onRecordingChange, toast, qc, t, vadOn, diarizeOn, livePreview, noiseReduce }: any) {
  const [recording, setRecording] = useState(false);
  const [wakelock, setWakelock] = useState<WakeLockSentinel | null>(null);
  const [duration, setDuration] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);
  const wsRef = useRef<WaveSurfer | null>(null);
  const recordRef = useRef<RecordPlugin | null>(null);
  const timerRef = useRef<number>(0);
  const chunksRef = useRef<Blob[]>([]);

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

  async function startRecording() {
    acquireWakeLock();
    onRecordingChange(true);
    chunksRef.current = [];

    // Create WaveSurfer with Record plugin
    const record = RecordPlugin.create({
      scrollingWaveform: true,
      scrollingWaveformWindow: 5,
      renderRecordedAudio: false,  // we handle upload ourselves
    });

    const ws = WaveSurfer.create({
      container: containerRef.current!,
      waveColor: "rgba(91,140,255,0.3)",
      progressColor: "rgba(91,140,255,0.8)",
      barWidth: 2,
      barGap: 1,
      barRadius: 2,
      height: 60,
      normalize: true,
      plugins: [record],
    });

    wsRef.current = ws;
    recordRef.current = record;

    record.on("record-start", () => {
      setRecording(true);
      setDuration(0);
      timerRef.current = window.setInterval(() => setDuration((d) => d + 1), 1000);
    });

    record.on("record-end", async (blob: Blob) => {
      clearInterval(timerRef.current);
      setDuration(0);
      ws.destroy();
      wsRef.current = null;
      recordRef.current = null;

      releaseWakeLock();
      setIsUploading(true);
      try {
        // Peak-normalize to -1 dBFS — boosts quiet recordings, leaves loud ones alone
        const normBlob = await normalizePeak(blob);
        const batchId = crypto.randomUUID();
        await recordFromMic(normBlob, batchId, vadOn, diarizeOn, livePreview, noiseReduce);
        await qc.invalidateQueries({ queryKey: ["recordings"] });
        toast("Recording uploaded", "ok");
      } catch (e) {
        toast(`Upload failed: ${(e as Error).message}`, "err");
      } finally {
        setIsUploading(false);
        onRecordingChange(false);
      }
    });

    // Record progress for more accurate timer
    record.on("record-progress", (ms: number) => {
      setDuration(Math.floor(ms / 1000));
    });

    try {
      await record.startRecording({
        noiseSuppression: false,
        echoCancellation: false,
        autoGainControl: true,
      });
    } catch (e) {
      toast(`Mic access denied: ${(e as Error).message}`, "err");
      ws.destroy();
      wsRef.current = null;
      recordRef.current = null;
      releaseWakeLock();
      onRecordingChange(false);
    }
  }

  async function stopRecording() {
    recordRef.current?.stopRecording();
    recordRef.current?.stopMic();
    setRecording(false);
  }

  useEffect(() => {
    return () => {
      clearInterval(timerRef.current);
      wsRef.current?.destroy();
      releaseWakeLock();
    };
  }, []);

  const fmt = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;

  return (
    <div className="flex flex-col items-center gap-3 py-4">
      {/* WaveSurfer waveform container — only visible during recording */}
      <div
        ref={containerRef}
        className={`w-full max-w-[500px] ${recording ? "" : "hidden"}`}
      />

      <button
        onClick={recording ? stopRecording : startRecording}
        className={`w-20 h-20 rounded-full text-2xl flex items-center justify-center transition-all shrink-0
          ${recording
            ? "bg-err text-white shadow-lg animate-pulse"
            : "bg-accent text-white hover:bg-accent/90"
          }
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

// ── Audio peak-normalization helper ──

/**
 * Peak-normalize an audio blob to -1 dBFS and return a 16-bit mono WAV blob.
 * Computes the peak sample across all channels, then scales so the peak hits
 * the target level. Quiet recordings get a boost; already-loud ones are unchanged
 * (or very gently attenuated if they'd clip).
 */
async function normalizePeak(blob: Blob): Promise<Blob> {
  const ctx = new AudioContext();
  try {
    const buf = await ctx.decodeAudioData(await blob.arrayBuffer());
    const numChannels = buf.numberOfChannels;
    const sampleRate = buf.sampleRate;
    const length = buf.length;

    // Find global peak across all channels
    let peak = 0;
    for (let ch = 0; ch < numChannels; ch++) {
      const data = buf.getChannelData(ch);
      for (let i = 0; i < length; i++) {
        const abs = Math.abs(data[i]);
        if (abs > peak) peak = abs;
      }
    }

    // Scale so peak hits -1 dBFS (≈ 0.891). Intentionally below 1.0 so
    // the encoder's int16 rounding never clips.
    const targetPeak = 10 ** (-1 / 20); // ~0.891
    const scale = peak > 0 ? targetPeak / peak : 1;

    // Render scaled audio and encode as mono WAV
    const offline = new OfflineAudioContext(1, length, sampleRate);
    const source = offline.createBufferSource();
    // Build mono buffer with scaling
    const monoBuf = offline.createBuffer(1, length, sampleRate);
    const outData = monoBuf.getChannelData(0);
    for (let i = 0; i < length; i++) {
      let sum = 0;
      for (let ch = 0; ch < numChannels; ch++) {
        sum += buf.getChannelData(ch)[i];
      }
      outData[i] = (sum / numChannels) * scale;
    }
    source.buffer = monoBuf;
    source.connect(offline.destination);
    source.start();

    const rendered = await offline.startRendering();
    return encodeWav(rendered);
  } finally {
    ctx.close();
  }
}

/**
 * Encode an AudioBuffer to a 16-bit mono WAV blob.
 */
function encodeWav(audioBuffer: AudioBuffer): Blob {
  const numChannels = audioBuffer.numberOfChannels;
  const sampleRate = audioBuffer.sampleRate;
  const length = audioBuffer.length;

  // Downmix to mono by averaging channels, and apply soft limiting
  const mono = new Float32Array(length);
  for (let i = 0; i < length; i++) {
    let sum = 0;
    for (let ch = 0; ch < numChannels; ch++) {
      sum += audioBuffer.getChannelData(ch)[i];
    }
    mono[i] = Math.max(-1, Math.min(1, sum / numChannels));
  }

  // 16-bit PCM
  const dataLen = length * 2;
  const buffer = new ArrayBuffer(44 + dataLen);
  const view = new DataView(buffer);

  // RIFF header
  writeStr(view, 0, "RIFF");
  view.setUint32(4, 36 + dataLen, true);
  writeStr(view, 8, "WAVE");
  writeStr(view, 12, "fmt ");
  view.setUint32(16, 16, true); // chunk size
  view.setUint16(20, 1, true);  // PCM
  view.setUint16(22, 1, true);  // mono
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true); // byte rate
  view.setUint16(32, 2, true);  // block align
  view.setUint16(34, 16, true); // bits per sample
  writeStr(view, 36, "data");
  view.setUint32(40, dataLen, true);

  // Write PCM samples
  let offset = 44;
  for (let i = 0; i < length; i++) {
    const s = Math.max(-1, Math.min(1, mono[i]));
    view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7FFF, true);
    offset += 2;
  }

  return new Blob([buffer], { type: "audio/wav" });
}

function writeStr(view: DataView, offset: number, str: string) {
  for (let i = 0; i < str.length; i++) {
    view.setUint8(offset + i, str.charCodeAt(i));
  }
}

// ── URL tab ──

function UrlTab({ toast, qc, t, vadOn, diarizeOn, livePreview, noiseReduce }: any) {
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

/* ─────────────────────────────────────────────── */

function ToggleSwitch({
  label,
  enabled,
  available,
  noToken,
  disabled,
  onChange,
}: {
  label: string;
  enabled: boolean;
  available: boolean;
  noToken?: boolean;
  disabled?: boolean;
  onChange: () => void;
}) {
  const badge = available
    ? null
    : noToken
    ? "⚠ no token"
    : "⏳ not cached";

  return (
    <button
      onClick={onChange}
      disabled={disabled}
      className={`
        flex items-center gap-2 px-3 py-2 rounded-sm text-[13px] transition-colors
        ${enabled ? "bg-[rgba(63,185,80,.12)] text-ok" : "bg-panel border border-border2 text-muted"}
        ${noToken ? "opacity-60" : "hover:bg-panel2"}
      `}
    >
      <div
        className={`
          w-[36px] h-[20px] rounded-full relative transition-colors flex-shrink-0
          ${enabled ? "bg-ok" : "bg-border2"}
        `}
      >
        <div
          className={`
            absolute top-[2px] w-[16px] h-[16px] rounded-full bg-white shadow-sm transition-transform
            ${enabled ? "translate-x-[18px]" : "translate-x-[2px]"}
          `}
        />
      </div>
      <span>{label}</span>
      {badge && <span className="text-[11px] text-muted2">{badge}</span>}
    </button>
  );
}
