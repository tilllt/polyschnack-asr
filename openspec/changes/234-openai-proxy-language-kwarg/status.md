# Change 234 — OpenAI-Proxy: `language` erreicht die Adapter wieder

Nutzer-Vorgabe 29.09.2026, wörtlich:

> ja repariere den bug

(Vorlauf: Bei der Nextcloud-Tag-Transkription wurde der Proxy gemessen — er
antwortete für **alle** Modelle mit 502. Befund gemeldet, Nutzer gab den Fix frei.)

## Ausgangslage

Live gemessen am 29.09.2026 (Revision b3c09f75, `whisper.cia-spandau.de`):
`POST /v1/audio/transcriptions` → **502** für parakeet, qwen3, moonshine, ark,
canary und pk-cpp, Fehlertext:

    transcribe() got an unexpected keyword argument 'language'

Ursache: Change 186/187 (`411b2f2`) gab dem Proxy den Sprachwähler und reichte
`language=<Wahl>` an `client.transcribe(...)`. Der zweite Schritt des damaligen
Plans — „Adapter … bekommen `language: Optional[str] = None`" — blieb ungetan:
ABC und alle fünf Adapter deklarierten weiter
`transcribe(audio_bytes, filename, mime, noise_reduce=True)`. Jeder Aufruf
prallte an der Signatur ab, **bevor** etwas transkribiert wurde.

Warum kein Test das sah: `tests/test_openai_proxy.py` benutzt ein Double
`_FakeClient` mit `transcribe(..., language=None)`. Ein Double, das mehr kann
als die echten Klassen, prüft nur sich selbst — der Fehler war in jedem Lauf grün.

## Umsetzung

- `app/asr_client/__init__.py`: ABC-`transcribe` hat jetzt
  `language: Optional[str] = None`; die Legacy-Funktion `transcribe(...)`
  nimmt und reicht es durch.
- **Eine Regel für das Formularfeld:** neuer Helfer `language_field(language)`
  → `{"language": "de"}` bei echter Wahl, `{}` bei `None` (AUTO). Alle fünf
  Adapter (ps-pk-onnx, pk-cpp, qwen3, crispasr, openai-compat) bauen ihre
  Formulardaten über `{**language_field(language), ...}`.
- AUTO lässt den Request Byte für Byte wie vor dem Sprachwähler (kein Feld,
  kein stiller Default auf eine Sprache). Engines, die die Sprache nicht setzen
  können (ps-pk-onnx: TDT), ignorieren das Feld.
- **Nicht enthalten** (bleibt bei Change 186 offen): `language` in
  `transcribe_streaming` / `transcribe_async` sowie im Run-Modell/`service.py`.

## Prüfstand

- `tests/test_asr_signature_invariant.py` (neu): vergleicht die
  `transcribe`-Signatur **jeder** Adapter-Klasse im Paket mit der Basisklasse
  (Name, Reihenfolge, Vorgabewert). Die Klassen werden per `pkgutil` im Paket
  gesucht — ein neuer Adapter kann sich nicht ausnehmen.
- `tests/test_asr_language_forwarding.py` (neu): je Adapter steht bei
  `language="de"` das Feld im Multipart-Body; ohne Angabe fehlt es.
- `tests/test_openai_proxy.py`: `_FakeClient` trägt die ABC-Signatur, der
  Wächter `test_fake_client_signatur_passt_zum_adapter_abc` hält das fest; zwei
  neue Tests belegen Durchreichen (`de`) und AUTO (`None`).
- 33/34 Tests grün (die drei Dateien). **Zwei rote Gegenproben** belegen, dass die
  neuen Tests den Fehler wirklich fangen: `language`-Parameter aus `pk_cpp`
  entfernt → Invarianten-Test rot; Formularfeld entfernt → Weiterleitungs-Test
  rot. Und mit dem Stand VOR dem Fix (Adapter/ABC auf HEAD zurückgenommen,
  Tests unverändert) sind `test_proxy_gegen_echten_adapter_kein_kwarg_fehler`
  und `test_fake_client_signatur_passt_zum_adapter_abc` rot — also genau die
  502-Situation vom lebenden System.
- Backend-Vollsuite: **1426 Tests grün in 988,9 s** (`cd webapp && .venv/bin/python
  -m pytest tests/ -q`). Achtung: blankes `pytest` im `webapp`-Ordner sammelt
  `benchmark/e2e_test.py` mit und bricht an einer fehlenden SQLite-Datei ab —
  CI prüft `tests/`, lokal genauso aufrufen.
- Live-Abnahme am ausgerollten Stand: Nachtrag (unten).
