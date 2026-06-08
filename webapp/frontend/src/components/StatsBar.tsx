import type { Stats } from "../api";
import { fmtTotalDur } from "../format";

interface Props {
  stats: Stats | undefined;
}

export function StatsBar({ stats }: Props) {
  return (
    <div className="flex gap-[18px] flex-wrap flex-1 justify-end">
      <StatItem val={stats?.total ?? "—"} lbl="gravações" />
      <StatItem val={stats?.done ?? "—"} lbl="prontas" />
      <StatItem val={stats?.processing ?? "—"} lbl="processando" />
      <StatItem val={fmtTotalDur(stats?.total_audio_s)} lbl="áudio total" />
    </div>
  );
}

function StatItem({
  val,
  lbl,
}: {
  val: string | number;
  lbl: string;
}) {
  return (
    <div className="flex flex-col items-end">
      <span className="text-[15px] font-semibold text-txt leading-none">
        {val}
      </span>
      <span className="text-[11px] text-muted uppercase tracking-[.05em]">
        {lbl}
      </span>
    </div>
  );
}
