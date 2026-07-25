# Bidirectional WaveSurfer ↔ Transcript Sync + Double-Click Segment Editing

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Remove the hidden `<audio>` element so WaveSurfer is the sole playback engine (pause actually stops audio). Clicking a transcript segment only highlights it (no seek/play). The active segment highlights as WaveSurfer plays. Double-click a segment's text to edit it inline.

**Architecture:** WaveSurfer becomes the single playback engine. The hidden `<audio>` and its `audioRef` are deleted. `onTimeUpdate` from WaveSurfer drives the active segment highlight. Segment click = highlight only. Double-click = enter edit mode (textarea).

**Tech Stack:** React 18, WaveSurfer.js 7, FastAPI (backend)

> **⚠️ Known issue:** For audio >30min, `minPxPerSec: 10` creates a 54,000px waveform that WaveSurfer cannot render. Task 1 adds a fix: set `minPxPerSec` based on duration, cap at 800px visible width.

---
## Task 1: Expose WaveSurfer API via imperative ref + remove hidden `<audio>`

**Objective:** WaveformPlayer exposes `seekTo(seconds)` and `getCurrentTime()` so RecordingCard can use WaveSurfer as the sole playback engine. Add `onTimeUpdate` and `onPlayStateChange` props.

**Files:**
- Modify: `webapp/frontend/src/components/WaveformPlayer.tsx`

**Step 1:** Add `React.forwardRef`, `useImperativeHandle`, dynamic waveform zoom for long audio, and zoom control buttons:

