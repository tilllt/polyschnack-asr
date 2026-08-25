import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { useT } from "../useLocale";
import { useDismiss } from "../useDismiss";
import { useFlipUp } from "../useFlipUp";
import type { FeatureValues, PostProcessOptions } from "./FeatureToggles";

/* ============================================================
   OptionsPanel — Change 116 (App-Redesign v7)
   Ausklappbares Options-Panel mit 3 Tabs (Vorbereitung ·
   Sprechererkennung · Nachbearbeitung), „?"-Hilfen je Option
   (inkl. Modell/Technik) und Ausgrauen nicht verfügbarer
   Optionen je gewählter Aktion (Transkribieren / Sprecher
   suchen / Neue Wortzeiten).
   ============================================================ */

export type ActionId = "tr" | "spk" | "alg";

type S = { de: string; en: string; pt: string };
const L = (d: S, lang: string): string => d[lang as keyof S] ?? d.de;

/** Sichtbare Labels (de/en/pt) — keine Fachbegriffe als UI-Label. */
const TXT: Record<string, S> = {
  tab_pre: { de: "Vorbereitung", en: "Preparation", pt: "Preparação" },
  tab_spk: { de: "Sprechererkennung", en: "Speakers", pt: "Falantes" },
  tab_post: { de: "Nachbearbeitung", en: "Post-processing", pt: "Pós-processamento" },
  opt_vad: { de: "Stille entfernen", en: "Remove silence", pt: "Remover silêncio" },
  vad_off: { de: "Aus", en: "Off", pt: "Desligado" },
  vad_edges: { de: "Ränder", en: "Edges", pt: "Bordas" },
  vad_all: { de: "Überall", en: "Everywhere", pt: "Em todo lugar" },
  opt_noise: { de: "Rauschfilter", en: "Noise filter", pt: "Filtro de ruído" },
  opt_enhance: { de: "Klang verbessern", en: "Improve sound", pt: "Melhorar som" },
  enh_light: { de: "Leicht", en: "Light", pt: "Leve" },
  enh_strong: { de: "Stark", en: "Strong", pt: "Forte" },
  opt_music: { de: "Musik entfernen", en: "Remove music", pt: "Remover música" },
  m_a: { de: "Methode A (htdemucs)", en: "Method A (htdemucs)", pt: "Método A (htdemucs)" },
  m_b: { de: "Methode B (mel-band)", en: "Method B (mel-band)", pt: "Método B (mel-band)" },
  opt_model: { de: "Sprachmodell", en: "Speech model", pt: "Modelo de fala" },
  model_std: { de: "Standard (Server)", en: "Default (server)", pt: "Padrão (servidor)" },
  opt_live: { de: "Live-Erkennung", en: "Live recognition", pt: "Reconhecimento ao vivo" },
  opt_spk_on: { de: "Sprecher erkennen", en: "Detect speakers", pt: "Detectar falantes" },
  opt_num: { de: "Anzahl", en: "Number", pt: "Quantidade" },
  num_auto: { de: "Automatisch", en: "Automatic", pt: "Automático" },
  opt_sens: { de: "Empfindlichkeit", en: "Sensitivity", pt: "Sensibilidade" },
  sens_less: { de: "Weniger", en: "Less", pt: "Menos" },
  sens_std: { de: "Standard", en: "Standard", pt: "Padrão" },
  sens_more: { de: "Mehr", en: "More", pt: "Mais" },
  opt_method: { de: "Verfahren", en: "Method", pt: "Método" },
  met_auto: { de: "Automatisch (Server)", en: "Automatic (server)", pt: "Automático (servidor)" },
  met_a: { de: "Methode A (pyannote)", en: "Method A (pyannote)", pt: "Método A (pyannote)" },
  met_b: { de: "Methode B (foxnose)", en: "Method B (foxnose)", pt: "Método B (foxnose)" },
  met_c: { de: "Methode C (Energie)", en: "Method C (energy)", pt: "Método C (energia)" },
  opt_punct: { de: "Zeichensetzung", en: "Punctuation", pt: "Pontuação" },
  opt_llmfix: { de: "ASR-Fehler korrigieren", en: "Fix ASR errors", pt: "Corrigir erros de ASR" },
  opt_template: { de: "Vorlage", en: "Template", pt: "Modelo de prompt" },
  opt_endpoint: { de: "KI-Server", en: "AI server", pt: "Servidor de IA" },
  ep_std: { de: "Standard (Server)", en: "Default (server)", pt: "Padrão (servidor)" },
  opt_target: { de: "Senden an", en: "Send to", pt: "Enviar para" },
  none: { de: "—", en: "—", pt: "—" },
  post_anon_hint: {
    de: "Nachbearbeitung ist nur für angemeldete Nutzer verfügbar.",
    en: "Post-processing is only available for signed-in users.",
    pt: "O pós-processamento está disponível apenas para usuários conectados.",
  },
  opt_cat_hint: {
    de: "Für diese Aktion nicht verfügbar.",
    en: "Not available for this action.",
    pt: "Não disponível para esta ação.",
  },
};

