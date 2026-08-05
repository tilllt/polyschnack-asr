# Contributing

Danke fürs Mitmachen! PolySchnack ist ein aktives Multi-Backend-Projekt —
der Standard ist pragmatisch: korrekt, getestet, dokumentiert.

---

## Setup

### Voraussetzungen

- [uv](https://docs.astral.sh/uv/) — der einzige Python-Paketmanager.
  Install: `curl -LsSf https://astral.sh/uv/install.sh | sh`
- Node.js 20+ (Frontend)
- Docker mit Compose v2 (`docker compose version`)
- (Optional) NVIDIA Container Toolkit für GPU-Arbeit

### ASR-Backend (`approach-a`)

```bash
cd approach-a
uv sync                 # erzeugt .venv und installiert Dependencies
uv run uvicorn polyschnack_service.main:app --reload --port 5092
```

### Webapp (`webapp`)

```bash
# Frontend (Vite Dev Server auf :5173)
cd webapp/frontend
npm install
npm run dev

# Backend (zweites Terminal)
cd webapp
uv sync
PS_PK_ONNX_URL=http://localhost:5092 uv run uvicorn app.main:app --reload --port 8088
```

### Full Stack (Docker)

```bash
# Kern-Stack (CPU; GPU via Overlay):
docker compose up -d
docker compose -f compose.yml -f compose.gpu.yml up -d   # GPU

# Mit optionalen Backends (Profile, --no-start = Admin-GUI startet on demand):
docker compose -f compose.yml -f compose.backends.yml \
  --profile crispr-pk-cpp --profile crispr-qwen3 --profile crispr-ark --profile crispr-moonshine-de --profile crispr-canary up -d --no-start
```

---

## Tests

**Backend (webapp):** pytest. Eine Testdatei einzeln, um den Output klein zu
halten (die Gesamtsuite dauert 6–10 min):

```bash
cd webapp
.venv/bin/python -m pytest tests/test_service_registry.py -q -p no:cacheprovider
```

Die komplette Suite läuft als Per-Datei-Loop mit Log nach
`/tmp/ps_full_suite.log` (Ergebnis: `grep "GESAMT" /tmp/ps_full_suite.log`):

```bash
bash webapp/run_full_suite.sh
```

**Frontend (webapp/frontend):** Vitest — pure Logik liegt in `src/karaoke.ts`
und `src/share.ts`:

```bash
cd webapp/frontend
npm test
```

**Backend-Images:** Die CI baut alle 9 Jobs (`test-core`, `test-webapp`,
`test-frontend`, `compose-validate`, `build-asr`, `build-webapp`, `build-cpp`,
`build-diar`, `build-ark`). Lokal ist kein Docker-Daemon nötig —
`compose-validate` prüft die YAML-Dateien per PyYAML.

---

## Code Style

| Belang | Konvention |
|--------|-----------|
| Python-Version | 3.10+ (`approach-a`), 3.12+ (`webapp`) |
| Paketmanager | `uv` only — nie `pip install` oder `python -m venv` |
| Typ-Annotationen | Pflicht auf allen öffentlichen Funktionen und Modul-Variablen |
| Web-Framework | FastAPI + Pydantic v2 |
| ORM / DB-Modelle | SQLModel (webapp) |
| DB-Logik | Liegt in `crud.py` — nie inline in Route-Handlern |
| Async | `async def` für I/O-gebundene Route-Handler; sync für reine CPU-Arbeit |
| Fehlerbehandlung | Benannte Exceptions, nie nacktes `except:` |
| Stil | Pure Functions bevorzugt; Factories für zustandsbehaftete Services |

Vor einem MR:

```bash
# aus approach-a oder webapp
uv run ruff check .
uv run mypy .
```

---

## Backend-Adapter hinzufügen (Checkliste)

Ein neues ASR-Backend ist erst nutzbar, wenn ALLE diese Stellen bedient sind
(Registry allein reicht nicht — `get_client()` fällt sonst still auf
`ps-pk-onnx` zurück):

1. **`compose.backends.yml`** — Service + Profil + Port + Healthcheck
   (hybrides CrispASR-Image-Muster, siehe `ark-asr-cpp/Dockerfile`).
2. **`webapp/app/backends.yaml`** — neuer YAML-Block mit allen Metadaten
   (name/backend, compose_profile, container_name, requires, capabilities)
   + `adapter` (Modul:Klassenname) + optional `url`/`url_env`/`adapter_kwargs`.
   Der `container_name` muss zu compose.yml passen; das `compose_profile`
   zum Docker-Profil. Selbst-Check: `python -m app.service_registry`.
   **Kein Code-Change an der Verdrahtung nötig** — `service_registry.py`
   lädt die YAML, `get_client()` instanziiert per importlib.
3. **Adapter-Klasse** — in `webapp/app/asr_client/adapters/` (erbt von
   `AsrClient`); URL aus eigener Env-Var (`<NAME>_URL`) oder `url`-Feld —
   nie `settings.ASR_URL` (das ist der ONNX-Container!).
4. **Tests** — `tests/test_get_client.py` (Factory-Zweig) +
   Registry-Tests; HTTP-Adapter-Tests mit `httpx.MockTransport`.
5. **CI** — Build-Job in `.gitlab-ci.yml` (Muster `build-cpp`).
6. **Doku** — README: Backend-Tabelle, Feature-Matrix, Profil-/Env-Tabellen,
   Modell-Download-Kommando, Lizenz-Hinweis.

---

## Pull Requests

### Branch-Namen

```
feat/short-description
fix/short-description
bench/short-description
docs/short-description
```

### Commit-Messages

[Conventional Commits](https://www.conventionalcommits.org/):

```
feat(webapp): add diarize_method selection
fix(webapp): handle empty transcript segments gracefully
bench: update benchmark results after GPU run
docs: document DIAR_URL and DIARIZE_METHOD
```

Typen: `feat`, `fix`, `refactor`, `test`, `bench`, `docs`, `chore`, `ci`.

### Checkliste vor einem MR

- [ ] `uv run ruff check .` läuft ohne Fehler
- [ ] `uv run mypy .` läuft (oder neue Fehler sind im MR begründet)
- [ ] Betroffene Backend-Testdateien grün (einzeln, s. o.)
- [ ] Frontend: `npm test` grün, falls `src/*.ts` geändert
- [ ] CI grün (alle 9 Jobs) nach Push
- [ ] README/Compose-Doku für das Feature aktualisiert (kein Feature ohne Doku!)
- [ ] Keine Secrets, Modellgewichte oder große Binaries committet
- [ ] MR-Beschreibung enthält Rollback-Plan bei Infrastruktur-Änderungen

---

## Projekt-Scope

PolySchnack ist ein **Multi-Backend-Transkriptionstool** (kein TTS-Projekt):
Fokus auf Transkriptions-Qualität, Word-Timestamps, Diarization, Editing,
Long-Audio und Benchmarking. Qualitäts-Verbesserungen (WER, Diarization-DER)
sind willkommen; neue große Frameworks oder Scope-Erweiterungen vorher im
Issue/Plan diskutieren.

Benchmarking läuft im separaten Repo `polyschnack-benchmark`
(deutsches WER-Korpus mit CommonVoice-DE, `benchmark/run.py` + `report.py`).