```tsx
import React, { useEffect, useRef, useState, useCallback, useImperativeHandle } from "react";
import WaveSurfer from "wavesurfer.js";
import RegionsPlugin from "wavesurfer.js/dist/plugins/regions.js";

export interface WaveSurferHandle {
  seekTo: (seconds: number) => void;
  playPause: () => void;
  getCurrentTime: () => number;
  isPlaying: () => boolean;
}

interface Props {
  audioUrl: string;
  onRegionChange?: (start: number, end: number) => void;
  onTimeUpdate?: (time: number) => void;
  onPlayStateChange?: (playing: boolean) => void;
  height?: number;
}

const ZOOM_STEPS = [1, 2, 4, 6, 10, 20, 50];
const DEFAULT_ZOOM_IDX = 0; // start fully zoomed-out

export const WaveformPlayer = React.forwardRef<WaveSurferHandle, Props>(
  function WaveformPlayer({ audioUrl, onRegionChange, onTimeUpdate, onPlayStateChange, height = 80 }, ref) {
    const containerRef = useRef<HTMLDivElement>(null);
    const wsRef = useRef<WaveSurfer | null>(null);
    const regionsRef = useRef<RegionsPlugin | null>(null);
    const [ready, setReady] = useState(false);
    const [currentTime, setCurrentTime] = useState(0);
    const [duration, setDuration] = useState(0);
    const [zoomIdx, setZoomIdx] = useState(DEFAULT_ZOOM_IDX);
    const [playing, setPlaying] = useState(false);

    const doZoom = useCallback((ws: WaveSurfer, idx: number) => {
      const pps = ZOOM_STEPS[idx];
      ws.zoom(pps);
      setZoomIdx(idx);
    }, []);

    useEffect(() => {
      if (!containerRef.current) return;
      const regions = RegionsPlugin.create();
      const ws = WaveSurfer.create({
        container: containerRef.current,
        waveColor: "rgba(91,140,255,0.3)",
        progressColor: "rgba(91,140,255,0.8)",
        cursorColor: "#3b82f6",
        cursorWidth: 1,
        barWidth: 2,
        barGap: 1,
        barRadius: 2,
        height,
        normalize: true,
        minPxPerSec: 1,
        plugins: [regions],
      });

      ws.load(audioUrl);

      ws.on("ready", () => {
        setReady(true);
        setDuration(ws.getDuration());
        // Initial zoom = fit container width
        const dur = ws.getDuration();
        const containerW = containerRef.current?.clientWidth ?? 800;
        const fitPps = Math.max(1, Math.round(containerW / dur));
        // Find closest zoom step
        let zi = 0;
        for (let i = 0; i < ZOOM_STEPS.length; i++) {
          if (ZOOM_STEPS[i] <= fitPps) zi = i;
        }
        doZoom(ws, zi);

        regions.addRegion({
          start: 0,
          end: dur,
          color: "rgba(91,140,255,0.08)",
          drag: true,
          resize: true,
        });
      });

      ws.on("timeupdate", (t) => { setCurrentTime(t); onTimeUpdate?.(t); });
      ws.on("play", () => { setPlaying(true); onPlayStateChange?.(true); });
      ws.on("pause", () => { setPlaying(false); onPlayStateChange?.(false); });
      ws.on("finish", () => { setPlaying(false); onPlayStateChange?.(false); });

      regions.on("region-updated", (r) => onRegionChange?.(r.start, r.end));

      wsRef.current = ws;
      regionsRef.current = regions;
      return () => { ws.destroy(); };
    }, [audioUrl]);

    useImperativeHandle(ref, () => ({
      seekTo: (s: number) => { wsRef.current?.setTime(s); wsRef.current?.play(); },
      playPause: () => wsRef.current?.playPause(),
      getCurrentTime: () => wsRef.current?.getCurrentTime() ?? 0,
      isPlaying: () => wsRef.current?.isPlaying() ?? false,
    }), []);

    return (
      <div className="w-full">
        <div ref={containerRef} className="w-full" />
        {ready && (
          <div className="flex items-center gap-3 mt-2">
            <button
              onClick={() => wsRef.current?.playPause()}
              className="btn-ghost-sm text-[13px] flex items-center gap-1"
              title={playing ? "Pause" : "Play"}
            >
              {playing ? "⏸" : "▶"}
            </button>
            <span className="text-[12px] text-muted2 tabular-nums">
              {fmtTime(currentTime)} / {fmtTime(duration)}
            </span>
            <span className="flex-1" />
            {/* Zoom controls */}
            <button
              onClick={() => { const w = wsRef.current; if (w) doZoom(w, Math.max(0, zoomIdx - 1)); }}
              disabled={zoomIdx <= 0}
              className="btn-ghost-sm text-[13px] px-1"
              title="Zoom out"
            >−</button>
            <span className="text-[11px] text-muted2 tabular-nums min-w-[36px] text-center">
              {ZOOM_STEPS[zoomIdx]}×
            </span>
            <button
              onClick={() => { const w = wsRef.current; if (w) doZoom(w, Math.min(ZOOM_STEPS.length - 1, zoomIdx + 1)); }}
              disabled={zoomIdx >= ZOOM_STEPS.length - 1}
              className="btn-ghost-sm text-[13px] px-1"
              title="Zoom in"
            >+</button>
          </div>
        )}
      </div>
    );
  }
);
```

**Step 2:** Commit.

```bash
git add webapp/frontend/src/components/WaveformPlayer.tsx
git commit -m "refactor: expose WaveSurfer via ref, add onTimeUpdate/onPlayStateChange"
```

---
## Task 2: Update RecordingCard — remove hidden `<audio>`, use WaveSurfer for segment tracking

**Objective:** Delete the `<audio>` element and `audioRef`. Use `wsRef` and `onTimeUpdate` for active segment tracking. Segment click triggers `wsRef.current.seekTo(time)` which seeks AND plays via WaveSurfer (the play/pause button updates automatically).

**Files:**
- Modify: `webapp/frontend/src/components/RecordingCard.tsx`

**Step 1:** Replace `audioRef` with `wsRef`:

```tsx
// Remove: const audioRef = useRef<HTMLAudioElement>(null);
import { WaveformPlayer, type WaveSurferHandle } from "./WaveformPlayer";
// Add:
const wsRef = useRef<WaveSurferHandle>(null);
```

**Step 2:** Pass `onTimeUpdate` that drives the active segment:

