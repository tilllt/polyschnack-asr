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

/** Change 216 (Nutzer-Befund 20.09.2026): Zusatz zur Meldung. `reason` bleibt
 *  der stabile Schlüssel (z. B. "empty_text"); `segmentIndex` nennt das
 *  betroffene Segment, damit die Oberfläche Aufnahme UND Segment benennen
 *  kann — vorher stand nur „nicht gespeichert" ohne Gegenstand. */
export interface SaveErrorDetail {
  segmentIndex?: number;
}

/** Change 068: Debounce für den Autosave (ms). */
const AUTOSAVE_DEBOUNCE_MS = 1500;

/**
 * Change 217: Fingerabdruck der Segmenttexte in ihrer REIHENFOLGE.
 *
 * Das ist die Client-Seite derselben Definition, die der Server in
 * `app/versions.py: content_fingerprint()` benutzt: verglichen wird der
 * Inhalt, nie ein Zeitstempel (`updated_at` wird bei JEDEM Schreiben neu
 * gesetzt und täuscht sonst eine Änderung vor — daraus entstand die
 * Versionsflut). Getrimmt wird wie beim Server (`rec.text = " ".join(
 * text.strip())`), damit beide Seiten denselben Stand gleich bewerten.
 * Der Client kennt im Yjs-Doc nur die Texte — der Server prüft zusätzlich
 * Segmente, Sprecher, Grenzen und Wörter und ist maßgeblich: er entscheidet,
 * ob geschrieben und ob eine Version angelegt wird.
 */
export function textsFingerprint(texts: readonly (string | undefined | null)[]): string {
  return texts.map((t) => String(t ?? "").trim()).join("\u0000");
}

