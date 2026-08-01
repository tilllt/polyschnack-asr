# PolySchnack — Project Specification

> Retroaktive OpenSpec-Dokumentation des IST-Zustands (2026-08-01).
> Webapp: FastAPI + SQLModel + SQLite, React (Vite) Frontend, Docker-Compose-Deployment.

## Purpose

PolySchnack ist ein selbstgehostetes ASR-Transkriptionssystem mit mehreren
Austauschbaren Backends (Parakeet/ONNX, parakeet.cpp, Qwen3-ASR, ARK-ASR,
Voxtral), Web-UI, Warteschlange, Benutzerkonten (OIDC), anonymem Shared Space
und Post-Processing (LLM, Delivery). Betrieben auf einer KI Box (RTX 3090).

## Capabilities

| Capability | Beschreibung |
|---|---|
| [Transcription](specs/transcription/spec.md) | Upload, Transkribieren, Retranskribieren, Toggles, Versionen, Export |
| [Identity & Access](specs/identity-access/spec.md) | OIDC-Login, anonyme Sessions, Admin-Designation, API-Keys |
| [Sharing](specs/sharing/spec.md) | Aufnahmen teilen (read/write/full) |
| [Backend & Queue](specs/backend-queue/spec.md) | Service-Registry, Ressourcen-Check, Queue mit Prioritäten |
| [Post-Processing](specs/postprocessing/spec.md) | Prompt-Templates, LLM (Server-Env + BYOK), Delivery (Mail/WebDAV) |
| [Retention & Limits](specs/retention-limits/spec.md) | Anonyme Daten löschen, harte Limits |
| [Model Matrix](specs/model-matrix/spec.md) | Feature-Übersicht der Backends, Model-/Download-Endpunkte |

## External Systems

- **ASR-Backends:** `approach-a` (Parakeet/ONNX, Port 5092), `pk-cpp`
  (parakeet.cpp), `qwen3-asr`, `ark-asr` (remote), `voxtral` (Mistral/LiteLLM)
  — jeweils Docker-Container oder Remote-URL, konfiguriert in der
  Service-Registry.
- **Docker Socket Proxy** (`tecriser/docker-socket-proxy`) — einziger Weg der
  Webapp zum Docker-Socket (nur Container-/Info-Routen, Exec/Create gesperrt).
- **OIDC-Provider** (z. B. authentik) — Login, Gruppen-Claims für Admins.
- **LLM-Endpunkt** — OpenAI-kompatibel (eigener LiteLLM-Proxy oder BYOK-User).
- **SMTP** — E-Mail-Delivery; **WebDAV** — Datei-Delivery (z. B. Nextcloud).

## Architecture Notes

- FastAPI-App `webapp/app`, Router je Ressource; zentrale Identitätsauflösung
  `app/identity.py` (Bearer-API-Key > OIDC-Session > anonymes Cookie).
- SQLite via SQLModel; Spalten-Migrationen durch `_auto_migrate` (ALTER TABLE
  bei fehlenden Spalten) — kein Alembic.
- `app/queue.py` — Thread-basierte Job-Queue mit PriorityQueue
  (anon = 1 < registriert = 0), Concurrency = Summe der Endpunkt-Kapazitäten.
- Secrets: `SESSION_SECRET` (Session + Fernet-Ableitung für Delivery-Passwörter
  und BYOK-Keys); API-Keys als SHA-256-Hash.
- Deutsches README; UI mehrsprachig (de/en/pt-BR).

## Conventions

- **Opt-in-Prinzip:** Kein Post-Processing, keine Toggles laufen automatisch.
- **Anon-Sperre für Paid-Pfade:** LLM/BYOK/paid-Backends → 403 + UI ausgegraut.
- **Env-Kette:** `POLYSCHNACK_*` → `POLYSNACK_*` → `PARAKEET_*` (Deprecation).
- Env-gesetzte Optionen sind in der Admin-GUI sichtbar, aber nicht editierbar.
