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
import { fmtTimecode } from "../format";
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
  onSeekTo?: (seconds: number) => void;
  onSeekPaused?: (seconds: number) => void;
  /** Klick auf ein Wort → in die Waveform laden (Zoom + Markierung). */
  onWordClick: (segIdx: number, wordIdx: number) => void;
  /** Geladenes Wort inkl. LIVE-Timing während des Marker-Drags. */
  timing?: { segIdx: number; wordIdx: number; start: number; end: number } | null;
  /** override-Flag des geladenen Wortes (manuell korrigiert). */
  override?: boolean;
  /** Reset: Override-Flag entfernen (Wort behält Zeit bis zum nächsten
   *  Re-Align). */
  onResetOverride?: () => void;
}

export function TimingEditor({
  segments,
  activeIdx,
  onActiveChange,
  currentTime,
  isPlaying,
  searchQuery,
  searchJump,
  onSeekTo,
  onSeekPaused,
  onWordClick,
  timing,
  override,
  onResetOverride,
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
              {t("timing_start")} {fmtTimecode(timing.start)}
            </span>
            <span className="text-[11px] text-muted2 tabular-nums">
              {t("timing_end")} {fmtTimecode(timing.end)}
            </span>
            <span className="text-[11px] text-muted2 tabular-nums">
              {t("timing_length")}{" "}
              {fmtTimecode(Math.max(0, timing.end - timing.start))}
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
      {/* Wortliste: read-only, Klick lädt das Wort in die Waveform */}
      <SegmentList
        segments={segments}
        activeIdx={activeIdx}
        onActiveChange={onActiveChange}
        currentTime={currentTime}
        isPlaying={isPlaying}
        searchQuery={searchQuery}
        searchJump={searchJump}
        onSeekTo={onSeekTo}
        onSeekPaused={onSeekPaused}
        readOnly
        onWordClick={onWordClick}
      />
    </div>
  );
}
