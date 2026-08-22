/**
 * Yjs-Kollaboration (Change 053): Live-Sync einer Transkription über den
 * Webapp-eigenen /yjs-WebSocket (pycrdt-websocket im Backend).
 *
 * - Room = Recording-UID, Doc-Struktur: Map "segments" (Index → Y.Text)
 * - Awareness: lokaler Nutzername + Liste der aktiven Teilnehmer
 * - Fallback: Server nicht erreichbar → "solo" (bestehendes Verhalten,
 *   einzelne Segmente weiterhin per updateSegment-PATCH speichern)
 * - Change 067-Fix: Verbindung nur bei enabled (Datei geteilt) — keine
 *   unnötige WebSocket-Verbindung/Checks für ungeteilte Aufnahmen.
 * - Change 068: Autosave statt „In DB speichern"-Button — debounced
 *   (1500 ms) atomarer Write ohne Version (create_version=false);
 *   die Version entsteht erst beim Verlassen des Edit-Mode (save(true)).
 *
 * Ehrliche Zustände: "connecting" | "connected" | "offline" | "solo" —
 * kein Fake-Status (User-Vorgabe: Progress nur echte Backend-Prozesse).
 */
import { useCallback, useEffect, useRef, useState } from "react";
import * as Y from "yjs";
import { WebsocketProvider } from "y-websocket";
import { replaceSegments } from "../api";
import { editorsFromStates, type EditLock } from "../collabLock";

export type YjsConnState = "solo" | "connecting" | "connected" | "offline";

/** Change 068: Debounce für den Autosave (ms). */
const AUTOSAVE_DEBOUNCE_MS = 1500;

interface SegmentLike {
  id?: number;
  start?: number;
  end?: number;
  text: string;
  [k: string]: unknown;
}

