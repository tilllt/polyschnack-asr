import { useState, useMemo } from "react";
import type { Segment } from "../api";
import { fmtTimecode } from "../format";

interface Props {
  segments: Segment[];
  /** Review-Fix 2026-08-15: Such-Query + Navigation an die SegmentList
   *  durchreichen, damit Treffer hervorgehoben UND angesprungen werden. */
  query: string;
  onQueryChange: (q: string) => void;
  onNavigateHit: (segIdx: number) => void;
  /** Change 124: Ersetzen läuft über die SegmentList (kennt die Anzeige +
   *  den Yjs-Schreibpfad) — hier nur das Request weiterreichen. */
  onReplaceRequest?: (req: {
    one: boolean;
    query: string;
    replace: string;
  }) => void;
}

export function SegmentSearch({ segments, query, onQueryChange, onNavigateHit, onReplaceRequest }: Props) {
  const [replace, setReplace] = useState("");
  const [saving, setSaving] = useState(false);

  const results = useMemo(() => {
    if (!query) return null;
    const out: { segIdx: number; count: number }[] = [];
    let total = 0;
    for (let i = 0; i < segments.length; i++) {
      const c = (segments[i].text.match(new RegExp(query, "gi")) || []).length;
      if (c > 0) { out.push({ segIdx: i, count: c }); total += c; }
    }
    return { perSeg: out, total };
  }, [query, segments]);

  function doReplace(one: boolean) {
    if (!query || saving || !onReplaceRequest) return;
    setSaving(true);
    // Change 124: kein direktes updateSegment mehr — die SegmentList
    // schreibt über den kollaborationsfähigen Pfad (Yjs setSegmentText /
    // REST), damit die Anzeige die Änderung wirklich übernimmt.
    try {
      onReplaceRequest({ one, query, replace });
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="border border-border rounded-sm bg-panel2 px-3 py-2 mb-3 space-y-2 max-w-full">
      {/* Review-Fix 2026-08-15: flex-wrap — die Zeile lief auf schmalen
          Screens (Handy) aus dem Viewport. Zähler + Input brechen jetzt
          sauber um statt den Dialog breiter als den Screen zu ziehen. */}
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-muted2 text-[12px] flex-shrink-0">🔍</span>
        <input
          value={query}
          onChange={(e) => onQueryChange(e.target.value)}
          placeholder="Search…"
          className="flex-1 min-w-[120px] bg-panel border border-border rounded-sm px-2 py-1 text-[13px] outline-none focus:border-accent"
        />
        {results && (
          <span className="text-[12px] text-muted2 tabular-nums whitespace-nowrap flex-shrink-0">
            {results.total} ×
          </span>
        )}
      </div>
      {results && results.perSeg.length > 0 && (
        <div className="flex items-center gap-1.5 flex-wrap">
          {/* Treffer-Segmente: Klick springt zur Fundstelle (scrollt in der
              SegmentList) — Review-Fix 2026-08-15. */}
          {results.perSeg.map((h) => (
            <button
              key={h.segIdx}
              onClick={() => onNavigateHit(h.segIdx)}
              title={`${h.count} Treffer`}
              className="text-[11px] px-1.5 py-[2px] rounded-sm font-semibold tabular-nums
                         text-green-300 bg-green-500/10 border border-green-500/30
                         hover:bg-green-500/25 transition-colors whitespace-nowrap"
            >
              {fmtTimecode(segments[h.segIdx]?.start ?? 0)} · {h.count}
            </button>
          ))}
        </div>
      )}
      {query && (
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-muted2 text-[12px] flex-shrink-0">✏️</span>
          <input
            value={replace}
            onChange={(e) => setReplace(e.target.value)}
            placeholder="Replace…"
            className="flex-1 min-w-[120px] bg-panel border border-border rounded-sm px-2 py-1 text-[13px] outline-none focus:border-accent"
          />
          <button
            onClick={() => doReplace(true)}
            disabled={saving || !replace}
            className="btn-ghost-sm text-[12px]"
          >
            Replace
          </button>
          <button
            onClick={() => doReplace(false)}
            disabled={saving || !replace}
            className="btn-ghost-sm text-[12px]"
          >
            All
          </button>
        </div>
      )}
    </div>
  );
}
