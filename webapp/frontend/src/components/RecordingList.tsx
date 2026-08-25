import type { Recording, RecordingSort } from "../api";
import { buildRenderItems } from "../grouping";
import { RecordingCard } from "./RecordingCard";
import { WhatsappGroup } from "./WhatsappGroup";
import { useT } from "../useLocale";
import { aggregateTags, mergeChipTags, type SortState } from "../sortState";

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

  const items = buildRenderItems(recordings);

  // Change 054: Tag-Filter-Chips — nur Tags mit ≥ 1 Aufnahme, mit Count.
  const tagList = aggregateTags(recordings);
  // Change 122: AKTIVE Tags bleiben immer als Chips sichtbar — auch wenn die
  // Trefferliste 0 ist (sonst verschwindet die Filterleiste im Leer-Zustand
  // und der Filter ist nicht mehr abwählbar).
  const chipTags = mergeChipTags(tagList, activeTags);
  const activeSet = new Set(activeTags);

  // Change 122: Filterleiste als eigene Einheit — wird im Leer-Zustand mit
  // gerendert, damit Sortierung + Tag-Filter auch bei 0 Treffern sichtbar
  // und abwählbar bleiben.
  const filterBar = (
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

      {chipTags.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-[11px] text-muted2 uppercase tracking-wide mr-0.5">
            {t("filter_tags")}
          </span>
          {chipTags.map(({ tag, count }) => {
            const active = activeSet.has(tag);
            return (
              <button
                key={tag}
                onClick={() => onToggleTag?.(tag)}
                aria-pressed={active}
                title={active ? t("tag_remove_hint") : t("tag_add_hint")}
                className={[
                  "text-[11px] px-2 py-[3px] rounded-sm border transition-colors",
                  active
                    ? "border-accent text-accent bg-accent/10 font-semibold"
                    : "border-border2 text-muted hover:text-txt hover:border-border3",
                ].join(" ")}
              >
                #{tag}
                {count > 0 ? ` (${count})` : ""}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );

  if (!recordings.length) {
    // Change 122: Leer-Zustand BEHÄLT die Filterleiste, wenn ein Filter
    // (Suche oder Tags) aktiv ist — sonst kann der User den Filter nicht
    // mehr abwählen und hängt fest.
    const hasFilter = Boolean(query) || activeTags.length > 0;
    return (
      <div className="text-center py-[60px] px-6 text-muted">
        {hasFilter && (
          <div className="max-w-md mx-auto text-left mb-6">{filterBar}</div>
        )}
        <div className="text-[40px] mb-3">🎧</div>
        <p className="text-[15px] m-1">
          {hasFilter
            ? `${t("no_results")}${query ? ` "${query}"` : ""}${
                activeTags.length > 0
                  ? " — " + activeTags.map((x) => `#${x}`).join(", ")
                  : ""
              }`
            : t("no_audio_yet")}
        </p>
        <small className="text-[12px] text-muted2">
          {hasFilter ? t("try_other_search") : t("drag_to_start")}
        </small>
      </div>
    );
  }

  return (
    <div className="mt-4 flex flex-col gap-4">
      {(onSort || chipTags.length > 0) && filterBar}

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
