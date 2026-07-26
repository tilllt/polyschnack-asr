import { useState, useMemo } from "react";
import type { Segment } from "../api";
import { updateSegment } from "../api";

interface Props {
  segments: Segment[];
  recordingId: string;
  onEdited: (segs: Segment[], text: string) => void;
}

export function SegmentSearch({ segments, recordingId, onEdited }: Props) {
  const [query, setQuery] = useState("");
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

  async function doReplace(one: boolean) {
    if (!query || saving) return;
    setSaving(true);
    try {
      const changed: Segment[] = segments.map((s) => ({ ...s }));
      for (let i = 0; i < changed.length; i++) {
        const oldText = changed[i].text;
        if (one) {
          const idx = oldText.search(new RegExp(query, "i"));
          if (idx !== -1) {
            changed[i] = { ...changed[i], text: oldText.replace(new RegExp(query, "i"), replace) };
            await updateSegment(recordingId, i, changed[i].text);
            break;
          }
        } else {
          const replaced = oldText.replace(new RegExp(query, "gi"), replace);
          if (replaced !== oldText) {
            changed[i] = { ...changed[i], text: replaced };
            await updateSegment(recordingId, i, replaced);
          }
        }
      }
      const totalText = changed.map((s) => s.text).join(" ");
      onEdited(changed, totalText);
    } catch {
      // keep state on error
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="border border-border rounded-sm bg-panel2 px-3 py-2 mb-3 space-y-2">
      <div className="flex items-center gap-2">
        <span className="text-muted2 text-[12px]">🔍</span>
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search…"
          className="flex-1 bg-panel border border-border rounded-sm px-2 py-1 text-[13px] outline-none focus:border-accent"
        />
        {results && (
          <span className="text-[12px] text-muted2 tabular-nums whitespace-nowrap">
            {results.total} ×
          </span>
        )}
      </div>
      {query && (
        <div className="flex items-center gap-2">
          <span className="text-muted2 text-[12px]">✏️</span>
          <input
            value={replace}
            onChange={(e) => setReplace(e.target.value)}
            placeholder="Replace…"
            className="flex-1 bg-panel border border-border rounded-sm px-2 py-1 text-[13px] outline-none focus:border-accent"
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
