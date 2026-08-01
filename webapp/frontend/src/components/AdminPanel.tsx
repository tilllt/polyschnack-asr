import { useEffect, useState } from "react";
import type { AdminConfig, AdminService, EnvSetting, ModelMatrixEntry } from "../api";
import {
  adminServiceAction,
  fetchAdminConfig,
  fetchAdminServices,
  fetchEnvSettings,
  fetchModelsMatrix,
  putAdminConfig,
  resetAdminConfig,
} from "../api";
import { useT } from "../useLocale";

/* ============================================================
   AdminPanel (Task 8/10) — nur für Admins (me.is_admin).
   Tabs: Services (Start/Stop mit Ressourcen-Status + Stop-Schutz),
   Config (Default-Backend mit Auto-Start), Modell-Matrix.
   ============================================================ */

type Tab = "services" | "config" | "matrix";

function statusColor(status: string): string {
  switch (status) {
    case "running": return "text-ok bg-[rgba(63,185,80,.15)]";
    case "stopped": return "text-muted bg-panel2";
    case "unhealthy": return "text-err bg-[rgba(248,81,73,.15)]";
    default: return "text-muted2 bg-panel2";
  }
}

export function AdminPanel() {
  const { t } = useT();
  const [tab, setTab] = useState<Tab>("services");
  const [services, setServices] = useState<AdminService[] | null>(null);
  const [config, setConfig] = useState<AdminConfig | null>(null);
  const [matrix, setMatrix] = useState<ModelMatrixEntry[]>([]);
  const [envSettings, setEnvSettings] = useState<EnvSetting[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function reload() {
    try {
      const [s, c, m] = await Promise.all([
        fetchAdminServices(),
        fetchAdminConfig(),
        fetchModelsMatrix(),
      ]);
      setServices(s);
      setConfig(c);
      setMatrix(m);
      fetchEnvSettings().then(setEnvSettings).catch(() => {});
      setErr(null);
    } catch (e) {
      setErr((e as Error).message);
    }
  }

  useEffect(() => { void reload(); }, []);

  async function act(name: string, action: "start" | "stop" | "restart") {
    setBusy(`${action}:${name}`);
    setErr(null);
    try {
      await adminServiceAction(name, action);
    } catch (e) {
      setErr(`${action} ${name}: ${(e as Error).message}`);
    } finally {
      setBusy(null);
      await reload();
    }
  }

  async function switchBackend(backend: string) {
    setBusy("switch");
    setErr(null);
    try {
      await putAdminConfig(backend);
    } catch (e) {
      setErr(`switch: ${(e as Error).message}`);
    } finally {
      setBusy(null);
      await reload();
    }
  }

  async function resetBackend() {
    setBusy("reset");
    try {
      await resetAdminConfig();
    } catch (e) {
      setErr(`reset: ${(e as Error).message}`);
    } finally {
      setBusy(null);
      await reload();
    }
  }

  const runningNames = new Set(
    (services ?? []).filter((s) => s.status === "running").map((s) => s.name),
  );

  return (
    <div className="bg-panel border border-border rounded-card px-3 py-3 mb-3 text-[12px]">
      <div className="flex items-center gap-3 mb-2 flex-wrap">
        <span className="font-bold text-txt text-[13px]">🛠 {t("admin")}</span>
        {(["services", "config", "matrix"] as Tab[]).map((tb) => (
          <button
            key={tb}
            onClick={() => setTab(tb)}
            className={`text-[12px] px-2 py-[3px] rounded-sm font-semibold ${
              tab === tb ? "bg-accent/15 text-accent" : "text-muted2 hover:text-txt"
            }`}
          >
            {t(tb)}
          </button>
        ))}
        <button onClick={() => void reload()} className="ml-auto text-muted2 hover:text-txt">
          ⟳
        </button>
      </div>

      {err && <div className="text-err text-[12px] mb-2">⚠️ {err}</div>}

      {tab === "services" && (
        <div className="space-y-1.5">
          {(services ?? []).map((s) => (
            <div key={s.name} className="flex items-center gap-2 flex-wrap bg-panel2 border border-border rounded-sm px-2 py-1.5">
              <span className="font-semibold text-txt w-[110px] truncate">{s.name}</span>
              <span className={`text-[10px] font-bold px-[6px] py-[1px] rounded-full uppercase ${statusColor(s.status)}`}>
                {s.status}
                {s.health ? ` · ${s.health}` : ""}
              </span>
              <span className="text-muted2 hidden sm:inline truncate max-w-[180px]">{s.model}</span>
              {!s.resources.ok && (
                <span className="text-err text-[11px]" title={s.resources.message}>
                  ⚠️ {Object.keys(s.resources.missing).join(", ")}
                </span>
              )}
              <span className="text-muted2">
                {t("active_jobs")}: {s.active_jobs}
              </span>
              <span className="ml-auto flex gap-1">
                {s.status !== "running" && (
                  <button
                    onClick={() => void act(s.name, "start")}
                    disabled={busy !== null || !s.resources.ok}
                    className="btn-ghost-sm text-accent disabled:opacity-40"
                    title={!s.resources.ok ? s.resources.message : undefined}
                  >
                    {t("start")}
                  </button>
                )}
                {s.status === "running" && (
                  <>
                    <button
                      onClick={() => void act(s.name, "restart")}
                      disabled={busy !== null || s.active_jobs > 0}
                      className="btn-ghost-sm disabled:opacity-40"
                      title={s.active_jobs > 0 ? `${s.active_jobs} ${t("active_jobs")}` : undefined}
                    >
                      {t("restart")}
                    </button>
                    <button
                      onClick={() => void act(s.name, "stop")}
                      disabled={busy !== null || s.active_jobs > 0}
                      className="btn-ghost-sm text-err disabled:opacity-40"
                      title={s.active_jobs > 0 ? `${s.active_jobs} ${t("active_jobs")}` : undefined}
                    >
                      {t("stop")}
                    </button>
                  </>
                )}
              </span>
            </div>
          ))}
          {services !== null && services.length === 0 && (
            <div className="text-muted italic">{t("no_audio_yet")}</div>
          )}
        </div>
      )}

      {tab === "config" && config && (
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-muted">{t("default_backend")}:</span>
          <select
            value={config.default_backend}
            onChange={(e) => void switchBackend(e.target.value)}
            disabled={busy !== null}
            className="bg-panel2 border border-border rounded-sm text-[12px] px-1.5 py-[3px] text-txt"
          >
            {matrix.map((m) => (
              <option key={m.backend} value={m.backend}>
                {m.backend}
                {runningNames.has(m.name) ? "" : ` (${t("start_auto")})`}
              </option>
            ))}
          </select>
          <button onClick={() => void resetBackend()} disabled={busy !== null} className="btn-ghost-sm">
            {t("reset_backend")}
          </button>
          <span className="ml-auto text-muted2">
            {t("capacity")}: {config.concurrency} · Queue: {config.max_queue_len}
          </span>
        </div>
      )}

      {tab === "config" && (
        <div className="mt-2 border-t border-border pt-2">
          <div className="flex items-center gap-2 mb-1.5">
            <span className="font-bold text-txt text-[12px]">🌐 {t("env_settings")}</span>
            <span className="text-muted2 text-[10px]">🔒 {t("env_hardcoded")}</span>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-3 gap-y-[3px] max-h-[200px] overflow-y-auto">
            {envSettings.map((s) => (
              <div key={s.key} className="flex items-center gap-1.5 text-[11px]">
                <span className="text-muted2 truncate w-[150px]" title={s.key}>
                  {s.name}
                </span>
                <span className="text-txt truncate flex-1 text-right font-mono" title={s.value}>
                  {s.value}
                </span>
                <span
                  className="text-[9px] font-bold uppercase px-[4px] py-[1px] rounded-sm bg-panel2 text-muted2 border border-border cursor-help"
                  title={t("env_hardcoded")}
                >
                  ENV
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {tab === "matrix" && (
        <div className="overflow-x-auto">
          <table className="w-full text-[11px] border-collapse">
            <thead>
              <tr className="text-muted2 text-left">
                <th className="pr-2 py-1">Backend</th>
                <th className="pr-2">TS</th>
                <th className="pr-2">Live</th>
                <th className="pr-2">Async</th>
                <th className="pr-2">NR</th>
                <th className="pr-2">VAD</th>
                <th className="pr-2">Diar.</th>
                <th className="pr-2">Enh.</th>
                <th className="pr-2">VRAM</th>
              </tr>
            </thead>
            <tbody>
              {matrix.map((m) => (
                <tr key={m.backend} className="border-t border-border">
                  <td className="pr-2 py-1 font-semibold text-txt">{m.backend}</td>
                  <td className="pr-2">{String(m.word_timestamps)}</td>
                  <td className="pr-2">{m.streaming ? "✅" : "—"}</td>
                  <td className="pr-2">{m.async_jobs ? "✅" : "—"}</td>
                  <td className="pr-2">{m.noise_reduce ? "✅" : "—"}</td>
                  <td className="pr-2">{m.vad}</td>
                  <td className="pr-2">{m.diarization}</td>
                  <td className="pr-2">{m.enhance ? "✅" : "—"}</td>
                  <td className="pr-2">{m.requires.vram_gb} GB</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
