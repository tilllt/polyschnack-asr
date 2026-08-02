import {
  useQuery,
  useMutation,
  useQueryClient,
} from "@tanstack/react-query";
import {
  fetchRecordings,
  fetchStats,
  fetchModelStatus,
  uploadRecording,
  deleteRecording,
  retranscribeRecording,
  type Recording,
  type Stats,
  type ModelStatus,
} from "./api";

/* ============================================================
   QUERIES
   ============================================================ */

export function useRecordings(q: string) {
  return useQuery<Recording[], Error>({
    queryKey: ["recordings", q] as const,
    queryFn: () => fetchRecordings(q),
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

  return useMutation<Recording, Error, { id: string; opts?: { enable_vad?: boolean; enable_diarize?: boolean; enable_streaming?: boolean; enable_noise_reduce?: boolean; enable_enhance?: string; backend?: string } }>({
    mutationFn: ({ id, opts }) => retranscribeRecording(id, opts),
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: ["recordings"] });
      void qc.invalidateQueries({ queryKey: ["stats"] });
    },
  });
}
