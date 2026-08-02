import type { Stats } from "../api";
import { fmtTotalDur } from "../format";

import { useT } from "../useLocale";

interface Props {
  stats: Stats | undefined;
  device?: string | null;
}

export function StatsBar({ stats, device }: Props) {
  const { t } = useT();
  return (
    <div className="flex gap-[10px] sm:gap-[18px] flex-wrap max-w-[960px] mx-auto px-3 sm:px-5">
      <StatItem val={stats?.total ?? "—"} lbl={t("recordings")} />
      <StatItem val={stats?.done ?? "—"} lbl={t("done")} />
      <StatItem val={stats?.uploaded ?? "—"} lbl={"uploaded"} />
      <StatItem val={stats?.processing ?? "—"} lbl={t("processing")} />
      <StatItem val={fmtTotalDur(stats?.total_audio_s)} lbl={t("total_audio")} />
      {device && (
        <div
          className={[
            "inline-flex items-center self-center gap-1 text-[11px] font-semibold px-2 py-[3px] rounded-full",
            device === "cuda"
              ? "bg-[rgba(59,130,246,.12)] text-accent"
              : device === "cpu"
              ? "bg-[rgba(234,179,8,.12)] text-[#eab308]"
              : "bg-[rgba(248,81,73,.1)] text-err",
          ].join(" ")}
          title={`ASR inference: ${device}`}
        >
          {device === "cuda" ? "⚡ GPU" : device === "cpu" ? "💻 CPU" : "❓"}
        </div>
      )}
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
