import { useEffect, useState } from "react";
import { cancelQueueJob, fetchQueue, type QueueStatus } from "../api";
import { useT } from "../useLocale";

/* ============================================================
   QueueWatcher (Task 7/10) — zeigt aktive Transkriptions-Queue.
   Fremde Jobs sind anonymisiert (keine Namen), Cancel nur für eigene.
   ============================================================ */

/** Change 162: progress_note → Phase-Key für ALLE Job-Kinds.

 *  Die Note ist die einzige zuverlässige Phasenquelle (Change 035) und
 *  trägt seit Change 150/151 Details: "diarization 42%", "asr Chunk 3/8",
 *  "alignment 2/5". Erstes Wort = Phasenname (Präfix-Logik), unbekannte
 *  Noten → null (Fallback auf job.kind im Aufrufer).
 *
 *  Live-Befund 2026-08-30: Queue zeigte "Transcription", während die
 *  Diarization lief — exakter Vergleich ("=== diarization") scheiterte an
 *  "diarization 42%". */
export function noteToPhaseKey(note: string | null | undefined): string | null {
  const first = (note ?? "").trim().split(/\s+/)[0]?.toLowerCase() ?? "";
  switch (first) {
    case "preparing":
    case "vad":
    case "enhance":
    case "separate":
    case "asr":
      return "transcribe";
    case "diarization":
      return "rediarize";
    case "alignment":
      return "align";
    case "postprocessing":
    case "finalizing":
      return "transcribe";
    default:
      return null; // z. B. "Re-Diarize läuft …" → kind="rediarize"
  }
}

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
        {status.jobs.map((j) => {
          // Change 156: ehrliche Phase + echter Fortschritt statt "in Arbeit…".
          // Change 162: progress_note → Phase für ALLE Kinds (noteToPhaseKey),
          // Fallback auf job.kind. Vorher prüfte die Queue nur den exakten
          // String "diarization" — seit Change 150/151 trägt die Note den
          // Prozentwert ("diarization 42%"), der Match schlug fehl und die
          // Queue zeigte wieder "Transcription" (User-Befund 2026-08-30).
          const notePhase = noteToPhaseKey(j.progress_note);
          const runningPhase =
            j.status === "running" && notePhase
              ? t(`phase_${notePhase}`)
              : j.kind
                ? t(`phase_${j.kind}`)
                : t("processing");
          const pct =
            typeof j.progress_pct === "number" && j.progress_pct > 0
              ? ` · ${Math.round(j.progress_pct)}%`
              : "";
          return (
          <li key={j.job_id} className="flex items-center gap-2 text-muted flex-wrap">
            <span className="text-txt font-semibold tabular-nums">#{j.job_id}</span>
            {j.status === "queued" && (
              <span className="bg-[rgba(46,160,67,.15)] text-accent px-[6px] py-[1px] rounded-full text-[10px] font-semibold">
                {j.backend}
              </span>
            )}
            {j.status === "queued" ? (
              <span>
                {t("queued")} · Pos. {j.position}
                {j.eta_s != null && <span className="text-muted2"> · ~{j.eta_s}s</span>}
              </span>
            ) : (
              <span className="text-proc">
                {runningPhase}
                {pct}
              </span>
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
          );
        })}
      </ul>
    </div>
  );
}
