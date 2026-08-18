import { useEffect, useRef, useState, useCallback, useImperativeHandle, forwardRef } from "react";
import WaveSurfer from "wavesurfer.js";
import RegionsPlugin from "wavesurfer.js/dist/plugins/regions.js";
import TimelinePlugin from "wavesurfer.js/dist/plugins/timeline.js";
import HoverPlugin from "wavesurfer.js/dist/plugins/hover.js";
import { useT } from "../useLocale";

export interface WaveSurferHandle {
  seekTo: (seconds: number) => void;
  /** Seek OHNE Autoplay (2026-08-16: Cursor-Wort-Navigation springt nur). */
  seekToPaused: (seconds: number) => void;
  playPause: () => void;
  getCurrentTime: () => number;
  isPlaying: () => boolean;
  /** Change 2026-08-17: Playback-Rate (x0.5/x1/x2). Die Karaoke-Markierung
   *  hängt an der AUDIO-Position (getCurrentTime) — sie skaliert damit
   *  automatisch korrekt mit jeder Geschwindigkeit, ohne Speed-Faktor. */
  setPlaybackRate: (rate: number) => void;
  getPlaybackRate: () => number;
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
}

const ZOOM_STEPS = [1, 2, 4, 6, 10, 20, 50];
/** Vertikaler Kopfraum der Wellenform in px (oben+unten, 2026-08-16). */
const WAVE_PAD = 5;

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

