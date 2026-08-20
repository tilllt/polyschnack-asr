import { useState } from "react";
import { WaveformPlayer } from "./WaveformPlayer";
import type {
  BenchmarkCategory,
  BenchmarkMeta,
  BenchmarkSample,
  BenchmarkSamplesResponse,
  BenchmarkPricing,
  BenchmarkResults,
} from "../benchmark";

// ── Collapsible Kategorie (nur eine offen, State in Page) ────────────────

interface CategoryProps {
  cat: BenchmarkCategory;
  samples: BenchmarkSample[];
  open: boolean;
  onToggle: () => void;
  showText: boolean;
  admin: boolean;
  onReject?: (sampleId: string) => void;
  onEdit?: (sampleId: string, fields: { text: string }) => void;
  previewUrl: (id: string) => string;
  audioUrl: (id: string) => string;
}

export function BenchmarkCategory({
  cat, samples, open, onToggle, showText, admin, onReject, onEdit, previewUrl, audioUrl,
}: CategoryProps) {
  return (
    <div className="border border-border rounded-lg overflow-hidden">
      <button
        onClick={onToggle}
        className="w-full flex items-center justify-between px-4 py-3 bg-[rgba(255,255,255,.03)] hover:bg-[rgba(255,255,255,.06)] text-left"
        aria-expanded={open}
      >
        <span className="font-semibold">
          {cat.name} <span className="text-dim">({samples.length})</span>
        </span>
        <span className="text-dim">{open ? "▾" : "▸"}</span>
      </button>
      {open && (
        <ul className="divide-y divide-border">
          {samples.map((s) => (
            <SampleRow
              key={s.id}
              sample={s}
              showText={showText}
              admin={admin}
              onReject={onReject}
              onEdit={onEdit}
              previewUrl={previewUrl}
              audioUrl={audioUrl}
            />
          ))}
        </ul>
      )}
    </div>
  );
}

