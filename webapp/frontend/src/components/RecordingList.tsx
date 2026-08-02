import type { Recording } from "../api";
import { buildRenderItems } from "../grouping";
import { RecordingCard } from "./RecordingCard";
import { WhatsappGroup } from "./WhatsappGroup";
import { useT } from "../useLocale";

interface Props {
  recordings: Recording[];
  query: string;
  isOidc?: boolean;
}

export function RecordingList({ recordings, query, isOidc = false }: Props) {
  const { t } = useT();
  if (!recordings.length) {
    return (
      <div className="text-center py-[60px] px-6 text-muted">
        <div className="text-[40px] mb-3">🎧</div>
        <p className="text-[15px] m-1">
          {query
            ? `${t("no_results")} "${query}"`
            : t("no_audio_yet")}
        </p>
        <small className="text-[12px] text-muted2">
          {query
            ? t("try_other_search")
            : t("drag_to_start")}
        </small>
      </div>
    );
  }

  const items = buildRenderItems(recordings);

  return (
    <div className="mt-4 flex flex-col gap-4">
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
            defaultCollapsed={idx > 0}
          />
        );
      })}
    </div>
  );
}
