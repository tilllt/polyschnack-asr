import { useT } from "../useLocale";
import { TuningPopover } from "./TuningPopover";

/* ============================================================
   FeatureToggles — inline an der Transcribe-Zeile (Task 9)
   ============================================================ */

export interface FeatureValues {
  vad: boolean;
  diarize: boolean;
  streaming: boolean;
  noise: boolean;
  enhance: string;
  backend: string;
  punctuation: boolean;
  llmEnhance: boolean;
  templateId: number | undefined;
  targetId: number | undefined;
  endpointId: number | undefined;
  /** Diarization-Tuning (ausklappbar): bekannte Sprecherzahl, "" = auto */
  numSpeakers: string;
  /** Diarization-Tuning: Sensitivität "more" | "std" | "less" */
  diarSens: string;
  /** Diarization-Tuning: Methode "" (Server-Default) | pyannote | foxnose | energy */
  diarMethod: string;
}

/** Sensitivität → min_duration_off (Sek.): less = weniger Sprecherwechsel */
export function diarSensToMinDurationOff(sens: string): number | undefined {
  if (sens === "less") return 0.4;
  if (sens === "more") return 0.05;
  return undefined; // "std" → Pipeline-Default
}

export interface PostProcessOptions {
  templates: { template_id: number; name: string }[];
  targets: { target_id: number; name: string; kind: string }[];
  endpoints: { endpoint_id: number; name: string }[];
  isOidc: boolean;
}

interface Props {
  values: FeatureValues;
  backends: string[]; // verfügbare Backend-Namen (Matrix, status active)
  /** Ob das AKTUELL gewählte Backend Streaming/Live unterstützt (aus der
   * Feature-Matrix). false → Live-Toggle wird ausgeblendet (Backend würde
   * den Modus still ignorieren). */
  streamingSupported?: boolean;
  /** Streaming-Fähigkeit je Backend-Name — beim Backend-Wechsel wird der
   * Live-Wert zurückgesetzt, wenn das neue Backend kein Streaming kann. */
  streamingByBackend?: Record<string, boolean>;
  flags?: { vad?: boolean; diarize?: boolean };
  pp?: PostProcessOptions;
  onChange: (patch: Partial<FeatureValues>) => void;
}

function MiniToggle({ label, on, disabled, onChange }: {
  label: string; on: boolean; disabled?: boolean; onChange: (v: boolean) => void;
}) {
  return (
    <label
      className={`flex items-center gap-1 text-[11px] select-none cursor-pointer ${
        disabled ? "opacity-40 cursor-not-allowed" : ""
      }`}
    >
      <input
        type="checkbox"
        checked={on}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
        className="accent-[#5b8cff]"
      />
      {label}
    </label>
  );
}

