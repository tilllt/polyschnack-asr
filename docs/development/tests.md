# Tests

## Übersicht

| Bereich | Befehl | CI-Job |
|---------|--------|--------|
| Backend (webapp) | `cd webapp && uv run pytest tests/ -q` | `test-webapp` |
| Frontend | `cd webapp/frontend && npm test` | `test-frontend` |
| Core (approach-a) | `cd approach-a && uv run pytest` | `test-core` |
| Compose-Validierung | — | `compose-validate` |

## Konventionen

- **TDD:** Neue Features beginnen mit einem roten Test, dann Implementierung.
- **Ein Commit pro Task** — Tests und Implementierung zusammen.
- **Frontend-Tests:** pure Logik in `src/*.test.ts`, Komponenten mit
  `@testing-library/react` in `src/components/*.test.tsx`.
- **jsdom-Version:** `^25.0.1` gepinnt — jsdom ≥ 26 braucht Node ≥ 20.19,
  der CI baut mit `node:20-slim` (webidl-Fehler bei neueren Versionen).

## Benchmark-Tests

- `polyschnack-benchmark`: `benchmark/tests/` (cv_extract, taxonomy, …)
- Webapp: `webapp/tests/test_benchmark_service.py` (Service/Manifeste),
  `webapp/tests/test_benchmark_router.py` (API + 2-Achsen-Matrix),
  `webapp/benchmark/e2e_test.py` (End-to-End gegen ein Seeded-Volume)
