// ── SuiteExplainer (Change 135) ────────────────────────────────────────────
// Zweistufige Erklärung je Benchmark-Tab (ASR/VAD/Align/Diar):
//   - Laien-Teil (immer sichtbar): Was wurde getestet? Was liest man ab?
//   - Profi-Teil (einblendbar): Methodologie, Metriken, Modelle, Quellen.
// Keine erfundenen Qualitätsstufen — nur die tatsächlichen Metriken,
// in einfachen Worten erklärt.

import { useState } from "react";

export type SuiteId = "asr" | "vad" | "align" | "diar";

interface SuiteExplainerContent {
  /** Laien: was wird hier getestet (2–4 Sätze). */
  layman: string;
  /** Laien: wie liest man die Ergebnisse ab. */
  readout: string;
  /** Profi: Methodologie/Metriken (Stichpunkte). */
  pro: string[];
}

const CONTENT: Record<SuiteId, SuiteExplainerContent> = {
  asr: {
    layman:
      "Hier wird getestet, wie gut jedes Spracherkennungs-Modell (ASR) gesprochenes Deutsch in Text verwandelt. Jede Probe-Aufnahme wird dem Modell vorgespielt — das Modell schreibt auf, was es hört. Verglichen wird mit dem bekannten Originaltext (Ground Truth).",
    readout:
      "Die Balken zeigen die Erkennungs-Qualität je Modell: 100 % = fehlerfrei verstanden, 0 % = nichts. Je grüner und breiter der Balken, desto besser. Unter den Balken steht (bei neuen Läufen) wörtlich, was das Modell statt des Originaltexts erkannt hat — da sieht man die Fehler direkt.",
    pro: [
      "Metrik WER (Word Error Rate): Wort-Abstand (Levenshtein) zwischen Hypothese und Referenz, normalisiert auf die Referenz-Wortzahl. Qualitätsanzeige = 1 − WER. CER analog auf Zeichenebene.",
      "coverage_pct: Anteil der erkannten Wörter relativ zur Referenz (unter 100 % = Wörter fehlen ganz).",
      "RTF (Real-Time Factor): Verarbeitungszeit ÷ Audiodauer — 0,1 heißt: 1 min Audio in 6 s.",
      "Testset: echte Common-Voice-Stimmen (CC0) + Piper-TTS + DEMAND-Umweltgeräusche (CC-BY-4.0, Zenodo), 2 Achsen (Kanal × Inhalt). Held-out-Samples bleiben geheim (Anti-Gaming).",
      "Modelle: ps-pk-onnx (Parakeet-TDT-0.6B, ONNX/CUDA), crispr-pk-cpp (CrispASR, parakeet-GGUF), crispr-qwen3 (Qwen3-ASR), crispr-moonshine-de, crispr-canary, crispr-voxtral, crispr-whisper, crispr-ark.",
      "Werte sind über die Läufe gepoolt (per_category/per_sample); settings = Auto-Pipeline (lowercase, Satzzeichen entfernt) für vergleichbare WER.",
    ],
  },
  vad: {
    layman:
      "VAD (Voice Activity Detection) beantwortet: Wo in einer Aufnahme wird gesprochen — und wo nicht? Das ist wichtig, um Stille abzuschneiden, nur die Sprachteile weiterzuverarbeiten oder Aufnahmen vorzubereiten. Getestet wird Sprache allein, Sprache mit Umgebungsgeräuschen und reine Geräuschproben ohne Sprache.",
    readout:
      "F1 ist die zentrale Kennzahl: 1,0 = perfekte Trennung von Sprache und Nicht-Sprache, kleinere Werte = mehr Fehler. B-Start/B-Ende (in ms) zeigen, wie genau der Anfang und das Ende der Sprache getroffen werden — klein ist gut. FP-Speech sind Sekunden, die fälschlich als Sprache markiert wurden, obwohl dort keine ist — 0 ist ideal. RTF sagt, wie schnell das Modell arbeitet.",
    pro: [
      "F1 über Grenzwert-Matching: GT-Sprachregionen vs. erkannte Regionen, IoU-basiert.",
      "Boundary-Genauigkeit: Median der Abweichung von GT-Start/-Ende in ms.",
      "FP-Speech: Summe der fälschlich als Sprache erkannten Zeit (ohne GT-Sprache).",
      "Testset V3.1-public (235 Samples): Common Voice + DEMAND-SNR-Mixe (0/5/10 dB, je 2 Noise-Quellen) + Noise/Musik/Babble-FP-Proben ohne GT + TEN-Referenzsamples.",
      "Engines: silero-onnx (produktiv), webrtc, humaware, speechbrain, energy; Referenz mit Lizenz-Klausel: TEN VAD, Cobra, MarbleNet (nur Vergleich, nicht produktiv).",
      "Submission: VAD-Container holen das Paket (/api/benchmark/vadpackage), messen, submitten mit HMAC-Signatur.",
    ],
  },
  align: {
    layman:
      "Forced-Alignment beantwortet: Zu welcher Zeit wurde jedes einzelne Wort gesprochen? Das Modell bekommt die Aufnahme UND den fertigen Text — es muss jedes Wort an die richtige Stelle im Audio legen. Das ist die Technik hinter Karaoke-Sync und Wort-Hervorhebung beim Abspielen.",
    readout:
      "Wortabdeckung zeigt, wie viel Prozent der Wörter überhaupt eine gültige Zeit bekommen haben — 100 % = alle. 0-Dauer-Wörter sind Aligner-Fehler (Wort auf 0 Sekunden gelegt) — je weniger, desto besser. Audio-Abdeckung vergleicht das letzte Wort-Ende mit der Audio-Dauer. RTF = Geschwindigkeit. Der Kreuz-Vergleich zeigt, wie stark sich die Aligner untereinander unterscheiden.",
    pro: [
      "Metriken: word_coverage_mean (%), zero_duration_total (Wörter mit Dauer 0), audio_coverage_mean (%), rtf_mean.",
      "Drei Methoden in einem Container (Change 133): qwen3-forced-aligner-0.6b (cstr-GGUF), TADA (tada-tts-1b, Sprachmodell-gestützt), wav2vec2-xlsr-de (Wav2Vec2, deutsch).",
      "Läuft auf denselben deutschen Samples wie der ASR-Benchmark (Common Voice + Piper-TTS), über die HTTP-API des Containers (POST /v1/audio/align, identischer Pfad wie in der Webapp).",
      "Kreuz-Vergleich: paarweise |Δ Wortstart|-Median über übereinstimmende Wörter — Konsistenz-Indikator, kein absolutes Maß (keine manuelle GT).",
      "Referenz-Benchmarks mit manuell gelabelten Wortgrenzen: Aligner-SUPERB (WBE, TIMIT), FA-Bench, PHONDAT/MAUS (deutsch) — Details: docs/benchmark/aligner.md.",
    ],
  },
  diar: {
    layman:
      "Diarization beantwortet: Wer spricht wann? Die Aufnahme wird in Abschnitte geteilt und jedem Abschnitt ein Sprecher zugeordnet („Sprecher 1, Sprecher 2, …“). Das ist die Grundlage für Meeting-Protokolle mit Sprecher-Zuordnung. Hier ist die Diar-Test-Suite noch im Aufbau — sobald sie läuft, erscheinen die Ergebnisse an dieser Stelle.",
    readout:
      "Noch keine Daten. Sobald die Diar-Suite läuft, zeigt dieser Tab je Methode: wie gut die Sprecher-Grenzen getroffen werden, wie viele Sprecher korrekt erkannt werden und wie viel Sprache falsch zugeordnet wurde. Die Samples werden wie in den anderen Tabs anhörbar sein.",
    pro: [
      "Geplante Metriken: DER (Diarization Error Rate = Missed Speech + False Alarm + Speaker Confusion) bzw. Jaccard-Ähnlichkeit je Segment.",
      "Geplantes Testset: Standard-Diarization-Sets (z. B. VoxConverse/AMI-artige deutsche Ausschnitte) statt synthetischer Mischungen — Abgrenzung siehe Change 136.",
      "Methoden im Stack: foxnose (WeSpeaker-Embedder + Clustering, mono-tauglich, Default), pyannote-seg-3.0 (GGUF), vad-turns (pausenbasierte Turns, kein Modell).",
      "Wichtig: energy/xcorr-Methoden brauchen Stereo — unser Client liefert Mono, daher nur als Vergleich gelistet.",
      "Speaker-Kennung: embedder=auto (wespeaker → SPEAKER_00/01/…), CACHE-DIR aufs Modell-Volume (Container-Neustarts überleben).",
    ],
  },
};

