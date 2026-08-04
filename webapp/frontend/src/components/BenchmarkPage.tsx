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

// ── Preisvergleich ────────────────────────────────────────────────────────

export function PriceComparison({ pricing }: { pricing: BenchmarkPricing | null }) {
  if (!pricing || !pricing.rows?.length) {
    return <p className="text-sm text-dim">Noch kein Preisvergleich verfügbar.</p>;
  }
  const sorted = [...pricing.rows].sort((a, b) =>
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

export function ResultsTable({ results }: { results: BenchmarkResults | null }) {
  if (!results || !results.rows?.length) {
    return <p className="text-sm text-dim">Noch keine Benchmark-Ergebnisse.</p>;
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
          {results.rows.map((r, i) => (
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

  if (!meta || !data) {
    return (
      <div className="max-w-5xl mx-auto px-4 py-8">
        <h1 className="text-2xl font-bold mb-4">PolySchnack Benchmark</h1>
        <p className="text-dim">Benchmark-Daten sind noch nicht verfügbar.</p>
      </div>
    );
  }

  const grouped = new Map<string, BenchmarkSample[]>();
  for (const s of data.samples) {
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

      {/* Methodik */}
      <section className="border border-border rounded-lg p-4">
        <h2 className="font-semibold mb-1">Methodik</h2>
        <p className="text-sm text-dim">{meta.methodology}</p>
        <p className="text-sm text-dim mt-1">{meta.disclaimer}</p>
      </section>

      {/* Samples nach Kategorie (collapsible) */}
      <section className="space-y-2">
        <h2 className="font-semibold">Samples</h2>
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
          />
        ))}
      </section>

      {/* Ergebnisse */}
      <section className="border border-border rounded-lg p-4">
        <h2 className="font-semibold mb-2">Ergebnisse</h2>
        <ResultsTable results={results} />
      </section>

      {/* Preisvergleich */}
      <section className="border border-border rounded-lg p-4">
        <h2 className="font-semibold mb-2">Preisvergleich</h2>
        <PriceComparison pricing={pricing} />
      </section>
    </div>
  );
}
