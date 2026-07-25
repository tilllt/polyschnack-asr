import { useState } from "react";
import { useRecordings, useStats } from "./hooks";
import { ToastProvider } from "./components/Toasts";
import { LocaleProvider, useT, type Lang } from "./useLocale";
import { StatsBar } from "./components/StatsBar";
import { UploadZone } from "./components/UploadZone";
import { SearchBar } from "./components/SearchBar";
import { RecordingList } from "./components/RecordingList";

function AppContent() {
  const [query, setQuery] = useState("");
  const { t, lang, setLang } = useT();

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
          px-6 py-[14px]
          flex items-center gap-4 flex-wrap
        "
      >
        {/* Brand */}
        <div className="flex items-center gap-[10px] flex-shrink-0">
          <span className="text-[20px] leading-none">🦜</span>
          <h1 className="text-[17px] m-0 font-bold tracking-[-0.01em] brand-gradient">
            Parakeet ASR
          </h1>
        </div>

        {/* Language switcher + Stats */}
        <div className="flex items-center gap-3 flex-shrink-0">
          <button
            onClick={() => {
              const langs: Array<Lang> = ["de", "en", "pt-BR"];
              const idx = langs.indexOf(lang);
              setLang(langs[(idx + 1) % langs.length]);
            }}
            className="btn-ghost-sm text-[12px] px-2"
            title={
              lang === "de" ? "Switch to English" :
              lang === "en" ? "Mudar para português" :
              "Zu Deutsch wechseln"
            }
          >
            {lang === "de" ? "🇬🇧 EN" :
             lang === "en" ? "🇧🇷 PT" :
             "🇩🇪 DE"}
          </button>
          <StatsBar stats={stats} />
        </div>
      </header>

      {/* ── Main content ── */}
      <main className="max-w-[960px] mx-auto px-5 py-6">
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
