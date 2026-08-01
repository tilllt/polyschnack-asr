import { useT } from "../useLocale";

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
}

interface Props {
  values: FeatureValues;
  backends: string[]; // verfügbare Backend-Namen (Matrix, status active)
  flags?: { vad?: boolean; diarize?: boolean };
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

export function FeatureToggles({ values, backends, flags, onChange }: Props) {
  const { t } = useT();
  const vadOk = flags?.vad ?? true;
  const diarOk = flags?.diarize ?? true;
  return (
    <div className="flex flex-wrap items-center justify-center gap-x-3 gap-y-1 px-2">
      <MiniToggle label="VAD" on={values.vad} disabled={!vadOk} onChange={(v) => onChange({ vad: v })} />
      <MiniToggle label="🎙 Speaker" on={values.diarize} disabled={!diarOk} onChange={(v) => onChange({ diarize: v })} />
      <MiniToggle label="⚡ Live" on={values.streaming} onChange={(v) => onChange({ streaming: v })} />
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
          onChange={(e) => onChange({ backend: e.target.value })}
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
    </div>
  );
}
