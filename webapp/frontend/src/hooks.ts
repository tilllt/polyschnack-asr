import {
  useQuery,
  useMutation,
  useQueryClient,
} from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import {
  fetchRecordings,
  fetchStats,
  fetchModelStatus,
  uploadRecording,
  deleteRecording,
  retranscribeRecording,
  realignRecording,
  rediarizeRecording,
  cancelRecording,
  type Recording,
  type RecordingSort,
  type RecordingSortDir,
  type Stats,
  type ModelStatus,
} from "./api";

/* ============================================================
   QUERIES
   ============================================================ */

export function useRecordings(
  q: string,
  opts: { sort?: RecordingSort | null; dir?: RecordingSortDir; tags?: string[] } = {},
) {
  const { sort = null, dir = "desc", tags = [] } = opts;
  return useQuery<Recording[], Error>({
    queryKey: ["recordings", q, sort, dir, tags] as const,
    queryFn: () => fetchRecordings(q, { sort, dir, tags }),
    // Refetch every 2s while any recording is processing; otherwise stop polling
    refetchInterval: (query) => {
      const data = query.state.data as Recording[] | undefined;
      if (!data) return false;
      return data.some((r) => r.status === "processing") ? 2000 : false;
    },
  });
}

export function useStats() {
  return useQuery<Stats, Error>({
    queryKey: ["stats"] as const,
    queryFn: fetchStats,
    refetchInterval: (query) => {
      const data = query.state.data as Stats | undefined;
      if (!data) return 2000;
      return data.processing > 0 ? 2000 : false;
    },
    staleTime: 0,
  });
}

/** ASR-Geräte-Status (cuda/cpu) — für das Badge in der Stats-Leiste. */
export function useModelStatus() {
  return useQuery<ModelStatus, Error>({
    queryKey: ["model-status"] as const,
    queryFn: fetchModelStatus,
    refetchInterval: 30_000,
    staleTime: 10_000,
  });
}

/* ============================================================
   VIEWPORT-LAZY-LOADING (2026-08-15, User-Befund: „Seite lädt
   bei langen Dateien ewig — alle Waveforms werden geladen")
   ============================================================ */

/**
 * Liefert `true`, sobald das Element in die Nähe des Viewports
 * (rootMargin, Standard 800px) gerät — und bleibt dann `true`
 * (einmal geladen = geladen). Kein Unload beim Wegscrollen, damit
 * WaveSurfer seine decodierte Audio behält (Play-Button reagiert
 * sofort, statt die 60-min-Datei erneut zu laden).
 */
export function useNearViewport<T extends HTMLElement>(rootMargin = "800px 0px") {
  const ref = useRef<T | null>(null);
  const [near, setNear] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (typeof IntersectionObserver === "undefined") {
      setNear(true); // Fallback: kein IO → immer laden
      return;
    }
    const obs = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          setNear(true);
          obs.disconnect();
        }
      },
      { rootMargin }
    );
    obs.observe(el);
    return () => obs.disconnect();
  }, [rootMargin]);

  return { ref, near };
}

/* ============================================================
   MUTATIONS
   ============================================================ */

export function useUpload() {
  const qc = useQueryClient();

  return useMutation<Recording | { duplicate: true; existing_id: string; recording: Recording }, Error, { file: File; batchId: string }>({
    mutationFn: ({ file, batchId }) => uploadRecording(file, batchId),
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: ["recordings"] });
      void qc.invalidateQueries({ queryKey: ["stats"] });
    },
  });
}

export function useDelete() {
  const qc = useQueryClient();

  return useMutation<void, Error, string>({
    mutationFn: (id) => deleteRecording(id),
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: ["recordings"] });
      void qc.invalidateQueries({ queryKey: ["stats"] });
    },
  });
}

export function useRetranscribe() {
  const qc = useQueryClient();

  return useMutation<Recording, Error, { id: string; opts?: { enable_vad?: boolean; enable_diarize?: boolean; diarize_num_speakers?: number; diarize_min_duration_off?: number; diarize_method?: string; enable_streaming?: boolean; enable_noise_reduce?: boolean; enable_enhance?: string; backend?: string } }>({
    mutationFn: ({ id, opts }) => retranscribeRecording(id, opts),
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: ["recordings"] });
      void qc.invalidateQueries({ queryKey: ["stats"] });
    },
  });
}

/** Change 046: Re-Alignment auf korrigiertem Text (Ground Truth) starten. */
export function useRealign() {
  const qc = useQueryClient();

  return useMutation<{ id: string; alignment: string }, Error, string>({
    mutationFn: (id) => realignRecording(id),
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: ["recordings"] });
    },
  });
}

/** Change 057: Re-Diarize — Sprecher-Zuordnung neu berechnen (NUR speaker-
 *  Felder; Text/Wörter/Zeiten bleiben unangetastet). */
export function useRediarize() {
  const qc = useQueryClient();

  return useMutation<{ id: string; diar_status: string }, Error, string>({
    mutationFn: (id) => rediarizeRecording(id),
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: ["recordings"] });
    },
  });
}

/** Laufende/wartende Transkription abbrechen (2026-08-15). */
export function useCancelRecording() {
  const qc = useQueryClient();

  return useMutation<{ cancelled: boolean }, Error, { id: string }>({
    mutationFn: ({ id }) => cancelRecording(id),
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: ["recordings"] });
      void qc.invalidateQueries({ queryKey: ["stats"] });
      void qc.invalidateQueries({ queryKey: ["queue"] });
    },
  });
}
