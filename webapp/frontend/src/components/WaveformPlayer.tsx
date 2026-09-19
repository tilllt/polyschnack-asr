import { useEffect, useRef, useState, useCallback, useMemo, useImperativeHandle, forwardRef } from "react";
import WaveSurfer from "wavesurfer.js";
import RegionsPlugin from "wavesurfer.js/dist/plugins/regions.js";
import TimelinePlugin from "wavesurfer.js/dist/plugins/timeline.js";
import HoverPlugin from "wavesurfer.js/dist/plugins/hover.js";
import type { UpdateSide } from "wavesurfer.js/dist/plugins/regions.js";
// Change 209: Range-Marker der Nachbarwörter (Typ + Live-Vorschau-Schrumpfen).
import type { TimingNeighbor } from "../timingNeighbors";
import { useT } from "../useLocale";
import { fetchPeaks, fetchPeaksBinary, envelopeToPeaks } from "../api";
import { DetailWaveformLayer } from "./DetailWaveformLayer";
import {
  clampMoveWordTiming,
  clampWordTiming,
  effectiveMaxPps,
  fitPps,
  MIN_PPS,
  MIN_WORD_DURATION_S,
  timeFromClick,
  timingPps,
  visibleWindow,
} from "../waveformTime";

export interface WaveSurferHandle {
  seekTo: (seconds: number) => void;
  /** Seek OHNE Autoplay (2026-08-16: Cursor-Wort-Navigation springt nur). */
  seekToPaused: (seconds: number) => void;
  /** Change 208 (Timing-Modus): NUR die Wortspanne abspielen und am Ende
   *  anhalten. Der Cursor bleibt danach am Wortanfang stehen — ein
   *  anschließender Play-Druck läuft ab dem Wort weiter. */
  playRange: (start: number, end: number) => void;
  playPause: () => void;
  getCurrentTime: () => number;
  isPlaying: () => boolean;
  /** Change 2026-08-17: Playback-Rate (x0.5/x1/x2). Die Karaoke-Markierung
   *  hängt an der AUDIO-Position (getCurrentTime) — sie skaliert damit
   *  automatisch korrekt mit jeder Geschwindigkeit, ohne Speed-Faktor. */
  setPlaybackRate: (rate: number) => void;
  getPlaybackRate: () => number;
}

// ────────────────────────────────────────────────────────────────────────
// Change 049: Streaming-Playback für sehr lange Aufnahmen
// ────────────────────────────────────────────────────────────────────────
// WebAudio dekodiert die KOMPLETTE Datei in den RAM — bei 4h52min sind das
// ~560 MB PCM (16 kHz mono) → auf Mobilgeräten OOM/Timeout, Playback startet
// nie (Befund 2026-08-20). Ab 2 h nutzt der Player deshalb das
// MediaElement-Backend: das <audio>-Element streamt die Preview per
// Range-Request (Server liefert 206) — Playback startet nach wenigen
// Sekunden Pufferung, kein Voll-Download, kein Voll-Dekode, RAM ~0.
// Seek (Wort-Klick) via ws.setTime() — identische Handle-API.
// Change 112 (2026-08-23): Schwelle 2 h → 30 min. Produktions-Befund
// Android-Chrome: 95-min-Aufnahme (5710 s, 16-MB-Preview) → WebAudio-
// Voll-Dekode = ~180 MB PCM pro Karte; mehrerer Karten + Poll-Reloads
// (peaks-Referenz-Drehung, s. u.) → OOM „Aw, Snap". MediaElement ab
// 30 min eliminiert den Voll-Dekode für alle längeren Aufnahmen.
export const LARGE_FILE_THRESHOLD_S = 1800; // 30 min

export type PlayerBackend = "WebAudio" | "MediaElement";

export function resolveBackend(durationHint?: number | null): PlayerBackend {
  if (durationHint && durationHint > LARGE_FILE_THRESHOLD_S) {
    return "MediaElement";
  }
  return "WebAudio";
}

interface Props {
  audioUrl: string;
  /** Server-berechnete Peak-Envelope (2000 Werte) — WaveSurfer rendert damit
   * SOFORT, ohne die Audiodatei zu dekodieren (Mini-Preview). Ohne Peaks
   * muss WaveSurfer die ganze Datei laden → bei langen Aufnahmen langsam
   * oder Timeout („Waveform data corrupted"). */
  peaks?: number[] | null;
  /** Exakte Dauer in Sekunden — nötig, damit WaveSurfer mit Peaks die
   * Timeline korrekt skaliert, ohne die Datei erst zu dekodieren. */
  durationHint?: number | null;
  onRegionChange?: (start: number, end: number) => void;
  onTimeUpdate?: (time: number) => void;
  onPlayStateChange?: (playing: boolean) => void;
  onLoadError?: () => void;
  height?: number;
  /** Change 056: Annotationen → 💬-Marker auf der Timeline (Top-Level). */
  annotations?: { id: number; start_s: number }[];
  /** Change 056: Klick auf einen Annotation-Marker (start_s). */
  onMarkerClick?: (start_s: number) => void;
  /** Change 137 (Timing-Tab): das aktive Wort — Alignment-Timing (start/end
   *  aus dem letzten Align) + Drag-Grenzen aus den Nachbarwörtern
   *  (minStart = Ende des Vorgängers, maxEnd = Start des Folgeworts).
   *  Gesetzt → Waveform zoomt auf das Wort (~30 % der Ansicht) und zeigt
   *  die Timing-Markierung mit Start-/Ende-Handles. null = normal. */
  timingWord?: TimingWord | null;
  /** Change 209 (User-Vorgabe 19.09.2026): Range-Marker der Nachbarwörter
   *  (n-1/n+1) im selben Zoom — Kontext für das Ziehen. Wird eine Kante des
   *  aktiven Wortes über einen Nachbarn gezogen, schrumpft sie mit (der
   *  Parent rechnet das live und der Server beim Speichern). */
  timingNeighbors?: { prev: TimingNeighbor | null; next: TimingNeighbor | null } | null;
  /** Change 209: Klick oder Anfassen eines Nachbar-Markers (oder seiner
   *  Region) macht dieses Wort zum aktiven Wort. */
  onTimingSelectWord?: (segIdx: number, wordIdx: number) => void;
  /** Change 155 (Timing-Zoom): Recording-UID für progressive Peaks
   *  (GET /recordings/{rid}/peaks?length=N). Nur im Timing-Kontext nötig. */
  recordingId?: string;
  /** Change 137: Live-Update während des Handle-Drags (Anzeige im
   *  Timing-Editor). */
  onTimingChange?: (start: number, end: number) => void;
  /** Change 137: Commit nach Loslassen — der Parent persistiert per PATCH
   *  (und rollt bei Fehler zurück). */
  onTimingCommit?: (start: number, end: number) => void;
}

/** Change 137: Wort-Timing-Detail (siehe Props.timingWord). segIdx/wordIdx
 *  identifizieren das Wort — der 30 %-Zoom läuft nur beim WECHSEL des
 *  Wortes, nicht bei jeder Timing-Änderung während eines Drags. */
export interface TimingWord {
  segIdx: number;
  wordIdx: number;
  start: number;
  end: number;
  minStart?: number;
  maxEnd?: number;
}

const ZOOM_STEPS = [1, 2, 4, 6, 10, 20, 50];
/** Vertikaler Kopfraum der Wellenform in px (oben+unten, 2026-08-16). */
const WAVE_PAD = 5;

// Change 096: Preview-Fetch + -DECODE im Web-Worker — der ArrayBuffer
// (bei Worker-Decode: 16-bit-PCM-WAV, sonst Originalformat) kommt
// transferable zurück; Progress 0–100 speist den Fortschritts-Background
// (Change 095). WaveSurfer dekodiert die WAV dann in Millisekunden.
// Safari-Worker ohne OfflineAudioContext → Fallback (Originalformat).
function workerFetch(
  url: string,
  onProgress: (pct: number) => void,
): Promise<{ arrayBuffer: ArrayBuffer; wav: boolean }> {
  return new Promise((resolve, reject) => {
    try {
      const worker = new Worker(new URL("../workers/fetch.worker.ts", import.meta.url), {
        type: "module",
      });
      const done = (fn: () => void) => {
        worker.terminate();
        fn();
      };
      worker.onmessage = (
        e: MessageEvent<{
          type: string;
          pct?: number;
          arrayBuffer?: ArrayBuffer;
          wav?: boolean;
          reason?: string;
        }>,
      ) => {
        if (e.data.type === "progress" && typeof e.data.pct === "number") {
          onProgress(e.data.pct);
        } else if (e.data.type === "done" && e.data.arrayBuffer) {
          done(() =>
            resolve({ arrayBuffer: e.data.arrayBuffer as ArrayBuffer, wav: e.data.wav === true }),
          );
        } else if (e.data.type === "error") {
          done(() => reject(new Error(e.data.reason || "worker fetch failed")));
        }
      };
      worker.onerror = (e) => done(() => reject(new Error(e.message || "worker error")));
      worker.postMessage({ url });
    } catch (err) {
      reject(err);
    }
  });
}