/** „?"-Hilfen: Erklärung ohne Fachbegriffe + Modell/Technik-Zeile. */
const HELP: Record<string, { t: S; m: S }> = {
  vad: {
    t: {
      de: "Erkennt leise Passagen und entfernt sie, bevor der Text erkannt wird. Aus: unverändert. Ränder: nur Stille am Anfang/Ende wird gekürzt. Überall: auch Pausen mitten in der Aufnahme fallen weg — bei Denkpausen können kurze Wörter verschluckt werden.",
      en: "Detects quiet passages and removes them before recognition. Off: unchanged. Edges: only silence at the start/end is trimmed. Everywhere: pauses in the middle are removed too — short words may get lost during thinking pauses.",
      pt: "Detecta passagens silenciosas e as remove antes do reconhecimento. Desligado: inalterado. Bordas: apenas silêncio no início/fim é cortado. Em todo lugar: pausas no meio também são removidas — palavras curtas podem se perder em pausas de pensamento.",
    },
    m: {
      de: "Silero VAD (silero_vad.onnx, MIT) — läuft im Server per ONNX Runtime.",
      en: "Silero VAD (silero_vad.onnx, MIT) — runs on the server via ONNX Runtime.",
      pt: "Silero VAD (silero_vad.onnx, MIT) — roda no servidor via ONNX Runtime.",
    },
  },
  noise: {
    t: {
      de: "Entfernt konstante Hintergrundgeräusche: Rauschen, Brummen, Lüfter, Straßenlärm. Gefiltert wird nur die Kopie für die Erkennung — die Originaldatei bleibt unverändert.",
      en: "Removes constant background noise: hiss, hum, fans, traffic. Only the copy used for recognition is filtered — the original file stays untouched.",
      pt: "Remove ruído de fundo constante: chiado, zumbido, ventiladores, trânsito. Apenas a cópia usada no reconhecimento é filtrada — o arquivo original permanece inalterado.",
    },
    m: {
      de: "noisereduce (spektrales Gating) im ASR-Dienst.",
      en: "noisereduce (spectral gating) in the ASR service.",
      pt: "noisereduce (filtragem espectral) no serviço de ASR.",
    },
  },
  enhance: {
    t: {
      de: "Hebt die Stimme hervor und gleicht dumpfe oder zu leise Aufnahmen aus. Leicht: dezente Anhebung. Stark: deutliche Bearbeitung — bei guter Qualität kann die Stimme „blechern“ klingen.",
      en: "Emphasizes the voice and compensates muffled or too-quiet recordings. Light: subtle lift. Strong: heavy processing — on good recordings the voice may sound metallic.",
      pt: "Destaca a voz e compensa gravações abafadas ou baixas. Leve: elevação sutil. Forte: processamento intenso — em gravações boas a voz pode soar metálica.",
    },
    m: {
      de: "ffmpeg-Filterkette — Leicht: Bandpass (80 Hz–4 kHz); Stark: Bandpass + adaptives Entrauschen (afftdn) + Lautstärke-Normalisierung.",
      en: "ffmpeg filter chain — Light: bandpass (80 Hz–4 kHz); Strong: bandpass + adaptive denoising (afftdn) + loudness normalization.",
      pt: "Cadeia de filtros ffmpeg — Leve: passa-banda (80 Hz–4 kHz); Forte: passa-banda + redução adaptativa (afftdn) + normalização de volume.",
    },
  },
  separate: {
    t: {
      de: "Trennt Musik und Gesang von der Sprache — für Vorträge, Podcasts, Videos mit Hintergrundmusik. Wichtig für Wortzeiten: Die Zeitmarken verankern dann auf der Stimme statt auf der Musik.",
      en: "Separates music and vocals from speech — for talks, podcasts, videos with background music. Important for word timestamps: they anchor on the voice instead of the music.",
      pt: "Separa música e voz da fala — para palestras, podcasts, vídeos com música de fundo. Importante para as marcações de tempo: elas se ancoram na voz em vez da música.",
    },
    m: {
      de: "Methode A: htdemucs · Methode B: mel-band-roformer (Frequenzbänder).",
      en: "Method A: htdemucs · Method B: mel-band-roformer (frequency bands).",
      pt: "Método A: htdemucs · Método B: mel-band-roformer (bandas de frequência).",
    },
  },
  model: {
    t: {
      de: "Welches Erkennungsmodell den Text erzeugt. Standard ist für die meisten Fälle optimal — nur ändern, wenn ihr wisst, was ihr tut.",
      en: "Which recognition model produces the text. The default is best for most cases — only change it if you know what you are doing.",
      pt: "Qual modelo de reconhecimento gera o texto. O padrão é o ideal na maioria dos casos — altere apenas se souber o que está fazendo.",
    },
    m: {
      de: "Standard = Parakeet TDT 0.6B (ONNX); Alternativen je Server-Konfiguration (z. B. C++, Moonshine-deutsch, Whisper).",
      en: "Default = Parakeet TDT 0.6B (ONNX); alternatives depend on server configuration (e.g. C++, Moonshine-German, Whisper).",
      pt: "Padrão = Parakeet TDT 0.6B (ONNX); alternativas conforme a configuração do servidor (ex.: C++, Moonshine-alemão, Whisper).",
    },
  },
  live: {
    t: {
      de: "Erkennt den Text während der Aufnahme, nicht erst danach. Nur bei Backends verfügbar, die Live-Erkennung unterstützen.",
      en: "Recognizes text while recording, not only afterwards. Only available for backends that support live recognition.",
      pt: "Reconhece o texto durante a gravação, não apenas depois. Disponível apenas para backends com reconhecimento ao vivo.",
    },
    m: {
      de: "Streaming-Modus des ASR-Backends (Backend-abhängig).",
      en: "Streaming mode of the ASR backend (backend-dependent).",
      pt: "Modo de streaming do backend de ASR (depende do backend).",
    },
  },
  diarize: {
    t: {
      de: "Markiert im Text, wer gerade spricht (Sprecher 1, Sprecher 2, …). Die Aktion „Sprecher suchen“ berechnet nur diese Zuordnung neu — Text und Zeitmarken bleiben unverändert.",
      en: "Marks who is speaking in the text (Speaker 1, Speaker 2, …). The “Detect speakers” action only recomputes this mapping — text and timestamps stay unchanged.",
      pt: "Marca quem está falando no texto (Falante 1, Falante 2, …). A ação “Detectar falantes” recalcula apenas essa atribuição — texto e marcações permanecem inalterados.",
    },
    m: {
      de: "Speaker Diarization im Diarisierungs-Dienst (Verfahren siehe unten).",
      en: "Speaker diarization in the diarization service (method below).",
      pt: "Diarização de falantes no serviço de diarização (método abaixo).",
    },
  },
  num: {
    t: {
      de: "Wie viele Personen voraussichtlich sprechen. Automatisch lässt das System die Zahl selbst ermitteln.",
      en: "How many people are expected to speak. Automatic lets the system figure it out.",
      pt: "Quantas pessoas devem falar. Automático permite que o sistema descubra.",
    },
    m: {
      de: "steuert die erwartete Sprecherzahl der Diarisierung.",
      en: "controls the expected speaker count for diarization.",
      pt: "controla a quantidade esperada de falantes na diarização.",
    },
  },
  sens: {
    t: {
      de: "Wie schnell das System einen Sprecherwechsel erkennt. Weniger: wechselt nur bei deutlichen Pausen. Mehr: erkennt auch schnelle Wortwechsel — kann einzelne Wörter dem falschen Sprecher zuordnen.",
      en: "How quickly the system detects speaker changes. Less: only switches on clear pauses. More: also catches quick exchanges — may assign single words to the wrong speaker.",
      pt: "Quão rápido o sistema detecta mudanças de falante. Menos: muda apenas em pausas claras. Mais: captura trocas rápidas — pode atribuir palavras ao falante errado.",
    },
    m: {
      de: "min_duration_off der Diarisierung (Weniger = 0,4 s, Mehr = 0,05 s).",
      en: "min_duration_off of diarization (Less = 0.4 s, More = 0.05 s).",
      pt: "min_duration_off da diarização (Menos = 0,4 s, Mais = 0,05 s).",
    },
  },
  method: {
    t: {
      de: "Das Rechenverfahren hinter der Sprechererkennung. Automatisch: das System wählt passend zur Aufnahme.",
      en: "The computation behind speaker detection. Automatic: the system picks what fits the recording.",
      pt: "O método de cálculo por trás da detecção de falantes. Automático: o sistema escolhe conforme a gravação.",
    },
    m: {
      de: "Methode A = pyannote (neuronales Netz, sehr genau); Methode B = foxnose (KI, sehr gut bei Sprecherwechseln, Standard); Methode C = Energie (Lautstärke-Vergleich, schnell, bei ähnlichen Stimmen ungenauer).",
      en: "Method A = pyannote (neural network, very accurate); Method B = foxnose (AI, excellent at speaker turns, default); Method C = energy (loudness comparison, fast, less accurate with similar voices).",
      pt: "Método A = pyannote (rede neural, muito preciso); Método B = foxnose (IA, ótima em trocas de falante, padrão); Método C = energia (comparação de volume, rápido, menos preciso com vozes parecidas).",
    },
  },
  punct: {
    t: {
      de: "Setzt automatisch Punkte, Kommas und Fragezeichen. Die reine Spracherkennung liefert nur Wörter ohne Satzzeichen — diese Option macht den Text lesbar. Der exakte Text bleibt erhalten.",
      en: "Adds periods, commas and question marks automatically. Raw recognition only outputs words without punctuation — this option makes the text readable. The exact text stays unchanged.",
      pt: "Adiciona pontos, vírgulas e interrogações automaticamente. O reconhecimento puro entrega apenas palavras sem pontuação — esta opção torna o texto legível. O texto exato permanece.",
    },
    m: {
      de: "LLM über den konfigurierten KI-Server (LiteLLM) — Anweisung: Satzzeichen setzen, keine Wörter ändern.",
      en: "LLM via the configured AI server (LiteLLM) — instruction: add punctuation, do not change words.",
      pt: "LLM via o servidor de IA configurado (LiteLLM) — instrução: adicionar pontuação, não alterar palavras.",
    },
  },
  llmfix: {
    t: {
      de: "Behebt Erkennungsfehler: falsche Wörter, Namen, Zahlen. Der exakte Text bleibt erhalten — es wird nur korrigiert, nichts umformuliert, gekürzt oder ergänzt. Für wörtliche Zitate und Protokolle gedacht.",
      en: "Fixes recognition errors: wrong words, names, numbers. The exact text stays unchanged — only corrections, nothing reformulated, cut or added. Meant for verbatim quotes and minutes.",
      pt: "Corrige erros de reconhecimento: palavras, nomes, números errados. O texto exato permanece — apenas correções, nada reformulado, cortado ou acrescentado. Para citações literais e atas.",
    },
    m: {
      de: "LLM über den konfigurierten KI-Server (LiteLLM); Standard-Modell: DeepSeek Chat. Anweisung: nur Fehler korrigieren.",
      en: "LLM via the configured AI server (LiteLLM); default model: DeepSeek Chat. Instruction: correct errors only.",
      pt: "LLM via o servidor de IA configurado (LiteLLM); modelo padrão: DeepSeek Chat. Instrução: apenas corrigir erros.",
    },
  },
  template: {
    t: {
      de: "Bestimmt, wie die KI nachbearbeitet — z. B. „Protokoll-Stil“ oder „Kurzfassung“. Ohne Vorlage verwendet die KI ihren Standardstil.",
      en: "Determines how the AI post-processes — e.g. “minutes style” or “summary”. Without a template the AI uses its default style.",
      pt: "Define como a IA pós-processa — ex.: “estilo ata” ou “resumo”. Sem modelo, a IA usa o estilo padrão.",
    },
    m: {
      de: "steuert den Prompt der LLM-Nachbearbeitung (Vorlagen aus den Einstellungen).",
      en: "controls the prompt of the LLM post-processing (templates from settings).",
      pt: "controla o prompt do pós-processamento por LLM (modelos das configurações).",
    },
  },
  endpoint: {
    t: {
      de: "Welcher KI-Dienst die Nachbearbeitung ausführt. Standard: der Dienst der Plattform. Eigener Anbieter: selbst hinterlegter Endpunkt — die Transkripte verlassen dann euren eigenen Server.",
      en: "Which AI service runs the post-processing. Default: the platform's service. Own provider: a custom endpoint — transcripts then leave your own server.",
      pt: "Qual serviço de IA executa o pós-processamento. Padrão: o serviço da plataforma. Próprio provedor: um endpoint personalizado — os transcrições saem então do seu servidor.",
    },
    m: {
      de: "OpenAI-kompatibler Endpunkt; Standard = LiteLLM-Proxy, eigener Anbieter = BYOK-Endpunkt.",
      en: "OpenAI-compatible endpoint; default = LiteLLM proxy, own provider = BYOK endpoint.",
      pt: "Endpoint compatível com OpenAI; padrão = proxy LiteLLM, provedor próprio = endpoint BYOK.",
    },
  },
  target: {
    t: {
      de: "Ziel, an das der fertige Text zusätzlich geschickt wird (E-Mail oder WebDAV-Ordner).",
      en: "Destination that additionally receives the finished text (email or WebDAV folder).",
      pt: "Destino que também recebe o texto final (e-mail ou pasta WebDAV).",
    },
    m: {
      de: "Delivery-Dienst der Plattform (SMTP/WebDAV).",
      en: "Platform delivery service (SMTP/WebDAV).",
      pt: "Serviço de entrega da plataforma (SMTP/WebDAV).",
    },
  },
};

