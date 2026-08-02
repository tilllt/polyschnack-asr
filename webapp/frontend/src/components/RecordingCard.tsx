import { useRef, useState, useEffect, useCallback } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Loader2, CheckCircle2, XCircle, Copy, Download, RotateCcw, Trash2, ChevronDown, Search } from "lucide-react";
import type { ModelMatrixEntry, Recording } from "../api";
import { fetchModelsMatrix, fetchModelStatus, fetchTemplates, fetchTargets, fetchLlmEndpoints, transcribeRange, startTranscription, fetchShares, createShare, deleteShare, fetchVersions, fetchVersionDiff, restoreVersion, toggleAnonLink, type ShareItem, type VersionItem } from "../api";
import { useDelete, useRetranscribe } from "../hooks";
import { useToast } from "./Toasts";
import { SegmentList } from "./SegmentList";
import { SegmentSearch } from "./SegmentSearch";
import { fmtBytes, fmtDurSec, fmtMs, fmtDate } from "../format";
import { WaveformPlayer, type WaveSurferHandle } from "./WaveformPlayer";
import { useT } from "../useLocale";
import { activeSegmentIndex } from "../karaoke";
import { buildShareUrl, formatExpiry } from "../share";
import { FeatureToggles, diarSensToMinDurationOff, type FeatureValues } from "./FeatureToggles";

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

/** Dropdown-Flip: öffnet nach unten, aber wenn das Menü unter den Viewport
 *  ragen würde (Mobile!), klappt es nach oben auf. */
function useFlipUp(open: boolean) {
  const ref = useRef<HTMLDivElement>(null);
  const [up, setUp] = useState(false);
  useEffect(() => {
    if (!open) return;
    const id = requestAnimationFrame(() => {
      const el = ref.current;
      if (!el) return;
      const r = el.getBoundingClientRect();
      setUp(r.bottom > window.innerHeight - 8);
    });
    return () => cancelAnimationFrame(id);
  }, [open]);
  return { ref, up };
}

interface Props {
  recording: Recording;
  compact?: boolean;
  isOidc?: boolean;
  defaultCollapsed?: boolean;
}

/* Diff-Array [{type: same|add|del, text}] → Text-Darstellung */
function renderDiff(diff: unknown[]): string {
  return (diff as { type: string; text: string }[])
    .map((l) => (l.type === "add" ? `+ ${l.text}` : l.type === "del" ? `- ${l.text}` : `  ${l.text}`))
    .join("\n");
}

const KIND_LABEL: Record<string, string> = {
  transcribe: "Transcribe",
  retranscribe: "Re-Transcribe",
  edit: "Edit",
  restore: "Restore",
  postprocess: "Post-Process",
};

