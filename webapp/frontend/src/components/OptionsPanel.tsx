import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { useT } from "../useLocale";
import { useDismiss } from "../useDismiss";
import { useFlipUp } from "../useFlipUp";
import type { BackendCapabilities } from "../api";
import type { FeatureValues, PostProcessOptions } from "./FeatureToggles";
import {
  ENHANCE_LEVELS,
  optionAvailability,
  rowsOf,
  pick,
  REASON,
  type OptionCategory,
  type OptionRow,
  type OptionSource,
  type OptionAvailability,
} from "../optionMatrix";

/* ============================================================
   OptionsPanel — Change 116 (App-Redesign v7) / Change 212

   Ein Panel für alle Quellen (Datei-Upload · Aufnahme · URL-Import)
   und für die Recording-Ansicht. Was angeboten wird, entscheidet
   ausschließlich die Matrix in `src/optionMatrix.ts` zusammen mit
   den Backend-Fähigkeiten aus `/api/backends` — hier wird nichts
   je Kategorie von Hand gepflegt.

   Beschriftungen sind Klartext (de/en/pt); Fachbegriffe wie „VAD“
   oder „Speaker“ kommen in der Oberfläche nicht mehr vor.
   ============================================================ */

export type ActionId = "tr" | "spk" | "alg";

type S = { de: string; en: string; pt: string };
const L = (d: S, lang: string): string => pick(d, lang);

/** Werte-Beschriftungen und Hinweise (die Options-Beschriftungen stehen in der
 *  Matrix, damit eine Option nur EINE Beschriftung hat). */
const TXT: Record<string, S> = {
  tab_pre: { de: "Vorbereitung", en: "Preparation", pt: "Preparação" },
  tab_spk: { de: "Sprechererkennung", en: "Speakers", pt: "Falantes" },
  tab_post: { de: "Nachbearbeitung", en: "Post-processing", pt: "Pós-processamento" },
  vad_off: { de: "Aus", en: "Off", pt: "Desligado" },
  vad_edges: { de: "Ränder", en: "Edges", pt: "Bordas" },
  vad_all: { de: "Überall", en: "Everywhere", pt: "Em todo lugar" },
  m_a: { de: "Methode A (htdemucs)", en: "Method A (htdemucs)", pt: "Método A (htdemucs)" },
  m_b: { de: "Methode B (mel-band)", en: "Method B (mel-band)", pt: "Método B (mel-band)" },
  model_std: { de: "Standard (Server)", en: "Default (server)", pt: "Padrão (servidor)" },
  num_auto: { de: "Automatisch", en: "Automatic", pt: "Automático" },
  sens_less: { de: "Weniger", en: "Less", pt: "Menos" },
  sens_std: { de: "Standard", en: "Standard", pt: "Padrão" },
  sens_more: { de: "Mehr", en: "More", pt: "Mais" },
  met_auto: { de: "Automatisch (Server)", en: "Automatic (server)", pt: "Automático (servidor)" },
  met_a: { de: "Methode A (pyannote)", en: "Method A (pyannote)", pt: "Método A (pyannote)" },
  met_b: { de: "Methode B (foxnose)", en: "Method B (foxnose)", pt: "Método B (foxnose)" },
  met_c: { de: "Methode C (Energie)", en: "Method C (energy)", pt: "Método C (energia)" },
  ep_std: { de: "Standard (Server)", en: "Default (server)", pt: "Padrão (servidor)" },
  none: { de: "—", en: "—", pt: "—" },
  opt_cat_hint: {
    de: "Für diese Auswahl ist keine Option dieser Gruppe wirksam.",
    en: "No option of this group has an effect for this selection.",
    pt: "Nenhuma opção deste grupo tem efeito para esta seleção.",
  },
};

/** „?“-Hilfen: Modell/Technik-Zeile. Die Erklärung (Klartext) steht als
 *  `note` in der Matrix und wird dort gepflegt. */