export function FeatureToggles({ values, backends, streamingSupported, streamingByBackend, flags, pp, onChange }: Props) {
  const { t } = useT();
  const vadOk = flags?.vad ?? true;
  const diarOk = flags?.diarize ?? true;
  const oidc = pp?.isOidc ?? false;
  const templates = pp?.templates ?? [];
  const targets = pp?.targets ?? [];
  const endpoints = pp?.endpoints ?? [];
  return (
    <div className="flex flex-wrap items-center justify-center gap-x-3 gap-y-1 px-2">
      <MiniToggle label="VAD" on={values.vad} disabled={!vadOk} onChange={(v) => onChange({ vad: v })} />
      <MiniToggle label="🎙 Speaker" on={values.diarize} disabled={!diarOk} onChange={(v) => onChange({ diarize: v })} />
      {values.diarize && (
        <TuningPopover label={t("diarize_tuning")}>
          <label className="flex flex-col gap-1 text-[11px]">
              {t("diarize_speakers")}
              <select
                value={values.numSpeakers}
                onChange={(e) => onChange({ numSpeakers: e.target.value })}
                className="bg-panel2 border border-border rounded-sm text-[11px] px-1 py-[2px] text-muted"
              >
                <option value="">{t("diarize_auto")}</option>
                <option value="1">1</option>
                <option value="2">2</option>
                <option value="3">3</option>
                <option value="4">4+</option>
              </select>
            </label>
            <label className="flex flex-col gap-1 text-[11px]">
              {t("diarize_sensitivity")}
              <select
                value={values.diarSens}
                onChange={(e) => onChange({ diarSens: e.target.value })}
                className="bg-panel2 border border-border rounded-sm text-[11px] px-1 py-[2px] text-muted"
              >
                <option value="less">{t("diarize_less_switches")}</option>
                <option value="std">{t("diarize_std")}</option>
                <option value="more">{t("diarize_more_detail")}</option>
              </select>
            </label>
            <label className="flex flex-col gap-1 text-[11px]">
              {t("diarize_method")}
              <select
                value={values.diarMethod}
                onChange={(e) => onChange({ diarMethod: e.target.value })}
                className="bg-panel2 border border-border rounded-sm text-[11px] px-1 py-[2px] text-muted"
              >
                <option value="">{t("diarize_method_default")}</option>
                <option value="pyannote">pyannote</option>
                <option value="foxnose">foxnose</option>
                <option value="energy">energy</option>
              </select>
            </label>
        </TuningPopover>
      )}
      {/* Live nur anbieten, wenn das gewählte Backend Streaming kann —
          sonst würde der Modus im Backend still ignoriert (stiller Fehler). */}
      {streamingSupported !== false && (
        <MiniToggle label="⚡ Live" on={values.streaming} onChange={(v) => onChange({ streaming: v })} />
      )}
      <MiniToggle label="🔇 NR" on={values.noise} onChange={(v) => onChange({ noise: v })} />
      <select
        value={values.enhance}
        onChange={(e) => onChange({ enhance: e.target.value })}
        className="bg-panel2 border border-border rounded-sm text-[11px] px-1 py-[2px] text-muted"
        title="Enhance"
      >
        <option value="off">Enhance: off</option>
        <option value="light">Enhance: light</option>
        <option value="strong">Enhance: strong</option>
      </select>
      {backends.length > 0 && (
        <select
          value={values.backend}
          onChange={(e) => {
            const b = e.target.value;
            // Backend ohne Streaming → Live-Wert zurücksetzen (sonst würde
            // der Modus still ignoriert).
            const patch: Partial<FeatureValues> = { backend: b };
            if (streamingByBackend?.[b] === false) patch.streaming = false;
            onChange(patch);
          }}
          className="bg-panel2 border border-border rounded-sm text-[11px] px-1 py-[2px] text-muted"
          title={t("backend")}
        >
          <option value="">{t("default_backend")}</option>
          {backends.map((b) => (
            <option key={b} value={b}>
              {b}
            </option>
          ))}
        </select>
      )}
      {/* ── Teil D: opt-in Post-Processing — nur für eingeloggte User ── */}
      {oidc && (
        <>
          <MiniToggle
            label={t("punctuation")}
            on={values.punctuation}
            onChange={(v) => onChange({ punctuation: v })}
          />
          <MiniToggle
            label={t("llm_enhance")}
            on={values.llmEnhance}
            disabled={!oidc}
            onChange={(v) => onChange({ llmEnhance: v })}
          />
          <select
            value={values.templateId ?? ""}
            disabled={!oidc}
            onChange={(e) => onChange({ templateId: e.target.value ? Number(e.target.value) : undefined })}
            className="bg-panel2 border border-border rounded-sm text-[11px] px-1 py-[2px] text-muted disabled:opacity-40"
            title={t("template")}
          >
            <option value="">{t("template")}: —</option>
            {templates.map((tp) => (
              <option key={tp.template_id} value={tp.template_id}>
                {t("template")}: {tp.name}
              </option>
            ))}
          </select>
          <select
            value={values.endpointId ?? ""}
            disabled={!oidc || endpoints.length === 0}
            onChange={(e) => onChange({ endpointId: e.target.value ? Number(e.target.value) : undefined })}
            className="bg-panel2 border border-border rounded-sm text-[11px] px-1 py-[2px] text-muted disabled:opacity-40"
            title={t("llm_endpoint")}
          >
            <option value="">{t("llm_endpoint")}: {t("server_default")}</option>
            {endpoints.map((ep) => (
              <option key={ep.endpoint_id} value={ep.endpoint_id}>
                {t("llm_endpoint")}: {ep.name}
              </option>
            ))}
          </select>
          <select
            value={values.targetId ?? ""}
            onChange={(e) => onChange({ targetId: e.target.value ? Number(e.target.value) : undefined })}
            className="bg-panel2 border border-border rounded-sm text-[11px] px-1 py-[2px] text-muted"
            title={t("send_to")}
          >
            <option value="">{t("send_to")}: —</option>
            {targets.map((tg) => (
              <option key={tg.target_id} value={tg.target_id}>
                {t("send_to")}: {tg.name}
              </option>
            ))}
          </select>
        </>
      )}
    </div>
  );
}
