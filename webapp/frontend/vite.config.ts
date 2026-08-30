import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  base: "/",
  build: {
    outDir: "dist",
  },
  resolve: {
    alias: {
      // Lokales Vendor-File statt node_modules: WaveSurfer RecordPlugin
      // rendert die Scrolling-Waveform alle 10 ms (100×/s kompletter
      // wavesurfer.load) — das blockiert den Main-Thread auf Tablets
      // (Ruckeln der Rec-Button-Animation). Vendor-Patch: 100 ms (10 FPS,
      // visuell gleichwertig). Siehe src/vendor/wavesurfer-record.js.
      "wavesurfer.js/dist/plugins/record.js": new URL(
        "./src/vendor/wavesurfer-record.js",
        import.meta.url
      ).pathname,
      // Lokales Vendor-File statt node_modules: WaveSurfer TimelinePlugin
      // initialisiert die Zeit-Labels einmal mit scrollWidth=0 (Wellenform
      // noch nicht geladen) → defaultTimeInterval(0)=Infinity → nur die
      // 0-Marke wird gerendert; "zoom"/"ready" führen nie zu einem Redraw
      // (nur "redraw" ist abonniert, das beim Peaks-Load nicht feuert).
      // Vendor-Patch: zusätzlich auf "zoom" + "ready" hören. Siehe
      // src/vendor/wavesurfer-timeline.js.
      "wavesurfer.js/dist/plugins/timeline.js": new URL(
        "./src/vendor/wavesurfer-timeline.js",
        import.meta.url
      ).pathname,
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    include: ["src/**/*.test.{ts,tsx}"],
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8088",
        changeOrigin: true,
      },
      "/auth": {
        target: "http://localhost:8088",
        changeOrigin: true,
      },
      "/health": {
        target: "http://localhost:8088",
        changeOrigin: true,
      },
    },
  },
});