/** true, wenn KEIN Text vorhanden ist (Ladephase-Erkennung „Leerstand"). */
function noneHasText(texts: readonly (string | undefined | null)[]): boolean {
  return !texts.some((t) => String(t ?? "").trim());
}

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
  // Change 189: Stand (`updated_at`), den dieser Client geladen hat. Der Raum
  // hängt daran — ein Client mit altem Stand landet in einem neuen, leeren
  // Raum und befüllt ihn aus dem Serverstand. Damit kann alter Text nicht mehr
  // über frisch geänderte Daten gelegt werden (Vorfall 14.09.2026).
  roomStamp?: string | null,
  // Change 207: Fehler des Autosaves sichtbar machen. Vorher wurden sie still
  // geschluckt (`catch { return false }`) — der Nutzer sah nicht, dass seine
  // Bearbeitung nie gespeichert wurde.
  // Change 216: zweiter Parameter nennt das betroffene Segment (Meldung mit
  // Gegenstand) — siehe SaveErrorDetail.
  onSaveError?: (reason: string, detail?: SaveErrorDetail) => void,
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
  // Change 207: Der Schutz gegen paralleles Speichern läuft über eine Ref, damit
  // `save` seine Identität behält. Vorher stand `saving` in den Abhängigkeiten
  // von `save` — und der Provider-Effekt hängt an `save`. Damit baute JEDER
  // Speicherversuch den Yjs-Provider (und die WebSocket-Verbindung) neu auf und
  // löste den nächsten Autosave aus: gemessen 675 Anfragen in 7 Sekunden, keine
  // einzige erfolgreich, weil der Server den Stand ablehnte.
  const savingRef = useRef(false);
  // Change 207: Fehlversuche zählen → Backoff statt Hämmern; Fehler einmal melden.
  const failuresRef = useRef(0);
  // Change 216 (Nutzer-Befund 20.09.2026): Ladephase ≠ Nutzeraktion.
  // Solange niemand getippt oder ein Segment zum Bearbeiten geöffnet hat, ist
  // der Stand allein aus dem Laden entstanden: er darf NIE gespeichert werden
  // und NIE eine Meldung erzeugen. Vorher löste der Autosave schon beim
  // Seitenaufbau aus, was der Nutzer falsch als „Not saved yet" sah.
  const userTouchedRef = useRef(false);
  // Change 216: Segment, das zuletzt angefasst wurde (für die Meldung).
  const lastTouchedIdxRef = useRef<number | null>(null);
  const onSaveErrorRef = useRef(onSaveError);
  onSaveErrorRef.current = onSaveError;
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

  /** Fingerprint des aktuellen Yjs-Doc-Stands (null wenn kein Doc).
   *  Change 217: getrimmt wie der Server (textsFingerprint) — beide Seiten
   *  müssen denselben Stand gleich bewerten. */
  const docFingerprint = useCallback((): string | null => {
    const doc = docRef.current;
    if (!doc) return null;
    const map = doc.getMap<Y.Text>("segments");
    const parts: string[] = [];
    map.forEach((t, k) => {
      parts[Number(k)] = t.toString();
    });
    return textsFingerprint(parts);
  }, []);

  /** Change 216: Serverstand (DB-Segmente) in das Yjs-Doc schreiben und
   *  anzeigen. Wird NUR in der Ladephase angewandt, wenn der Raum einen
   *  Leerstand liefert: der Leerstand wird dann nicht gespeichert, sondern
   *  der Serverstand geladen und angezeigt (nichts überschreiben).
   *  Der Ausgangs-Fingerprint wird auf den Zielzustand gesetzt — das Befüllen
   *  löst damit keinen Autosave und keine Meldung aus. */
  const reseedFromServer = useCallback((): boolean => {
    const doc = docRef.current;
    const base = segmentsRef.current;
    if (!doc || !base.length) return false;
    const next = base.map((s) => s.text ?? "");
    lastSavedRef.current = textsFingerprint(next);
    const map = doc.getMap<Y.Text>("segments");
    doc.transact(() => {
      const keys: string[] = [];
      map.forEach((_t, k) => keys.push(k));
      keys.forEach((k) => {
        if (Number(k) >= next.length) map.delete(k);
      });
      next.forEach((txt, i) => {
        const key = String(i);
        const existing = map.get(key);
        if (!existing) {
          map.set(key, new Y.Text(txt));
          return;
        }
        if (existing.toString() !== txt) {
          existing.delete(0, existing.length);
          existing.insert(0, txt);
        }
      });
    });
    remoteCbRef.current?.(next);
    return true;
  }, []);

  /** Change 068: Yjs-Stand atomar in die DB schreiben (mit/ohne Version). */
  const save = useCallback(
    async (withVersion: boolean): Promise<boolean> => {
      if (!recordingId || savingRef.current) return false;
      // Change 216: Ladephase — reiner Seitenaufbau ist keine Nutzeraktion.
      // Kein Speichervorgang, keine Meldung (der Nutzer sah den Toast sonst
      // beim Laden, ohne etwas getan zu haben).
      if (!userTouchedRef.current) return false;
      const fp = docFingerprint();
      if (fp === null || fp === lastSavedRef.current) return false;
      savingRef.current = true;
      setSaving(true);
      try {
        const base = segmentsRef.current;
        const map = docRef.current?.getMap<Y.Text>("segments") ?? null;
        if (!map || !base.length) return false;
        // Change 216: Pro Index direkt aus dem Doc lesen. Ein FEHLENDER
        // Schlüssel behält den Servertext — vorher wurde er zu "" gemacht
        // (Join/Split des Fingerprints kann „fehlt" und „leer" nicht
        // unterscheiden), ein nur halb gefüllter Raum löschte damit Text.
        const merged = base.map((s, i) => {
          const t = map.get(String(i));
          return { ...s, text: t ? t.toString() : s.text ?? "" };
        });
        // Change 213 (Nutzer-Befunde 19.09.2026): Ein leeres Segment ist eine
        // LÖSCHUNG, kein Fehlerzustand. Vorher (Change 207) brach die Prüfung den
        // GESAMTEN Speichervorgang ab: ein einzelnes leeres Segment verhinderte,
        // dass irgendeine Änderung gespeichert wurde — und weil genau dieser
        // Speichervorgang den Zustand bereinigt hätte, blieb er bei jedem Laden
        // erhalten (Toast „Not saved yet", Altbestand im Zusammenarbeits-Dokument).
        // Der Server ersetzt die Segmentliste vollständig — ein weggelassenes
        // Segment ist damit gelöscht, samt seinen Wörtern. Es gilt die Invariante
        // „kein Segment ohne Text".
        const gefuellt = merged.filter((s) => String(s.text ?? "").trim());
        if (!gefuellt.length) {
          // Change 216: Sonderfall ALLE Segmente leer — hier ist ein Hinweis
          // berechtigt, ABER nur wenn der Nutzer das verursacht hat (die
          // Ladephase ist oben bereits abgefangen: reines Laden schreibt und
          // meldet nie). Die Meldung nennt das betroffene Segment, damit die
          // Oberfläche Aufnahme UND Segment nennen kann.
          failuresRef.current = 0;
          savingRef.current = false;
          setSaving(false);
          const idx =
            lastTouchedIdxRef.current ??
            merged.findIndex((s) => !String(s.text ?? "").trim());
          onSaveErrorRef.current?.("empty_text", {
            segmentIndex: idx >= 0 ? idx : undefined,
          });
          return false;
        }
        const result = await replaceSegments(recordingId, gefuellt as never[], withVersion);
        lastSavedRef.current = fp;
        remoteCbRef.current?.(result.segments.map((s) => s.text));
        // Change 217: Der Server meldet ehrlich, was er getan hat. Bei
        // ``changed === false`` war der Inhalt identisch — es wurde nichts
        // geschrieben und keine Version angelegt. Das ist KEIN Fehler (keine
        // Meldung, kein Backoff), aber auch kein Speichererfolg: der Aufruf
        // meldet dann ``false`` statt ``true``.
        if (result.changed === false) return false;
        return true;
      } catch (err) {
        // Change 207: NICHT mehr still schlucken. Der Nutzer muss wissen, dass
        // seine Bearbeitung nicht gespeichert wurde — und der Autosave darf
        // nicht im Sekundentakt weiterhämmern (Backoff in scheduleAutosave).
        failuresRef.current += 1;
        if (failuresRef.current === 1) {
          onSaveErrorRef.current?.(
            err instanceof Error ? err.message : "save_failed",
            // Change 216: echte Fehler bleiben sichtbar — mit Gegenstand.
            lastTouchedIdxRef.current === null
              ? undefined
              : { segmentIndex: lastTouchedIdxRef.current },
          );
        }
        return false;
      } finally {
        savingRef.current = false;
        setSaving(false);
      }
    },
    [recordingId, docFingerprint],
  );

  /** Autosave (ohne Version) nach Debounce anstoßen. */
  const scheduleAutosave = useCallback(() => {
    if (autosaveTimerRef.current !== null) {
      window.clearTimeout(autosaveTimerRef.current);
    }
    // Change 207: Nach einem Fehlversuch langsamer nachfassen. Der Autosave darf
    // einen dauerhaft abgelehnten Stand nicht im Sekundentakt senden.
    const delay = failuresRef.current >= 1 ? AUTOSAVE_DEBOUNCE_MS * 4 : AUTOSAVE_DEBOUNCE_MS;
    autosaveTimerRef.current = window.setTimeout(() => {
      autosaveTimerRef.current = null;
      void save(false);
    }, delay);
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
    lastSavedRef.current = textsFingerprint(segmentsRef.current.map((s) => s.text ?? ""));

    const proto = window.location.protocol === "https:" ? "wss" : "ws";
    const wsBase = `${proto}://${window.location.host}/yjs`;

    const doc = new Y.Doc();
    const segmentsMap = doc.getMap<Y.Text>("segments");
    // Change 189: Raum = uid + Stand-Suffix (bereinigt, damit der Name in der
    // URL bleibt); ohne Stand-Suffix wie bisher nur die uid.
    const stamp = roomStamp ? String(roomStamp).replace(/[^0-9A-Za-z]/g, "") : "";
    const roomName = stamp ? `${recordingId}:${stamp}` : recordingId;
    const provider = new WebsocketProvider(wsBase, roomName, doc, {
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
      const next = texts.filter((x) => x !== undefined);
      // Change 216 (Nutzer-Befund 20.09.2026): Ladephase — liefert der
      // Zusammenarbeits-Raum einen LEERSTAND (alle Segmente leer), während der
      // Serverstand Text hat, dann wird dieser Leerstand NICHT gespeichert und
      // NICHTS gemeldet. Stattdessen wird der Serverstand geladen und angezeigt
      // (nichts überschreiben). Vorher lief hier der Autosave los und meldete
      // „Not saved yet" — schon beim Laden der Seite, ohne Zutun des Nutzers.
      if (
        !userTouchedRef.current &&
        noneHasText(next) &&
        !noneHasText(segmentsRef.current.map((s) => s.text ?? ""))
      ) {
        reseedFromServer();
        return;
      }
      remoteCbRef.current?.(next);
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
  }, [recordingId, enabled, roomStamp, save, scheduleAutosave, reseedFromServer]);

  /** Eigene Bearbeitungs-Aktivität melden; beim Verlassen des Edit-Mode
   *  (aktiv → inaktiv) genau EINE Version anlegen (Change 068).
   *  Change 084: editing trägt den Segment-Index (number) oder null —
   *  andere Clients sehen damit, WELCHES Segment gesperrt ist. */
  const setEditingActive = useCallback(
    (idx: number | null) => {
      // Change 216: Ein geöffnetes Textfeld ist eine Nutzeraktion — ab hier
      // darf (und muss) gespeichert und gemeldet werden.
      if (idx !== null) {
        userTouchedRef.current = true;
        lastTouchedIdxRef.current = idx;
      }
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
    // Change 216: Tippen ist eine Nutzeraktion — ab hier wird gespeichert
    // und (nur bei echten Fehlern/Leerstand) gemeldet.
    userTouchedRef.current = true;
    lastTouchedIdxRef.current = idx;
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
