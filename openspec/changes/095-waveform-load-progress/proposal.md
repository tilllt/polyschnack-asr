# Change 095 — Waveform-Ladezustand: Klick-Guard, Spinner-Fix, Fortschritts-Background

**Status:** Implementiert (lokal getestet), Commit folgt
**User-Befunde (2026-08-23, Chrome/Android):**
> „Man kann wieder in die Waveform klicken bevor das audio geladen ist."
> „Analysiere warum das laden einer 40mb Audiodatei so lange dauert."
> Spinner auf Mobile kaputt („zeigt ein Drehendes U"); stattdessen
> Spinner + Loading… mit dem Text-Hintergrund als temporärem Progress-Bar
> (100 % geladen = kompletter Background).

## Analyse: Warum dauert das Laden so lange?

Gemessen (Produktions-Build, 45,7-MB-Preview, Desktop-Emulation):
- **Netz (fetch): < 1 s** — die Datei kommt schnell; auf Mobile über
  WLAN/LTE realistisch 5–20 s, aber NICHT der Flaschenhals.
- **decodeAudioData: ~26 s (Desktop)**, auf Mobile-CPU deutlich mehr
  (30–90 s). Der Browser dekodiert die 95-min-MP3 einmalig in PCM
  (~180 MB Puffer) auf dem Hauptthread — DAS ist der Flaschenhals.
- Der Waveform-Render (Peaks) steht sofort; nur das Playback wartet auf
  den Decode. Mit dem Fortschritts-Background wird die Wartezeit sichtbar.
- Optimierungs-Option (Folge-Change): kleinere Preview (24–32 kbps Opus,
  ~15–20 MB) halbiert Netz + Decode-Zeit; Decode im Web-Worker verhindert
  UI-Freeze.

## Delta zum IST

**IST (vor diesem Change):**
- `canPlay` kam aus einem 300-ms-Poll auf `getMediaElement().buffer`.
  WS 7.12 erzeugt im Peaks-Pfad `decodedData` SOFORT per
  `createBuffer(peaks, duration)` — der Poll kann also einen stummen
  Fake-Buffer sehen → Play-Button enabled + Waveform-Klick erlaubt,
  obwohl kein Ton (Regression „man kann wieder klicken").
- Lade-Zustand: CSS-Ring-Spinner (`border-2 border-t-transparent`) — auf
  Mobile optisch ein „drehendes U"; kein Ladefortschritt sichtbar.

**SOLL (dieser Change):**
- **canPlay nur mit echtem Decode-Beweis:** WebAudio → WS-`decode`-Event
  (feuert nach decodeAudioData); MediaElement → readyState>=3-Poll (wie
  gehabt). Klick auf die Waveform vor dem Decode = komplett wirkungslos
  (Guard `!canPlayRef` bleibt; kein Scroll/Zeit-Sprung/Play).
- **Loading-UI:** Spinner als SVG (überall identisch, kein „U"-Problem) +
  „Loading…" (`t("loading_audio")`); der Text-Hintergrund füllt sich mit
  dem Ladefortschritt (WS-`loading`-Event, 0–100 %) als temporärer
  Progress-Bar; bei 100 % ist der Background komplett gefüllt. Gilt für
  beide Lade-Zustände (`!ready`-Block und `!canPlay`-Text neben dem
  Play-Button).

## ADDED Requirements

### Requirement: Klick-Guard gegen vorzeitiges Abspielen

- **Ablauf:** WebAudio-Backends setzen `canPlay` ausschließlich über das
  WS-`decode`-Event; der buffer-Poll entfällt dort (Fake-Buffer-Risiko).
  MediaElement-Backend behält den readyState-Poll. Der
  `onContainerClick`-Guard (`!canPlayRef → return`) bleibt: Klick vor dem
  Decode löst nichts aus (kein Seek, kein Scroll, kein Play).
- **Architektur:** `frontend/src/components/WaveformPlayer.tsx`.

#### Scenario: Klick vor Decode (Android)
- **Akteure:** User, langsame Verbindung.
- **Eingaben:** Klick in die (über Peaks sichtbare) Waveform, solange der
  Decode läuft.
- **Ergebnis:** Keine Reaktion (kein Playback, kein Zeitsprung, kein
  Scroll); der Loading-Status mit Fortschritt bleibt sichtbar.

### Requirement: Spinner + Loading mit Fortschritts-Background

- **Ablauf:** Die Lade-Zustände (`!ready`, `!canPlay`) zeigen einen
  SVG-Spinner (animate-spin, Kreis + Bogen — kein CSS-Ring) + „Loading…"
  (i18n). Hinter dem Text füllt ein Balken (bg-proc/20) von 0 auf 100 %
  — Fortschritt aus dem WS-`loading`-Event; bei `ready` wird 100 gesetzt
  (kompletter Background).
- **Architektur:** `frontend/src/components/WaveformPlayer.tsx`
  (loadPct-State, loading-Listener, LoadProgress-JSX).

#### Scenario: 40-MB-Preview auf Android
- **Akteure:** User.
- **Eingaben:** Aufnahme öffnen, Welle lädt.
- **Ergebnis:** Welle (Peaks) steht sofort; darunter Spinner + „Loading…"
  mit sich füllendem Hintergrund; sobald der Decode fertig ist, ist der
  Background komplett und der Play-Button aktiv.
