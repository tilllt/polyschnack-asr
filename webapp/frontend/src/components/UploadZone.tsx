import { useCallback, useEffect, useRef, useState } from "react";
import { ChevronDown } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { fetchBackendCapabilities, fetchLlmEndpoints, fetchModelStatus, fetchModelsMatrix, fetchTemplates, fetchTargets, importFromUrl, recordFromMic, startTranscription, uploadRecording, duplicateRecording, mergeRecordings, type BackendCapabilities, type ModelMatrixEntry, type UserInfo } from "../api";
import { fmtBytes } from "../format";
import { useToast } from "./Toasts";
import { useT } from "../useLocale";
import { diarSensToMinDurationOff, type FeatureValues } from "./FeatureToggles";
import { OptionsPanel } from "./OptionsPanel";
import { normalizeEnhance } from "../optionMatrix";
import { filterAvailableBackends } from "../backendSelect";
import {
  PendingRecording,
  deletePendingRecording,
  loadPendingRecordings,
  pendingToFormData,
  savePendingRecording,
} from "../offlineQueue";
import WaveSurfer from "wavesurfer.js";
import RecordPlugin from "wavesurfer.js/dist/plugins/record.js";
import { ensureAudioSessionForRecording, restoreAudioSessionAfterRecording, isWebKitAudioSession } from "../audioSession";
import { Zone } from "./Zone";
import {
  RECORD_BUTTON_SHAPE,
  RECORD_GESTURE_TIPS,
  RecordGestureHint,
  gestureTipAt,
} from "./RecordGestureHint";
import { SourceTab, ZoneCircle, SourceIcon } from "./SourceCircle";

interface Props {
  user?: UserInfo | null;
}

