# Change 015 — Design

## Kontext

Der Export (Change 008, template-basiert) ist funktional, aber: (1) das
Encoding-Problem ist aus Sicht der Ziel-Editoren ungelöst — `charset=utf-8`
im Header hilft dem Browser, nicht dem Editor nach dem Speichern; (2) es
gibt nur 3 Formate; (3) kein vollständiger, wieder-importierbarer Export.

## Entscheidungen

### 1. Encoding: UTF-8 mit BOM (`utf-8-sig`) für Text-Exporte

- **Ansatz:** `download_transcript` encodiert den gerenderten String je
  Extension: Text-Extensions (`txt, srt, vtt, csv, ass, transcript, …`)
  → `content.encode("utf-8-sig")` (BOM-Prefix), `json|jsonl` → reines
  `utf-8`. `Response(content=bytes, media_type=…, headers=…)`.
- **Warum BOM:** Die Spezifikationen erlauben BOM in UTF-8; Windows-
  Editoren (Notepad < 1903, Excel, ältere Tools) erkennen UTF-8 ohne BOM
  NICHT und rendern Latin-1 → „Ã¤". BOM ist die einzige verlustfreie
  Heuristik, die auf allen Zielsystemen funktioniert.
- **Warum nicht `utf-8-sig` überall:** JSON-Dateien mit BOM sind für
  strikte Parser problematisch (und unnötig — JSON-Editoren erkennen
  UTF-8). SRT/VTT werden von Videoplayern meist BOM-tolerant gelesen;
  die Alternative (kein BOM) bricht in Windows-Editoren. Trade-off
  akzeptiert: BOM für alles, was ein Mensch in einem Editor öffnet.
- **Regressionstest:** Golden-Test „Umlaute im TXT-Download starten mit
  `b"\xef\xbb\xbf"` und enthalten `Grüße` als korrekte UTF-8-Bytes".

### 2. Neue Templates: dateibasiert, SubtitleEdit-Vokabular

- **Ansatz:** Sechs neue JSON-Dateien in `app/export_templates/`, die beim
  Start nach `DATA_DIR/export_templates/` kopiert werden (bestehender
  Mechanismus `ensure_standard_templates`). Kein Code für csv/youtube/ass/
  transcript/jsonl nötig — nur Platzhalter-Kombinationen.
- **Word-Level-SRT** braucht dagegen eine kleine Renderer-Erweiterung:
  neues optionales Template-Feld `format_paragraph_word` + `format_timecode_word`.
  `render_template`: wenn das Feld existiert UND Segmente Word-Arrays mit
  `start/end/text` haben → Loop über Wörter (alle Segmente), sonst
  Segment-Loop (Fallback). Damit bleibt das Template-System deklarativ.
- **Dropdown:** `RecordingCard.tsx` lädt `GET /export-templates` einmal
  beim Mount und baut das Dropdown daraus (Fallback: harte Liste, falls
  der Call fehlschlägt — stille Fehler inakzeptabel, aber hier harmlos:
  hartkodierte Liste bleibt nutzbar).

### 3. Backup-Schema v1 (`transcript.json`)

```json
{
  "schema_version": 1,
  "type": "polyschnack-backup",
  "exported_at": "2026-08-18T…Z",
  "app_version": "…",
  "recording": {
    "uid": "<export-uuid, KEINE DB-Interna>",
    "title": "…", "original_name": "…", "language": "de",
    "backend": "…", "duration_s": 1340.7,
    "created_at": "…", "segments_manual": false,
    "settings": { "enable_vad": false, "enable_diarize": false,
      "diarize_method": null, "diarize_num_speakers": null,
      "diarize_min_duration_off": null, "enable_noise_reduce": true,
      "enable_enhance": "off", "enable_punctuation": false,
      "enable_llm_enhance": false, "enable_streaming": false,
      "prompt_template_name": null, "delivery_target_name": null },
    "text": "…",
    "segments": [ { "start": 0.0, "end": 3.2, "text": "…",
      "speaker": "SPEAKER_00", "words": [ {"start":…, "end":…,
      "word": "…", "confidence": 0.98} ] } ],
    "versions": [ { "version_no": 1, "kind": "transcribe",
      "text": "…", "segments": […], "backend": "…",
      "language": "de", "created_at": "…" } ],
    "retention_minutes": null
  }
}
```

