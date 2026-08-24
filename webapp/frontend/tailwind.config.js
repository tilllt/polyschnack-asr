/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Change 116: CRT-Grün-Theme (User 2026-08-24) — dunkle grünschwarze
        // Flächen, dunkelgrüner Akzent „alter grüner Röhrenmonitor".
        bg: "#070b08",
        panel: "#0d130e",
        panel2: "#121a14",
        panel3: "#18231a",
        border: "#1f2b21",
        border2: "#2c3d2d",
        txt: "#d2e8cd",
        muted: "#7d9c74",
        muted2: "#556b4f",
        accent: "#2ea043",
        accent2: "#1f7a37",
        ok: "#2ea043",
        warn: "#d29922",
        err: "#f85149",
        proc: "#4ade80",
        "seg-bg": "#16231a",
        "seg-hl": "#1c3323",
        "seg-hl-border": "#2ea043",
      },
      borderRadius: {
        card: "12px",
        sm: "7px",
      },
      keyframes: {
        "toast-in": {
          from: { opacity: "0", transform: "translateY(8px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        "toast-out": {
          to: { opacity: "0", transform: "translateY(8px)" },
        },
      },
      animation: {
        "toast-in": "toast-in 0.2s ease",
        "toast-out": "toast-out 0.3s ease 2.7s forwards",
      },
    },
  },
  plugins: [
    // Change 093 (User 2026-08-22): hover-Effekte NUR auf Geräten mit
    // echter Hover-Fähigkeit (Maus/Trackpad). Auf Touch (Android/iOS)
    // bleibt der erste Tap sonst „sticky hover" — das angetippte Wort
    // blieb blau markiert, obwohl das Playback weiterlief.
    function ({ addVariant }) {
      addVariant("hoverable", "@media (hover: hover) { &:hover }");
    },
  ],
};
