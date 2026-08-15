import { useEffect, useRef, useState } from "react";
import { Mic } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { importFromUrl, recordFromMic, uploadRecording, duplicateRecording, mergeRecordings, type UserInfo } from "../api";
import { fmtBytes } from "../format";
import { useToast } from "./Toasts";
import { useT } from "../useLocale";
import { ImportToggles, IMPORT_DEFAULTS, type ImportFeatureValues } from "./ImportToggles";
import { diarSensToMinDurationOff } from "./FeatureToggles";
import {
  PendingRecording,
  deletePendingRecording,
  loadPendingRecordings,
  pendingToFormData,
  savePendingRecording,
} from "../offlineQueue";
import WaveSurfer from "wavesurfer.js";
import RecordPlugin from "wavesurfer.js/dist/plugins/record.js";

interface Props {
  user?: UserInfo | null;
}

export function UploadZone({ user }: Props) {
  const [inputMode, setInputMode] = useState<"upload" | "record" | "url">("upload");
  const [recording, setRecording] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const fileRef = useRef<HTMLInputElement>(null);
  const { toast } = useToast();
  const { t } = useT();
  const qc = useQueryClient();

  // — Import-Feature-Auswahl (2026-08-14): Seit Task 9 leben die Toggles an
  //   der Transcribe-Zeile — aber beim Upload/YouTube-Import gibt es noch
  //   keine Aufnahme. Diese Werte steuern Upload UND URL-Import; sie werden
  //   als enable_*-Flags an der angelegten Recording gespeichert.
  const [importFeat, setImportFeat] = useState<ImportFeatureValues>(IMPORT_DEFAULTS);
  const vadOn = importFeat.vad;
  const diarizeOn = importFeat.diarize;
  const livePreview = importFeat.streaming;
  const noiseReduce = importFeat.noise;
  const enhanceLevel = importFeat.enhance;
  const [dupPrompt, setDupPrompt] = useState<{ file: File; batchId: string; existingId: string } | null>(null);
  // merged-Modus: der Upload-Loop pausiert bei einem Duplikat und wartet auf
  // die Entscheidung im Dialog („Upload again" → uid, „Skip" → null).
  const dupWaitRef = useRef<((uid: string | null) => void) | null>(null);
  const [pendingFiles, setPendingFiles] = useState<File[] | null>(null);
  const [mergeMode, setMergeMode] = useState<"separate" | "merged">("separate");
  const [uploadingName, setUploadingName] = useState("");

  // — Upload logic —
  async function handleFiles(files: FileList | File[]) {
    const items = Array.from(files);
    if (!items.length) return;
    // Kein Sofort-Upload mehr: erst Liste zeigen (Reihenfolge + Modus wählen)
    setPendingFiles(items);
  }

  async function startUpload() {
    if (!pendingFiles || !pendingFiles.length) return;
    const files = pendingFiles;
    setPendingFiles(null);
    setIsUploading(true);
    setUploadProgress(0);
    const batchId = crypto.randomUUID();
    const totalSize = files.reduce((s, f) => s + f.size, 0);
    let uploadedBytes = 0;
    const uids: string[] = [];
    const errors: string[] = [];

    for (const f of files) {
      setUploadingName(f.name);
      try {
        const r = await uploadRecording(f, batchId, vadOn, diarizeOn, livePreview, noiseReduce, enhanceLevel, false, (pct) => {
          setUploadProgress(Math.round(((uploadedBytes + (f.size * pct) / 100) / totalSize) * 100));
        },
          importFeat.numSpeakers ? Number(importFeat.numSpeakers) : undefined,
          diarSensToMinDurationOff(importFeat.diarSens),
        );
        if (r && typeof r === "object" && "duplicate" in r && r.duplicate) {
          const existingId = String(r.existing_id ?? "");
          // IMMER auf die Dialog-Entscheidung warten (Upload again → uid,
          // Skip → null) — auch ohne Merge-Modus. Vorher verpuffte die
          // „Upload again"-UID im separate-Zweig (dupWaitRef war null) und
          // der skipped-Toast kam trotz Entscheidung sofort. (2026-08-14)
          const chosen = await new Promise<string | null>((resolve) => {
            dupWaitRef.current = resolve;
            setDupPrompt({ file: f, batchId, existingId });
          });
          if (chosen) uids.push(chosen);
          else errors.push(`${f.name}: ${t("skipped_duplicate")}`);
        } else if ("uid" in r) {
          uids.push(r.uid);
        }
        uploadedBytes += f.size;
      } catch (e) {
        errors.push(`${f.name}: ${(e as Error).message}`);
        uploadedBytes += f.size;
      }
    }

    if (mergeMode === "merged" && uids.length >= 2) {
      try {
        await mergeRecordings(uids, batchId);
        toast(`1 ${t("recordings")} · ${t("merged_ok")}`, "ok");
      } catch (e) {
        errors.push(`Merge: ${(e as Error).message}`);
      }
    } else if (mergeMode === "merged") {
      errors.push(t("merge_need_two"));
    }

    errors.forEach((msg) => toast(msg, "err"));
    if (mergeMode !== "merged" && uids.length > 0) {
      toast(`${uids.length} ${t("recordings")}`, "ok");
    }

    await qc.invalidateQueries({ queryKey: ["recordings"] });
    await qc.invalidateQueries({ queryKey: ["stats"] });
    setUploadingName("");
    setIsUploading(false);
  }

  async function handleDuplicate(existingId: string) {
    setIsUploading(true);
    setUploadingName(dupPrompt?.file.name ?? "");
    setUploadProgress(0);
    try {
      const dup = await duplicateRecording(existingId);
      dupWaitRef.current?.(dup.uid ?? null);
      dupWaitRef.current = null;
      // Feedback kommt aus der Upload-Loop (Zusammenfassung) — kein eigener
      // Toast nötig, sonst doppelte Meldung. (2026-08-14)
      await qc.invalidateQueries({ queryKey: ["recordings"] });
    } catch (e) {
      // Kopieren unmöglich (z.B. Datei gelöscht, „Upload again" nach
      // Upload→Löschen→Neu-Upload): dann die Datei doch echt hochladen —
      // der Browser hat sie ja noch. force=true umgeht die Duplikat-Sperre.
      const f = dupPrompt?.file;
      const batch = dupPrompt?.batchId;
      if (f) {
        try {
          const up = await uploadRecording(
            f,
            batch ?? crypto.randomUUID(),
            vadOn, diarizeOn, livePreview, noiseReduce, enhanceLevel,
            true,
            (pct) => setUploadProgress(pct),
            importFeat.numSpeakers ? Number(importFeat.numSpeakers) : undefined,
            diarSensToMinDurationOff(importFeat.diarSens),
          );
          const uid = "uid" in up ? up.uid : null;
          dupWaitRef.current?.(uid);
          dupWaitRef.current = null;
          toast("Uploaded", "ok");
        } catch (e2) {
          dupWaitRef.current?.(null);
          dupWaitRef.current = null;
          toast(`Upload failed: ${(e2 as Error).message}`, "err");
        }
      } else {
        dupWaitRef.current?.(null);
        dupWaitRef.current = null;
        toast(`Upload failed: ${(e as Error).message}`, "err");
      }
    } finally {
      setUploadingName("");
      setIsUploading(false);
    }
  }

  function moveFile(idx: number, dir: -1 | 1) {
    setPendingFiles((prev) => {
      if (!prev) return prev;
      const j = idx + dir;
      if (j < 0 || j >= prev.length) return prev;
      const next = [...prev];
      [next[idx], next[j]] = [next[j], next[idx]];
      return next;
    });
  }

  function removeFile(idx: number) {
    setPendingFiles((prev) => {
      if (!prev) return null;
      const next = prev.filter((_, i) => i !== idx);
      if (next.length < 2) setMergeMode("separate"); // Merge-Sinn entfällt
      return next.length ? next : null;
    });
  }

  // — Drag/drop handlers (for UploadTab) —
  function handleClick() {
    if (isUploading) return;
    fileRef.current?.click();
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter" || e.key === " ") fileRef.current?.click();
  }

  function handleDragOver(e: React.DragEvent) {
    e.preventDefault();
    setIsDragging(true);
  }

  function handleDragLeave(e: React.DragEvent) {
    if (!e.currentTarget.contains(e.relatedTarget as Node)) {
      setIsDragging(false);
    }
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files.length) void handleFiles(e.dataTransfer.files);
  }

  function handleInputChange(e: React.ChangeEvent<HTMLInputElement>) {
    if (e.target.files?.length) {
      void handleFiles(e.target.files);
      e.target.value = "";
    }
  }

  const active = isDragging || isUploading;

  return (
    <div className="flex flex-col gap-4">
      {/* Anon-Retention-Hinweis: anonyme User werden gewarnt */}
      {user?.anonymous && (
        <div className="border border-amber-500/40 bg-amber-500/10 rounded-sm px-3 py-2 text-[12px] text-amber-200 leading-snug">
          ⚠️{" "}
          {t("anon_retention_warning").replace(
            "{minutes}",
            String(user.retention_minutes ?? 15),
          )}
        </div>
      )}
      {/* Tab bar */}
      <div className="flex gap-0 border-b border-border">
        <TabButton active={inputMode === "upload"} disabled={recording} onClick={() => setInputMode("upload")}>
          📤 {t("tab_upload")}
        </TabButton>
        <TabButton active={inputMode === "record"} disabled={recording} onClick={() => setInputMode("record")}>
          🎤 {t("tab_record")}
        </TabButton>
        <TabButton active={inputMode === "url"} disabled={recording} onClick={() => setInputMode("url")}>
          🔗 {t("tab_url")}
        </TabButton>
      </div>

      {/* Tab content */}
      {inputMode === "upload" && (
        <>
          <UploadTab
            isUploading={isUploading}
            isDragging={isDragging}
            uploadProgress={uploadProgress}
            uploadName={uploadingName}
            active={active}
            handleClick={handleClick}
            handleKeyDown={handleKeyDown}
            handleDragOver={handleDragOver}
            handleDragLeave={handleDragLeave}
            handleDrop={handleDrop}
            handleInputChange={handleInputChange}
            fileRef={fileRef}
            t={t}
          />

          {/* Dateiliste vor dem Upload. Sortier-/Merge-GUI (↑/↓, einzeln/
              gemerged) erst ab 2 Dateien — bei einer Datei nur Name + ✕
              (User 2026-08-14). */}
          {pendingFiles && pendingFiles.length > 0 && !isUploading && (
            <div className="border border-border rounded-card bg-panel p-3 flex flex-col gap-2">
              <div className="text-[12px] font-semibold text-txt">
                {t("files_selected")} ({pendingFiles.length})
              </div>
              <ImportToggles values={importFeat} onChange={(p) => setImportFeat((f) => ({ ...f, ...p }))} />
              {pendingFiles.map((f, i) => (
                <div key={`${f.name}-${i}`} className="flex items-center gap-2 text-[12px]">
                  <span className="flex-1 truncate text-muted">
                    {i + 1}. {f.name}
                    <span className="text-muted2 ml-1">({fmtBytes(f.size)})</span>
                  </span>
                  {pendingFiles.length > 1 && (
                    <>
                      <button
                        onClick={() => moveFile(i, -1)}
                        disabled={i === 0}
                        className="btn-ghost-sm text-[11px] px-1"
                        title={t("move_up")}
                        aria-label={t("move_up")}
                      >
                        ↑
                      </button>
                      <button
                        onClick={() => moveFile(i, 1)}
                        disabled={i === pendingFiles.length - 1}
                        className="btn-ghost-sm text-[11px] px-1"
                        title={t("move_down")}
                        aria-label={t("move_down")}
                      >
                        ↓
                      </button>
                    </>
                  )}
                  <button
                    onClick={() => removeFile(i)}
                    className="btn-ghost-sm text-err text-[11px] px-1"
                    aria-label={t("remove_file")}
                  >
                    ✕
                  </button>
                </div>
              ))}
              {pendingFiles.length > 1 && (
                <>
                  <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[12px] mt-1">
                    <label className="flex items-center gap-1.5 cursor-pointer text-muted">
                      <input
                        type="radio"
                        checked={mergeMode === "separate"}
                        onChange={() => setMergeMode("separate")}
                      />
                      {t("transcribe_separately")}
                    </label>
                    <label className="flex items-center gap-1.5 cursor-pointer text-muted">
                      <input
                        type="radio"
                        checked={mergeMode === "merged"}
                        onChange={() => setMergeMode("merged")}
                      />
                      {t("merge_into_one")}
                    </label>
                  </div>
                  {mergeMode === "merged" && (
                    <div className="text-[11px] text-muted2">{t("merge_note")}</div>
                  )}
                </>
              )}
              <button
                onClick={() => void startUpload()}
                disabled={isUploading}
                className="btn-primary text-[13px] mt-1 self-start"
              >
                {t("upload")} ({pendingFiles.length})
              </button>
            </div>
          )}
        </>
      )}
      {inputMode === "record" && (
        <RecordTab
          setIsUploading={setIsUploading}
          onRecordingChange={setRecording}
          toast={toast}
          qc={qc}
          t={t}
          vadOn={vadOn} diarizeOn={diarizeOn}
          livePreview={livePreview} noiseReduce={noiseReduce} enhanceLevel={enhanceLevel}
        />
      )}
      {inputMode === "url" && (
        <UrlTab
          toast={toast}
          qc={qc}
          t={t}
          importFeat={importFeat}
          onFeatChange={(p) => setImportFeat((f) => ({ ...f, ...p }))}
        />
      )}

      {/* Duplicate file prompt */}
      {dupPrompt && (
        <div className="bg-[rgba(248,81,73,.08)] border border-err/30 rounded-sm px-4 py-3 text-[13px] flex items-center gap-3">
          <span className="text-muted flex-1">
            <strong>{dupPrompt.file.name}</strong> {t("duplicate_exists")}
          </span>
          <button
            onClick={async () => {
              const existingId = dupPrompt.existingId;
              setDupPrompt(null);
              await handleDuplicate(existingId);
            }}
            className="btn-ghost-sm text-err text-[12px]"
          >
            {t("upload_again")}
          </button>
          <button
            onClick={() => {
              dupWaitRef.current?.(null);
              dupWaitRef.current = null;
              setDupPrompt(null);
            }}
            className="btn-ghost-sm text-[12px]"
          >
            {t("skip")}
          </button>
        </div>
      )}

      {/* Task 9: globale Feature-Toggles entfernt — Toggles docken jetzt an die
          Transcribe-Zeile der jeweiligen Aufnahme (RecordingCard) an. */}

      {/* CPU/GPU-Badge ist in die Stats-Leiste (Header) gewandert (Settings-UI-Task). */}
    </div>
  );
}

