# Post-Processing

## Purpose

Nach der Transkription optional nachbearbeiten (LLM via Server-Env oder
eigenem BYOK-Endpunkt) und an eigene Ziele zustellen (E-Mail, WebDAV).
Alles strikt opt-in.

## Requirements

### Req 1: Prompt-Templates

- **Ablauf:** CRUD `routers/templates.py` (`/api/templates`) — owner-only,
  nur registrierte User (paid). Ein Template ist ein System-Prompt; `{text}`
  wird durch die Transkription ersetzt.
- **Auswahl:** `prompt_template_id` am Transcribe/Retranscribe → das Ergebnis
  wird eine neue Version `kind="postprocess"`.

#### Scenario: Anon kann kein Template anlegen

- **Akteure:** Anonymer User.
- **Eingaben:** `POST /api/templates`.
- **Ergebnis:** 403 „login required (paid path)".

### Req 2: LLM-Pfad (Server-Env + BYOK)

- **Ablauf:** `llm.py::chat(system, user_text, endpoint=None)` ruft einen
  OpenAI-kompatiblen Endpunkt (`{base_url}/chat/completions`). Ohne
  `endpoint` gelten `POLYSCHNACK_LLM_URL/API_KEY/MODEL` (Server-Env);
  mit `endpoint` (BYOK) gewinnt der User-Endpunkt.
- **BYOK:** `UserLlmEndpoint` (user_id, name, base_url, Fernet-verschlüsselter
  api_key, model). CRUD `routers/llm_endpoints.py` — owner-only, nur OIDC,
  **SSRF-Blockliste** in `llm_url.py` (private Netze, localhost, Metadata →
  422). Der Key wird nie ausgegeben; PUT ohne Key behält den alten.
- **Pipeline:** `service.py::process_recording` lädt Endpunkt/Template erst im
  Worker (eigene Session), entschlüsselt den Key nur für den Request,
  loggt ihn nie.

#### Scenario: BYOK-Key bleibt geheim

- **Akteure:** User mit Mistral-BYOK.
- **Eingaben:** `PUT /api/llm-endpoints/1` ohne api_key.
- **Ergebnis:** Key bleibt unverändert; keine Antwort enthält ihn.

#### Scenario: SSRF-Versuch

- **Akteure:** Böswilliger User.
- **Eingaben:** `POST /api/llm-endpoints` mit `base_url="http://169.254.169.254/"`.
- **Ergebnis:** 422 „private/loopback-Adressen sind nicht erlaubt".

### Req 3: Delivery-Targets

- **Ablauf:** CRUD `routers/targets.py` (`/api/targets`) — kind
  `email|webdav`; `config`-JSON, Passwörter Fernet-verschlüsselt
  (`crypto.py`, Schlüssel aus SESSION_SECRET). Für alle User (auch anonym).
- **Zustellung:** `deliver.py` — E-Mail via smtplib (TXT+JSON-Anhang,
  `POLYSCHNACK_SMTP_*`), WebDAV via httpx PUT (Basic-Auth, Zielpfad).
- **Status:** `delivery_status ∈ pending|done|failed` + `delivery_error`
  am Recording; Transcribe setzt `pending`, Worker aktualisiert.

#### Scenario: Meeting-Zusammenfassung + Mail

- **Akteure:** Registrierter User mit Template „Zusammenfassung" und
  E-Mail-Target.
- **Eingaben:** Transcribe mit `prompt_template_id=…, delivery_target_id=…`.
- **Ergebnis:** Nach ASR läuft der LLM-Pass (Server-Env oder BYOK je Auswahl);
  `postprocess`-Version entsteht; E-Mail mit TXT+JSON fliegt raus;
  `delivery_status="done"`.

#### Scenario: Delivery-Fehler

- **Akteure:** User mit falsch konfiguriertem WebDAV-Target.
- **Eingaben:** Transcribe mit `delivery_target_id=…`.
- **Ergebnis:** `delivery_status="failed"`, `delivery_error` mit Meldung;
  Transkription selbst bleibt `done`.
