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

/** Change 062/065: gepoolte VAD-Ergebnisse (kind="vad" aus latest.json). */
export interface VadResultRow {
  backend: string;
  kind: "vad";
  /** Change 065: Testset-Version (z. B. "v4-public") + Release-Link. */
  testset_version?: string;
  testset_release_url?: string;
  n_samples: number;
  vad_f1_mean: number;
  boundary_start_ms_median: number;
  boundary_end_ms_median: number;
  fp_time_s: number;
  rtf_mean: number;
}

export interface BenchmarkResults {
  version?: number;
  run_id?: string;
  generated_at?: string;
  rows: ResultRow[];
  per_category?: BenchmarkPerCategoryRow[];
  /** Change 039: sample_id -> { backend: wer } für Sample-Mini-Tabellen. */
  per_sample?: Record<string, Record<string, number>>;
  /** Change 062: VAD-Modell-Ergebnisse (getrennt vom ASR-Pool). */
  vad?: VadResultRow[];
}

/** Change 073: VAD-Testset-Sample (öffentlich anhörbar auf der Benchmark-Seite). */
export interface VadSample {
  id: string;
  source: string;
  variant: string;
  split: string;
  /** true = Sample hat Ground-Truth-Sprachregionen (GT); FP-Samples nicht. */
  has_gt: boolean;
  preview_url: string;
  audio_url: string;
}

export interface VadSamplesResponse {
  samples: VadSample[];
  count: number;
}

/** Change 075: Status des Benchmark-Set-Auto-Updates (öffentlich, keine Secrets). */
export interface AvailableSet {
  version: number;
  tag: string;
  published_at?: string | null;
  zip_url?: string;
  zip_size?: number | null;
  sha_url?: string | null;
}

export interface BenchmarkSetStatus {
  mechanism: string;
  configured: boolean;
  /** Change 076: true = env-URL-Pinning aktiv (kein Discovery). */
  pinning_mode: boolean;
  repo: string;
  url: string;
  /** SHA256 nur als 8-Zeichen-Präfix (kein voller Hash nach außen). */
  sha_prefix: string;
  auto_install: boolean;
  current_version: number | null;
  installed_versions: number[];
  /** Change 076: verfügbare Releases aus dem Repo (gecacht). */
  available: AvailableSet[];
  last_error: string | null;
}

export interface SetInstallResponse {
  ok: boolean;
  skipped?: boolean;
  reason?: string;
  installed_version?: number | null;
  current_version?: number | null;
  sha256?: string;
  sample_count?: number;
  supersedes?: number | null;
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

/** Change 073: VAD-Testset-Samples (öffentliche Liste mit Audio-URLs). */
export async function fetchVadSamples(): Promise<VadSamplesResponse | null> {
  const res = await fetch("/api/benchmark/vadsamples");
  if (res.status === 404) return null;
  return checkOk(res).then((r) => r.json());
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

/** Change 075: Status des Set-Updaters (öffentlich). */
export async function fetchBenchmarkSetStatus(): Promise<BenchmarkSetStatus | null> {
  const res = await fetch("/api/benchmark/sets");
  if (res.status === 404) return null;
  return checkOk(res).then((r) => r.json());
}

/** Change 075: Benchmark-Set installieren (Admin). */
export async function installBenchmarkSet(
  url?: string,
  sha256?: string,
  repo?: string,
  version?: number,
): Promise<SetInstallResponse> {
  return fetch("/api/benchmark/sets/install", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      url: url ?? undefined,
      sha256: sha256 ?? undefined,
      repo: repo ?? undefined,
      version: version ?? undefined,
    }),
  }).then(checkOk).then((r) => r.json());
}
