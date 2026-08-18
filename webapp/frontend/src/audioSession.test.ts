/**
 * Change 016 (2026-08-18): iOS-AudioSession-Härtung.
 *
 * WaveSurfer 7 setzt bei jedem WebAudio-Player-Start
 * `navigator.audioSession.type = "playback"`; WebKit blockiert dann
 * `getUserMedia` ("AudioSession category is not compatible with audio
 * capture"). `ensureAudioSessionForRecording()` setzt die Session vor
 * jedem Mikrofon-Zugriff auf `play-and-record`.
 */
import { describe, expect, it, vi, afterEach } from "vitest";
import { ensureAudioSessionForRecording } from "./audioSession";

describe("ensureAudioSessionForRecording (Change 016)", () => {
  const originalNavigator = globalThis.navigator;

  afterEach(() => {
    Object.defineProperty(globalThis, "navigator", {
      value: originalNavigator,
      configurable: true,
    });
    vi.restoreAllMocks();
  });

  it("setzt audioSession.type auf play-and-record (WebKit)", () => {
    const audioSession = { type: "playback" };
    Object.defineProperty(globalThis, "navigator", {
      value: { audioSession },
      configurable: true,
    });

    ensureAudioSessionForRecording();

    expect(audioSession.type).toBe("play-and-record");
  });

  it("lässt play-and-record unverändert (idempotent)", () => {
    const audioSession = { type: "play-and-record" };
    Object.defineProperty(globalThis, "navigator", {
      value: { audioSession },
      configurable: true,
    });

    ensureAudioSessionForRecording();

    expect(audioSession.type).toBe("play-and-record");
  });

  it("tut nichts, wenn navigator.audioSession fehlt (Desktop-Browser)", () => {
    Object.defineProperty(globalThis, "navigator", {
      value: {},
      configurable: true,
    });

    expect(() => ensureAudioSessionForRecording()).not.toThrow();
  });

  it("übersteht einen werfenden audioSession-Getter (Exoten)", () => {
    Object.defineProperty(globalThis, "navigator", {
      value: {
        get audioSession() {
          throw new Error("nope");
        },
      },
      configurable: true,
    });

    expect(() => ensureAudioSessionForRecording()).not.toThrow();
  });
});
