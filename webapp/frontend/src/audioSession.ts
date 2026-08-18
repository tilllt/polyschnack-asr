/**
 * iOS-Mikrofon-Härtung (Change 016, 2026-08-18).
 *
 * WaveSurfer 7 setzt bei jedem WebAudio-Player-Start
 * `navigator.audioSession.type = "playback"` (webaudio.js::
 * setWebAudioSessionPlayback). WebKit verbietet dann `getUserMedia` mit
 * "AudioSession category is not compatible with audio capture" — die
 * Audio-Session-Spec (§6.3) erlaubt den Mikrofon-Track nur bei
 * `play-and-record` oder `auto`.
 *
 * `ensureAudioSessionForRecording()` setzt die Session deshalb unmittelbar
 * vor jedem Mikrofon-Zugriff explizit auf `play-and-record`. Nur WebKit
 * hat `navigator.audioSession` — alle anderen Browser ignorieren das
 * still (kein try/catch-Fehlschlag, kein Verhalten).
 *
 * `restoreAudioSessionAfterRecording()` setzt die Session nach dem Ende
 * der Aufnahme zurück auf `playback` — der Zustand, den WaveSurfer für
 * die Wiedergabe ohnehin herstellt. Ohne das Zurücksetzen behält iOS die
 * `play-and-record`-Session (und damit den aktiven Mikrofon-Indikator in
 * der Statusleiste) dauerhaft, auch wenn alle Tracks gestoppt sind
 * (Datenschutz-Befund 2026-08-18).
 */
export function ensureAudioSessionForRecording(): void {
  try {
    const s = (navigator as unknown as { audioSession?: { type: string } })
      .audioSession;
    if (s && s.type !== "play-and-record") {
      s.type = "play-and-record";
    }
  } catch {
    // Kein WebKit / API nicht verfügbar — nichts zu tun.
  }
}

/**
 * AudioSession nach der Aufnahme freigeben: zurück auf `playback`
 * (WaveSurfer-Default für reine Wiedergabe). Nur WebKit hat die API —
 * andere Browser ignorieren das still.
 */
export function restoreAudioSessionAfterRecording(): void {
  try {
    const s = (navigator as unknown as { audioSession?: { type: string } })
      .audioSession;
    if (s && s.type !== "playback") {
      s.type = "playback";
    }
  } catch {
    // Kein WebKit / API nicht verfügbar — nichts zu tun.
  }
}

/**
 * WebKit-Erkennung: `navigator.audioSession` existiert nur in Safari
 * (iOS + macOS). Auf diesen Geräten darf das Mikrofon NICHT dauerhaft
 * vorgewärmt werden — iOS zeigt den Aktiv-Indikator dann permanent
 * (2026-08-18). Der Stream wird dort erst beim echten Record-Start
 * geholt.
 */
export function isWebKitAudioSession(): boolean {
  try {
    return !!(navigator as unknown as { audioSession?: unknown }).audioSession;
  } catch {
    return false;
  }
}
