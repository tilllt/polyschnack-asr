# Change 182 — Cancel während blockierender Prep-Calls + Recovery verwaister processing-Jobs

**Status:** Proposed

## Befund (2026-08-31, Live: re-transcribe hing in "separate")

1. **Cancel-Matrix-Lücken:** Der Worker prüft cancel_requested nur ZWISCHEN
   den Phasen (nach ASR, nach Diar). Während der blockierenden Prep-Calls
   (VAD/Enhance/**Separation**) gibt es keinen Check — Cancel wirkt erst
   nach dem Call (bis zu 3600 s!).
2. **sep-HTTP-Hang:** SeparateClient hatte read-Timeout 3600 s. Live: der
   sep-Server erzeugte die vocals, der Worker hing trotzdem im
   Antwort-Transfer (5+ min ohne Byte) — Cancel nutzlos, Job stalled.
3. **Kein Recovery für processing:** Nach einem Webapp-Restart blieb
   status=processing verwaist hängen (die Queue ist In-Memory) — nur
   Alignments hatten ein boot-recovery.

## Lösung

- separate_client.py: read-Timeout 3600 → 300 s (idle).
- service.py: `_abort_if_cancelled` direkt NACH der Prep (vor dem ASR).
- service.py/main.py: `recover_stale_processing` — verwaiste
  processing-Jobs beim Boot auf failed (ehrlich, mit Grund).

## Cancel-Matrix (vollständig, aus dem Code)

| Phase | Cancel-Check |
|---|---|
| Prep (VAD/Enhance/Separation) | ✗ während des Calls · **✓ NEU direkt danach** |
| ASR | ✗ während des Calls · ✓ nach ASR (2544) |
| Diarize | ✗ während des Calls · ✓ nach Diar (2623) |
| Aligner/Punctuation | ✗ während des Calls (Timeout nötig — LLM-Pfad prüfen) |
| realign (bg-align) | ✓ vor jeder Gruppe (align_cancelled) |

## Betroffene Dateien

- `webapp/app/service.py`, `webapp/app/separate_client.py`,
  `webapp/app/main.py`
