import { useCallback, useEffect, useState } from "react";
import { useDebouncedValue, useRecordings, useStats, useModelStatus } from "./hooks";
import { toggleActivePlayback } from "./components/WaveformPlayer";
import { ToastProvider } from "./components/Toasts";
import { useT, LocaleProvider } from "./useLocale";
import { parseSharePath } from "./share";
import { parseBenchmarkPath } from "./benchmark";
import { nextSortState, sortParams, type SortState } from "./sortState";
import type { RecordingSort } from "./api";
import {
  fetchBenchmarkMeta,
  fetchBenchmarkSamples,
  fetchBenchmarkResults,
  fetchBenchmarkPricing,
  fetchVadSamples,
  fetchDiarSamples,
  rejectBenchmarkSample,
  editBenchmarkSample,
  type BenchmarkMeta,
  type BenchmarkSamplesResponse,
  type VadSamplesResponse,
  type DiarSamplesResponse,
  type BenchmarkResults,
  type BenchmarkPricing,
} from "./benchmark";
import { BenchmarkPageContent } from "./components/BenchmarkPage";
import { SharedRecordingView } from "./components/SharedRecordingView";
import { fetchMe, fetchMyCredits, formatCents, type UserInfo } from "./api";
import { StatsBar } from "./components/StatsBar";
import { UploadZone } from "./components/UploadZone";
import { QueueWatcher } from "./components/QueueWatcher";
import { LogIn, LogOut, Settings } from "lucide-react";

import { LangMenu } from "./components/LangMenu";
import { AdminPanel } from "./components/AdminPanel";
import { UserSettingsPage } from "./components/UserSettingsPage";
import { SearchBar } from "./components/SearchBar";
import { RecordingList } from "./components/RecordingList";
import { InstallBanner } from "./components/InstallBanner";

