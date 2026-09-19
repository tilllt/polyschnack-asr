import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Loader2, X, Download, AlertTriangle, Info, ChevronDown, Sparkles } from "lucide-react";
import type {
  AssExportResult,
  ExportCatalog,
  ExportParamSpec,
  Recording,
  RenderFormat,
  RenderJob,
} from "../api";
import {
  AssExportError,
  cancelRenderJob,
  downloadUrl,
  fetchAssExport,
  fetchExportPresets,
  fetchRenderJob,
  renderFileUrl,
  startRender,
} from "../api";
import { useT } from "../useLocale";
import { useToast } from "./Toasts";

/* Change 193 — Export-Dialog für animierte ASS-Untertitel.
 *
 * Bewusste Entscheidungen:
 * - Der Katalog (Presets + Parameter-Schema) kommt komplett vom Backend; die
 *   UI erfindet weder Grenzen noch Beschriftungen. Gezeigt werden nur die
 *   Parameter, die das jeweilige Preset in seiner Vorlage wirklich benutzt
 *   (`used_params`) — sonst stünden Regler im Dialog, die nichts bewirken.
 * - Der Download läuft über fetch + Blob, nicht über einen <a href>: nur so
 *   sind Fehler (409 „keine Wortzeiten") und die Warn-Header sichtbar.
 * - Kein Rendern-Knopf, solange das Backend `render_available: false` meldet.
 */

/** Diese Parameter stehen direkt sichtbar; der Rest liegt unter „Weitere Optionen". */
const PRIMARY_PARAMS = [
  "font_size",
  "words_per_line",
  "position",
  "text_color",
  "accent_color",
  "dim_color",
  "tail_ms",
  "uppercase",
];

type ParamValue = number | string | boolean;

function descriptionFor(preset: ExportCatalog["presets"][number], lang: string): string {
  if (lang === "pt-BR" && preset.description_pt) return preset.description_pt;
  if (lang === "en" && preset.description_en) return preset.description_en;
  return preset.description || preset.description_en || preset.description_pt || "";
}