const TECHNIQUE: Record<string, S> = {
  vad: {
    de: "Silero VAD (silero_vad.onnx, MIT) — läuft im Server per ONNX Runtime.",
    en: "Silero VAD (silero_vad.onnx, MIT) — runs on the server via ONNX Runtime.",
    pt: "Silero VAD (silero_vad.onnx, MIT) — roda no servidor via ONNX Runtime.",
  },
  noise: {
    de: "noisereduce (spektrales Gating) im ASR-Dienst.",
    en: "noisereduce (spectral gating) in the ASR service.",
    pt: "noisereduce (filtragem espectral) no serviço de ASR.",
  },
  enhance: {
    de: "ffmpeg-Filterkette — Leicht: Bandpass (80 Hz–4 kHz); Mittel: + adaptives Entrauschen (afftdn) + Lautstärke-Normalisierung; Stark: zusätzlich Kompressor (compand).",
    en: "ffmpeg filter chain — Light: bandpass (80 Hz–4 kHz); Medium: + adaptive denoising (afftdn) + loudness normalization; Strong: plus compressor (compand).",
    pt: "Cadeia de filtros ffmpeg — Leve: passa-banda (80 Hz–4 kHz); Média: + redução adaptativa (afftdn) + normalização de volume; Forte: mais compressor (compand).",
  },
  separate: {
    de: "Methode A: htdemucs · Methode B: mel-band-roformer (Frequenzbänder).",
    en: "Method A: htdemucs · Method B: mel-band-roformer (frequency bands).",
    pt: "Método A: htdemucs · Método B: mel-band-roformer (bandas de frequência).",
  },
  model: {
    de: "Standard = Parakeet TDT 0.6B (ONNX); Alternativen je Server-Konfiguration (z. B. C++, Moonshine-deutsch, Whisper).",
    en: "Default = Parakeet TDT 0.6B (ONNX); alternatives depend on server configuration (e.g. C++, Moonshine-German, Whisper).",
    pt: "Padrão = Parakeet TDT 0.6B (ONNX); alternativas conforme a configuração do servidor (ex.: C++, Moonshine-alemão, Whisper).",
  },
  live: {
    de: "Streaming-Modus des ASR-Backends (Backend-abhängig).",
    en: "Streaming mode of the ASR backend (backend-dependent).",
    pt: "Modo de streaming do backend de ASR (depende do backend).",
  },
  diarize: {
    de: "Speaker Diarization im Diarisierungs-Dienst (Verfahren siehe unten).",
    en: "Speaker diarization in the diarization service (method below).",
    pt: "Diarização de falantes no serviço de diarização (método abaixo).",
  },
  num: {
    de: "steuert die erwartete Sprecherzahl der Diarisierung.",
    en: "controls the expected speaker count for diarization.",
    pt: "controla a quantidade esperada de falantes na diarização.",
  },
  sens: {
    de: "min_duration_off der Diarisierung (Weniger = 0,4 s, Mehr = 0,05 s).",
    en: "min_duration_off of diarization (Less = 0.4 s, More = 0.05 s).",
    pt: "min_duration_off da diarização (Menos = 0,4 s, Mais = 0,05 s).",
  },
  method: {
    de: "Methode A = pyannote (neuronales Netz, sehr genau); Methode B = foxnose (KI, sehr gut bei Sprecherwechseln, Standard); Methode C = Energie (Lautstärke-Vergleich, schnell, bei ähnlichen Stimmen ungenauer).",
    en: "Method A = pyannote (neural network, very accurate); Method B = foxnose (AI, excellent at speaker turns, default); Method C = energy (loudness comparison, fast, less accurate with similar voices).",
    pt: "Método A = pyannote (rede neural, muito preciso); Método B = foxnose (IA, ótima em trocas de falante, padrão); Método C = energia (comparação de volume, rápido, menos preciso com vozes parecidas).",
  },
  punct: {
    de: "LLM über den konfigurierten KI-Server (LiteLLM) — Anweisung: Satzzeichen setzen, keine Wörter ändern.",
    en: "LLM via the configured AI server (LiteLLM) — instruction: add punctuation, do not change words.",
    pt: "LLM via o servidor de IA configurado (LiteLLM) — instrução: adicionar pontuação, não alterar palavras.",
  },
  llmfix: {
    de: "LLM über den konfigurierten KI-Server (LiteLLM); Standard-Modell: DeepSeek Chat. Anweisung: nur Fehler korrigieren.",
    en: "LLM via the configured AI server (LiteLLM); default model: DeepSeek Chat. Instruction: correct errors only.",
    pt: "LLM via o servidor de IA configurado (LiteLLM); modelo padrão: DeepSeek Chat. Instrução: apenas corrigir erros.",
  },
  template: {
    de: "steuert den Prompt der LLM-Nachbearbeitung (Vorlagen aus den Einstellungen).",
    en: "controls the prompt of the LLM post-processing (templates from settings).",
    pt: "controla o prompt do pós-processamento por LLM (modelos das configurações).",
  },
  endpoint: {
    de: "OpenAI-kompatibler Endpunkt; Standard = LiteLLM-Proxy, eigener Anbieter = BYOK-Endpunkt.",
    en: "OpenAI-compatible endpoint; default = LiteLLM proxy, own provider = BYOK endpoint.",
    pt: "Endpoint compatível com OpenAI; padrão = proxy LiteLLM, provedor próprio = endpoint BYOK.",
  },
  target: {
    de: "Delivery-Dienst der Plattform (SMTP/WebDAV).",
    en: "Platform delivery service (SMTP/WebDAV).",
    pt: "Serviço de entrega da plataforma (SMTP/WebDAV).",
  },
};