export function useYjsTranscription<T extends { text: string }>(
  recordingId: string | undefined,
  segments: T[],
  onRemoteChange?: (texts: string[]) => void,
  // Change 067-Fix: true nur bei geteilten Aufnahmen (has_shares ||
  // is_anon_shared || shared_with_me) — sonst keine Yjs-Verbindung.
  enabled = true,
) {
  const [conn, setConn] = useState<YjsConnState>("solo");
  // Change 067-Fix (User-Befund 2026-08-21): NUR ANDERE Clients, die
  // gerade aktiv bearbeiten (editing-Flag in der Awareness) — NICHT der
  // eigene Client und NICHT bloß „Seite offen". Damit erscheint die
  // Kollaborations-Leiste nur, wenn die Datei wirklich geteilt ist UND
  // jemand anderes gerade darin arbeitet.
  const [activeEditors, setActiveEditors] = useState<string[]>([]);
  // Change 084: fremder Edit-Lock { index, name } — sperrt
  // Strukturoperationen, solange ein anderer Client ein Segment editiert.
  const [editLock, setEditLock] = useState<EditLock | null>(null);
  const [saving, setSaving] = useState(false);
  const docRef = useRef<Y.Doc | null>(null);
  const provRef = useRef<WebsocketProvider | null>(null);
  const initedRef = useRef(false);
  const autosaveTimerRef = useRef<number | null>(null);
  // Change 068: Zuletzt GESPEICHERTE Texte (Fingerprint) — Autosave und
  // Edit-Mode-Ende speichern nur, wenn sich der Text wirklich geändert hat
  // (keine Leer-Writes, keine Versions-Spam bei Nichtstun).
  const lastSavedRef = useRef<string>("");
  const segmentsRef = useRef(segments as SegmentLike[]);
  segmentsRef.current = segments as SegmentLike[];
  const remoteCbRef = useRef(onRemoteChange);
  remoteCbRef.current = onRemoteChange;

  /** Fingerprint des aktuellen Yjs-Doc-Stands (null wenn kein Doc). */
  const docFingerprint = useCallback((): string | null => {
    const doc = docRef.current;
    if (!doc) return null;
    const map = doc.getMap<Y.Text>("segments");
    const parts: string[] = [];
    map.forEach((t, k) => {
      parts[Number(k)] = t.toString();
    });
    return parts.join("\u0000");
  }, []);

  /** Change 068: Yjs-Stand atomar in die DB schreiben (mit/ohne Version). */
  const save = useCallback(
    async (withVersion: boolean): Promise<boolean> => {
      if (!recordingId || saving) return false;
      const fp = docFingerprint();
      if (fp === null || fp === lastSavedRef.current) return false;
      setSaving(true);
      try {
        const texts = fp.split("\u0000");
        const base = segmentsRef.current;
        if (!base.length || texts.length !== base.length) return false;
        const merged = base.map((s, i) => ({ ...s, text: texts[i] ?? s.text }));
        const result = await replaceSegments(recordingId, merged as never[], withVersion);
        lastSavedRef.current = fp;
        remoteCbRef.current?.(result.segments.map((s) => s.text));
        return true;
      } catch {
        // Autosave-Fehler still schlucken — der nächste Doc-Update
        // startet den Debounce erneut (Retry). Kein Fake-Erfolg.
        return false;
      } finally {
        setSaving(false);
      }
    },
    [recordingId, saving, docFingerprint],
  );

  /** Autosave (ohne Version) nach Debounce anstoßen. */
  const scheduleAutosave = useCallback(() => {
    if (autosaveTimerRef.current !== null) {
      window.clearTimeout(autosaveTimerRef.current);
    }
    autosaveTimerRef.current = window.setTimeout(() => {
      autosaveTimerRef.current = null;
      void save(false);
    }, AUTOSAVE_DEBOUNCE_MS);
  }, [save]);

  useEffect(() => {
    if (!recordingId) return;
    // Change 067-Fix: Keine Verbindung/Checks für ungeteilte Aufnahmen —
    // kein WebSocket, kein Awareness, kein Solo-Timer. Kollaboration kann
    // es ohne Freigabe ohnehin nicht geben.
    if (!enabled) {
      setConn("solo");
      return;
    }

    // Change 068: Ausgangs-Fingerprint = aktueller DB-Stand → das
    // initiale Doc-Befüllen erzeugt keinen unnötigen Autosave.
    lastSavedRef.current = segmentsRef.current
      .map((s) => s.text ?? "")
      .join("\u0000");

    const proto = window.location.protocol === "https:" ? "wss" : "ws";
    const wsBase = `${proto}://${window.location.host}/yjs`;

    const doc = new Y.Doc();
    const segmentsMap = doc.getMap<Y.Text>("segments");
    const provider = new WebsocketProvider(wsBase, recordingId, doc, {
      connect: true,
    });
    docRef.current = doc;
    provRef.current = provider;
    setConn("connecting");

    // Server nicht erreichbar (kein /yjs-Mount im Image) → nach 4 s Solo-Modus.
    const soloTimer = window.setTimeout(() => {
      if (!provider.wsconnected) {
        setConn("solo");
        provider.disconnect();
      }
    }, 4000);

    const onStatus = (e: { status: string }) => {
      if (e.status === "connected") {
        window.clearTimeout(soloTimer);
        setConn("connected");
        if (!initedRef.current) {
          initedRef.current = true;
          // Erster Client im leeren Room: Segmente initial befüllen.
          if (segmentsMap.size === 0 && segmentsRef.current.length) {
            segmentsRef.current.forEach((s, i) => {
              segmentsMap.set(String(i), new Y.Text(s.text ?? ""));
            });
          }
        }
      } else if (e.status === "disconnected") {
        setConn((prev) => (prev === "solo" ? "solo" : "offline"));
      }
    };

    // Remote-Änderungen → Parent benachrichtigen (Anzeige live aktualisieren)
    // + Autosave planen (Change 068: ohne Version, debounced).
    const onDocUpdate = () => {
      const texts: string[] = [];
      segmentsMap.forEach((t, k) => {
        texts[Number(k)] = t.toString();
      });
      remoteCbRef.current?.(texts.filter((x) => x !== undefined));
      scheduleAutosave();
    };
    doc.on("update", onDocUpdate);

    // Change 067-Fix: Nur ANDERE Clients zählen, die gerade aktiv
    // bearbeiten (editing-Flag). Der eigene Client wird über clientID
    // ausgeschlossen — sonst stünde „1 bearbeitet gerade", obwohl nur
    // die eigene Seite offen ist (User-Befund 2026-08-21).
    // Change 084: editing trägt den Segment-Index; editorsFromStates
    // liefert zusätzlich den editLock (fremder Editor + Segment) für
    // die Sperre von Strukturoperationen.
    const onAwareness = () => {
      const myId = provider.awareness.clientID;
      const { activeEditors: names, editLock: lock } = editorsFromStates(
        provider.awareness.getStates(),
        myId,
      );
      setActiveEditors(names);
      setEditLock(lock);
    };
    provider.awareness.on("change", onAwareness);
    provider.awareness.setLocalStateField("user", {
      name: (window as unknown as { POLYSCHNACK_USER?: { name?: string } })
        .POLYSCHNACK_USER?.name ?? "Nutzer",
    });
    // Editing-Flag initial false — wird von SegmentList über
    // setEditingActive(true/false) gesetzt, sobald ein Textfeld aktiv ist.
    provider.awareness.setLocalStateField("editing", false);

    provider.on("status", onStatus);

    return () => {
      window.clearTimeout(soloTimer);
      if (autosaveTimerRef.current !== null) {
        window.clearTimeout(autosaveTimerRef.current);
        autosaveTimerRef.current = null;
      }
      // Change 068 Unmount-Flush: pending Änderungen sofort MIT Version
      // speichern („Edit-Mode verlassen" = Seite verlassen) — best-effort,
      // nur wenn sich der Text seit dem letzten Save geändert hat.
      void save(true);
      provider.awareness.off("change", onAwareness);
      provider.off("status", onStatus);
      provider.destroy();
      doc.destroy();
      docRef.current = null;
      provRef.current = null;
      initedRef.current = false;
    };
  }, [recordingId, enabled, save, scheduleAutosave]);

  /** Eigene Bearbeitungs-Aktivität melden; beim Verlassen des Edit-Mode
   *  (aktiv → inaktiv) genau EINE Version anlegen (Change 068).
   *  Change 084: editing trägt den Segment-Index (number) oder null —
   *  andere Clients sehen damit, WELCHES Segment gesperrt ist. */
  const setEditingActive = useCallback(
    (idx: number | null) => {
      provRef.current?.awareness.setLocalStateField(
        "editing",
        idx === null ? false : idx,
      );
      if (idx === null) {
        void save(true);
      }
    },
    [save],
  );

  /** Ein Segment-Text lokal ändern → wird live an alle Clients gesynct. */
  const setSegmentText = useCallback((idx: number, text: string) => {
    const doc = docRef.current;
    if (!doc) return;
    const map = doc.getMap<Y.Text>("segments");
    let t = map.get(String(idx));
    if (!t) {
      map.set(String(idx), new Y.Text(text));
      return;
    }
    if (t.toString() !== text) {
      t.delete(0, t.length);
      t.insert(0, text);
    }
  }, []);

  /** Yjs-Texte als String-Array (Index = Segment-Position). */
  const getSegmentTexts = useCallback((): string[] => {
    const doc = docRef.current;
    if (!doc) return [];
    const map = doc.getMap<Y.Text>("segments");
    const out: string[] = [];
    map.forEach((t, k) => {
      out[Number(k)] = t.toString();
    });
    return out.filter((x) => x !== undefined);
  }, []);

  const hasCollab = conn === "connected" || conn === "connecting";
  return {
    conn,
    activeEditors,
    editLock,
    hasCollab,
    setSegmentText,
    getSegmentTexts,
    save,
    saving,
    setEditingActive,
  };
}
