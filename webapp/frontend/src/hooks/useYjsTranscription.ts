/**
 * Yjs-Kollaboration (Change 053): Live-Sync einer Transkription über den
 * Webapp-eigenen /yjs-WebSocket (pycrdt-websocket im Backend).
 *
 * - Room = Recording-UID, Doc-Struktur: Map "segments" (Index → Y.Text)
 * - Awareness: lokaler Nutzername + Liste der aktiven Teilnehmer
 * - Fallback: Server nicht erreichbar → "solo" (bestehendes Verhalten,
 *   einzelne Segmente weiterhin per updateSegment-PATCH speichern)
 * - finalize(): Yjs-Texte → PUT /recordings/{rid}/segments (DB + Version)
 *
 * Ehrliche Zustände: "connecting" | "connected" | "offline" | "solo" —
 * kein Fake-Status (User-Vorgabe: Progress nur echte Backend-Prozesse).
 */
import { useCallback, useEffect, useRef, useState } from "react";
import * as Y from "yjs";
import { WebsocketProvider } from "y-websocket";
import { replaceSegments } from "../api";

export type YjsConnState = "solo" | "connecting" | "connected" | "offline";

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
) {
  const [conn, setConn] = useState<YjsConnState>("solo");
  const [activeUsers, setActiveUsers] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const docRef = useRef<Y.Doc | null>(null);
  const provRef = useRef<WebsocketProvider | null>(null);
  const initedRef = useRef(false);
  const segmentsRef = useRef(segments as SegmentLike[]);
  segmentsRef.current = segments as SegmentLike[];
  const remoteCbRef = useRef(onRemoteChange);
  remoteCbRef.current = onRemoteChange;

  useEffect(() => {
    if (!recordingId) return;

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

    // Remote-Änderungen → Parent benachrichtigen (Anzeige live aktualisieren).
    const onDocUpdate = () => {
      const texts: string[] = [];
      segmentsMap.forEach((t, k) => {
        texts[Number(k)] = t.toString();
      });
      remoteCbRef.current?.(texts.filter((x) => x !== undefined));
    };
    doc.on("update", onDocUpdate);

    const onAwareness = () => {
      const names: string[] = [];
      provider.awareness.getStates().forEach((st: unknown) => {
        const n = (st as { user?: { name?: string } })?.user?.name;
        if (typeof n === "string" && n) names.push(n);
      });
      setActiveUsers([...new Set(names)]);
    };
    provider.awareness.on("change", onAwareness);
    provider.awareness.setLocalStateField("user", {
      name: (window as unknown as { POLYSCHNACK_USER?: { name?: string } })
        .POLYSCHNACK_USER?.name ?? "Nutzer",
    });

    provider.on("status", onStatus);

    return () => {
      window.clearTimeout(soloTimer);
      provider.awareness.off("change", onAwareness);
      provider.off("status", onStatus);
      provider.destroy();
      doc.destroy();
      docRef.current = null;
      provRef.current = null;
      initedRef.current = false;
    };
  }, [recordingId]);

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

  /** Export-Brücke (REQ-BENCH-033): Yjs-Doc → rec.segments in der DB. */
  const finalize = useCallback(async (): Promise<boolean> => {
    if (!recordingId || saving) return false;
    setSaving(true);
    try {
      const texts = getSegmentTexts();
      const base = segmentsRef.current;
      if (!base.length || texts.length !== base.length) return false;
      const merged = base.map((s, i) => ({ ...s, text: texts[i] ?? s.text }));
      const result = await replaceSegments(recordingId, merged as never[]);
      remoteCbRef.current?.(result.segments.map((s) => s.text));
      return true;
    } catch {
      return false;
    } finally {
      setSaving(false);
    }
  }, [recordingId, saving, getSegmentTexts]);

  const hasCollab = conn === "connected" || conn === "connecting";
  return { conn, activeUsers, hasCollab, setSegmentText, getSegmentTexts, finalize, saving };
}
