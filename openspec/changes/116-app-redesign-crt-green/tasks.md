# Tasks — Change 116 (App-Redesign CRT-Grün)

## Done

- [x] Design-Tokens: tailwind.config.js + index.css auf CRT-Grün (Akzent #2ea043)
- [x] Farb-Sweep Blau→Grün über alle Komponenten (Waveform, UploadZone,
      QueueWatcher, InstallBanner, StatsBar, App-Header, Toggle-Accents)
- [x] OptionsPanel.tsx: 3 Tabs (Vorbereitung/Sprechererkennung/Nachbearbeitung),
      „?"-Hilfen mit Modell/Technik (de/en/pt), Ausgrauen je Aktion
- [x] RecordingCard: Aktions-Tabs (Transkribieren/Sprecher suchen/Neue
      Wortzeiten), Optionen-Toggle, Start-Button, Export-Button (Download-Menü)
- [x] Backend: /rediarize akzeptiert num_speakers/min_duration_off/method
      (übersteuert Run-Settings) — service.py + segments.py + api.ts + hooks.ts
- [x] i18n-Keys de/en/pt (act_tr, act_spk, act_alg, start_btn, start_cap, export …)
- [x] Tests angepasst (Change-116-Block) — 309/309 grün, tsc grün,
      Backend test_rediarize 10/10, Browser-Theme-Check grün

## Offen

- [ ] CI nach Push prüfen + melden
