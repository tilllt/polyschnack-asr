import { useEffect, useRef, useState } from "react";
import { Mic } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { fetchModelStatus, triggerDownload, uploadRecording } from "../api";
import { useToast } from "./Toasts";
import { useT } from "../useLocale";

export function UploadZone() {
  const [isDragging, setIsDragging] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const fileRef = useRef<HTMLInputElement>(null);
  const { toast } = useToast();
  const { t } = useT();
  const qc = useQueryClient();

  // — Model toggles —
  const [vadOn, setVadOn] = useState(false);
  const [diarizeOn, setDiarizeOn] = useState(false);
  const [modelStatus, setModelStatus] = useState<{ vad: boolean; diarize: boolean; hf: boolean } | null>(null);

  useEffect(() => {
    fetchModelStatus()
      .then((s) => setModelStatus({ vad: s.vad_available, diarize: s.diarize_available, hf: s.hf_token }))
      .catch(() => {});
  }, []);

  function toggleVad() {
    if (!modelStatus?.vad) {
      triggerDownload("vad").catch(() => {});
      toast("Downloading VAD model…", "ok");
    }
    setVadOn((v) => !v);
  }

  function toggleDiarize() {
    if (!modelStatus?.hf) return;  // silently disabled — admin must set HF_TOKEN
    if (!modelStatus?.diarize) {
      triggerDownload("diarize").catch(() => {});
    }
    setDiarizeOn((d) => !d);
  }

  // — Upload logic —
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
        uploadRecording(f, batchId, vadOn, diarizeOn, (pct) => {
          const fileBytes = (f.size * pct) / 100;
          setUploadProgress(Math.round(((uploadedBytes + fileBytes) / totalSize) * 100));
        }).then((r) => {
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

  // — Drag/drop handlers —
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
      {/* Upload zone */}
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

      {/* Toggle switches */}
      <div className="flex items-center justify-center gap-6 flex-wrap">
        <ToggleSwitch
          label="VAD (Silence trim)"
          enabled={vadOn}
          available={modelStatus?.vad ?? false}
          onChange={toggleVad}
        />
        <ToggleSwitch
          label="Speaker Diarization"
          enabled={diarizeOn}
          available={modelStatus?.diarize ?? false}
          noToken={modelStatus !== null && !modelStatus.hf}
          onChange={toggleDiarize}
        />
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
  onChange,
}: {
  label: string;
  enabled: boolean;
  available: boolean;
  noToken?: boolean;
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