/** Registriert `me` als aktiven Player und pausiert den vorherigen. */
export function claimExclusivePlayback(me: Playable): void {
  if (activePlayer && activePlayer !== me && activePlayer.isPlaying()) {
    activePlayer.pause();
  }
  // Immer merken (auch wenn nicht spielend): Space/Play-Shortcuts zielen
  // auf den zuletzt beanspruchten Player (Feature 2026-08-16).
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
  function WaveformPlayer({ audioUrl, peaks, durationHint, onRegionChange, onTimeUpdate, onPlayStateChange, onLoadError, height = 80 }, ref) {
    const { t } = useT();
    const containerRef = useRef<HTMLDivElement>(null);
    const timelineRef = useRef<HTMLDivElement>(null);
    const wsRef = useRef<WaveSurfer | null>(null);
    const regionsRef = useRef<RegionsPlugin | null>(null);
    const onTimeUpdateRef = useRef(onTimeUpdate);
    const onPlayStateRef = useRef(onPlayStateChange);
    const onRegionRef = useRef(onRegionChange);
    const onLoadErrorRef = useRef(onLoadError);
    const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    // Keep refs in sync with latest props
    onTimeUpdateRef.current = onTimeUpdate;
    onPlayStateRef.current = onPlayStateChange;
    onRegionRef.current = onRegionChange;
    onLoadErrorRef.current = onLoadError;
    const [ready, setReady] = useState(false);
    const [error, setError] = useState(false);
    const [currentTime, setCurrentTime] = useState(0);
    const [duration, setDuration] = useState(0);
    const [zoomIdx, setZoomIdx] = useState(0);
    const [playing, setPlaying] = useState(false);
    // Change 2026-08-17: Playback-Rate (x0.5/x1/x2) — State für die UI,
    // Ref für getPlaybackRate aus dem Handle (stale-closure-sicher).
    const [playRate, setPlayRate] = useState(1);
    const playRateRef = useRef(1);
    playRateRef.current = playRate;
    // Play erst möglich, wenn das echte Audio dekodiert ist (2026-08-16):
    // das `ready`-Event feuert mit Server-Peaks VOR dem Hintergrund-Decode
    // der Audiodatei — Play war also drückbar, obwohl noch nichts hörbar
    // war. `canplay` der Media-Quelle = echte Abspielbarkeit.
    const [canPlay, setCanPlay] = useState(false);
    const canPlayRef = useRef(false);
    canPlayRef.current = canPlay;

    const doZoom = useCallback((ws: WaveSurfer, idx: number) => {
      const pps = ZOOM_STEPS[idx];
      ws.zoom(pps);
      setZoomIdx(idx);
    }, []);

    useEffect(() => {
      if (!containerRef.current) return;

      let cancelled = false;

      const regions = RegionsPlugin.create();
      const timeline = TimelinePlugin.create({ container: timelineRef.current! });
      const hover = HoverPlugin.create();
      let ws: WaveSurfer;

      try {
        ws = WaveSurfer.create({
          container: containerRef.current,
          backend: "WebAudio",
          waveColor: "rgba(91,140,255,0.3)",
          progressColor: "rgba(91,140,255,0.8)",
          cursorColor: "#3b82f6",
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
          minPxPerSec: 1,
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
      try {
        // Peaks roh übergeben — der Kopfraum kommt aus dem Container-Padding
        // (WaveSurfer zeichnet nach dem Decode ohnehin aus dem Audio, eine
        // Client-Skalierung der Peaks wäre nach dem Decode wirkungslos).
        ws.load(
          audioUrl,
          hasPeaks ? [peaks as number[]] : undefined,
          hasPeaks ? (durationHint as number) : undefined,
        );
      } catch (e) {
        setError(true);
        setReady(true);
        onLoadErrorRef.current?.();
        return;
      }

      // Timeout safety net — mit Server-Peaks rendert WaveSurfer sofort (10s);
      // OHNE Peaks muss der Browser die ganze Datei dekodieren (WebAudio) —
      // bei langen Aufnahmen dauert das deutlich länger, der alte 10s-Timeout
      // warf dann faelschlich "Waveform data corrupted". 60s fuer den
      // Browser-Decode-Pfad.
      timerRef.current = setTimeout(() => {
        if (!cancelled) {
          setError(true);
          setReady(true);
          onLoadErrorRef.current?.();
        }
      }, hasPeaks ? 10000 : 60000);

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
        setReady(true);
        const dur = ws.getDuration();
        setDuration(dur);
        // Initial zoom = fit container width
        const containerW = containerRef.current?.clientWidth ?? 800;
        const fitPps = Math.max(1, Math.round(containerW / dur));
        let zi = 0;
        for (let i = 0; i < ZOOM_STEPS.length; i++) {
          if (ZOOM_STEPS[i] <= fitPps) zi = i;
        }
        doZoom(ws, zi);

        regions.addRegion({
          start: 0,
          end: dur,
          color: "rgba(91,140,255,0.08)",
          drag: true,
          resize: true,
        });
      });

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
        play: () => { if (canPlayRef.current) ws.play(); },
        playPause: () => {
          const playing = ws.isPlaying();
          const atEnd = ws.getDuration() > 0 && ws.getCurrentTime() >= ws.getDuration() - 0.02;
          const action = decidePlayPause(playing, atEnd, canPlayRef.current);
          if (action === "pause") ws.pause();
          else if (action === "stay") ws.setTime(ws.getDuration());
          else if (action === "play") ws.play();
          // "noop": Audio noch nicht abspielbar → nichts
        },
        isPlaying: () => ws.isPlaying(),
        isReady: () => canPlayRef.current,
      };
      // Abspielbarkeit (Fix 2026-08-18): Polling auf ws.getDecodedData()
      // statt zweitem Fetch. Der alte readyFetch lud die Audio-URL ein
      // ZWEITES Mal — parallel zum WaveSurfer-internen Fetch, also KEIN
      // Cache-Treffer: bei langen Aufnahmen (volle WAV ohne Preview)
      // doppelter Download → „loading audio“ drehte sich scheinbar ewig.
      // getDecodedData() ist der ECHTE decodierte Buffer: null, bis die
      // Datei dekodiert ist (ready/decode-Events feuern im Peaks-Pfad
      // vorher aus den Server-Peaks — deshalb kein Event, sondern Polling).
      const decodePoll = window.setInterval(() => {
        if (cancelled) return;
        try {
          if (ws.getDecodedData()) {
            window.clearInterval(decodePoll);
            setCanPlay(true);
          }
        } catch {
          window.clearInterval(decodePoll);
        }
      }, 300);
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
      claimExclusivePlayback(me);
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

      // ── Karaoke-Timing: rAF-Sync-Loop (2026-08-14) ──
      // `timeupdate` feuert nur ~4x/Sekunde (Browser-HTMLMediaElement) — das
      // Wort-Highlight hinkte dadurch bis 250ms hinterher („beginnt genau,
      // wird dann schnell ungenau"). Der rAF-Loop liest die exakte Zeit
      // direkt von der Quelle (getCurrentTime, ~40fps, 25ms-Schwelle) —
      // frame-genau und driftfrei, weil nie ein Timer akkumuliert.
      let rafId: number | null = null;
      let lastT = -1;
      const syncLoop = () => {
        const t = ws.getCurrentTime();
        if (Math.abs(t - lastT) >= 0.025) {
          lastT = t;
          setCurrentTime(t);
          onTimeUpdateRef.current?.(t);
        }
        rafId = ws.isPlaying() ? requestAnimationFrame(syncLoop) : null;
      };
      const startSync = () => {
        if (rafId == null) rafId = requestAnimationFrame(syncLoop);
      };

      wsRef.current = ws;
      regionsRef.current = regions;
      return () => {
        cancelled = true;
        window.clearInterval(decodePoll);
        window.clearTimeout(canPlayTimeout);
        if (rafId != null) cancelAnimationFrame(rafId);
        releaseExclusivePlayback(me);
        ws.destroy();
      };
    }, [audioUrl]);

    useImperativeHandle(ref, () => ({
      seekTo: (s: number) => {
        if (!canPlayRef.current) return;
        wsRef.current?.setTime(s); wsRef.current?.play();
      },
      seekToPaused: (s: number) => { wsRef.current?.setTime(s); },
      playPause: () => {
        const w = wsRef.current;
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

    return (
      <div className="w-full">
        {!ready && (
          <div className="flex items-center justify-center h-[80px] text-muted2 text-[13px] gap-2">
            <span className="animate-spin inline-block w-4 h-4 border-2 border-current border-t-transparent rounded-full" />
            Loading waveform…
          </div>
        )}
        {error && (
          <div className="flex items-center justify-center h-[80px] text-[13px] gap-2 bg-[rgba(248,81,73,.08)] border border-err/20 rounded-sm">
            <span>⚠️</span>
            <span className="text-err">Waveform data corrupted</span>
          </div>
        )}
        <div ref={containerRef} className={`w-full ${ready && !error ? "" : "hidden"}`} style={{ paddingTop: WAVE_PAD, paddingBottom: WAVE_PAD }} />
        {/* Timeline ruler */}
        <div ref={timelineRef} className={`w-full ${ready && !error ? "mt-0" : "hidden"}`} />
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
              <span className="text-[12px] text-muted2 flex items-center gap-1.5">
                <span className="animate-spin inline-block w-3 h-3 border-2 border-current border-t-transparent rounded-full" />
                {t("loading_audio")}
              </span>
            )}
            <span className="text-[12px] text-muted2 tabular-nums">
              {fmtTime(currentTime)} / {fmtTime(duration)}
            </span>
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
              onClick={() => { const w = wsRef.current; if (w) doZoom(w, Math.max(0, zoomIdx - 1)); }}
              disabled={zoomIdx <= 0}
              className="btn-ghost-sm text-[13px] px-1 disabled:opacity-30"
              title="Zoom out"
            >−</button>
            <span className="text-[11px] text-muted2 tabular-nums min-w-[36px] text-center">
              {ZOOM_STEPS[zoomIdx]}×
            </span>
            <button
              onClick={() => { const w = wsRef.current; if (w) doZoom(w, Math.min(ZOOM_STEPS.length - 1, zoomIdx + 1)); }}
              disabled={zoomIdx >= ZOOM_STEPS.length - 1}
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