function SampleRow({
  sample, showText, admin, onReject, onEdit, previewUrl, audioUrl,
}: {
  sample: BenchmarkSample;
  showText: boolean;
  admin: boolean;
  onReject?: (id: string) => void;
  onEdit?: (id: string, fields: { text: string }) => void;
  previewUrl: (id: string) => string;
  audioUrl: (id: string) => string;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(sample.text);

  return (
    <li className="px-4 py-3">
      <div className="flex flex-wrap items-center gap-2 mb-2">
        <span className="font-mono text-xs text-dim">{sample.id}</span>
        {sample.accent && <span className="text-xs badge">{sample.accent}</span>}
        {sample.age && <span className="text-xs badge">{sample.age}</span>}
        <div className="ml-auto flex items-center gap-2">
          <a href={audioUrl(sample.id)} download={`${sample.id}.wav`} className="btn-ghost text-xs">
            ⬇ WAV
          </a>
          {admin && onReject && (
            <button
              onClick={() => onReject(sample.id)}
              className="btn-ghost text-xs text-red-400"
              title="Sample ablehnen → Auto-Ersatz + neue Version"
            >
              ✕ Ablehnen
            </button>
          )}
          {admin && onEdit && (
            <button onClick={() => setEditing((e) => !e)} className="btn-ghost text-xs">
              {editing ? "Fertig" : "Edit"}
            </button>
          )}
        </div>
      </div>

      <WaveformPlayer audioUrl={previewUrl(sample.id)} height={56} />

      {editing && onEdit ? (
        <div className="mt-2 flex gap-2">
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            className="flex-1 bg-bg border border-border rounded px-2 py-1 text-sm"
          />
          <button
            onClick={() => { onEdit(sample.id, { text: draft }); setEditing(false); }}
            className="btn text-xs"
          >
            Speichern
          </button>
        </div>
      ) : (
        showText && <p className="mt-2 text-sm text-dim">{sample.text}</p>
      )}
    </li>
  );
}

// ── 2-Achsen-Matrix (Kanal × Inhalt) ─────────────────────────────────────

interface MatrixProps {
  meta: BenchmarkMeta;
  active: { kanal: string; inhalt: string } | null;
  onSelect: (cell: { kanal: string; inhalt: string } | null) => void;
}

export function AxesMatrix({ meta, active, onSelect }: MatrixProps) {
  const axes = meta.axes;
  if (!axes || !meta.matrix) {
    return <p className="text-sm text-dim">Keine Taxonomie-Achsen im Manifest.</p>;
  }
  const kanalKeys = Object.keys(axes.kanal.kategorien);
  const inhaltKeys = Object.keys(axes.inhalt.kategorien);

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm border-collapse">
        <thead>
          <tr>
            <th className="py-1 pr-2 text-left text-dim font-normal">
              Kanal ↓ · Inhalt →
            </th>
            {inhaltKeys.map((ik) => (
              <th key={ik} className="py-1 px-2 text-center font-medium">
                {axes.inhalt.kategorien[ik].name}
              </th>
            ))}
            <th className="py-1 px-2 text-center font-medium">Σ</th>
          </tr>
        </thead>
        <tbody>
          {kanalKeys.map((kk) => (
            <tr key={kk}>
              <td className="py-1 pr-2 whitespace-nowrap">
                <span className="font-medium">{axes.kanal.kategorien[kk].name}</span>
                <span className="text-dim text-xs block">{kk}</span>
              </td>
              {inhaltKeys.map((ik) => {
                const n = meta.matrix?.[kk]?.[ik] ?? 0;
                const isActive = active?.kanal === kk && active?.inhalt === ik;
                return (
                  <td key={ik} className="py-1 px-1 text-center">
                    <button
                      onClick={() => onSelect(isActive ? null : { kanal: kk, inhalt: ik })}
                      disabled={n === 0}
                      className={[
                        "min-w-[2.4rem] px-2 py-1 rounded text-xs",
                        n === 0
                          ? "text-dim/30 cursor-not-allowed"
                          : isActive
                            ? "bg-accent text-bg font-bold"
                            : "bg-[rgba(255,255,255,.05)] hover:bg-[rgba(255,255,255,.12)] cursor-pointer",
                      ].join(" ")}
                      title={`${axes.kanal.kategorien[kk].name} × ${axes.inhalt.kategorien[ik].name}: ${n} Samples`}
                    >
                      {n > 0 ? n : "·"}
                    </button>
                  </td>
                );
              })}
              <td className="py-1 px-2 text-center text-dim">
                {inhaltKeys.reduce((acc, ik) => acc + (meta.matrix?.[kk]?.[ik] ?? 0), 0)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="text-xs text-dim mt-2">
        {meta.matrix_total ?? 0} Samples gesamt · Klick auf eine Zelle filtert die Samples darunter
        {active ? ` (aktiv: ${active.kanal} × ${active.inhalt})` : ""}
      </p>
    </div>
  );
}

// ── Test-Set-Erklärung ────────────────────────────────────────────────────

export function TestSetExplanation({ meta }: { meta: BenchmarkMeta }) {
  const axes = meta.axes;
  const total = meta.matrix_total ?? meta.sample_count;
  return (
    <div className="text-sm text-dim space-y-2">
      <p>
        Das Test-Set besteht aus <strong className="text-txt">{total} Samples</strong>{" "}
        (echte CommonVoice-Sprecher + Piper-TTS), aufgeteilt nach{" "}
        <strong className="text-txt">2 Achsen</strong> — angelehnt an die Best
        Practice echter ASR-Benchmarks (GigaSpeechBench, LibriSpeech, REVERB, CHiME):
      </p>
      <ul className="list-disc pl-5 space-y-1">
        {axes?.kanal && (
          <li>
            <strong className="text-txt">Kanal (Akustik):</strong>{" "}
            {axes.kanal.beschreibung.toLowerCase()}{" "}
            {Object.values(axes.kanal.kategorien).map((k) => k.name).join(" · ")}
          </li>
        )}
        {axes?.inhalt && (
          <li>
            <strong className="text-txt">Inhalt (Schwierigkeit):</strong>{" "}
            {axes.inhalt.beschreibung.toLowerCase()}{" "}
            {Object.values(axes.inhalt.kategorien).map((k) => k.name).join(" · ")}
          </li>
        )}
        <li>
          <strong className="text-txt">Quelle:</strong> <code className="text-xs">cv</code> =
          echte Stimmen (CC0), <code className="text-xs">tts</code> = synthetisch (Piper)
        </li>
      </ul>
      <p>
        Jedes Sample liegt als unkomprimierte WAV vor (Benchmark-Lauf) und als{" "}
        <strong className="text-txt">MP3-128k-Preview</strong> (Anhören).{" "}
        Referenztexte und held-out-Samples bleiben privat (Anti-Gaming) — die
        WER/CER-Werte sind deshalb nicht „trainierbar".
      </p>
    </div>
  );
}

// ── Modellqualität je Kategorie (REQ-BEN-047) ────────────────────────────

const MODEL_COLORS = [
  "#8b5cf6", "#22d3ee", "#fbbf24", "#34d399",
  "#f472b6", "#60a5fa", "#fb923c", "#a3e635",
];

function modelColor(backend: string): string {
  let h = 0;
  for (const ch of backend) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return MODEL_COLORS[h % MODEL_COLORS.length];
}

export function CategoryQualityChart({
  categoryId, categoryName, rows, hiddenModels,
}: {
  categoryId: string;
  categoryName: string;
  rows: Array<{ backend: string; wer: number; n: number }>;
  hiddenModels: ReadonlySet<string>;
}) {
  const visible = rows.filter((r) => !hiddenModels.has(r.backend));
  if (visible.length === 0) return null;
  const sorted = [...visible].sort((a, b) => a.wer - b.wer);
  return (
    <div className="border border-border rounded-lg p-3">
      <h3 className="font-semibold text-sm mb-2">{categoryName}</h3>
      <div className="space-y-1.5">
        {sorted.map((r) => (
          <div
            key={r.backend}
            className="flex items-center gap-2"
            data-testid={`cat-bar-${categoryId}-${r.backend}`}
            title={`${r.backend}: WER ${(r.wer * 100).toFixed(1)} % (${r.n} Samples)`}
          >
            <span className="w-32 font-mono text-xs text-dim truncate">{r.backend}</span>
            <div className="flex-1 h-4 bg-[rgba(255,255,255,.06)] rounded overflow-hidden">
              <div
                className="h-full rounded"
                style={{ width: `${Math.min(100, Math.max(2, r.wer * 100))}%`, background: modelColor(r.backend) }}
              />
            </div>
            <span className="text-xs tabular-nums w-14 text-right">{(r.wer * 100).toFixed(1)}%</span>
            <span className="text-xs text-dim w-10 text-right">({r.n})</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export function CategoryQualityCharts({
  results, meta, hiddenModels,
}: {
  results: BenchmarkResults | null;
  meta: BenchmarkMeta;
  hiddenModels: ReadonlySet<string>;
}) {
  const perCat = results?.per_category;
  if (!perCat?.length) {
    return <p className="text-sm text-dim">Noch keine Kategorie-Ergebnisse (nach dem ersten Submit).</p>;
  }
  const catName = new Map(meta.categories.map((c) => [c.id, c.name]));
  const byCat = new Map<string, Array<{ backend: string; wer: number; n: number }>>();
  for (const r of perCat) {
    const arr = byCat.get(r.category) ?? [];
    arr.push({ backend: r.backend, wer: r.wer, n: r.n });
    byCat.set(r.category, arr);
  }
  const cats = [...byCat.entries()].sort((a, b) => a[0].localeCompare(b[0]));
  return (
    <div className="grid gap-3 md:grid-cols-2">
      {cats.map(([id, rows]) => (
        <CategoryQualityChart
          key={id}
          categoryId={id}
          categoryName={catName.get(id) ?? id}
          rows={rows}
          hiddenModels={hiddenModels}
        />
      ))}
    </div>
  );
}

// ── Modell-Filter (REQ-BEN-048) ──────────────────────────────────────────

export function ModelFilterChips({
  models, hiddenModels, onToggle, onReset,
}: {
  models: string[];
  hiddenModels: ReadonlySet<string>;
  onToggle: (backend: string) => void;
  onReset: () => void;
}) {
  if (models.length === 0) return null;
  const chipCls = (active: boolean) =>
    [
      "px-2.5 py-1 rounded-full text-xs font-medium border transition-colors",
      active
        ? "bg-[rgba(139,92,246,.25)] border-accent text-txt"
        : "bg-transparent border-border text-dim hover:text-txt",
    ].join(" ");
  return (
    <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Modell-Filter">
      <span className="text-sm text-dim">Modelle:</span>
      <button
        onClick={onReset}
        data-active={hiddenModels.size === 0 ? "true" : "false"}
        className={chipCls(hiddenModels.size === 0)}
      >
        Alle
      </button>
      {models.map((m) => {
        const active = !hiddenModels.has(m);
        return (
          <button
            key={m}
            onClick={() => onToggle(m)}
            data-active={active ? "true" : "false"}
            data-testid={`model-chip-${m}`}
            className={chipCls(active)}
          >
            {m}
          </button>
        );
      })}
    </div>
  );
}

// ── Preisvergleich ────────────────────────────────────────────────────────

export function PriceComparison({ pricing, hiddenModels }: { pricing: BenchmarkPricing | null; hiddenModels?: ReadonlySet<string> }) {
  if (!pricing || !pricing.rows?.length) {
    return <p className="text-sm text-dim">Noch kein Preisvergleich verfügbar.</p>;
  }
  const filtered = hiddenModels?.size
    ? pricing.rows.filter((r) => !hiddenModels.has(r.backend))
    : pricing.rows;
  if (!filtered.length) {
    return <p className="text-sm text-dim">Keine Preisdaten für die ausgewählten Modelle.</p>;
  }
  const sorted = [...filtered].sort((a, b) =>
    (a.wer ?? 99) - (b.wer ?? 99) || (a.eur_per_min_selfhost ?? 99) - (b.eur_per_min_selfhost ?? 99),
  );
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-dim border-b border-border">
            <th className="py-2 pr-2">Backend</th>
            <th className="py-2 pr-2">WER %</th>
            <th className="py-2 pr-2">€/min (Selbstkosten)</th>
            <th className="py-2 pr-2">€/min (SaaS)</th>
            <th className="py-2 pr-2">€/min (kommerziell)</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((r) => (
            <tr key={r.backend} className="border-b border-border/50">
              <td className="py-2 pr-2 font-mono">{r.backend}</td>
              <td className="py-2 pr-2">{r.wer != null ? (r.wer * 100).toFixed(1) : "–"}</td>
              <td className="py-2 pr-2">{r.eur_per_min_selfhost != null ? r.eur_per_min_selfhost.toFixed(4) : "–"}</td>
              <td className="py-2 pr-2">{r.eur_per_min_saas != null ? r.eur_per_min_saas.toFixed(4) : "–"}</td>
              <td className="py-2 pr-2">{r.eur_per_min_commercial != null ? r.eur_per_min_commercial.toFixed(4) : "–"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ── Ergebnisse-Tabelle ────────────────────────────────────────────────────

export function ResultsTable({ results, hiddenModels }: { results: BenchmarkResults | null; hiddenModels?: ReadonlySet<string> }) {
  if (!results || !results.rows?.length) {
    return <p className="text-sm text-dim">Noch keine Benchmark-Ergebnisse.</p>;
  }
  const rows = hiddenModels?.size
    ? results.rows.filter((r) => !hiddenModels.has(r.backend))
    : results.rows;
  if (!rows.length) {
    return <p className="text-sm text-dim">Keine Ergebnisse für die ausgewählten Modelle.</p>;
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-dim border-b border-border">
            <th className="py-2 pr-2">Backend</th>
            <th className="py-2 pr-2">Settings</th>
            <th className="py-2 pr-2">WER %</th>
            <th className="py-2 pr-2">CER %</th>
            <th className="py-2 pr-2">Coverage %</th>
            <th className="py-2 pr-2">RTF</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={`${r.backend}-${r.settings ?? ""}-${i}`} className="border-b border-border/50">
              <td className="py-2 pr-2 font-mono">{r.backend}</td>
              <td className="py-2 pr-2">{r.settings ?? "auto"}</td>
              <td className="py-2 pr-2">{r.wer != null ? (r.wer * 100).toFixed(1) : "–"}</td>
              <td className="py-2 pr-2">{r.cer != null ? (r.cer * 100).toFixed(1) : "–"}</td>
              <td className="py-2 pr-2">{r.coverage_pct != null ? r.coverage_pct.toFixed(1) : "–"}</td>
              <td className="py-2 pr-2">{r.rtf != null ? r.rtf.toFixed(2) : "–"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────

interface PageProps {
  meta: BenchmarkMeta | null;
  data: BenchmarkSamplesResponse | null;
  results: BenchmarkResults | null;
  pricing: BenchmarkPricing | null;
  admin: boolean;
  onReject: (sampleId: string) => void;
  onEdit: (sampleId: string, fields: { text: string }) => void;
  onReload: () => void;
}

export function BenchmarkPageContent({ meta, data, results, pricing, admin, onReject, onEdit, onReload }: PageProps) {
  const [openCat, setOpenCat] = useState<string | null>(null);
  const [showText, setShowText] = useState(true);
  const [matrixCell, setMatrixCell] = useState<{ kanal: string; inhalt: string } | null>(null);
  const [hiddenModels, setHiddenModels] = useState<ReadonlySet<string>>(new Set());

  // REQ-BEN-048: Modell-Liste aus per_category (Fallback: gepoolte rows)
  const modelList = results?.per_category?.length
    ? [...new Set(results.per_category.map((r) => r.backend))].sort()
    : results?.rows?.length
      ? [...new Set(results.rows.map((r) => r.backend))].sort()
      : [];

  const toggleModel = (backend: string) => {
    const next = new Set(hiddenModels);
    if (next.has(backend)) next.delete(backend);
    else next.add(backend);
    setHiddenModels(next);
  };

  if (!meta || !data) {
    return (
      <div className="max-w-5xl mx-auto px-4 py-8">
        <h1 className="text-2xl font-bold mb-4">PolySchnack Benchmark</h1>
        <p className="text-dim">Benchmark-Daten sind noch nicht verfügbar.</p>
      </div>
    );
  }

  // Matrix-Filter: nur Samples der aktiven Zelle (kanal×inhalt)
  const filtered = matrixCell
    ? data.samples.filter(
        (s) => (s.kanal ?? "clean") === matrixCell.kanal && (s.inhalt ?? "allgemein") === matrixCell.inhalt,
      )
    : data.samples;

  const grouped = new Map<string, BenchmarkSample[]>();
  for (const s of filtered) {
    const arr = grouped.get(s.category) ?? [];
    arr.push(s);
    grouped.set(s.category, arr);
  }
  const cats = meta.categories.map((c) => ({
    cat: c,
    samples: grouped.get(c.id) ?? [],
  }));

  return (
    <div className="max-w-5xl mx-auto px-4 py-8 space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold">PolySchnack Benchmark</h1>
          <p className="text-sm text-dim">
            Version {meta.version}
            {meta.created_at ? ` · Stand ${new Date(meta.created_at).toLocaleDateString("de-DE")}` : ""}
            {" "}· {meta.sample_count} Samples
          </p>
        </div>
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 text-sm text-dim cursor-pointer">
            <input type="checkbox" checked={showText} onChange={(e) => setShowText(e.target.checked)} />
            Referenztext anzeigen
          </label>
          <button onClick={onReload} className="btn-ghost text-sm">↻ Neu laden</button>
        </div>
      </div>

      {/* REQ-BEN-048: Modell-Filter (oben) */}
      {modelList.length > 0 && (
        <section className="border border-border rounded-lg p-3">
          <ModelFilterChips
            models={modelList}
            hiddenModels={hiddenModels}
            onToggle={toggleModel}
            onReset={() => setHiddenModels(new Set())}
          />
        </section>
      )}

      {/* Methodik */}
      <section className="border border-border rounded-lg p-4">
        <h2 className="font-semibold mb-1">Methodik</h2>
        <p className="text-sm text-dim">{meta.methodology}</p>
        <p className="text-sm text-dim mt-1">{meta.disclaimer}</p>
      </section>

      {/* 2-Achsen-Matrix */}
      <section className="border border-border rounded-lg p-4">
        <h2 className="font-semibold mb-2">Test-Set · 2-Achsen-Matrix</h2>
        <AxesMatrix meta={meta} active={matrixCell} onSelect={setMatrixCell} />
      </section>

      {/* REQ-BEN-047: Modellqualität je Kategorie */}
      <section className="space-y-3">
        <h2 className="font-semibold">Modellqualität je Kategorie</h2>
        <CategoryQualityCharts results={results} meta={meta} hiddenModels={hiddenModels} />
      </section>

      {/* Test-Set-Erklärung */}
      <section className="border border-border rounded-lg p-4">
        <h2 className="font-semibold mb-2">Wie ist das Test-Set aufgebaut?</h2>
        <TestSetExplanation meta={meta} />
      </section>

      {/* Samples nach Kategorie (collapsible) */}
      <section className="space-y-2">
        <h2 className="font-semibold">
          Samples
          {matrixCell ? (
            <button onClick={() => setMatrixCell(null)} className="ml-2 btn-ghost text-xs">
              Filter: {matrixCell.kanal} × {matrixCell.inhalt} ✕
            </button>
          ) : null}
        </h2>
        {cats.map(({ cat, samples: ss }) => {
          // REQ-BEN-049: Kategorien mit 0 Samples ausblenden, nicht leer zeigen
          if (ss.length === 0) return null;
          return (
            <BenchmarkCategory
              key={cat.id}
              cat={cat}
              samples={ss}
              open={openCat === cat.id}
              onToggle={() => setOpenCat(openCat === cat.id ? null : cat.id)}
              showText={showText}
              admin={admin}
              onReject={onReject}
              onEdit={onEdit}
              previewUrl={(id) => `/api/benchmark/preview/${id}`}
              audioUrl={(id) => `/api/benchmark/audio/${id}`}
            />
          );
        })}
        {filtered.length === 0 && (
          <p className="text-sm text-dim">Keine Samples in dieser Matrix-Zelle.</p>
        )}
      </section>

      {/* Ergebnisse */}
      <section className="border border-border rounded-lg p-4">
        <h2 className="font-semibold mb-2">Ergebnisse</h2>
        <ResultsTable results={results} hiddenModels={hiddenModels} />
      </section>

      {/* Preisvergleich */}
      <section className="border border-border rounded-lg p-4">
        <h2 className="font-semibold mb-2">Preisvergleich</h2>
        <PriceComparison pricing={pricing} hiddenModels={hiddenModels} />
      </section>
    </div>
  );
}
