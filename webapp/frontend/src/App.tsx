import { useEffect, useState } from "react";
import { useRecordings, useStats } from "./hooks";
import { ToastProvider } from "./components/Toasts";
import { LocaleProvider, useT, type Lang } from "./useLocale";
import { fetchMe, type UserInfo } from "./api";
import { StatsBar } from "./components/StatsBar";
import { UploadZone } from "./components/UploadZone";
import { SearchBar } from "./components/SearchBar";
import { RecordingList } from "./components/RecordingList";

function AppContent() {
  const [query, setQuery] = useState("");
  const [user, setUser] = useState<UserInfo | null>(null);
  const { t, lang, setLang } = useT();

  useEffect(() => {
    fetchMe().then(setUser).catch(() => setUser({ anonymous: true }));
  }, []);

  const recordingsQuery = useRecordings(query);
  const statsQuery = useStats();

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
        <div className="flex items-center justify-between gap-2 sm:gap-4 mb-2 sm:mb-0">
          <div className="flex items-center gap-[6px] sm:gap-[10px] flex-shrink-0">
            <span className="text-[18px] sm:text-[20px] leading-none">🦜</span>
            <h1 className="text-[15px] sm:text-[17px] m-0 font-bold tracking-[-0.01em] brand-gradient">
              PolySchnack
            </h1>
          </div>

          <div className="flex items-center gap-2 sm:gap-3 flex-shrink-0">
            {user && !user.anonymous && !user.authenticated && (
              <a href="/auth/login" className="btn-ghost-sm text-[12px]">
                Login
              </a>
            )}
            {user?.authenticated && (
              <div className="flex items-center gap-2">
                <span className="text-[12px] text-muted">{user.name}</span>
                <a href="/auth/logout" className="btn-ghost-sm text-[12px]">
                  Logout
                </a>
              </div>
            )}
            <select
              value={lang}
              onChange={(e) => setLang(e.target.value as Lang)}
              className="
                bg-panel border border-border2 rounded-sm
                text-[12px] text-txt px-2 py-1
                outline-none cursor-pointer
                focus:border-accent
              "
            >
              <option value="en">🇬🇧 English</option>
              <option value="de">🇩🇪 Deutsch</option>
              <option value="pt-BR">🇧🇷 Português</option>
            </select>
          </div>
        </div>

        {/* Row 2: Stats — full width on mobile, inline on desktop */}
        <StatsBar stats={stats} />
      </header>

      {/* ── Main content ── */}
      <main className="max-w-[960px] mx-auto px-3 sm:px-5 py-4 sm:py-6 overflow-x-hidden">
        <UploadZone />

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

        <RecordingList recordings={recordings} query={query} />
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
