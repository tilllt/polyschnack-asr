# Change 150 — Echter Diarization-Fortschritt über CrispASR /progress

**Status:** Proposed (Umsetzung läuft)

## Problem

Die Diarization-Phase ist eine Blackbox (ein synchroner POST an
crispr-diar) — die UI zeigt nur „Sprecher zuordnen …" ohne Zahlen.
Der User fordert echten Fortschritt für ALLE CrispASR-basierten
Services (kein Raten — „Progress nur echt").

## Lösung

1. **CrispASR-Server (upstream-PR):** `GET /progress` liefert
   `{"busy": bool, "progress": -1..100}` — der Whisper-Decode-Fortschritt
   wird in der Chunk-Schleife von `do_transcribe` gesetzt (Scope-Guard
   `progress_scope`, Global-Atomic ok bei einem Job pro Container).
   → PR gegen CrispStrobe/CrispASR (User-Auftrag).
2. **Webapp:** Während `run_diarization` pollt die Webapp `/progress`
   am crispr-diar-Container → `set_progress` mit echten Prozent
   (`note="diarization X%"`).
3. **Frontend:** `phaseDetail` zeigt „X %" für die Diarization-Phase
   (analog „Chunk X/Y" bei ASR).

## Betroffene Services

- **crispr-diar** — /progress ✓ (dieser Change)
- **crispr-* ASR-Backends** — haben bereits echte Chunk-Zähler
  (client-seitiges Chunking, `chunk_index/total_chunks` in der SSE) —
  kein zusätzlicher Bedarf
- **crispr-sep** — htdemucs-Binary ohne Server-/progress; separat
  zu prüfen (Folge-Change falls gewünscht)

## Verifikation

- Server: lokaler Build + Smoke-Test (Server starten, Transkription,
  /progress pollt 0→100)
- Webapp: Unit-Test des Polling-Clients (Mock-HTTP)
- Nach Deploy: Diarization-Phase zeigt echte Prozente
