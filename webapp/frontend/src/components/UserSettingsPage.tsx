import { useEffect, useState } from "react";
import { useT } from "../useLocale";
import { TemplatesSection, TargetsSection, LlmEndpointsSection } from "./PostProcessPanel";
import { fetchStats, type Stats, type UserInfo } from "../api";
import { fmtBytes, fmtTotalDur } from "../format";

interface Props {
  user: UserInfo | null;
}

/** User-Settings-Seite: Konto-Basisinfos, Statistik, Postprocessing,
 * Targets, BYOK. Nur für eingeloggte User — das Backend-Gate
 * (require_authenticated) erzwingt das auch serverseitig.
 */
export function UserSettingsPage({ user }: Props) {
  const { t } = useT();
  const [stats, setStats] = useState<Stats | null>(null);

  useEffect(() => {
    let alive = true;
    fetchStats()
      .then((s) => alive && setStats(s))
      .catch(() => alive && setStats(null));
    return () => {
      alive = false;
    };
  }, []);

  if (!user?.authenticated) return null;
  const groups = user.groups ?? [];

  return (
    <div className="flex flex-col gap-4">
      <h2 className="text-[16px] font-bold">⚙️ {t("settings")}</h2>

      <section className="bg-panel border border-border rounded-card px-3 py-3">
        <h3 className="font-bold text-[13px] mb-2">👤 {t("account")}</h3>
        <dl className="flex flex-col gap-[3px] text-[12px]">
          <InfoRow label={t("name_label")} value={user.name || "—"} />
          <InfoRow label={t("username")} value={user.preferred_username || "—"} />
          <InfoRow label={t("email")} value={user.email || "—"} />
          <InfoRow label={t("oidc_sub")} value={user.sub || "—"} mono />
          <InfoRow
            label={t("admin_role")}
            value={user.is_admin ? "✓ Admin" : "—"}
          />
        </dl>
        <div className="mt-2 flex items-center gap-1 flex-wrap">
          <span className="text-[11px] text-muted uppercase tracking-[.05em]">
            {t("groups")}:
          </span>
          {groups.length === 0 && (
            <span className="text-[12px] text-muted">{t("no_groups")}</span>
          )}
          {groups.map((g) => (
            <span
              key={g}
              className="text-[11px] px-2 py-[2px] rounded-full bg-accent/10 text-accent border border-accent/20"
            >
              {g}
            </span>
          ))}
        </div>
      </section>

      <section className="bg-panel border border-border rounded-card px-3 py-3">
        <h3 className="font-bold text-[13px] mb-2">📊 {t("stats")}</h3>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-4 gap-y-2 text-[12px]">
          <StatCell val={stats?.total ?? "—"} lbl={t("recordings")} />
          <StatCell val={stats?.done ?? "—"} lbl={t("done")} />
          <StatCell val={stats?.processing ?? "—"} lbl={t("processing")} />
          <StatCell val={stats?.uploaded ?? "—"} lbl="uploaded" />
          <StatCell val={fmtTotalDur(stats?.total_audio_s)} lbl={t("total_audio")} />
          <StatCell val={fmtBytes(stats?.total_size_bytes)} lbl={t("storage")} />
        </div>
      </section>

      <section className="bg-panel border border-border rounded-card px-3 py-3">
        <h3 className="font-bold text-[13px] mb-2">🧩 {t("postprocess")}</h3>
        <TemplatesSection />
      </section>

      <section className="bg-panel border border-border rounded-card px-3 py-3">
        <h3 className="font-bold text-[13px] mb-2">📦 {t("targets")}</h3>
        <TargetsSection />
      </section>

      <section className="bg-panel border border-border rounded-card px-3 py-3">
        <h3 className="font-bold text-[13px] mb-2">🔑 {t("byok")}</h3>
        <LlmEndpointsSection />
      </section>
    </div>
  );
}

function InfoRow({
  label,
  value,
  mono,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <dt className="text-muted shrink-0">{label}</dt>
      <dd
        className={[
          "text-right break-all",
          mono ? "font-mono text-[11px]" : "",
        ].join(" ")}
      >
        {value}
      </dd>
    </div>
  );
}

function StatCell({ val, lbl }: { val: string | number; lbl: string }) {
  return (
    <div className="flex flex-col items-start">
      <span className="text-[14px] font-semibold text-txt leading-none">
        {val}
      </span>
      <span className="text-[10px] text-muted uppercase tracking-[.05em]">
        {lbl}
      </span>
    </div>
  );
}
