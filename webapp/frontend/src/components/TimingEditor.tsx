/**
 * Change 137 (Timing-Tab): Wort-Timing manuell präzisieren.
 *
 * Der Timing-Tab zeigt die Transkription read-only (SegmentList readOnly —
 * KEINE Edit-Funktionen: kein Text-Edit, kein Sprecher-Edit, keine Grenzen,
 * kein Split) + eine Kopfzeile mit dem Timing des geladenen Wortes
 * (Start/Ende/Länge, Override-Badge, Reset). Der Klick auf ein Wort lädt es
 * in die Waveform-Detailansicht (RecordingCard → WaveformPlayer timingWord).
 */
import type { Segment } from "../api";
import { fmtShortTimecode } from "../format";
import { useT } from "../useLocale";
import { SegmentList } from "./SegmentList";

interface Props {
  segments: Segment[];
  /** Wortliste-Modus: alle Edit-Funktionen aus (readOnly). */
  readOnly?: boolean;
  /** Aktives Segment (Karaoke/Auto-Scroll) — wie im Transkription-Tab. */
  activeIdx: number;
  onActiveChange: (idx: number) => void;
  currentTime?: number;
  isPlaying?: boolean;
  searchQuery?: string;
  searchJump?: { idx: number; nonce: number } | null;
  /** Seek für den Transkriptions-Tab. Im Timing-Modus wird er bewusst NICHT
   *  durchgereicht — er startet das Playback (siehe Kommentar an der
   *  Wortliste). */
  onSeekTo?: (seconds: number) => void;
  /** Seek ohne Abspielen. */
  onSeekPaused?: (seconds: number) => void;
  /** Klick auf ein Wort → in die Waveform laden (Zoom + Markierung). */
  onWordClick: (segIdx: number, wordIdx: number) => void;
  /** Change 141: „Folgen"-Toggle (Auto-Scroll der Wortliste an das
   *  Playback) — an die SegmentList durchgereicht. */
  followPlayback?: boolean;
  /** Geladenes Wort inkl. LIVE-Timing während des Marker-Drags. */
  timing?: { segIdx: number; wordIdx: number; start: number; end: number } | null;
  /** override-Flag des geladenen Wortes (manuell korrigiert). */
  override?: boolean;
  /** Reset: Override-Flag entfernen (Wort behält Zeit bis zum nächsten
   *  Re-Align). */
  onResetOverride?: () => void;
  /** Change 210: die Wortliste füllt die verfügbare Höhe (Edit-Vollbild) —
   *  sonst bleibt sie im Timing-Tab bei ~62vh, damit deutlich mehr Wörter
   *  ohne Scrollen erreichbar sind. */
  listFillHeight?: boolean;
}

export function TimingEditor({
  segments,
  activeIdx,
  onActiveChange,
  currentTime,
  isPlaying,
  searchQuery,
  searchJump,
  onSeekPaused,
  onWordClick,
  followPlayback = true,
  timing,
  override,
  onResetOverride,
  listFillHeight,
}: Props) {
  const { t } = useT();
  const word =
    timing && timing.segIdx >= 0 && timing.segIdx < segments.length
      ? segments[timing.segIdx]?.words?.[timing.wordIdx]
      : undefined;
  const wordText = word?.word ?? "";

  return (
    <div className="flex flex-col gap-2">
      {/* Kopfzeile: Timing des geladenen Wortes (Start/Ende/Länge) */}
      <div className="flex items-center gap-2 flex-wrap bg-panel2 border border-border rounded-sm px-2.5 py-1.5">
        {timing && word ? (
          <>
            <span className="text-[13px] font-semibold text-txt">
              „{wordText}"
            </span>
            <span className="text-[11px] text-muted2 tabular-nums">
              {t("timing_start")} {fmtShortTimecode(timing.start)}
            </span>
            <span className="text-[11px] text-muted2 tabular-nums">
              {t("timing_end")} {fmtShortTimecode(timing.end)}
            </span>
            <span className="text-[11px] text-muted2 tabular-nums">
              {t("timing_length")}{" "}
              {fmtShortTimecode(Math.max(0, timing.end - timing.start))}
            </span>
            {/* Change 210: Farblegende — sonst ist nicht klar, welche Markierung
                welches Wort ist (Befund: „nicht deutlich genug zu sehen"). */}
            <span
              data-testid="timing-legend"
              className="text-[10.5px] text-muted2 flex items-center gap-1.5"
            >
              <span
                className="inline-block w-2.5 h-2.5 rounded-sm"
                style={{
                  background: "rgba(46,160,67,0.35)",
                  border: "2px solid rgba(46,160,67,0.95)",
                }}
              />
              {t("timing_legend_active")}
              <span className="mx-0.5">·</span>
              <span
                className="inline-block w-2.5 h-2.5 rounded-sm"
                style={{
                  background: "rgba(210,153,34,0.22)",
                  border: "1px dashed rgba(210,153,34,0.95)",
                }}
              />
              {t("timing_legend_neighbor")}
            </span>
            {override && (
              <span
                className="text-[10.5px] font-semibold text-[#2ea043] border border-[#2ea043]/40 rounded-sm px-1.5 py-[1px]"
                title={t("timing_override_hint")}
              >
                ✎ {t("timing_override_hint")}
              </span>
            )}
            {onResetOverride && override && (
              <button
                type="button"
                onClick={onResetOverride}
                className="ml-auto text-[11px] text-muted2 hover:text-txt border border-border hover:border-muted rounded-sm px-2 py-[2px] cursor-pointer"
                title={t("timing_reset_title")}
              >
                {t("timing_reset")}
              </button>
            )}
          </>
        ) : (
          <span className="text-[12px] text-muted2">
            💡 {t("timing_word_hint")}
          </span>
        )}
      </div>
      {/* Wortliste: read-only, Klick lädt das Wort in die Waveform.
          Change 208 (User-Vorgabe 19.09.2026): Im Timing-Modus startet ein
          Klick kein Playback — er zoomt auf das Wort und zeigt die Markierung.
          Deshalb wird `onSeekTo` (spielt ab) NICHT durchgereicht: hier wird
          ausschließlich pausiert gesprungen. Fehlt der pausierte Seek, bleibt
          der Klick ganz ohne Seek — Abspielen ist hier nie gewollt. */}
      <SegmentList
        segments={segments}
        activeIdx={activeIdx}
        onActiveChange={onActiveChange}
        currentTime={currentTime}
        isPlaying={isPlaying}
        searchQuery={searchQuery}
        searchJump={searchJump}
        onSeekTo={onSeekPaused}
        onSeekPaused={onSeekPaused}
        readOnly
        onWordClick={onWordClick}
        followPlayback={followPlayback}
        // Change 210: deutlich mehr Wörter ohne Scrollen erreichbar; im
        // Vollbild füllt die Liste die Höhe.
        tall
        fillHeight={listFillHeight}
      />
    </div>
  );
}
