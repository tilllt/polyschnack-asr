import { useT } from "../useLocale";

/**
 * ImportToggles — kompakte Feature-Auswahl für Upload/YouTube-Import.
 *
 * Seit Task 9 leben die Feature-Toggles an der Transcribe-Zeile der
 * RecordingCard — aber beim Upload/Import gibt es noch KEINE Aufnahme,
 * die Werte waren hart auf Defaults gesetzt (diarize=false etc.).
 * Diese Reihe erlaubt die Auswahl VOR dem Upload/Import; die Werte
 * werden als enable_*-Flags an der angelegten Recording gespeichert.
 * (2026-08-14, User-Befund: „Keine Diarization bei YouTube-Download")
 */

export interface ImportFeatureValues {
  vad: boolean;
  diarize: boolean;
  numSpeakers: string;
  diarSens: string;
  streaming: boolean;
  noise: boolean;
  enhance: string;
}

export const IMPORT_DEFAULTS: ImportFeatureValues = {
  vad: false,
  diarize: false,
  numSpeakers: "",
  diarSens: "std",
  streaming: false,
  noise: true,
  enhance: "off",
};

function MiniToggle({ label, on, onChange }: {
  label: string; on: boolean; onChange: (v: boolean) => void;
}) {
  return (
    <label className="flex items-center gap-1 text-[11px] select-none cursor-pointer">
      <input
        type="checkbox"
        checked={on}
        onChange={(e) => onChange(e.target.checked)}
        className="accent-[#5b8cff]"
      />
      {label}
    </label>
  );
}

export function ImportToggles({ values, onChange }: {
  values: ImportFeatureValues;
  onChange: (p: Partial<ImportFeatureValues>) => void;
}) {
  const { t } = useT();
  return (
    <div className="flex flex-wrap items-center justify-center gap-x-3 gap-y-1 px-2">
      <MiniToggle label="VAD" on={values.vad} onChange={(v) => onChange({ vad: v })} />
      <MiniToggle label="🎙 Speaker" on={values.diarize} onChange={(v) => onChange({ diarize: v })} />
      {values.diarize && (
        <details className="relative">
          <summary className="text-[11px] text-muted cursor-pointer select-none px-1 py-[2px] border border-border rounded-sm bg-panel2">
            {t("diarize_tuning")}
          </summary>
          <div className="absolute right-0 bottom-full mb-1 z-20 flex flex-col gap-2 bg-panel3 border border-border2 rounded-sm px-3 py-2 shadow-[0_8px_24px_rgba(0,0,0,.4)] min-w-[200px]">
            <label className="flex flex-col gap-1 text-[11px]">
              {t("diarize_speakers")}
              <select
                value={values.numSpeakers}
                onChange={(e) => onChange({ numSpeakers: e.target.value })}
                className="bg-panel2 border border-border rounded-sm text-[11px] px-1 py-[2px] text-muted"
              >
                <option value="">—</option>
                {[2, 3, 4, 5, 6].map((n) => (
                  <option key={n} value={n}>{n}</option>
                ))}
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
          </div>
        </details>
      )}
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
        <option value="medium">Enhance: medium</option>
        <option value="aggressive">Enhance: aggressive</option>
      </select>
    </div>
  );
}
