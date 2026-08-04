# Entwicklung

## Voraussetzungen

- [uv](https://docs.astral.sh/uv/) (Python Package Manager)
- Node.js 20+
- Docker mit Compose v2

## ASR Backend (approach-a)

```bash
cd approach-a
uv sync
uv run uvicorn polyschnack_service.main:app --reload --port 5092
```

## Web App

```bash
cd webapp/frontend
npm install
npm run dev              # Vite Dev Server auf :5173

# Zweites Terminal:
cd webapp
ASR_URL=http://localhost:5092 uv run uvicorn app.main:app --reload --port 8080
```

## Tests

### Backend (webapp)

```bash
cd webapp && uv run pytest tests/ -q
```

### Frontend

```bash
cd webapp/frontend && npm test        # Vitest
```

!!! note "Frontend-Tests"
    Seit `7459cba` sind die Frontend-Tests Teil des CI-Jobs `test-frontend`.
    Pure Logik liegt testbar in `src/karaoke.ts` + `src/share.ts` +
    `src/benchmark.ts`, Komponenten-Tests in `src/components/*.test.tsx`.

## Doku (MkDocs)

Die Doku ist eine [MkDocs](https://www.mkdocs.org/)-Site (Material-Theme)
unter `docs/`. Lokal bauen:

```bash
cd docs
uvx mkdocs serve     # http://localhost:8000
uvx mkdocs build     # statisches Site-Build
```

GitLab Pages baut die Site automatisch aus dem `pages`-Job (siehe
`.gitlab-ci.yml`).
