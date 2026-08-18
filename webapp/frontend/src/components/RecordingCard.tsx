import { useRef, useState, useEffect, useCallback, useMemo } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Loader2, CheckCircle2, XCircle, Copy, Download, RotateCcw, Trash2, ChevronDown, Search, Maximize2, X } from "lucide-react";
import type { ModelMatrixEntry, Recording, Segment } from "../api";
import { fetchModelsMatrix, fetchModelStatus, fetchTemplates, fetchTargets, fetchLlmEndpoints, fetchExportTemplates, transcribeRange, startTranscription, fetchShares, createShare, deleteShare, fetchVersions, fetchVersionDiff, restoreVersion, toggleAnonLink, replaceSegments, type ShareItem, type VersionItem, type ExportTemplate } from "../api";
import { useDelete, useRetranscribe, useCancelRecording } from "../hooks";
import { filterAvailableBackends } from "../backendSelect";
import { useToast } from "./Toasts";
import { SegmentList } from "./SegmentList";
import { SegmentSearch } from "./SegmentSearch";
import { fmtBytes, fmtDurSec, fmtMs, fmtDate } from "../format";
import { WaveformPlayer, type WaveSurferHandle } from "./WaveformPlayer";
import { useT } from "../useLocale";
import { useNearViewport } from "../hooks";
import { activeSegmentIndex } from "../karaoke";
import { deriveSegments, insertSegment, deleteSegment, splitSegmentAtRange } from "../resegment";
import { buildShareUrl, formatExpiry } from "../share";
import { FeatureToggles, diarSensToMinDurationOff, type FeatureValues } from "./FeatureToggles";
import { VersionDiff } from "./VersionDiff";

/** ETA aus der beobachteten Fortschrittsrate (ms pro Prozentpunkt).
 *  Die alte Formel extrapolierte linear ueber created_at (Upload-Zeit!) —
 *  bei Re-Transcribe stundenalter Dateien kam Unsinn heraus, und bei
 *  nicht-linearen Phasen (ASR schnell, Alignment langsam) massiv falsch. */
function etaFromRate(rateMsPerPct: number | null, pct: number): string {
  if (!rateMsPerPct || rateMsPerPct <= 0 || pct <= 0 || pct >= 100) return "";
  const ms = rateMsPerPct * (100 - pct);
  if (ms > 120_000) return `~${Math.round(ms / 60_000)}m`;
  return `~${Math.max(1, Math.round(ms / 1000))}s`;
}

type EtaRef = { pct: number; ts: number; rate: number | null };

/** Rate aus dem letzten Fortschrittssprung des Polls ableiten und ETA rendern. */
function updateEta(ref: { current: EtaRef }, pct: number): string {
  const now = Date.now();
  const prev = ref.current;
  if (prev.ts > 0 && pct > prev.pct && now - prev.ts > 1500) {
    ref.current = { pct, ts: now, rate: (now - prev.ts) / (pct - prev.pct) };
  } else if (pct !== prev.pct) {
    ref.current = { pct, ts: now, rate: prev.rate };
  }
  return etaFromRate(ref.current.rate, pct);
}

/** Change 011: Sekunden seit einem ISO-Zeitstempel (0 wenn unbekannt/zukunft). */
export function secondsSince(iso: string | null | undefined): number {
  if (!iso) return 0;
  const t = new Date(iso).getTime();
  if (!Number.isFinite(t)) return 0;
  return Math.max(0, Math.floor((Date.now() - t) / 1000));
}

/** Change 011: „seit Xs" / „seit Xm" aus Sekunden. */
export function fmtSince(s: number): string {
  if (s < 60) return `seit ${s}s`;
  return `seit ${Math.floor(s / 60)}m ${s % 60}s`;
}

/** Change 011: Heartbeat-Zustand einer Recording-Karte.
 *  fresh  = letzter Heartbeat < 8 s (Job lebt, kein messbarer Fortschritt)
 *  stalled = letzter Heartbeat > 45 s bei processing (verdaechtig/haengend)
 */
const HEARTBEAT_FRESH_S = 8;
const HEARTBEAT_STALL_S = 45;

export function heartbeatState(r: {
  last_heartbeat_at?: string | null;
  phase_started_at?: string | null;
  status?: string;
}): { fresh: boolean; stalled: boolean; sincePhase: number; sinceBeat: number } {
  const sinceBeat = secondsSince(r.last_heartbeat_at);
  const sincePhase = secondsSince(r.phase_started_at);
  if (!r.last_heartbeat_at) {
    return { fresh: false, stalled: false, sincePhase, sinceBeat: -1 };
  }
  const fresh = sinceBeat <= HEARTBEAT_FRESH_S;
  const stalled = r.status === "processing" && sinceBeat > HEARTBEAT_STALL_S;
  return { fresh, stalled, sincePhase, sinceBeat };
}

