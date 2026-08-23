/* ============================================================
   Lokaler Aufnahme-Puffer (IndexedDB)
   Sichere Aufnahmen sofort im Browser, BEVOR der Upload läuft.
   Verhindert Datenverlust bei Netzabriss/Serverfehler/Timeout:
   Der Blob überlebt in IndexedDB, bis der Upload nachweislich
   erfolgreich war (dann wird der Eintrag gelöscht).
   ============================================================ */

const DB_NAME = "polyschnack-recordings";
const STORE = "pending";
const DB_VERSION = 1;

export interface PendingRecording {
  id: string; // batchId
  blob: Blob;
  fileName: string;
  mime: string;
  createdAt: number;
  vad: boolean;
  diarize: boolean;
  streaming: boolean;
  noiseReduce: boolean;
  enhance: string;
  separate: string;
}

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(STORE)) {
        db.createObjectStore(STORE, { keyPath: "id" });
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

/** Aufnahme lokal sichern — VOR dem Upload. */
export async function savePendingRecording(rec: PendingRecording): Promise<void> {
  try {
    const db = await openDb();
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction(STORE, "readwrite");
      tx.objectStore(STORE).put(rec);
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
    db.close();
  } catch (e) {
    console.warn("IndexedDB save failed — recording stays in memory only:", e);
  }
}

/** Alle lokal gesicherten, noch nicht hochgeladenen Aufnahmen. */
export async function loadPendingRecordings(): Promise<PendingRecording[]> {
  try {
    const db = await openDb();
    const all = await new Promise<PendingRecording[]>((resolve, reject) => {
      const tx = db.transaction(STORE, "readonly");
      const req = tx.objectStore(STORE).getAll();
      req.onsuccess = () => resolve(req.result as PendingRecording[]);
      req.onerror = () => reject(req.error);
    });
    db.close();
    return all.sort((a, b) => a.createdAt - b.createdAt);
  } catch {
    return [];
  }
}

/** Eintrag löschen — NUR nach erfolgreichem Upload. */
export async function deletePendingRecording(id: string): Promise<void> {
  try {
    const db = await openDb();
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction(STORE, "readwrite");
      tx.objectStore(STORE).delete(id);
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
    db.close();
  } catch (e) {
    console.warn("IndexedDB delete failed:", e);
  }
}

/** Aufnahme + zugehörige Batch-Daten als FormData bauen (wie recordFromMic). */
export function pendingToFormData(rec: PendingRecording): FormData {
  const fd = new FormData();
  fd.append("file", new File([rec.blob], rec.fileName, { type: rec.mime }));
  fd.append("batch_id", rec.id);
  fd.append("enable_vad", String(rec.vad));
  fd.append("enable_diarize", String(rec.diarize));
  fd.append("enable_streaming", String(rec.streaming));
  fd.append("enable_noise_reduce", String(rec.noiseReduce));
  fd.append("enable_enhance", rec.enhance);
  fd.append("separate_backend", rec.separate);
  return fd;
}
