import { useRef, useState, useEffect, useCallback, useMemo } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, CheckCircle2, XCircle, Copy, Download, RotateCcw, Trash2, ChevronDown, Search, Maximize2, X, Pencil, Check, AlertTriangle, Users } from "lucide-react";
import type { ModelMatrixEntry, Recording, Segment, Annotation } from "../api";
import { fetchModelsMatrix, fetchModelStatus, fetchTemplates, fetchTargets, fetchLlmEndpoints, fetchExportTemplates, transcribeRange, startTranscription, fetchShares, createShare, deleteShare, fetchVersions, fetchVersionDiff, restoreVersion, toggleAnonLink, replaceSegments, updateRecordingTitle, fetchAnnotations, createAnnotation, formatCents, type ShareItem, type VersionItem, type ExportTemplate } from "../api";
import { useDelete, useRetranscribe, useRealign, useRediarize, useCancelRecording, useRecordingDetail } from "../hooks";
import { filterAvailableBackends } from "../backendSelect";
import { useToast } from "./Toasts";
import { SegmentList } from "./SegmentList";
import { SegmentSearch } from "./SegmentSearch";
import { fmtBytes, fmtDurSec, fmtMs, fmtDate, parseUtcMs } from "../format";
import { WaveformPlayer, type WaveSurferHandle } from "./WaveformPlayer";
import { AnnotationThreads } from "./AnnotationThreads";
import { useT } from "../useLocale";
import { useNearViewport } from "../hooks";
import { activeSegmentIndex } from "../karaoke";
import { deriveSegments, deleteSegment, splitSegmentAtRange } from "../resegment";
import { buildShareUrl, formatExpiry } from "../share";
import { FeatureToggles, diarSensToMinDurationOff, type FeatureValues } from "./FeatureToggles";
import { VersionDiff } from "./VersionDiff";
import { TagEditor } from "./TagEditor";
import { useDismiss } from "../useDismiss";
import { copyToClipboard } from "../clipboard";

/** Change 082: ETA-Rest als ehrliche Spanne (Sekunden) → „4–7m" / „45s–1m".
 *  Kein Fake-Wert: nur die Backend-Berechnung (Dauer × RTF) füllt die
 *  Felder — ohne bekannte Rate bleibt alles leer. */
export function fmtEtaRange(lowS: number | null | undefined, highS: number | null | undefined): string {
  if (!lowS || !highS || lowS <= 0 || highS <= 0) return "";
  if (highS < 60) return `~${Math.max(1, Math.round(lowS))}–${Math.round(highS)}s`;
  if (highS < 120) return `~${Math.max(1, Math.round(lowS / 60))}–${Math.round(highS / 60)}m`;
  const l = Math.round(lowS / 60);
  const h = Math.round(highS / 60);
  return l === h ? `~${l}m` : `~${l}–${h}m`;
}

/** Fix 2026-08-18: Audio-URL des Players. IMMER zuerst die schlanke
 *  64-kbps-MP3-Preview anfordern — der Server generiert das Sidecar beim
 *  ersten Zugriff synchron (recordings.py get_audio_preview).
 *  `audio_preview_url` ist im Recording-Objekt nur gesetzt, wenn die
 *  Preview schon existiert; die URL ist aber deterministisch konstruierbar.
 *  Erst wenn die Preview fehlschlägt (onLoadError → previewFailed), wird
 *  EINMAL auf die volle Datei zurückgefallen. */
export function resolveAudioUrl(
  rec: { audio_preview_url?: string | null; audio_url: string; uid: string },
  previewFailed: boolean,
): string {
  if (previewFailed) return rec.audio_url;
  return rec.audio_preview_url ?? `/api/recordings/${rec.uid}/audio/preview`;
}

/** Change 011: Sekunden seit einem ISO-Zeitstempel (0 wenn unbekannt/zukunft).
 *  Change 081: naive Strings (ohne Z/Offset) werden als UTC interpretiert —
 *  sonst entsteht in UTC+2 ein konstanter 2h-Skew („keine Aktivität seit 120m"). */