/** Change 011: Warte-ETA (queued) kompakt formatieren. */
export function fmtEtaS(etaS: number | null | undefined): string {
  if (!etaS || etaS <= 0) return "";
  if (etaS >= 120) return `~${Math.round(etaS / 60)}m`;
  return `~${Math.max(1, Math.round(etaS))}s`;
}

/** Serverseitige progress_note → i18n-Key (alignment traegt einen Zaehler). */
const NOTE_LABELS: Record<string, string> = {
  preparing: "preparing",
  vad: "vad",
  enhance: "enhance",
  asr: "transcribing",
  diarization: "diarizing",
  finalizing: "finalizing",
};

function fmtTime(sec: number): string {
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

/** Dropdown-Flip: öffnet nach unten, aber wenn das Menü unter den Viewport
 *  ragen würde (Mobile!), klappt es nach oben auf. Zusätzlich horizontal:
 *  right-0-verankerte Menüs ragen auf schmalen Screens links aus dem
 *  Viewport, wenn der Trigger-Button nicht ganz rechts steht. Statt nur
 *  left/right zu tauschen (verschiebt das Problem nur auf die andere
 *  Seite) wird per translateX exakt geklemmt: dx > 0 schiebt das Menü
 *  nach rechts, bis es komplett sichtbar ist (Fix 2026-08-15, User-
 *  Befund „abgeschnittene Modals bei allen Buttons"). */
function useFlipUp(open: boolean) {
  const ref = useRef<HTMLDivElement>(null);
  const [up, setUp] = useState(false);
  const [dx, setDx] = useState(0);
  useEffect(() => {
    if (!open) return;
    const id = requestAnimationFrame(() => {
      const el = ref.current;
      if (!el) return;
      const r = el.getBoundingClientRect();
      setUp(r.bottom > window.innerHeight - 8);
      // Menü ist right-0 verankert: ragt es links aus dem Viewport
      // (r.left < 0), schiebe es um exakt den Überstand nach rechts.
      let shift = 0;
      if (r.left < 8) shift = 8 - r.left;
      // Sicherheitsnetz rechts (min-w kann breiter als der Platz sein).
      if (r.right > window.innerWidth - 8) {
        shift = Math.min(shift, window.innerWidth - 8 - r.right);
      }
      setDx(shift);
    });
    return () => cancelAnimationFrame(id);
  }, [open]);
  return { ref, up, dx };
}

interface Props {
  recording: Recording;
  compact?: boolean;
  isOidc?: boolean;
  /** Admin → alle Backends wählbar (Auto-Start im Backend); Anon → nur laufende */
  isAdmin?: boolean;
  defaultCollapsed?: boolean;
}

/* Diff-Array [{type: same|add|del, text}] wird in VersionDiff.tsx als
 * GitHub-artige Ansicht gerendert (Zeilennummern, Hunks, Wort-Highlight). */

const KIND_LABEL: Record<string, string> = {
  transcribe: "Transcribe",
  retranscribe: "Re-Transcribe",
  edit: "Edit",
  restore: "Restore",
  postprocess: "Post-Process",
};

export function RecordingCard({ recording: r, compact = false, isOidc = false, isAdmin = false, defaultCollapsed = false }: Props) {
  const wsRef = useRef<WaveSurferHandle>(null);
  const etaRef = useRef<EtaRef>({ pct: -1, ts: 0, rate: null });
  // Fix 2026-08-17: monotone Sequenznummer für Segment-Persistenz (PUT-Guard
  // „letzter Drag gewinnt"): Antworten älterer PUTs werden verworfen, damit
  // eine langsame Antwort keinen neueren Drag-Stand überschreibt.
  const persistSeq = useRef(0);
  // Fix 2026-08-17: Play-Zustand der Wiedergabe (onPlayStateChange aus
  // WaveformPlayer) — für den Karaoke-Vorlauf (Lead nur bei playing).
  const [isPlaying, setIsPlaying] = useState(false);
  const [activeSegIdx, setActiveSegIdx] = useState(-1);
  const [currentTime, setCurrentTime] = useState(0);
  const [cropRange, setCropRange] = useState<{start: number; end: number} | null>(null);
  const [dlOpen, setDlOpen] = useState(false);
  // Change 015: Export-Formate dynamisch aus GET /export-templates
  // (Fallback: hartkodierte txt|srt|vtt, falls der Call fehlschlägt).
  const [exportTemplates, setExportTemplates] = useState<ExportTemplate[] | null>(null);
  useEffect(() => {
    let cancelled = false;
    fetchExportTemplates()
      .then((ts) => {
        if (!cancelled && ts.length > 0) setExportTemplates(ts);
      })
      .catch(() => {
        /* Fallback: null → hartkodierte Liste unten */
      });
    return () => {
      cancelled = true;
    };
  }, []);
  const [searchOpen, setSearchOpen] = useState(false);
  // Review-Fix 2026-08-15 (Such-UI): Query + Sprung-Ziel liegen hier, damit
  // SegmentSearch (eingeben) und SegmentList (hervorheben + scrollen) den
  // gleichen Suchzustand teilen.
  const [searchQuery, setSearchQuery] = useState("");
  const [searchJump, setSearchJump] = useState<{ idx: number; nonce: number } | null>(null);
  // Feature 2026-08-16 (Edit-Vollbild): Zoom auf NUR diese Transkription.
  // Overlay (fixed inset-0) — die SegmentList füllt die volle Höhe, Playback
  // läuft über den bestehenden Player (Space/Play-Button, kein 2. Player).
  const [focusMode, setFocusMode] = useState(false);
  useEffect(() => {
    if (!focusMode) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setFocusMode(false);
    };
    window.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [focusMode]);
  // Feature 2026-08-15: Segmentlänge in der Transkriptionsansicht wählbar.
  // null = Original-Segmente (ASR-Chunks, oft ~105 s); Zahl = max. Dauer in
  // Sekunden für die Re-Segmentierung. Preview UND Export nutzen dieselbe
  // Aufteilung (resegment.ts ←→ service.resegment_by_duration).
  const [segMaxDuration, setSegMaxDuration] = useState<number | null>(null);
  const [waveformError, setWaveformError] = useState(false);
  const dlRef = useRef<HTMLDivElement>(null);
  const { toast } = useToast();
  const { t } = useT();
  const qc = useQueryClient();

  // Collapse-Default steuert die Liste (nur erste Transkription offen);
  // Toggle bleibt pro Karte möglich.
  const [collapsed, setCollapsed] = useState(defaultCollapsed);
  // Lazy-Loading (2026-08-15): Waveform/Audio laden nur, wenn die Karte
  // (a) uncollapsed ist UND (b) in Viewport-Nähe gerät ODER der User sie
  // gerade expandiert. Einmal geladen = bleibt geladen (Hook-Flag).
  const { ref: cardRef, near: nearViewport } = useNearViewport<HTMLDivElement>();
  const [expandedOnce, setExpandedOnce] = useState(false);
  const loadWaveform = !collapsed && (nearViewport || expandedOnce);

  // ──── Task 9: inline feature toggles + backend, armed re-transcribe ────
  const [feat, setFeat] = useState<FeatureValues>({
    vad: r.enable_vad,
    diarize: r.enable_diarize,
    numSpeakers: r.diarize_num_speakers != null ? String(r.diarize_num_speakers) : "",
    diarSens: r.diarize_min_duration_off != null
      ? (r.diarize_min_duration_off >= 0.3 ? "less" : r.diarize_min_duration_off <= 0.08 ? "more" : "std")
      : "std",
    diarMethod: r.diarize_method ?? "",
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
  const [diffData, setDiffData] = useState<{ type: string; text: string }[]>([]);
  const [diffFrom, setDiffFrom] = useState<number | null>(null);
  const [diffTo, setDiffTo] = useState<number | null>(null);
  const [diffLoading, setDiffLoading] = useState(false);

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
  // Re-arm-Status zurücksetzen, wenn die Aufnahme transkribiert wird.
  // Bei "failed" bleibt das Panel offen, damit der User Backend/Parameter
  // korrigieren und erneut transkribieren kann.
  useEffect(() => {
    if (r.status !== "done" && r.status !== "failed") setReArmed(false);
  }, [r.status]);

  // Anon: nur laufende Backends anbieten; Admin: alle (Auto-Start im Backend).
  // reachable === null (Proxy down) → nur Default bleibt übrig (immer true).
  const availableBackends = filterAvailableBackends(matrix, isAdmin);

  // Streaming/Live-Fähigkeit je Backend aus der Feature-Matrix — der Live-
  // Toggle erscheint nur, wenn das gewählte Backend Streaming kann (sonst
  // würde der Modus im Backend still ignoriert). Default ("" = ps-pk-onnx)
  // kann Streaming.
  const streamingByBackend: Record<string, boolean> = { "": true };
  for (const b of matrix) {
    streamingByBackend[b.backend] = !!b.streaming;
  }
  const streamingSupported = streamingByBackend[feat.backend] ?? false;

  async function handleStartTranscription(id: string) {
    try {
      await startTranscription(
        id, feat.vad, feat.diarize, feat.streaming, feat.noise, feat.enhance, feat.backend,
        feat.punctuation, feat.llmEnhance, feat.templateId, feat.targetId, feat.endpointId,
        feat.numSpeakers ? Number(feat.numSpeakers) : undefined,
        diarSensToMinDurationOff(feat.diarSens),
        feat.diarMethod || undefined,
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
      setDiffData([]);
      setDiffFrom(null);
      setDiffTo(null);
      if (vs.length >= 2) {
        // Sofort der Diff der letzten gegen die vorletzte Version (GitHub-Stil)
        const last = vs[vs.length - 1];
        const prev = vs[vs.length - 2];
        setDiffLoading(true);
        try {
          const d = await fetchVersionDiff(r.uid, last.version_no, prev.version_no);
          setDiffFrom(d.from);
          setDiffTo(d.to);
          setDiffData(d.diff as { type: string; text: string }[]);
        } finally {
          setDiffLoading(false);
        }
      }
    } catch (e) {
      toast(`Versionen: ${(e as Error).message}`, "err");
    }
  }

  async function showDiff(v: VersionItem) {
    try {
      setDiffLoading(true);
      setDiffData([]);
      const d = await fetchVersionDiff(r.uid, v.version_no);
      setDiffFrom(d.from);
      setDiffTo(d.to);
      setDiffData(d.diff as { type: string; text: string }[]);
    } catch (e) {
      toast(`Diff: ${(e as Error).message}`, "err");
    } finally {
      setDiffLoading(false);
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
  const cancelMut = useCancelRecording();

  function handleCancelJob() {
    cancelMut.mutate(
      { id: r.uid },
      {
        onSuccess: (res: { cancelled: boolean }) =>
          toast(res.cancelled ? t("cancel_started") : t("cancel_no_job"), res.cancelled ? "ok" : "err"),
        onError: (e: Error) => toast(`${t("cancel_error")}: ${e.message}`, "err"),
      }
    );
  }

  // ──── Segment time tracking ────
  const segments = r.segments;
  const hasSegments = segments && segments.length > 0;
  // Change 009 (Single Source of Truth): die Anzeige ist eine REINE
  // Funktion des Recording-Modells. Es gibt genau EINE Segment-Wahrheit
  // (Server/Cache) — kein dragSegments-Overlay-State, kein Reset-Effekt,
  // keine Referenz-/Inhalts-Vergleiche zur Synchronisation.
  // segments_manual == true → segments direkt (manuelle Aufteilung ist die
  // Wahrheit, keine erneute Re-Segmentierung — gezogene Grenzen
  // verschwinden nie wieder aus der Anzeige); sonst + Segmentlänge →
  // resegmentByDuration (Auto-Vorschau); sonst segments.
  const displaySegments = useMemo(
    () => deriveSegments(segments, segMaxDuration, !!r.segments_manual) as Segment[],
    [segments, segMaxDuration, r.segments_manual],
  );

  // Change 009: Commit = EIN optimistisches Cache-Update auf das
  // Recording-Modell (next + segments_manual: true); PUT im Hintergrund;
  // bei Server-Fehler Rollback auf den vorherigen Modell-Stand +
  // Fehler-Toast. PUT-Guard „letzter Drag gewinnt" (monotone Sequenz,
  // 007) bleibt für parallele PUTs. Die Drag-PREVIEW dagegen ist lokal in
  // SegmentList (dragPreview-State) — der Parent sieht sie nicht.
  async function handleBoundaryDragEnd(next: Segment[]) {
    if (!next || !r.uid) return;
    const seq = ++persistSeq.current;
    const prevSegments = segments; // Rollback-Ziel (Modell vor dem Commit)
    const prevText = r.text ?? "";
    const prevManual = !!r.segments_manual;
    // Optimistisch: Modell sofort aktualisieren — Anzeige folgt automatisch.
    handleEdited(next, next.map((s) => s.text).join(" "), true);
    try {
      const result = await replaceSegments(r.uid, next);
      if (persistSeq.current !== seq) return; // ein neuerer Drag hat gewonnen
      // Server-Antwort ist die Wahrheit (inkl. Flag).
      handleEdited(result.segments, result.text, result.segments_manual);
      toast(t("boundary_saved"), "ok");
    } catch (err) {
      if (persistSeq.current !== seq) return;
      // Rollback auf den vorherigen Modell-Stand + sichtbarer Fehler.
      handleEdited(prevSegments ?? null, prevText, prevManual);
      toast(
        err instanceof Error ? err.message : t("boundary_save_error"),
        "err",
      );
    }
  }

  // ── Feature 2026-08-16: Segment einfügen/löschen (+/− im Mockup) ─────
  // Change 009: identisches Commit-Muster wie der Grenz-Drag — ein
  // optimistisches Cache-Update (next + segments_manual: true), PUT im
  // Hintergrund, Rollback bei Fehler.
  async function persistSegmentList(next: Segment[]) {
    if (!r.uid) return;
    const seq = ++persistSeq.current;
    const prevSegments = segments;
    const prevText = r.text ?? "";
    const prevManual = !!r.segments_manual;
    handleEdited(next, next.map((s) => s.text).join(" "), true);
    try {
      const result = await replaceSegments(r.uid, next);
      if (persistSeq.current !== seq) return; // ein neuerer Drag hat gewonnen
      handleEdited(result.segments, result.text, result.segments_manual);
      toast(t("boundary_saved"), "ok");
    } catch (err) {
      if (persistSeq.current !== seq) return;
      handleEdited(prevSegments ?? null, prevText, prevManual);
      toast(
        err instanceof Error ? err.message : t("boundary_save_error"),
        "err",
      );
    }
  }

  function handleSegmentInsert(afterIdx: number) {
    if (!r.uid || !displaySegments) return;
    const next = insertSegment(displaySegments, afterIdx) as Segment[];
    if (next === displaySegments) return; // keine Wörter → nichts zu teilen
    void persistSegmentList(next);
  }

  function handleSegmentDelete(idx: number) {
    if (!r.uid || !displaySegments || displaySegments.length <= 1) return;
    const next = deleteSegment(displaySegments, idx) as Segment[];
    void persistSegmentList(next);
  }

  // ── Feature 2026-08-16: Text-Markierung → Segment teilen ──────────────
  // Markierter Teil wird eigenes Segment (mit gewähltem Sprecher), Rest
  // behält den Originalsprecher. Gleiche Persistenz wie +/− (PUT + Cache).
  function handleSplitSegment(idx: number, charStart: number, charEnd: number, speaker: string) {
    if (!r.uid || !displaySegments) return;
    const next = splitSegmentAtRange(displaySegments, idx, charStart, charEnd, speaker) as Segment[];
    if (next === displaySegments || next.length === displaySegments.length) return; // nichts geändert
    void persistSegmentList(next);
  }

  const handleTimeUpdate = useCallback((t: number) => {
    setCurrentTime(t);
    // Fix 2026-08-16: gegen displaySegments (ANGEZEIGTE Segmentierung)
    // rechnen, nicht gegen den Cache. Nach dem Verschieben einer Grenze
    // oder einer anderen Segment-Länge zeigen die Segmente andere
    // start/end als der Cache — activeSegmentIndex(Cache) lieferte sonst
    // das falsche aktive Segment → Karaoke-Markierung + Auto-Scroll
    // hingen am falschen Wort („Timing durcheinander").
    const idx = activeSegmentIndex(displaySegments ?? [], t);
    setActiveSegIdx((prev) => (prev === idx ? prev : idx));
  }, [displaySegments]);

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
        diarize_method: feat.diarMethod || undefined,
        enable_streaming: feat.streaming,
        enable_noise_reduce: feat.noise,
        enable_enhance: feat.enhance,
        backend: feat.backend,
      },
    }, {
      onSuccess: () => toast(t("retranscribe_started"), "ok"),
      // Stiller Fehler-Fix: ohne onError verschwand ein fehlgeschlagenes
      // Re-Transcribe komplett ohne Rückmeldung (nur der Status-Badge
      // kippte auf failed).
      onError: (e) => toast(`${t("retranscribe_error")}: ${e.message}`, "err"),
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
  const note = r.progress_note ?? "";
  const phaseKey = note.startsWith("alignment")
    ? "aligning"
    : NOTE_LABELS[note] ?? "transcribing";
  // Live-Details aus der alignment-note: "alignment Gruppe 3/12 — aktiv
  // seit 42s — CLI 45%" → "Gruppe 3/12 — aktiv seit 42s — CLI 45%"
  const phaseDetail =
    note.startsWith("alignment") && note.length > "alignment".length
      ? note.slice("alignment".length).trim()
      : "";
  // Change 011: Heartbeat-Zustand + ETA für die Progress-Zeile. Die ETA
  // kommt aus der beobachteten Rate; ohne Rate (Sync-ASR, Diarization)
  // zeigt die Zeile „aktiv seit Xs" aus phase_started_at — nie mehr „…".
  const hb = heartbeatState(r);
  const eta = updateEta(etaRef, r.progress_pct);

  function handleEdited(
    newSegs: typeof segments,
    newText: string,
    manual?: boolean,
  ) {
    // Update cache for all recordings queries (with and without search)
    qc.setQueriesData({ queryKey: ["recordings"] }, (old: Recording[] | undefined) => {
      if (!old) return old;
      return old.map((rec) =>
        rec.id === r.id
          ? {
              ...rec,
              segments: newSegs,
              text: newText,
              // Change 009: das Flag gehört zum Modell (PUT setzt es true,
              // Rollback stellt den alten Wert wieder her). Undefiniert =
              // Text-Edit (Wort-Diff, 010) — Flag bleibt unverändert.
              ...(manual !== undefined ? { segments_manual: manual } : {}),
            }
          : rec
      );
    });
  }

  return (
    <div
      ref={cardRef}
      className={`
        ${r.shared_with_me ? "bg-amber-500/5 border-amber-400/40" : "bg-panel border-border"}
        border rounded-card
        transition-colors duration-200 hover:border-border2
        ${statusBorderClass}
        flex flex-col
        ${focusMode ? "fixed inset-x-0 top-0 z-[101] rounded-none h-[100dvh] overflow-hidden" : ""}
      `}
    >
      {/* ── Header ── */}
      <div className="flex-shrink-0 px-3 sm:px-4 pt-[10px] sm:pt-[14px] pb-[8px] sm:pb-[10px] flex items-start gap-2 sm:gap-[10px]">
        <button
          onClick={() => {
            setCollapsed((v) => {
              const nv = !v;
              if (!nv) setExpandedOnce(true); // Expand → Waveform sofort laden
              return nv;
            });
          }}
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
        {/* Feature 2026-08-16 (Edit-Vollbild): Icon rechts oben auf der
            Karte — macht die GANZE Karte fullscreen (Waveform/Player
            bleiben oben gepinnt, die Transkription füllt den Rest). */}
        {hasSegments && segments && (
          <button
            onClick={() => {
              // Kollabierte Transkription: vor dem Fullscreen automatisch
              // expandieren (sonst zeigt der Vollbild nur die erste Zeile).
              if (collapsed) {
                setCollapsed(false);
                setExpandedOnce(true); // Waveform sofort laden (wie Expand)
              }
              setFocusMode((v) => !v);
            }}
            title={focusMode ? t("focus_edit_close") : t("focus_edit_open")}
            aria-label={focusMode ? t("focus_edit_close") : t("focus_edit_open")}
            className="flex-shrink-0 mt-[2px] p-1 -m-1 text-muted2 hover:text-accent transition-colors"
          >
            {focusMode ? <X size={18} /> : <Maximize2 size={18} />}
          </button>
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
      <div className={`px-3 sm:px-4 pb-[10px] flex gap-[10px] sm:gap-[14px] flex-wrap text-muted text-[11px] sm:text-[12px] ${focusMode ? "flex-shrink-0" : ""}`}>
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

      {/* ── Audio player (Lazy: nur bei Viewport-Nähe + uncollapsed) ── */}
      <div className={`${compact ? "px-4 pb-1" : "px-4 pb-[6px]"} ${focusMode ? "flex-shrink-0" : ""}`}>
        {loadWaveform ? (
          <WaveformPlayer
            ref={wsRef}
            // Schlanke 64-kbps-MP3-Preview fürs Playback (kein Voll-Download
            // der WAV); Fallback auf die volle Datei, solange die Preview
            // noch nicht generiert ist.
            audioUrl={r.audio_preview_url ?? r.audio_url}
            peaks={r.waveform_peaks}
            durationHint={r.duration_s}
            onTimeUpdate={handleTimeUpdate}
            onRegionChange={(s, e) => setCropRange({ start: s, end: e })}
            onLoadError={() => setWaveformError(true)}
            onPlayStateChange={setIsPlaying}
          />
        ) : (
          // Platzhalter mit fester Höhe — verhindert Layout-Springen beim
          // Scrollen; der Player mountet erst, wenn die Karte in
          // Viewport-Nähe kommt oder expandiert wird (2026-08-15).
          <div className="flex items-center justify-center h-[84px] text-muted2 text-[12px] select-none" aria-hidden="true">
            ⏳ {t("waveform_lazy_hint")}
          </div>
        )}
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
          <div className="mt-2 px-4 flex flex-col items-center gap-1">
            <button
              disabled
              className="bg-panel2 border border-border text-muted text-[13px] px-5 py-[7px] rounded-sm font-semibold opacity-70 cursor-not-allowed"
            >
              ⏳ {t("in_queue")}
            </button>
            {/* Change 011: Queue-Position + Warte-ETA auf der Karte */}
            {(r.queue_position ?? null) !== null && (
              <span className="text-[12px] text-muted2 tabular-nums">
                Warteschlange · Position {r.queue_position}
                {fmtEtaS(r.queue_eta_s) ? ` · ${fmtEtaS(r.queue_eta_s)}` : ""}
                {r.queue_backend ? ` · ${r.queue_backend}` : ""}
              </span>
            )}
          </div>
        )}
        {(r.status === "done" || r.status === "failed") && reArmed && (
          <div className="mt-2 flex flex-col items-center gap-2 border border-border rounded-sm p-2 bg-panel2/50">
            <FeatureToggles
              values={feat}
              backends={availableBackends}
              streamingSupported={streamingSupported}
              streamingByBackend={streamingByBackend}
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
      <div className={`px-4 pb-[14px] ${focusMode ? "flex-1 min-h-0 flex flex-col" : ""}`}>
        {r.status === "done" && (
          <>
            {searchOpen && hasSegments && segments && r.id && (
              <div className="mb-3">
                <SegmentSearch
                  segments={segments}
                  recordingId={r.uid}
                  onEdited={handleEdited}
                  query={searchQuery}
                  onQueryChange={setSearchQuery}
                  onNavigateHit={(idx) =>
                    setSearchJump((s) => ({ idx, nonce: (s?.nonce ?? 0) + 1 }))
                  }
                />
              </div>
            )}
            {hasSegments && segments ? (
              <>
                {/* Feature 2026-08-15: Segmentlänge wählbar (freies
                    Zahlenfeld, Sekunden) — Preview zeigt die re-segmentierten
                    Segmente; der Export nutzt dieselben (persistiert über
                    PUT /segments beim Beenden des Drags). */}
                <div className="mb-2 flex items-center gap-2 flex-wrap">
                  <span className="text-muted2 text-[11px]">📐 {t("seg_len")}</span>
                  <input
                    type="number"
                    min={1}
                    step={1}
                    value={segMaxDuration ?? ""}
                    onChange={(e) => {
                      const v = e.target.value === "" ? null : Number(e.target.value);
                      setSegMaxDuration(v != null && v > 0 ? v : null);
                    }}
                    placeholder={t("seg_len_placeholder")}
                    className="w-[64px] bg-panel border border-border rounded-sm px-1.5 py-[3px] text-[12px] outline-none focus:border-accent tabular-nums"
                  />
                  {segMaxDuration != null && (
                    <span className="text-[11px] text-muted2">
                      {displaySegments.length} × ≤ {segMaxDuration} s
                    </span>
                  )}
                  <span className="text-[11px] text-muted2">
                    {t("boundary_drag_hint_short")}
                  </span>
                </div>
                <SegmentList
                  segments={displaySegments}
                  activeIdx={activeSegIdx}
                  onActiveChange={setActiveSegIdx}
                  onSeekTo={(sec) => wsRef.current?.seekTo(sec)}
                  onSeekPaused={(sec) => wsRef.current?.seekToPaused(sec)}
                  recordingId={r.uid}
                  onEdited={handleEdited}
                  currentTime={currentTime}
                  isPlaying={isPlaying}
                  searchQuery={searchQuery}
                  searchJump={searchJump}
                  onBoundaryDragEnd={handleBoundaryDragEnd}
                  onSegmentInsert={handleSegmentInsert}
                  onSegmentDelete={handleSegmentDelete}
                  onSplitSegment={handleSplitSegment}
                  fillHeight={!!focusMode}
                />
              </>
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
            <div className="flex items-center justify-between gap-2 text-[12px] mb-[6px]">
              <span className="text-muted min-w-0">
                {phaseDetail ? (
                  <span className="text-accent truncate" title={note}>
                    ⚙ {t(phaseKey)} · {phaseDetail}
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1.5">
                    <span className="inline-block w-2.5 h-2.5 rounded-full border-2 border-accent border-t-transparent animate-spin" />
                    {t(phaseKey)}
                    {hb.sincePhase > 0 ? ` · ${fmtSince(hb.sincePhase)}` : ""}
                  </span>
                )}
              </span>
              {/* Change 011: ETA-Zeile wird NIE mehr ausgeblendet — auch bei
                  phaseDetail (Alignment). Fallback: „aktiv seit Xs" statt „…". */}
              <span className="text-muted2 tabular-nums shrink-0">
                {r.progress_pct}%
                {eta
                  ? ` · ${eta}`
                  : hb.sincePhase > 0
                    ? ` · ${fmtSince(hb.sincePhase)}`
                    : ""}
              </span>
            </div>
            <div className="w-full h-1.5 bg-border rounded-full overflow-hidden">
              <div
                className={`h-full bg-accent rounded-full transition-[width] duration-700 ease-out ${
                  hb.fresh && hb.sinceBeat > 0 && !hb.stalled
                    ? "animate-pulse"
                    : ""
                }`}
                style={{ width: `${r.progress_pct}%` }}
              />
            </div>
            {/* Change 011: Stall-Warnung — Job lebt nicht mehr (kein Heartbeat) */}
            {hb.stalled && (
              <div className="mt-[6px] text-[12px] text-warn">
                ⚠ keine Aktivität {fmtSince(hb.sinceBeat)}
              </div>
            )}
          </div>
        )}
      </div>

      {/* ── Actions ── */}
      <div className={`px-3 sm:px-4 pb-[14px] flex items-center gap-2 flex-wrap ${focusMode ? "flex-shrink-0" : ""}`}>
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
                style={{ transform: dlFlip.dx ? `translateX(${dlFlip.dx}px)` : undefined }}
                className={`
                  dl-menu-enter
                  absolute ${dlFlip.up ? "bottom-[calc(100%+6px)]" : "top-[calc(100%+6px)]"} right-0
                  bg-panel3 border border-border2 rounded-sm
                  p-1 min-w-[110px] max-w-[calc(100vw-16px)] z-50
                  shadow-[0_8px_24px_rgba(0,0,0,.4)]
                `}
              >
                {/* Change 015: Formate dynamisch aus /export-templates
                    (Fallback hartkodiert, falls der Call fehlschlägt). */}
                {(exportTemplates ?? [
                  { name: "Plain Text", extension: "txt" },
                  { name: "SubRip (SRT)", extension: "srt" },
                  { name: "WebVTT", extension: "vtt" },
                ]).map((fmt) => (
                  <a
                    key={fmt.extension}
                    href={`${r.download_url}?format=${fmt.extension}`}
                    download
                    onClick={() => setDlOpen(false)}
                    className="
                      flex items-center gap-2 px-[10px] py-[7px] rounded-[5px]
                      text-txt text-[13px] no-underline cursor-pointer
                      hover:bg-panel2 transition-colors duration-[120ms]
                    "
                  >
                    <span className="font-semibold text-[11px] text-accent w-[26px]">
                      {fmt.extension.toUpperCase()}
                    </span>
                    <span>{fmt.name}</span>
                  </a>
                ))}
                {/* Change 015: vollständiger Backup-Download (ZIP) — nur
                    Owner/Share-full (Backend verlangt full, 403 sonst). */}
                {(r.access_level === "full" || r.access_level === "owner") && (
                  <>
                    <div className="my-1 h-px bg-border2" />
                    <a
                      href={r.backup_url}
                      download
                      onClick={() => setDlOpen(false)}
                      className="
                        flex items-center gap-2 px-[10px] py-[7px] rounded-[5px]
                        text-txt text-[13px] no-underline cursor-pointer
                        hover:bg-panel2 transition-colors duration-[120ms]
                      "
                    >
                      <span className="font-semibold text-[11px] text-accent w-[26px]">
                        ZIP
                      </span>
                      <span>{t("backup_zip")}</span>
                    </a>
                  </>
                )}
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
              <div
                ref={shareFlip.ref}
                style={{ transform: shareFlip.dx ? `translateX(${shareFlip.dx}px)` : undefined }}
                className={`dl-menu-enter absolute ${shareFlip.up ? "bottom-[calc(100%+6px)]" : "top-[calc(100%+6px)]"} right-0 bg-panel3 border border-border2 rounded-sm p-2 min-w-[240px] max-w-[calc(100vw-16px)] z-50 shadow-[0_8px_24px_rgba(0,0,0,.4)]`}
              >
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
                      {/* Fix 2026-08-15 (User): Retention-Warnung nur für
                          anonyme Nutzer — OIDC-Konten haben keine Ablauf-
                          Frist, der Hinweis wäre dort irreführend. */}
                      {!isOidc && (
                        <p className="text-[10px] text-amber-300/90 leading-snug">
                          ⚠️{" "}
                          {t("anon_link_expiry")
                            .replace("{expiry}", formatExpiry(anonLink.expiresAt, anonLink.retentionMinutes))
                            .replace("{minutes}", String(anonLink.retentionMinutes))}
                        </p>
                      )}
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
              <div
                ref={versFlip.ref}
                style={{ transform: versFlip.dx ? `translateX(${versFlip.dx}px)` : undefined }}
                className={`dl-menu-enter absolute ${versFlip.up ? "bottom-[calc(100%+6px)]" : "top-[calc(100%+6px)]"} right-0 bg-panel3 border border-border2 rounded-sm p-2 min-w-[280px] max-w-[calc(100vw-16px)] z-50 shadow-[0_8px_24px_rgba(0,0,0,.4)]`}
              >
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
                {(diffLoading || diffData.length > 0) && (
                  <div className="mb-1">
                    {diffLoading ? (
                      <p className="text-[10px] text-muted2 px-1 py-1 animate-pulse">
                        {t("diff_loading")}
                      </p>
                    ) : (
                      <VersionDiff
                        diff={diffData}
                        fromLabel={diffFrom !== null ? `V${diffFrom}` : undefined}
                        toLabel={diffTo !== null ? `V${diffTo}` : undefined}
                      />
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* Re-Transcribe — während processing/queued wird der Button zum
            „Abbrechen" (Job-Cancel, 2026-08-15): läuft der Aligner/ASR
            hängt, kann der User den Job stoppen statt ewig zu warten. */}
        {r.status === "processing" || r.status === "queued" ? (
          <button
            onClick={handleCancelJob}
            disabled={cancelMut.isPending}
            className="btn-danger-sm flex items-center gap-1"
            title={t("cancel_title")}
          >
            <XCircle size={12} className={cancelMut.isPending ? "animate-pulse" : ""} />
            {cancelMut.isPending ? t("cancel_pending") : t("cancel")}
          </button>
        ) : (
          <button
            onClick={handleRetranscribe}
            disabled={retranscribeMut.isPending}
            className={`btn-ghost-sm flex items-center gap-1 ${reArmed ? "text-accent" : ""}`}
          >
            <RotateCcw size={12} className={retranscribeMut.isPending ? "animate-spin" : ""} />
            {t("retranscribe")}
          </button>
        )}

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
