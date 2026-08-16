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
      "/health": {
        target: "http://localhost:8088",
        changeOrigin: true,
      },
    },
  },
});
