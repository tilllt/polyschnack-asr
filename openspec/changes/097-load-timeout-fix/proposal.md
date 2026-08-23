# Change 097 — Load-Timeout-Logikfehler: kein Wechsel auf die volle Datei

**Status:** Implementiert, Commit folgt
**Anlass (Ruben-Review, 24.08.):** „Es ist eigentlich nicht möglich, dass ein
64-kbps/90-min-MP3-File 30 s zum Decoden braucht — das ist ein Logikfehler /
WaveSurfer wird falsch benutzt."

## Befund (verifiziert, Messungen)

**Ruben liegt RICHTIG — es war ein Logikfehler, zusätzlich zur Codec-Frage:**

1. **Der 10-s-Timeout (mit Server-Peaks) schoss in den Fehlerpfad:**
   WaveSurfer dekodiert die Datei IMMER (auch wenn die Welle aus den
   Server-Peaks kommt) — `ready` feuert erst NACH dem Decode. Der alte
   `loadTimeoutMs = hasPeaks ? 10000 : 60000` ging fälschlich von sofortigem
   `ready` aus. Bei Decodes > 10 s (auf Mobile normal):
   - Timeout feuert → `setError` + `onLoadError` → RecordingCard setzt
     `previewFailed` → `resolveAudioUrl` liefert die **volle Original-Datei
     (136 MB)** → `audioUrl` ist Effekt-Dependency (WaveformPlayer.tsx:725)
     → kompletter Neu-Load (alter WS wird destroyed → **der dokumentierte
     AbortError**) → Fetch + Decode der vollen Datei (noch länger).
   - Gemessen: „Play-Button nach ~30 s" = Decode der VOLLEN Datei, nicht der
     Preview. Ein echter Logikfehler (doppelter Load + falsche Datei).

2. **Zusätzlicher Faktor: die 45,7-MB-Preview war 44,1 kHz** (Altbestand vom
   22.08.), nicht 16 kHz wie der Code (`PREVIEW_SR=16000`) vorgibt. Isolierte
   Messung (ohne App-Logik, Chrome): decodeAudioData der 45,7-MB-MP3 =
   **~20 s** — 44,1 kHz × 90 min → ~1,0-GB-PCM-Buffer (statt 365 MB bei
   16 kHz). Ein „64-kbps-File" ist also nicht automatisch schnell — die
   Sample-Rate bestimmt die Decode-Arbeit. (Der 4×-CPU-Throttle spielt
   KEINE Rolle: decodeAudioData läuft außerhalb des JS-Threads, Messung
   1× vs. 4×: 19,7 s vs. 20,7 s.)

## Fix

- `loadTimeoutMs` WebAudio: immer **60 s** (reines Sicherheitsnetz für Netz
  UND Decode). Der Timeout löst **kein `onLoadError`** mehr aus (kein Wechsel
  auf die volle Datei — die Preview ist die richtige Wahl; echte
  Preview-Fehler meldet `ws.on("error")`).
- `ready`-Handler: `setError(false)` — ein späterer Decode-Erfolg heilt den
  Timeout-Fehlerzustand (UI zeigt dann Welle + Play statt Fehler).
- Der Opus-Change (096) bleibt — er adressiert den Codec-Teil (15,5 MB +
  effizienter Opus-Decode im Worker → 2,9 s statt 20 s).

## Verifikation

- Backend-Log nach dem Load: NUR `/audio/preview`, kein `/audio` (keine
  volle Datei, kein Doppel-Load, kein AbortError mehr).
- canPlay weiterhin ~2,9 s (Worker-Decode, Opus-Preview).
