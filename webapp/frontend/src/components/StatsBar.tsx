import type { Stats } from "../api";
import { fmtBytes, fmtTotalDur } from "../format";

import { useT } from "../useLocale";

export function StatsBar({ stats }: { stats: Stats | undefined }) {
  const { t } = useT();
  return (
    <div className="flex gap-[10px] sm:gap-[18px] flex-wrap max-w-[960px] mx-auto px-3 sm:px-5">
      {/* Change 192: auf drei Kennzahlen gekürzt — Anzahl, Gesamtlänge, Speicher.
          „fertig/hochgeladen/in Arbeit" stehen im Queue- und Listenkontext. */}
      <StatItem val={stats?.total ?? "—"} lbl={t("recordings")} />
      <StatItem val={fmtTotalDur(stats?.total_audio_s)} lbl={t("total_audio")} />
      <StatItem val={fmtBytes(stats?.total_size_bytes)} lbl={t("storage")} />
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
