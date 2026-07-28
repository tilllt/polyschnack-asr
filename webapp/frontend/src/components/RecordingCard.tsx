import { useRef, useState, useEffect, useCallback } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Loader2, CheckCircle2, XCircle, Copy, Download, RotateCcw, Trash2, ChevronDown, Search } from "lucide-react";
import type { Recording } from "../api";
import { transcribeRange, startTranscription } from "../api";
import { useDelete, useRetranscribe } from "../hooks";
import { useToast } from "./Toasts";
import { SegmentList } from "./SegmentList";
import { SegmentSearch } from "./SegmentSearch";
import { fmtBytes, fmtDurSec, fmtMs, fmtDate } from "../format";
import { WaveformPlayer, type WaveSurferHandle } from "./WaveformPlayer";
import { useT } from "../useLocale";

function fmtETA(duration_s: number | null, pct: number, created_at: string): string {
  if (pct <= 0 || !duration_s) return "…";
  const elapsed = (Date.now() - new Date(created_at).getTime()) / 1000;
  if (elapsed < 3) return "~" + Math.round(duration_s * 0.15) + "s";
  const estimated_total = (elapsed / pct) * 100;
  const eta_s = Math.max(0, estimated_total - elapsed);
  if (eta_s > 120) return `~${Math.round(eta_s / 60)}m`;
  return `~${Math.round(eta_s)}s`;
}