export function RecordingCard({ recording: r, compact = false, isOidc = false, defaultCollapsed = false }: Props) {
  const wsRef = useRef<WaveSurferHandle>(null);
  const [activeSegIdx, setActiveSegIdx] = useState(-1);
  const [currentTime, setCurrentTime] = useState(0);
  const [cropRange, setCropRange] = useState<{start: number; end: number} | null>(null);
  const [dlOpen, setDlOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [waveformError, setWaveformError] = useState(false);
  const dlRef = useRef<HTMLDivElement>(null);
  const { toast } = useToast();
  const { t } = useT();
  const qc = useQueryClient();

  // Collapse-Default steuert die Liste (nur erste Transkription offen);
  // Toggle bleibt pro Karte möglich.
  const [collapsed, setCollapsed] = useState(defaultCollapsed);

  // ──── Task 9: inline feature toggles + backend, armed re-transcribe ────
  const [feat, setFeat] = useState<FeatureValues>({
    vad: r.enable_vad,
    diarize: r.enable_diarize,
    numSpeakers: r.diarize_num_speakers != null ? String(r.diarize_num_speakers) : "",
    diarSens: r.diarize_min_duration_off != null
      ? (r.diarize_min_duration_off >= 0.3 ? "less" : r.diarize_min_duration_off <= 0.08 ? "more" : "std")
      : "std",
    streaming: r.enable_streaming,
    noise: r.enable_noise_reduce,
    enhance: r.enable_enhance,
    backend: r.backend ?? "",
    punctuation: r.enable_punctuation ?? false,
    llmEnhance: r.enable_llm_enhance ?? false,
    templateId: r.prompt_template_id ?? undefined,
    targetId: r.delivery_target_id ?? undefined,
    endpointId: undefined,
  });
  const [reArmed, setReArmed] = useState(false);
  const [matrix, setMatrix] = useState<ModelMatrixEntry[]>([]);
  const [flags, setFlags] = useState<{ vad: boolean; diarize: boolean }>({ vad: true, diarize: true });
  const [templates, setTemplates] = useState<{ template_id: number; name: string }[]>([]);
  const [targets, setTargets] = useState<{ target_id: number; name: string; kind: string }[]>([]);
  const [endpoints, setEndpoints] = useState<{ endpoint_id: number; name: string }[]>([]);
  const [shareOpen, setShareOpen] = useState(false);
  const [shares, setShares] = useState<ShareItem[]>([]);
  const [shareUser, setShareUser] = useState("");
  const [shareLevel, setShareLevel] = useState<"read" | "write" | "full">("read");
  const [anonLink, setAnonLink] = useState<{
    active: boolean;
    url: string;
    retentionMinutes: number;
    expiresAt: string | null;
  } | null>(null);
  const [linkCopied, setLinkCopied] = useState(false);
  const [versOpen, setVersOpen] = useState(false);
  const [versions, setVersions] = useState<VersionItem[]>([]);
  const [diffText, setDiffText] = useState("");
  const [diffInfo, setDiffInfo] = useState("");

  // Dropdown-Flip für Download/Share/Versionen (Mobile: nach oben klappen)
  const dlFlip = useFlipUp(dlOpen);
  const shareFlip = useFlipUp(shareOpen);
  const versFlip = useFlipUp(versOpen);

  useEffect(() => {
    fetchModelsMatrix().then(setMatrix).catch(() => {});
    fetchModelStatus()
      .then((ms) => setFlags({ vad: ms.vad_available, diarize: ms.diarize_available }))
      .catch(() => {});
    // Settings-Daten (Templates/Targets/BYOK) nur für eingeloggte User —
    // Backend-Gate liefert sonst 403 (siehe deps.require_authenticated).
    if (isOidc) {
      fetchTemplates().then(setTemplates).catch(() => {});
      fetchTargets().then(setTargets).catch(() => {});
      fetchLlmEndpoints().then(setEndpoints).catch(() => {});
    }
  }, [isOidc]);
  // Re-arm-Status zurücksetzen, wenn die Aufnahme transkribiert wird
  useEffect(() => { if (r.status !== "done") setReArmed(false); }, [r.status]);

  const availableBackends = matrix.filter((m) => m.status === "active").map((m) => m.name);

  async function handleStartTranscription(id: string) {
    try {
      await startTranscription(
        id, feat.vad, feat.diarize, feat.streaming, feat.noise, feat.enhance, feat.backend,
        feat.punctuation, feat.llmEnhance, feat.templateId, feat.targetId, feat.endpointId,
        feat.numSpeakers ? Number(feat.numSpeakers) : undefined,
        diarSensToMinDurationOff(feat.diarSens),
      );
      await qc.invalidateQueries({ queryKey: ["recordings"] });
    } catch (e) {
      toast(`Failed: ${(e as Error).message}`, "err");
    }
  }

  async function loadShares() {
    try {
      setShares(await fetchShares(r.uid));
    } catch (e) {
      toast(`Shares: ${(e as Error).message}`, "err");
    }
  }

  async function doShare() {
    try {
      if (!shareUser.trim()) return;
      await createShare(r.uid, shareUser.trim(), shareLevel);
      setShareUser("");
      await loadShares();
      await qc.invalidateQueries({ queryKey: ["recordings"] });
    } catch (e) {
      toast(`Share: ${(e as Error).message}`, "err");
    }
  }

  async function removeShare(shareId: number) {
    try {
      await deleteShare(r.uid, shareId);
      await loadShares();
    } catch (e) {
      toast(`Share: ${(e as Error).message}`, "err");
    }
  }

  async function toggleAnonLinkState(enabled: boolean) {
    try {
      const res = await toggleAnonLink(r.uid, enabled);
      setAnonLink({
        active: res.share_token,
        url: buildShareUrl(r.uid),
        retentionMinutes: res.retention_minutes,
        expiresAt: res.expires_at,
      });
      setLinkCopied(false);
      if (!enabled) toast(t("anon_link_off"), "ok");
    } catch (e) {
      toast(`Anon-Link: ${(e as Error).message}`, "err");
    }
  }

  async function copyAnonLink() {
    if (!anonLink) return;
    try {
      await navigator.clipboard.writeText(anonLink.url);
      setLinkCopied(true);
      setTimeout(() => setLinkCopied(false), 2000);
    } catch {
      toast(anonLink.url, "ok");
    }
  }

  async function loadVersions() {
    try {
      const vs = await fetchVersions(r.uid);
      setVersions(vs);
      setDiffText("");
      setDiffInfo("");
      if (vs.length >= 2) {
        const last = vs[vs.length - 1];
        const prev = vs[vs.length - 2];
        const d = await fetchVersionDiff(r.uid, last.version_no, prev.version_no);
        setDiffInfo(`V${d.from ?? "—"} → V${d.to}`);
        setDiffText(renderDiff(d.diff));
      }
    } catch (e) {
      toast(`Versionen: ${(e as Error).message}`, "err");
    }
  }

  async function showDiff(v: VersionItem) {
    try {
      setDiffInfo(`V${v.version_no}`);
      const d = await fetchVersionDiff(r.uid, v.version_no);
      setDiffText(renderDiff(d.diff));
    } catch (e) {
      toast(`Diff: ${(e as Error).message}`, "err");
    }
  }

  async function doRestore(v: VersionItem) {
    try {
      await restoreVersion(r.uid, v.version_no);
      toast(`V${v.version_no} wiederhergestellt`, "ok");
      await qc.invalidateQueries({ queryKey: ["recordings"] });
      await loadVersions();
    } catch (e) {
      toast(`Restore: ${(e as Error).message}`, "err");
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
    const idx = activeSegmentIndex(segments ?? [], t);
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
    // Task 9: kein confirm()-Dialog — klappt die Feature-Auswahl an die Zeile
    // und ersetzt den Button durch „▶ Transcribe".
    setReArmed((v) => !v);
  }

  function handleArmedTranscribe() {
    retranscribeMut.mutate({
      id: r.uid,
      opts: {
        enable_vad: feat.vad,
        enable_diarize: feat.diarize,
        diarize_num_speakers: feat.numSpeakers ? Number(feat.numSpeakers) : undefined,
        diarize_min_duration_off: diarSensToMinDurationOff(feat.diarSens),
        enable_streaming: feat.streaming,
        enable_noise_reduce: feat.noise,
        enable_enhance: feat.enhance,
        backend: feat.backend,
      },
    }, {
      onSuccess: () => toast(t("retranscribe_started"), "ok"),
    });
    setReArmed(false);
  }

  // Reset waveform error when audio URL changes
  useEffect(() => { setWaveformError(false); }, [r.audio_url]);

  // ──── Status badge ────
  const statusBorderClass =
    r.status === "done"
      ? "border-l-[3px] border-l-ok"
      : r.status === "failed"
      ? "border-l-[3px] border-l-err"
      : "border-l-[3px] border-l-proc";

  const hasText = (r.text ?? "").trim().length > 0;

  function handleEdited(newSegs: typeof segments, newText: string) {
    // Update cache for all recordings queries (with and without search)
    qc.setQueriesData({ queryKey: ["recordings"] }, (old: Recording[] | undefined) => {
      if (!old) return old;
      return old.map((rec) =>
        rec.id === r.id ? { ...rec, segments: newSegs, text: newText } : rec
      );
    });
  }

  return (
    <div
      className={`
        ${r.shared_with_me ? "bg-amber-500/5 border-amber-400/40" : "bg-panel border-border"}
        border rounded-card
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
        {r.shared_with_me && (
          <span className="flex-shrink-0 text-[9px] font-bold uppercase tracking-wide text-amber-300 bg-amber-500/10 border border-amber-500/30 rounded-sm px-1.5 py-[2px]" title={t("shared_badge")}>
            🔗 {t("shared_badge")}
          </span>
        )}
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
      <div className="px-3 sm:px-4 pb-[10px] flex gap-[10px] sm:gap-[14px] flex-wrap text-muted text-[11px] sm:text-[12px]">
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
          onTimeUpdate={handleTimeUpdate}
          onRegionChange={(s, e) => setCropRange({ start: s, end: e })}
          onLoadError={() => setWaveformError(true)}
        />
        {waveformError && (
          <div className="mt-2 text-center">
            <span className="text-[12px] text-err">ⓘ Try Re-transcribe to regenerate waveform data</span>
          </div>
        )}
        {r.status === "uploaded" && (
          <div className="mt-2 flex flex-col items-center gap-2">
            <FeatureToggles
              values={feat}
              backends={availableBackends}
              flags={flags}
              pp={{ templates, targets, endpoints, isOidc }}
              onChange={(p) => setFeat((f) => ({ ...f, ...p }))}
            />
            <button
              onClick={() => handleStartTranscription(r.uid)}
              className="bg-accent text-white text-[13px] px-5 py-[7px] rounded-sm font-semibold hover:opacity-90 transition-opacity"
            >
              ▶ {t("transcribe")}
            </button>
          </div>
        )}
        {r.status === "queued" && (
          <div className="mt-2 flex justify-center">
            <button
              disabled
              className="bg-panel2 border border-border text-muted text-[13px] px-5 py-[7px] rounded-sm font-semibold opacity-70 cursor-not-allowed"
            >
              ⏳ {t("in_queue")}
            </button>
          </div>
        )}
        {r.status === "done" && reArmed && (
          <div className="mt-2 flex flex-col items-center gap-2 border border-border rounded-sm p-2 bg-panel2/50">
            <FeatureToggles
              values={feat}
              backends={availableBackends}
              flags={flags}
              pp={{ templates, targets, endpoints, isOidc }}
              onChange={(p) => setFeat((f) => ({ ...f, ...p }))}
            />
            <button
              onClick={handleArmedTranscribe}
              disabled={retranscribeMut.isPending}
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
      <div className="px-3 sm:px-4 pb-[14px] flex items-center gap-2 flex-wrap">
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
                ref={dlFlip.ref}
                className={`
                  dl-menu-enter
                  absolute ${dlFlip.up ? "bottom-[calc(100%+6px)]" : "top-[calc(100%+6px)]"} right-0
                  bg-panel3 border border-border2 rounded-sm
                  p-1 min-w-[110px] max-w-[calc(100vw-16px)] z-50
                  shadow-[0_8px_24px_rgba(0,0,0,.4)]
                `}
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
              </div>
            )}
          </div>
        )}

        {/* Share dropdown (nur Owner — Backend liefert access_level "full") */}
        {r.status === "done" && (r.access_level === "full" || r.access_level === "owner") && (
          <div className="relative inline-flex">
            <button
              onClick={() => {
                setShareOpen((o) => !o);
                if (!shareOpen) {
                  void loadShares();
                  // Initialer Anon-Link-Zustand aus der Recording
                  const retMin = r.retention_minutes ?? 60;
                  const exp =
                    r.shared_at && r.is_anon_shared
                      ? new Date(new Date(r.shared_at).getTime() + retMin * 60000).toISOString()
                      : null;
                  setAnonLink(
                    r.is_anon_shared
                      ? {
                          active: true,
                          url: buildShareUrl(r.uid),
                          retentionMinutes: retMin,
                          expiresAt: exp,
                        }
                      : null,
                  );
                }
              }}
              className="btn-ghost-sm flex items-center gap-1"
            >
              🔗 {t("share")}
            </button>
            {shareOpen && (
              <div ref={shareFlip.ref} className={`dl-menu-enter absolute ${shareFlip.up ? "bottom-[calc(100%+6px)]" : "top-[calc(100%+6px)]"} right-0 bg-panel3 border border-border2 rounded-sm p-2 min-w-[240px] max-w-[calc(100vw-16px)] z-50 shadow-[0_8px_24px_rgba(0,0,0,.4)]`}>
                <div className="space-y-1 max-h-[150px] overflow-y-auto mb-1.5">
                  {shares.length === 0 && <p className="text-muted2 text-[11px]">{t("no_shares")}</p>}
                  {shares.map((sh) => (
                    <div key={sh.share_id} className="flex items-center gap-2 text-[12px]">
                      <span className="font-semibold text-txt flex-1 truncate">{sh.user_name ?? `#${sh.user}`}</span>
                      <span className="text-muted2 text-[10px] uppercase">{sh.level}</span>
                      <button onClick={() => void removeShare(sh.share_id)} className="text-err hover:opacity-80" title={t("delete")}>✕</button>
                    </div>
                  ))}
                </div>
                <div className="flex gap-1.5">
                  <input
                    value={shareUser}
                    onChange={(e) => setShareUser(e.target.value)}
                    placeholder={t("share_with_placeholder")}
                    className="flex-1 bg-panel2 border border-border rounded-sm px-2 py-1 text-[12px] text-txt min-w-0"
                  />
                  <select
                    value={shareLevel}
                    onChange={(e) => setShareLevel(e.target.value as "read" | "write" | "full")}
                    className="bg-panel2 border border-border rounded-sm px-1 py-1 text-[11px] text-muted"
                  >
                    <option value="read">read</option>
                    <option value="write">write</option>
                    <option value="full">full</option>
                  </select>
                  <button onClick={() => void doShare()} className="bg-accent text-white text-[11px] px-2 py-1 rounded-sm font-semibold hover:opacity-90">
                    {t("share")}
                  </button>
                </div>

                {/* ── Anon-Share-Link (read-only) + Retention-Warnung ── */}
                <div className="mt-2 pt-2 border-t border-border">
                  <div className="flex items-center justify-between gap-2 mb-1">
                    <span className="text-[11px] font-semibold text-txt">{t("anon_link")}</span>
                    <button
                      onClick={() => void toggleAnonLinkState(!(anonLink?.active ?? false))}
                      className={`text-[10px] px-2 py-0.5 rounded-sm font-semibold ${
                        anonLink?.active
                          ? "bg-amber-500/20 text-amber-300 hover:bg-amber-500/30"
                          : "bg-panel2 border border-border text-muted hover:bg-panel3"
                      }`}
                    >
                      {anonLink?.active ? t("anon_link_on") : t("share")}
                    </button>
                  </div>
                  {anonLink?.active ? (
                    <div className="space-y-1">
                      <div className="flex items-center gap-1.5">
                        <code className="flex-1 min-w-0 truncate text-[10px] text-muted bg-panel2 border border-border rounded-sm px-1.5 py-1">
                          {anonLink.url}
                        </code>
                        <button
                          onClick={() => void copyAnonLink()}
                          className="btn-ghost-sm text-[10px] px-1.5 py-1 flex-shrink-0"
                          title={t("copy_link")}
                        >
                          {linkCopied ? "✓" : "⧉"}
                        </button>
                      </div>
                      {linkCopied && <p className="text-[10px] text-emerald-400">{t("link_copied")}</p>}
                      <p className="text-[10px] text-amber-300/90 leading-snug">
                        ⚠️{" "}
                        {t("anon_link_expiry")
                          .replace("{expiry}", formatExpiry(anonLink.expiresAt, anonLink.retentionMinutes))
                          .replace("{minutes}", String(anonLink.retentionMinutes))}
                      </p>
                    </div>
                  ) : (
                    <p className="text-[10px] text-muted2 leading-snug">{t("anon_link_hint")}</p>
                  )}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Versionen dropdown */}
        {r.status === "done" && (
          <div className="relative inline-flex">
            <button
              onClick={() => { setVersOpen((o) => !o); if (!versOpen) void loadVersions(); }}
              className="btn-ghost-sm flex items-center gap-1"
            >
              🕘 {t("versions")}
            </button>
            {versOpen && (
              <div ref={versFlip.ref} className={`dl-menu-enter absolute ${versFlip.up ? "bottom-[calc(100%+6px)]" : "top-[calc(100%+6px)]"} right-0 bg-panel3 border border-border2 rounded-sm p-2 min-w-[280px] max-w-[calc(100vw-16px)] z-50 shadow-[0_8px_24px_rgba(0,0,0,.4)]`}>
                <div className="space-y-1 max-h-[140px] overflow-y-auto mb-1.5">
                  {versions.length === 0 && <p className="text-muted2 text-[11px]">{t("no_versions")}</p>}
                  {[...versions].reverse().map((v) => (
                    <div key={v.version_no} className="flex items-center gap-2 text-[12px]">
                      <button
                        onClick={() => void showDiff(v)}
                        className="font-mono font-semibold text-accent hover:underline"
                        title={t("show_diff")}
                      >
                        V{v.version_no}
                      </button>
                      <span className="text-muted2 text-[10px] uppercase w-[80px] truncate">{KIND_LABEL[v.kind] ?? v.kind}</span>
                      <span className="text-muted2 text-[10px] flex-1 truncate">{new Date(v.created_at).toLocaleString()}</span>
                      <button
                        onClick={() => void doRestore(v)}
                        className="text-muted hover:text-txt text-[10px] underline"
                        title={t("restore")}
                      >
                        {t("restore")}
                      </button>
                    </div>
                  ))}
                </div>
                {diffText && (
                  <pre className="bg-panel2 border border-border rounded-sm p-1.5 text-[10px] leading-[1.4] text-txt max-h-[160px] overflow-y-auto whitespace-pre-wrap">
                    <span className="text-muted2 block mb-0.5">{diffInfo}</span>
                    {diffText}
                  </pre>
                )}
              </div>
            )}
          </div>
        )}

        <button
          onClick={handleRetranscribe}
          disabled={retranscribeMut.isPending}
          className={`btn-ghost-sm flex items-center gap-1 ${reArmed ? "text-accent" : ""}`}
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
  if (status === "queued") {
    return (
      <span className="flex-shrink-0 flex items-center gap-[5px] text-[11px] font-bold px-[9px] py-[3px] rounded-full uppercase tracking-[.05em] bg-[rgba(240,160,60,.15)] text-[#f0a03c]">
        <Loader2 size={11} className="animate-spin" />
        {t("queued")}
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
