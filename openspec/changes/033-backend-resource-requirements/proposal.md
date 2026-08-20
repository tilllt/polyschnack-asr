# Change 033 — Backend-Ressourcen-Requirements + 207er-Nachlauf (whisper/voxtral)

## Problem

Die Mindest-Ressourcen der ASR-Benchmark-Backends (VRAM, Miet-Disk, Modell-
größen) waren nirgends dokumentiert. Das führte zu Fehlentscheidungen bei der
vast-Miete: **voxtral-mini-realtime braucht 16 GB+ VRAM** (Modellkarte), der
Runner mietete aber ausschließlich 12-GB-Karten (GPU_PREF 3060/4070) → die
nächtlichen 207er-Läufe (20.08., 00:12–04:20) hingen bis zum Cron-Timeout
(3600 s) und lieferten kein Ergebnis. Zusätzlich fehlten **whisper-large-v3**
und **voxtral-mini-realtime** komplett in der 207er-Rangliste (nur 4 von 6
Backends gemessen).

## Ziel

1. **Requirements je Backend** in `docs/benchmark/requirements/`: belegte
   Mindestwerte für GPU/VRAM, Miet-Disk, Modell-/Image-Größen, Port/Health,
   slow_start, Lizenzen und Besonderheiten — als Entscheidungsbasis für
   künftige Läufe (auch fürs Ressourcen-Checking der Box-Services).
2. **GPU-Auswahl env-steuerbar** im Runner (`VAST_GPU_PREF`, `VAST_MAX_PRICE`);
   Default bleibt `RTX 3060, RTX 4070` / 0,35 $/h (User-Vorgabe 18.08.).
3. **207er-Nachlauf** whisper-large-v3 + voxtral-mini-realtime auf frischen
   Instanzen — als Hintergrundprozess mit notify statt Cron (Cron-Cap 3600 s
   war kleiner als Miete+Modell-Start+Transkription).

## Entscheidungen

- **Doku im Repo polyschnack-asr** (`docs/benchmark/requirements/`, eine Datei
  je Backend + README mit Übersicht und Methodik). Die Runner-Skripte selbst
  (`/opt/data/scripts/start_timing_vast.py`, `backend_benchmark_full.py`)
  bleiben auf dem Betreiber-Host (nicht versioniert) — sie referenzieren
  Host-Pfade und lesen Secrets aus der Host-`.env`.
- **Keine Schätzwerte:** Modellgrößen per HF-HEAD (Content-Length, 20.08.),
  Image-Größen per Harbor-/Docker-Hub-API; GHCR-Größen sind nicht öffentlich
  abrufbar (403/404) → dort Modellgrößen statt Image-Größen dokumentiert.
  VRAM-Klassen belegt durch erfolgreiche Läufe (3060 bzw. 3090).
- **voxtral-Lauf** mit `VAST_GPU_PREF="RTX 3090, RTX 4090"` und
  `VAST_MAX_READY_WAIT_S=3600` (vLLM lädt 10+ GB, belegt 19.08.).
- **Alt-Instanzen aufgeräumt:** 2 „running"-3060er ohne erreichbaren Server
  (whisper-Image bzw. vLLM — Container nie bereit) + 2 exited 3090er
  (qwen3/ark-Debug) wurden per DELETE entfernt (20.08., ~0,42 $/h Einsparung).

## Nicht-Ziele

- Kein automatisches Ressourcen-Checking zur Laufzeit (Server-Crash-Erkennung
  im Runner bleibt unverändert).
- Keine ark-Fehleranalyse (UTF-8/WER 1.0) — separat aus der Nacht-Suite offen.
- Kein Verschieben der Runner-Skripte ins Repo.
- Kein `--instance`-Reuse für die 207er-Läufe (frische Instanz = faire
  Startzeitmessung, User-Vorgabe).

## Offene Fragen

- GHCR-Image-Größen: nur mit Lese-Recht des Paket-Owners abrufbar — ggf. später
  einmalig per `docker manifest inspect` dokumentieren.
