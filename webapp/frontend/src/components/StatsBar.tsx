import type { Stats } from "../api";
import { fmtTotalDur } from "../format";

import { useT } from "../useLocale";

interface Props {
  stats: Stats | undefined;
}

export function StatsBar({ stats }: Props) {
  const { t } = useT();
  return (
    <div className="flex gap-[10px] sm:gap-[18px] flex-wrap max-w-[960px] mx-auto px-3 sm:px-5">
      <StatItem val={stats?.total ?? "—"} lbl={t("recordings")} />
      <StatItem val={stats?.done ?? "—"} lbl={t("done")} />
      <StatItem val={stats?.uploaded ?? "—"} lbl={"uploaded"} />
      <StatItem val={stats?.processing ?? "—"} lbl={t("processing")} />
      <StatItem val={fmtTotalDur(stats?.total_audio_s)} lbl={t("total_audio")} />
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
    <div className="flex flex-col items-start sm:items-end">
      <span className="text-[13px] sm:text-[15px] font-semibold text-txt leading-none">
        {val}
      </span>
      <span className="text-[10px] sm:text-[11px] text-muted uppercase tracking-[.05em]">
        {lbl}
      </span>
    </div>
  );
}
