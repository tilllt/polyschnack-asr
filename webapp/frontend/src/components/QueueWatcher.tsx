import { useEffect, useState } from "react";
import { cancelQueueJob, fetchQueue, type QueueStatus } from "../api";
import { useT } from "../useLocale";

/* ============================================================
   QueueWatcher (Task 7/10) — zeigt aktive Transkriptions-Queue.
   Fremde Jobs sind anonymisiert (keine Namen), Cancel nur für eigene.
   ============================================================ */

export function QueueWatcher() {
  const { t } = useT();
  const [status, setStatus] = useState<QueueStatus | null>(null);

  useEffect(() => {
    let alive = true;
    let timer: number;

    async function poll() {
      try {
        const s = await fetchQueue();
        if (!alive) return;
        setStatus(s);
        timer = window.setTimeout(poll, s.jobs.length ? 4000 : 10000);
      } catch {
        if (!alive) return;
        timer = window.setTimeout(poll, 10000);
      }
    }
    poll();
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, []);

  if (!status || status.jobs.length === 0) return null;

  return (
    <div className="bg-panel border border-border rounded-card px-3 py-2 mb-3 text-[12px]">
      <div className="font-semibold text-muted mb-1">
        ⏳ {t("in_queue")} · {status.jobs.length} Jobs · {t("capacity")}: {status.concurrency}
      </div>
      <ul className="space-y-1">
        {status.jobs.map((j) => (
          <li key={j.job_id} className="flex items-center gap-2 text-muted flex-wrap">
            <span className="text-txt font-semibold tabular-nums">#{j.job_id}</span>
            <span className="bg-[rgba(91,140,255,.12)] text-accent px-[6px] py-[1px] rounded-full text-[10px] font-semibold">
              {j.backend}
            </span>
            {j.status === "queued" ? (
              <span>
                {t("queued")} · Pos. {j.position}
                {j.eta_s != null && <span className="text-muted2"> · ~{j.eta_s}s</span>}
              </span>
            ) : (
              <span className="text-proc">{t("processing")}…</span>
            )}
            {j.is_mine && j.status === "queued" && (
              <button
                onClick={async () => {
                  await cancelQueueJob(j.job_id).catch(() => {});
                  setStatus(await fetchQueue().catch(() => status));
                }}
                className="text-err hover:underline ml-auto"
                title="Cancel"
              >
                ✕
              </button>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
