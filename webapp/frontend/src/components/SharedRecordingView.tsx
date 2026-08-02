/* ============================================================
   SHARED RECORDING VIEW — Anon-Share-Link (/r/:uid) read-only
   ============================================================ */
import { useEffect, useState } from "react";
import type { Recording } from "../api";
import { fetchRecording } from "../api";
import { useT } from "../useLocale";
import { fmtDate, fmtDurSec } from "../format";
import { SegmentList } from "./SegmentList";

interface Props {
  uid: string;
}

export function SharedRecordingView({ uid }: Props) {
  const { t } = useT();
  const [rec, setRec] = useState<Recording | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchRecording(uid)
      .then((r) => { if (!cancelled) setRec(r); })
      .catch((e) => { if (!cancelled) setError((e as Error).message ?? String(e)); });
    return () => { cancelled = true; };
  }, [uid]);

  if (error) {
    return (
      <div className="max-w-[960px] mx-auto px-3 sm:px-5 py-8 text-center">
        <div className="text-err text-[14px] mb-2">⚠️ {t("error_loading")}</div>
        <div className="text-muted text-[12px]">{error}</div>
        <div className="text-muted2 text-[12px] mt-4">
          {t("anon_link")} — {t("anon_link_expiry").split("{expiry}")[0]}…
        </div>
      </div>
    );
  }

  if (!rec) {
    return (
      <div className="max-w-[960px] mx-auto px-3 sm:px-5 py-8 text-center text-muted text-[13px]">
        <span className="inline-block animate-spin w-4 h-4 border-2 border-current border-t-transparent rounded-full align-middle mr-2" />
        Loading…
      </div>
    );
  }

  const segments = rec.segments ?? [];

  return (
    <div className="max-w-[960px] mx-auto px-3 sm:px-5 py-4 sm:py-6">
      <div className="bg-seg-bg border border-border rounded-sm p-3 mb-3">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <h2 className="text-[14px] font-semibold text-txt break-all">
            {rec.original_name}
          </h2>
          <span className="text-[10px] font-bold uppercase tracking-wide text-amber-300 bg-amber-500/10 border border-amber-500/30 rounded-sm px-2 py-0.5">
            🔗 {t("shared_badge")}
          </span>
        </div>
        <div className="text-[11px] text-muted2 mt-1 space-x-3">
          <span>{fmtDate(rec.created_at)}</span>
          {rec.duration_s != null && <span>{fmtDurSec(rec.duration_s)}</span>}
          {rec.language && <span>{rec.language}</span>}
        </div>
      </div>

      {segments.length > 0 ? (
        <SegmentList
          segments={segments}
          activeIdx={-1}
          onActiveChange={() => {}}
          onSeekTo={() => {}}
        />
      ) : (
        <div className="bg-panel2 border border-border rounded-sm px-[14px] py-3 whitespace-pre-wrap leading-[1.65] max-h-[240px] overflow-y-auto scrollbar-thin text-[13.5px] text-txt break-words">
          {rec.text}
        </div>
      )}

      <p className="text-[11px] text-muted2 mt-3">
        ⚠️ {t("anon_link_hint")} {t("anon_link_expiry").replace("{expiry}", "").replace("{minutes}", "").trim()}
      </p>
    </div>
  );
}
