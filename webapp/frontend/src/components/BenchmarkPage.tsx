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
  /** Change 039: beste Modelle je Kategorie (sehr kleine Tabelle). */
  qualityRows: Array<{ backend: string; wer: number; n: number }>;
  /** Change 039: WER je Backend für genau dieses Sample (per_sample). */
  perSample: Record<string, Record<string, number>>;
  hiddenModels: ReadonlySet<string>;
}

export function BenchmarkCategory({
  cat, samples, open, onToggle, showText, admin, onReject, onEdit, previewUrl, audioUrl,
  qualityRows, perSample, hiddenModels,
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
        <>
          {/* Change 039: beste Modelle je Kategorie als Teil der Kategorie */}
          {qualityRows.length > 0 && (
            <CategoryQualityChart
              categoryId={cat.id}
              categoryName={cat.name}
              rows={qualityRows}
              hiddenModels={hiddenModels}
            />
          )}
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
                perSample={perSample[s.id]}
                hiddenModels={hiddenModels}
              />
            ))}
          </ul>
        </>
      )}
    </div>
  );
}

function SampleRow({
  sample, showText, admin, onReject, onEdit, previewUrl, audioUrl, perSample, hiddenModels,
}: {
  sample: BenchmarkSample;
  showText: boolean;
  admin: boolean;
  onReject?: (id: string) => void;
  onEdit?: (id: string, fields: { text: string }) => void;
  previewUrl: (id: string) => string;
  audioUrl: (id: string) => string;
  /** Change 039: WER je Backend für genau dieses Sample (optional). */
  perSample?: Record<string, number>;
  hiddenModels: ReadonlySet<string>;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(sample.text);

  // Change 039/040: Qualität pro Modell für dieses Sample als Mini-Balken
  // (grafisch), sortiert nach WER aufsteigend. ▤-Icon + grüne Akzente =
  // klar als Sample-Grafik erkennbar (Kategorie-Grafiken: ▦ + violett).
  const sampleRows = perSample
    ? Object.entries(perSample)
        .filter(([b]) => !hiddenModels.has(b))
        .sort((a, b) => a[1] - b[1])
    : [];
  const bestW = sampleRows.length ? sampleRows[0][1] : 0;

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

      {sampleRows.length > 0 && (
        <div className="mt-1.5" data-testid={`sample-wer-${sample.id}`}>
          <div className="flex items-center gap-1 text-[9px] text-emerald-300 uppercase tracking-wide mb-0.5">
            <span aria-hidden>▤</span>
            <span>Sample-Qualität</span>
          </div>
          <div className="space-y-1">
            {sampleRows.map(([backend, wer]) => {
              const pct = Math.max(4, Math.round((wer / (bestW || 0.0001)) * 100));
              return (
                <div
                  key={backend}
                  data-testid={`sample-wer-${sample.id}-${backend}`}
                  className="flex items-center gap-1.5"
                  title={`${backend}: WER ${(wer * 100).toFixed(1)} %`}
                >
                  <span className="w-24 font-mono text-[9px] truncate text-right">{backend}</span>
                  <div className="flex-1 h-[5px] rounded-sm bg-bg/40 overflow-hidden">
                    <div
                      className="h-full rounded-sm"
                      style={{ width: `${pct}%`, backgroundColor: werColor(wer) }}
                    />
                  </div>
                  <span className="w-8 text-right text-[9px] tabular-nums">{(wer * 100).toFixed(1)}%</span>
                </div>
              );
            })}
          </div>
        </div>
      )}

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
    <div className="overflow-hidden">
      {/* Change 039: immer ohne Scrollbar — table-fixed skaliert die Zellen
          auf die verfügbare Breite, sehr kleine Schrift, Header truncated. */}
      <table className="w-full table-fixed text-[10px] border-collapse">
        <thead>
          <tr>
            <th className="py-0.5 pr-1 text-left text-dim font-normal w-24 align-bottom">
              Kanal ↓ · Inhalt →
            </th>
            {inhaltKeys.map((ik) => (
              <th key={ik} className="py-0.5 px-0.5 text-center font-medium overflow-hidden">
                <span className="block truncate" title={axes.inhalt.kategorien[ik].name}>
                  {axes.inhalt.kategorien[ik].name}
                </span>
              </th>
            ))}
            <th className="py-0.5 px-0.5 text-center font-medium w-7">Σ</th>
          </tr>
        </thead>
        <tbody>
          {kanalKeys.map((kk) => (
            <tr key={kk}>
              <td className="py-0.5 pr-1 overflow-hidden">
                <span className="block truncate font-medium" title={axes.kanal.kategorien[kk].name}>
                  {axes.kanal.kategorien[kk].name}
                </span>
                <span className="text-dim text-[9px] block truncate">{kk}</span>
              </td>
              {inhaltKeys.map((ik) => {
                const n = meta.matrix?.[kk]?.[ik] ?? 0;
                const isActive = active?.kanal === kk && active?.inhalt === ik;
                return (
                  <td key={ik} className="py-0.5 px-0.5 text-center">
                    <button
                      onClick={() => onSelect(isActive ? null : { kanal: kk, inhalt: ik })}
                      disabled={n === 0}
                      className={[
                        "w-full px-0.5 py-0.5 rounded text-[10px] leading-none",
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
              <td className="py-0.5 px-0.5 text-center text-dim">
                {inhaltKeys.reduce((acc, ik) => acc + (meta.matrix?.[kk]?.[ik] ?? 0), 0)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="text-xs text-dim mt-1">
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
// Change 040: grafische Darstellung — CSS-Balken statt Mini-Tabelle.
// Balkenbreite = relative Qualität (bestes Modell = volle Breite),
// Farbe = WER-Skala (grün = gut … rot = schlecht). Kategorie-Grafiken
// sind durch ▦-Icon + violette Akzente klar von Sample-Grafiken (▤, grün)
// unterscheidbar.

function werColor(wer: number): string {
  // WER 0 → grün (120°), WER ≥ 0.6 → rot (0°)
  const t = Math.min(Math.max(wer, 0), 0.6) / 0.6;
  return `hsl(${Math.round(120 * (1 - t))} 70% 45%)`;
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
  const best = sorted[0].wer || 0.0001; // bestes Modell = volle Balkenbreite
  return (
    <div className="px-3 py-2 border-b border-border/40" data-testid={`cat-quality-${categoryId}`}>
      <div className="flex items-center gap-1 text-[9px] text-violet-300 uppercase tracking-wide mb-1">
        <span aria-hidden>▦</span>
        <span>Kategorie · {categoryName}</span>
      </div>
      <div className="space-y-1">
        {sorted.map((r) => {
          const pct = Math.max(4, Math.round((r.wer / best) * 100));
          return (
            <div
              key={r.backend}
              data-testid={`cat-bar-${categoryId}-${r.backend}`}
              className="flex items-center gap-1.5"
              title={`${r.backend}: WER ${(r.wer * 100).toFixed(1)} % (${r.n} Samples)`}
            >
              <span className="w-24 font-mono text-[9px] truncate text-right">{r.backend}</span>
              <div className="flex-1 h-[5px] rounded-sm bg-bg/40 overflow-hidden">
                <div
                  className="h-full rounded-sm"
                  style={{ width: `${pct}%`, backgroundColor: werColor(r.wer) }}
                />
              </div>
              <span className="w-8 text-right text-[9px] tabular-nums">{(r.wer * 100).toFixed(1)}%</span>
              <span className="w-5 text-right text-[9px] text-dim">({r.n})</span>
            </div>
          );
        })}
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
  models, hiddenModels, onToggle, onToggleAll,
}: {
  models: string[];
  hiddenModels: ReadonlySet<string>;
  onToggle: (backend: string) => void;
  onToggleAll: () => void;
}) {
  if (models.length === 0) return null;
  const chipCls = (active: boolean) =>
    [
      "px-2.5 py-1 rounded-full text-xs font-medium border transition-colors",
      active
        ? "bg-[rgba(139,92,246,.25)] border-accent text-txt"
        : "bg-transparent border-border text-dim hover:text-txt",
    ].join(" ");
  // Change 040: „Alle" ist ein Toggle — ist alles sichtbar, blendet ein
  // Klick alle Modelle aus; sonst zeigt er alle wieder an.
  const allActive = hiddenModels.size === 0;
  return (
    <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Modell-Filter">
      <span className="text-sm text-dim">Modelle:</span>
      <button
        onClick={onToggleAll}
        data-active={allActive ? "true" : "false"}
        data-testid="model-chip-alle"
        className={chipCls(allActive)}
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

  // Change 040: „Alle" toggelt — alles sichtbar → alle ausblenden; sonst → alle zeigen.
  const toggleAllModels = () => {
    if (hiddenModels.size === 0) setHiddenModels(new Set(modelList));
    else setHiddenModels(new Set());
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
  // Change 039: nur Kategorien mit > 0 Samples anzeigen (Filter wirkt)
  const cats = meta.categories
    .map((c) => ({
      cat: c,
      samples: grouped.get(c.id) ?? [],
    }))
    .filter(({ samples: ss }) => ss.length > 0);

  // Change 039: Qualität je Kategorie (per_category) als Map für die
  // Kategorie-Blöcke + per_sample für die Sample-Mini-Tabellen.
  const qualityByCat = new Map<string, Array<{ backend: string; wer: number; n: number }>>();
  for (const r of results?.per_category ?? []) {
    const arr = qualityByCat.get(r.category) ?? [];
    arr.push({ backend: r.backend, wer: r.wer, n: r.n });
    qualityByCat.set(r.category, arr);
  }
  const perSample = results?.per_sample ?? {};

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
            onToggleAll={toggleAllModels}
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

      {/* REQ-BEN-047/Change 039: Modellqualität je Kategorie jetzt als Teil
          der Kategorie-Blöcke unten (sehr kleine Tabellen) — keine separate
          Sektion mehr. Nur Kategorien mit > 0 Samples (Filter wirkt). */}

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
        {cats.map(({ cat, samples: ss }) => (
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
            qualityRows={qualityByCat.get(cat.id) ?? []}
            perSample={perSample}
            hiddenModels={hiddenModels}
          />
        ))}
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
