import type { BackendCapabilities } from "./api";

/* ============================================================
   optionMatrix.ts — Change 212
   „Ein Optionen-Panel für alle drei Quellen, Verfügbarkeit aus
   einer Matrix“

   Eine deklarative Tabelle (eine Zeile je Option) ist die einzige
   Wahrheit darüber, ob eine Option für die gewählte Quelle, die
   gewählte Aktion und das gewählte Backend überhaupt eine Wirkung
   hat. Das Panel leitet daraus ab, was es zeigt — es gibt keine
   pro Tab von Hand gepflegte Verfügbarkeitslogik mehr.

   Darstellungsregeln (eine Regel, nicht je Tab):
   - Option wirkt hier und ist gedeckt      → bedienbar.
   - Option wirkt, das Backend kann sie
     nicht, sie erklärt aber etwas Wichtiges → sichtbar mit Klartext-
     Begründung, OHNE Bedienelement (niemals ein Knopf ohne Funktion).
   - Option wirkt hier grundsätzlich nicht   → ausgeblendet.
   Fachbegriffe sind verboten: angezeigt wird der Klartext (de/en/pt).
   ============================================================ */

/** Quellen, aus denen ein Auftrag entstehen kann (plus Recording-Ansicht). */
export type OptionSource = "upload" | "record" | "url" | "recording";

/** Kategorien des Panels (dieselben drei wie bisher). */
export type OptionCategory = "pre" | "spk" | "post";

/** Aktionen der Recording-Ansicht. */
export type OptionAction = "tr" | "spk" | "alg";

/**
 * Voraussetzungen einer Option. Sie werden aus den API-Fakten geprüft, nicht
 * geraten:
 * - ``backend``     Backend-Fähigkeiten liegen vor (aus ``/api/backends``) —
 *                   gilt auch für die Backend-Wahl selbst (Liste nicht leer).
 * - ``streaming``   das gewählte Backend kann Live-Erkennung
 *                   (``streaming_by_backend``).
 * - ``diarize``     nur wirksam, wenn Sprechererkennung eingeschaltet ist.
 * - ``vad_service`` Stille-Erkennung ist auf diesem Server verfügbar
 *                   (``/api/models/status`` → ``vad_available``).
 * - ``diar_service`` Sprechererkennung ist verfügbar (``diarize_available``).
 * - ``oidc``        Nachbearbeitung nur für angemeldete Nutzer.
 */
export type OptionRequirement =
  | "backend"
  | "streaming"
  | "diarize"
  | "vad_service"
  | "diar_service"
  | "oidc";

export type OptionId =
  | "vad"
  | "noise"
  | "enhance"
  | "separate"
  | "model"
  | "live"
  | "diarize"
  | "num"
  | "sens"
  | "method"
  | "punct"
  | "llmfix"
  | "template"
  | "endpoint"
  /** Change 228: zweite LLM-Stufe „KI-Formatierung“ */
  | "format"
  | "formatPreset"
  | "formatServer"
  | "target";

/** Klartext in den drei Sprachen der Oberfläche. */
export interface OptText {
  de: string;
  en: string;
  pt: string;
}

/** Sprachwahl der Oberfläche (``pt-BR``) auf die Textschlüssel abbilden. */
export function pick(text: OptText, lang: string): string {
  if (lang === "en") return text.en;
  if (lang === "pt" || lang === "pt-BR") return text.pt;
  return text.de;
}

export interface OptionRow {
  id: OptionId;
  category: OptionCategory;
  /** Quellen, in denen die Option eine Wirkung hat. */
  sources: OptionSource[];
  /** Voraussetzungen (siehe OptionRequirement) — alle müssen erfüllt sein. */
  requires: OptionRequirement[];
  /** Aktionen, auf die die Option wirkt (Recording-Ansicht). */
  actions: OptionAction[];
  /** Wie eine nicht angebotene Option dargestellt wird. */
  whenBlocked: "hide" | "explain";
  /** Fähigkeits-Fakt, der die Option überflüssig macht (Backend kann es selbst). */
  blockedBy?: "native_punctuation";
  /** Sichtbare Beschriftung — Klartext, kein Fachbegriff. */
  label: OptText;
  /** Erklärung in Klartext (Was passiert? Wann ist sie nicht nötig?). */
  note: OptText;
}

