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
                px-3 sm:px-6 py-2 sm:py-[10px]
              "
            >
              {/* Row 1: Logo · GPU/CPU-Icon ─── ml-auto ─── Credits(Desktop) · Username · Sprachwahl · Settings · Logout */}
              <div className="flex flex-wrap items-center gap-x-2 sm:gap-x-3 gap-y-1">
                <a
                  href="/"
                  title={t("home")}
                  aria-label={t("home")}
                  className="flex items-center gap-[6px] sm:gap-[10px] flex-shrink-0 no-underline"
                >
                  <img
                    src="/logo.svg"
                    alt="PolySchnack"
                    className="h-[24px] sm:h-[28px] w-auto rounded-[6px]"
                  />
                  <h1 className="text-[14px] sm:text-[16px] m-0 font-bold tracking-[-0.01em] brand-gradient">
                    PolySchnack
                  </h1>
                </a>

                {/* GPU/CPU-Icon (inline SVG) */}
                {modelStatusQuery.data?.asr_device && (
                  <span
                    className="inline-flex items-center"
                    title={`ASR inference: ${modelStatusQuery.data.asr_device}`}
                  >
                    {modelStatusQuery.data.asr_device === "cuda" ? (
                      <svg viewBox="0 0 122.88 104.91" className="h-[18px] w-[18px] fill-current text-accent" aria-label="GPU">
                        <path d="M32.05,19.59H90.83a11.71,11.71,0,0,1,9,2.76,11.73,11.73,0,0,1,3.76,9V72.52a11.78,11.78,0,0,1-3.77,9,11.77,11.77,0,0,1-9,3.76H32.05a11.76,11.76,0,0,1-9-3.77,11.7,11.7,0,0,1-3.76-9V32.39a11.75,11.75,0,0,1,3.76-9,11.69,11.69,0,0,1,9-3.75Zm-3,33.76-4.25,9.37H18.73l8.14-17.51L18.73,41.7h6.06l4.26,9.61Zm10.55,9.37H35.21l8.2-16.5-8.2-16.5h4.34l8.2,16.5-8.2,16.5Zm0,0,8.41-16.5L39.56,41.7Zm3.91-16.5,8.2,16.5h-4.11l-8.2-16.5,8.2-16.5h4.11Zm3.91,0,8.2,8.4,0,0,0,0,0,0h0l-8.2,8.11v-7.14l8.2-8.2v0l-8.2,8.2V41.7h0l8.26-8.26-8.21-.26v-7.89l8.22,8.22h0l8.19,8.19-8.19,8.19v-7.53l-8.2-8.2v0l8.2-8.21h0Zm17.27,0L70.82,52.1H66.7l8.2-16.5-8.2-16.5h4.11l8.2,16.5-8.2,16.5Zm-4.56,9.37-8.2-16.5,8.2-16.5h4.11l-8.2,16.5,8.2,16.5H70.58Zm11-9.38L73.76,62.72H68.6l8.2-17.51L68.6,27.7h5.16l8.2,17.5Z"/>
                        <rect x="79.4" y="10.35" width="3.86" height="11.89" rx="1.27"/>
                        <rect x="79.4" y="82.67" width="3.86" height="11.89" rx="1.27"/>
                        <rect x="68.57" y="10.35" width="3.86" height="11.89" rx="1.27"/>
                        <rect x="68.57" y="82.67" width="3.86" height="11.89" rx="1.27"/>
                      </svg>
                    ) : modelStatusQuery.data.asr_device === "cpu" ? (
                      <svg viewBox="0 0 122.88 122.88" className="h-[18px] w-[18px] fill-current text-[#eab308]" aria-label="CPU">
                        <rect x="30.2" y="30.2" width="62.48" height="62.48" rx="8" ry="8"/>
                        <path d="M48.62,10.35h4.99V26.79H48.62V10.35Zm10.47,0h5.08V26.79H59.09V10.35Zm10.56,0h5.08V26.79H69.65V10.35ZM48.62,96.09h4.99V112.53H48.62V96.09Zm10.47,0h5.08V112.53H59.09V96.09Zm10.56,0h5.08V112.53H69.65V96.09Z"/>
                        <rect x="50.12" y="41" width="22.64" height="26" rx="3"/>
                        <rect x="10.35" y="48.71" width="17.29" height="5" rx="1.27"/>
                        <rect x="95.24" y="48.71" width="17.29" height="5" rx="1.27"/>
                        <rect x="10.35" y="63.27" width="17.29" height="5" rx="1.27"/>
                        <rect x="95.24" y="63.27" width="17.29" height="5" rx="1.27"/>
                        <rect x="10.35" y="77.83" width="17.29" height="5" rx="1.27"/>
                        <rect x="95.24" y="77.83" width="17.29" height="5" rx="1.27"/>
                      </svg>
                    ) : null}
                  </span>
                )}

                {/* ml-auto: Rechte Gruppe */}
                <div className="flex items-center gap-2 ml-auto">
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
                      {/* Credits: nur auf Desktop sichtbar */}
                      {credits != null && (
                        <span
                          className="hidden sm:inline-flex items-center text-[12px] font-semibold text-[#eab308] gap-1 cursor-pointer"
                          title={t("credits_balance")}
                          onClick={() => setView("settings")}
                        >
                          💰 {formatCents(credits.credits_cents)}
                        </span>
                      )}
                      <span className="text-[12px] text-muted">{user.name}</span>
                      <LangMenu />
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

              {/* Row 2: Navigation — Transcribe · Benchmark · Admin */}
              <nav className="flex items-center gap-1 mt-1" aria-label="Hauptmenü">
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
                    className={`text-[11px] px-2 py-[3px] rounded-sm transition-colors ${
                      view === key
                        ? "bg-accent/20 text-accent"
                        : "text-muted hover:text-txt hover:bg-[rgba(255,255,255,.05)]"
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </nav>

              {/* Row 3: Stats — kleiner */}
              <div className="mt-[2px]">
                <StatsBar stats={stats} />
              </div>
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