// ── Tab button ──

function TabButton({ active, disabled, onClick, children }: { active: boolean; disabled?: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`px-3 py-[6px] sm:px-4 sm:py-2 text-[12px] sm:text-[13px] font-semibold border-b-2 transition-colors ${
        active
          ? "border-accent text-accent"
          : "border-transparent text-muted hover:text-txt"
      } ${disabled ? "opacity-40 pointer-events-none" : ""}`}
    >
      {children}
    </button>
  );
}

// ── Upload tab ──

function UploadTab({ isUploading, uploadProgress, uploadName, active, handleClick, handleKeyDown, handleDragOver, handleDragLeave, handleDrop, handleInputChange, fileRef, t }: any) {
  return (
    <div
      role="button"
      tabIndex={0}
      aria-label={t("drag_zone")}
      onClick={handleClick}
      onKeyDown={handleKeyDown}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      className={`
        border-2 border-dashed rounded-card
        px-4 py-6 sm:px-6 sm:py-9 text-center cursor-pointer
        select-none transition-all duration-200
        bg-panel
        ${
          active
            ? "border-accent bg-[rgba(91,140,255,0.06)] text-txt"
            : "border-border2 text-muted hover:border-accent hover:bg-[rgba(91,140,255,0.06)] hover:text-txt"
        }
      `}
    >
      <div className="text-[32px] mb-2 leading-none">
        {isUploading ? (
          <div className="flex flex-col items-center gap-2">
            <span className="text-[18px]">⏳</span>
            <div className="w-[200px] h-2 bg-border rounded-full overflow-hidden">
              <div
                className="h-full bg-accent rounded-full transition-all duration-300"
                style={{ width: `${uploadProgress}%` }}
              />
            </div>
            <span className="text-[11px] text-muted2">{uploadProgress}%</span>
            {/* Dateiname unter dem Balken — was lade ich gerade hoch? */}
            {uploadName && (
              <span className="text-[11px] text-muted max-w-[280px] truncate">
                📄 {uploadName}
              </span>
            )}
          </div>
        ) : (
          <Mic size={32} className="mx-auto text-muted" />
        )}
      </div>
      <div className="font-semibold text-[15px] text-txt">
        {isUploading ? t("uploading") : t("drag_here")}
      </div>
      <div className="text-[12.5px] mt-1 text-muted">
        {t("multi_files")}
      </div>
      <div className="mt-[10px] text-[11px] text-muted2 tracking-[.03em]">
        {t("upload_formats")}
      </div>
      <input
        ref={fileRef}
        type="file"
        accept="audio/*"
        multiple
        className="hidden"
        onChange={handleInputChange}
      />
    </div>
  );
}