/** Begründungen für nicht angebotene Optionen (Klartext, keine Fachbegriffe). */
export const REASON: Record<string, OptText> = {
  action: {
    de: "Für diese Aktion ohne Wirkung.",
    en: "Has no effect for this action.",
    pt: "Sem efeito para esta ação.",
  },
  caps_missing: {
    de: "Backend-Informationen sind gerade nicht abrufbar — die Option wird deshalb nicht angeboten.",
    en: "Backend information is currently unavailable — the option is therefore not offered.",
    pt: "As informações do backend estão indisponíveis no momento — a opção não é oferecida.",
  },
  no_backends: {
    de: "Der Server meldet kein wählbares Sprachmodell.",
    en: "The server reports no selectable speech model.",
    pt: "O servidor não informa nenhum modelo de fala selecionável.",
  },
  streaming: {
    de: "Das gewählte Sprachmodell kann keine Live-Erkennung — deshalb nicht angeboten.",
    en: "The selected speech model cannot do live recognition — not offered.",
    pt: "O modelo de fala escolhido não faz reconhecimento ao vivo — não oferecido.",
  },
  diarize_off: {
    de: "Nur zusammen mit der Sprechererkennung wirksam — diese erst einschalten.",
    en: "Only effective together with speaker detection — switch that on first.",
    pt: "Só tem efeito junto com a detecção de falantes — ative-a primeiro.",
  },
  diar_service: {
    de: "Sprechererkennung ist auf diesem Server nicht verfügbar.",
    en: "Speaker detection is not available on this server.",
    pt: "A detecção de falantes não está disponível neste servidor.",
  },
  vad_service: {
    de: "Stille-Erkennung ist auf diesem Server nicht verfügbar.",
    en: "Silence detection is not available on this server.",
    pt: "A detecção de silêncio não está disponível neste servidor.",
  },
  oidc: {
    de: "Nachbearbeitung ist nur für angemeldete Nutzer verfügbar.",
    en: "Post-processing is only available for signed-in users.",
    pt: "O pós-processamento está disponível apenas para usuários conectados.",
  },
  punct_native: {
    de: "Der Server setzt Satzzeichen und Groß-/Kleinschreibung automatisch — hier ist nichts einzustellen.",
    en: "The server adds punctuation and capitalization automatically — nothing to configure here.",
    pt: "O servidor adiciona pontuação e maiúsculas automaticamente — nada a configurar aqui.",
  },
};

/** Klang-Verbesserung: genau die Stufen, die der Dienst kennt (service.py). */
export const ENHANCE_LEVELS: { value: string; label: OptText }[] = [
  { value: "off", label: { de: "Aus", en: "Off", pt: "Desligado" } },
  { value: "light", label: { de: "Leicht", en: "Light", pt: "Leve" } },
  { value: "medium", label: { de: "Mittel", en: "Medium", pt: "Média" } },
  { value: "aggressive", label: { de: "Stark", en: "Strong", pt: "Forte" } },
];

/** Alte Werte der Vor-Redesign-Oberfläche auf die echten Stufen abbilden. */
export function normalizeEnhance(value: string): string {
  if (value === "strong") return "aggressive"; // hieß früher „Stark“, der Dienst kennt „aggressive“
  return ENHANCE_LEVELS.some((l) => l.value === value) ? value : "off";
}

/* ============================================================
   Die Matrix
   ============================================================ */