function HelpTip({ row }: { row: OptionRow }) {
  const { lang } = useT();
  const wrapRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  useDismiss(wrapRef, open, () => setOpen(false));
  const flip = useFlipUp(open);
  const technique = TECHNIQUE[row.id];
  const modelLine = technique ? `${pick(technique, lang)}` : "";
  return (
    <div ref={wrapRef} className="relative inline-flex">
      <button
        type="button"
        aria-label="?"
        onClick={(e) => {
          e.stopPropagation();
          setOpen((o) => !o);
        }}
        className="w-[17px] h-[17px] rounded-full border border-border2 bg-panel text-muted text-[10px] font-bold leading-none cursor-pointer flex items-center justify-center transition-colors hover:border-accent hover:text-accent"
      >
        ?
      </button>
      {open && (
        <div
          ref={flip.ref}
          style={{ transform: flip.dx ? `translateX(${flip.dx}px)` : undefined }}
          className={`dl-menu-enter absolute ${flip.up ? "bottom-[calc(100%+6px)]" : "top-[calc(100%+6px)]"} right-0 z-[110] w-[300px] max-w-[calc(100vw-16px)] bg-panel3 border border-border2 rounded-sm px-3 py-2 shadow-[0_8px_24px_rgba(0,0,0,.4)] text-[11px] leading-[1.5] text-txt`}
        >
          <p>{pick(row.note, lang)}</p>
          {modelLine && (
            <p className="mt-1.5 pt-1.5 border-t border-dashed border-border2 text-muted text-[10px]">
              <span className="font-semibold text-accent">Modell/Technik:</span> {modelLine}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

/**
 * Eine Optionszeile. Nicht angebotene Optionen erscheinen — wenn sie dem
 * Verständnis helfen — mit Klartext-Begründung, aber OHNE Bedienelement
 * (kein Knopf ohne Funktion, keine stillen Fehler).
 */
function Row({ row, availability, control }: {
  row: OptionRow;
  availability: OptionAvailability;
  control: ReactNode;
}) {
  const { lang } = useT();
  // Option wirkt in dieser Quelle grundsätzlich nicht → ausgeblendet
  // (keine Zeile ohne Wirkung, kein Knopf ohne Funktion).
  if (availability.state === "hidden") return null;
  const label = pick(row.label, lang);
  const blocked = availability.state === "blocked";
  const reason = blocked ? pick(availability.reason, lang) : "";

  return (
    <>
      {/* Change 118: nicht angebotene Optionen sind schwächer ausgegraut
          (opacity-25) und tragen KEIN Bedienelement. */}
      <div
        className={`flex items-start gap-2 min-h-[28px] py-[3px] ${blocked ? "opacity-25" : ""}`}
        data-opt={row.id}
        data-opt-state={availability.state}
      >
        <div className="flex-1 min-w-0">
          <span className="text-[12px] font-semibold">{label}</span>
        </div>
        {availability.state === "available" && <span>{control}</span>}
        <HelpTip row={row} />
      </div>
      {/* Die Begründung steht NEBEN der ausgegrauten Zeile (nicht darin) —
          bei 25 % Deckkraft wäre der Klartext nicht mehr lesbar, und eine
          unhörbare Begründung wäre ein stiller Fehler. */}
      {reason && (
        <div className="text-[10.5px] leading-[1.35] text-muted2 -mt-[2px] mb-[3px]">
          {reason}
        </div>
      )}
    </>
  );
}

function Toggle({ on, onChange }: { on: boolean; onChange: (v: boolean) => void }) {
  return (
    <input
      type="checkbox"
      checked={on}
      onChange={(e) => onChange(e.target.checked)}
      className="accent-[#2ea043] w-[14px] h-[14px] cursor-pointer"
    />
  );
}

function Sel({ value, onChange, options }: {
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="bg-panel2 border border-border2 rounded-sm text-[11px] px-1.5 py-[3px] text-txt cursor-pointer max-w-[185px]"
    >
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  );
}

interface Props {
  /** Quelle des Auftrags — steuert (über die Matrix) die Verfügbarkeit. */
  source: OptionSource;
  values: FeatureValues;
  /** Wählbare Backends (aus /api/models/matrix, nach Zugriff gefiltert). */
  backends: string[];
  /** Backend-Fähigkeiten aus /api/backends (streaming_by_backend,
   *  native_punctuation). Nichts davon wird im Frontend angenommen. */
  caps?: BackendCapabilities | null;
  flags?: { vad?: boolean; diarize?: boolean };
  pp?: PostProcessOptions;
  action: ActionId;
  onChange: (patch: Partial<FeatureValues>) => void;
}

export function OptionsPanel({
  source,
  values,
  backends,
  caps = null,
  flags,
  pp,
  action,
  onChange,
}: Props) {
  const { lang } = useT();
  const [tab, setTab] = useState<OptionCategory>("pre");
  const oidc = pp?.isOidc ?? false;
  const templates = pp?.templates ?? [];
  const targets = pp?.targets ?? [];
  const endpoints = pp?.endpoints ?? [];

  const ctx = {
    source,
    action,
    backends,
    backend: values.backend,
    caps,
    services: { vad: flags?.vad ?? true, diarize: flags?.diarize ?? true, oidc },
    values: { diarize: values.diarize },
  };

  // Verfügbarkeit kommt ausschließlich aus der Matrix (siehe optionMatrix.ts).
  const rows: Record<OptionCategory, { row: OptionRow; av: OptionAvailability }[]> = {
    pre: rowsOf("pre").map((row) => ({ row, av: optionAvailability(row, ctx) })),
    spk: rowsOf("spk").map((row) => ({ row, av: optionAvailability(row, ctx) })),
    post: rowsOf("post").map((row) => ({ row, av: optionAvailability(row, ctx) })),
  };
  // Eine Gruppe gilt als nicht verfügbar, wenn in ihr KEINE Option wirkt.
  const tabDis = (id: OptionCategory): boolean =>
    rows[id].every((r) => r.av.state !== "available");

  const tabs: { id: OptionCategory; label: string }[] = [
    { id: "pre", label: L(TXT.tab_pre, lang) },
    { id: "spk", label: L(TXT.tab_spk, lang) },
    { id: "post", label: L(TXT.tab_post, lang) },
  ];

  // Change 118: Wird die aktive Gruppe durch einen Wechsel nicht mehr
  // verfügbar, springt das Panel zur ersten verfügbaren Gruppe.
  useEffect(() => {
    if (!tabDis(tab)) return;
    const alt = tabs.find((t) => !tabDis(t.id));
    if (alt) setTab(alt.id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [action, oidc, flags?.vad, flags?.diarize, backends.length, caps, values.backend, source]);

  const control = (id: string, av: OptionAvailability): ReactNode => {
    if (av.state !== "available") return null;
    switch (id) {
      case "vad":
        return (
          <Sel
            value={values.vad}
            onChange={(v) => onChange({ vad: v })}
            options={[
              { value: "off", label: L(TXT.vad_off, lang) },
              { value: "edges", label: L(TXT.vad_edges, lang) },
              { value: "all", label: L(TXT.vad_all, lang) },
            ]}
          />
        );
      case "noise":
        return <Toggle on={values.noise} onChange={(v) => onChange({ noise: v })} />;
      case "enhance":
        return (
          <Sel
            value={values.enhance}
            onChange={(v) => onChange({ enhance: v })}
            // Genau die Stufen, die der Dienst kennt (kein erfundener Wert).
            options={ENHANCE_LEVELS.map((l) => ({ value: l.value, label: L(l.label, lang) }))}
          />
        );
      case "separate":
        return (
          <Sel
            value={values.separate}
            onChange={(v) => onChange({ separate: v })}
            options={[
              { value: "none", label: L(TXT.vad_off, lang) },
              { value: "htdemucs", label: L(TXT.m_a, lang) },
              { value: "mel-band-roformer", label: L(TXT.m_b, lang) },
            ]}
          />
        );
      case "model":
        return (
          <Sel
            value={values.backend}
            onChange={(v) => {
              const patch: Partial<FeatureValues> = { backend: v };
              // Backend ohne Live-Erkennung → Live-Wert zurücksetzen, damit im
              // Lauf kein stiller No-Op hängen bleibt. Fakt aus /api/backends.
              if (caps?.streaming_by_backend?.[v] === false) patch.streaming = false;
              onChange(patch);
            }}
            options={[
              { value: "", label: L(TXT.model_std, lang) },
              ...backends.map((b) => ({ value: b, label: b })),
            ]}
          />
        );
      case "live":
        return <Toggle on={values.streaming} onChange={(v) => onChange({ streaming: v })} />;
      case "diarize":
        return <Toggle on={values.diarize} onChange={(v) => onChange({ diarize: v })} />;
      case "num":
        return (
          <Sel
            value={values.numSpeakers}
            onChange={(v) => onChange({ numSpeakers: v })}
            options={[
              { value: "", label: L(TXT.num_auto, lang) },
              { value: "1", label: "1" },
              { value: "2", label: "2" },
              { value: "3", label: "3" },
              { value: "4", label: "4+" },
            ]}
          />
        );
      case "sens":
        return (
          <Sel
            value={values.diarSens}
            onChange={(v) => onChange({ diarSens: v })}
            options={[
              { value: "less", label: L(TXT.sens_less, lang) },
              { value: "std", label: L(TXT.sens_std, lang) },
              { value: "more", label: L(TXT.sens_more, lang) },
            ]}
          />
        );
      case "method":
        return (
          <Sel
            value={values.diarMethod}
            onChange={(v) => onChange({ diarMethod: v })}
            options={[
              { value: "", label: L(TXT.met_auto, lang) },
              { value: "pyannote", label: L(TXT.met_a, lang) },
              { value: "foxnose", label: L(TXT.met_b, lang) },
              { value: "energy", label: L(TXT.met_c, lang) },
            ]}
          />
        );
      case "punct":
        return <Toggle on={values.punctuation} onChange={(v) => onChange({ punctuation: v })} />;
      case "llmfix":
        return <Toggle on={values.llmEnhance} onChange={(v) => onChange({ llmEnhance: v })} />;
      case "template":
        return (
          <Sel
            value={values.templateId === undefined ? "" : String(values.templateId)}
            onChange={(v) => onChange({ templateId: v ? Number(v) : undefined })}
            options={[
              { value: "", label: L(TXT.none, lang) },
              ...templates.map((tp) => ({ value: String(tp.template_id), label: tp.name })),
            ]}
          />
        );
      case "endpoint":
        return (
          <Sel
            value={values.endpointId === undefined ? "" : String(values.endpointId)}
            onChange={(v) => onChange({ endpointId: v ? Number(v) : undefined })}
            options={[
              { value: "", label: L(TXT.ep_std, lang) },
              ...endpoints.map((ep) => ({ value: String(ep.endpoint_id), label: ep.name })),
            ]}
          />
        );
      case "target":
        return (
          <Sel
            value={values.targetId === undefined ? "" : String(values.targetId)}
            onChange={(v) => onChange({ targetId: v ? Number(v) : undefined })}
            options={[
              { value: "", label: L(TXT.none, lang) },
              ...targets.map((tg) => ({ value: String(tg.target_id), label: tg.name })),
            ]}
          />
        );
      default:
        return null;
    }
  };

  return (
    <div className="border border-border rounded-sm bg-panel2/60 p-2" data-panel-source={source}>
      {/* Options-Gruppen */}
      <div className="flex gap-[2px] border-b border-border mb-2">
        {tabs.map((tb) => (
          <button
            key={tb.id}
            type="button"
            data-testid={`opt-tab-${tb.id}`}
            disabled={tabDis(tb.id)}
            onClick={() => setTab(tb.id)}
            title={tabDis(tb.id) ? L(TXT.opt_cat_hint, lang) : undefined}
            className={`flex-1 text-center text-[11.5px] font-semibold py-[6px] cursor-pointer border-b-2 -mb-px transition-colors ${
              tabDis(tb.id)
                ? "text-muted2 opacity-30 cursor-not-allowed border-b-transparent"
                : tab === tb.id
                  ? "text-accent border-b-accent"
                  : "text-muted border-b-transparent hover:text-txt"
            }`}
          >
            {tb.label}
          </button>
        ))}
      </div>

      <div className="flex flex-col">
        {rows[tab].map(({ row, av }) => (
          <Row key={row.id} row={row} availability={av} control={control(row.id, av)} />
        ))}
      </div>

      {/* Backend-Fähigkeiten nicht abrufbar (z. B. Fehler der API) → einmal
          sagen, statt pro Zeile zu wiederholen (keine stillen Fehler). */}
      {caps === null && (
        <p className="text-[10px] text-muted2 mt-1">{L(REASON.caps_missing, lang)}</p>
      )}
    </div>
  );
}
