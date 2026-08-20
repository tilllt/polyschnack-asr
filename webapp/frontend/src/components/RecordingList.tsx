import type { Recording, RecordingSort } from "../api";
import { buildRenderItems } from "../grouping";
import { RecordingCard } from "./RecordingCard";
import { WhatsappGroup } from "./WhatsappGroup";
import { useT } from "../useLocale";
import { aggregateTags, type SortState } from "../sortState";

/** Change 054: Sort-Badges in fester Reihenfolge (User-Vorgabe). */
export const SORT_BADGES: RecordingSort[] = [
  "date",
  "edited",
  "name",
  "filename",
  "length",
];

interface Props {
  recordings: Recording[];
  query: string;
  isOidc?: boolean;
  isAdmin?: boolean;
  /** Change 054: aktive Sortierung (null = Default Date desc). */
  sort?: SortState;
  onSort?: (key: RecordingSort) => void;
  /** Change 054: aktive Tag-Filter (ODER). */
  activeTags?: string[];
  onToggleTag?: (tag: string) => void;
}

export function RecordingList({
  recordings,
  query,
  isOidc = false,
  isAdmin = false,
  sort = null,
  onSort,
  activeTags = [],
  onToggleTag,
}: Props) {
  const { t } = useT();

  if (!recordings.length) {
    return (
      <div className="text-center py-[60px] px-6 text-muted">
        <div className="text-[40px] mb-3">🎧</div>
        <p className="text-[15px] m-1">
          {query || activeTags.length > 0
            ? `${t("no_results")}${query ? ` "${query}"` : ""}`
            : t("no_audio_yet")}
        </p>
        <small className="text-[12px] text-muted2">
          {query || activeTags.length > 0
            ? t("try_other_search")
            : t("drag_to_start")}
        </small>
      </div>
    );
  }

  const items = buildRenderItems(recordings);

  // Change 054: Tag-Filter-Chips — nur Tags mit ≥ 1 Aufnahme, mit Count.
  const tagList = aggregateTags(recordings);
  const activeSet = new Set(activeTags);

  return (
    <div className="mt-4 flex flex-col gap-4">
      {/* ── Change 054: Sort-Badges + Tag-Filter (klein, platzsparend) ── */}
      {(onSort || tagList.length > 0) && (
        <div className="flex flex-col gap-1.5">
          {onSort && (
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="text-[11px] text-muted2 uppercase tracking-wide mr-0.5">
                {t("sort_by")}
              </span>
              {SORT_BADGES.map((key) => {
                const active = sort?.key === key;
                const dir = active ? sort.dir : null;
                return (
                  <button
                    key={key}
                    onClick={() => onSort(key)}
                    title={t("sort_hint")}
                    aria-pressed={active}
                    className={[
                      "text-[11px] px-2 py-[3px] rounded-sm border transition-colors",
                      active
                        ? "border-accent text-accent bg-accent/10 font-semibold"
                        : "border-border2 text-muted hover:text-txt hover:border-border3",
                    ].join(" ")}
                  >
                    {t(`sort_${key}`)}
                    {dir === "desc" ? " ↓" : dir === "asc" ? " ↑" : ""}
                  </button>
                );
              })}
            </div>
          )}

          {tagList.length > 0 && (
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="text-[11px] text-muted2 uppercase tracking-wide mr-0.5">
                {t("filter_tags")}
              </span>
              {tagList.map(({ tag, count }) => {
                const active = activeSet.has(tag);
                return (
                  <button
                    key={tag}
                    onClick={() => onToggleTag?.(tag)}
                    aria-pressed={active}
                    className={[
                      "text-[11px] px-2 py-[3px] rounded-sm border transition-colors",
                      active
                        ? "border-accent text-accent bg-accent/10 font-semibold"
                        : "border-border2 text-muted hover:text-txt hover:border-border3",
                    ].join(" ")}
                  >
                    #{tag} ({count})
                  </button>
                );
              })}
            </div>
          )}
        </div>
      )}

      {items.map((item, idx) => {
        if (item.type === "whatsapp-group") {
          return (
            <WhatsappGroup
              key={`group-${item.batch_id}`}
              group={item}
              defaultCollapsed={idx > 0}
            />
          );
        }
        return (
          <RecordingCard
            key={item.recording.id}
            recording={item.recording}
            isOidc={isOidc}
            isAdmin={isAdmin}
            defaultCollapsed={idx > 0}
          />
        );
      })}
    </div>
  );
}