export const OPTION_MATRIX: OptionRow[] = [
  {
    id: "vad",
    category: "pre",
    // Alle Quellen: der Wert landet im Lauf und gilt für jeden Auftrag.
    sources: ["upload", "record", "url", "recording"],
    requires: ["vad_service"],
    actions: ["tr"],
    whenBlocked: "explain",
    label: { de: "Stille entfernen", en: "Remove silence", pt: "Remover silêncio" },
    note: {
      de: "Erkennt leise Passagen und entfernt sie, bevor der Text erkannt wird. Aus: unverändert. Ränder: nur Stille am Anfang/Ende wird gekürzt. Überall: auch Pausen mitten in der Aufnahme fallen weg — bei Denkpausen können kurze Wörter verschluckt werden.",
      en: "Detects quiet passages and removes them before recognition. Off: unchanged. Edges: only silence at the start/end is trimmed. Everywhere: pauses in the middle are removed too — short words may get lost during thinking pauses.",
      pt: "Detecta passagens silenciosas e as remove antes do reconhecimento. Desligado: inalterado. Bordas: apenas silêncio no início/fim é cortado. Em todo lugar: pausas no meio também são removidas — palavras curtas podem se perder.",
    },
  },
  {
    id: "noise",
    category: "pre",
    sources: ["upload", "record", "url", "recording"],
    requires: [],
    actions: ["tr"],
    whenBlocked: "hide",
    label: { de: "Rauschfilter", en: "Noise filter", pt: "Filtro de ruído" },
    note: {
      de: "Entfernt konstante Hintergrundgeräusche: Rauschen, Brummen, Lüfter, Straßenlärm. Gefiltert wird nur die Kopie für die Erkennung — die Originaldatei bleibt unverändert.",
      en: "Removes constant background noise: hiss, hum, fans, traffic. Only the copy used for recognition is filtered — the original file stays untouched.",
      pt: "Remove ruído de fundo constante: chiado, zumbido, ventiladores, trânsito. Apenas a cópia usada no reconhecimento é filtrada — o arquivo original permanece inalterado.",
    },
  },
  {
    id: "enhance",
    category: "pre",
    sources: ["upload", "record", "url", "recording"],
    requires: [],
    actions: ["tr"],
    whenBlocked: "hide",
    label: { de: "Klang verbessern", en: "Improve sound", pt: "Melhorar som" },
    note: {
      de: "Hebt die Stimme hervor und gleicht dumpfe oder zu leise Aufnahmen aus. Leicht: dezente Anhebung. Mittel: zusätzliche Rauschminderung. Stark: deutliche Bearbeitung — bei guter Qualität kann die Stimme „blechern“ klingen.",
      en: "Emphasizes the voice and compensates muffled or too-quiet recordings. Light: subtle lift. Medium: extra noise reduction. Strong: heavy processing — on good recordings the voice may sound metallic.",
      pt: "Destaca a voz e compensa gravações abafadas ou baixas. Leve: elevação sutil. Média: redução de ruído adicional. Forte: processamento intenso — em gravações boas a voz pode soar metálica.",
    },
  },
  {
    id: "separate",
    category: "pre",
    sources: ["upload", "record", "url", "recording"],
    requires: [],
    // Musik entfernen ist die einzige Option, die auch „Neue Wortzeiten“ beeinflusst.
    actions: ["tr", "alg"],
    whenBlocked: "explain",
    label: { de: "Musik entfernen", en: "Remove music", pt: "Remover música" },
    note: {
      de: "Trennt Musik und Gesang von der Sprache — für Vorträge, Podcasts, Videos mit Hintergrundmusik. Wichtig für Wortzeiten: Die Zeitmarken verankern dann auf der Stimme statt auf der Musik.",
      en: "Separates music and vocals from speech — for talks, podcasts, videos with background music. Important for word timestamps: they anchor on the voice instead of the music.",
      pt: "Separa música e voz da fala — para palestras, podcasts, vídeos com música de fundo. Importante para as marcações de tempo: elas se ancoram na voz em vez da música.",
    },
  },
  {
    id: "model",
    category: "pre",
    sources: ["upload", "record", "url", "recording"],
    requires: ["backend"],
    actions: ["tr"],
    // Ohne wählbares Backend gäbe es nichts zu wählen → Zeile nur mit
    // Klartext-Begründung zeigen (Change 118: nicht angebotene Optionen
    // bleiben sichtbar ausgegraut, damit man die Option nicht sucht).
    whenBlocked: "explain",
    label: { de: "Sprachmodell", en: "Speech model", pt: "Modelo de fala" },
    note: {
      de: "Welches Erkennungsmodell den Text erzeugt. Standard ist für die meisten Fälle optimal — nur ändern, wenn ihr wisst, was ihr tut.",
      en: "Which recognition model produces the text. The default is best for most cases — only change it if you know what you are doing.",
      pt: "Qual modelo de reconhecimento gera o texto. O padrão é o ideal na maioria dos casos — altere apenas se souber o que está fazendo.",
    },
  },
  {
    id: "live",
    category: "pre",
    sources: ["upload", "record", "url", "recording"],
    requires: ["backend", "streaming"],
    actions: ["tr"],
    whenBlocked: "explain",
    label: { de: "Live-Erkennung", en: "Live recognition", pt: "Reconhecimento ao vivo" },
    note: {
      de: "Der Server erkennt den Text in Abschnitten und zeigt ihn während der Verarbeitung mit. Nur bei Sprachmodellen verfügbar, die das können — bei sehr langen Aufnahmen die schonende Betriebsart.",
      en: "The server recognizes the text in chunks and shows it while processing. Only available for speech models that support it — the gentle mode for very long recordings.",
      pt: "O servidor reconhece o texto em blocos e o mostra durante o processamento. Disponível apenas para modelos de fala que o suportam — o modo suave para gravações muito longas.",
    },
  },
  {
    id: "diarize",
    category: "spk",
    sources: ["upload", "record", "url", "recording"],
    requires: ["diar_service"],
    actions: ["tr"],
    whenBlocked: "explain",
    label: { de: "Sprecher erkennen", en: "Detect speakers", pt: "Detectar falantes" },
    note: {
      de: "Markiert im Text, wer gerade spricht (Sprecher 1, Sprecher 2, …). Die Aktion „Sprecher suchen“ berechnet nur diese Zuordnung neu — Text und Zeitmarken bleiben unverändert.",
      en: "Marks who is speaking in the text (Speaker 1, Speaker 2, …). The “Detect speakers” action only recomputes this mapping — text and timestamps stay unchanged.",
      pt: "Marca quem está falando no texto (Falante 1, Falante 2, …). A ação “Detectar falantes” recalcula apenas essa atribuição — texto e marcações permanecem inalterados.",
    },
  },
  {
    id: "num",
    category: "spk",
    sources: ["upload", "record", "url", "recording"],
    requires: ["diarize"],
    actions: ["tr", "spk"],
    whenBlocked: "explain",
    label: { de: "Anzahl", en: "Number", pt: "Quantidade" },
    note: {
      de: "Wie viele Personen voraussichtlich sprechen. Automatisch lässt das System die Zahl selbst ermitteln.",
      en: "How many people are expected to speak. Automatic lets the system figure it out.",
      pt: "Quantas pessoas devem falar. Automático permite que o sistema descubra.",
    },
  },
  {
    id: "sens",
    category: "spk",
    sources: ["upload", "record", "url", "recording"],
    requires: ["diarize"],
    actions: ["tr", "spk"],
    whenBlocked: "explain",
    label: { de: "Empfindlichkeit", en: "Sensitivity", pt: "Sensibilidade" },
    note: {
      de: "Wie schnell das System einen Sprecherwechsel erkennt. Weniger: wechselt nur bei deutlichen Pausen. Mehr: erkennt auch schnelle Wortwechsel — kann einzelne Wörter dem falschen Sprecher zuordnen.",
      en: "How quickly the system detects speaker changes. Less: only switches on clear pauses. More: also catches quick exchanges — may assign single words to the wrong speaker.",
      pt: "Quão rápido o sistema detecta mudanças de falante. Menos: muda apenas em pausas claras. Mais: captura trocas rápidas — pode atribuir palavras ao falante errado.",
    },
  },
  {
    id: "method",
    category: "spk",
    sources: ["upload", "record", "url", "recording"],
    requires: ["diarize"],
    actions: ["tr", "spk"],
    whenBlocked: "explain",
    label: { de: "Verfahren", en: "Method", pt: "Método" },
    note: {
      de: "Das Rechenverfahren hinter der Sprechererkennung. Automatisch: das System wählt passend zur Aufnahme.",
      en: "The computation behind speaker detection. Automatic: the system picks what fits the recording.",
      pt: "O método de cálculo por trás da detecção de falantes. Automático: o sistema escolhe conforme a gravação.",
    },
  },
  {
    id: "punct",
    category: "post",
    sources: ["upload", "record", "url", "recording"],
    requires: ["oidc", "backend"],
    // Punktuiert das Backend nativ, ist die Option bereits erfüllt → nur erklären.
    blockedBy: "native_punctuation",
    actions: ["tr"],
    whenBlocked: "explain",
    label: { de: "Zeichensetzung", en: "Punctuation", pt: "Pontuação" },
    note: {
      de: "Setzt automatisch Punkte, Kommas und Fragezeichen. Die reine Spracherkennung liefert nur Wörter ohne Satzzeichen — diese Option macht den Text lesbar. Der exakte Text bleibt erhalten.",
      en: "Adds periods, commas and question marks automatically. Raw recognition only outputs words without punctuation — this option makes the text readable. The exact text stays unchanged.",
      pt: "Adiciona pontos, vírgulas e interrogações automaticamente. O reconhecimento puro entrega apenas palavras sem pontuação — esta opção torna o texto legível. O texto exato permanece.",
    },
  },
  {
    id: "llmfix",
    category: "post",
    sources: ["upload", "record", "url", "recording"],
    requires: ["oidc"],
    actions: ["tr"],
    whenBlocked: "explain",
    label: { de: "ASR-Fehler korrigieren", en: "Fix ASR errors", pt: "Corrigir erros de ASR" },
    note: {
      de: "Behebt Erkennungsfehler: falsche Wörter, Namen, Zahlen. Der exakte Text bleibt erhalten — es wird nur korrigiert, nichts umformuliert, gekürzt oder ergänzt. Für wörtliche Zitate und Protokolle gedacht.",
      en: "Fixes recognition errors: wrong words, names, numbers. The exact text stays unchanged — only corrections, nothing reformulated, cut or added. Meant for verbatim quotes and minutes.",
      pt: "Corrige erros de reconhecimento: palavras, nomes, números errados. O texto exato permanece — apenas correções, nada reformulado, cortado ou acrescentado. Para citações literais e atas.",
    },
  },
  {
    id: "template",
    category: "post",
    sources: ["upload", "record", "url", "recording"],
    requires: ["oidc"],
    actions: ["tr"],
    whenBlocked: "explain",
    label: { de: "Vorlage", en: "Template", pt: "Modelo de prompt" },
    note: {
      de: "Bestimmt, wie die KI nachbearbeitet — z. B. „Protokoll-Stil“ oder „Kurzfassung“. Ohne Vorlage verwendet die KI ihren Standardstil.",
      en: "Determines how the AI post-processes — e.g. “minutes style” or “summary”. Without a template the AI uses its default style.",
      pt: "Define como a IA pós-processa — ex.: “estilo ata” ou “resumo”. Sem modelo, a IA usa o estilo padrão.",
    },
  },
  {
    id: "endpoint",
    category: "post",
    sources: ["upload", "record", "url", "recording"],
    requires: ["oidc"],
    actions: ["tr"],
    whenBlocked: "explain",
    label: { de: "KI-Server", en: "AI server", pt: "Servidor de IA" },
    note: {
      de: "Welcher KI-Dienst die Nachbearbeitung ausführt. Standard: der Dienst der Plattform. Eigener Anbieter: selbst hinterlegter Endpunkt — die Transkripte verlassen dann euren eigenen Server.",
      en: "Which AI service runs the post-processing. Default: the platform's service. Own provider: a custom endpoint — transcripts then leave your own server.",
      pt: "Qual serviço de IA executa o pós-processamento. Padrão: o serviço da plataforma. Próprio provedor: um endpoint personalizado — as transcrições saem então do seu servidor.",
    },
  },
  {
    id: "format",
    category: "post",
    sources: ["upload", "record", "url", "recording"],
    requires: ["oidc"],
    actions: ["tr"],
    whenBlocked: "explain",
    label: { de: "KI-Formatierung", en: "AI formatting", pt: "Formatação por IA" },
    note: {
      de: "Zweite KI-Stufe: formt den fertigen Text um — z. B. in ein stichwortartiges Protokoll. Der Wortlaut stimmt danach bewusst nicht mehr mit dem Audio überein, deshalb steht das Ergebnis in einem eigenen Bereich UNTER dem Transkript und das wörtliche Transkript bleibt erhalten. Es fallen zusätzliche Zeit und Token an.",
      en: "Second AI stage: reshapes the finished text — e.g. into bullet-point minutes. The wording then deliberately differs from the audio, so the result appears in its own area BELOW the transcript and the verbatim transcript is kept. Extra time and tokens apply.",
      pt: "Segunda etapa de IA: transforma o texto final — por ex. numa ata em tópicos. O texto deixa de coincidir com o áudio, por isso o resultado aparece numa área própria ABAIXO da transcrição e a transcrição literal mantém-se. Há tempo e tokens adicionais.",
    },
  },
  {
    id: "formatPreset",
    category: "post",
    sources: ["upload", "record", "url", "recording"],
    requires: ["oidc"],
    actions: ["tr"],
    whenBlocked: "explain",
    label: { de: "Format", en: "Format", pt: "Formato" },
    note: {
      de: "Wohin umgeformt wird — z. B. „Stichwort-Protokoll“ oder „Zusammenfassung“. Eigene Vorlagen kannst du zusätzlich auswählen; sie ersetzen die Vorgabe. Ohne Auswahl gilt das Stichwort-Protokoll.",
      en: "What the text is transformed into — e.g. “bullet-point minutes” or “summary”. Your own templates can be picked as well; they replace the preset. Without a choice, bullet-point minutes apply.",
      pt: "Em que o texto é transformado — ex. “ata em tópicos” ou “resumo”. Os teus próprios modelos também podem ser escolhidos; substituem a predefinição. Sem escolha aplica-se a ata em tópicos.",
    },
  },
  {
    id: "formatServer",
    category: "post",
    sources: ["upload", "record", "url", "recording"],
    requires: ["oidc"],
    actions: ["tr"],
    whenBlocked: "explain",
    label: { de: "KI-Server für Formatierung", en: "AI server for formatting",
             pt: "Servidor de IA para formatação" },
    note: {
      de: "Welcher Dienst umformt. Vorgabe: derselbe Dienst wie bei der Nachbearbeitung (der der Plattform). Eigener Anbieter: selbst hinterlegter Endpunkt — der Text verlässt dann euren Server. Der Dienst der Plattform ist kostenpflichtig.",
      en: "Which service reshapes the text. Default: the same service as post-processing (the platform's). Own provider: a custom endpoint — the text then leaves your server. The platform service is chargeable.",
      pt: "Que serviço transforma o texto. Predefinição: o mesmo serviço da pós-produção (o da plataforma). Próprio provedor: um endpoint próprio — o texto sai então do teu servidor. O serviço da plataforma é pago.",
    },
  },
  {
    id: "target",
    category: "post",
    sources: ["upload", "record", "url", "recording"],
    requires: ["oidc"],
    actions: ["tr"],
    whenBlocked: "explain",
    label: { de: "Senden an", en: "Send to", pt: "Enviar para" },
    note: {
      de: "Ziel, an das der fertige Text zusätzlich geschickt wird (E-Mail oder WebDAV-Ordner).",
      en: "Destination that additionally receives the finished text (email or WebDAV folder).",
      pt: "Destino que também recebe o texto final (e-mail ou pasta WebDAV).",
    },
  },
];