```tsx
const handleTimeUpdate = useCallback((t: number) => {
  if (!hasSegments || !segments) return;
  let idx = -1;
  for (let i = 0; i < segments.length; i++) {
    if (t >= segments[i].start && t < segments[i].end) { idx = i; break; }
  }
  if (idx === -1 && t >= (segments[segments.length - 1]?.start ?? 0)) {
    idx = segments.length - 1;
  }
  setActiveSegIdx((prev) => (prev === idx ? prev : idx));
}, [hasSegments, segments]);
```

**Step 3:** Remove the `useEffect` that attaches `timeupdate` listener to audio (no longer needed).

**Step 4:** Update the JSX — remove `<audio>` element, pass `onTimeUpdate`:

```tsx
<WaveformPlayer
  ref={wsRef}
  audioUrl={r.audio_url}
  onTimeUpdate={handleTimeUpdate}
  onRegionChange={(s, e) => setCropRange({ start: s, end: e })}
/>
{/* Delete: <audio ref={audioRef} preload="none" src={r.audio_url} className="hidden" /> */}
```

**Step 5:** Remove `audioRef` from SegmentList props:

```tsx
<SegmentList
  segments={segments}
  activeIdx={activeSegIdx}
  onActiveChange={setActiveSegIdx}
  // no audioRef prop
/>
```

**Step 6:** Update SegmentList's `seekTo` — remove auto-play:

```tsx
// In SegmentList.tsx:
function seekTo(idx: number) {
  // Remove everything — segment click is highlight-only
  onActiveChange(idx);
}
```

**Step 7:** Commit.

```bash
git add webapp/frontend/src/components/RecordingCard.tsx webapp/frontend/src/components/SegmentList.tsx
git commit -m "refactor: remove hidden audio, segment click = highlight only, WaveSurfer is sole engine"
```

---
## Task 3: Update SegmentList — remove audioRef, highlight-only click, double-click edit

**Objective:** Segment click = highlight only (no seek/play). Double-click on text = inline edit mode.

**Files:**
- Modify: `webapp/frontend/src/components/SegmentList.tsx`
- Modify: `webapp/frontend/src/api.ts`

**Step 1:** Clean up SegmentList props — remove `audioRef`:

```tsx
interface Props {
  segments: Segment[];
  activeIdx: number;
  onActiveChange: (idx: number) => void;
  recordingId: number;
  onEdited?: (segments: Segment[], text: string) => void;
}
```

**Step 2:** Replace `seekTo` with `highlightOnly`:

```tsx
function handleClick(idx: number) {
  onActiveChange(idx);  // just highlight, no seek/play
}
```

**Step 3:** Add double-click edit state:

```tsx
const [editingIdx, setEditingIdx] = useState<number | null>(null);
const [editText, setEditText] = useState("");
const [saving, setSaving] = useState(false);
```

**Step 4:** Add double-click handler:

```tsx
onDoubleClick={(e) => {
  if (!recordingId) return;
  setEditingIdx(i);
  setEditText(seg.text);
  e.stopPropagation();
}}
```

**Step 5:** Add edit UI (textarea replaces text on double-click):

```tsx
{editingIdx === i ? (
  <textarea
    className="flex-1 min-w-0 bg-panel2 border border-border rounded-sm px-2 py-1 text-[13px] resize-y"
    value={editText}
    onChange={(e) => setEditText(e.target.value)}
    onKeyDown={async (e) => {
      if (e.key === "Escape") { setEditingIdx(null); return; }
      if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        await handleSave(i);
      }
    }}
    onBlur={() => handleSave(i)}
    autoFocus
  />
) : (
  <span className="text-txt flex-1 min-w-0">{seg.text}</span>
)}
```

**Step 6:** Add `handleSave`:

```tsx
async function handleSave(idx: number) {
  if (saving || !recordingId || !onEdited) return;
  setSaving(true);
  try {
    const result = await updateSegment(recordingId, idx, editText);
    onEdited(result.segments, result.text);
    setEditingIdx(null);
  } catch {
    // keep the edit open on error
  } finally {
    setSaving(false);
  }
}
```

**Step 7:** Add `updateSegment` to api.ts:

```tsx
export async function updateSegment(recordingId: number, segmentIdx: number, text: string):
  Promise<{ segments: Segment[]; text: string }> {
  const res = await fetch(`/api/recordings/${recordingId}/segments/${segmentIdx}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  }).then(checkOk);
  return res.json();
}
```

**Step 8:** Commit.

```bash
git add webapp/frontend/src/components/SegmentList.tsx webapp/frontend/src/api.ts
git commit -m "feat: segment click = highlight only, double-click = inline edit"
```

---
## Task 4: Add backend endpoint `PATCH /api/recordings/{rid}/segments/{idx}`

**Objective:** Allow editing a specific segment's text in the JSON `segments` column.

**Files:**
- Add route: `webapp/app/routers/segments.py`
- Modify: `webapp/app/main.py`

**Step 1:** Create `segments.py`:

```python
\"\"\"PATCH endpoint for inline segment text editing.\"\"\"
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import Session

from ..config import settings
from ..crud import get_recording
from ..db import get_session

router = APIRouter(prefix="/api")


class SegmentUpdate(BaseModel):
    text: str


@router.patch("/recordings/{rid}/segments/{idx}")
def update_segment(
    rid: int,
    idx: int,
    body: SegmentUpdate,
    request: Request = None,
    session: Session = Depends(get_session),
):
    \"\"\"Update the text of a single segment.\"\"\"
    rec = get_recording(session, rid)
    if rec is None:
        raise HTTPException(status_code=404, detail="not found")

    uid = request.session.get("user_id") if settings.OIDC_ENABLED else None
    if uid is not None and rec.user_id != uid:
        raise HTTPException(status_code=403, detail="not your recording")

    segments = rec.segments or []
    if idx < 0 or idx >= len(segments):
        raise HTTPException(status_code=404, detail="segment not found")

    new_text = body.text.strip()
    if not new_text:
        raise HTTPException(status_code=400, detail="text must not be empty")

    segments[idx]["text"] = new_text
    rec.segments = segments
    # Regenerate full text
    rec.text = " ".join(s["text"] for s in segments)
    session.add(rec)
    session.commit()
    session.refresh(rec)

    return {"segments": rec.segments, "text": rec.text}
```

**Step 2:** Register in main.py:

```python
from .routers.segments import router as segments_router
app.include_router(segments_router)
```

**Step 3:** Commit.

```bash
git add webapp/app/routers/segments.py webapp/app/main.py
git commit -m "feat: PATCH /recordings/{rid}/segments/{idx} for inline corrections"
```

---
## Task 5: Wire edit saves into RecordingCard query cache

**Objective:** When SegmentList calls `onEdited`, update the React Query cache so the changes appear immediately without a refetch.

**Files:**
- Modify: `webapp/frontend/src/components/RecordingCard.tsx`

**Step 1:** Pass `recordingId` and `onEdited` to SegmentList:

```tsx
<SegmentList
  segments={segments}
  activeIdx={activeSegIdx}
  onActiveChange={setActiveSegIdx}
  recordingId={r.id}
  onEdited={(newSegs, newText) => {
    qc.setQueryData(["recordings"], (old: Recording[] | undefined) => {
      if (!old) return old;
      return old.map((rec) =>
        rec.id === r.id ? { ...rec, segments: newSegs, text: newText } : rec
      );
    });
  }}
/>
```

**Step 2:** Commit.

```bash
git add webapp/frontend/src/components/RecordingCard.tsx
git commit -m "fix: optimistic cache update after segment edit"
```

---
## Verification

1. Play audio via WaveSurfer → active segment highlights as cursor moves
2. Pause → everything stops (no ghost playback)
3. Click a segment → no seek/play, just highlight
4. Double-click segment text → textarea appears with original text
5. Type correction, press Ctrl+Enter → segment saves, full text updates
6. Press Escape → edit cancels, reverts to original text
7. Play from WaveSurfer → highlight follows cursor again

---
## Risks

| Risk | Mitigation |
|------|------------|
| `onTimeUpdate` fires rapidly — setState per frame | Use `ref` for prev idx comparison, only setState on change |
| Double-click also triggers single click handler | Add `clickTimer` ref — if double-click fires, skip the single-click action |
