// Change 096: Worker-Fetch + Worker-DECODE der Audio-Preview.
// Der schwere decodeAudioData (Opus/MP3 → PCM, der Lade-Flaschenhals:
// 26 s Desktop / 60–90 s Mobile) läuft im Web-Worker via
// OfflineAudioContext — der JS-Main-Thread bleibt frei. Das Ergebnis
// wird als 16-bit-PCM-WAV an den Main-Thread transferiert; WaveSurfer
// dekodiert die unkomprimierte WAV dann in Millisekunden (kein
// Kompressions-Decode mehr im UI-Kontext).
// Fallback: Safari-Worker haben kein OfflineAudioContext → der rohe
// ArrayBuffer geht zurück und WS dekodiert das Originalformat wie bisher.
/// <reference lib="webworker" />

function pcmToWav(channels: Float32Array[], sampleRate: number): ArrayBuffer {
  const numCh = channels.length;
  const numFrames = channels[0].length;
  const bytesPerSample = 2;
  const dataSize = numFrames * numCh * bytesPerSample;
  const buffer = new ArrayBuffer(44 + dataSize);
  const view = new DataView(buffer);
  const writeStr = (off: number, s: string) => {
    for (let i = 0; i < s.length; i++) view.setUint8(off + i, s.charCodeAt(i));
  };
  writeStr(0, "RIFF");
  view.setUint32(4, 36 + dataSize, true);
  writeStr(8, "WAVE");
  writeStr(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true); // PCM
  view.setUint16(22, numCh, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * numCh * bytesPerSample, true);
  view.setUint16(32, numCh * bytesPerSample, true);
  view.setUint16(34, 16, true);
  writeStr(36, "data");
  view.setUint32(40, dataSize, true);
  let off = 44;
  for (let i = 0; i < numFrames; i++) {
    for (let c = 0; c < numCh; c++) {
      const s = Math.max(-1, Math.min(1, channels[c][i]));
      view.setInt16(off, s < 0 ? s * 0x8000 : s * 0x7fff, true);
      off += 2;
    }
  }
  return buffer;
}

async function decodeToWav(arrayBuffer: ArrayBuffer): Promise<ArrayBuffer | null> {
  try {
    if (!("OfflineAudioContext" in self)) return null;
    const decodeCtx = new OfflineAudioContext(2, 1, 48000);
    const decoded = await decodeCtx.decodeAudioData(arrayBuffer);
    // Change 096: Auf 16 kHz herunterrendern — Opus-Dateien melden immer
    // 48 kHz; der Browser-AudioBuffer wäre sonst 3× so groß (95 min:
    // ~1,1 GB statt ~365 MB float) und sprengt Mobile-RAM.
    const outRate = 16000;
    const outLen = Math.ceil((decoded.length * outRate) / decoded.sampleRate);
    const renderCtx = new OfflineAudioContext(decoded.numberOfChannels, outLen, outRate);
    const src = renderCtx.createBufferSource();
    src.buffer = decoded;
    src.connect(renderCtx.destination);
    src.start(0);
    const rendered = await renderCtx.startRendering();
    const channels: Float32Array[] = [];
    for (let c = 0; c < rendered.numberOfChannels; c++) {
      channels.push(rendered.getChannelData(c));
    }
    return pcmToWav(channels, rendered.sampleRate);
  } catch {
    return null; // Decode fehlgeschlagen → Main-Thread-Fallback (Originalformat)
  }
}

self.onmessage = async (e: MessageEvent<{ url: string }>) => {
  try {
    const resp = await fetch(e.data.url);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const total = Number(resp.headers.get("content-length") || 0);
    const body = resp.body;
    let raw: ArrayBuffer;
    if (!body) {
      raw = await resp.arrayBuffer();
    } else {
      const reader = body.getReader();
      const chunks: Uint8Array[] = [];
      let received = 0;
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        chunks.push(value);
        received += value.length;
        if (total > 0) {
          self.postMessage({ type: "progress", pct: Math.min(100, (received / total) * 100) });
        }
      }
      const merged = new Uint8Array(received);
      let off = 0;
      for (const c of chunks) {
        merged.set(c, off);
        off += c.length;
      }
      raw = merged.buffer;
    }
    // Change 096: Der schwere Decode passiert HIER im Worker.
    const wav = await decodeToWav(raw);
    if (wav) {
      self.postMessage({ type: "done", arrayBuffer: wav, wav: true }, { transfer: [wav] });
    } else {
      self.postMessage({ type: "done", arrayBuffer: raw, wav: false }, { transfer: [raw] });
    }
  } catch (err) {
    self.postMessage({ type: "error", reason: String(err) });
  }
};