export function optionRow(id: OptionId): OptionRow | undefined {
  return OPTION_MATRIX.find((r) => r.id === id);
}

/* ============================================================
   Verfügbarkeit — eine Regel für alle Optionen
   ============================================================ */

/** Was das Panel zum Entscheiden braucht (alles aus der API, nichts geraten). */
export interface OptionContext {
  source: OptionSource;
  action: OptionAction;
  /** Wählbare Backend-Namen (aus /api/models/matrix, nach Zugriff gefiltert). */
  backends: string[];
  /** Gewähltes Backend ("" = Server-Default). */
  backend: string;
  /** Backend-Fähigkeiten aus /api/backends; null = (noch) nicht abrufbar. */
  caps: BackendCapabilities | null;
  /** Dienste aus /api/models/status. */
  services: { vad: boolean; diarize: boolean; oidc: boolean };
  /** Aktuelle Werte, soweit sie die Verfügbarkeit bestimmen. */
  values: { diarize: boolean };
}

export type OptionAvailability =
  | { state: "available" }
  | { state: "blocked"; reason: OptText }
  | { state: "hidden" };

/** Fähigkeit eines Backends — `undefined` = die API sagt nichts dazu. */
export function capsFor(
  caps: BackendCapabilities | null,
  backend: string,
): { streaming?: boolean; nativePunctuation?: boolean } {
  if (!caps) return {};
  const key = backend || "";
  return {
    streaming: caps.streaming_by_backend?.[key],
    nativePunctuation: caps.native_punctuation?.[key],
  };
}