// ── Record tab ──

function RecordTab({ setIsUploading, onRecordingChange, toast, qc, t, vadOn, diarizeOn, livePreview, noiseReduce, enhanceLevel }: any) {
  const [recording, setRecording] = useState(false);
  const [paused, setPaused] = useState(false);
  const [continuous, setContinuous] = useState(false);
  const [showHelp, setShowHelp] = useState(false);
  const [pendingCount, setPendingCount] = useState(0);
  const [retrying, setRetrying] = useState(false);
  const [uploadPhase, setUploadPhase] = useState<"idle" | "saving" | "processing" | "uploading" | "done">("idle");
  const [uploadPct, setUploadPct] = useState(0);
  const [wakelock, setWakelock] = useState<WakeLockSentinel | null>(null);
  const [duration, setDuration] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);
  const wsRef = useRef<WaveSurfer | null>(null);
  const recordRef = useRef<RecordPlugin | null>(null);
  const micStreamRef = useRef<MediaStream | null>(null); // Pre-Warm (2026-08-15)
  const prewarmInFlight = useRef<Promise<void> | null>(null);
  const timerRef = useRef<number>(0);
  const chunksRef = useRef<Blob[]>([]);
  const touchStartY = useRef<number | null>(null);
  const touchStartT = useRef<number>(0);
  const gestureDone = useRef(false);
  const isTouch = typeof window !== "undefined" && ("ontouchstart" in window || navigator.maxTouchPoints > 0);

  // Anleitung beim ersten Besuch automatisch zeigen
  useEffect(() => {
    if (isTouch && !localStorage.getItem("ps_pushtorecord_help_seen")) {
      setShowHelp(true);
      localStorage.setItem("ps_pushtorecord_help_seen", "1");
    }
  }, [isTouch]);

  // Offline-Puffer beim Start laden + offene Aufnahmen automatisch hochladen
  useEffect(() => {
    void loadPendingRecordings().then((recs) => {
      setPendingCount(recs.length);
      if (recs.length > 0 && navigator.onLine) {
        void retryPending();
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function retryPending() {
    if (retrying) return;
    setRetrying(true);
    try {
      const recs = await loadPendingRecordings();
      for (const rec of recs) {
        try {
          const res = await fetch("/api/recordings", { method: "POST", body: pendingToFormData(rec) }).then((r) => {
            if (!r.ok) throw new Error(`HTTP ${r.status}`);
            return r;
          });
          await res.json();
          await deletePendingRecording(rec.id);
          toast(`Upload ok: ${rec.fileName}`, "ok");
        } catch (e) {
          toast(`Retry fehlgeschlagen: ${(e as Error).message}`, "err");
        }
      }
      setPendingCount((await loadPendingRecordings()).length);
      await qc.invalidateQueries({ queryKey: ["recordings"] });
    } finally {
      setRetrying(false);
    }
  }

  async function acquireWakeLock() {
    try {
      const wl = await navigator.wakeLock.request("screen");
      setWakelock(wl);
      wl.addEventListener("release", () => setWakelock(null));
    } catch {}
  }

  function releaseWakeLock() {
    wakelock?.release().catch(() => {});
    setWakelock(null);
  }

  // ── Mikrofon-Pre-Warm (2026-08-15) ──
  // Der Delay zwischen Knopfdruck und Aufnahme kam von getUserMedia():
  // Der Browser musste den Mikrofon-Stream JEDES MAL neu aushandeln
  // (Permission-Check + Stream-Start, auf Mobil oft 300–800 ms). Ab jetzt
  // wird der Stream beim Betreten des Record-Tabs und nach jedem Stop
  // vorab geholt und gecacht — startRecording() nutzt ihn direkt.
  async function prewarmMic() {
    if (micStreamRef.current) return; // schon warm
    if (prewarmInFlight.current) return prewarmInFlight.current; // dedupe
    prewarmInFlight.current = (async () => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          audio: { noiseSuppression: false, echoCancellation: false, autoGainControl: true },
        });
        micStreamRef.current = stream;
      } catch {
        // Kein Zugriff — startRecording zeigt dann den Fehler-Toast.
      } finally {
        prewarmInFlight.current = null;
      }
    })();
    return prewarmInFlight.current;
  }

  // Beim ersten Betreten des Record-Tabs den Stream vorab anfordern —
  // damit Permission-Prompt/Stream-Start NICHT beim ersten Knopfdruck
  // passieren (das war der spürbare Delay).
  useEffect(() => {
    void prewarmMic();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function startRecording() {
    acquireWakeLock();
    onRecordingChange(true);
    chunksRef.current = [];

    // Create WaveSurfer with Record plugin
    const record = RecordPlugin.create({
      scrollingWaveform: true,
      scrollingWaveformWindow: 5,
      renderRecordedAudio: false,  // we handle upload ourselves
    });

    const ws = WaveSurfer.create({
      container: containerRef.current!,
      waveColor: "rgba(91,140,255,0.3)",
      progressColor: "rgba(91,140,255,0.8)",
      barWidth: 2,
      barGap: 1,
      barRadius: 2,
      height: 60,
      normalize: true,
      plugins: [record],
    });

    wsRef.current = ws;
    recordRef.current = record;

    record.on("record-start", () => {
      setRecording(true);
      setDuration(0);
      timerRef.current = window.setInterval(() => setDuration((d) => d + 1), 1000);
    });

    record.on("record-end", async (blob: Blob) => {
      clearInterval(timerRef.current);
      setDuration(0);
      setPaused(false);
      setContinuous(false);
      ws.destroy();
      wsRef.current = null;
      recordRef.current = null;
      // Stream freigeben (Safety Net) — nächster Start prewarmt neu
      micStreamRef.current?.getTracks().forEach((t) => t.stop());
      micStreamRef.current = null;
      void prewarmMic();

      releaseWakeLock();
      setIsUploading(true);

      // 1) SOFORT lokal sichern (IndexedDB) — bevor irgendetwas anderes
      //    passieren kann. Netzabriss/Serverfehler dürfen die Aufnahme
      //    nicht mehr vernichten: der Blob überlebt, bis der Upload
      //    nachweislich erfolgreich war.
      setUploadPhase("saving");
      const ext = blob.type.includes("mp4") ? ".mp4" : ".webm";
      const pending: PendingRecording = {
        id: crypto.randomUUID(),
        blob,
        fileName: `recording_${Date.now()}${ext}`,
        mime: blob.type,
        createdAt: Date.now(),
        vad: vadOn,
        diarize: diarizeOn,
        streaming: livePreview,
        noiseReduce,
        enhance: enhanceLevel,
      };
      await savePendingRecording(pending);
      setPendingCount((await loadPendingRecordings()).length);

      try {
        // 2) Peak-normalize (kann bei langen Aufnahmen dauern — Feedback zeigen)
        setUploadPhase("processing");
        const normBlob = await normalizePeak(blob);
        const batchId = pending.id;

        // 3) Upload mit sichtbarem Fortschritt
        setUploadPhase("uploading");
        setUploadPct(0);
        await recordFromMic(normBlob, batchId, vadOn, diarizeOn, livePreview, noiseReduce, enhanceLevel, (pct) => setUploadPct(pct));
        await deletePendingRecording(pending.id); // Upload bestätigt → Puffer leeren
        setPendingCount((await loadPendingRecordings()).length);
        setUploadPhase("done");
        await qc.invalidateQueries({ queryKey: ["recordings"] });
        toast("Recording uploaded", "ok");
      } catch (e) {
        // Upload fehlgeschlagen — Aufnahme bleibt sicher im IndexedDB-Puffer.
        setUploadPhase("done");
        toast(`Upload failed — Aufnahme lokal gesichert: ${(e as Error).message}`, "err");
      } finally {
        setIsUploading(false);
        onRecordingChange(false);
        setTimeout(() => setUploadPhase("idle"), 2500); // Status noch kurz zeigen
      }
    });

    // Record progress for more accurate timer
    record.on("record-progress", (ms: number) => {
      setDuration(Math.floor(ms / 1000));
    });

    try {
      // Pre-Warmed Stream direkt verwenden (kein erneutes getUserMedia) —
      // der Delay zwischen Druck und Aufnahme entfällt. Der Recorder übernimmt
      // den Stream via renderMicStream, startRecording startet sofort.
      if (micStreamRef.current) {
        record.renderMicStream(micStreamRef.current);
      }
      await record.startRecording({
        noiseSuppression: false,
        echoCancellation: false,
        autoGainControl: true,
      });
    } catch (e) {
      toast(`Mic access denied: ${(e as Error).message}`, "err");
      ws.destroy();
      wsRef.current = null;
      recordRef.current = null;
      releaseWakeLock();
      onRecordingChange(false);
    }
  }

  async function stopRecording() {
    recordRef.current?.stopRecording();
    recordRef.current?.stopMic();
    // Stream freigeben + sofort neu prewarmen → nächster Start ohne Delay
    micStreamRef.current?.getTracks().forEach((t) => t.stop());
    micStreamRef.current = null;
    void prewarmMic();
    setRecording(false);
    setPaused(false);
    setContinuous(false);
  }

  // ── Mobile Push-to-Record Gesten ──
  // Drücken = aufnehmen / fortsetzen · Loslassen = Pause (gleiche Datei!)
  // Swipe ↑ = Daueraufnahme · Swipe ↓ = Stop + Upload

  function onTouchStart(e: React.TouchEvent) {
    touchStartY.current = e.touches[0]?.clientY ?? null;
    touchStartT.current = Date.now();
    gestureDone.current = false;

    if (recording && paused) {
      // Fortsetzen nach Pause — weiter in dieselbe Datei
      recordRef.current?.resumeRecording();
      setPaused(false);
      timerRef.current = window.setInterval(() => setDuration((d) => d + 1), 1000);
    } else if (!recording && !paused) {
      // Neue Aufnahme starten
      void startRecording();
    }
    // Läuft bereits (continuous): nichts tun — Gesten entscheiden
  }

  function onTouchMove(e: React.TouchEvent) {
    if (touchStartY.current === null || gestureDone.current) return;
    const dy = (e.touches[0]?.clientY ?? touchStartY.current) - touchStartY.current;
    const dt = Date.now() - touchStartT.current;
    // Nur echte Swipes (min. 60px) erkennen — kein Zittern
    if (Math.abs(dy) < 60 || dt < 120) return;

    if (dy < -60) {
      // Swipe nach oben → Daueraufnahme: loslassen pausiert NICHT mehr
      gestureDone.current = true;
      setContinuous(true);
      if (recording && paused) {
        recordRef.current?.resumeRecording();
        setPaused(false);
      }
    } else if (dy > 60) {
      // Swipe nach unten → Stop + Upload
      gestureDone.current = true;
      if (recording) {
        void stopRecording();
      }
    }
  }

  function onTouchEnd() {
    // Loslassen ohne Swipe = Pause (nur wenn nicht Continuous-Modus)
    if (!gestureDone.current && recording && !paused && !continuous) {
      recordRef.current?.pauseRecording();
      setPaused(true);
      clearInterval(timerRef.current); // Timer pausiert mit
    }
    touchStartY.current = null;
  }

  function onTouchCancel() {
    // Abgebrochene Geste (z. B. System-UI): pausieren statt weiterlaufen
    if (recording && !paused && !continuous) {
      recordRef.current?.pauseRecording();
      setPaused(true);
      clearInterval(timerRef.current);
    }
    touchStartY.current = null;
  }

  useEffect(() => {
    return () => {
      clearInterval(timerRef.current);
      wsRef.current?.destroy();
      releaseWakeLock();
    };
  }, []);

  const fmt = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;

  return (
    <div className="flex flex-col items-center gap-3 py-4">
      {/* WaveSurfer waveform container — only visible during recording */}
      <div
        ref={containerRef}
        className={`w-full max-w-[500px] px-2 sm:px-0 ${recording ? "" : "hidden"}`}
      />

      {/* Offline-Puffer: lokal gesicherte Aufnahmen, deren Upload noch aussteht */}
      {pendingCount > 0 && (
        <div className="w-full max-w-[500px] bg-[rgba(217,158,43,.1)] border border-[#d99e2b]/40 rounded-sm px-3 py-2 flex items-center gap-2">
          <span className="text-[12px] text-txt flex-1">
            💾 {t("offline_pending")}: {pendingCount}
          </span>
          <button
            onClick={() => void retryPending()}
            disabled={retrying}
            className="bg-[#d99e2b] text-white text-[11px] px-2.5 py-1 rounded-sm font-semibold hover:opacity-90 disabled:opacity-50 whitespace-nowrap"
          >
            {retrying ? t("offline_retrying") : t("offline_retry")}
          </button>
        </div>
      )}

      {/* Mobile: animierte Gesten-Anleitung */}
      {isTouch && showHelp && (
        <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-6" onClick={() => setShowHelp(false)}>
          <div className="bg-panel border border-border rounded-card p-5 max-w-[320px] w-full space-y-4" onClick={(e) => e.stopPropagation()}>
            <div className="text-center font-bold text-[14px]">📱 {t("push_record_help_title")}</div>

            {/* Geste 1: Drücken & Loslassen = Pause */}
            <div className="flex items-center gap-3">
              <div className="w-12 h-12 rounded-full bg-accent/20 border border-accent/40 flex items-center justify-center text-[20px] animate-pulse shrink-0">🎤</div>
              <div className="text-[12px] text-txt leading-snug">
                <b>👆 {t("push_record_gesture_1a")}</b>
                <div className="text-muted2">{t("push_record_gesture_1b")}</div>
              </div>
            </div>

            {/* Geste 2: Swipe ↑ = Daueraufnahme */}
            <div className="flex items-center gap-3">
              <div className="w-12 h-12 rounded-full bg-accent/20 border border-accent/40 flex items-center justify-center text-[20px] shrink-0 animate-bounce">⬆️</div>
              <div className="text-[12px] text-txt leading-snug">
                <b>{t("push_record_gesture_2a")}</b>
                <div className="text-muted2">{t("push_record_gesture_2b")}</div>
              </div>
            </div>

            {/* Geste 3: Swipe ↓ = Stop */}
            <div className="flex items-center gap-3">
              <div className="w-12 h-12 rounded-full bg-err/20 border border-err/40 flex items-center justify-center text-[20px] shrink-0 animate-pulse">⬇️</div>
              <div className="text-[12px] text-txt leading-snug">
                <b>{t("push_record_gesture_3a")}</b>
                <div className="text-muted2">{t("push_record_gesture_3b")}</div>
              </div>
            </div>

            <button
              onClick={() => setShowHelp(false)}
              className="w-full bg-accent text-white text-[12px] py-2 rounded-sm font-semibold"
            >
              {t("push_record_help_close")}
            </button>
          </div>
        </div>
      )}

      {/* Aufnahme-Button — Mobile: Push-to-Record, Desktop: wie bisher */}
      <div className="relative">
        <button
          onClick={isTouch ? undefined : (recording ? stopRecording : startRecording)}
          onTouchStart={isTouch ? onTouchStart : undefined}
          onTouchMove={isTouch ? onTouchMove : undefined}
          onTouchEnd={isTouch ? onTouchEnd : undefined}
          onTouchCancel={isTouch ? onTouchCancel : undefined}
          className={`w-16 h-16 sm:w-20 sm:h-20 rounded-full text-xl sm:text-2xl flex items-center justify-center transition-all shrink-0 select-none touch-none
            ${recording
              ? continuous
                ? "bg-accent text-white shadow-lg animate-pulse"
                : paused
                  ? "bg-[#d99e2b] text-white shadow-lg"
                  : "bg-err text-white shadow-lg animate-pulse"
              : "bg-accent text-white hover:bg-accent/90"
            }
          `}
        >
          {recording ? (paused ? "⏸" : continuous ? "🔴" : "⏹") : "🎤"}
        </button>

        {/* Help-Button (mobile) */}
        {isTouch && (
          <button
            onClick={() => setShowHelp(true)}
            className="absolute -top-1 -right-1 w-6 h-6 rounded-full bg-panel2 border border-border text-[11px] text-muted hover:text-txt flex items-center justify-center"
            title={t("push_record_help_title")}
          >
            ?
          </button>
        )}
      </div>

      {/* Statuszeile für Mobile-Modus */}
      {isTouch && recording && (
        <div className="text-[12px] text-center">
          {paused ? (
            <span className="text-[#d99e2b] font-semibold">⏸ {t("push_record_paused")}</span>
          ) : continuous ? (
            <span className="text-accent font-semibold">🔴 {t("push_record_continuous")}</span>
          ) : (
            <span className="text-muted">{t("push_record_hold_hint")}</span>
          )}
        </div>
      )}

      <div className="text-[22px] sm:text-[28px] font-mono tabular-nums">{fmt(duration)}</div>

      {/* Sichtbares Upload-Feedback — direkt nach Stop, kein stummes Warten */}
      {uploadPhase !== "idle" && (
        <div className="w-full max-w-[500px] bg-panel2 border border-border rounded-sm px-3 py-2 space-y-1">
          <div className="flex items-center gap-2 text-[12px] text-txt">
            {uploadPhase !== "done" ? (
              <span className="inline-block w-3 h-3 rounded-full border-2 border-accent border-t-transparent animate-spin" />
            ) : (
              <span>✅</span>
            )}
            <span className="flex-1">
              {uploadPhase === "saving" && t("upload_phase_saving")}
              {uploadPhase === "processing" && t("upload_phase_processing")}
              {uploadPhase === "uploading" && t("upload_phase_uploading")}
              {uploadPhase === "done" && t("upload_phase_done")}
            </span>
          </div>
          {uploadPhase === "uploading" && (
            <div className="flex items-center gap-2">
              <div className="flex-1 h-1.5 bg-border rounded-full overflow-hidden">
                <div className="h-full bg-accent rounded-full transition-all duration-200" style={{ width: `${uploadPct}%` }} />
              </div>
              <span className="text-[10px] text-muted2 tabular-nums w-8 text-right">{uploadPct}%</span>
            </div>
          )}
        </div>
      )}

      {wakelock && (
        <div className="text-[11px] text-muted2 flex items-center gap-1">
          <span>🔒</span> {t("rec_wakelock")}
        </div>
      )}

      <div className="text-[12px] text-muted">{t("rec_btn")}</div>
    </div>
  );
}

// ── Audio peak-normalization helper ──

/**
 * Peak-normalize an audio blob to -1 dBFS and return a 16-bit mono WAV blob.
 * Computes the peak sample across all channels, then scales so the peak hits
 * the target level. Quiet recordings get a boost; already-loud ones are unchanged
 * (or very gently attenuated if they'd clip).
 */
async function normalizePeak(blob: Blob): Promise<Blob> {
  const ctx = new AudioContext();
  try {
    const buf = await ctx.decodeAudioData(await blob.arrayBuffer());
    const numChannels = buf.numberOfChannels;
    const sampleRate = buf.sampleRate;
    const length = buf.length;

    // Find global peak across all channels
    let peak = 0;
    for (let ch = 0; ch < numChannels; ch++) {
      const data = buf.getChannelData(ch);
      for (let i = 0; i < length; i++) {
        const abs = Math.abs(data[i]);
        if (abs > peak) peak = abs;
      }
    }

    // Scale so peak hits -1 dBFS (≈ 0.891). Intentionally below 1.0 so
    // the encoder's int16 rounding never clips.
    const targetPeak = 10 ** (-1 / 20); // ~0.891
    const scale = peak > 0 ? targetPeak / peak : 1;

    // Render scaled audio and encode as mono WAV
    const offline = new OfflineAudioContext(1, length, sampleRate);
    const source = offline.createBufferSource();
    // Build mono buffer with scaling
    const monoBuf = offline.createBuffer(1, length, sampleRate);
    const outData = monoBuf.getChannelData(0);
    for (let i = 0; i < length; i++) {
      let sum = 0;
      for (let ch = 0; ch < numChannels; ch++) {
        sum += buf.getChannelData(ch)[i];
      }
      outData[i] = (sum / numChannels) * scale;
    }
    source.buffer = monoBuf;
    source.connect(offline.destination);
    source.start();

    const rendered = await offline.startRendering();
    return encodeWav(rendered);
  } finally {
    ctx.close();
  }
}

/**
 * Encode an AudioBuffer to a 16-bit mono WAV blob.
 */
function encodeWav(audioBuffer: AudioBuffer): Blob {
  const numChannels = audioBuffer.numberOfChannels;
  const sampleRate = audioBuffer.sampleRate;
  const length = audioBuffer.length;

  // Downmix to mono by averaging channels, and apply soft limiting
  const mono = new Float32Array(length);
  for (let i = 0; i < length; i++) {
    let sum = 0;
    for (let ch = 0; ch < numChannels; ch++) {
      sum += audioBuffer.getChannelData(ch)[i];
    }
    mono[i] = Math.max(-1, Math.min(1, sum / numChannels));
  }

  // 16-bit PCM
  const dataLen = length * 2;
  const buffer = new ArrayBuffer(44 + dataLen);
  const view = new DataView(buffer);

  // RIFF header
  writeStr(view, 0, "RIFF");
  view.setUint32(4, 36 + dataLen, true);
  writeStr(view, 8, "WAVE");
  writeStr(view, 12, "fmt ");
  view.setUint32(16, 16, true); // chunk size
  view.setUint16(20, 1, true);  // PCM
  view.setUint16(22, 1, true);  // mono
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true); // byte rate
  view.setUint16(32, 2, true);  // block align
  view.setUint16(34, 16, true); // bits per sample
  writeStr(view, 36, "data");
  view.setUint32(40, dataLen, true);

  // Write PCM samples
  let offset = 44;
  for (let i = 0; i < length; i++) {
    const s = Math.max(-1, Math.min(1, mono[i]));
    view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7FFF, true);
    offset += 2;
  }

  return new Blob([buffer], { type: "audio/wav" });
}

