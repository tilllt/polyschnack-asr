// Benchmark-API-Wrapper + Pfad-Erkennung für die öffentliche /benchmark-Seite.

export interface BenchmarkCategory {
  id: string;
  name: string;
  description?: string;
}

export interface BenchmarkSample {
  id: string;
  category: string;
  text: string;
  accent?: string;
  age?: string;
  kanal?: string;
  inhalt?: string;
  quelle?: string;
  preview_url: string;
  audio_url: string;
}

export interface BenchmarkAxis {
  beschreibung: string;
  kategorien: Record<string, { name: string }>;
}

export interface BenchmarkMeta {
  version: number;
  created_at?: string;
  supersedes?: number | null;
  categories: BenchmarkCategory[];
  sample_count: number;
  per_category: Record<string, number>;
  axes?: { kanal: BenchmarkAxis; inhalt: BenchmarkAxis };
  matrix?: Record<string, Record<string, number>>;
  matrix_total?: number;
  methodology?: string;
  disclaimer?: string;
}

export interface BenchmarkSamplesResponse {
  version: number;
  samples: BenchmarkSample[];
}

export interface PriceRow {
  backend: string;
  group: "polyschnack" | "commercial";
  wer?: number | null;
  eur_per_min_selfhost?: number | null;
  eur_per_min_saas?: number | null;
  eur_per_min_commercial?: number | null;
}

export interface BenchmarkPricing {
  generated_at?: string;
  rows: PriceRow[];
}

export interface ResultRow {
  backend: string;
  settings?: string;
  sample_id?: string;
  category?: string;
  wer?: number | null;
  cer?: number | null;
  coverage_pct?: number | null;
  rtf?: number | null;
  eur_per_min?: number | null;
}

/** REQ-BEN-046: gepoolte Qualität je (Kategorie × Backend) aus latest.json. */
export interface BenchmarkPerCategoryRow {
  category: string;
  backend: string;
  wer: number;
  cer: number;
  n: number;
}

export interface BenchmarkResults {
  version?: number;
  run_id?: string;
  generated_at?: string;
  rows: ResultRow[];
  per_category?: BenchmarkPerCategoryRow[];
  /** Change 039: sample_id -> { backend: wer } für Sample-Mini-Tabellen. */
  per_sample?: Record<string, Record<string, number>>;
}

export function parseBenchmarkPath(path: string): boolean {
  const p = path.split("?")[0].replace(/\/+$/, "");
  return p === "/benchmark" || p.startsWith("/benchmark/");
}

async function checkOk(res: Response): Promise<Response> {
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res;
}

export async function fetchBenchmarkMeta(): Promise<BenchmarkMeta> {
  return fetch("/api/benchmark/meta").then(checkOk).then((r) => r.json());
}

export async function fetchBenchmarkSamples(): Promise<BenchmarkSamplesResponse> {
  return fetch("/api/benchmark/samples").then(checkOk).then((r) => r.json());
}

export async function fetchBenchmarkResults(): Promise<BenchmarkResults | null> {
  const res = await fetch("/api/benchmark/results");
  if (res.status === 404) return null;
  return checkOk(res).then((r) => r.json());
}

export async function fetchBenchmarkPricing(): Promise<BenchmarkPricing | null> {
  const res = await fetch("/api/benchmark/pricing");
  if (res.status === 404) return null;
  return checkOk(res).then((r) => r.json());
}

export async function fetchBenchmarkVersions(): Promise<{ versions: Array<{ version: number; created_at?: string; active: number; rejected: number }> } | null> {
  const res = await fetch("/api/benchmark/versions");
  if (res.status === 404) return null;
  return checkOk(res).then((r) => r.json());
}

export async function rejectBenchmarkSample(sampleId: string): Promise<{ new_version: number; replacement: string }> {
  return fetch(`/api/benchmark/samples/${encodeURIComponent(sampleId)}/reject`, {
    method: "POST",
  }).then(checkOk).then((r) => r.json());
}

export async function editBenchmarkSample(
  sampleId: string,
  fields: { text?: string; category?: string; accent?: string; age?: string; held_out?: boolean },
): Promise<{ ok: boolean; sample: BenchmarkSample }> {
  return fetch(`/api/benchmark/samples/${encodeURIComponent(sampleId)}/edit`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(fields),
  }).then(checkOk).then((r) => r.json());
}
