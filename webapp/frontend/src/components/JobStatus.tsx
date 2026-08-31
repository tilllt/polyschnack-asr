/**
 * Change 183 Phase 3 — EINE Job-Status-Darstellung für alle Orte.
 *
 * Wird OBERHALB (QueueWatcher) und in der RecordingCard gerendert —
 * identisches Aussehen, identische Daten (normiertes JobStatusData,
 * das der Recording-Response und die Queue-API beide liefern).
 *
 * Die sechs Anforderungen:
 *  1. Was läuft        — Modus (kind) + Phase (job_kind_* / phase_*)
 *  2. Seit wann        — phase_started_at (atomar vom Job)
 *  3. Wie lange noch   — ETA (nur wenn plausibel; sonst keine Anzeige)
 *  4. Heartbeat        — NUR graphisch (Punkt: grün/orange/rot)
 *  5. Cancelbar        — einheitlicher Cancel-Button
 *  6. Progress %       — nur wenn echte pct-Daten existieren
 */
import type { JobStatusData } from "../api";
import { useT } from "../useLocale";

function secondsSince(iso?: string | null): number {
  if (!iso) return -1;
  const ms = Date.parse(iso);
  if (Number.isNaN(ms)) return -1;
  return Math.max(0, (Date.now() - ms) / 1000);
}

function fmtTime(sec: number): string {
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

/** Heartbeat-Level aus heartbeat_at (wie bisher, nur graphisch). */
function hbLevel(iso?: string | null): "fresh" | "warn" | "stalled" | "none" {
  if (!iso) return "none";
  const s = secondsSince(iso);
  if (s <= 5) return "fresh";
  if (s <= 30) return "warn";
  return "stalled";
}

function fmtEtaRange(total?: number | null, low?: number | null, high?: number | null): string {
  if (total == null || total <= 0) return "";
  // Anti-Fake (Change 183): Absurde ETAs (> 24 h) nie anzeigen.
  if (total > 86400) return "";
  const m = Math.round(total / 60);
  if (low == null || high == null) return `~${m}m`;
  const lm = Math.round(Math.max(total, low) / 60);
  const hm = Math.round(Math.max(total, high) / 60);
  return `~${lm}–${hm}m`;
}

export default function JobStatus({
  job,
  eta,
  onCancel,
  cancelDisabled,
}: {
  job?: JobStatusData | null;
  eta?: { total?: number | null; low?: number | null; high?: number | null };
  onCancel?: () => void;
  cancelDisabled?: boolean;
}) {
  if (!job) return null;
  const { t } = useT();
  const phase = job.phase || (job.kind ? undefined : undefined);
  const phaseLabel =
    phase && phase !== job.kind ? t(`phase_${phase}` as never) || phase : null;
  const kindLabel = job.kind ? (t(`job_kind_${job.kind}` as never) as string) || job.kind : "";
  const since = secondsSince(job.phase_started_at);
  const hb = hbLevel(job.heartbeat_at);
  const etaText = fmtEtaRange(eta?.total, eta?.low, eta?.high);
  const showPct = typeof job.pct === "number" && job.pct >= 0;

  return (
    <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[12px]">
      {/* 1. Was läuft */}
      <span className="font-semibold text-accent uppercase tracking-wide shrink-0">
        {kindLabel}
        {phaseLabel ? <span className="text-muted2 normal-case font-normal"> · {phaseLabel}</span> : null}
      </span>
      {/* 2. Seit wann */}
      {since >= 0 && (
        <span className="text-muted2 shrink-0">
          {t("phase_running_since")} {fmtTime(since)}
        </span>
      )}
      {/* 3. Wie lange noch */}
      {etaText && <span className="text-muted2 shrink-0">{t("phase_eta")} {etaText}</span>}
      {/* 4. Heartbeat — nur graphisch */}
      <span
        className={`inline-block w-2 h-2 rounded-full shrink-0 ${
          hb === "fresh"
            ? "bg-ok animate-pulse"
            : hb === "warn"
              ? "bg-warn/80"
              : hb === "stalled"
                ? "bg-err"
                : "bg-border"
        }`}
        title={hb === "none" ? "" : t("hb_" + hb)}
      />
      {/* 6. Progress % — nur wenn echte Daten */}
      {showPct && <span className="text-muted2 shrink-0">{Math.round(job.pct!)}%</span>}
      {/* 5. Cancelbar */}
      {onCancel && job.status !== "done" && job.status !== "failed" && job.status !== "cancelled" && (
        <button
          onClick={onCancel}
          disabled={cancelDisabled || job.cancel_requested}
          className="text-[10px] px-2 py-[1px] rounded-full border border-err/50 text-err hover:bg-err/10 disabled:opacity-40 disabled:cursor-not-allowed shrink-0"
        >
          {job.cancel_requested ? t("cancelling") : t("cancel")}
        </button>
      )}
    </div>
  );
}
