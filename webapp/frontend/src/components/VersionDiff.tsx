import { useMemo } from "react";
import type { DiffModel, DiffRow, DiffWord } from "../versionDiff";
import { buildDiffModel } from "../versionDiff";

interface Props {
  /** Diff-Zeilen vom Backend: [{type: same|add|del, text}] */
  diff: { type: string; text: string }[];
  fromLabel?: string;
  toLabel?: string;
}

/** Ein einzelnes Inline-Wort mit Highlight (GitHub-Stil). */
function Word({ w }: { w: DiffWord }) {
  if (w.type === "same") return <>{w.text}</>;
  const cls =
    w.type === "add"
      ? "bg-green-500/25 text-green-100 rounded-[2px]"
      : "bg-red-500/25 text-red-100 rounded-[2px]";
  return <span className={cls}>{w.text}</span>;
}

function DiffCell({ row }: { row: DiffRow }) {
  const lineNo = (n: number | null) =>
    n === null ? (
      <span className="text-muted2/40 select-none"> </span>
    ) : (
      <span className="text-muted2/70 select-none tabular-nums">{n}</span>
    );

  if (row.skipped !== undefined) {
    return (
      <div className="flex text-[10px] text-muted2 italic px-1 py-[1px] bg-panel2/40">
        <span className="w-8 shrink-0" />
        <span>⋯ {row.skipped} unveränderte Zeilen ⋯</span>
      </div>
    );
  }

  if (row.type === "same") {
    return (
      <div className="flex text-[11px] leading-[1.45] px-1 py-[1px] text-muted whitespace-pre-wrap break-words">
        <span className="w-8 shrink-0 text-right pr-2">{lineNo(row.aLine)}</span>
        <span className="w-8 shrink-0 text-right pr-2">{lineNo(row.bLine)}</span>
        <span className="min-w-0 flex-1">{row.text}</span>
      </div>
    );
  }

  const isAdd = row.type === "add";
  return (
    <div
      className={`flex text-[11px] leading-[1.45] px-1 py-[1px] whitespace-pre-wrap break-words ${
        isAdd ? "bg-green-500/10 text-green-100" : "bg-red-500/10 text-red-100"
      }`}
    >
      <span className="w-8 shrink-0 text-right pr-2 select-none text-muted2/70 tabular-nums">
        {lineNo(row.aLine)}
      </span>
      <span className="w-8 shrink-0 text-right pr-2 select-none text-muted2/70 tabular-nums">
        {lineNo(row.bLine)}
      </span>
      <span className="w-4 shrink-0 select-none">{isAdd ? "+" : "−"}</span>
      <span className="min-w-0 flex-1">
        {row.words ? row.words.map((w, i) => <Word key={i} w={w} />) : row.text}
      </span>
    </div>
  );
}

/** GitHub-artige Diff-Ansicht für Transkript-Versionen. */
export function VersionDiff({ diff, fromLabel, toLabel }: Props) {
  const model: DiffModel = useMemo(
    () => buildDiffModel(diff as { type: "same" | "add" | "del"; text: string }[]),
    [diff],
  );

  return (
    <div className="rounded-sm overflow-hidden border border-border2">
      {/* Kopfzeile wie GitHub: „from → to“ + Statistik */}
      <div className="flex items-center justify-between gap-2 bg-panel2 border-b border-border2 px-2 py-1 text-[10px]">
        <span className="text-muted2 font-medium">
          {fromLabel !== undefined && toLabel !== undefined ? (
            <>
              <span className="text-txt font-semibold">{fromLabel}</span>
              <span className="text-muted2 mx-1">→</span>
              <span className="text-txt font-semibold">{toLabel}</span>
            </>
          ) : (
            <span className="text-txt font-semibold">{toLabel ?? ""}</span>
          )}
        </span>
        <span className="flex items-center gap-2 font-mono">
          <span className="text-green-400">+{model.stats.add}</span>
          <span className="text-red-400">−{model.stats.del}</span>
        </span>
      </div>

      {model.identical ? (
        <p className="text-[11px] text-muted2 px-2 py-2">✓ Keine Unterschiede</p>
      ) : (
        <div className="max-h-[320px] overflow-y-auto bg-panel3">
          {model.hunks.map((h, hi) => (
            <div key={hi}>
              {/* Hunk-Header wie GitHub: @@ -a,b +c,d @@ */}
              <div className="flex bg-[#0d1117] border-y border-border2/60 px-1 py-[1px] text-[10px] font-mono text-accent/80 select-none">
                <span className="w-8 shrink-0" />
                <span>@@ -{h.aStart} +{h.bStart} @@</span>
              </div>
              {h.rows.map((r, ri) => (
                <DiffCell key={ri} row={r} />
              ))}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
