# Change 186 — Sprachwähler (Default AUTO, manuell = Backend-Capabilities)

**Status:** Proposal

## Befund (Live, prod KI-Box — User 2026-09-08)

User: „bei dieser Transkription versagt parakeet total und erkennt häufig
Englisch. Können wir einen Sprachwähler einbauen — Default AUTO, manuell
auswählbar: eine der Sprachen, die das Backend-Modell per capabilities
unterstützt?"

Konkret betroffen: **ps-pk-onnx** (approach-a, `parakeet-tdt-0.6b-v3`) — das
Default-Backend der Webapp. Deutsche Aufnahmen werden teils als englischer
Text transkribiert.

## Ist-Zustand (verifiziert 2026-09-08)

1. **UI:** Das Transkriptions-Options-Panel (`RecordingCard.tsx`,
   `FeatureValues`) kennt VAD/Diarize/Streaming/Noise/Enhance/Separate/
   Backend/Punctuation/LLM — **kein Sprach-Feld**.
2. **API:** `upload_recording` (recordings.py:862) und die re-transcribe-Route
   akzeptieren Form-Felder für alle Settings — **kein `language`-Feld**.
   `create_queued_run` (crud.py) hat zwar einen `language`-Parameter, aber der
   Upload-Router übergibt ihn nie → Run.language ist immer NULL (AUTO).
3. **service.py process_recording:** liest `run.language` NIRGENDS; ruft
   `client.transcribe_streaming/transcribe_async(...)` OHNE language; schreibt
   danach `language = result["language"]` (was das Backend behauptet).
4. **Adapter** (pk_python, pk_cpp, qwen3_asr_http, crisp_asr_http,
   openai_compat_http): `transcribe()`-Signaturen haben KEIN language-kwarg,
   senden kein `language`-Form-Feld an den OpenAI-kompatiblen Endpoint.
5. **Backend approach-a** (app.py): `transcribe_audio()` liest nur
   `model`/`response_format` aus dem Formular — **ignoriert `language`**
   komplett; der verbose_json-Response enthält HARTKODIERT
   `"language": "english"` (Zeile ~1061) — auch bei deutscher Transkription.
6. **Modell-Fähigkeit:** `parakeet-tdt-0.6b-v3` ist laut loader.py
   „NeMo Parakeet 0.6B Multilingual"; README: 25 Sprachen (de, en, fr, …)
   mit automatischer Spracherkennung. Das onnx_asr-Modul unterstützt
   Sprach-Forcing über `<|lang|>`-Token nur bei AED-Modellen (Canary,
   nemo.py `_decoding` Zeile 232–238: `language` → batch_tokens[:,4]).
   **TDT-Modelle (parakeet) haben diesen Mechanismus nicht** — onnx_asr
   `NemoConformerTdt` erbt von `_AsrWithTransducerDecoding`, dessen
   `_decoding()` nur `need_logprobs` liest. → Sprach-Forcing im Modell ist
   für parakeet-tdt NICHT möglich; die Sprache wird vom Modell auto-erkannt.
7. **Capabilities:** `BackendCapabilities.languages` existiert bereits und
   wird pro Backend aus `backends.yaml` geladen (ps-pk-onnx: [de, en],
   moonshine-de: [de], canary: [de, en, fr, es], …). `/api/models/status`
   liefert sie an die UI (`models.py:211`). Die Model-Matrix
   (`fetchModelsMatrix`) enthält sie ebenfalls.

## Ziel

**Sprachwähler in der Transkriptions-Optionen** mit:
- **Default: AUTO** (= bisheriges Verhalten, Sprache vom Modell erkennen lassen)
- **Manuell:** genau die Sprachen, die das gewählte Backend in seinen
  Capabilities deklariert (`languages`-Liste), mit Anzeigenamen
  (de → Deutsch, en → Englisch, …)

Die gewählte Sprache wird durchgereicht: UI → Upload/Re-Transcribe-API →
TranscriptionRun.language → service.py → Adapter → Backend-Request
(`language`-Form-Feld, OpenAI-konform). Backends, die Forcing unterstützen
(Canary/Whisper-Familie via onnx_asr/CrispASR), forcieren damit; ps-pk-onnx
(TDT, kein Forcing) erhält den Parameter als Metadatum + Signal — der Nutzen
dort ist primär, dass die ERKANNTE Sprache korrekt zurückgemeldet wird.