function writeStr(view: DataView, offset: number, str: string) {
  for (let i = 0; i < str.length; i++) {
    view.setUint8(offset + i, str.charCodeAt(i));
  }
}

// ── URL tab ──

function UrlTab({ toast, qc, t, importFeat, onFeatChange }: {
  toast: ReturnType<typeof useToast>["toast"];
  qc: ReturnType<typeof useQueryClient>;
  t: ReturnType<typeof useT>["t"];
  importFeat: ImportFeatureValues;
  onFeatChange: (p: Partial<ImportFeatureValues>) => void;
}) {
  const [url, setUrl] = useState("");
  const [isDownloading, setIsDownloading] = useState(false);

  async function handleSubmit() {
    if (!url.trim() || isDownloading) return;
    setIsDownloading(true);
    try {
      const result = await importFromUrl(
        url.trim(),
        importFeat.vad, importFeat.diarize, importFeat.streaming,
        importFeat.noise, importFeat.enhance,
        importFeat.numSpeakers ? Number(importFeat.numSpeakers) : undefined,
        diarSensToMinDurationOff(importFeat.diarSens),
      );
      toast(`Imported${result.original_name ? ": " + result.original_name : ""}`, "ok");
      await qc.invalidateQueries({ queryKey: ["recordings"] });
      await qc.invalidateQueries({ queryKey: ["stats"] });
      setUrl("");
    } catch (e) {
      toast(`Import failed: ${(e as Error).message}`, "err");
    } finally {
      setIsDownloading(false);
    }
  }

  return (
    <div className="flex flex-col items-center gap-3 py-6">
      <div className="text-[12px] text-muted">{t("url_placeholder")}</div>
      <ImportToggles values={importFeat} onChange={onFeatChange} />
      <div className="flex gap-2 w-full max-w-[500px]">
        <input
          type="url"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://youtube.com/watch?v=…"
          className="flex-1 bg-panel border border-border2 rounded-sm px-3 py-2 text-[13px] text-txt outline-none focus:border-accent"
          onKeyDown={(e) => { if (e.key === "Enter") handleSubmit(); }}
        />
        <button
          onClick={handleSubmit}
          disabled={isDownloading || !url.trim()}
          className="btn-accent text-[13px] px-4 py-2 rounded-sm whitespace-nowrap"
        >
          {isDownloading ? "⏳ " + t("url_downloading") : "🔗 " + t("url_download")}
        </button>
      </div>
    </div>
  );
}

/* ─────────────────────────────────────────────── */

// Task 9: ToggleSwitch entfernt — die Feature-Toggles leben jetzt in
// FeatureToggles.tsx an der Transcribe-Zeile der RecordingCard.
