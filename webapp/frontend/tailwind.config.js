/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "#0c0e14",
        panel: "#13161f",
        panel2: "#1a1e2a",
        panel3: "#1f2432",
        border: "#252a38",
        border2: "#2e3447",
        txt: "#dde3f0",
        muted: "#7a859a",
        muted2: "#5a6478",
        accent: "#5b8cff",
        accent2: "#3a6de0",
        ok: "#3fb950",
        warn: "#d29922",
        err: "#f85149",
        proc: "#58a6ff",
        "seg-bg": "#1c2133",
        "seg-hl": "#2a3558",
        "seg-hl-border": "#5b8cff",
      },
      borderRadius: {
        card: "12px",
        sm: "7px",
      },
      keyframes: {
        "toast-in": {
          from: { opacity: "0", transform: "translateY(8px)" },
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
  plugins: [],
};