**Zusatz-Fix (Kern des „erkennt Englisch"-Befunds):** approach-a meldet
hartkodiert `"language": "english"`. Die echte erkannte Sprache muss aus dem
Modell kommen (parakeet-tdt liefert sie über den Decoder-Pfad nicht explizit —
prüfen: onnx_asr-TimestampedResult hat kein language-Feld). Pragmatisch:
ohne Forcing bleibt `language` im Response None/ausgelassen → die Webapp
speichert dann die USER-WAHL (AUTO → None), statt fälschlich „english".
So verschwindet die falsche englische Sprach-Anzeige in der UI
(RecordingCard zeigt `r.language` an).

## Umsetzung (Schichten)

1. **Backends (approach-a, pk-asr-cpp + OpenAI-kompatible):**
   - `language`-Form-Feld akzeptieren; wenn gesetzt und das Modell es kann
     (Canary), an `recognize(..., language=...)` durchreichen.
   - Hartkodiertes `"language": "english"` entfernen; stattdessen die
     erkannte Sprache zurückgeben, wenn verfügbar, sonst weglassen (None).
   - Für OpenAI-kompatible Server (CrispASR-Whisper/Canary, qwen3, remote):
     `language` ist ein Standard-Form-Feld — nur durchreichen.
2. **Adapter** (`webapp/app/asr_client/__init__.py` + 5 Adapter):
   `transcribe/transcribe_streaming/transcribe_async` bekommen
   `language: Optional[str] = None`; wenn gesetzt → `data["language"] = ...`.
3. **API-Router** (recordings.py upload + re-transcribe + url_import +
   recovery): `language: Optional[str] = Form(None)` akzeptieren und an
   `create_queued_run(language=...)` übergeben; Validierung gegen die
   Backend-Capabilities (unbekannte Sprache → 422 oder still AUTO? —
   Entscheidung: still AUTO + Log, da alte Clients kein Feld senden).
4. **service.py:** `run.language` aus dem Run lesen (wie die anderen
   Settings, Change 099-Muster) und an die Adapter-Calls durchreichen.
5. **Frontend** (RecordingCard.tsx, FeatureToggles.tsx):
   - `FeatureValues.language: string` ("" = AUTO).
   - Options-Panel: Sprach-Select — Optionen aus der Model-Matrix des
     gewählten Backends (`matrix.find(b => b.backend === feat.backend)
     .languages`), mit AUTO als erstem Eintrag; Anzeigenamen über eine
     kleine de/en/fr/es/…-Map.
   - Upload-FormData und Re-Transcribe-Payload um `language` ergänzen
     (nur wenn != "").
6. **Anzeige:** RecordingCard zeigt `r.language` — bei AUTO/None ausblenden
   oder „Auto", damit nicht fälschlich „Englisch" steht.

## Tests

- **Backend approach-a:** Transkription mit `language=de` → kein
  „english"-Hardcode mehr; Response ohne language-Feld bei AUTO.
- **Adapter:** MockTransport-Test — `language=de` landet im Form-Data;
  language=None sendet kein Feld.
- **Router:** upload mit `language=de` → Run.language == "de"; ohne Feld →
  None (AUTO); unbekannte Sprache → AUTO.
- **service.py:** Run.language wird an den Adapter-Call durchgereicht
  (Monkeypatch-Spy auf client.transcribe_async).
- **Frontend:** Sprach-Select zeigt AUTO + Backend-Sprachen; Auswahl landet
  in FormData; Backend-Wechsel aktualisiert die Sprach-Optionen.

## Offene Punkte / Risiken

- **parakeet-tdt kann kein echtes Sprach-Forcing** (TDT-Architektur) — der
  Sprachwähler verbessert die Erkennung bei ps-pk-onnx NICHT direkt. Der
  reale Hebel für „erkennt Englisch": (a) korrekte Sprach-Anzeige (Fix oben),
  (b) für Forcing auf ein Canary-/Whisper-Backend wechseln, (c) prüfen, ob
  eine deutsch-spezifische Modellvariante (parakeet-tdt-0.6b-v2-de o.ä.)
  existiert und als eigenes Backend angeboten werden soll. → Dem User im
  Ergebnisbericht transparent machen.
- UI-Sprachenliste muss zur Backend-Liste passen (de-Display „Deutsch").
- Alte Clients/offlineQueue senden kein language → Default AUTO bleibt
  kompatibel.