function HelpTip({ id }: { id: string }) {
  const { lang } = useT();
  const wrapRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  useDismiss(wrapRef, open, () => setOpen(false));
  const flip = useFlipUp(open);
  const h = HELP[id];
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
          <p>{L(h.t, lang)}</p>
          <p className="mt-1.5 pt-1.5 border-t border-dashed border-border2 text-muted text-[10px]">
            <span className="font-semibold text-accent">Modell/Technik:</span> {L(h.m, lang)}
          </p>
        </div>
      )}
    </div>
  );
}

function Row({ id, label, help, dis, control }: {
  id: string; label: string; help: string; dis: boolean; control: ReactNode;
}) {
  return (
    <div
      className={`flex items-center gap-2 min-h-[28px] py-[3px] ${dis ? "opacity-25" : ""}`}
      data-opt={id}
    >
      <span className="text-[12px] font-semibold flex-1 min-w-0">{label}</span>
      <span className={dis ? "pointer-events-none" : ""}>{control}</span>
      <HelpTip id={help} />
    </div>
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

function Sel({ value, onChange, options, title }: {
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
  title?: string;
}) {
  return (
    <select
      value={value}
      title={title}
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
  values: FeatureValues;
  backends: string[];
  streamingSupported?: boolean;
  streamingByBackend?: Record<string, boolean>;
  flags?: { vad?: boolean; diarize?: boolean };
  pp?: PostProcessOptions;
  action: ActionId;
  onChange: (patch: Partial<FeatureValues>) => void;
}

export function OptionsPanel({ values, backends, streamingSupported, streamingByBackend, flags, pp, action, onChange }: Props) {
  const { lang } = useT();
  const [tab, setTab] = useState<"pre" | "spk" | "post">("pre");
  const oidc = pp?.isOidc ?? false;
  const templates = pp?.templates ?? [];
  const targets = pp?.targets ?? [];
  const endpoints = pp?.endpoints ?? [];
  const vadOk = flags?.vad ?? true;
  const diarOk = flags?.diarize ?? true;

  const rowDis = (tabId: string, rowId: string): boolean => {
    if (action === "spk") {
      if (tabId !== "spk") return true;
      if (rowId === "diarize") return true; // die Aktion selbst ist der Schalter
      return false;
    }
    if (action === "alg") {
      return !(tabId === "pre" && rowId === "separate");
    }
    if (tabId === "post" && !oidc) return true;
    return false;
  };

  // Change 118: Kategorie-Tab disabled, wenn ALLE seine Optionen bei der
  // gewählten Aktion nicht verfügbar sind (rowDis + Flags/Backend-Zustand).
  const tabRows: Record<"pre" | "spk" | "post", { id: string; extra: boolean }[]> = {
    pre: [
      { id: "vad", extra: !vadOk },
      { id: "noise", extra: false },
      { id: "enhance", extra: false },
      { id: "separate", extra: false },
      { id: "model", extra: backends.length === 0 },
      // live wird nur gerendert, wenn Streaming unterstützt wird
      { id: "live", extra: streamingSupported === false },
    ],
    spk: [
      { id: "diarize", extra: !diarOk },
      { id: "num", extra: false },
      { id: "sens", extra: false },
      { id: "method", extra: false },
    ],
    post: [
      { id: "punct", extra: !oidc },
      { id: "llmfix", extra: !oidc },
      { id: "template", extra: !oidc },
      { id: "endpoint", extra: !oidc },
      { id: "target", extra: !oidc },
    ],
  };
  const tabDis = (tid: "pre" | "spk" | "post"): boolean =>
    tabRows[tid].every((r) => rowDis(tid, r.id) || r.extra);

  const tabs: { id: "pre" | "spk" | "post"; label: string }[] = [
    { id: "pre", label: L(TXT.tab_pre, lang) },
    { id: "spk", label: L(TXT.tab_spk, lang) },
    { id: "post", label: L(TXT.tab_post, lang) },
  ];

  // Change 118: Wird der aktive Tab durch einen Aktion-Wechsel nicht mehr
  // verfügbar, springt das Panel zum ersten verfügbaren Tab (z. B.
  // Nachbearbeitung → Vorbereitung bei „Neue Wortzeiten“).
  useEffect(() => {
    if (!tabDis(tab)) return;
    const alt = tabs.find((t) => !tabDis(t.id));
    if (alt) setTab(alt.id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [action, oidc, vadOk, diarOk, backends.length, streamingSupported]);

  return (
    <div className="border border-border rounded-sm bg-panel2/60 p-2">
      {/* Options-Tabs */}
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

      {tab === "pre" && (
        <div className="flex flex-col">
          <Row id="vad" label={L(TXT.opt_vad, lang)} help="vad" dis={rowDis("pre", "vad") || !vadOk}
            control={
              <Sel
                value={values.vad}
                onChange={(v) => onChange({ vad: v })}
                options={[
                  { value: "off", label: L(TXT.vad_off, lang) },
                  { value: "edges", label: L(TXT.vad_edges, lang) },
                  { value: "all", label: L(TXT.vad_all, lang) },
                ]}
              />
            }
          />
          <Row id="noise" label={L(TXT.opt_noise, lang)} help="noise" dis={rowDis("pre", "noise")}
            control={<Toggle on={values.noise} onChange={(v) => onChange({ noise: v })} />}
          />
          <Row id="enhance" label={L(TXT.opt_enhance, lang)} help="enhance" dis={rowDis("pre", "enhance")}
            control={
              <Sel
                value={values.enhance}
                onChange={(v) => onChange({ enhance: v })}
                options={[
                  { value: "off", label: L(TXT.vad_off, lang) },
                  { value: "light", label: L(TXT.enh_light, lang) },
                  { value: "strong", label: L(TXT.enh_strong, lang) },
                ]}
              />
            }
          />
          <Row id="separate" label={L(TXT.opt_music, lang)} help="separate" dis={rowDis("pre", "separate")}
            control={
              <Sel
                value={values.separate}
                onChange={(v) => onChange({ separate: v })}
                options={[
                  { value: "none", label: L(TXT.vad_off, lang) },
                  { value: "htdemucs", label: L(TXT.m_a, lang) },
                  { value: "mel-band-roformer", label: L(TXT.m_b, lang) },
                ]}
              />
            }
          />
          <Row id="model" label={L(TXT.opt_model, lang)} help="model" dis={rowDis("pre", "model") || backends.length === 0}
            control={
              <Sel
                value={values.backend}
                onChange={(v) => {
                  const b = v;
                  const patch: Partial<FeatureValues> = { backend: b };
                  if (streamingByBackend?.[b] === false) patch.streaming = false;
                  onChange(patch);
                }}
                options={[{ value: "", label: L(TXT.model_std, lang) }, ...backends.map((b) => ({ value: b, label: b }))]}
              />
            }
          />
          {streamingSupported !== false && (
            <Row id="live" label={L(TXT.opt_live, lang)} help="live" dis={rowDis("pre", "live")}
              control={<Toggle on={values.streaming} onChange={(v) => onChange({ streaming: v })} />}
            />
          )}
        </div>
      )}

      {tab === "spk" && (
        <div className="flex flex-col">
          <Row id="diarize" label={L(TXT.opt_spk_on, lang)} help="diarize" dis={rowDis("spk", "diarize") || !diarOk}
            control={<Toggle on={values.diarize} onChange={(v) => onChange({ diarize: v })} />}
          />
          <Row id="num" label={L(TXT.opt_num, lang)} help="num" dis={rowDis("spk", "num")}
            control={
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
            }
          />
          <Row id="sens" label={L(TXT.opt_sens, lang)} help="sens" dis={rowDis("spk", "sens")}
            control={
              <Sel
                value={values.diarSens}
                onChange={(v) => onChange({ diarSens: v })}
                options={[
                  { value: "less", label: L(TXT.sens_less, lang) },
                  { value: "std", label: L(TXT.sens_std, lang) },
                  { value: "more", label: L(TXT.sens_more, lang) },
                ]}
              />
            }
          />
          <Row id="method" label={L(TXT.opt_method, lang)} help="method" dis={rowDis("spk", "method")}
            control={
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
            }
          />
        </div>
      )}

      {tab === "post" && (
        <div className="flex flex-col">
          <Row id="punct" label={L(TXT.opt_punct, lang)} help="punct" dis={rowDis("post", "punct") || !oidc}
            control={<Toggle on={values.punctuation} onChange={(v) => onChange({ punctuation: v })} />}
          />
          <Row id="llmfix" label={L(TXT.opt_llmfix, lang)} help="llmfix" dis={rowDis("post", "llmfix") || !oidc}
            control={<Toggle on={values.llmEnhance} onChange={(v) => onChange({ llmEnhance: v })} />}
          />
          <Row id="template" label={L(TXT.opt_template, lang)} help="template" dis={rowDis("post", "template") || !oidc}
            control={
              <Sel
                value={values.templateId === undefined ? "" : String(values.templateId)}
                onChange={(v) => onChange({ templateId: v ? Number(v) : undefined })}
                options={[
                  { value: "", label: L(TXT.none, lang) },
                  ...templates.map((tp) => ({ value: String(tp.template_id), label: tp.name })),
                ]}
              />
            }
          />
          <Row id="endpoint" label={L(TXT.opt_endpoint, lang)} help="endpoint" dis={rowDis("post", "endpoint") || !oidc}
            control={
              <Sel
                value={values.endpointId === undefined ? "" : String(values.endpointId)}
                onChange={(v) => onChange({ endpointId: v ? Number(v) : undefined })}
                options={[
                  { value: "", label: L(TXT.ep_std, lang) },
                  ...endpoints.map((ep) => ({ value: String(ep.endpoint_id), label: ep.name })),
                ]}
              />
            }
          />
          <Row id="target" label={L(TXT.opt_target, lang)} help="target" dis={rowDis("post", "target") || !oidc}
            control={
              <Sel
                value={values.targetId === undefined ? "" : String(values.targetId)}
                onChange={(v) => onChange({ targetId: v ? Number(v) : undefined })}
                options={[
                  { value: "", label: L(TXT.none, lang) },
                  ...targets.map((tg) => ({ value: String(tg.target_id), label: tg.name })),
                ]}
              />
            }
          />
          {!oidc && (
            <p className="text-[10px] text-muted2 mt-1">{L(TXT.post_anon_hint, lang)}</p>
          )}
        </div>
      )}
    </div>
  );
}