/* ============================================================
   AUDIO-EXKLUSIVITÄT — immer nur EIN Player spielt app-weit.
   Modul-Singleton: der zuletzt gestartete Player pausiert den
   vorherigen (auch über mehrere RecordingCards/Benchmark-Samples
   hinweg). User-Anforderung 2026-08-15: „Wenn ein neues angeklickt
   wird, hört eins, das schon spielt, auf."
   ============================================================ */
type Playable = {
  pause: () => void;
  play: () => void;
  playPause: () => void;
  isPlaying: () => boolean;
  isReady: () => boolean;
};
export type { Playable };
let activePlayer: Playable | null = null;

/**
 * Pure Entscheidung für Play/Stop-Toggles (2026-08-16).
 *
 * - spielt das Audio → "pause" (Stop: Markierung bleibt exakt stehen)
 * - steht es am ENDE (finish) → "stay": Toggle lässt die Markierung am
 *   Ende stehen, statt auf 0 zu springen (WaveSurfer-`_play()` resettet
 *   sonst jede Position >= duration auf 0 — User: „beim Stoppen am Ende
 *   springt die Markierung immer zurück")
 * - nicht abspielbar (Audio noch nicht geladen/decodiert) → "noop"
 * - sonst → "play"
 */
export type PlayPauseAction = "pause" | "stay" | "play" | "noop";
export function decidePlayPause(playing: boolean, atEnd: boolean, canPlay: boolean): PlayPauseAction {
  if (playing) return "pause";
  if (atEnd) return "stay";
  if (!canPlay) return "noop";
  return "play";
}

/** Change 208 (Timing-Modus): Ist die angeforderte Wortspanne durchgelaufen?
 *  Pur gehalten (ohne WaveSurfer), damit die Abbruch-Bedingung prüfbar ist. */
export function rangeFinished(
  current: number,
  range: { start: number; end: number } | null,
): boolean {
  if (!range) return false;
  return current >= range.end;
}

/** Change 105: WS7 7.12 resumt den WebAudio-Context NIE (Autoplay-Policy:
 *  `new AudioContext()` startet auf Chrome/Android im Zustand „suspended“ —
 *  `bufferNode.start()` läuft dann stumm, obwohl der Play-State gesetzt ist.
 *  User-Befund 2026-08-23 (Android/Mobile): „Play drückbar, spielt nicht“.
 *  Vor jedem ws.play() explizit resumen (der Klick ist die User-Geste, die
 *  resume() erlaubt). */
export function ensureAudioContext(ws: WaveSurfer): void {
  try {
    const el = (ws as unknown as {
      getMediaElement?: () => {
        audioContext?: { state?: string; resume?: () => Promise<unknown> };
      };
    }).getMediaElement?.();
    const ac = el?.audioContext;
    if (ac && ac.state === "suspended") {
      ac.resume?.();
    }
  } catch {
    /* AudioContext nicht verfügbar — play versucht es trotzdem */
  }
}

/** Registriert `me` als aktiven Player und pausiert den vorherigen. */
export function claimExclusivePlayback(me: Playable): void {
  if (activePlayer && activePlayer !== me && activePlayer.isPlaying()) {
    activePlayer.pause();
  }
  // Immer merken (auch wenn nicht spielend): Space/Play-Shortcuts zielen
  // auf den zuletzt beanspruchten Player (Feature 2026-08-16).
  activePlayer = me;
}

/**
 * Setzt `me` als aktiven Player OHNE den Vorgänger zu pausieren.
 * NUR fürs Mount (Change 195): ein neu mountender Player darf kein
 * laufendes Playback eines anderen unterbrechen — nur User-Initiiertes
 * (Play-Button, Waveform-Klick) soll pausieren.
 */
export function registerActivePlayer(me: Playable): void {
  activePlayer = me;
}

/** Gibt die Exklusivität frei, wenn `me` noch der aktive Player ist. */
export function releaseExclusivePlayback(me: Playable): void {
  if (activePlayer === me) activePlayer = null;
}

/**
 * Globaler Play/Stop (Feature 2026-08-16, Space-Taste): togglet den
 * zuletzt beanspruchten Player — spielt er, wird pausiert; steht er,
 * wird gestartet. Am Ende der Aufnahme bleibt die Markierung stehen
 * (kein Auto-Reset auf 0); ohne geladenes Audio kein Play. Kein
 * aktiver Player → no-op.
 */
export function toggleActivePlayback(): void {
  const p = activePlayer;
  if (!p) return;
  p.playPause();
}

