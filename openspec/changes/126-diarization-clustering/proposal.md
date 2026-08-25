# Change 126 — Diarization-Pipeline: globales Speaker-Clustering erzwingen

## Problem

Diarization liefert bei realem Meeting (75 min, 3 Speaker, Mono-Raummikrofon)
26/26 Segmente mit **SPEAKER_00** — ein einziger „Speaker". Manuelle
CLI-Tests mit den Prod-Modellen (CrispASR 0.8.29 lokal) belegen: **die
Modelle funktionieren** — pyannote-seg-3.0+TitaNet findet 5 Cluster (314
Segmente), foxnose+WeSpeaker findet 4 Cluster (534 Segmente, 492 Turns,
Verteilung 49/24/22/5 %). Die Pipeline zerstört das Ergebnis.

Root Causes (Code-verifiziert):

1. **Chunk-lokale Labels (CrispASR #292):** `diarize.py` sendet
   `chunk_seconds=30` → der Server diarisiert pro 30-s-Chunk; die
   Speaker-Labels sind **chunk-lokal** („A" in Chunk 1 ≠ „A" in Chunk 50).
   Der Server markiert das mit `chunk_id` — `diarize.py` **ignoriert
   chunk_id** und mappt jedes Label blind global.
2. **Kein garantiertes globales Clustering:** Global stabile IDs entstehen
   nur mit Embedder (Server: `diarize_embedder` = auto/TitaNet bzw.
   WeSpeaker bei foxnose; Code crispasr_server.cpp Z. 1516, Fallback
   „auto" Z. 787). Die Webapp sendet **keinen** `diarize_embedder` — sie
   vertraut der Server-Config, die auf der KI-Box offenbar nicht greift
   (oder Container-Version älter als das Clustering). Ergebnis: jedes
   Segment bekommt Default-„A" → alles SPEAKER_00.
3. **Härtungslücke `_normalise_speaker`:** versteht nur einzelne
   Buchstaben A–Z; „(speaker 0)"/„speaker N"/Zahlen fallen lautlos auf
   SPEAKER_00.
4. **Keine Qualitäts-Sichtbarkeit:** 1 Speaker bei 75-min-Audio geht still
   durch (kein Log, kein UI-Hinweis).

## Lösung

Webapp-Code (diarize.py/config/service.py) + Deploy-Doku:

1. **`diarize.py` sendet `diarize_embedder` explizit** — neue Config
   `DIARIZE_EMBEDDER` (Default „auto" = TitaNet beim Server; bei
   `diarize_method=foxnose` wird der WeSpeaker-Pfad gesendet). Damit
   erzwingt der Request serverseitig das globale Clustering, unabhängig
   von der Container-Config.
2. **Default-Methode auf `foxnose`** (beste Testergebnisse: 4 Speaker,
   feinste Turns, ausgewogenste Verteilung) — `DIARIZE_METHOD`-Default in
   config.py; whitelist bleibt (pyannote weiterhin wählbar).
3. **`_normalise_speaker` härten:** „(speaker N)", „speaker N", nackte
   Zahlen 0–99 → SPEAKER_0N (bisher: stiller Fallback auf SPEAKER_00).
4. **Qualitäts-Warnung:** `_run_diarization` loggt warning, wenn bei
   Audio > 10 min nur **1** Speaker erkannt wird („Diarization lieferte
   nur 1 Speaker bei X min — Embedder/Clustering serverseitig prüfen")
   — kein stiller Fail mehr; Status/Fehler sichtbar.
5. **`chunk_id` dokumentieren:** nach globalem Clustering sind Labels
   konsistent; `diarize.py` loggt debug bei mehreren chunk_ids, damit
   Regressionen (Server ohne Clustering) sichtbar werden.
6. **Deploy-Doku:** Abschnitt im Repo (README/Compose-Kommentar), dass der
   diar-Container eine CrispASR-Version mit Embedder/Clustering braucht
   und die Modelle (pyannote-seg-3.0.gguf, titanet-large.gguf bzw.
   wespeaker-resnet34-lm.gguf) im Cache liegen müssen; Env-Beispiel.

Nicht Teil dieses Changes: Server-Binary/Image selbst (wird vom User
deployt), UI-Redesign der Speaker-Anzeige.

## Betroffene Dateien

- `webapp/app/diarize.py` (diarize_embedder senden, chunk_id-Doku,
  _normalise_speaker härten)
- `webapp/app/config.py` (DIARIZE_METHOD-Default foxnose, DIARIZE_EMBEDDER)
- `webapp/app/service.py` (_run_diarization: 1-Speaker-Warnung)
- `webapp/tests/` (neue Tests: normalise_speaker, Request-Builder, Warnung)
- Deploy-Doku (README/Compose-Kommentar)

## Verifikation

1. Backend-Tests grün (neu: normalise_speaker-Formate, diarize.py sendet
   embedder, Warnung bei 1 Speaker).
2. Frontend unverändert grün (Regression).
3. Manueller Re-Diarization-Test gegen die reale Datei (nach Deploy durch
   User): erwartet ≥ 3 Speaker mit stabilen Labels statt SPEAKER_00.
4. CLI-Referenz steht (diarize_local.sh: foxnose 4 Speaker / pyannote 5).