function fmtTime(sec: number): string {
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

interface Props {
  recording: Recording;
  compact?: boolean;
}

export function RecordingCard({ recording: r, compact = false }: Props) {
  const wsRef = useRef<WaveSurferHandle>(null);
  const [activeSegIdx, setActiveSegIdx] = useState(-1);
  const [currentTime, setCurrentTime] = useState(0);
  const [cropRange, setCropRange] = useState<{start: number; end: number} | null>(null);
  const [dlOpen, setDlOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const dlRef = useRef<HTMLDivElement>(null);
  const { toast } = useToast();
  const { t } = useT();
  const qc = useQueryClient();

  // Default collapse: recordings older than 7 days start collapsed
  const isOld = r.created_at && (Date.now() - new Date(r.created_at).getTime()) > 7 * 24 * 3600 * 1000;
  const [collapsed, setCollapsed] = useState(isOld);

  async function handleStartTranscription(id: string) {
    try {
      await startTranscription(id, r.enable_vad, r.enable_diarize, r.enable_streaming, r.enable_noise_reduce);
      await qc.invalidateQueries({ queryKey: ["recordings"] });
    } catch (e) {
      toast(`Failed: ${(e as Error).message}`, "err");
    }
  }

  async function handleTranscribeCrop(id: string, start: number, end: number) {
    try {
      await transcribeRange(id, start, end);
      toast(`✂ Crop transcribing ${fmtTime(start)}–${fmtTime(end)}`, "ok");
      await qc.invalidateQueries({ queryKey: ["recordings"] });
    } catch (e) {
      toast(`Crop failed: ${(e as Error).message}`, "err");
    }
  }
  const deleteMut = useDelete();
  const retranscribeMut = useRetranscribe();

  // ──── Segment time tracking ────
  const segments = r.segments;
  const hasSegments = segments && segments.length > 0;

  const handleTimeUpdate = useCallback((t: number) => {
    setCurrentTime(t);
    if (!hasSegments || !segments) return;
    let idx = -1;
    for (let i = 0; i < segments.length; i++) {
      if (t >= segments[i].start && t < segments[i].end) { idx = i; break; }
    }
    if (idx === -1 && t >= (segments[segments.length - 1]?.start ?? 0)) {
      idx = segments.length - 1;
    }
    setActiveSegIdx((prev) => (prev === idx ? prev : idx));
  }, [hasSegments, segments]);

  // ──── Close dl menu on outside click ────
  useEffect(() => {
    if (!dlOpen) return;
    function handleClick(e: MouseEvent) {
      if (!dlRef.current?.contains(e.target as Node)) setDlOpen(false);
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [dlOpen]);

  // ──── Actions ────
  async function handleCopy() {
    let text = r.text ?? "";
    if (!text && hasSegments && segments) {
      text = segments.map((s) => s.text).join(" ");
    }
    if (!text.trim()) {
      toast(t("no_text_to_copy"), "err");
      return;
    }
    try {
      await navigator.clipboard.writeText(text.trim());
      toast(t("text_copied"), "ok");
    } catch {
      toast(t("copy_failed"), "err");
    }
  }

  function handleDelete() {
    if (!confirm(t("confirm_delete"))) return;
    deleteMut.mutate(r.uid, {
      onSuccess: () => toast(t("deleted"), "ok"),
      onError: (e) => toast(`${t("delete_error")}: ${e.message}`, "err"),
    });
  }

  function handleRetranscribe() {
    if (!confirm(t("confirm_retranscribe"))) return;
    retranscribeMut.mutate(r.uid, {
      onSuccess: () => toast(t("retranscribe_started"), "ok"),
      onError: (e) => toast(`${t("error")}: ${e.message}`, "err"),
    });
  }

  // ──── Status badge ────
  const statusBorderClass =
    r.status === "done"
      ? "border-l-[3px] border-l-ok"
      : r.status === "failed"
      ? "border-l-[3px] border-l-err"
      : "border-l-[3px] border-l-proc";

  const hasText = (r.text ?? "").trim().length > 0;

  function handleEdited(newSegs: typeof segments, newText: string) {
    qc.setQueryData(["recordings"], (old: Recording[] | undefined) => {
      if (!old) return old;
      return old.map((rec) =>
        rec.id === r.id ? { ...rec, segments: newSegs, text: newText } : rec
      );
    });
  }

  return (
    <div
      className={`
        bg-panel border border-border rounded-card
        transition-colors duration-200 hover:border-border2
        ${statusBorderClass}
      `}
    >
      {/* ── Header ── */}
      <div className="px-3 sm:px-4 pt-[10px] sm:pt-[14px] pb-[8px] sm:pb-[10px] flex items-start gap-2 sm:gap-[10px]">
        <button
          onClick={() => setCollapsed((v) => !v)}
          className="flex-shrink-0 mt-[2px] text-muted2 hover:text-txt transition-colors"
          title={collapsed ? "Expand" : "Collapse"}
        >
          <ChevronDown
            size={14}
            className={`transition-transform duration-200 ${collapsed ? "-rotate-90" : ""}`}
          />
        </button>
        <span
          title={r.original_name}
          className="font-semibold flex-1 min-w-0 leading-[1.35] text-[13px] sm:text-[14px] text-txt truncate"
        >
          {r.original_name}
        </span>
        <StatusBadge status={r.status} t={t} />
        {r.status === "done" && (
          <button
            onClick={() => setSearchOpen((v) => !v)}
            className={`flex-shrink-0 text-[12px] px-[6px] py-[3px] rounded-sm font-semibold transition-colors ${
              searchOpen
                ? "bg-accent/15 text-accent"
                : "text-muted2 hover:text-txt"
            }`}
            title="Search transcript"
          >
            <Search size={13} />
          </button>
        )}
      </div>

      {!collapsed && (<>
      {/* ── Meta chips ── */}
      <div className="px-4 pb-[10px] flex gap-[14px] flex-wrap text-muted text-[12px]">
        {r.size_bytes != null && (
          <span title={t("size")}>{fmtBytes(r.size_bytes)}</span>
        )}
        {r.duration_s != null && (
          <span title={t("duration")} className="flex items-center gap-1">
            <span>⏱</span>
            {fmtDurSec(r.duration_s)}
          </span>
        )}
        {r.processing_ms != null && (
          <span title={t("processing_time")} className="flex items-center gap-1">
            <span>⚡</span>
            {fmtMs(r.processing_ms)}
          </span>
        )}
        {r.created_at && (
          <span title={t("created_at")}>{fmtDate(r.created_at)}</span>
        )}
        {r.language && (
          <span className="bg-[rgba(91,140,255,.1)] text-accent px-[7px] py-[1px] rounded-full text-[11px] font-semibold">
            {r.language}
          </span>
        )}
      </div>

      {/* ── Audio player ── */}
      <div className={compact ? "px-4 pb-1" : "px-4 pb-[6px]"}>
        <WaveformPlayer
          ref={wsRef}
          audioUrl={r.audio_url}
          peaks={r.waveform_peaks}
          duration={r.duration_s}
          onTimeUpdate={handleTimeUpdate}
          onRegionChange={(s, e) => setCropRange({ start: s, end: e })}
        />
        {r.status === "uploaded" && (
          <div className="mt-2 flex justify-center">
            <button
              onClick={() => handleStartTranscription(r.uid)}
              className="bg-accent text-white text-[13px] px-5 py-[7px] rounded-sm font-semibold hover:opacity-90 transition-opacity"
            >
              ▶ {t("transcribe")}
            </button>
          </div>
        )}
      </div>

      {/* ── Transcript / Segments / Error ── */}
      <div className="px-4 pb-[14px]">
        {r.status === "done" && (
          <>
            {searchOpen && hasSegments && segments && r.id && (
              <div className="mb-3">
                <SegmentSearch
                  segments={segments}
                  recordingId={r.uid}
                  onEdited={handleEdited}
                />
              </div>
            )}
            {hasSegments && segments ? (
              <SegmentList
                segments={segments}
                activeIdx={activeSegIdx}
                onActiveChange={setActiveSegIdx}
                onSeekTo={(sec) => wsRef.current?.seekTo(sec)}
                recordingId={r.uid}
                onEdited={handleEdited}
                currentTime={currentTime}
              />
            ) : hasText ? (
              <div className="bg-panel2 border border-border rounded-sm px-[14px] py-3 whitespace-pre-wrap leading-[1.65] max-h-[240px] overflow-y-auto scrollbar-thin text-[13.5px] text-txt break-words">
                {r.text}
              </div>
            ) : (
              <div className="text-muted italic text-[13px] py-[6px]">
                {t("empty_transcript")}
              </div>
            )}
          </>
        )}
        {r.status === "processing" && r.text && (
          <div className="bg-panel2 border border-border rounded-sm px-[14px] py-3 whitespace-pre-wrap leading-[1.65] max-h-[240px] overflow-y-auto scrollbar-thin text-[13.5px] text-txt/70 break-words">
            {r.text}
          </div>
        )}
        {r.status === "failed" && (
          <div className="text-err text-[13px] py-1 leading-[1.5]">
            <span className="mr-1">⚠️</span>
            {r.error ?? t("unknown_error")}
          </div>
        )}
        {r.status === "processing" && (
          <div className="px-4 pb-2">
            <div className="flex items-center justify-between text-[12px] mb-[6px]">
              <span className="text-muted">{t("transcribing")}</span>
              <span className="text-muted2 tabular-nums">{r.progress_pct}% · {fmtETA(r.duration_s, r.progress_pct, r.created_at)}</span>
            </div>
            <div className="w-full h-1.5 bg-border rounded-full overflow-hidden">
              <div
                className="h-full bg-accent rounded-full transition-[width] duration-700 ease-out"
                style={{ width: `${r.progress_pct}%` }}
              />
            </div>
          </div>
        )}
      </div>

      {/* ── Actions ── */}
      <div className="px-4 pb-[14px] flex items-center gap-2 flex-wrap">
        {r.status === "done" && cropRange && (
          <button
            onClick={() => handleTranscribeCrop(r.uid, cropRange.start, cropRange.end)}
            className="btn-ghost-sm text-accent"
          >
            ✂ Transcribe {fmtTime(cropRange.start)}–{fmtTime(cropRange.end)}
          </button>
        )}
        {r.status === "done" && hasText && (
          <button
            onClick={handleCopy}
            className="btn-ghost-sm"
          >
            <Copy size={12} />
            {t("copy")}
          </button>
        )}

        {/* Download dropdown */}
        {r.status === "done" && (
          <div ref={dlRef} className="relative inline-flex">
            <button
              onClick={() => setDlOpen((o) => !o)}
              className="btn-ghost-sm flex items-center gap-1"
            >
              <Download size={12} />
              Download
              <ChevronDown size={11} className={`transition-transform ${dlOpen ? "rotate-180" : ""}`} />
            </button>
            {dlOpen && (
              <div
                className="
                  dl-menu-enter
                  absolute top-[calc(100%+6px)] right-0
                  bg-panel3 border border-border2 rounded-sm
                  p-1 min-w-[110px] z-50
                  shadow-[0_8px_24px_rgba(0,0,0,.4)]
                "
              >
                {(["txt", "srt", "vtt"] as const).map((fmt) => (
                  <a
                    key={fmt}
                    href={`${r.download_url}?format=${fmt}`}
                    download
                    onClick={() => setDlOpen(false)}
                    className="
                      flex items-center gap-2 px-[10px] py-[7px] rounded-[5px]
                      text-txt text-[13px] no-underline cursor-pointer
                      hover:bg-panel2 transition-colors duration-[120ms]
                    "
                  >
                    <span className="font-semibold text-[11px] text-accent w-[26px]">
                      {fmt.toUpperCase()}
                    </span>
                    <span>
                      {fmt === "txt" ? t("plain_text") : fmt === "srt" ? "SubRip" : "WebVTT"}
                    </span>
                  </a>
                ))}
                <div className="border-t border-border my-1" />
                <a
                  href={r.audio_url}
                  download
                  onClick={() => setDlOpen(false)}
                  className="
                    flex items-center gap-2 px-[10px] py-[7px] rounded-[5px]
                    text-txt text-[13px] no-underline cursor-pointer
                    hover:bg-panel2 transition-colors duration-[120ms]
                  "
                >
                  <span className="font-semibold text-[11px] text-accent w-[26px]">WAV</span>
                  <span>{t("original_audio")}</span>
                </a>

              </div>
            )}
          </div>
        )}

        <button
          onClick={handleRetranscribe}
          disabled={retranscribeMut.isPending}
          className="btn-ghost-sm flex items-center gap-1"
        >
          <RotateCcw size={12} className={retranscribeMut.isPending ? "animate-spin" : ""} />
          {t("retranscribe")}
        </button>

        <button
          onClick={handleDelete}
          disabled={deleteMut.isPending}
          className="btn-danger-sm flex items-center gap-1"
        >
          <Trash2 size={12} />
          {t("delete")}
        </button>
      </div>
      </>)}
    </div>
  );
}

/* ──────────────────────────────────────────────────── */

function StatusBadge({ status, t }: { status: Recording["status"]; t: (key: string) => string }) {
  if (status === "done") {
    return (
      <span className="flex-shrink-0 flex items-center gap-[5px] text-[11px] font-bold px-[9px] py-[3px] rounded-full uppercase tracking-[.05em] bg-[rgba(63,185,80,.15)] text-ok">
        <CheckCircle2 size={11} />
          {t("ready")}
      </span>
    );
  }
  if (status === "failed") {
    return (
      <span className="flex-shrink-0 flex items-center gap-[5px] text-[11px] font-bold px-[9px] py-[3px] rounded-full uppercase tracking-[.05em] bg-[rgba(248,81,73,.15)] text-err">
        <XCircle size={11} />
        {t("failed")}
      </span>
    );
  }
  return (
    <span className="flex-shrink-0 flex items-center gap-[5px] text-[11px] font-bold px-[9px] py-[3px] rounded-full uppercase tracking-[.05em] bg-[rgba(88,166,255,.15)] text-proc">
        <Loader2 size={11} className="animate-spin" />
        {t("processing")}
    </span>
  );
}
