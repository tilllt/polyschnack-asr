import { useEffect, useRef, useState } from "react";
import { Search } from "lucide-react";
import { useT } from "../useLocale";

interface Props {
  value: string;
  onChange: (q: string) => void;
  count: number | null;
}

export function SearchBar({ value, onChange, count }: Props) {
  const [local, setLocal] = useState(value);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const { t } = useT();

  // Sync external reset (e.g. if parent clears)
  useEffect(() => {
    setLocal(value);
  }, [value]);

  function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
    const v = e.target.value;
    setLocal(v);
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      onChange(v.trim());
    }, 300);
  }

  return (
    <div className="mt-[22px] flex items-center gap-3 flex-wrap">
      {/* Search input */}
      <div className="relative flex-1 min-w-[200px]">
        <Search
          size={14}
          className="absolute left-[11px] top-1/2 -translate-y-1/2 text-muted2 pointer-events-none"
        />
        <input
          type="search"
          value={local}
          onChange={handleChange}
          placeholder={t("search_placeholder")}
          autoComplete="off"
          className="
            w-full bg-panel border border-border2 rounded-sm
            text-txt text-[14px] font-[inherit]
            py-[9px] pr-3 pl-[34px]
            outline-none transition-colors duration-150
            placeholder:text-muted2
            focus:border-accent
          "
        />
      </div>
      {/* Count */}
      {count !== null && count > 0 && (
        <span className="text-muted text-[13px] whitespace-nowrap flex-shrink-0">
          {count} {t("recordings")}
        </span>
      )}
    </div>
  );
}
