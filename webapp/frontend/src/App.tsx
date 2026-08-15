import { useEffect, useState } from "react";
import { useRecordings, useStats, useModelStatus } from "./hooks";
import { ToastProvider } from "./components/Toasts";
import { useT, type Lang, LocaleProvider } from "./useLocale";
import { parseSharePath } from "./share";
import { parseBenchmarkPath } from "./benchmark";
import {
  fetchBenchmarkMeta,
  fetchBenchmarkSamples,
  fetchBenchmarkResults,
  fetchBenchmarkPricing,
  rejectBenchmarkSample,
  editBenchmarkSample,
  type BenchmarkMeta,
  type BenchmarkSamplesResponse,
  type BenchmarkResults,
  type BenchmarkPricing,
} from "./benchmark";
import { BenchmarkPageContent } from "./components/BenchmarkPage";
import { SharedRecordingView } from "./components/SharedRecordingView";
import { fetchMe, type UserInfo } from "./api";
import { StatsBar } from "./components/StatsBar";
import { UploadZone } from "./components/UploadZone";
import { QueueWatcher } from "./components/QueueWatcher";
import { AdminPanel } from "./components/AdminPanel";
import { UserSettingsPage } from "./components/UserSettingsPage";
import { SearchBar } from "./components/SearchBar";
import { RecordingList } from "./components/RecordingList";
import { InstallBanner } from "./components/InstallBanner";

function AppContent() {
  const [query, setQuery] = useState("");
  const [user, setUser] = useState<UserInfo | null>(null);
  const [view, setView] = useState<"main" | "settings">("main");
  const { t, lang, setLang } = useT();

  // Anon-Share-Link: /r/:uid → read-only-Ansicht ohne Login
  const shareUid = parseSharePath(window.location.pathname)?.uid ?? null;

  // Benchmark-Seite: /benchmark → öffentliche BenchmarkPage
  const isBenchmark = parseBenchmarkPath(window.location.pathname);
  const [benchMeta, setBenchMeta] = useState<BenchmarkMeta | null>(null);
  const [benchData, setBenchData] = useState<BenchmarkSamplesResponse | null>(null);
  const [benchResults, setBenchResults] = useState<BenchmarkResults | null>(null);
  const [benchPricing, setBenchPricing] = useState<BenchmarkPricing | null>(null);
  const [benchTick, setBenchTick] = useState(0);

  useEffect(() => {
    if (!isBenchmark) return;
    fetchBenchmarkMeta().then(setBenchMeta).catch(() => setBenchMeta(null));
    fetchBenchmarkSamples().then(setBenchData).catch(() => setBenchData(null));
    fetchBenchmarkResults().then(setBenchResults).catch(() => setBenchResults(null));
    fetchBenchmarkPricing().then(setBenchPricing).catch(() => setBenchPricing(null));
  }, [isBenchmark, benchTick]);

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

  const recordingsQuery = useRecordings(query);
  const statsQuery = useStats();
  const modelStatusQuery = useModelStatus();

  const recordings = recordingsQuery.data ?? [];
  const stats = statsQuery.data;

  return (
    <div className="min-h-screen bg-bg">
      {/* ── Sticky header ── */}
      <header
        className="
          sticky top-0 z-[100]
          bg-[rgba(12,14,20,.92)] backdrop-blur-[12px]
          border-b border-border
          px-3 sm:px-6 py-3 sm:py-[14px]
        "
      >
        {/* Row 1: Brand + Lang/Login */}
        <div className="flex flex-wrap items-center gap-x-2 sm:gap-x-4 gap-y-1 mb-2 sm:mb-0">
          <a
            href="/"
            title={t("home")}
            aria-label={t("home")}
            className="flex items-center gap-[6px] sm:gap-[10px] flex-shrink-0 no-underline"
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
            <a
              href="/benchmark"
              className={`text-[12px] px-2 py-1 rounded-sm transition-colors ${
                isBenchmark
                  ? "bg-accent/20 text-accent"
                  : "text-muted hover:text-txt hover:bg-[rgba(255,255,255,.05)]"
              }`}
            >
              Benchmark
            </a>

          <div className="flex items-center gap-2 sm:gap-3 flex-shrink-0 ml-auto">
            {user && user.oidc_enabled && !user.authenticated && (
              <a href="/auth/login" className="btn-ghost-sm text-[12px]">
                Login
              </a>
            )}
            {user?.authenticated && (
              <div className="flex items-center gap-2">
                <span className="text-[12px] text-muted">{user.name}</span>
                <button
                  className="btn-ghost-sm text-[12px]"
                  onClick={() => setView(view === "settings" ? "main" : "settings")}
                >
                  {view === "settings" ? "← " + t("back") : "⚙️ " + t("settings")}
                </button>
                <a href="/auth/logout" className="btn-ghost-sm text-[12px]">
                  Logout
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
            <select
              value={lang}
              onChange={(e) => setLang(e.target.value as Lang)}
              className="
                bg-panel border border-border2 rounded-sm
                text-[12px] text-txt px-2 py-1
                outline-none cursor-pointer
                focus:border-accent
                shrink-0
              "
            >
              <option value="en">🇬🇧 English</option>
              <option value="de">🇩🇪 Deutsch</option>
              <option value="pt-BR">🇧🇷 Português</option>
            </select>
          </div>
        </div>

        {/* Row 2: Stats — full width on mobile, inline on desktop */}
        <StatsBar stats={stats} device={modelStatusQuery.data?.asr_device} />
      </header>

      {/* PWA-Install-Banner (nur wenn installierbar + nicht abgelehnt) */}
      <InstallBanner />

      {/* ── Main content ── */}
      <main className="max-w-[960px] mx-auto px-3 sm:px-5 py-4 sm:py-6 overflow-x-hidden">
        {isBenchmark ? (
          <BenchmarkPageContent
            meta={benchMeta}
            data={benchData}
            results={benchResults}
            pricing={benchPricing}
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

            {user?.is_admin && <AdminPanel />}

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

            <RecordingList recordings={recordings} query={query} isOidc={!!user?.authenticated} isAdmin={!!user?.is_admin} />
          </>
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