function AppContent() {
  const [query, setQuery] = useState("");
  const [user, setUser] = useState<UserInfo | null>(null);
  // Change 191: vier Ansichten in einem Top-Menü (Transkribieren ist Default).
  const [view, setView] = useState<"main" | "settings" | "benchmark" | "admin">("main");
  const { t } = useT();
  // Change 054: Sort-Badges (null = Default Date desc) + Tag-Filter (ODER).
  const [sort, setSort] = useState<SortState>(null);
  const [activeTags, setActiveTags] = useState<string[]>([]);

  // Anon-Share-Link: /r/:uid → read-only-Ansicht ohne Login
  const shareUid = parseSharePath(window.location.pathname)?.uid ?? null;

  // Benchmark-Seite: /benchmark → öffentliche BenchmarkPage
  const isBenchmark = parseBenchmarkPath(window.location.pathname);
  // Change 191: Benchmark ist zusätzlich ein Menüpunkt — der Pfad /benchmark
  // bleibt gültig (alte Links), die Ansicht schaltet derselbe Zustand.
  const showBenchmark = isBenchmark || view === "benchmark";
  const [benchMeta, setBenchMeta] = useState<BenchmarkMeta | null>(null);
  const [benchData, setBenchData] = useState<BenchmarkSamplesResponse | null>(null);
  const [benchResults, setBenchResults] = useState<BenchmarkResults | null>(null);
  const [benchPricing, setBenchPricing] = useState<BenchmarkPricing | null>(null);
  const [benchVad, setBenchVad] = useState<VadSamplesResponse | null>(null);
  const [benchDiar, setBenchDiar] = useState<DiarSamplesResponse | null>(null);
  const [benchTick, setBenchTick] = useState(0);

  useEffect(() => {
    if (!showBenchmark) return;
    fetchBenchmarkMeta().then(setBenchMeta).catch(() => setBenchMeta(null));
    fetchBenchmarkSamples().then(setBenchData).catch(() => setBenchData(null));
    fetchBenchmarkResults().then(setBenchResults).catch(() => setBenchResults(null));
    fetchBenchmarkPricing().then(setBenchPricing).catch(() => setBenchPricing(null));
    // Change 073: VAD-Testset-Samples (anhörbar) — eigener Fetch, 404 = kein Paket.
    fetchVadSamples().then(setBenchVad).catch(() => setBenchVad(null));
    // Change 136: Diar-Testset-Calls (anhörbar) — eigener Fetch, 404 = kein Paket.
    fetchDiarSamples().then(setBenchDiar).catch(() => setBenchDiar(null));
  }, [showBenchmark, benchTick]);

  const onBenchReject = async (sampleId: string) => {
    try {
      const res = await rejectBenchmarkSample(sampleId);
      alert(`Sample abgelehnt → neue Version v${res.new_version}, Ersatz: ${res.replacement}`);
      setBenchTick((n) => n + 1);
    } catch (e) {
      alert(`Ablehnen fehlgeschlagen: ${(e as Error).message}`);
    }
  };

  const onBenchEdit = async (sampleId: string, fields: { text: string }) => {
    try {
      await editBenchmarkSample(sampleId, fields);
      setBenchTick((n) => n + 1);
    } catch (e) {
      alert(`Edit fehlgeschlagen: ${(e as Error).message}`);
    }
  };

  useEffect(() => {
    fetchMe().then(setUser).catch(() => setUser({ anonymous: true }));
  }, []);

  // Change 086: Kontostand (virtuelle Credits) für eingeloggte User.
  const [credits, setCredits] = useState<{ credits_cents: number } | null>(null);
  useEffect(() => {
    if (user?.authenticated) {
      fetchMyCredits().then(setCredits).catch(() => setCredits(null));
    } else {
      setCredits(null);
    }
  }, [user?.authenticated]);

  // ── Globaler Play/Stop-Shortcut: Space (Feature 2026-08-16) ──
  // Läuft im CAPTURE-Modus: verhindert den Zeilen-Space-Seek und das
  // Button-Aktivieren. Greift NICHT, wenn ein Eingabefeld fokussiert ist
  // (Edit-Mode: Text-Edit, Sprecher-Rename, Suche, Formulare).
  useEffect(() => {
    function isEditableTarget(t: EventTarget | null): boolean {
      if (!(t instanceof HTMLElement)) return false;
      const tag = t.tagName;
      return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || t.isContentEditable;
    }
    function onKeyDown(e: KeyboardEvent) {
      if (e.code !== "Space" || e.repeat) return;
      if (isEditableTarget(e.target)) return;
      e.preventDefault();
      e.stopPropagation();
      toggleActivePlayback();
    }
    window.addEventListener("keydown", onKeyDown, true);
    return () => window.removeEventListener("keydown", onKeyDown, true);
  }, []);

  // Change 120: Debounce für Sort/Tag — schnelle Badge-Klicks bündeln die
  // Requests (Badge-State bleibt sofort, nur der Fetch wird gebündelt).
  const debouncedSort = useDebouncedValue(sort, 250);
  const debouncedTags = useDebouncedValue(activeTags, 250);

  const recordingsQuery = useRecordings(query, { ...sortParams(debouncedSort), tags: debouncedTags });
  const statsQuery = useStats();
  const modelStatusQuery = useModelStatus();

  const recordings = recordingsQuery.data ?? [];
  const stats = statsQuery.data;

  // Change 054: Badge-Klick-Zyklus (1. desc, 2. asc, 3. Default) + Tag-Toggle.
  const onSortBadge = useCallback((key: RecordingSort) => {
    setSort((cur) => nextSortState(cur, key));
  }, []);
  const onToggleTag = useCallback((tag: string) => {
    setActiveTags((cur) =>
      cur.includes(tag) ? cur.filter((x) => x !== tag) : [...cur, tag],
    );
  }, []);

  return (
    <div className="min-h-screen bg-bg">
      {/* ── Sticky header ── */}
      <header
        className="
          sticky top-0 z-[100]
          bg-[rgba(7,11,8,.92)] backdrop-blur-[12px]
          border-b border-border
          px-3 sm:px-6 py-3 sm:py-[14px]
        "
      >
        {/* Row 1: Logo · Menü · Sprache — Nutzerbereich (Guthaben/Name/Symbol) rechtsbündig */}
        <div className="flex flex-wrap items-center gap-x-2 sm:gap-x-4 gap-y-1 mb-2 sm:mb-0">
          <a
            href="/"
            title={t("home")}
            aria-label={t("home")}
            className="flex items-center gap-[6px] sm:gap-[10px] flex-shrink-0 no-underline order-1"
          >
            <img
              src="/logo.svg"
              alt="PolySchnack"
              className="h-[26px] sm:h-[30px] w-auto rounded-[6px]"
            />
            <h1 className="text-[15px] sm:text-[17px] m-0 font-bold tracking-[-0.01em] brand-gradient">
              PolySchnack
            </h1>
          </a>
          {/* GPU/CPU-Badge zwischen Logo-Text und Menü */}
          {modelStatusQuery.data?.asr_device && (
            <div
              className={[
                "inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-[3px] rounded-full order-2",
                modelStatusQuery.data.asr_device === "cuda"
                  ? "bg-[rgba(46,160,67,.15)] text-accent"
                  : modelStatusQuery.data.asr_device === "cpu"
                  ? "bg-[rgba(234,179,8,.12)] text-[#eab308]"
                  : "bg-[rgba(248,81,73,.1)] text-err",
              ].join(" ")}
              title={`ASR inference: ${modelStatusQuery.data.asr_device}`}
            >
              {modelStatusQuery.data.asr_device === "cuda" ? "⚡ GPU" : modelStatusQuery.data.asr_device === "cpu" ? "💻 CPU" : "❓"}
            </div>
          )}
          {/* Change 191: Top-Menü — Admin ist nur für Admins sichtbar. */}
          <nav className="flex flex-wrap items-center gap-1" aria-label="Hauptmenü">
            {([
              ["main", t("transcribe")],
              ["benchmark", t("benchmark")],
              ...(user?.is_admin ? [["admin", t("admin")] as const] : []),
            ] as const).map(([key, label]) => (
              <button
                key={key}
                type="button"
                onClick={() => setView(key as typeof view)}
                aria-current={view === key ? "page" : undefined}
                className={`text-[12px] px-2 py-1 rounded-sm transition-colors order-3 ${
                  view === key
                    ? "bg-accent/20 text-accent"
                    : "text-muted hover:text-txt hover:bg-[rgba(255,255,255,.05)]"
                }`}
              >
                {label}
              </button>
            ))}
          </nav>

          {/* Change 192: Sprachwahl als Flaggen-Dropdown, direkt neben dem Menü. */}
          <LangMenu />

          <div className="flex items-center gap-2 sm:gap-3 flex-shrink-0 ml-auto order-2">
            {/* Change 191: ein Symbol für An-/Abmelden, je nach Kontext. */}
            {user && user.oidc_enabled && !user.authenticated && (
              <a
                href="/auth/login"
                className="btn-ghost-sm text-[12px] inline-flex items-center"
                title={t("login")}
                aria-label={t("login")}
              >
                <LogIn size={14} />
              </a>
            )}
            {user?.authenticated && (
              <div className="flex items-center gap-2">
                <span className="text-[12px] text-muted">{user.name}</span>
                {credits != null && (
                  <button
                    className="btn-ghost-sm text-[12px]"
                    title={t("credits_balance")}
                    onClick={() => setView(view === "settings" ? "main" : "settings")}
                  >
                    💰 {formatCents(credits.credits_cents)}
                  </button>
                )}
                <button
                  className="btn-ghost-sm inline-flex items-center"
                  title={t("settings")}
                  aria-label={t("settings")}
                  onClick={() => setView(view === "settings" ? "main" : "settings")}
                >
                  <Settings size={14} />
                </button>
                <a
                  href="/auth/logout"
                  className="btn-ghost-sm text-[12px] inline-flex items-center"
                  title={t("logout")}
                  aria-label={t("logout")}
                >
                  <LogOut size={14} />
                </a>
              </div>
            )}
            {user?.anonymous && user.name && (
              <span
                className="text-[12px] text-muted truncate max-w-[70px] sm:max-w-[160px]"
                title={t("anon_link_hint")}
              >
                🎭 {user.name}
              </span>
            )}
          </div>
        </div>

        {/* Row 2: Stats — full width on mobile, inline on desktop */}
        <StatsBar stats={stats} />
      </header>

      {/* PWA-Install-Banner (nur wenn installierbar + nicht abgelehnt) */}
      <InstallBanner />

      {/* ── Main content ── */}
      <main className="max-w-[960px] mx-auto px-3 sm:px-5 py-4 sm:py-6 overflow-x-hidden">
        {showBenchmark ? (
          <BenchmarkPageContent
            meta={benchMeta}
            data={benchData}
            results={benchResults}
            pricing={benchPricing}
            vadSamples={benchVad}
            diarSamples={benchDiar}
            admin={!!user?.is_admin}
            onReject={onBenchReject}
            onEdit={onBenchEdit}
            onReload={() => setBenchTick((n) => n + 1)}
          />
        ) : shareUid ? (
          <SharedRecordingView uid={shareUid} />
        ) : view === "main" ? (
          <>
            <UploadZone user={user} />

            <QueueWatcher />

            <SearchBar
              value={query}
              onChange={setQuery}
              count={recordings.length > 0 ? recordings.length : null}
            />

            {recordingsQuery.isError && (
              <div className="mt-4 text-err text-[13px]">
                {t("error_loading")}{" "}
                {recordingsQuery.error?.message ?? t("unknown")}
              </div>
            )}

            <RecordingList
              recordings={recordings}
              query={query}
              isOidc={!!user?.authenticated}
              isAdmin={!!user?.is_admin}
              sort={sort}
              onSort={onSortBadge}
              activeTags={activeTags}
              onToggleTag={onToggleTag}
            />
          </>
        ) : view === "admin" && user?.is_admin ? (
          <AdminPanel />
        ) : (
          <UserSettingsPage user={user} />
        )}
      </main>
    </div>
  );
}

export default function App() {
  return (
    <LocaleProvider>
      <ToastProvider>
        <AppContent />
      </ToastProvider>
    </LocaleProvider>
  );
}
