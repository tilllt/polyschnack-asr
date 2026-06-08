import { useRef, useState, useEffect, useCallback } from "react";
import { Loader2, CheckCircle2, XCircle, Copy, Download, RotateCcw, Trash2, ChevronDown } from "lucide-react";
import type { Recording } from "../api";
import { useDelete, useRetranscribe } from "../hooks";
import { useToast } from "./Toasts";
import { SegmentList } from "./SegmentList";
import { fmtBytes, fmtDurSec, fmtMs, fmtDate } from "../format";

interface Props {
  recording: Recording;
  compact?: boolean;
}

export function RecordingCard({ recording: r, compact = false }: Props) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const [activeSegIdx, setActiveSegIdx] = useState(-1);
  const [dlOpen, setDlOpen] = useState(false);
  const dlRef = useRef<HTMLDivElement>(null);
  const { toast } = useToast();
  const deleteMut = useDelete();
  const retranscribeMut = useRetranscribe();

  // ──── Segment time tracking ────
  const segments = r.segments;
  const hasSegments = segments && segments.length > 0;

  const handleTimeUpdate = useCallback(() => {
    if (!audioRef.current || !hasSegments || !segments) return;
    const t = audioRef.current.currentTime;
    let idx = -1;
    for (let i = 0; i < segments.length; i++) {
      if (t >= segments[i].start && t < segments[i].end) {
        idx = i;
        break;
      }
    }
    // If past all end markers, stay on last
    if (idx === -1 && t >= (segments[segments.length - 1]?.start ?? 0)) {
      idx = segments.length - 1;
    }
    setActiveSegIdx((prev) => (prev === idx ? prev : idx));
  }, [hasSegments, segments]);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio || !hasSegments) return;
    audio.addEventListener("timeupdate", handleTimeUpdate);
    return () => audio.removeEventListener("timeupdate", handleTimeUpdate);
  }, [handleTimeUpdate, hasSegments]);

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
      toast("Sem texto para copiar.", "err");
      return;
    }
    try {
      await navigator.clipboard.writeText(text.trim());
      toast("Texto copiado!", "ok");
    } catch {
      toast("Falha ao copiar (sem permissão?)", "err");
    }
  }

  function handleDelete() {
    if (!confirm("Excluir essa gravação permanentemente?")) return;
    deleteMut.mutate(r.id, {
      onSuccess: () => toast("Gravação excluída.", "ok"),
      onError: (e) => toast(`Erro ao excluir: ${e.message}`, "err"),
    });
  }

  function handleRetranscribe() {
    if (!confirm("Re-transcrever esse áudio? A transcrição atual será substituída.")) return;
    retranscribeMut.mutate(r.id, {
      onSuccess: () => toast("Re-transcrição iniciada!", "ok"),
      onError: (e) => toast(`Erro: ${e.message}`, "err"),
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

  return (
    <div
      className={`
        bg-panel border border-border rounded-card overflow-hidden
        transition-colors duration-200 hover:border-border2
        ${statusBorderClass}
      `}
    >
      {/* ── Header ── */}
      <div className="px-4 pt-[14px] pb-[10px] flex items-start gap-[10px]">
        <span
          title={r.original_name}
          className="font-semibold flex-1 min-w-0 break-words leading-[1.35] text-[14px] text-txt"
        >
          {r.original_name}
        </span>
        <StatusBadge status={r.status} />
      </div>

      {/* ── Meta chips ── */}
      <div className="px-4 pb-[10px] flex gap-[14px] flex-wrap text-muted text-[12px]">
        {r.size_bytes != null && (
          <span title="Tamanho">{fmtBytes(r.size_bytes)}</span>
        )}
        {r.duration_s != null && (
          <span title="Duração" className="flex items-center gap-1">
            <span>⏱</span>
            {fmtDurSec(r.duration_s)}
          </span>
        )}
        {r.processing_ms != null && (
          <span title="Tempo de processamento" className="flex items-center gap-1">
            <span>⚡</span>
            {fmtMs(r.processing_ms)}
          </span>
        )}
        {r.created_at && (
          <span title="Criado em">{fmtDate(r.created_at)}</span>
        )}
        {r.language && (
          <span className="bg-[rgba(91,140,255,.1)] text-accent px-[7px] py-[1px] rounded-full text-[11px] font-semibold">
            {r.language}
          </span>
        )}
      </div>

      {/* ── Audio player ── */}
      <div className={compact ? "px-4 pb-1" : "px-4 pb-[6px]"}>
        <audio
          ref={audioRef}
          controls
          preload="none"
          src={r.audio_url}
        />
      </div>

      {/* ── Transcript / Segments / Error ── */}
      <div className="px-4 pb-[14px]">
        {r.status === "done" && (
          <>
            {hasSegments && segments ? (
              <SegmentList
                segments={segments}
                audioRef={audioRef}
                activeIdx={activeSegIdx}
                onActiveChange={setActiveSegIdx}
              />
            ) : hasText ? (
              <div
                className="
                  bg-panel2 border border-border rounded-sm
                  px-[14px] py-3 whitespace-pre-wrap leading-[1.65]
                  max-h-[240px] overflow-y-auto scrollbar-thin
                  text-[13.5px] text-txt break-words
                "
              >
                {r.text}
              </div>
            ) : (
              <div className="text-muted italic text-[13px] py-[6px]">
                (transcrição vazia)
              </div>
            )}
          </>
        )}
        {r.status === "failed" && (
          <div className="text-err text-[13px] py-1 leading-[1.5]">
            <span className="mr-1">⚠️</span>
            {r.error ?? "Erro desconhecido"}
          </div>
        )}
        {r.status === "processing" && (
          <div className="text-muted italic text-[13px] py-[6px]">
            transcrevendo…
          </div>
        )}
      </div>

      {/* ── Actions ── */}
      <div className="px-4 pb-[14px] flex items-center gap-2 flex-wrap">
        {r.status === "done" && hasText && (
          <button
            onClick={handleCopy}
            className="btn-ghost-sm"
          >
            <Copy size={12} />
            Copiar
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
                      {fmt === "txt" ? "Plain text" : fmt === "srt" ? "SubRip" : "WebVTT"}
                    </span>
                  </a>
                ))}
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
          Re-transcrever
        </button>

        <button
          onClick={handleDelete}
          disabled={deleteMut.isPending}
          className="btn-danger-sm flex items-center gap-1"
        >
          <Trash2 size={12} />
          Excluir
        </button>
      </div>
    </div>
  );
}

/* ──────────────────────────────────────────────────── */

function StatusBadge({ status }: { status: Recording["status"] }) {
  if (status === "done") {
    return (
      <span className="flex-shrink-0 flex items-center gap-[5px] text-[11px] font-bold px-[9px] py-[3px] rounded-full uppercase tracking-[.05em] bg-[rgba(63,185,80,.15)] text-ok">
        <CheckCircle2 size={11} />
        pronto
      </span>
    );
  }
  if (status === "failed") {
    return (
      <span className="flex-shrink-0 flex items-center gap-[5px] text-[11px] font-bold px-[9px] py-[3px] rounded-full uppercase tracking-[.05em] bg-[rgba(248,81,73,.15)] text-err">
        <XCircle size={11} />
        falhou
      </span>
    );
  }
  return (
    <span className="flex-shrink-0 flex items-center gap-[5px] text-[11px] font-bold px-[9px] py-[3px] rounded-full uppercase tracking-[.05em] bg-[rgba(88,166,255,.15)] text-proc">
      <Loader2 size={11} className="animate-spin" />
      processando
    </span>
  );
}