export function secondsSince(iso: string | null | undefined): number {
  if (!iso) return 0;
  const t = parseUtcMs(iso);
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

export type HeartbeatLevel = "fresh" | "warn" | "stalled";

export function heartbeatState(r: {
  last_heartbeat_at?: string | null;
  phase_started_at?: string | null;
  processing_started_at?: string | null;
  status?: string;
}): {
  fresh: boolean;
  stalled: boolean;
  sincePhase: number;
  sinceBeat: number;
  sinceStart: number;
  level: HeartbeatLevel;
} {
  const sinceBeat = secondsSince(r.last_heartbeat_at);
  const sincePhase = secondsSince(r.phase_started_at);
  const sinceStart = secondsSince(r.processing_started_at);
  if (!r.last_heartbeat_at) {
    // Anlauf: noch kein Signal — neutral warn, keine Stall-Warnung.
    return { fresh: false, stalled: false, sincePhase, sinceBeat: -1, sinceStart, level: "warn" };
  }
  const fresh = sinceBeat <= HEARTBEAT_FRESH_S;
  const stalled = r.status === "processing" && sinceBeat > HEARTBEAT_STALL_S;
  const level: HeartbeatLevel = sinceBeat <= HEARTBEAT_FRESH_S ? "fresh" : sinceBeat <= HEARTBEAT_STALL_S ? "warn" : "stalled";
  return { fresh, stalled, sincePhase, sinceBeat, sinceStart, level };
}

/** Change 011: Warte-ETA (queued) kompakt formatieren. */
export function fmtEtaS(etaS: number | null | undefined): string {
  if (!etaS || etaS <= 0) return "";
  if (etaS >= 120) return `~${Math.round(etaS / 60)}m`;
  return `~${Math.max(1, Math.round(etaS))}s`;
}

/** Change 035: feste Phasenreihenfolge der Transkription (Chips). */
export const PHASES = [
  { key: "preparing", labelKey: "preparing" },
  { key: "asr", labelKey: "transcribing" },
  { key: "diarization", labelKey: "diarizing" },
  { key: "alignment", labelKey: "aligning" },
  { key: "postprocessing", labelKey: "finalizing" },
] as const;

/** Change 035: aktive Phase aus progress_note (+ pct-Fallback).

 *  Noten sind die einzige zuverlässige Quelle; ohne Note (Streaming-ASR,
 *  Lücken zwischen Phasen) hilft der Prozentwert: ≤20 → Anlauf,
 *  21–94 → ASR, ≥95 → Nachbearbeitung. Keine falsche Präzision: Wo die
 *  Backend-Noten fehlen, wird konservativ auf die wahrscheinlichste Phase
 *  geraten, nie auf „fertig". */
export function activePhaseIndex(r: {
  progress_note?: string | null;
  progress_pct?: number;
}): number {
  const n = r.progress_note ?? "";
  if (n === "preparing" || n === "vad" || n === "enhance") return 0;
  if (n === "asr") return 1;
  if (n === "diarization") return 2;
  if (n.startsWith("alignment")) return 3;
  if (n === "postprocessing" || n === "finalizing") return 4;
  const pct = r.progress_pct ?? 0;
  if (pct <= 20) return 0;
  if (pct < 95) return 1; // Streaming-ASR schreibt pct ohne note
  return 4; // 95+ ohne note → Nachbearbeitung/Ende
}

/** Serverseitige progress_note → i18n-Key: entfällt mit Change 035 — die
 *  Phase wird über die festen Phasen-Chips (PHASES/activePhaseIndex)
 *  abgebildet. */

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
  // Change 082: 1-s-Ticker — re-rendert die Karte, damit der Heartbeat-
  // Zähler („Herzschlag vor Xs") und die Phasen-Dauer live ticken.
  const [, setTick] = useState(0);
  useEffect(() => {
    const iv = setInterval(() => setTick((t) => t + 1), 1000);
    return () => clearInterval(iv);
  }, []);
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
  // Change 014: Titel-Inline-Edit (Owner/full). Guard gegen doppeltes
  // Speichern (Enter + nachfolgender Blur beim Unmount des Inputs).
  const [editingTitle, setEditingTitle] = useState(false);
  const [titleDraft, setTitleDraft] = useState("");
  const titleSaveLock = useRef(false);
  async function handleTitleSave() {
    const next = titleDraft.trim();
    if (!next || next === (r.title ?? r.original_name)) {
      setEditingTitle(false);
      return;
    }
    if (titleSaveLock.current) {
      // Fix 2026-08-18: Ein Save läuft bereits — der Edit-Mode muss trotzdem
      // verlassen werden können (Klick/Enter/Haken dürfen NIE blockieren).
      setEditingTitle(false);
      return;
    }
    titleSaveLock.current = true;
    // Timeout: ein hängender Request (Server antwortet nicht) darf den
    // Edit-Mode nicht dauerhaft blockieren — nach 20 s Abbruch + Meldung.
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), 20000);
    try {
      await updateRecordingTitle(r.uid, next, ctrl.signal);
      toast(t("title_saved"), "ok");
      await qc.invalidateQueries({ queryKey: ["recordings"] });
    } catch (e) {
      const msg = ctrl.signal.aborted
        ? t("title_save_timeout")
        : (e as Error).message;
      toast(`${t("title_save_error")}: ${msg}`, "err");
    } finally {
      clearTimeout(timer);
      titleSaveLock.current = false;
      setEditingTitle(false);
    }
  }
  // Change 014: Defekt = failed mit fehlender/beschädigter Audio-Datei
  // (recording_health.mark_broken) → eigener Badge im Karten-Header.
  const isBroken = r.status === "failed" && !!r.error && /Audio-Datei fehlt/.test(r.error);
  // Titel nur für Besitzer/Full-Share editierbar (Backend: Owner/Admin).
  const canEditTitle = r.access_level === "owner" || r.access_level === "full";
  // Change 046: Re-Align braucht write-Zugriff (Backend: ensure_access write).
  const canEdit =
    r.access_level === "owner" ||
    r.access_level === "full" ||
    r.access_level === "write";
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
  // Change 088: Default-Re-Segmentierung — 25 s statt null. ASR liefert
  // chunk-bedingte Riesen-Segmente (Ø 119 s bei 95-min-Aufnahmen); ohne
  // Default zeigt die Anzeige die rohen Blöcke. Feld leeren = Original.
  // Manuell angefasste Segmente sind per _manual-Flag markiert und bleiben
  // trotz Default exakt erhalten (resegment.ts-Hybrid) — auch bei
  // segments_manual=true greift der Default für die unangefassten Teile.
  const [segMaxDuration, setSegMaxDuration] = useState<number | null>(25);
  const [waveformError, setWaveformError] = useState(false);
  // Fix 2026-08-18: IMMER zuerst die 64-kbps-MP3-Preview anfordern — der
  // Server generiert das Sidecar beim ersten Zugriff synchron (recordings.py
  // get_audio_preview). audio_preview_url ist im Recording-Objekt nur
  // gesetzt, wenn die Preview schon existiert; die URL ist aber
  // deterministisch konstruierbar. Erst wenn die Preview fehlschlägt
  // (410/Netz), fällt der Player EINMAL auf die volle Datei zurück.
  const [previewFailed, setPreviewFailed] = useState(false);
  useEffect(() => {
    setPreviewFailed(false);
  }, [r.uid]);
  const dlRef = useRef<HTMLDivElement>(null);
  // Change 058: Share-/Versionen-Dropdowns schließen wie das Download-Menü
  // bei Klick außerhalb (+ Escape) — einheitliche Schließ-Logik über
  // useDismiss statt nur Trigger-Toggle.
  const shareRef = useRef<HTMLDivElement>(null);
  const versRef = useRef<HTMLDivElement>(null);
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
    vad: r.vad_mode ?? (r.enable_vad ? "edges" : "off"),  // Change 114
    diarize: r.enable_diarize,
    numSpeakers: r.diarize_num_speakers != null ? String(r.diarize_num_speakers) : "",
    diarSens: r.diarize_min_duration_off != null
      ? (r.diarize_min_duration_off >= 0.3 ? "less" : r.diarize_min_duration_off <= 0.08 ? "more" : "std")
      : "std",
    diarMethod: r.diarize_method ?? "",
    streaming: r.enable_streaming,
    noise: r.enable_noise_reduce,
    enhance: r.enable_enhance,
    separate: r.separate_backend ?? "none",
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
        id, feat.vad !== "off", feat.diarize, feat.streaming, feat.noise, feat.enhance, feat.backend,
        feat.punctuation, feat.llmEnhance, feat.templateId, feat.targetId, feat.endpointId,
        feat.numSpeakers ? Number(feat.numSpeakers) : undefined,
        diarSensToMinDurationOff(feat.diarSens),
        feat.diarMethod || undefined,
        feat.separate,
        feat.vad,  // Change 114: vad_mode
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
      const url = buildShareUrl(r.uid);
      setAnonLink({
        active: res.share_token,
        url,
        retentionMinutes: res.retention_minutes,
        expiresAt: res.expires_at,
      });
      setLinkCopied(false);
      if (enabled) {
        // Change 058: generierter Link wird SOFORT in die Zwischenablage
        // kopiert + Toast-Hinweis (User-Anforderung).
        const ok = await copyToClipboard(url);
        if (ok) {
          setLinkCopied(true);
          toast(t("anon_link_created"), "ok");
        } else {
          toast(t("copy_failed"), "err");
        }
      } else {
        toast(t("anon_link_off"), "ok");
      }
    } catch (e) {
      toast(`Anon-Link: ${(e as Error).message}`, "err");
    }
  }

  async function copyAnonLink() {
    if (!anonLink) return;
    const ok = await copyToClipboard(anonLink.url);
    if (ok) {
      setLinkCopied(true);
      setTimeout(() => setLinkCopied(false), 2000);
      toast(t("link_copied"), "ok");
    } else {
      toast(t("copy_failed"), "err");
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
  const realignMut = useRealign();
  // Change 113: BGM-Removal-Auswahl für Re-Align (analog Re-Transcribe).
  const [realignSep, setRealignSep] = useState<string>("none");
  const rediarizeMut = useRediarize();
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
  // Change 059: die Liste liefert nur die Karten-Shell (lite) — Transkription
  // + Peaks werden beim Aufklappen pro Karte nachgeladen (useRecordingDetail,
  // Cache pro uid, Polling nur während processing). Fallback auf die
  // Listenfelder (z. B. Test-Fixtures ohne lite).
  const detailQ = useRecordingDetail(
    r.uid,
    !collapsed && (r.status === "done" || r.status === "processing"),
  );
  const detail = detailQ.data;
  const segments = detail?.segments ?? r.segments;
  const recText = detail?.text ?? r.text;
  // „Loading…"-Hinweis: solange der erste Voll-Datensatz lädt und noch
  // nichts da ist (bei Cache-Treffer sofort rendern).
  const transcriptLoading = detailQ.isLoading || (detailQ.isFetching && !detail);
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
    () => deriveSegments(segments, segMaxDuration) as Segment[],
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
    const prevText = recText ?? "";
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
    const prevText = recText ?? "";
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

  // Change 055: der „+"-Insert-Button zwischen den Segmenten ist entfernt —
  // Einfügen läuft über den Insert-Segment-Modus (handleSplitSegment).
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

  // ──── Close dropdowns on outside click / Escape (Change 058) ────
  // Einheitlich über useDismiss: dl (Download), share, vers.
  useDismiss(dlRef, dlOpen, () => setDlOpen(false));
  useDismiss(shareRef, shareOpen, () => setShareOpen(false));
  useDismiss(versRef, versOpen, () => setVersOpen(false));

  // ──── Actions ────
  async function handleCopy() {
    let text = recText ?? "";
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
        enable_vad: feat.vad !== "off",
        vad_mode: feat.vad,  // Change 114
        enable_diarize: feat.diarize,
        diarize_num_speakers: feat.numSpeakers ? Number(feat.numSpeakers) : undefined,
        diarize_min_duration_off: diarSensToMinDurationOff(feat.diarSens),
        diarize_method: feat.diarMethod || undefined,
        enable_streaming: feat.streaming,
        enable_noise_reduce: feat.noise,
        enable_enhance: feat.enhance,
        separate_backend: feat.separate,
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

  // Change 046: Re-Alignment auf korrigiertem Text (Ground Truth) — der
  // Forced-Aligner verifiziert die Word-Timestamps erneut. Läuft im
  // Hintergrund (alignment-Feld), Transkription bleibt sichtbar.
  // Change 113: gewähltes BGM-Removal (realignSep) wird mitgesendet.
  function handleRealign() {
    realignMut.mutate(
      { id: r.uid, opts: { separate_backend: realignSep } },
      {
        onSuccess: () => toast(t("realign_started"), "ok"),
        onError: (e) => toast(`${t("realign_error")}: ${e.message}`, "err"),
      },
    );
  }

  // Change 057: Re-Diarize — Sprecher-Zuordnung neu berechnen (NUR
  // speaker-Felder; Text/Wörter/Zeiten bleiben unangetastet). Läuft im
  // Hintergrund (diar_status-Feld).
  function handleRediarize() {
    rediarizeMut.mutate(r.uid, {
      onSuccess: () => toast(t("rediarize_started"), "ok"),
      onError: (e) => toast(`${t("rediarize_error")}: ${e.message}`, "err"),
    });
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

  const hasText = (recText ?? "").trim().length > 0;
  const note = r.progress_note ?? "";

  // ──── Change 056: Annotationen (zeitgebundene Kommentare) ────
  const annQuery = useQuery<Annotation[], Error>({
    queryKey: ["annotations", r.uid] as const,
    queryFn: () => fetchAnnotations(r.uid),
    enabled: !!r.uid && hasText,
  });
  const annotations = annQuery.data ?? [];
  // Playback-Fenster: Annotation, über die gerade gespielt wird (Bubble +
  // Highlight im Thread-Bereich). Marker-Klick (ohne Playback) setzt
  // annHighlightId direkt; Playback überschreibt es laufend.
  const activeAnnotation = useMemo(
    () =>
      annotations.find((a) => currentTime >= a.start_s && currentTime <= a.end_s) ?? null,
    [annotations, currentTime],
  );
  const [annHighlightId, setAnnHighlightId] = useState<number | null>(null);
  useEffect(() => {
    if (activeAnnotation) setAnnHighlightId(activeAnnotation.id);
  }, [activeAnnotation]);
  // Annotate-Popover (Text-Markierung → 💬)
  const [annotateSel, setAnnotateSel] = useState<{
    idx: number;
    charStart: number;
    charEnd: number;
    preview: string;
  } | null>(null);
  const [annotateBody, setAnnotateBody] = useState("");
  const [annotateSaving, setAnnotateSaving] = useState(false);

  function handleAnnotate(sel: { idx: number; charStart: number; charEnd: number; preview: string }) {
    setAnnotateSel(sel);
    setAnnotateBody("");
  }

  async function saveAnnotation() {
    if (!annotateSel) return;
    const body = annotateBody.trim();
    if (!body) return;
    setAnnotateSaving(true);
    try {
      // Change 077: createAnnotation liefert die neue Annotation — sie
      // wird sofort aktiv (Scope-Modus zeigt sie + Antworten unten),
      // statt nach dem Speichern „nichts" anzuzeigen.
      const created = await createAnnotation(r.uid, {
        segment_idx: annotateSel.idx,
        char_start: annotateSel.charStart,
        char_end: annotateSel.charEnd,
        body,
      });
      setAnnotateSel(null);
      setAnnHighlightId(created.id);
      toast(t("annot_saved"), "ok");
      void qc.invalidateQueries({ queryKey: ["annotations", r.uid] });
    } catch (e) {
      toast(`${t("annot_save_error")}: ${(e as Error).message}`, "err");
    } finally {
      setAnnotateSaving(false);
    }
  }

  function handleMarkerClick(t: number) {
    wsRef.current?.seekToPaused(t);
    const near = annotations.find((a) => Math.abs(a.start_s - t) < 0.75);
    setAnnHighlightId(near?.id ?? null);
  }

  // Live-Details aus der alignment-note: "alignment Gruppe 3/12 — aktiv
  // seit 42s — CLI 45%" → "Gruppe 3/12 — aktiv seit 42s — CLI 45%"
  const phaseDetail =
    note.startsWith("alignment") && note.length > "alignment".length
      ? note.slice("alignment".length).trim()
      : "";
  // Change 082: Heartbeat-Zustand + echte ETA (Backend: Dauer × RTF).
  // Keine Rate-ETA mehr — ohne Backend-Felder zeigt die Zeile
  // „verarbeitet seit Xs" bzw. „aktiv seit Xs" — nie mehr „…".
  const hb = heartbeatState(r);
  const etaRange = fmtEtaRange(r.eta_low_s, r.eta_high_s);

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
    // Change 059: der Detail-Cache (nachgeladene Transkription) muss
    // mitziehen — er ist die Segment-Wahrheit der aufgeklappten Karte.
    qc.setQueryData(["recording-detail", r.uid], (old: Recording | undefined) =>
      old
        ? {
            ...old,
            segments: newSegs,
            text: newText,
            ...(manual !== undefined ? { segments_manual: manual } : {}),
          }
        : old
    );
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
        <div className="flex-1 min-w-0">
          {editingTitle ? (
            <div className="flex items-center gap-1">
              <input
                autoFocus
                value={titleDraft}
                onChange={(e) => setTitleDraft(e.target.value)}
                onBlur={handleTitleSave}
                onKeyDown={(e) => {
                  if (e.key === "Enter") handleTitleSave();
                  if (e.key === "Escape") setEditingTitle(false);
                }}
                className="w-full min-w-0 bg-panel2 border border-accent/50 rounded-sm px-1.5 py-[1px] text-[13px] sm:text-[14px] text-txt outline-none"
                placeholder={t("title_placeholder")}
                aria-label={t("edit_title")}
              />
              <button
                onClick={handleTitleSave}
                className="flex-shrink-0 text-accent hover:text-accent/80 transition-colors"
                title={t("save")}
                aria-label={t("save")}
              >
                <Check size={14} />
              </button>
            </div>
          ) : (
            <>
              <div className="flex items-center gap-1 min-w-0">
                <span
                  title={r.title ?? r.original_name}
                  className="font-semibold flex-1 min-w-0 leading-[1.35] text-[13px] sm:text-[14px] text-txt truncate"
                >
                  {r.title ?? r.original_name}
                </span>
                {canEditTitle && (
                  <button
                    onClick={() => {
                      setTitleDraft(r.title ?? r.original_name);
                      setEditingTitle(true);
                    }}
                    className="flex-shrink-0 p-0.5 -m-0.5 text-muted2 hover:text-accent transition-colors"
                    title={t("edit_title")}
                    aria-label={t("edit_title")}
                  >
                    <Pencil size={12} />
                  </button>
                )}
              </div>
              {r.title && r.title !== r.original_name && (
                <div
                  className="text-muted2 text-[11px] leading-[1.3] truncate"
                  title={t("original_file") + ": " + r.original_name}
                >
                  {r.original_name}
                </div>
              )}
              {/* Change 054: Tags (Anzeige + Editor bei write/full/owner) */}
              <TagEditor uid={r.uid} tags={r.tags ?? []} canEdit={canEdit} />
            </>
          )}
        </div>
        <StatusBadge status={r.status} t={t} />
        {isBroken && (
          <span
            className="flex-shrink-0 flex items-center gap-1 text-[9px] font-bold uppercase tracking-wide text-err bg-[rgba(248,81,73,.12)] border border-err/40 rounded-sm px-1.5 py-[2px]"
            title={t("broken_title")}
          >
            <AlertTriangle size={9} /> {t("broken_badge")}
          </span>
        )}
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
        {/* Change 086: Job-Kosten (User sichtbar) */}
        {r.cost_cents != null && r.status === "done" && (
          <span title={t("cost")} className="flex items-center gap-1">
            <span>💰</span>
            {formatCents(r.cost_cents)}
          </span>
        )}
        {r.reserved_cents != null && r.status === "processing" && (
          <span title={t("reserved_cost")} className="flex items-center gap-1 text-muted2">
            <span>💳</span>~{formatCents(r.reserved_cents)}
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
            // Fix 2026-08-18: Schlanke 64-kbps-MP3-Preview fürs Playback
            // (kein Voll-Download der WAV). Die URL wird deterministisch
            // gebaut (Server generiert das Sidecar synchron beim ersten
            // Zugriff); Fallback auf die volle Datei NUR wenn die Preview
            // fehlschlägt (onLoadError → previewFailed).
            audioUrl={resolveAudioUrl(r, previewFailed)}
            peaks={detail?.waveform_peaks ?? r.waveform_peaks}
            durationHint={r.duration_s}
            onTimeUpdate={handleTimeUpdate}
            onRegionChange={(s, e) => setCropRange({ start: s, end: e })}
            onLoadError={() => {
              setWaveformError(true);
              if (!previewFailed) setPreviewFailed(true);
            }}
            onPlayStateChange={setIsPlaying}
            // Change 056: Annotation-Marker auf der Timeline + Klick.
            annotations={annotations.map((a) => ({ id: a.id, start_s: a.start_s }))}
            onMarkerClick={handleMarkerClick}
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
        {/* Change 056: Playback-Bubble — läuft die Wiedergabe über eine
            Annotation, wird sie hier angezeigt (SoundCloud-Stil). Klick →
            Highlight im Thread-Bereich. */}
        {activeAnnotation && isPlaying && (
          <button
            onClick={() => setAnnHighlightId(activeAnnotation.id)}
            className="mt-2 w-full text-left flex items-start gap-1.5 rounded-sm border border-accent/40 bg-accent/5 px-2 py-1.5 hover:bg-accent/10 transition-colors"
            data-testid={`playback-annotation-${activeAnnotation.id}`}
            title={t("annot_seek_hint")}
          >
            <span aria-hidden className="text-[12px]">💬</span>
            <span className="text-[11px] text-txt leading-[1.4]">
              <span className="font-semibold">{activeAnnotation.user_name ?? t("annot_anonymous")}: </span>
              {activeAnnotation.body.length > 140
                ? `${activeAnnotation.body.slice(0, 140)}…`
                : activeAnnotation.body}
            </span>
          </button>
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
        {/* Change 045/115: Hintergrund-Alignment — Live-Details statt
            statischem Text: Heartbeat-Ampel + Worker-note („Gruppe 3/12 —
            aktiv seit 42s — CLI 45%", enthält die Align-RTF-Ausgabe). */}
        {r.status === "done" && r.alignment === "running" && (
          <div
            className="mt-2 flex items-center gap-1.5 text-[11px] text-accent/90"
            data-testid={`bg-align-${r.uid}`}
          >
            <span
              title={hb.level === "fresh" ? "Heartbeat aktiv" : hb.level === "warn" ? "Heartbeat langsam" : "kein Heartbeat"}
              className={`w-2 h-2 rounded-full shrink-0 ${
                hb.level === "fresh"
                  ? "bg-ok animate-pulse"
                  : hb.level === "warn"
                    ? "bg-warn"
                    : "bg-red-500"
              }`}
            />
            <span className="truncate">
              {phaseDetail ? (
                <>⚙ {phaseDetail}</>
              ) : (
                <>
                  <span className="animate-pulse" aria-hidden>⟳</span>{" "}
                  Präzises Alignment läuft im Hintergrund …
                  {hb.sinceBeat > 0 && (
                    <span className="text-muted2 tabular-nums">
                      {" "}· {t("phase_running_since")} {fmtSince(hb.sinceBeat)}
                    </span>
                  )}
                </>
              )}
            </span>
          </div>
        )}
        {/* Change 101: Re-Align ohne Effekt — der Aligner hat keine Wörter
            ersetzt (nicht erreichbar oder lieferte nichts). Statt der
            stillen „done“-Lüge ein sichtbarer Hinweis; Grund im Tooltip. */}
        {r.status === "done" && r.alignment === "skipped" && (
          <div
            className="mt-2 flex items-center gap-1.5 text-[11px] text-err/90"
            data-testid={`bg-align-skipped-${r.uid}`}
            title={r.error ?? undefined}
          >
            <span aria-hidden>⚠️</span>
            <span>{t("align_skipped")}</span>
          </div>
        )}
        {/* Change 057/115: Re-Diarize läuft — Live-Heartbeat („läuft seit
            Xs") statt statischem Hinweis; verschwindet beim nächsten
            Polling. */}
        {(r.status === "done" && (r.diar_status === "running" || r.diar_status === "pending")) && (
          <div
            className="mt-2 flex items-center gap-1.5 text-[11px] text-accent/90"
            data-testid={`bg-diar-${r.uid}`}
          >
            <span
              title={hb.level === "fresh" ? "Heartbeat aktiv" : hb.level === "warn" ? "Heartbeat langsam" : "kein Heartbeat"}
              className={`w-2 h-2 rounded-full shrink-0 ${
                hb.level === "fresh"
                  ? "bg-ok animate-pulse"
                  : hb.level === "warn"
                    ? "bg-warn"
                    : "bg-red-500"
              }`}
            />
            <span className="animate-pulse" aria-hidden>⟳</span>
            <span>{t("rediarize_running")}</span>
            {hb.sinceBeat > 0 && (
              <span className="text-muted2 tabular-nums">
                · {t("phase_running_since")} {fmtSince(hb.sinceBeat)}
              </span>
            )}
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
            {transcriptLoading ? (
              <div className="flex items-center gap-2 text-muted2 text-[13px] py-[6px] animate-pulse">
                <span aria-hidden>⏳</span> {t("loading_transcript")}
              </div>
            ) : hasSegments && segments ? (
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
                  // Change 102: Der Yjs-Autosave persistiert NIE die
                  // abgeleitete Anzeige (resegmentByDuration-Vorschau),
                  // sondern die DB-Segmente als Struktur-Base.
                  persistBase={segments}
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
                  onSegmentDelete={handleSegmentDelete}
                  onSplitSegment={handleSplitSegment}
                  onAnnotate={handleAnnotate}
                  // Change 077: Annotation-Text-Markierung + Scope —
                  // annotierte Passagen werden im Transkript markiert;
                  // Klick öffnet die Annotation (Scroll + Seek pausiert),
                  // `annHighlightId` steuert den Scope unten.
                  annotations={annotations}
                  activeAnnotationId={annHighlightId}
                  onAnnotateJump={(a) => {
                    setAnnHighlightId(a.id);
                    wsRef.current?.seekToPaused(a.start_s);
                  }}
                  fillHeight={!!focusMode}
                  // Change 067-Fix: Kollaboration nur bei geteilten
                  // Aufnahmen — sonst keine Yjs-Verbindung/Checks.
                  collabEnabled={!!(r.has_shares || r.is_anon_shared || r.shared_with_me)}
                />
              </>
            ) : hasText ? (
              <div className="bg-panel2 border border-border rounded-sm px-[14px] py-3 whitespace-pre-wrap leading-[1.65] max-h-[240px] overflow-y-auto scrollbar-thin text-[13.5px] text-txt break-words">
                {recText}
              </div>
            ) : (
              <div className="text-muted italic text-[13px] py-[6px]">
                {t("empty_transcript")}
              </div>
            )}
          </>
        )}
        {/* Change 056: Annotation-Threads (Markdown, Antworten, Mentions) —
            unter der Transkription; lesen können alle, schreiben/antworten
            nur mit write-Zugriff (canEdit-Prop). */}
        {hasText && (
          <div className="mt-1 px-4 pb-2">
            <AnnotationThreads
              rid={r.uid}
              annotations={annotations}
              isLoading={annQuery.isLoading}
              canEdit={canEdit}
              activeId={annHighlightId}
              onSeek={(sec) => wsRef.current?.seekToPaused(sec)}
            />
          </div>
        )}
        {r.status === "processing" && recText && (
          <div className="bg-panel2 border border-border rounded-sm px-[14px] py-3 whitespace-pre-wrap leading-[1.65] max-h-[240px] overflow-y-auto scrollbar-thin text-[13.5px] text-txt/70 break-words">
            {recText}
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
            <div className="flex flex-wrap items-center gap-1 text-[12px] mb-[6px]">
              {/* Change 035: Phasen-Chips statt nur Text — jede Phase hat
                  einen Status (erledigt/aktiv/übersprungen/offen); die
                  Prozent-Zahl bleibt als Zusatzinfo, wo sie real ist. */}
              <span className="flex flex-wrap items-center gap-1 min-w-0">
                {PHASES.map((p, i) => {
                  const active = activePhaseIndex(r);
                  const skipped = p.key === "diarization" && !r.enable_diarize;
                  let chip = "text-muted2 border-border";
                  if (skipped) chip = "text-muted2/40 border-border line-through";
                  else if (i < active) chip = "text-ok/80 border-ok/30";
                  else if (i === active) chip = "text-accent border-accent/50 bg-accent/10 animate-pulse";
                  return (
                    <span
                      key={p.key}
                      className={`text-[10px] px-[6px] py-[1px] rounded-full border font-semibold uppercase tracking-wide shrink-0 ${chip}`}
                    >
                      {t(p.labelKey)}
                      {i === active && hb.sincePhase > 0 && (
                        <span className="normal-case font-normal ml-1">
                          {t("phase_running_since")} {fmtTime(hb.sincePhase)}
                        </span>
                      )}
                    </span>
                  );
                })}
              </span>
            </div>
            {/* Live-Details (Alignment: Gruppe 3/12 · CLI 45%) */}
            {phaseDetail && (
              <div className="text-[11px] text-accent truncate mb-1" title={note}>
                ⚙ {phaseDetail}
              </div>
            )}
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
            {/* Change 092b (User 2026-08-22): Heartbeat-Ampel + echter
                ETA-Rest UNTER dem Progress-Bar (nicht neben den Chips) —
                auf schmalen Screens blieb die Zeile sonst unter den
                Chips hängen. ETA aus Dauer × RTF; Fallbacks „verarbeitet
                seit" / „aktiv seit". */}
            <div className="mt-[5px] flex items-center justify-between gap-2 text-[11px]">
              <span className="text-muted2 tabular-nums shrink-0 flex items-center gap-1.5">
                <span
                  title={hb.level === "fresh" ? "Heartbeat aktiv" : hb.level === "warn" ? "Heartbeat langsam" : "kein Heartbeat"}
                  className={`w-2 h-2 rounded-full shrink-0 ${
                    hb.level === "fresh"
                      ? "bg-ok animate-pulse"
                      : hb.level === "warn"
                        ? "bg-warn"
                        : "bg-red-500"
                  }`}
                />
                {hb.sinceBeat > 0 && (
                  <span className="text-muted2">{t("heartbeat_ago")} {hb.sinceBeat}s</span>
                )}
                <span>{r.progress_pct}%</span>
              </span>
              <span className="text-muted2 tabular-nums truncate">
                {etaRange
                  ? `${t("eta_estimated")} ${etaRange}`
                  : hb.sinceStart > 0
                    ? `${t("processing_since")} ${fmtSince(hb.sinceStart)}`
                    : hb.sincePhase > 0
                      ? fmtSince(hb.sincePhase)
                      : ""}
              </span>
            </div>
            {/* Change 011/035: Stall-Warnung nur bei totem Job (kein Heartbeat);
                Text präzisiert — „möglicherweise hängend" statt kryptisch. */}
            {hb.stalled && (
              <div className="mt-[6px] text-[12px] text-warn">
                ⚠ möglicherweise hängend · keine Aktivität {fmtSince(hb.sinceBeat)}
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
                    href={`${r.download_url}?format=${fmt.extension}${
                      segMaxDuration != null ? `&max_duration_s=${segMaxDuration}` : ""
                    }`}
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

        {/* Change 046: Re-Align-Button — nach User-Korrekturen (Ground
            Truth) die Word-Timestamps akustisch verifizieren. Nur bei
            done + Schreibzugriff; während des Laufs deaktiviert (der
            Hinweis "Präzises Alignment läuft…" erscheint oben).
            Change 113: BGM-Removal-Auswahl wie beim Re-Transcribe — bei
            Musik-Aufnahmen alignt der Forced-Aligner auf den Vocals. */}
        {r.status === "done" && hasText && canEdit && (
          <span className="flex items-center gap-1">
            <select
              value={realignSep}
              onChange={(e) => setRealignSep(e.target.value)}
              disabled={realignMut.isPending || r.alignment === "running"}
              className="bg-panel2 border border-border rounded-sm text-[11px] px-1 py-[2px] text-muted"
              title="Music Removal vor dem Re-Align (Change 113)"
            >
              <option value="none">Sep: aus</option>
              <option value="htdemucs">Sep: htdemucs</option>
              <option value="mel-band-roformer">Sep: melband</option>
            </select>
            <button
              onClick={handleRealign}
              disabled={realignMut.isPending || r.alignment === "running"}
              title={t("realign_title")}
              className="btn-ghost-sm"
            >
              <RotateCcw size={12} />
              {t("realign")}
            </button>
          </span>
        )}

        {/* Change 057: Re-Diarize-Button — Sprecher-Zuordnung neu berechnen
            (NUR speaker-Felder; Text/Wörter/Zeiten bleiben unangetastet).
            Nur bei done + Schreibzugriff; während des Laufs deaktiviert. */}
        {r.status === "done" && hasText && canEdit && (
          <button
            onClick={handleRediarize}
            disabled={
              rediarizeMut.isPending ||
              r.diar_status === "running" ||
              r.diar_status === "pending"
            }
            title={t("rediarize_title")}
            className="btn-ghost-sm"
          >
            <Users size={12} />
            {t("rediarize")}
          </button>
        )}

        {/* Share dropdown (nur Owner — Backend liefert access_level "full") */}
        {r.status === "done" && (r.access_level === "full" || r.access_level === "owner") && (
          <div ref={shareRef} className="relative inline-flex">
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
                className={`dl-menu-enter absolute ${shareFlip.up ? "bottom-[calc(100%+6px)]" : "top-[calc(100%+6px)]"} right-0 bg-panel3 border border-border2 rounded-sm p-2 min-w-[240px] max-w-[calc(100vw-16px)] z-50 shadow-[0_8px_24px_rgba(0,0,0,.4)] max-h-[min(72dvh,520px)] overflow-y-auto`}
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
                      title={t("anon_link")}
                      aria-label={t("anon_link")}
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
          <div ref={versRef} className="relative inline-flex">
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

      {/* Change 056: Annotate-Popover (Text markieren → 💬 → Kommentar).
          Overlay zentriert; zeigt die markierte Passage + Markdown-Eingabe. */}
      {annotateSel && (
        <div
          className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4"
          onClick={() => setAnnotateSel(null)}
          data-testid="annotate-popover"
        >
          <div
            className="bg-panel border border-border rounded-md p-3 max-w-md w-full shadow-xl max-h-[85dvh] overflow-y-auto"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="text-[13px] font-semibold mb-1 flex items-center gap-1.5">
              <span aria-hidden>💬</span> {t("annotate")}
            </div>
            <div className="text-[11px] text-muted2 mb-2 border-l-2 border-accent/40 pl-2 line-clamp-2 italic">
              „{annotateSel.preview}“
            </div>
            <textarea
              autoFocus
              value={annotateBody}
              onChange={(e) => setAnnotateBody(e.target.value)}
              placeholder={t("annot_placeholder")}
              className="w-full bg-panel border border-border rounded-sm px-2 py-1.5 text-[13px] text-txt outline-none focus:border-accent placeholder:text-muted2"
              rows={4}
            />
            <div className="text-[10px] text-muted2 mt-1">
              {t("annot_md_hint")} · @name {t("annot_mention_hint")}
            </div>
            <div className="flex justify-end gap-2 mt-2">
              <button
                onClick={() => setAnnotateSel(null)}
                className="btn-ghost-sm"
              >
                {t("cancel")}
              </button>
              <button
                onClick={() => void saveAnnotation()}
                disabled={annotateSaving || !annotateBody.trim()}
                className="bg-accent text-white text-[12px] px-3 py-[5px] rounded-sm font-semibold hover:opacity-90 transition-opacity disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {annotateSaving ? t("annot_saving") : t("annot_save")}
              </button>
            </div>
          </div>
        </div>
      )}
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
