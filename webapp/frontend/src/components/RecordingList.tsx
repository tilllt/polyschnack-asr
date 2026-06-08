import type { Recording } from "../api";
import { buildRenderItems } from "../grouping";
import { RecordingCard } from "./RecordingCard";
import { WhatsappGroup } from "./WhatsappGroup";

interface Props {
  recordings: Recording[];
  query: string;
}

export function RecordingList({ recordings, query }: Props) {
  if (!recordings.length) {
    return (
      <div className="text-center py-[60px] px-6 text-muted">
        <div className="text-[40px] mb-3">🎧</div>
        <p className="text-[15px] m-1">
          {query
            ? `Nenhum resultado para "${query}"`
            : "Nenhum áudio ainda"}
        </p>
        <small className="text-[12px] text-muted2">
          {query
            ? "Tente outra busca."
            : "Arraste arquivos acima para começar."}
        </small>
      </div>
    );
  }

  const items = buildRenderItems(recordings);

  return (
    <div className="mt-4 flex flex-col gap-4">
      {items.map((item) => {
        if (item.type === "whatsapp-group") {
          return (
            <WhatsappGroup key={`group-${item.batch_id}`} group={item} />
          );
        }
        return (
          <RecordingCard
            key={item.recording.id}
            recording={item.recording}
          />
        );
      })}
    </div>
  );
}