/** Erste nicht erfüllte Voraussetzung → Begründung; null = alles erfüllt. */
function unmetRequirement(req: OptionRequirement, ctx: OptionContext): OptText | null {
  switch (req) {
    case "backend":
      if (!ctx.caps) return REASON.caps_missing;
      if (ctx.backends.length === 0) return REASON.no_backends;
      return null;
    case "streaming": {
      const can = capsFor(ctx.caps, ctx.backend).streaming;
      if (can === undefined) return REASON.caps_missing;
      return can ? null : REASON.streaming;
    }
    case "diarize":
      return ctx.values.diarize ? null : REASON.diarize_off;
    case "vad_service":
      return ctx.services.vad ? null : REASON.vad_service;
    case "diar_service":
      return ctx.services.diarize ? null : REASON.diar_service;
    case "oidc":
      return ctx.services.oidc ? null : REASON.oidc;
    default:
      return null;
  }
}

/**
 * Verfügbarkeit einer Matrix-Zeile. Reihenfolge:
 * 1. wirkt die Option in dieser Quelle? → sonst ausgeblendet.
 * 2. wirkt sie bei dieser Aktion / sind die Voraussetzungen erfüllt?
 * 3. Fähigkeits-Fakt, der die Option überflüssig macht (Backend kann es selbst).
 */
export function optionAvailability(row: OptionRow, ctx: OptionContext): OptionAvailability {
  if (!row.sources.includes(ctx.source)) return { state: "hidden" };

  let reason: OptText | null = row.actions.includes(ctx.action) ? null : REASON.action;
  if (!reason) {
    for (const req of row.requires) {
      reason = unmetRequirement(req, ctx);
      if (reason) break;
    }
  }
  if (!reason && row.blockedBy === "native_punctuation") {
    const native = capsFor(ctx.caps, ctx.backend).nativePunctuation;
    // Nur wenn die API es ausdrücklich sagt — sonst nichts behaupten.
    if (native === true) reason = REASON.punct_native;
  }

  if (!reason) return { state: "available" };
  return row.whenBlocked === "explain"
    ? { state: "blocked", reason }
    : { state: "hidden" };
}

/** Zeilen einer Kategorie in Matrix-Reihenfolge. */
export function rowsOf(category: OptionCategory): OptionRow[] {
  return OPTION_MATRIX.filter((r) => r.category === category);
}
