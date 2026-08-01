# Change Proposal 005 — Post-Processing, Delivery & BYOK

**Status:** Implemented (retroaktiv)

## Why
- Fertige Transkriptionen automatisch nachbearbeiten (LLM) und zustellen
  (E-Mail/WebDAV); registrierte User mit eigenen LLM-Endpunkten (BYOK).

## What
- `PromptTemplate` (owner-only, nur OIDC — paid) + `routers/templates.py`.
- `DeliveryTarget` (email|webdav, Passwörter Fernet) + `routers/targets.py`
  + `deliver.py` (smtplib/httpx) + SMTP-Env.
- `llm.py::chat(..., endpoint=None)` — Server-Env oder BYOK-Override.
- `UserLlmEndpoint` (Fernet-Key) + `routers/llm_endpoints.py` + SSRF-Blockliste
  `llm_url.py` (private Netze/Metadata → 422).
- Pipeline in `service.py`: Template/Enhance/BYOK → `postprocess`-Version →
  Delivery mit Status (pending|done|failed).
- Frontend: PostProcessPanel (Templates/Targets/Endpoints), Toggles +
  Selects an der Transcribe-Zeile.

## Changes
- Neu: `llm.py`, `crypto.py`, `llm_url.py`, `deliver.py`, `routers/templates.py`,
  `routers/targets.py`, `routers/llm_endpoints.py`, `PostProcessPanel.tsx`;
  Tests `test_llm*.py`, `test_templates_targets.py`, `test_deliver.py`,
  `test_postprocess_pipeline.py`, `test_admin_env_settings.py`.
- Geändert: `models.py` (Recording-Felder), `config.py` (LLM/SMTP/Anon-Env),
  `service.py`, `routers/recordings.py`, `AdminPanel.tsx` (ENV-Badge).

## Downgrade
- BYOK entfernen → nur Server-Env-LLM; Delivery entfernen → Status entfällt.