/** Startwerte der Optionen (Change 212). Ein Satz für alle drei Quellen. */
export const SOURCE_OPTION_DEFAULTS: FeatureValues = {
  vad: "off",
  diarize: false,
  streaming: false,
  noise: true,
  enhance: "off",
  separate: "none",
  backend: "",
  punctuation: false,
  llmEnhance: false,
  templateId: undefined,
  targetId: undefined,
  endpointId: undefined,
  numSpeakers: "",
  diarSens: "std",
  diarMethod: "",
};

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

  // — Change 212: EIN Optionszustand für alle drei Quellen. Er liegt hier
  //   oberhalb der Quellen-Tabs und wird von Datei-Upload, Aufnahme und
  //   URL-Import gemeinsam benutzt (vorher: ImportToggles-Chips je Tab).
  const [values, setValues] = useState<FeatureValues>(SOURCE_OPTION_DEFAULTS);
  const [optsOpen, setOptsOpen] = useState(true);
  const [matrix, setMatrix] = useState<ModelMatrixEntry[]>([]);
  const [caps, setCaps] = useState<BackendCapabilities | null>(null);
  const [flags, setFlags] = useState<{ vad: boolean; diarize: boolean }>({ vad: true, diarize: true });
  const [templates, setTemplates] = useState<{ template_id: number; name: string }[]>([]);
  const [targets, setTargets] = useState<{ target_id: number; name: string; kind: string }[]>([]);
  const [endpoints, setEndpoints] = useState<{ endpoint_id: number; name: string }[]>([]);
  const isOidc = !!user?.authenticated;

  useEffect(() => {
    fetchModelsMatrix().then(setMatrix).catch(() => setMatrix([]));
    // Fähigkeiten NUR aus der API (kein hartkodierter Wert im Frontend).
    fetchBackendCapabilities().then(setCaps).catch(() => setCaps(null));
    fetchModelStatus()
      .then((ms) => setFlags({ vad: ms.vad_available, diarize: ms.diarize_available }))
      .catch(() => {});
    if (isOidc) {
      fetchTemplates().then(setTemplates).catch(() => {});
      fetchTargets().then(setTargets).catch(() => {});
      fetchLlmEndpoints().then(setEndpoints).catch(() => {});
    }
  }, [isOidc]);

  const availableBackends = filterAvailableBackends(matrix, !!user?.is_admin);
  const vadOn = values.vad !== "off";
  const diarizeOn = values.diarize;
  const livePreview = values.streaming;
  const noiseReduce = values.noise;
  const enhanceLevel = values.enhance;

  /**
   * Change 212: Abschicken STARTET den Auftrag. Der Upload/Import legt nur
   * die Aufnahme samt Einstellungen an — eingereiht wird erst hier, sonst
   * wartet die Aufnahme auf einen zweiten Klick auf der Recording-Karte.
   * Fehler beim Start werden gemeldet (kein stiller Fehler).
   */
  const startJob = useCallback(
    async (uid: string, label: string, v: FeatureValues) => {
      try {
        await startTranscription(
          uid,
          v.vad !== "off",
          v.diarize,
          v.streaming,
          v.noise,
          v.enhance,
          v.backend,
          v.punctuation,
          v.llmEnhance,
          v.templateId,
          v.targetId,
          v.endpointId,
          v.numSpeakers ? Number(v.numSpeakers) : undefined,
          diarSensToMinDurationOff(v.diarSens),
          v.diarMethod || undefined,
          v.separate,
          v.vad,
        );
      } catch (e) {
        toast(`${t("job_start_failed")}: ${label} — ${(e as Error).message}`, "err");
      }
    },
    [t, toast],
  );

  /**
   * Change 212: Alle Optionsänderungen laufen über diese eine Stelle
   * (gemeinsames Panel). Alte Werte der Vor-Redesign-Oberfläche („strong")
   * werden auf die Stufe abgebildet, die der Dienst kennt — es kann kein
   * Wert in den Lauf geraten, der dort nichts bewirkt.
   */
  const patchValues = useCallback((patch: Partial<FeatureValues>) => {
    setValues((v) => {
      const next = { ...v, ...patch };
      if (patch.enhance !== undefined) next.enhance = normalizeEnhance(patch.enhance);
      return next;
    });
  }, []);
  const [dupPrompt, setDupPrompt] = useState<{ file: File; batchId: string; existingId: string } | null>(null);

  // ── Change 220 (Nutzer-Vorgabe 20.09.2026): Die URL-Zeile sitzt ÜBER der
  //    Quellen-Auswahl (volle Containerbreite, Beispiel-Adresse als
  //    Platzhalter) und nicht mehr im Bereich darunter. Ihr Zustand liegt
  //    deshalb hier oben — so kann auch der Download-Kreis denselben Absatz
  //    auslösen (Adresse steht schon da, ein Druck startet den Import: kein
  //    wirkungsloser Knopf). Anmeldedaten/Cookies bleiben reiner
  //    Komponenten-Zustand und werden nach dem Import geleert (Change 080).
  const [url, setUrl] = useState("");
  const [isDownloading, setIsDownloading] = useState(false);
  const [showAuth, setShowAuth] = useState(false);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [videoPassword, setVideoPassword] = useState("");
  const [cookiesFile, setCookiesFile] = useState<File | null>(null);

  /**
   * Change 220: Der Aufnahme-Kreis in der Quellen-Reihe ist KEIN zweiter
   * Knopf. Er hält hier nur den Zugriff auf den BESTEHENDEN Aufnahmeknopf im
   * Bereich darunter (RecordTab meldet seine Start/Stop-Funktion an).
   */
  const recordCtl = useRef<{ toggle: () => void } | null>(null);

  /** Change 212/220: Der URL-Import ist ein fertiger Auftrag → sofort starten. */
  const submitUrl = useCallback(async () => {
    if (!url.trim() || isDownloading) return;
    setIsDownloading(true);
    try {
      const result = await importFromUrl(
        url.trim(),
        values.vad !== "off", values.diarize, values.streaming,
        values.noise, values.enhance,
        values.numSpeakers ? Number(values.numSpeakers) : undefined,
        diarSensToMinDurationOff(values.diarSens),
        values.diarMethod || undefined,
        username.trim() || undefined,
        password || undefined,
        videoPassword || undefined,
        cookiesFile,
        values.separate,
        values.vad,
      );
      toast(`Imported${result.original_name ? ": " + result.original_name : ""}`, "ok");
      if (result?.uid) await startJob(result.uid, result.original_name ?? url.trim(), values);
      await qc.invalidateQueries({ queryKey: ["recordings"] });
      await qc.invalidateQueries({ queryKey: ["stats"] });
      setUrl("");
      // Change 080: Anmeldedaten nach dem Import leeren.
      setUsername("");
      setPassword("");
      setVideoPassword("");
      setCookiesFile(null);
      setShowAuth(false);
    } catch (e) {
      toast(`Import failed: ${(e as Error).message}`, "err");
    } finally {
      setIsDownloading(false);
    }
  }, [url, isDownloading, values, username, password, videoPassword, cookiesFile, toast, startJob, qc]);

  /**
   * Auswahl einer Quelle: der Kreis schaltet den Bereich darunter wirklich um.
   * Ist die Quelle schon gewählt, bleibt der Kreis trotzdem wirksam —
   *   Aufnehmen     → startet/stoppt über den bestehenden Aufnahmeknopf,
   *   Download(URL) → startet den Import, wenn eine Adresse eingetragen ist.
   */
  function selectSource(next: "upload" | "record" | "url") {
    setInputMode(next);
  }

  // ── Offline-Puffer: Recovery in der IMMER gemounteten Komponente ──
  // (2026-08-16: lag vorher im RecordTab und lief beim App-Start nicht,
  //  weil der Start-Tab "upload" ist. Jetzt: Auto-Retry beim Start +
  //  bei jedem online-Event, Banner in allen Tabs sichtbar.)
  const [pendingCount, setPendingCount] = useState(0);
  const [retrying, setRetrying] = useState(false);
  // Change 069: Pending-Liste im Banner — Dateiname/Größe sichtbar +
  // Discard pro Eintrag (User-Befund 2026-08-21: „man kann nicht
  // herausfinden was das für eine Datei ist, Discard geht nicht").
  const [pendingRecs, setPendingRecs] = useState<PendingRecording[]>([]);

  const refreshPending = useCallback(async () => {
    const recs = await loadPendingRecordings();
    setPendingRecs(recs);
    setPendingCount(recs.length);
  }, []);

  const discardPending = useCallback(
    async (id: string) => {
      await deletePendingRecording(id);
      await refreshPending();
    },
    [refreshPending],
  );

  const retryPending = useCallback(async () => {
    if (retrying) return;
    setRetrying(true);
    try {
      const recs = await loadPendingRecordings();
      for (const rec of recs) {
        try {
          const res = await fetch("/api/recordings", { method: "POST", body: pendingToFormData(rec) });
          if (!res.ok) {
            // Change 069: Server-Detail durchreichen (z. B. 422 „Audio
            // konnte nicht gelesen werden") — der User soll wissen, was
            // mit der Datei los ist, statt nur „HTTP 500".
            let detail = "";
            try {
              const body = await res.clone().json();
              if (body && typeof body.detail === "string") detail = body.detail;
            } catch {
              // kein JSON-Body
            }
            throw new Error(detail || `HTTP ${res.status}`);
          }
          await res.json();
          await deletePendingRecording(rec.id);
          toast(`Upload ok: ${rec.fileName}`, "ok");
        } catch (e) {
          toast(`Retry fehlgeschlagen (${rec.fileName}): ${(e as Error).message}`, "err");
        }
      }
      await refreshPending();
      await qc.invalidateQueries({ queryKey: ["recordings"] });
    } finally {
      setRetrying(false);
    }
  }, [retrying, refreshPending, toast, qc]);

  // Beim Start + bei jedem online-Event: nach Crash/Device-aus lokal
  // gepufferte Aufnahmen automatisch hochladen.
  useEffect(() => {
    void loadPendingRecordings().then((recs) => {
      setPendingCount(recs.length);
      if (recs.length > 0 && navigator.onLine) void retryPending();
    });
    const onOnline = () => {
      void loadPendingRecordings().then((recs) => {
        setPendingCount(recs.length);
        if (recs.length > 0) void retryPending();
      });
    };
    window.addEventListener("online", onOnline);
    return () => window.removeEventListener("online", onOnline);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
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
    // Change 211 (Nutzer-Befund 19.09.2026): Weitere Auswahl ANHÄNGEN statt
    // ersetzen — mehrfaches „Click to upload" sammelt eine Upload-Liste.
    // Dedupe über Name+Größe+Änderungszeit, damit dieselbe Datei nicht doppelt
    // in der Liste landet.
    setPendingFiles((prev) => {
      const key = (f: File) => `${f.name}|${f.size}|${f.lastModified}`;
      const seen = new Set((prev ?? []).map(key));
      const add = items.filter((f) => !seen.has(key(f)));
      return [...(prev ?? []), ...add];
    });
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
          values.numSpeakers ? Number(values.numSpeakers) : undefined,
          diarSensToMinDurationOff(values.diarSens),
          values.diarMethod || undefined,
          values.separate,
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
          // Change 212: im Sammel-Modus (merged) erst NACH dem Merge starten —
          // sonst liefen die Einzel-Aufträge, die gleich gelöscht werden.
          if (mergeMode !== "merged") await startJob(r.uid, f.name, values);
        }
        uploadedBytes += f.size;
      } catch (e) {
        errors.push(`${f.name}: ${(e as Error).message}`);
        uploadedBytes += f.size;
      }
    }

    if (mergeMode === "merged" && uids.length >= 2) {
      try {
        const merged = await mergeRecordings(uids, batchId);
        toast(`1 ${t("recordings")} · ${t("merged_ok")}`, "ok");
        // Change 212: Der zusammengeführte Auftrag startet ebenfalls sofort.
        if (merged?.uid) await startJob(merged.uid, t("merge_into_one"), values);
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
      // Change 212: Die Kopie ist ein neuer, unverarbeiteter Auftrag → starten.
      if (dup?.uid) await startJob(dup.uid, dupPrompt?.file.name ?? "", values);
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
            values.numSpeakers ? Number(values.numSpeakers) : undefined,
            diarSensToMinDurationOff(values.diarSens),
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

  /**
   * Change 212/220: EIN Optionen-Panel für alle drei Quellen — inhaltlich
   * unverändert (Matrix aus src/optionMatrix.ts, Abschicken startet den
   * Auftrag). Change 220 (Nutzer-Vorgabe 20.09.2026): Das Panel steht jetzt
   * GANZ UNTEN, unter dem Bereich der gewählten Quelle — nicht mehr über den
   * Quellen. Der Zustand bleibt hier oben, damit alle drei Quellen weiterhin
   * denselben Satz Einstellungen benutzen.
   */
  const optionsPanel = (
    <div className="border border-border rounded-sm bg-panel" data-testid="options-panel">
      <button
        type="button"
        onClick={() => setOptsOpen((o) => !o)}
        aria-expanded={optsOpen}
        className="w-full inline-flex items-center gap-[6px] text-[11.5px] font-semibold text-muted px-3 py-2 cursor-pointer hover:text-txt"
      >
        {t("opts_toggle")}
        <ChevronDown size={12} className={`transition-transform ${optsOpen ? "rotate-180" : ""}`} />
      </button>
      {optsOpen && (
        <div className="px-2 pb-2">
          <OptionsPanel
            source={inputMode}
            values={values}
            backends={availableBackends}
            caps={caps}
            flags={flags}
            pp={{ templates, targets, endpoints, isOidc }}
            action="tr"
            onChange={patchValues}
          />
        </div>
      )}
    </div>
  );

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
      {/* ── Change 222 (Nutzer-Vorgabe 20.09.2026): Quellen-Auswahl ──
          Die drei Zeichen sind NACKTE Umschalter — kein Kreis, kein Text, keine
          Bewegung. Die Kreise selbst sitzen jetzt IN der jeweiligen Zone (also
          in der Ablegefläche bzw. der Adress-Zone), in derselben Größe wie der
          Aufnahmeknopf. Die Adress-Zeile ist ebenfalls in ihre Zone gewandert
          (Nutzer: „Die Download URL Zeile muss mit in die drop-area").
          Der gewählte Umschalter ist doppelt kodiert: grünes Zeichen UND
          grüner Strich darunter (siehe .ps-src-tab-on in index.css). */}
      <div className="ps-source-row" data-testid="source-row" role="group" aria-label={t("src_picker_label")}>
        <SourceTab
          kind="upload"
          label={t("src_upload")}
          selected={inputMode === "upload"}
          disabled={recording}
          onSelect={() => selectSource("upload")}
        />
        <SourceTab
          kind="record"
          label={t("src_record")}
          selected={inputMode === "record"}
          onSelect={() => {
            if (inputMode === "record") recordCtl.current?.toggle();
            else selectSource("record");
          }}
        />
        <SourceTab
          kind="download"
          label={t("src_download")}
          selected={inputMode === "url"}
          disabled={recording}
          onSelect={() => selectSource("url")}
        />
      </div>

      {/* Tab content */}
      {pendingCount > 0 && (
        <div className="w-full bg-[rgba(217,158,43,.1)] border border-[#d99e2b]/40 rounded-sm px-3 py-2 mt-2">
          <div className="flex items-center gap-2">
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
          {/* Change 069: Pending-Liste — Dateiname/Größe sichtbar + Discard */}
          <ul className="mt-1.5 space-y-1">
            {pendingRecs.map((pr) => (
              <li key={pr.id} className="flex items-center gap-2 text-[11px] text-fg-muted">
                <span className="truncate flex-1" title={pr.fileName}>
                  🎙 {pr.fileName}
                </span>
                <span className="whitespace-nowrap text-muted2">
                  {pr.blob.size > 0 ? fmtBytes(pr.blob.size) : "0 B"} · {new Date(pr.createdAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                </span>
                <button
                  onClick={() => void discardPending(pr.id)}
                  disabled={retrying}
                  className="text-err hover:underline disabled:opacity-40 whitespace-nowrap"
                  title="Lokale Aufnahme verwerfen"
                >
                  ✕ Discard
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
      {inputMode === "upload" && (
        <div className="ps-tab-body" data-testid="area-upload">
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
        </div>
      )}
      {inputMode === "record" && (
        <div data-testid="area-record">
        <RecordTab
          ctlRef={recordCtl}
          setIsUploading={setIsUploading}
          onRecordingChange={setRecording}
          toast={toast}
          qc={qc}
          t={t}
          vadOn={vadOn} diarizeOn={diarizeOn}
          livePreview={livePreview} noiseReduce={noiseReduce} enhanceLevel={enhanceLevel}
          refreshPending={refreshPending}
          onStartJob={(uid: string, label: string) => startJob(uid, label, values)}
        />
        </div>
      )}
      {inputMode === "url" && (
        <UrlArea
          t={t}
          onSubmit={() => void submitUrl()}
          canSubmit={!!url.trim()}
          url={url}
          setUrl={setUrl}
          isDownloading={isDownloading}
          showAuth={showAuth} setShowAuth={setShowAuth}
          username={username} setUsername={setUsername}
          password={password} setPassword={setPassword}
          videoPassword={videoPassword} setVideoPassword={setVideoPassword}
          setCookiesFile={setCookiesFile}
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

      {/* ── Change 220 (Nutzer-Vorgabe 20.09.2026): Das Optionen-Panel steht
          GANZ UNTEN — unter der Quellen-Auswahl und unter dem Bereich der
          gewählten Quelle. Inhaltlich unverändert (Change 212). ── */}
      {optionsPanel}

      {/* CPU/GPU-Badge ist in die Stats-Leiste (Header) gewandert (Settings-UI-Task). */}
    </div>
  );
}

// ── Tab button ──
// Change 220 (Nutzer-Vorgabe 20.09.2026): Die frühere Tab-Leiste ist entfallen.
// Die Quellen-Auswahl sind jetzt die drei Kreis-Knöpfe (SourceCircle.tsx) —
// eine zweite Bedienleiste daneben würde nur doppelt anbieten, was es schon gibt.

// ── Upload tab ──

function UploadTab({ isUploading, uploadProgress, uploadName, active, handleClick, handleKeyDown, handleDragOver, handleDragLeave, handleDrop, handleInputChange, fileRef, t }: any) {
  return (
    <Zone
      variant="dashed"
      role="button"
      tabIndex={0}
      aria-label={t("drag_zone")}
      onClick={handleClick}
      onKeyDown={handleKeyDown}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      className={`ps-zone-drop${active ? " ps-zone-active" : ""}`}
    >
      <div className="ps-zone-stack">
        {isUploading ? (
          <>
            <div className="ps-zone-icon" aria-hidden="true">⏳</div>
            <div className="ps-zone-bar">
              <div style={{ width: `${uploadProgress}%` }} />
            </div>
            <div className="ps-zone-hint">
              {uploadProgress}%{uploadName ? ` · 📄 ${uploadName}` : ""}
            </div>
            <div className="ps-zone-title">{t("uploading")}</div>
          </>
        ) : (
          <>
            {/* Change 222: Der Kreis sitzt IN der Ablegefläche — mit Zeichen und
                der stillen, oben gekrümmten Beschriftung „Upload". Die Zone
                selbst bleibt die Ablegefläche (Klick und Ziehen); der Klick auf
                den Kreis wird deshalb nicht weitergereicht, sonst liefe die
                Dateiauswahl zweimal.
                Der Formathinweis („MP3, M4A, WAV …") ist entfallen — Nutzer:
                „bei Upload können wir die Formate weglassen, too much
                information". */}
            <ZoneCircle
              kind="upload"
              testId="upload"
              label={t("src_upload")}
              disabled={isUploading}
              onActivate={() => handleClick()}
              buttonClassName="ps-zone-activate"
            />
            <div className="ps-zone-title">{t("drag_here")}</div>
            <div className="ps-zone-hint">{t("multi_files")}</div>
          </>
        )}
      </div>
      <input
        ref={fileRef}
        type="file"
        accept="audio/*"
        multiple
        className="hidden"
        onChange={handleInputChange}
      />
    </Zone>
  );
}

// ── Record tab ──

function RecordTab({ ctlRef, setIsUploading, onRecordingChange, toast, qc, t, vadOn, diarizeOn, livePreview, noiseReduce, enhanceLevel, refreshPending, onStartJob }: any) {
  const [recording, setRecording] = useState(false);
  const [paused, setPaused] = useState(false);
  const [continuous, setContinuous] = useState(false);
  // Change 216 (Nutzer-Vorgabe 20.09.2026): Die Hinweise stehen nicht mehr
  // als Block neben dem Knopf, sondern als halbtransparente Kopie ÜBER ihm.
  // Die Reihenfolge und die Bewegung stehen in RecordGestureHint.tsx.
  const [tipIdx, setTipIdx] = useState(0);
  useEffect(() => {
    // Change 222: Während einer Aufnahme stehen die Hinweise still — es gibt
    // dann nichts zu wechseln (sie sind ausgeblendet, siehe RecordGestureHint).
    if (recording) return;
    const id = window.setInterval(
      () => setTipIdx((i) => (i + 1) % RECORD_GESTURE_TIPS.length),
      2600
    );
    return () => window.clearInterval(id);
  }, [recording]);
  const [uploadPhase, setUploadPhase] = useState<"idle" | "saving" | "processing" | "uploading" | "done">("idle");
  const [uploadPct, setUploadPct] = useState(0);
  const [wakelock, setWakelock] = useState<WakeLockSentinel | null>(null);
  const [duration, setDuration] = useState(0);
  const [micDevices, setMicDevices] = useState<MediaDeviceInfo[]>([]);
  const [micDeviceId, setMicDeviceId] = useState<string>(() =>
    localStorage.getItem("ps_mic_device") ?? ""
  );
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

  // ── Periodischer Crash-Snapshot (2026-08-16) ──
  // Ein zweiter MediaRecorder (Timeslice 5 s) auf demselben Stream
  // schreibt den bisherigen Aufnahmestand regelmässig nach IndexedDB.
  // Wenn die App während der Aufnahme crasht/abgeschaltet wird, bleibt
  // der letzte Stand im Offline-Puffer und wird beim nächsten Start
  // automatisch hochgeladen (statt die ganze Aufnahme zu verlieren).
  const snapshotRecRef = useRef<MediaRecorder | null>(null);
  const snapshotChunksRef = useRef<Blob[]>([]);
  const snapshotPendingRef = useRef<PendingRecording | null>(null);
  /** Change 211 (Nutzer-Befund 19.09.2026): Timer für die Mindesthaltedauer —
   *  eine neue Aufnahme startet erst nach ~350 ms Halten, damit ein kurzer
   *  Tipp keine 0,2-Sekunden-Aufnahme erzeugt. */
  const holdTimerRef = useRef<number | null>(null);

  // Change 211 (Nutzer-Vorgabe 19.09.2026): Die einmalige Anleitung beim ersten
  // Besuch entfällt — die Gestenhilfe ist jetzt dauerhaft sichtbar. Der frühere
  // localStorage-Merker („ps_pushtorecord_help_seen") wird nicht mehr gebraucht.

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
  //
  // iOS-Härtung (Change 016, 2026-08-18): WaveSurfer 7 setzt bei jedem
  // WebAudio-Player-Start navigator.audioSession.type = "playback"
  // (webaudio.js::setWebAudioSessionPlayback). WebKit verbietet dann
  // getUserMedia mit "AudioSession category is not compatible with audio
  // capture" (Audio-Session-Spec §6.3: nur play-and-record/auto erlauben
  // den Mikrofon-Track). Vor jedem Mikrofon-Zugriff wird die Session
  // deshalb explizit auf play-and-record gesetzt (nur WebKit; andere
  // Browser haben kein navigator.audioSession → still ignoriert).
  // Helfer lebt in src/audioSession.ts (testbar, Change 016).

  async function prewarmMic() {
    // iOS/macOS-Safari (WebKit): KEIN Pre-Warm. Das Mikro bliebe sonst
    // dauerhaft geöffnet — iOS zeigt den Aktiv-Indikator permanent, und
    // die play-and-record-Session wird nie freigegeben (Datenschutz-
    // Befund 2026-08-18). Der Stream wird dort erst beim echten
    // Record-Start geholt (startRecording → ensureAudioSessionForRecording
    // + getUserMedia im RecordPlugin).
    if (isWebKitAudioSession()) return;
    if (micStreamRef.current) return; // schon warm
    if (prewarmInFlight.current) return prewarmInFlight.current; // dedupe
    prewarmInFlight.current = (async () => {
      try {
        const audio: MediaTrackConstraints = {
          noiseSuppression: false,
          echoCancellation: false,
          autoGainControl: true,
        };
        if (micDeviceId) {
          audio.deviceId = { exact: micDeviceId };
        }
        ensureAudioSessionForRecording();
        const stream = await navigator.mediaDevices.getUserMedia({ audio });
        micStreamRef.current = stream;
        // Geräteliste nachführen (IDs sind erst nach Permission sichtbar)
        void refreshMicDevices();
      } catch (e) {
        // Kein Zugriff — startRecording zeigt dann den Fehler-Toast.
        // Change 016: Ursache loggen (stille Fehler inakzeptabel), damit
        // Permission-Ablehnung vs. AudioSession-Konflikt unterscheidbar ist.
        console.warn("mic prewarm failed:", (e as Error)?.message ?? e);
      } finally {
        prewarmInFlight.current = null;
      }
    })();
    return prewarmInFlight.current;
  }

  // Verfügbare Mikrofon-Inputs auflisten (nur audioinput, mit Label wenn
  // erlaubt). Nach Permission-Aufruf erneut aufrufen — erst dann sind die
  // deviceLabels sichtbar.
  async function refreshMicDevices() {
    try {
      const all = await navigator.mediaDevices.enumerateDevices();
      const mics = all.filter((d) => d.kind === "audioinput");
      setMicDevices(mics);
      // Auswahl validieren: gewählte ID noch vorhanden? Sonst Default ("").
      if (micDeviceId && !mics.some((m) => m.deviceId === micDeviceId)) {
        setMicDeviceId("");
        localStorage.removeItem("ps_mic_device");
      }
    } catch {
      // enumerateDevices nicht verfügbar — kein Dropdown anzeigen.
    }
  }

  function onMicDeviceChange(e: React.ChangeEvent<HTMLSelectElement>) {
    const id = e.target.value;
    setMicDeviceId(id);
    if (id) localStorage.setItem("ps_mic_device", id);
    else localStorage.removeItem("ps_mic_device");
    // Laufenden Stream mit neuem Gerät ersetzen → nächster Start nutzt es
    micStreamRef.current?.getTracks().forEach((t) => t.stop());
    micStreamRef.current = null;
    void prewarmMic();
  }

  // Beim ersten Betreten des Record-Tabs den Stream vorab anfordern —
  // damit Permission-Prompt/Stream-Start NICHT beim ersten Knopfdruck
  // passieren (das war der spürbare Delay).
  useEffect(() => {
    void prewarmMic();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Bei Änderung der gewählten deviceId: neu prewarmen (Wechsel + Erstwahl)
  useEffect(() => {
    micStreamRef.current?.getTracks().forEach((t) => t.stop());
    micStreamRef.current = null;
    void prewarmMic();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [micDeviceId]);

  async function startRecording() {
    acquireWakeLock();
    onRecordingChange(true);
    chunksRef.current = [];

    // Crash-Snapshot: Grunddaten vorab festlegen — der finale Upload
    // (record-end) nutzt dieselbe id und überschreibt den Snapshot.
    snapshotChunksRef.current = [];
    snapshotPendingRef.current = {
      id: crypto.randomUUID(),
      blob: new Blob([], { type: "audio/webm" }),
      fileName: `recording_${Date.now()}.webm`,
      mime: "audio/webm",
      createdAt: Date.now(),
      vad: vadOn,
      diarize: diarizeOn,
      streaming: livePreview,
      separate: "none",
      noiseReduce,
      enhance: enhanceLevel,
    };

    // Create WaveSurfer with Record plugin
    // Change 224 (Nutzer-Design-Idee: „wie wäre es wenn die Wellenform den
    // Background der ‚Drop Zone' langsam mit den aufgenommenen Wellen füllt"):
    // `scrollingWaveform: false` — die Wellen laufen nicht mehr als 60-px-Band
    // durch, sondern wachsen von links nach rechts über die GANZE Zonenfläche
    // und füllen sie langsam. Die Höhe kommt deshalb von der Fläche selbst
    // (WaveSurfer zeichnet genau `height` px hoch), nicht mehr als fester Wert.
    const record = RecordPlugin.create({
      scrollingWaveform: false,
      renderRecordedAudio: false,  // we handle upload ourselves
    });

    const flaechenhoehe = Math.max(60, Math.round(containerRef.current!.clientHeight));

    const ws = WaveSurfer.create({
      container: containerRef.current!,
      waveColor: "rgba(91,140,255,0.3)",
      progressColor: "rgba(91,140,255,0.8)",
      barWidth: 2,
      barGap: 1,
      barRadius: 2,
      height: flaechenhoehe,
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
      // Crash-Snapshot stoppen — ab jetzt wird kein Chunk mehr gesammelt
      // (Guard oben), damit der letzte dataavailable den finalen Eintrag
      // nicht überschreibt. Der finale Blob nutzt dieselbe id und ersetzt
      // den letzten Snapshot im IndexedDB-Puffer.
      const snapshotId = snapshotPendingRef.current?.id;
      snapshotPendingRef.current = null;
      snapshotRecRef.current?.stop();
      snapshotRecRef.current = null;

      clearInterval(timerRef.current);
      setDuration(0);
      setPaused(false);
      setContinuous(false);
      ws.destroy();
      wsRef.current = null;
      recordRef.current = null;
      // Stream freigeben (Safety Net) — nächster Start prewarmt neu.
      // iOS (WebKit): Session zurücksetzen, kein Prewarm (Mikro sonst
      // dauerhaft aktiv, 2026-08-18).
      micStreamRef.current?.getTracks().forEach((t) => t.stop());
      micStreamRef.current = null;
      restoreAudioSessionAfterRecording();
      if (!isWebKitAudioSession()) void prewarmMic();

      releaseWakeLock();
      setIsUploading(true);

      // 1) SOFORT lokal sichern (IndexedDB) — bevor irgendetwas anderes
      //    passieren kann. Netzabriss/Serverfehler dürfen die Aufnahme
      //    nicht mehr vernichten: der Blob überlebt, bis der Upload
      //    nachweislich erfolgreich war.
      setUploadPhase("saving");
      const ext = blob.type.includes("mp4") ? ".mp4" : ".webm";
      const pending: PendingRecording = {
        id: snapshotId ?? crypto.randomUUID(),
        blob,
        fileName: `recording_${Date.now()}${ext}`,
        mime: blob.type,
        createdAt: Date.now(),
        vad: vadOn,
        diarize: diarizeOn,
        streaming: livePreview,
        noiseReduce,
        enhance: enhanceLevel,
        // Change 106 v1: Upload-Pfad ohne Separate — die Wahl liegt beim
        // Re-Transcribe auf der Karte (FeatureToggles).
        separate: "none",
      };
      await savePendingRecording(pending);
      void refreshPending();

      try {
        // 2) Peak-normalize (kann bei langen Aufnahmen dauern — Feedback zeigen)
        setUploadPhase("processing");
        const normBlob = await normalizePeak(blob);
        const batchId = pending.id;

        // 3) Upload mit sichtbarem Fortschritt
        setUploadPhase("uploading");
        setUploadPct(0);
        const rec = await recordFromMic(normBlob, batchId, vadOn, diarizeOn, livePreview, noiseReduce, enhanceLevel, (pct) => setUploadPct(pct));
        await deletePendingRecording(pending.id); // Upload bestätigt → Puffer leeren
        void refreshPending();
        setUploadPhase("done");
        // Change 212: Abschicken startet den Auftrag — die Aufnahme bleibt
        // nicht als „wartend" liegen und braucht keinen zweiten Klick.
        if (rec?.uid) await onStartJob(rec.uid, pending.fileName);
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
      ensureAudioSessionForRecording();
      try {
        await record.startRecording({
          noiseSuppression: false,
          echoCancellation: false,
          autoGainControl: true,
        });
      } catch (e) {
        // Change 016 (iOS): WaveSurfer-Player (Recording-Liste) setzen die
        // AudioSession auf "playback" — WebKit blockiert dann getUserMedia
        // mit "AudioSession category is not compatible with audio capture".
        // Falls die Session zwischen Pre-Warm und Start gedriftet ist,
        // explizit neu setzen und EINMAL erneut versuchen (Sicherheitsnetz;
        // Permission-Ablehnungen lösen keinen Retry aus).
        const msg = (e as Error)?.message ?? "";
        if (msg.includes("AudioSession category")) {
          ensureAudioSessionForRecording();
          await record.startRecording({
            noiseSuppression: false,
            echoCancellation: false,
            autoGainControl: true,
          });
        } else {
          throw e;
        }
      }

      // Crash-Snapshot: zweiter MediaRecorder auf demselben Stream —
      // alle 5 s wird der bisherige Stand nach IndexedDB geschrieben.
      if (micStreamRef.current && typeof MediaRecorder !== "undefined") {
        const snap = new MediaRecorder(micStreamRef.current, {
          audioBitsPerSecond: 128000,
        });
        snap.ondataavailable = (e) => {
          if (e.data.size === 0 || !snapshotPendingRef.current) return;
          snapshotChunksRef.current.push(e.data);
          const partial = new Blob(snapshotChunksRef.current, {
            type: snap.mimeType || "audio/webm",
          });
          void savePendingRecording({
            ...snapshotPendingRef.current!,
            blob: partial,
            mime: partial.type,
          });
        };
        snap.start(5000);
        snapshotRecRef.current = snap;
      }
      record.on("record-pause", () => snapshotRecRef.current?.pause());
      record.on("record-resume", () => snapshotRecRef.current?.resume());
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
    // Stream freigeben + sofort neu prewarmen → nächster Start ohne Delay.
    // iOS (WebKit): NICHT neu prewarmen und die AudioSession zurücksetzen —
    // sonst bleibt das Mikro dauerhaft aktiv (Indikator) und die
    // play-and-record-Session wird nie freigegeben (2026-08-18).
    micStreamRef.current?.getTracks().forEach((t) => t.stop());
    micStreamRef.current = null;
    restoreAudioSessionAfterRecording();
    if (!isWebKitAudioSession()) void prewarmMic();
    setRecording(false);
    setPaused(false);
    setContinuous(false);
  }

  // ── Change 220 (Nutzer-Vorgabe 20.09.2026): Der Quellen-Kreis „Aufnehmen"
  //    ist KEIN zweiter Knopf und hat keinen eigenen Zustand: er delegiert an
  //    genau diesen bestehenden Aufnahmeknopf (starten/stoppen). Die Funktionen
  //    werden nach jedem Rendern veröffentlicht — der Kreis arbeitet damit
  //    immer mit dem aktuellen Stand (laufende Aufnahme, Pause, Mikrofonwahl)
  //    und kann nie ins Leere greifen. Beim Verlassen des Bereichs wird
  //    abgemeldet, damit kein alter Aufruf liegen bleibt.
  useEffect(() => {
    if (!ctlRef) return;
    ctlRef.current = {
      toggle: () => {
        if (recording) void stopRecording();
        else void startRecording();
      },
    };
    return () => {
      ctlRef.current = null;
    };
  });

  // ── Mobile Push-to-Record Gesten ──
  // Drücken = aufnehmen / fortsetzen · Loslassen = Pause (gleiche Datei!)
  // Swipe ↑ = Daueraufnahme · Swipe ↓ = Stop + Upload

  function onTouchStart(e: React.TouchEvent) {
    // Default verhindern: Der Browser darf den Touch nicht als Scroll-Geste
    // interpretieren (sonst hüpft die Seite beim Drücken des Buttons).
    e.preventDefault();
    touchStartY.current = e.touches[0]?.clientY ?? null;
    touchStartT.current = Date.now();
    gestureDone.current = false;

    if (recording && paused) {
      // Fortsetzen nach Pause — weiter in dieselbe Datei (sofort, kein Halten nötig)
      recordRef.current?.resumeRecording();
      setPaused(false);
      timerRef.current = window.setInterval(() => setDuration((d) => d + 1), 1000);
    } else if (!recording && !paused) {
      // Change 211 (Nutzer-Befund 19.09.2026): Eine neue Aufnahme startet erst
      // nach kurzem HALTEN (~350 ms). Ein versehentlicher kurzer Tipp erzeugte
      // vorher 0,2-Sekunden-Fragmente. Loslassen vor Ablauf → nur Hinweis.
      holdTimerRef.current = window.setTimeout(() => {
        holdTimerRef.current = null;
        void startRecording();
      }, 350);
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
    // Change 211 (Nutzer-Befund 19.09.2026): Kurzer Tipp (unter der
    // Mindesthaltedauer) startet KEINE Aufnahme — stattdessen der Hinweis,
    // dass nur beim Halten aufgenommen wird.
    if (holdTimerRef.current !== null) {
      window.clearTimeout(holdTimerRef.current);
      holdTimerRef.current = null;
      toast(t("push_gesture_hold"), "info");
      touchStartY.current = null;
      return;
    }
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
      // Record-Tab verlassen (auch mitten in der Aufnahme): Mic-Stream
      // stoppen + AudioSession zurücksetzen — sonst bleibt das Mikro auf
      // iOS dauerhaft aktiv (Indikator, 2026-08-18).
      micStreamRef.current?.getTracks().forEach((t) => t.stop());
      micStreamRef.current = null;
      restoreAudioSessionAfterRecording();
    };
  }, []);

  const fmt = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;

  // Change 217: Status für die eine kompakte Zeile unter der Zone. Auf
  // Touch-Geräten steht die Geste schon in der Hinweiszeile der Kopie —
  // dort bleibt nur die Uhrzeit (kein doppelter Hinweis, keine zweite Zeile).
  const statusText = !recording
    ? t("rec_btn")
    : paused
      ? t("push_record_paused")
      : isTouch
        ? null
        : t("push_record_continuous");

  return (
    <div className="ps-tab-body">
      {/* Change 217 (Nutzer-Vorgabe 20.09.2026): Die Wellenform belegt im
          Ruhezustand KEINEN Platz mehr.
          Change 224 (Nutzer: „Push to record schiebt den Button durch das
          einblenden der Waveform nach unten. Können wir die Waveform in den
          Hintergrund der area einblenden, so daß sich das Layout nicht
          verändert?"): Deshalb ist sie jetzt GAR KEIN Geschwister der Zone
          mehr, sondern deren HINTERGRUND-Schicht (`.ps-record-wave`, absolut,
          z-index 0) — siehe den Block direkt in der Zone unten. Damit kann sie
          das Layout weder im Ruhezustand noch beim Einblenden verschieben, und
          der Knopf bleibt stehen, wo er ist. */}

      {/* Offline-Puffer-Banner: liegt jetzt in der Hauptkomponente
          (UploadZone), damit er in allen Tabs + beim App-Start sichtbar ist. */}

      {/* Change 211 (Nutzer-Vorgabe 19.09.2026): Die einmalige Gesten-Anleitung
          (Modal mit „Verstanden") ist entfernt — an ihre Stelle tritt die
          dauerhafte, animierte Hilfe direkt am Record-Knopf. */}

      {/* Aufnahme-Button — Mobile: Push-to-Record, Desktop: wie bisher.
          Change 215: Der Aufnahmeknopf steht in derselben Zone wie die anderen
          Quellen — Linienart durchgezogen, Maße identisch.
          Change 216 (Nutzer-Vorgabe 20.09.2026): Der Knopf steht MITTIG in der
          Zone. Die Hinweise stehen nicht mehr als Block daneben, sondern als
          halbtransparente Kopie ÜBER dem Knopf (RecordGestureHint). Die Kopie
          liegt absolut in `.ps-record-stage` und kann die Knopfposition
          deshalb nicht verändern. */}
      <Zone variant="solid" className="ps-zone-record">
        {/* Wellenform als HINTERGRUND der Zone (Change 224): absolut, deckt die
            Zone ab, ohne je Platz zu belegen — der Knopf kann sich beim
            Einblenden deshalb nicht verschieben (Nutzer: „so daß sich das Layout
            nicht verändert?"). Sie liegt hinter der Bühne (z-index 0 gegen 1)
            und nimmt keine Klicks an. */}
        <div
          ref={containerRef}
          data-testid="record-wave"
          className={`ps-record-wave${recording ? " ps-record-wave--an" : ""}`}
        />
        <div className="ps-record-stage">
          <button
            data-testid="record-button"
            onClick={isTouch ? undefined : (recording ? stopRecording : startRecording)}
            onTouchStart={isTouch ? onTouchStart : undefined}
            onTouchMove={isTouch ? onTouchMove : undefined}
            onTouchEnd={isTouch ? onTouchEnd : undefined}
            onTouchCancel={isTouch ? onTouchCancel : undefined}
            className={`ps-record-btn ${RECORD_BUTTON_SHAPE} text-xl sm:text-2xl flex items-center justify-center transition-all shrink-0 select-none touch-none
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
            {recording
              ? paused
                ? <svg width="28" height="28" viewBox="0 0 24 24" aria-hidden="true" focusable="false" style={{ display: "block" }}><rect x="7" y="5.5" width="3.6" height="13" rx="1.2" fill="#d99e2b"/><rect x="13.4" y="5.5" width="3.6" height="13" rx="1.2" fill="#d99e2b" fillOpacity="0.6"/></svg>
                : continuous
                  ? <svg width="28" height="28" viewBox="0 0 24 24" aria-hidden="true" focusable="false" style={{ display: "block" }}><circle cx="12" cy="12" r="9" fill="var(--ps-err, #f85149)" fillOpacity="0.25"/><circle cx="12" cy="12" r="6" fill="var(--ps-err, #f85149)"/></svg>
                  : <svg width="28" height="28" viewBox="0 0 24 24" aria-hidden="true" focusable="false" style={{ display: "block" }}><rect x="4.5" y="4.5" width="15" height="15" rx="2.5" fill="var(--ps-err, #f85149)" fillOpacity="0.3"/><rect x="7.5" y="7.5" width="9" height="9" rx="1.5" fill="var(--ps-err, #f85149)"/></svg>
              : <SourceIcon kind="record" size={28} />}
          </button>

          {/* Change 216: halbtransparente Kopie des Knopfes + eine Zeile Text.
              Nur auf Touch-Geräten — dort gibt es die Wischgesten. */}
          {isTouch && (
            <RecordGestureHint
              tipIdx={tipIdx}
              label={t(gestureTipAt(tipIdx).key)}
              verdeckt={recording}
            />
          )}
        </div>
      </Zone>

      {/* Change 217 (Nutzer-Vorgabe 20.09.2026): Eingangsquelle (Mikrofon),
          Aufnahmezeit und Status stehen in EINER kompakten Zeile unter der
          Zone. Vorher waren das drei eigene Blöcke (Mikrofon-Auswahl,
          Statuszeile, große Aufnahmezeit 22/28 px) — sie machten den Tab
          höher als die anderen. Diese Zeile ist jetzt gleich hoch wie die
          eine Zeile der anderen Tabs. */}
      <div className="ps-tab-line">
        <span className="tabular-nums font-mono font-semibold text-txt">{fmt(duration)}</span>
        {statusText ? (
          <>
            <span aria-hidden="true">·</span>
            <span className={paused && recording ? "text-[#d99e2b] font-semibold" : undefined}>
              {statusText}
            </span>
          </>
        ) : null}
        {micDevices.length > 1 && !recording && (
          <label className="inline-flex items-center gap-1">
            <span aria-hidden="true">🎙</span>
            <span className="sr-only">{t("mic_select_label")}</span>
            <select
              value={micDeviceId}
              onChange={onMicDeviceChange}
              aria-label={t("mic_select_label")}
              className="bg-panel2 border border-border rounded-sm px-1 text-[11px] leading-none h-[18px] text-txt max-w-[150px]"
            >
              <option value="">{t("mic_select_default")}</option>
              {micDevices.map((d) => (
                <option key={d.deviceId} value={d.deviceId}>
                  {d.label || `${t("mic_select_unnamed")} ${d.deviceId.slice(0, 4)}…`}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>

      {/* Nur während/nach einer Aufnahme — im Ruhezustand nicht vorhanden,
          damit kein Element die Tab-Höhe vergrößert. */}
      {wakelock && (
        <div className="text-[11px] text-muted2 flex items-center gap-1">
          <span>🔒</span> {t("rec_wakelock")}
        </div>
      )}

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

function UrlArea({
  t,
  onSubmit,
  canSubmit,
  isDownloading,
  url,
  setUrl,
  showAuth,
  setShowAuth,
  username,
  setUsername,
  password,
  setPassword,
  videoPassword,
  setVideoPassword,
  setCookiesFile,
}: {
  t: ReturnType<typeof useT>["t"];
  /** Change 220: Der Absatz liegt in der URL-Zeile bzw. am Download-Kreis. */
  onSubmit: () => void;
  /** Steht eine Adresse in der Zeile? Ohne Adresse ist der Absatz gesperrt. */
  canSubmit: boolean;
  isDownloading: boolean;
  /** Change 222: Die Adress-Zeile lebt jetzt IN dieser Zone („drop-area") —
   *  sie kommt wie zuvor aus UploadZone, nur der Ort hat sich geändert. */
  url: string;
  setUrl: (v: string) => void;
  /** Change 080: optionale Anmeldedaten — reiner Komponenten-Zustand in
   *  UploadZone, wird nach dem Import geleert und nie persistiert. */
  showAuth: boolean;
  setShowAuth: React.Dispatch<React.SetStateAction<boolean>>;
  username: string;
  setUsername: (v: string) => void;
  password: string;
  setPassword: (v: string) => void;
  videoPassword: string;
  setVideoPassword: (v: string) => void;
  setCookiesFile: (f: File | null) => void;
}) {
  return (
    <div className="ps-tab-body" data-testid="area-url">
      {/* Change 215: dieselbe Zone wie im Upload- und Aufnahme-Tab.
          Change 220 (Nutzer-Vorgabe 20.09.2026): Die Eingabezeile ist aus der
          Zone heraus nach OBEN gewandert (direkt über die Quellen-Kreise,
          volle Containerbreite). Hier bleibt der Bereich der Quelle „Download":
          Symbol, Zustand und die optionale Anmeldung — die Zone behält
          unverändert ihre festen Maße aus Change 215. */}
      <Zone variant="solid" className="ps-zone-url" waechst>
        <div className="ps-zone-stack">
          {/* Change 222 (Nutzer-Vorgabe 20.09.2026): Die Adress-Zeile steht IN
              der Zone („Die Download URL Zeile muss mit in die drop-area") —
              gleiche Zone, gleiche Maße wie in den anderen Tabs (Change 215).
              Ganz oben, weil sie die Eingabe dieser Fläche ist; darunter der
              Kreis „Download" mit der stillen, unter dem Kreis stehenden
              Beschriftung, der den Import startet. Der frühere Absatz-Knopf ist
              entfallen: der Kreis IST der Knopf, ein zweiter wäre doppelt. */}
          <div className="ps-url-row" data-testid="url-line">
            <label className="sr-only" htmlFor="ps-url-input">{t("url_line_label")}</label>
            <input
              id="ps-url-input"
              data-testid="url-input"
              type="url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder={t("url_placeholder")}
              autoComplete="off"
              spellCheck={false}
              className="ps-url-input"
              onKeyDown={(e) => { if (e.key === "Enter") onSubmit(); }}
            />
          </div>
          {/* Change 223 (Nutzer-Vorgabe 20.09.2026): Die Beschriftung des
              Kreises steht hier UNTER dem Kreis („Mache die Button Beschreibung
              unten an den Kreis") — der Kreis selbst bleibt an derselben
              Position. Die frühere Erklärzeile darüber ist entfallen: „mit dem
              Beispieltext in der textarea und dem mit Download beschrifteten
              Button erklärt sich die Funktion". */}
          <ZoneCircle
            kind="download"
            testId="download"
            labelSide="bottom"
            label={isDownloading ? t("url_downloading") : t("src_download")}
            disabled={!canSubmit || isDownloading}
            onActivate={onSubmit}
          />

          {/* Change 225 (Nutzer-Vorgabe 20.09.2026): „Der ‚Credentials' knopf für
              den download muss vom layout überarbeitet werden. Er muss mit in
              die ‚Dropzone' und soll wie alle anderen ausklappbaren Ebenen auch
              aussehen. Die ausklappenden Optionen müssen mit in die drop zone
              und diese, animiert, nach unten vergrößern."
              Deshalb: derselbe Aufbau wie das Optionen-Panel (Rahmen, Zeile mit
              Chevron, der sich beim Öffnen dreht) und der Inhalt darunter in
              `.ps-zone-fold` — die Zone wächst dadurch animiert nach unten. */}
          <div
            className="w-full border border-border rounded-sm bg-panel"
            data-testid="auth-fold"
          >
            <button
              type="button"
              data-testid="auth-toggle"
              onClick={() => setShowAuth((s) => !s)}
              aria-expanded={showAuth}
              className="w-full inline-flex items-center gap-[6px] text-[11.5px] font-semibold text-muted px-3 py-2 cursor-pointer hover:text-txt"
            >
              {t("url_auth_toggle")}
              <ChevronDown size={12} className={`transition-transform ${showAuth ? "rotate-180" : ""}`} />
            </button>
            <div
              className={`ps-zone-fold${showAuth ? " ps-zone-fold--offen" : ""}`}
              data-testid="auth-fold-body"
            >
              <div className="px-2 pb-2 flex flex-col gap-2">
                <div className="flex flex-col sm:flex-row gap-2">
                  <input
                    type="text"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    placeholder={t("url_username")}
                    autoComplete="off"
                    className="flex-1 bg-panel border border-border2 rounded-sm px-3 py-2 text-[13px] text-txt outline-none focus:border-accent"
                  />
                  <input
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder={t("url_password")}
                    autoComplete="new-password"
                    className="flex-1 bg-panel border border-border2 rounded-sm px-3 py-2 text-[13px] text-txt outline-none focus:border-accent"
                  />
                </div>
                <input
                  type="password"
                  value={videoPassword}
                  onChange={(e) => setVideoPassword(e.target.value)}
                  placeholder={t("url_video_password")}
                  autoComplete="new-password"
                  className="w-full bg-panel border border-border2 rounded-sm px-3 py-2 text-[13px] text-txt outline-none focus:border-accent"
                />
                <label className="flex items-center gap-2 text-[12px] text-muted cursor-pointer">
                  <input
                    type="file"
                    accept=".txt"
                    onChange={(e) => setCookiesFile(e.target.files?.[0] ?? null)}
                    className="text-[12px]"
                  />
                  {t("url_cookies")}
                </label>
                <div className="text-[11px] text-muted">{t("url_cookies_hint")}</div>
              </div>
            </div>
          </div>
        </div>
      </Zone>
    </div>
  );
}

/* ─────────────────────────────────────────────── */

// Task 9: ToggleSwitch entfernt — die Feature-Toggles leben jetzt in
// FeatureToggles.tsx an der Transcribe-Zeile der RecordingCard.