- **Keine DB-IDs:** `recording.uid` ist eine frisch generierte Export-UUID
  (nicht die DB-uid), `versions` tragen keine `created_by_user_id`-IDs.
  Anon-Backups: `retention_minutes` = verbleibende Minuten (aus
  `last_seen_at`-Logik), null bei registrierten Usern.
- **Versionen:** `TranscriptVersion`-Snapshots (text+segments je Änderung)
  werden mit exportiert — Import stellt sie wieder her, Diff/Restore
  funktioniert nach dem Import.
- **Settings-Namen:** Referenzen auf PromptTemplate/DeliveryTarget werden
  als NAME exportiert (nicht als DB-FK), weil die Ziel-Instanz andere IDs
  hat; beim Import wird nach Name aufgelöst (fehlt er → null, kein Fehler).

### 4. Backup-ZIP-Struktur

```
<stem>-backup-<exportuuid>.zip
├── transcript.json     # Schema v1 (s. o.)
├── audio.<ext>         # Kopie von stored_path (Original)
├── transcript.txt      # Plain-Text-Export (BOM, wie Download)
├── transcript.srt      # SRT-Export
└── manifest.json       # {"schema_version":1,"files":{"transcript.json":"sha256:…",…}}
```

- `build_backup_zip` streamt die Dateien in einen `io.BytesIO`/tempfile,
  hashat beim Schreiben (ein Pass), hängt `manifest.json` zuletzt an.
- Dateinamen: `transcript.txt/.srt` werden über die bestehenden
  Template-Renderer erzeugt (Konsistenz mit Download garantiert).
- `GET /recordings/{rid}/backup`: `ensure_access(…, "full")`,
  `status=="done"` (sonst 409), Response mit `Content-Disposition` +
  `application/zip`.

### 5. Import

- `POST /recordings/import-backup` (Multipart `file`): ZIP in Temp-Datei,
  `zipfile.ZipFile` → `manifest.json` lesen → für jede gelistete Datei
  SHA-256 verifizieren (Mismatch → 400 „Integritätsprüfung fehlgeschlagen").
  `transcript.json` parsen → `schema_version` prüfen (≠1 → 400 mit
  „nicht kompatible Backup-Version").
- Audio-Extension aus `audio.*` ableiten, Datei nach
  `storage_path_for(uid, ext, anon=…)` kopieren (Change-014-Pfade),
  `probe_duration_path` validiert. Dann `Recording` anlegen:
  `status="done"`, Titel/Dateiname/Sprache/Backend/Dauer/Einstellungen/
  Segmente/Words aus dem JSON, `owner_user_id` = aktueller User,
  `content_hash` = SHA-256 der Audio-Datei. `TranscriptVersion`-Snapshots
  in `version_no`-Reihenfolge anlegen.
- **Kein Transkriptions-Job:** alles synchron, ein Request.
- **Anon:** normale Upload-Logik (Limits, Retention ab Import-Zeitpunkt).

## Offene Fragen

- Soll der Backup-Import auch `share_token`/Shared-Status übernehmen?
  → Nein, v1: neues Recording ohne Shares (Owner = Importer). Sicherer
  Default, kein Leak über Backups.
- Word-Level-SRT: Timecode-Darstellung pro Wort mit `format_timecode_word`
  oder Standard-`format_timecode`? → v1: Standard-Timecode-Feld wiederverwenden,
  nur der Loop ändert sich; `format_timecode_word` optional für später.

## Trade-offs

- **BOM vs. puristisches UTF-8:** BOM ist für strikte Unix-Parser ein
  Störfaktor, aber die Zielgruppe (Windows-Editoren, Excel) gewinnt.
  Text-Formate sind von Natur aus Editor-orientiert → BOM. JSON bleibt
  BOM-frei.
- **ZIP mit Kopien statt Referenzen:** Backup muss standalone
  wiederherstellbar sein (auch nach Retention/Deploy) → Kopien, keine
  Pfad-Referenzen.
- **Import legt neues Recording an** (statt bestehendes zu überschreiben):
  idempotent, kein Risiko für bestehende Daten; Duplikat-Erkennung über
  `content_hash` greift wie bei Uploads.
