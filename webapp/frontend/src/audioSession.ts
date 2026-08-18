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
