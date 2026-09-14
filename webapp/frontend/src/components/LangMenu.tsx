/**
 * Change 192: Sprachwahl als Flaggen-Dropdown (statt nativem <select>).
 *
 * Die aktuelle Sprache wird als Flagge gezeigt; ein Klick öffnet die Liste.
 * Schließt per Klick außerhalb und Escape (useDismiss, Change 058).
 * Flaggen in einem nativen <select> werden je nach Plattform nicht gerendert —
 * deshalb ein eigenes Dropdown im dunklen Design des Projekts.
 */
import { useRef, useState } from "react";

import { useDismiss } from "../useDismiss";
import { useT, type Lang } from "../useLocale";

const LANGS: { code: Lang; flag: string; label: string }[] = [
  { code: "de", flag: "🇩🇪", label: "Deutsch" },
  { code: "en", flag: "🇬🇧", label: "English" },
  { code: "pt-BR", flag: "🇧🇷", label: "Português" },
];

export function LangMenu() {
  const { t, lang, setLang } = useT();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useDismiss(ref, open, () => setOpen(false));

  const current = LANGS.find((l) => l.code === lang) ?? LANGS[1];

  return (
    <div className="relative flex-shrink-0" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={t("language")}
        title={t("language")}
        className="text-[15px] leading-none px-2 py-1 rounded-sm border border-border hover:bg-[rgba(255,255,255,.05)] transition-colors"
      >
        <span aria-hidden="true">{current.flag}</span>
      </button>
      {open && (
        <ul
          role="listbox"
          aria-label={t("language")}
          className="absolute left-0 top-full mt-1 z-[130] min-w-[160px] bg-panel border border-border2 rounded-sm shadow-lg py-1"
        >
          {LANGS.map((l) => (
            <li key={l.code}>
              <button
                type="button"
                role="option"
                aria-selected={l.code === lang}
                onClick={() => {
                  setLang(l.code);
                  setOpen(false);
                }}
                className={`w-full text-left px-3 py-[6px] text-[12.5px] flex items-center gap-2 hover:bg-accent/10 ${
                  l.code === lang ? "text-accent" : "text-txt"
                }`}
              >
                <span aria-hidden="true">{l.flag}</span>
                {l.label}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