export function ExportDialog({
  recording,
  onClose,
}: {
  recording: Recording;
  onClose: () => void;
}) {
  const { t, lang } = useT();
  const { toast } = useToast();
  // Katalog über React Query (Projektstandard): gecacht, aber pro Test-Client
  // isoliert — kein Modul-Global, das zwischen Tests hängen bleibt.
  const catalogQuery = useQuery({
    queryKey: ["export-presets"],
    queryFn: fetchExportPresets,
    staleTime: Infinity,
  });
  const catalog: ExportCatalog | null = catalogQuery.data ?? null;
  const loadError = catalogQuery.error ? (catalogQuery.error as Error).message : null;
  const [preset, setPreset] = useState<string>("");
  const [values, setValues] = useState<Record<string, ParamValue>>({});
  const [advanced, setAdvanced] = useState(false);
  const [busy, setBusy] = useState(false);
  const [exportError, setExportError] = useState<{ code: string; hint: string } | null>(null);
  const [result, setResult] = useState<AssExportResult | null>(null);

  // ---- Change 200: Video-Export über den Render-Dienst ---------------------
  const [renderFormat, setRenderFormat] = useState<string>("");
  const [renderJob, setRenderJob] = useState<RenderJob | null>(null);
  const [renderBusy, setRenderBusy] = useState(false);
  const [renderError, setRenderError] = useState<{ code: string; hint: string } | null>(null);
  const renderFormats: RenderFormat[] = catalog?.render_formats ?? [];
  const renderAvailable = Boolean(catalog?.render_available) && renderFormats.length > 0;

  useEffect(() => {
    if (renderFormat || renderFormats.length === 0) return;
    // Transparentes WebM ist der häufigste Wunsch (Overlay im Schnittprogramm),
    // sonst das erste Format, das der Dienst meldet.
    const preferred = renderFormats.find((f) => f.id === "alpha_webm") ?? renderFormats[0];
    setRenderFormat(preferred.id);
  }, [renderFormats, renderFormat]);

  // Fortschritt pollen, solange ein Auftrag läuft. Der Prozentwert kommt aus
  // ffmpeg — ist er 0, sagen wir das (statt einen Fortschritt zu erfinden).
  const renderState = renderJob?.state;
  useEffect(() => {
    if (!renderJob) return;
    if (renderState !== "running" && renderState !== "queued") return;
    const jobId = renderJob.id;
    let alive = true;
    const tick = async () => {
      try {
        const job = await fetchRenderJob(recording.uid, jobId);
        if (alive) setRenderJob(job);
      } catch (e) {
        if (!alive) return;
        const err = e as AssExportError;
        setRenderError({ code: err.code ?? "unknown_error", hint: err.hint ?? err.message ?? "" });
        setRenderJob(null);
      }
    };
    void tick();
    const timer = setInterval(tick, 2000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [renderJob?.id, renderState, recording.uid]);

  async function handleRender() {
    if (!activePreset || !renderFormat) return;
    setRenderBusy(true);
    setRenderError(null);
    setRenderJob(null);
    try {
      const job = await startRender(recording.uid, {
        preset: activePreset.name,
        params: payload,
        format: renderFormat,
        fps: 25,
      });
      setRenderJob(job);
      toast(t("ass_render_started"), "ok");
    } catch (e) {
      const err = e as AssExportError;
      setRenderError({ code: err.code ?? "unknown_error", hint: err.hint ?? err.message ?? "" });
      toast(t("ass_render_failed"), "err");
    } finally {
      setRenderBusy(false);
    }
  }

  async function handleRenderCancel() {
    if (!renderJob) return;
    try {
      setRenderJob(await cancelRenderJob(recording.uid, renderJob.id));
    } catch (e) {
      const err = e as AssExportError;
      setRenderError({ code: err.code ?? "unknown_error", hint: err.hint ?? err.message ?? "" });
    }
  }

  // Vorbelegung: „Hervorhebung" ist der meistgenutzte Stil, sonst das erste Preset.
  useEffect(() => {
    if (!catalog || preset) return;
    const initial = catalog.presets.find((p) => p.name === "highlight") ?? catalog.presets[0];
    if (initial) setPreset(initial.name);
  }, [catalog, preset]);

  const activePreset = useMemo(
    () => catalog?.presets.find((p) => p.name === preset) ?? null,
    [catalog, preset],
  );

  // Preset-Wechsel lädt dessen Standardwerte — jedes Preset ist ein Look.
  useEffect(() => {
    if (activePreset) setValues({ ...activePreset.parameters });
  }, [activePreset]);

  // Escape schließt (nicht während eines laufenden Downloads).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !busy) onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [busy, onClose]);

  const spec = (key: string): ExportParamSpec | undefined => catalog?.parameter_specs[key];

  /** Nur die Parameter senden, die das Preset benutzt. */
  const payload = useMemo(() => {
    const out: Record<string, ParamValue> = {};
    for (const key of activePreset?.used_params ?? []) {
      if (key in values) out[key] = values[key];
    }
    return out;
  }, [activePreset, values]);

  const usedVisible = (activePreset?.used_params ?? []).filter((k) => spec(k));
  const primaryKeys = usedVisible.filter((k) => PRIMARY_PARAMS.includes(k));
  const advancedKeys = usedVisible.filter((k) => !PRIMARY_PARAMS.includes(k));

  async function handleDownload() {
    if (!activePreset) return;
    setBusy(true);
    setExportError(null);
    setResult(null);
    try {
      const res = await fetchAssExport(recording.uid, activePreset.name, payload);
      downloadUrl(res.url, res.filename);
      setResult(res);
      toast(t("ass_export_ok"), "ok");
    } catch (e) {
      const err = e as AssExportError;
      setExportError({
        code: err.code ?? "unknown_error",
        hint: err.hint ?? (err.message ?? ""),
      });
      toast(t("ass_export_failed"), "err");
    } finally {
      setBusy(false);
    }
  }

  function errorText(code: string, hint: string): string {
    const key = `ass_err_${code}`;
    const mapped = t(key);
    const base = mapped === key ? `${t("ass_err_generic")} (${code})` : mapped;
    return hint ? `${base} — ${hint}` : base;
  }

  function warningText(w: string): string {
    if (w === "uniform_timing") return t("ass_warn_uniform_timing");
    if (w === "fallback_timing_words") return t("ass_warn_fallback_timing_words");
    if (w.startsWith("skipped_segments:")) return t("ass_warn_skipped_segments");
    if (w.startsWith("skipped_words:")) return t("ass_warn_skipped_words");
    if (w.startsWith("preset_style_source_invalid:")) return t("ass_warn_preset_style");
    // Change 201: Schriftgroesse an der Bildschirmbreite ausgerichtet
    if (w.startsWith("fit_overflow:")) {
      const n = w.slice("fit_overflow:".length);
      return t("ass_warn_fit_overflow").replace("{n}", n);
    }
    if (w.startsWith("fit_unavailable:")) return t("ass_warn_fit_unavailable");
    // Change 202: Vorlage übernimmt die berechnete Größe je Zeile nicht
    if (w.startsWith("fit_tag_missing:")) {
      const preset = w.slice("fit_tag_missing:".length);
      return t("ass_warn_fit_tag_missing")
        .replace("{tag}", "fs_tag")
        .replace("{preset}", preset);
    }
    return w;
  }

  return (
    <div
      className="fixed inset-0 z-[60] bg-black/40 flex items-center justify-center p-4"
      onClick={() => {
        if (!busy) onClose();
      }}
      data-testid="export-dialog"
    >
      <div
        className="bg-panel border border-border rounded-md w-full max-w-[580px] max-h-[88dvh] overflow-y-auto shadow-xl p-4"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start gap-2 mb-1">
          <Sparkles size={14} className="text-accent mt-[2px]" />
          <div className="flex-1 min-w-0">
            <div className="text-[14px] font-semibold leading-tight">{t("ass_export_title")}</div>
            <div className="text-[11px] text-muted2 truncate">
              {recording.title ?? recording.original_name}
            </div>
          </div>
          <button
            onClick={onClose}
            disabled={busy}
            title={t("ass_export_close")}
            className="text-muted2 hover:text-txt disabled:opacity-40"
            data-testid="export-dialog-close"
          >
            <X size={15} />
          </button>
        </div>

        {loadError && (
          <div className="text-[11px] text-red-400 bg-red-500/10 border border-red-500/30 rounded-sm px-2 py-1.5 my-2">
            {t("ass_export_catalog_error")} — {loadError}
          </div>
        )}

        {!catalog && !loadError && (
          <div className="flex items-center gap-2 text-[12px] text-muted2 py-6 justify-center">
            <Loader2 size={14} className="animate-spin" />
            {t("ass_export_loading")}
          </div>
        )}

        {catalog && (
          <>
            {/* Preset-Auswahl */}
            <div className="text-[11px] uppercase tracking-wide text-muted2 mt-3 mb-1.5">
              {t("ass_export_preset")}
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5">
              {catalog.presets.map((p) => {
                const on = p.name === preset;
                return (
                  <button
                    key={p.name}
                    type="button"
                    onClick={() => setPreset(p.name)}
                    aria-pressed={on}
                    data-testid={`preset-${p.name}`}
                    className={`text-left px-2.5 py-2 rounded-sm border transition-colors ${
                      on
                        ? "border-accent/60 bg-accent/[.1]"
                        : "border-border2 bg-panel2/50 hover:border-white/15"
                    }`}
                  >
                    <div className={`text-[12px] font-semibold ${on ? "text-accent" : "text-txt"}`}>
                      {p.title}
                    </div>
                    <div className="text-[11px] text-muted2 leading-[1.35] mt-[2px]">
                      {descriptionFor(p, lang)}
                    </div>
                  </button>
                );
              })}
            </div>

            {/* Parameter */}
            {activePreset && primaryKeys.length > 0 && (
              <div className="mt-3 border border-border rounded-sm bg-panel2/40 px-2.5 py-1.5">
                {primaryKeys.map((key) => (
                  <ParamRow
                    key={key}
                    name={key}
                    spec={spec(key)!}
                    value={values[key]}
                    onChange={(v) => setValues((s) => ({ ...s, [key]: v }))}
                  />
                ))}
              </div>
            )}

            {advancedKeys.length > 0 && (
              <>
                <button
                  type="button"
                  onClick={() => setAdvanced((a) => !a)}
                  aria-expanded={advanced}
                  data-testid="export-advanced-toggle"
                  className="mt-2 flex items-center gap-1 text-[11px] text-muted2 hover:text-txt"
                >
                  <ChevronDown
                    size={12}
                    className={`transition-transform ${advanced ? "rotate-180" : ""}`}
                  />
                  {t("ass_export_more_options")}
                </button>
                {advanced && (
                  <div className="mt-1.5 border border-border rounded-sm bg-panel2/40 px-2.5 py-1.5">
                    {advancedKeys.map((key) => (
                      <ParamRow
                        key={key}
                        name={key}
                        spec={spec(key)!}
                        value={values[key]}
                        onChange={(v) => setValues((s) => ({ ...s, [key]: v }))}
                      />
                    ))}
                  </div>
                )}
              </>
            )}

            {/* Kein Render-Dienst: sagen, was mit der Datei geht, statt einen
                Knopf zu zeigen, der nur 503 liefert. */}
            {!renderAvailable && (
              <div className="flex items-start gap-1.5 text-[11px] text-muted2 mt-3">
                <Info size={12} className="mt-[2px] shrink-0" />
                <span>
                  {t("ass_export_render_off")}
                  {catalog.render_note ? ` (${catalog.render_note})` : ""}
                </span>
              </div>
            )}

            {renderAvailable && (
              <div className="mt-4 pt-3 border-t border-border2" data-testid="render-section">
                <div className="text-[11px] text-muted2 mb-2">{t("ass_render_title")}</div>
                <div className="space-y-1.5">
                  {renderFormats.map((f) => (
                    <label
                      key={f.id}
                      className="flex items-start gap-2 text-[12px] cursor-pointer"
                      data-testid={`render-format-${f.id}`}
                    >
                      <input
                        type="radio"
                        name="render-format"
                        className="mt-[3px]"
                        checked={renderFormat === f.id}
                        onChange={() => setRenderFormat(f.id)}
                      />
                      <span>
                        <span className="text-txt">{f.label}</span>
                        {f.note ? (
                          <span className="block text-[11px] text-muted2">{f.note}</span>
                        ) : null}
                      </span>
                    </label>
                  ))}
                </div>

                <button
                  type="button"
                  onClick={handleRender}
                  disabled={renderBusy || renderState === "running" || renderState === "queued"}
                  className="btn-ghost-sm mt-3 flex items-center gap-1.5 disabled:opacity-40"
                  data-testid="render-start"
                >
                  {renderState === "running" || renderState === "queued" ? (
                    <Loader2 size={12} className="animate-spin" />
                  ) : (
                    <Sparkles size={12} />
                  )}
                  {renderState === "running" || renderState === "queued"
                    ? t("ass_render_running")
                    : t("ass_render_start")}
                </button>

                {renderJob && (renderState === "running" || renderState === "queued") && (
                  <div className="mt-2" data-testid="render-progress">
                    <div className="h-1.5 w-full bg-panel2 rounded-[3px] overflow-hidden">
                      <div
                        className="h-full bg-accent transition-[width] duration-300"
                        style={{ width: `${Math.round((renderJob.progress || 0) * 100)}%` }}
                      />
                    </div>
                    <div className="mt-1 text-[11px] text-muted2">
                      {renderJob.progress > 0
                        ? `${Math.round(renderJob.progress * 100)} %`
                        : t("ass_render_waiting")}
                      {" · "}
                      <button
                        type="button"
                        onClick={handleRenderCancel}
                        className="underline decoration-dotted"
                        data-testid="render-cancel"
                      >
                        {t("ass_render_cancel")}
                      </button>
                    </div>
                  </div>
                )}

                {renderJob && renderState === "canceled" && (
                  <div className="mt-2 text-[11px] text-muted2" data-testid="render-canceled">
                    {t("ass_render_canceled")}
                  </div>
                )}

                {renderJob && renderState === "done" && (
                  <div className="mt-2 text-[11px]" data-testid="render-done">
                    {/* Anker auf die API-URL — der Browser lädt die Datei selbst
                        (Blob-Downloads verwerfen manche Browser still). */}
                    <a
                      href={renderFileUrl(recording.uid, renderJob.id)}
                      download={renderJob.filename}
                      className="text-accent underline decoration-dotted"
                      data-testid="render-download"
                    >
                      {t("ass_render_download")}
                    </a>
                    {renderJob.size_bytes > 0 ? (
                      <span className="text-muted2">
                        {" · "}
                        {(renderJob.size_bytes / (1024 * 1024)).toFixed(1)} MB
                      </span>
                    ) : null}
                  </div>
                )}

                {renderJob && renderState === "failed" && (
                  <div
                    className="mt-2 text-[11px] text-red-300 bg-red-500/10 border border-red-500/30 rounded-sm px-2 py-1.5"
                    data-testid="render-failed"
                  >
                    {t("ass_render_failed")}
                    {renderJob.error ? `: ${renderJob.error.slice(0, 300)}` : ""}
                  </div>
                )}

                {renderError && (
                  <div
                    className="mt-2 text-[11px] text-red-300 bg-red-500/10 border border-red-500/30 rounded-sm px-2 py-1.5"
                    data-testid="render-request-error"
                  >
                    {errorText(renderError.code, renderError.hint)}
                  </div>
                )}
              </div>
            )}

            {exportError && (
              <div
                className="mt-3 text-[11px] text-red-300 bg-red-500/10 border border-red-500/30 rounded-sm px-2 py-1.5"
                data-testid="ass-export-error"
              >
                {errorText(exportError.code, exportError.hint)}
              </div>
            )}

            {result && result.warnings.length > 0 && (
              <div
                className="mt-3 text-[11px] text-amber-300 bg-amber-500/10 border border-amber-500/30 rounded-sm px-2 py-1.5 space-y-0.5"
                data-testid="ass-export-warning"
              >
                {result.warnings.map((w) => (
                  <div key={w} className="flex items-start gap-1.5">
                    <AlertTriangle size={12} className="mt-[2px] shrink-0" />
                    <span>{warningText(w)}</span>
                  </div>
                ))}
              </div>
            )}

            {result && result.warnings.length === 0 && (
              <div
                className="mt-3 text-[11px] text-muted2"
                data-testid="ass-export-result"
              >
                {result.words} {t("ass_export_words")} · {result.lines} {t("ass_export_lines")}
              </div>
            )}

            {/* Ersatzweg, immer sichtbar sobald eine Datei erzeugt wurde: einige
                Browser verwerfen programmatisch ausgelöste Downloads still — ein
                Link, den der Nutzer selbst anklickt, funktioniert dort zuverlässig. */}
            {result && (
              <div className="mt-1 text-[11px] text-muted2">
                <a
                  href={result.url}
                  download={result.filename}
                  className="text-accent underline decoration-dotted"
                  data-testid="ass-export-fallback"
                >
                  {t("ass_export_fallback")}
                </a>
              </div>
            )}

            {/* Aktionen */}
            <div className="flex items-center gap-2 mt-4">
              <button
                type="button"
                onClick={onClose}
                disabled={busy}
                className="btn-ghost-sm disabled:opacity-40"
              >
                {t("ass_export_close")}
              </button>
              <button
                type="button"
                onClick={handleDownload}
                disabled={busy || !activePreset}
                data-testid="ass-export-download"
                className="ml-auto flex items-center gap-1.5 bg-accent/[.12] text-accent border border-accent/30 rounded-sm px-3 py-[5px] text-[12px] font-medium hover:bg-accent/[.18] disabled:opacity-40"
              >
                {busy ? <Loader2 size={13} className="animate-spin" /> : <Download size={13} />}
                {busy ? t("ass_export_working") : t("ass_export_download")}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function ParamRow({
  name,
  spec,
  value,
  onChange,
}: {
  name: string;
  spec: ExportParamSpec;
  value: ParamValue | undefined;
  onChange: (v: ParamValue) => void;
}) {
  const { t } = useT();
  const label = t(`ep_${name}`);
  const inputCls =
    "bg-panel border border-border rounded-sm px-1.5 py-[3px] text-[12px] outline-none focus:border-accent";

  return (
    <div className="flex items-center gap-2 min-h-[26px] py-[2px]">
      <span className="text-[12px] flex-1 min-w-0">{label === `ep_${name}` ? name : label}</span>

      {spec.type === "int" && (spec.max ?? 0) - (spec.min ?? 0) <= 1000 && (
        <div className="flex items-center gap-2" data-testid={`param-${name}`}>
          <input
            type="range"
            min={spec.min}
            max={spec.max}
            step={1}
            value={Number(value ?? spec.min ?? 0)}
            onChange={(e) => onChange(Number(e.target.value))}
            className="accent-[#2ea043] w-[150px] cursor-pointer"
          />
          <span className="tabular-nums text-[12px] text-muted2 w-[38px] text-right">
            {Number(value ?? 0)}
          </span>
        </div>
      )}

      {spec.type === "int" && (spec.max ?? 0) - (spec.min ?? 0) > 1000 && (
        <input
          type="number"
          min={spec.min}
          max={spec.max}
          value={Number(value ?? 0)}
          onChange={(e) => onChange(Number(e.target.value))}
          data-testid={`param-${name}`}
          className={`${inputCls} w-[76px] tabular-nums`}
        />
      )}

      {spec.type === "color" && (
        <div className="flex items-center gap-1.5" data-testid={`param-${name}`}>
          <input
            type="color"
            value={String(value ?? "#FFFFFF")}
            onChange={(e) => onChange(e.target.value)}
            className="w-[34px] h-[22px] bg-transparent border border-border2 rounded-sm cursor-pointer"
          />
          <span className="text-[11px] text-muted2 tabular-nums">
            {String(value ?? "").toUpperCase()}
          </span>
        </div>
      )}

      {spec.type === "bool" && (
        <input
          type="checkbox"
          checked={Boolean(value)}
          onChange={(e) => onChange(e.target.checked)}
          data-testid={`param-${name}`}
          className="accent-[#2ea043] w-[15px] h-[15px] cursor-pointer"
        />
      )}

      {spec.type === "enum" && (
        <select
          value={String(value ?? "")}
          onChange={(e) => onChange(e.target.value)}
          data-testid={`param-${name}`}
          className="bg-panel2 border border-border2 rounded-sm text-[11px] px-1.5 py-[3px] text-txt cursor-pointer"
        >
          {(spec.values ?? []).map((v) => {
            const vk = `ass_pos_${v}`;
            const vl = t(vk);
            return (
              <option key={v} value={v}>
                {vl === vk ? v : vl}
              </option>
            );
          })}
        </select>
      )}

      {spec.type === "str" && (
        <input
          type="text"
          value={String(value ?? "")}
          maxLength={spec.max_len}
          onChange={(e) => onChange(e.target.value)}
          data-testid={`param-${name}`}
          className={`${inputCls} w-[140px]`}
        />
      )}
    </div>
  );
}