export const WaveformPlayer = forwardRef<WaveSurferHandle, Props>(
  function WaveformPlayer({ audioUrl, peaks, durationHint, onRegionChange, onTimeUpdate, onPlayStateChange, onLoadError, height = 80, annotations, onMarkerClick, timingWord = null, timingNeighbors = null, onTimingSelectWord, recordingId, onTimingChange, onTimingCommit }, ref) {
    const { t } = useT();
    const containerRef = useRef<HTMLDivElement>(null);
    // Change 072 (User-Befund 2026-08-21, „Waveforms lade endlos“ trotz 070):
    // DEADLOCK — der IntersectionObserver (Change 052) beobachtete den
    // Canvas-Container, der bis `ready` die Klasse `hidden` (display:none)
    // trägt. display:none-Elemente liefern NIE isIntersecting:true → inView
    // blieb false → der Init-Effekt (if (!inView) return) startete WaveSurfer
    // nie → ready blieb false → Container blieb hidden → „Loading waveform…“
    // für immer. Der 070-Fix (peaks als Dependency) konnte nicht greifen,
    // weil der Effekt gar nicht erst lief. Jetzt beobachtet der Observer den
    // ÄUSSEREN Wrapper (immer sichtbar, nie hidden).
    const outerRef = useRef<HTMLDivElement>(null);
    const timelineRef = useRef<HTMLDivElement>(null);
    const wsRef = useRef<WaveSurfer | null>(null);
    // Change 083: aktuell angewandte px/s (fit oder Zoomstufe) — der
    // Klick-Seek rechnet damit Scroll+Klick in Zeit um.
    const ppsRef = useRef(MIN_PPS);
    const regionsRef = useRef<RegionsPlugin | null>(null);
    const onTimeUpdateRef = useRef(onTimeUpdate);
    const onPlayStateRef = useRef(onPlayStateChange);
    // Change 049: sehr lange Aufnahmen (≥ 2 h) streamen statt voll zu
    // dekodieren — WebAudio würde ~560 MB PCM in den Handy-RAM laden.
    const backend = resolveBackend(durationHint);
    const onRegionRef = useRef(onRegionChange);
    const onLoadErrorRef = useRef(onLoadError);
    const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    // Keep refs in sync with latest props
    onTimeUpdateRef.current = onTimeUpdate;
    onPlayStateRef.current = onPlayStateChange;
    onRegionRef.current = onRegionChange;
    onLoadErrorRef.current = onLoadError;
    // ── Change 137: Timing-Tab (Wort-Markierung + 30 %-Zoom) ──
    const timingWordRef = useRef<TimingWord | null>(timingWord);
    timingWordRef.current = timingWord;
    const onTimingChangeRef = useRef(onTimingChange);
    onTimingChangeRef.current = onTimingChange;
    const onTimingCommitRef = useRef(onTimingCommit);
    onTimingCommitRef.current = onTimingCommit;
    // Change 209: Auswahl eines Nachbar-Markers.
    const onTimingSelectRef = useRef(onTimingSelectWord);
    onTimingSelectRef.current = onTimingSelectWord;
    const [timingZoom, setTimingZoom] = useState(false);
    // Crop-Auswahl-Region (✂ Transcribe): in der Timing-Ansicht ausgeblendet,
    // damit sie nicht mit den Timing-Handles um die Drag-Gesten konkurriert.
    const cropRegionRef = useRef<{ remove: () => void } | null>(null);
    const [ready, setReady] = useState(false);
    const [error, setError] = useState(false);
    const [currentTime, setCurrentTime] = useState(0);
    const [duration, setDuration] = useState(0);
    const [zoomIdx, setZoomIdx] = useState(0);
    // Spiegelt zoomIdx für Handler außerhalb von React-Render (Klick-Seek).
    const zoomIdxRef = useRef(0);
    // Change 100: true erst, wenn der AKTUELLE ws echtes Audio geladen hat
    // (ready-Event). doZoom bricht ab, wenn nicht — sonst wirft WS7
    // „Error: No audio loaded“ (Re-Init-Fenster nach Change-059-Re-Init,
    // Firefox-Konsolenbefund 2026-08-23).
    const wsReadyRef = useRef(false);
    const [playing, setPlaying] = useState(false);
    // Change 2026-08-17: Playback-Rate (x0.5/x1/x2) — State für die UI,
    // Ref für getPlaybackRate aus dem Handle (stale-closure-sicher).
    const [playRate, setPlayRate] = useState(1);
    const playRateRef = useRef(1);
    // Change 208 (Timing-Modus): angeforderte Wortspanne. Läuft sie durch,
    // hält der Player an und stellt den Cursor auf den Wortanfang zurück.
    const playRangeRef = useRef<{ start: number; end: number } | null>(null);
    // Change 208: Der Exklusiv-Player (`me`) entsteht im Init-Effekt — hier
    // gemerkt, damit die imperative Schnittstelle ihn auch nutzen kann.
    const meRef = useRef<Playable | null>(null);
    playRateRef.current = playRate;
    // Play erst möglich, wenn das echte Audio dekodiert ist (2026-08-16):
    // das `ready`-Event feuert mit Server-Peaks VOR dem Hintergrund-Decode
    // der Audiodatei — Play war also drückbar, obwohl noch nichts hörbar
    // war. `canplay` der Media-Quelle = echte Abspielbarkeit.
    const [canPlay, setCanPlay] = useState(false);
    const canPlayRef = useRef(false);
    canPlayRef.current = canPlay;
    // Change 095: Ladefortschritt (0–100) aus dem WS-"loading"-Event —
    // füllt den Background des "Loading…"-Textes als temporären Progress-Bar.
    const [loadPct, setLoadPct] = useState(0);

    // Change 199: sichtbares Zeitfenster der gezoomten View — die Detail-Ebene
    // zeichnet nur im Timing-Modus UND pausiert, braucht aber immer die
    // aktuelle Scroll-Position, um das richtige Sidecar-Fenster zu laden.
    const [viewWin, setViewWin] = useState({ start: 0, end: 0 });
    // Change 199: Zustand des Sidecars. „fehlt" ist sichtbar zu melden —
    // eine stumm bleibende dünnere Wellenform wäre von „hier ist nichts"
    // nicht zu unterscheiden (Altaufnahme, deren Nachlauf noch aussteht).
    const [sidecarStatus, setSidecarStatus] = useState<"idle" | "ok" | "fehlt">("idle");

    // Change 155 (Timing-Zoom): progressive Peaks — Cache je Länge
    // (pro Player-Instanz; die Peaks ändern sich nie).
    const peaksCacheRef = useRef(new Map<number, Promise<number[] | null>>());

    // Change 056: Annotation-Marker als Overlay im Timeline-Container.
    // wavesurfer 7.x hat KEIN Markers-Plugin (erst 8.x) — ein 8er-Upgrade
    // wäre ein Breaking-Change-Risiko für Regions/Timeline/Hover/MediaElement.
    // Stattdessen: 💬-Elemente absolut in der Timeline (left% = start_s/dur)
    // → bleiben bei Zoom (Breite wächst) und Scroll (Container) korrekt.
    // onMarkerClick per Ref (stale-closure-sicher).
    const onMarkerClickRef = useRef(onMarkerClick);
    onMarkerClickRef.current = onMarkerClick;
    const updateMarkers = useCallback(() => {
      const tl = timelineRef.current;
      if (!tl || !ready || !duration) return;
      tl.querySelectorAll("[data-ann-marker]").forEach((el) => el.remove());
      for (const a of annotations ?? []) {
        if (a.start_s > duration) continue;
        const btn = document.createElement("button");
        btn.dataset.annMarker = "1";
        btn.textContent = "💬";
        btn.title = `Annotation @ ${a.start_s.toFixed(1)}s`;
        btn.setAttribute("aria-label", `Annotation @ ${a.start_s.toFixed(1)}s`);
        btn.style.cssText =
          "position:absolute;top:-15px;left:" +
          `${(a.start_s / duration) * 100}%;` +
          "transform:translateX(-50%);font-size:11px;line-height:1;" +
          "cursor:pointer;background:transparent;border:none;padding:0;" +
          "filter:drop-shadow(0 1px 1px rgba(0,0,0,.4));";
        btn.addEventListener("click", (e) => {
          e.stopPropagation();
          onMarkerClickRef.current?.(a.start_s);
        });
        tl.appendChild(btn);
      }
    }, [annotations, ready, duration]);
    // Neu-Zeichnen bei Annotationen/Ready — Zoom läuft über doZoom.
    useEffect(() => {
      updateMarkers();
    }, [updateMarkers]);

    // ── Change 196: Timing-Markierung per WS RegionsPlugin ──
    const timingRegionRef = useRef<any>(null);
    // Change 209: Kennung des zuletzt angelegten aktiven Wortes (siehe unten).
    const prevRegionKeyRef = useRef<string | null>(null);
    // Change 209: Regionen der Nachbarwörter (n-1 / n+1).
    const neighborRegionsRef = useRef<{ prev: any; next: any }>({ prev: null, next: null });
    const neighborDataRef = useRef(timingNeighbors);
    neighborDataRef.current = timingNeighbors;

    // Change 137: Crop-Auswahl-Region (✂ Transcribe) in der Timing-Ansicht
    // ausblenden (Change 196: jetzt auch Timing-Region verwalten).
    useEffect(() => {
      const regionsPlugin = regionsRef.current;
      if (!regionsPlugin || !ready) return;

      if (timingWord) {
        // Crop entfernen (wie bisher)
        if (cropRegionRef.current) {
          cropRegionRef.current.remove();
          cropRegionRef.current = null;
        }
        // Timing-Region anlegen (falls noch nicht)
        if (!timingRegionRef.current) {
          const dur = wsRef.current?.getDuration?.() ?? 0;
          if (dur > 0 && timingWord.start < dur && timingWord.end <= dur) {
            const region = (regionsPlugin as any).addRegion({
              start: timingWord.start,
              end: timingWord.end,
              color: "rgba(46,160,67,0.18)",
              drag: true,
              resize: true,
              minLength: MIN_WORD_DURATION_S,
            });
            // Live-Constraint-Clamping bei Update
            region.on("update", (side?: UpdateSide) => {
              const tw = timingWordRef.current;
              if (!tw) return;
              const s = region.start, e = region.end;
              const clamped = side === "start" || side === "end"
                ? clampWordTiming(s, e, tw.minStart, tw.maxEnd, MIN_WORD_DURATION_S)
                : clampMoveWordTiming(tw.start, tw.end, s - tw.start, tw.minStart, tw.maxEnd, MIN_WORD_DURATION_S);
              if (clamped.start !== s || clamped.end !== e) {
                region.setOptions({ start: clamped.start, end: clamped.end });
              }
              onTimingChangeRef.current?.(clamped.start, clamped.end);
            });
            // Commit nach Loslassen
            region.on("update-end", () => {
              const r = timingRegionRef.current;
              if (r) onTimingCommitRef.current?.(r.start, r.end);
            });
            timingRegionRef.current = region;
          }
        }
      } else {
        // Timing-Region entfernen
        if (timingRegionRef.current) {
          timingRegionRef.current.remove();
          timingRegionRef.current = null;
        }
        // Crop wiederherstellen (wie bisher)
        if (!cropRegionRef.current) {
          const dur = wsRef.current?.getDuration?.() ?? 0;
          if (dur > 0) {
            cropRegionRef.current = (regionsPlugin as any).addRegion({
              start: 0,
              end: dur,
              color: "rgba(46,160,67,0.03)",
              drag: true,
              resize: true,
            });
          }
        }
      }
    }, [timingWord, ready]);

    // Change 209 (Nebenfund): Die aktive Timing-Markierung wurde nur EINMAL
    // angelegt und blieb beim Wechsel des Wortes am alten Wort stehen — hier
    // wandert sie mit. Während eines Drags bleibt die Kennung gleich, laufende
    // Gesten werden also nicht angefasst.
    useEffect(() => {
      if (!timingWord || !timingRegionRef.current) return;
      const key = `${timingWord.segIdx}:${timingWord.wordIdx}`;
      if (prevRegionKeyRef.current === key) return;
      prevRegionKeyRef.current = key;
      try {
        timingRegionRef.current.setOptions({
          start: timingWord.start,
          end: timingWord.end,
        });
      } catch {
        /* setOptions nicht verfügbar — Region bleibt an alter Stelle */
      }
    }, [timingWord, ready]);

    // ── Change 209: Range-Marker der Nachbarwörter (n-1 / n+1) ──
    useEffect(() => {
      const plugin = regionsRef.current as any;
      const mine = neighborRegionsRef.current;
      const clear = (which: "prev" | "next") => {
        if (mine[which]) {
          try {
            mine[which].remove();
          } catch {
            /* schon entfernt */
          }
          mine[which] = null;
        }
      };

      if (!timingWord || !ready || !plugin) {
        clear("prev");
        clear("next");
        return;
      }

      const make = (which: "prev" | "next", n: TimingNeighbor) => {
        const region = mine[which];
        if (!region) {
          const dur = wsRef.current?.getDuration?.() ?? 0;
          if (dur > 0 && n.start >= 0 && n.end <= dur) {
            const created = plugin.addRegion({
              start: n.start,
              end: n.end,
              // Blasser als das aktive Wort (grün) — reiner Kontext.
              color: "rgba(139,148,158,0.22)",
              drag: false,
              resize: true, // sichtbare Marker; Anfassen macht das Wort aktiv
              minLength: MIN_WORD_DURATION_S,
            });
            // Klick, Anfassen oder Ziehen eines Nachbar-Markers: dieses Wort
            // wird das aktive Wort. Bewusst OHNE eigenen Timing-Commit — der
            // Zoom lädt es neu, gezogen wird dann an seinen Handles.
            const select = () => {
              const cur = neighborDataRef.current?.[which];
              if (cur) onTimingSelectRef.current?.(cur.segIdx, cur.wordIdx);
            };
            created.on("click", select);
            created.on("update", select);
            const el = created.element as HTMLElement | undefined;
            if (el) {
              el.style.cursor = "pointer";
              el.addEventListener("pointerdown", select);
            }
            mine[which] = created;
          }
        } else {
          try {
            region.setOptions({ start: n.start, end: n.end });
          } catch {
            /* setOptions nicht verfügbar */
          }
        }
      };

      if (timingNeighbors?.prev) make("prev", timingNeighbors.prev);
      else clear("prev");
      if (timingNeighbors?.next) make("next", timingNeighbors.next);
      else clear("next");
    }, [timingWord, timingNeighbors, ready]);

    const doZoom = useCallback((ws: WaveSurfer, idx: number) => {
      // Change 100: kein zoom() ohne geladenes Audio — WS7 wirft sonst
      // „Error: No audio loaded“ (z. B. im Re-Init-Fenster nach asynchron
      // nachgelieferten Peaks, Change 059).
      if (!wsReadyRef.current) return;
      // Change 083: Index 0 = „fit“ (ganze Audiolänge sichtbar, exakter
      // px/s-Wert statt Runden auf die kleinste Zoomstufe); danach die
      // festen Stufen ZOOM_STEPS.
      const pps =
        idx === 0
          ? fitPps(containerRef.current?.clientWidth ?? 800, ws.getDuration())
          : ZOOM_STEPS[idx - 1];
      ppsRef.current = pps;
      ws.zoom(pps);
      setZoomIdx(idx);
      zoomIdxRef.current = idx;
      // Change 056: Timeline-Breite hat sich geändert → Marker neu setzen.
      updateMarkers();
      // Change 2026-09-15: Progressive Peaks auch beim manuellen Zoom —
      // ab 10× sind 2000 Basispunkte pixelig.
      if (recordingId && idx >= 3) {
        const dur = ws.getDuration?.() ?? 0;
        const needed = Math.min(
          300000,
          Math.max(2000, Math.ceil(pps * Math.max(dur, 1))),
        );
        if (needed > 2000) {
          const cache = peaksCacheRef.current;
          let prom = cache.get(needed);
          if (!prom) {
            prom = fetchPeaks(recordingId, needed).catch(() => null);
            cache.set(needed, prom);
          }
          void prom.then((fine) => {
            if (!fine || fine.length <= 2000 || !wsReadyRef.current) return;
            const w = wsRef.current;
            if (!w) return;
            try {
              (w as any).setPeaks?.([fine]);
              w.zoom(pps);
            } catch {/* WS7 ohne Audio — ignoriert */}
            
          });
        }
      }
    }, [updateMarkers, recordingId]);

    // Change 199: residentes Envelope aus dem Sidecar. Es trägt die Timeline
    // (ersetzt die 2000-Punkte-Basis) und liefert — anders als der feste
    // 300.000er-Deckel, der mit der Aufnahmelänge verfällt — auf jeder Länge
    // dieselbe Balkenzahl im Maximalzoom, weil das Budget mit der Dauer
    // skaliert. Fehlt das Sidecar (Bestandsaufnahme vor dem Nachlauf),
    // bleiben die JSON-Peaks stehen; der Zustand wird gemeldet statt
    // verschwiegen.
    useEffect(() => {
      if (!ready || !recordingId) return;
      let cancelled = false;
      fetchPeaksBinary(recordingId, "res")
        .then((bytes) => {
          if (cancelled || !wsReadyRef.current || bytes.length === 0) return;
          const cur = wsRef.current as unknown as {
            setPeaks?: (p: Array<Float32Array | number[]>) => void;
          };
          if (!cur?.setPeaks) return;
          cur.setPeaks([envelopeToPeaks(bytes)]);
          setSidecarStatus("ok");
        })
        .catch(() => {
          if (!cancelled) setSidecarStatus("fehlt");
        });
      return () => {
        cancelled = true;
      };
    }, [ready, recordingId]);

    // Change 199: Scroll-Position für die Detail-Ebene verfolgen. Der Scroller
    // ist das Elternelement des WS-Wrappers — dort feuert 'scroll' bei
    // Mausrad, Trackpad und Programm-Scroll (Timing-Sprung zentriert das
    // Wort per setScroll).
    useEffect(() => {
      if (!ready || !timingZoom) return;
      const w = wsRef.current;
      if (!w) return;
      const wrap = (w as unknown as { getWrapper?: () => HTMLElement }).getWrapper?.();
      const scroller = wrap?.parentElement ?? null;
      if (!scroller) return;
      const onScroll = () => {
        const cw = containerRef.current?.clientWidth ?? 800;
        setViewWin(
          visibleWindow(cw, w.getScroll?.() ?? 0, ppsRef.current, w.getDuration?.() ?? 0),
        );
      };
      onScroll();
      scroller.addEventListener("scroll", onScroll, { passive: true });
      return () => scroller.removeEventListener("scroll", onScroll);
    }, [ready, timingZoom]);

    // Change 137: 30 %-Zoom beim WECHSEL des Timing-Wortes (nicht bei jeder
    // Timing-Änderung während eines Drags — das würde den Zoom springen
    // lassen). Ohne Wort → zurück zu „fit“.
    const prevTimingWordKeyRef = useRef<string | null>(null);
    useEffect(() => {
      if (!ready || !wsReadyRef.current || !wsRef.current) return;
      const tw = timingWord;
      const key = tw ? `${tw.segIdx}:${tw.wordIdx}` : null;
      if (key === prevTimingWordKeyRef.current) return;
      prevTimingWordKeyRef.current = key;
      const w = wsRef.current;
      if (tw) {
        const width = containerRef.current?.clientWidth ?? 800;
        // Change 199: die echte Obergrenze ist die Browser-Breite
        // (2^25 / Dauer), nicht MAX_TIMING_PPS — auf langen Dateien würde
        // sonst ein Zoom angefordert, den der Browser still kappt.
        const pps = timingPps(
          width,
          Math.max(tw.end - tw.start, 1e-3),
          MIN_PPS,
          effectiveMaxPps(w.getDuration?.() ?? duration),
        );
        ppsRef.current = pps;
        // Change 142: Im Timing-Zoom sind die Balken (barWidth 2/gap 1) zu
        // gestreckten Strichen mit Lücken entartet — man erkennt das Wort
        // nicht mehr. Durchgehende Wellenform (barWidth 0 = gefüllte Kurve);
        // setOptions VOR zoom, damit der Render die neuen Optionen nutzt.
        try {
          w.setOptions({ barWidth: 0, barGap: 0, barRadius: 0 });
        } catch {
          /* setOptions nicht verfügbar — Zoom läuft mit bisheriger Optik */
        }
        w.zoom(pps);
        setTimingZoom(true);
        // Change 155: progressive Peaks — MediaElement-Backend (> 30 min)
        // dekodiert NICHT → die 2000-Punkt-Basis begrenzt den Zoom hart.
        // Feinere Peaks nachladen (einmal je Länge, Browser-Cache) →
        // setPeaks + zoom, damit der 30-%-Wort-Zoom auch bei langen
        // Aufnahmen greift. Schlägt der Fetch fehl, bleibt der bestehende
        // Zoom (Basis-Auflösung) — optional.
        const wDur = w.getDuration?.() ?? duration;
        const needed = Math.min(
          300000,
          Math.max(2000, Math.ceil(pps * Math.max(wDur, 1))),
        );
        if (recordingId && needed > 2000) {
          const cache = peaksCacheRef.current;
          let prom = cache.get(needed);
          if (!prom) {
            prom = fetchPeaks(recordingId, needed).catch(() => null);
            cache.set(needed, prom);
          }
          void prom.then((fine) => {
            if (!fine || fine.length <= 2000 || !wsReadyRef.current) return;
            try {
              const cur = wsRef.current as unknown as {
                setPeaks?: (p: Array<Float32Array | number[]>) => void;
                zoom?: (pps: number) => void;
              };
              cur?.setPeaks?.([fine]);
              cur?.zoom?.(ppsRef.current);
            } catch {
              /* setPeaks nicht verfügbar — Basis-Peaks bleiben */
            }
            
          });
        }
        
        try {
          // Change 2026-09-15: Center the word in the visible view
          w.setTime(tw.start);
          // Calculate scroll position so the word appears centered
          // (word midpoint at 50% of the visible width)
          const wDur = w.getDuration?.() ?? 0;
          const cw = containerRef.current?.clientWidth ?? 800;
          const wordMid = (tw.start + tw.end) / 2;
          const targetScroll = Math.max(0, pps * wordMid - cw / 2);
          if (wDur > 0 && targetScroll >= 0) {
            (w as any).setScroll?.(targetScroll);
            // Change 199: Fenster sofort setzen — der Scroll-Listener feuert
            // bei programmatischem setScroll nicht in jedem Browser.
            setViewWin(visibleWindow(cw, targetScroll, pps, wDur));
          }
        } catch {
          /* WS7 noch ohne geladenes Audio — Seek überspringen */
        }
      } else {
        setTimingZoom(false);
        // Change 142: zurück zur Balken-Optik (Kopfraum-Design).
        try {
          w.setOptions({ barWidth: 2, barGap: 1, barRadius: 2 });
        } catch {
          /* setOptions nicht verfügbar */
        }
        doZoom(w, 0);
      }
    }, [ready, timingWord, doZoom]);

    // Change 083-Fix (2026-08-22): Initial-Zoom erst NACH dem
    // Sichtbarwerden. Der ready-Handler lief mit display:none-Container
    // (hidden bis ready → clientWidth 0) → fitPps fiel auf MIN_PPS:
    // Welle nur 285 px statt Container-Breite und der Klick-Seek um
    // Faktor ~3,4 verzerrt („Klick bei 9 min → Playback bei 31 min“).
    // Change 100 (Zoom-Reset 2026-08-23): Der Effekt darf NUR EINMAL
    // feuern. doZoom hängt an updateMarkers ← [annotations, ready,
    // duration] — späte asynchrone Detail-Daten (Peaks/Annotations,
    // Change 059) ändern die doZoom-Referenz erneut → der Effekt rief
    // doZoom(0) und verwarf jeden User-Zoom (Repro: Zoom-in → nach
    // ~300 ms wieder „fit“). initialZoomRef sperrt den Initial-Fit.
    const initialZoomRef = useRef(false);
    useEffect(() => {
      if (ready && !error && wsRef.current && !initialZoomRef.current) {
        initialZoomRef.current = true;
        doZoom(wsRef.current, 0);
      }
    }, [ready, error, doZoom]);

    // Change 052: Lazy-Loading — Audio erst laden, wenn der Player in den
    // Viewport kommt (IntersectionObserver, 200 px Vorlauf). Ohne das
    // fetchen beim Öffnen einer Benchmark-Kategorie ALLE Sample-Player
    // gleichzeitig (belegt: 8× Preview-Request in einem Schub) — bei
    // langsamem Netz queueen die Requests und der Play-Klick bleibt
    // wirkungslos, weil die Datei noch nicht geladen ist.
    const [inView, setInView] = useState(false);
    useEffect(() => {
      // Change 072: outerRef statt containerRef beobachten — der Container
      // ist bis `ready` hidden (display:none) und liefert nie eine
      // Intersection; der Wrapper ist immer sichtbar.
      const el = outerRef.current;
      if (!el) return;
      if (typeof IntersectionObserver === "undefined") {
        setInView(true); // jsdom/ohne IO: sofort laden (Tests, alte Browser)
        return;
      }
      const obs = new IntersectionObserver(
        (entries) => {
          for (const e of entries) {
            if (e.isIntersecting) {
              setInView(true);
              obs.disconnect();
            }
          }
        },
        { rootMargin: "200px" },
      );
      obs.observe(el);
      return () => obs.disconnect();
    }, []);

    // Change 112 (2026-08-23, Android-Oszillations-Befund): Die Karten-Polls
    // (Status/ETA) liefern bei jedem Fetch ein NEUES `peaks`-Array mit
    // identischem Inhalt → der Load-Effekt (Dependency `peaks`) brach den
    // laufenden Fetch/Decode ab und startete ihn neu: Kurve leer 1–3 s
    // („verschwindet/erscheint periodisch"), ~180 MB PCM-Allokation pro
    // Reload bei 95-min-Audios → kumuliert OOM „Aw, Snap" auf Android.
    // Signatur statt Referenz: triggert nur bei echten Inhalt-Wechseln
    // (async nachgelieferte Peaks, Change 059) — nicht bei Referenz-
    // Drehungen durch Polls.
    const peaksSignature = useMemo(() => {
      if (!peaks || peaks.length === 0) return "";
      return `${peaks.length}:${peaks[0]}:${peaks[peaks.length - 1]}`;
    }, [peaks]);

    useEffect(() => {
      if (!containerRef.current) return;
      if (!inView) return; // Change 052: erst laden, wenn sichtbar

      let cancelled = false;

      const regions = RegionsPlugin.create();
      const timeline = TimelinePlugin.create({ container: timelineRef.current! });
      const hover = HoverPlugin.create();
      let ws: WaveSurfer;

      try {
        ws = WaveSurfer.create({
          container: containerRef.current,
          backend: backend,
          // Change 077 (Playback-Regression 2026-08-21): WaveSurfer-Default
          // `interact:true` startet beim Klick auf die Waveform sofort Play —
          // auch wenn die Audio-Datei noch nicht geladen/dekodiert ist
          // (Cursor läuft über die Server-Peaks, aber kein Ton). Interact
          // aus; der eigene Click-Handler unten sucht + spielt NUR bei
          // canPlay (echter Decode-Buffer vorhanden).
          interact: false,
          waveColor: "rgba(46,160,67,0.35)",
          progressColor: "rgba(46,160,67,0.85)",
          cursorColor: "#2ea043",
          cursorWidth: 1,
          barWidth: 2,
          barGap: 1,
          barRadius: 2,
          // Kopfraum auf Canvas-Ebene (2026-08-16): Der Container hat
          // 5px vertikales Padding (siehe render), die Canvas-Höhe ist
          // height-2*PAD. Dadurch berühren die Balken die Oberkante nie —
          // egal ob WaveSurfer aus den Server-Peaks (Mini-Preview) oder
          // nach dem Decode aus dem Audio zeichnet (WaveSurfer verwirft
          // die Peaks nach erfolgreichem Decode! Der alte Ansatz, die
          // Peaks clientseitig auf 88 % zu skalieren, wirkte nur im
          // Preview und die Wellenform war nach dem Laden wieder hart
          // abgeschnitten).
          height: Math.max(20, height - 2 * WAVE_PAD),
          normalize: false,
          // Change 083: minPxPerSec auf MIN_PPS (0.05) gesenkt — vorher
          // erzwang 1 px/s bei langen Audios einen Ausschnitt statt Fit.
          minPxPerSec: MIN_PPS,
          plugins: [regions, timeline, hover],
        });
      } catch (e) {
        setError(true);
        setReady(true);
        onLoadErrorRef.current?.();
        return;
      }

      // Peaks + Dauer vom Server → Waveform rendert sofort (Mini-Preview),
      // ohne die komplette Audiodatei im Browser zu dekodieren. WaveSurfer
      // erwartet peaks als Array-of-Channels: [peaks] = Mono. Nur wenn BEIDE
      // da sind (ohne durationHint kann WaveSurfer die Timeline nicht
      // skalieren — dann lieber selbst dekodieren).
      const hasPeaks = !!(peaks && peaks.length > 0 && durationHint && durationHint > 0);
      // Change 198: EINE Entscheidung für beide Stellen (Fetch-Pfad UND
      // Fortschritts-Anzeige) — sonst läuft die Anzeige der Ladelogik
      // hinterher. Worker nur im WebAudio-Modus (s. Begründung unten).
      const useWorker = backend === "WebAudio" && typeof Worker !== "undefined" && !!audioUrl;
      const doLoad = (url: string) => {
        ws.load(
          url,
          hasPeaks ? [peaks as number[]] : undefined,
          hasPeaks ? (durationHint as number) : undefined,
        );
      };
      try {
        // Peaks roh übergeben — der Kopfraum kommt aus dem Container-Padding
        // (WaveSurfer zeichnet nach dem Decode ohnehin aus dem Audio, eine
        // Client-Skalierung der Peaks wäre nach dem Decode wirkungslos).
        // Change 096: Der Netz-Fetch läuft im Web-Worker (kein Buffer-
        // Handling auf dem JS-Main-Thread); WS lädt das Blob — genau EIN
        // Fetch, kein doppelter Decode (WS dekodiert das Blob wie gehabt
        // im Browser-Audio-Thread). Worker nicht verfügbar / Fehler →
        // direkter WS-Fetch (bisheriges Verhalten).
        // Change 198: NUR im WebAudio-Modus. Im MediaElement-Modus (lange
        // Aufnahmen, s. resolveBackend) hat der Worker den Zweck verfehlt:
        // er lud die KOMPLETTE Datei (bei 98 min: 47 MB) herunter, um sie
        // dann als blob:-URL zu übergeben — ein Blob kennt keine
        // Range-Requests, damit war das Streaming-Backend wirkungslos und
        // ein abgebrochener Download wurde (mangels Längenprüfung) still zu
        // einem kürzeren Audio dekodiert → korrupte Welle ohne Fehlermeldung.
        // MediaElement streamt die URL jetzt direkt: Range-Requests,
        // Pufferung und Wiederholung macht der Browser selbst; die Welle
        // kommt weiterhin sofort aus den Server-Peaks.
        if (useWorker) {
          workerFetch(audioUrl, (pct) => {
            if (!cancelled) setLoadPct(pct);
          })
            .then(({ arrayBuffer: buf, wav }) => {
              if (cancelled) return;
              // Worker-Decode → unkomprimierte WAV (WS-decode trivial);
              // sonst Originalformat (Opus-Preview / Alt-MP3).
              const mime = wav
                ? "audio/wav"
                : audioUrl.toLowerCase().endsWith(".opus")
                  ? "audio/ogg"
                  : "audio/mpeg";
              const blobUrl = URL.createObjectURL(new Blob([buf], { type: mime }));
              doLoad(blobUrl);
            })
            .catch(() => {
              if (cancelled) return;
              doLoad(audioUrl);
            });
        } else {
          doLoad(audioUrl);
        }
      } catch (e) {
        setError(true);
        setReady(true);
        onLoadErrorRef.current?.();
        return;
      }

      // Timeout safety net — mit Server-Peaks rendert WaveSurfer die Welle
      // sofort, ABER `ready` kommt trotzdem erst NACH dem Decode (WS
      // dekodiert die Datei immer, auch mit Peaks). OHNE Peaks muss der
      // Browser die ganze Datei dekodieren (WebAudio).
      // Change 097 (Ruben-Review 24.08., User-Befund „30 s bis Play"): Der
      // alte 10-s-Wert (mit Peaks) ging fälschlich von sofortigem ready aus
      // → bei Decodes > 10 s feuerte der Timeout → onLoadError → Wechsel auf
      // die volle Original-Datei → doppelter Load (AbortError) + noch
      // längerer Decode. Der Timeout ist jetzt ein reines Netz-/Decode-
      // Sicherheitsnetz (60 s) und löst KEIN onLoadError aus (kein Wechsel
      // auf die volle Datei — die Preview ist die richtige Wahl; echte
      // Preview-Fehler meldet ws.on("error")). Ein späteres `ready` heilt
      // den Timeout-Fehlerzustand (setError(false) im ready-Handler).
      // Change 049: MediaElement streamt (kein Decode) — aber der erste
      // Preview-Zugriff kann den Server-ffmpeg synchron triggern (Minuten
      // bei sehr langen Dateien) → grosszuegiger Timeout, der Fehlerpfad
      // bleibt ws.on("error").
      const loadTimeoutMs = backend === "MediaElement" ? 120000 : 60000;
      timerRef.current = setTimeout(() => {
        if (!cancelled) {
          setError(true);
          setReady(true);
        }
      }, loadTimeoutMs);

      // WaveSurfer fires "error" when audio fails to load/decode
      ws.on("error", () => {
        if (cancelled) return;
        if (timerRef.current) clearTimeout(timerRef.current);
        setError(true);
        setReady(true);
        onLoadErrorRef.current?.();
      });

      ws.on("ready", () => {
        if (cancelled) return;
        if (timerRef.current) clearTimeout(timerRef.current);
        setError(false); // Change 097: heilt einen Timeout-Fehlerzustand
        setReady(true);
        wsReadyRef.current = true; // Change 100: echtes Audio geladen
        setLoadPct(100); // geladen — der Progress-Background ist voll
        const dur = ws.getDuration();
        setDuration(dur);
        // Initial-Zoom läuft in einem useEffect auf `ready` (NACH dem
        // React-Commit) — hier ist der Container noch display:none
        // (hidden bis ready), clientWidth=0 → fitPps fiele auf MIN_PPS
        // (Welle 285 px statt Container-Breite; Klick-Seek verzerrt um
        // Faktor ~3,4: „Klick bei 9 min → Playback bei 31 min“).
        // Change 137: Die Crop-Auswahl-Region (✂ Transcribe) legt ein
        // eigener Effekt an (timingWord-abhängig ausgeblendet).
      });

      // Change 095: Ladefortschritt des Audio-Fetches (0–100) — füllt den
      // Hintergrund des "Loading…"-Textes als temporären Progress-Bar.
      // Change 096: im Worker-Fetch-Pfad liefert der Worker den Fortschritt
      // (der WS-"loading"-Event des Blobs wäre nur ein instanter 0→100).
      // Change 198: ohne Worker (MediaElement streamt direkt) liefert WS den
      // echten Fortschritt — Bedingung an `useWorker` gekoppelt, damit die
      // Anzeige nicht hinter der Ladelogik zurückbleibt.
      if (!useWorker) {
        ws.on("loading", (pct: number) => {
          if (cancelled) return;
          setLoadPct(pct);
        });
      }

      // Change 196: Scroll (gezoomte View) verschiebt das sichtbare Fenster —
      // die Timing-Region passt sich automatisch an (WS Region nativ).

      ws.on("timeupdate", (t) => {
        // Fix 2026-08-17 (Space-Stop-Sprung): WaveSurfer 7 feuert beim Pause
        // ueber initReactiveState ein timeupdate mit 0 — das interne
        // _currentTime-Signal (Initialwert 0) wird nie von WebAudio-Media-
        // timeupdate aktualisiert, nur der WS-Timer emittiert laufend echte
        // Werte. Unser Handler uebernahm die 0 blind → Karaoke-Markierung
        // sprang zum Playback-Start (live reproduziert: 2.662 → 0.000).
        // Die echte Position (getCurrentTime, aus playbackPosition) ist
        // korrekt — 0 nur akzeptieren, wenn wirklich am Anfang.
        const real = ws.getCurrentTime();
        if (t === 0 && real > 0.05) t = real;
        setCurrentTime(t);
        onTimeUpdateRef.current?.(t);
      });
      // Audio-Exklusivität: Start dieses Players pausiert jeden anderen.
      const me: Playable = {
        pause: () => ws.pause(),
        play: () => { if (canPlayRef.current) { ensureAudioContext(ws); ws.play(); } },
        playPause: () => {
          const playing = ws.isPlaying();
          const atEnd = ws.getDuration() > 0 && ws.getCurrentTime() >= ws.getDuration() - 0.02;
          const action = decidePlayPause(playing, atEnd, canPlayRef.current);
          if (action === "pause") ws.pause();
          else if (action === "stay") ws.setTime(ws.getDuration());
          else if (action === "play") { ensureAudioContext(ws); ws.play(); }
          // "noop": Audio noch nicht abspielbar → nichts
        },
        isPlaying: () => ws.isPlaying(),
        isReady: () => canPlayRef.current,
      };
      // Abspielbarkeit (Fix 2026-08-18, korrigiert 2026-08-22): Polling auf
      // den ECHTEN Playback-Puffer statt ws.getDecodedData(). WS 7.12+
      // erzeugt decodedData im Peaks-Pfad SOFORT aus den Server-Peaks
      // (createBuffer) — getDecodedData() ist damit KEIN Indikator mehr für
      // geladenes Audio; der Play-Button war wieder drückbar, bevor die
      // Datei geladen/dekodiert war (Regression, User-Befund 22.08.:
      // „Play drücken, nichts passiert“). Echte Abspielbarkeit:
      // WebAudio: der decodeAudioData-Puffer des Media-Elements (.buffer)
      // MediaElement: readyState >= 3 (HAVE_FUTURE_DATA, wie gehabt).
      // Change 095 (Regression 2026-08-23): canPlay NUR mit ECHTEM
      // Decode-Beweis. Der reine buffer-Poll ist nicht zuverlässig:
      // WS 7.12 erzeugt im Peaks-Pfad decodedData SOFORT per
      // createBuffer(peaks, duration) — getMediaElement().buffer kann
      // also ein stummer Fake sein (User-Befund: „man kann wieder in die
      // Waveform klicken bevor das Audio geladen ist" — die UI reagierte,
      // aber kein Ton). Echter Beweis: das WS-"decode"-Event (feuert nach
      // decodeAudioData) bzw. readyState>=3 beim MediaElement-Backend.
      let decodePoll: number | undefined;
      if (backend === "MediaElement") {
        decodePoll = window.setInterval(() => {
          if (cancelled) return;
          try {
            const el = (ws as unknown as { getMediaElement?: () => HTMLMediaElement | null })
              .getMediaElement?.();
            if (el && el.readyState >= 3) {
              window.clearInterval(decodePoll);
              setCanPlay(true);
            }
          } catch {
            window.clearInterval(decodePoll);
          }
        }, 300);
      } else {
        ws.on("decode", () => {
          if (cancelled) return;
          setCanPlay(true);
        });
      }
      // Timeout-Netz: wird canPlay nie true (Netz hängt, Datei fehlt,
      // Decode schlägt fehl), kommt ein SICHTBARER Fehler statt eines
      // Endlos-Spinners („stille Fehler inakzeptabel“, 2026-08-18).
      // 90s, weil der Server die Preview-MP3 beim ersten Zugriff synchron
      // generieren kann (ffmpeg) — der Request dauert dann einmalig länger.
      const canPlayTimeout = window.setTimeout(() => {
        if (cancelled) return;
        window.clearInterval(decodePoll);
        if (!canPlayRef.current) {
          setError(true);
          setReady(true);
          onLoadErrorRef.current?.();
        }
      }, 90000);
      // Beim Mount als aktiven Player merken (zuletzt geöffnete Card) —
      // damit der globale Play/Stop-Shortcut (Space) ein Ziel hat, auch
      // bevor je ein Play lief. Cleanup gibt die Exklusivität frei.
      // Change 195: NICHT claimExclusivePlayback — pausiert den Vorgänger
      // nicht beim Mount (das passiert erst beim Play).
      registerActivePlayer(me);
      meRef.current = me; // Change 208: für die imperative Schnittstelle
      ws.on("play", () => {
        claimExclusivePlayback(me);
        setPlaying(true);
        onPlayStateRef.current?.(true);
        startSync();
      });
      // WICHTIG (2026-08-16): pause/finish geben die Exklusivität NICHT
      // frei — releaseExclusivePlayback würde activePlayer auf null setzen,
      // und der globale Play/Stop-Shortcut (Space) hätte nach dem ersten
      // Stop kein Ziel mehr („stop per space → space startet nicht wieder").
      // claimExclusivePlayback beim play überschreibt den aktiven Player
      // ohnehin; release bleibt nur fürs Unmount/destroy.
      ws.on("pause", () => {
        setPlaying(false);
        onPlayStateRef.current?.(false);
      });
      ws.on("finish", () => {
        setPlaying(false);
        onPlayStateRef.current?.(false);
      });

      regions.on("region-updated", (r) => onRegionRef.current?.(r.start, r.end));

      // ── Change 077: eigener Waveform-Klick (interact:false ersetzt) ──
      // WaveSurfer-`interact` ist aus (kein Play vor Decode). Klick auf die
      // Waveform sucht zur Position und spielt NUR bei canPlay (echter
      // Decode-Buffer/MediaElement readyState>=3); sonst nur Seek pausiert.
      // So funktioniert „klicken zum Hören" wie gewohnt, aber nie stumm.
      const onContainerClick = (e: MouseEvent) => {
        if (!canPlayRef.current) return; // kein Play-Pfad vor Decode
        const el = containerRef.current;
        if (!el) return;
        const rect = el.getBoundingClientRect();
        if (rect.width <= 0) return;
        const dur = ws.getDuration();
        if (!(dur > 0)) return;
        // Change 083-Fix (2026-08-22): px/s im Fit-Modus (idx 0) LIVE aus
        // der aktuellen Container-Breite — robust gegen Layout-Änderungen
        // nach dem Initial-Zoom (der frühere fixe ppsRef-Wert verzerrte
        // den Seek um Faktor 3,4: „Klick bei 9 min → 31 min“).
        const pps =
          zoomIdxRef.current === 0 ? fitPps(el.clientWidth, dur) : ppsRef.current;
        const t = timeFromClick(
          e.clientX - rect.left,
          ws.getScroll?.() ?? 0,
          pps,
          dur,
        );
        ws.setTime(t);
        // Change 093 (User 2026-08-22): Seek SOFORT an die Karte melden —
        // vorher hing das Transkript-Scroll/Karaoke-Highlight am nächsten
        // timeupdate/rAF-Tick, der nur feuert, wenn ws.play() wirklich
        // startet (WebAudio-Kontext/Puffer). Startet es nicht sofort
        // (z. B. Android-Kontext), blieb die Transkription an der alten
        // Stelle, obwohl der Cursor gesprungen war.
        setCurrentTime(t);
        onTimeUpdateRef.current?.(t);
        // Change 105: setTime darf den Seek/Scroll nicht blockieren — bei
        // nicht korrekt initialisiertem WS7 (z. B. Container-0-Breite vor
        // Change 105) wirft WS7 „No audio loaded“ und der Handler bräche
        // VOR dem Transkript-Scroll ab (User: „Klick scrollt nicht“).
        try {
          ws.setTime(t);
        } catch {
          /* WS7 noch ohne geladenes Audio — Seek überspringen */
        }
        // Change 104: KEIN ws.play() ohne abspielbares Audio — während der
        // Decode noch läuft (canPlay=false, Play-Button grau) würde der
        // Klick den Play-State setzen (Flicker zum Pause-Symbol), aber kein
        // Ton startet (User-Befund 2026-08-23). Nur Seek + Transkript-Scroll.
        // Change 195: claimExclusivePlayback VOR ws.play() — pausiert den
        // vorherigen Player direkt, unabhängig vom WS7-Event-Timing.
        // Der ws.on("play")-Handler bleibt als doppelte Absicherung für
        // andere Play-Pfade (toggleActivePlayback, seekTo, externe API).
        if (canPlayRef.current) {
          claimExclusivePlayback(me);
          ensureAudioContext(ws);
          ws.play();
        }
      };
      containerRef.current.addEventListener("click", onContainerClick);

      // ── Karaoke-Timing: rAF-Sync-Loop (2026-08-14) ──
      // `timeupdate` feuert nur ~4x/Sekunde (Browser-HTMLMediaElement) — das
      // Wort-Highlight hinkte dadurch bis 250ms hinterher („beginnt genau,
      // wird dann schnell ungenau"). Der rAF-Loop liest die exakte Zeit
      // direkt von der Quelle (getCurrentTime, ~40fps, 25ms-Schwelle) —
      // frame-genau und driftfrei, weil nie ein Timer akkumuliert.
      let rafId: number | null = null;
      let lastT = -1;
      const doSync = () => {
        const t = ws.getCurrentTime();
        if (Math.abs(t - lastT) >= 0.025) {
          lastT = t;
          setCurrentTime(t);
          onTimeUpdateRef.current?.(t);
        }
        // Change 208 (Timing-Modus): Wortspanne durchgelaufen → anhalten und
        // den Cursor auf den Wortanfang zurückstellen. Damit läuft ein
        // anschließender Play-Druck wieder ab dem Wort (User-Vorgabe).
        const range = playRangeRef.current;
        if (rangeFinished(t, range) && range) {
          playRangeRef.current = null;
          try { ws.pause(); } catch { /* WS7 ohne Audio */ }
          try { ws.setTime(range.start); } catch { /* WS7 ohne Audio */ }
          lastT = range.start;
          setCurrentTime(range.start);
          onTimeUpdateRef.current?.(range.start);
        }
      };
      const syncLoop = () => {
        doSync();
        rafId = ws.isPlaying() ? requestAnimationFrame(syncLoop) : null;
      };
      const startSync = () => {
        if (rafId == null) rafId = requestAnimationFrame(syncLoop);
      };
      // ── Fix 2026-08-18 (Change 019): rAF stoppt im Hidden-Tab, das
      // WebAudio-Playback läuft aber weiter → die Karaoke-Anzeige fror ein
      // und sprang beim Zurückkehren akkumuliert nach (Eindruck von
      // Playback-Drift). Im Hintergrund pollt stattdessen ein 500-ms-
      // Interval (Feuert im Hidden-Tab weiter), beim Visible sofortiger
      // Resync + rAF-Neustart. Zeitquelle bleibt NUR ws.getCurrentTime().
      let bgPollId: number | null = null;
      const stopBgPoll = () => {
        if (bgPollId != null) {
          window.clearInterval(bgPollId);
          bgPollId = null;
        }
      };
      const onVisibility = () => {
        if (document.hidden) {
          if (rafId != null) {
            cancelAnimationFrame(rafId);
            rafId = null;
          }
          if (bgPollId == null) {
            bgPollId = window.setInterval(() => {
              if (!ws.isPlaying()) {
                stopBgPoll();
                return;
              }
              doSync();
            }, 500);
          }
        } else {
          stopBgPoll();
          doSync(); // sofortiger Resync — kein akkumulierter Sprung
          if (ws.isPlaying()) startSync();
        }
      };
      document.addEventListener("visibilitychange", onVisibility);

      // Change 100: neuer ws hat noch kein Audio geladen — Zoom-Gate zu,
      // bis sein ready-Event kommt (sonst „Error: No audio loaded“).
      wsReadyRef.current = false;
      wsRef.current = ws;
      regionsRef.current = regions;
      return () => {
        cancelled = true;
        containerRef.current?.removeEventListener("click", onContainerClick);
        window.clearInterval(decodePoll);
        window.clearTimeout(canPlayTimeout);
        if (timerRef.current) {
          window.clearTimeout(timerRef.current);
          timerRef.current = null;
        }
        if (rafId != null) cancelAnimationFrame(rafId);
        stopBgPoll();
        document.removeEventListener("visibilitychange", onVisibility);
        releaseExclusivePlayback(me);
        ws.destroy();
      };
      // Change 059-Fix (User-Befund 2026-08-21): seit der lite-Liste
      // kommen die Peaks ASYNCHRON über den Detail-Fetch nach. `peaks`
      // und `durationHint` MÜSSEN Dependencies sein — sonst startet der
      // Player mit peaks=null (Browser-Decode der ganzen Datei) und wird
      // nie neu initialisiert, wenn die Server-Peaks eintreffen
      // („Loading waveform…" hängt für immer auf langsamen Verbindungen).
      // Change 112: statt `peaks` die Inhalts-Signatur verwenden — Polls
      // drehen die Referenz bei gleichem Inhalt (siehe oben), echte
      // Nachlieferungen ändern die Signatur.
    }, [audioUrl, backend, inView, peaksSignature, durationHint]);

    useImperativeHandle(ref, () => ({
      seekTo: (s: number) => {
        playRangeRef.current = null; // Change 208: Navigation hebt die Wortspanne auf
        if (!canPlayRef.current) return;
        ensureAudioContext(wsRef.current!);
        wsRef.current?.setTime(s); wsRef.current?.play();
      },
      seekToPaused: (s: number) => {
        playRangeRef.current = null; // Change 208: Navigation hebt die Wortspanne auf
        wsRef.current?.setTime(s);
      },
      // Change 208 (User-Vorgabe 19.09.2026): Im Timing-Modus wird die
      // Wortspanne abgespielt und am Ende angehalten. Der Cursor steht danach
      // wieder am Wortanfang — ein anschließender Play-Druck läuft ab dem Wort
      // (nicht ab dem Wortende) weiter.
      playRange: (start: number, end: number) => {
        const w = wsRef.current;
        playRangeRef.current = null;
        if (!w || !(end > start)) return;
        if (!canPlayRef.current) {
          // Audio noch nicht abspielbar (Decode läuft): nur den Cursor setzen.
          try { w.setTime(start); } catch { /* WS7 noch ohne Audio */ }
          return;
        }
        const active = meRef.current;
        if (active) claimExclusivePlayback(active);
        ensureAudioContext(w);
        try { w.setTime(start); } catch { /* WS7 noch ohne Audio */ }
        setCurrentTime(start);
        onTimeUpdateRef.current?.(start);
        playRangeRef.current = { start, end };
        w.play();
      },
      playPause: () => {
        const w = wsRef.current;
        playRangeRef.current = null; // Change 208: Play/Stop hebt die Wortspanne auf
        if (!w) return;
        const playing = w.isPlaying();
        const atEnd = w.getDuration() > 0 && w.getCurrentTime() >= w.getDuration() - 0.02;
        const action = decidePlayPause(playing, atEnd, canPlayRef.current);
        if (action === "pause") w.pause();
        else if (action === "stay") w.setTime(w.getDuration());
        else if (action === "play") w.playPause();
        // "noop": Audio noch nicht abspielbar → nichts
      },
      getCurrentTime: () => wsRef.current?.getCurrentTime() ?? 0,
      isPlaying: () => wsRef.current?.isPlaying() ?? false,
      setPlaybackRate: (rate: number) => {
        wsRef.current?.setPlaybackRate(rate);
        setPlayRate(rate);
      },
      getPlaybackRate: () => playRateRef.current,
    }), []);

    // Change 095: Spinner als SVG — der alte CSS-Ring (border-2 mit
    // border-t-transparent) sah auf Mobile wie ein „drehendes U" aus.
    const spinnerSvg = (size: number) => (
      <svg className="animate-spin" width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden>
        <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" opacity="0.25" />
        <path d="M22 12a10 10 0 0 1-10 10" stroke="currentColor" strokeWidth="4" strokeLinecap="round" />
      </svg>
    );

    return (
      // Change 072: outerRef auf dem ÄUSSEREN Wrapper — der ist nie hidden
      // (der Canvas-Container darunter bleibt bis ready display:none).
      <div ref={outerRef} className="w-full">
        {!ready && (
          // Change 095: Spinner + "Loading…" mit dem Ladefortschritt als
          // temporärem Progress-Bar im Text-Hintergrund (100 % = komplett
          // gefüllter Background; User-Design 2026-08-23).
          <div className="relative flex items-center justify-center h-[80px] overflow-hidden rounded-sm bg-panel2 text-muted2 text-[13px] gap-2">
            <div
              className="absolute inset-y-0 left-0 bg-proc/20 transition-[width] duration-200"
              style={{ width: `${Math.min(100, Math.max(0, loadPct))}%` }}
            />
            <span className="relative flex items-center gap-2">
              {spinnerSvg(16)}
              {t("loading_audio")}
            </span>
          </div>
        )}
        {error && (
          <div className="flex items-center justify-center h-[80px] text-[13px] gap-2 bg-[rgba(248,81,73,.08)] border border-err/20 rounded-sm">
            <span>⚠️</span>
            <span className="text-err">Waveform data corrupted</span>
          </div>
        )}
        {/* Change 105: NICHT display:none (hidden) bis ready — WaveSurfer
            misst den Container beim create; bei Breite 0 initialisiert es
            ohne Canvas (leerer Wrapper, keine Welle, Playback tot; User-
            Befund 2026-08-23 Android/Mobile: „Loading fertig, Play drückbar,
            spielt nicht“). visibility:hidden behält das Layout — WS7
            erstellt das Canvas mit echter Breite, sichtbar wird es bei
            ready. */}
        {/* Change 199: die Detail-Ebene liegt ÜBER der WS-Welle. Beide sind
            vertikal zentriert, deshalb deckt sich die Nulllinie. */}
        <div className="relative w-full">
          <div ref={containerRef} className="w-full" style={{ paddingTop: WAVE_PAD, paddingBottom: WAVE_PAD, visibility: ready && !error ? "visible" : "hidden" }} />
          {ready && !error && (
            <DetailWaveformLayer
              recordingId={recordingId}
              duration={duration}
              win={viewWin}
              playing={playing}
              timingZoom={timingZoom}
              width={containerRef.current?.clientWidth ?? 0}
              height={height + WAVE_PAD * 2}
              onUnavailable={() => setSidecarStatus("fehlt")}
            />
          )}
        </div>
        {/* Timeline ruler (Change 056: relative → 💬-Marker als Overlay) */}
        <div ref={timelineRef} className={`w-full relative ${ready && !error ? "mt-0" : "hidden"}`} />
        {ready && !error && (
          <div className="flex items-center gap-3 mt-2">
            <button
              onClick={() => wsRef.current?.playPause()}
              disabled={!canPlay}
              className="btn-ghost-sm text-[13px] flex items-center gap-1 disabled:opacity-30 disabled:cursor-not-allowed"
              title={canPlay ? (playing ? "Pause" : "Play") : t("loading_audio")}
            >
              {playing ? "⏸" : "▶"}
            </button>
            {!canPlay && (
              // Audio dekodiert noch (Waveform kann via Peaks schon stehen) —
              // sichtbare Status-Meldung statt stiller Disabled-Button.
              // Change 095: Spinner-SVG + Fortschritts-Background im Text.
              <span className="relative inline-flex items-center gap-1.5 text-[12px] text-muted2 rounded-sm overflow-hidden px-1.5 py-0.5">
                <span
                  className="absolute inset-y-0 left-0 bg-proc/20 transition-[width] duration-200"
                  style={{ width: `${Math.min(100, Math.max(0, loadPct))}%` }}
                />
                <span className="relative">{spinnerSvg(12)}</span>
                <span className="relative">{t("loading_audio")}</span>
              </span>
            )}
            <span className="text-[12px] text-muted2 tabular-nums">
              {fmtTime(currentTime)} / {fmtTime(duration)}
            </span>
            {/* Change 199: fehlende Detail-Peaks sichtbar machen. Die
                Wellenform bleibt dann in Basisauflösung — ohne Hinweis wäre
                das von „diese Aufnahme hat eben keine Details" nicht zu
                unterscheiden. */}
            {sidecarStatus === "fehlt" && (
              <span
                className="text-[11px] text-muted2"
                title="Für diese Aufnahme liegen noch keine Detail-Peaks vor — die Wellenform bleibt in Basisauflösung. Der Hintergrund-Nachlauf erzeugt sie."
              >
                ⓘ Basisauflösung
              </span>
            )}
            {/* Change 2026-08-17: Playback-Speed x0.5/x1/x1.5/x2 — die
                Karaoke-Markierung hängt an der Audio-Position und folgt
                damit automatisch korrekt jeder Geschwindigkeit.
                Fix 2026-08-17 (1× nicht wählbar): der Button-Klick rief
                direkt wsRef.current.setPlaybackRate(r) auf, aber NUR das
                imperative Handle aktualisierte den React-State playRate →
                der State blieb auf 1, der 1×-Button dadurch dauerhaft
                disabled. Jetzt: gemeinsamer Handler (WS + State). */}
            <span className="flex items-center gap-[2px] ml-1">
              {[0.5, 1, 1.5, 2].map((r) => (
                <button
                  key={r}
                  onClick={() => {
                    wsRef.current?.setPlaybackRate(r);
                    setPlayRate(r);
                  }}
                  disabled={!canPlay || Math.abs(playRate - r) < 0.01}
                  className={`text-[11px] px-[5px] py-[2px] rounded-sm border transition-colors ${
                    Math.abs(playRate - r) < 0.01
                      ? "bg-accent/20 border-accent/40 text-accent"
                      : "border-border text-muted hover:text-txt hover:bg-[rgba(255,255,255,.05)]"
                  } disabled:opacity-40`}
                  title={`Speed ${r}×`}
                >
                  {r}×
                </button>
              ))}
            </span>
            <span className="flex-1" />
            <button
              onClick={() => {
                const w = wsRef.current;
                if (!w) return;
                // Change 137: Im Timing-Zoom („Wort“) zoomt − auf die größte
                // normale Stufe zurück (danach laufen die Stufen normal weiter).
                if (timingZoom) {
                  setTimingZoom(false);
                  doZoom(w, ZOOM_STEPS.length - 1);
                } else {
                  doZoom(w, Math.max(0, zoomIdx - 1));
                }
              }}
              disabled={!timingZoom && zoomIdx <= 0}
              className="btn-ghost-sm text-[13px] px-1 disabled:opacity-30"
              title="Zoom out"
            >−</button>
            <span className="text-[11px] text-muted2 tabular-nums min-w-[36px] text-center">
              {timingZoom ? "Wort" : zoomIdx === 0 ? "fit" : `${ZOOM_STEPS[zoomIdx - 1]}×`}
            </span>
            <button
              onClick={() => {
                const w = wsRef.current;
                if (w && !timingZoom) doZoom(w, Math.min(ZOOM_STEPS.length - 1, zoomIdx + 1));
              }}
              disabled={timingZoom || zoomIdx >= ZOOM_STEPS.length - 1}
              className="btn-ghost-sm text-[13px] px-1 disabled:opacity-30"
              title="Zoom in"
            >+</button>
          </div>
        )}
      </div>
    );
  }
);

function fmtTime(sec: number): string {
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}