export function SuiteExplainer({ suite }: { suite: SuiteId }) {
  const [showPro, setShowPro] = useState(false);
  const c = CONTENT[suite];
  return (
    <section className="border border-border rounded-lg p-4" data-testid={`suite-explainer-${suite}`}>
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div className="min-w-0 flex-1">
          <h2 className="font-semibold mb-1">Was wird hier getestet?</h2>
          <p className="text-sm text-dim">{c.layman}</p>
          <p className="text-sm text-dim mt-2">
            <strong className="text-txt">So liest du die Ergebnisse:</strong> {c.readout}
          </p>
        </div>
      </div>
      <button
        type="button"
        onClick={() => setShowPro((v) => !v)}
        aria-expanded={showPro}
        data-testid={`explainer-toggle-${suite}`}
        className="mt-3 btn-ghost text-xs"
      >
        {showPro ? "▾ Technische Details ausblenden" : "▸ Technische Details (für Profis)"}
      </button>
      {showPro && (
        <ul className="mt-2 space-y-1 border-t border-border pt-2 text-xs text-dim list-disc pl-4" data-testid={`explainer-pro-${suite}`}>
          {c.pro.map((line, i) => (
            <li key={i}>{line}</li>
          ))}
        </ul>
      )}
    </section>
  );
}
