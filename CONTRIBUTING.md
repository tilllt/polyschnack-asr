# Contributing

Thank you for considering a contribution. This is a PoC/research project, so the
bar is practical: correctness, clarity, and staying true to the project goals.

---

## Setup

### Prerequisites

- [uv](https://docs.astral.sh/uv/) — the only Python package manager used here.
  Install once: `curl -LsSf https://astral.sh/uv/install.sh | sh`
- Docker with Compose v2 (`docker compose version`)
- (Optional) NVIDIA Container Toolkit for GPU work

### ASR service (`approach-a`)

```bash
cd approach-a
uv sync               # creates .venv and installs all deps
uv run uvicorn polyschnack_service.main:app --reload --port 5092
```

### Web app (`webapp`)

```bash
cd webapp
uv sync
ASR_URL=http://localhost:5092 uv run uvicorn app.main:app --reload --port 8080
```

### Full stack (docker)

```bash
# from repo root
docker compose up -d --build
```

---

## Code Style

| Concern | Convention |
|---------|-----------|
| Python version | 3.10+ (`approach-a`), 3.12+ (`webapp`) |
| Package manager | `uv` only — never `pip install` or `python -m venv` |
| Type annotations | Required on all public functions and module-level variables |
| Web framework | FastAPI + Pydantic v2 |
| ORM / DB models | SQLModel (webapp) |
| DB logic | Lives in `crud.py` — never inline in route handlers |
| Async | `async def` for I/O-bound route handlers; sync for pure CPU work |
| Error handling | Named exceptions, never bare `except:` |
| Style | Pure functions preferred over classes; factories for stateful services |

Run the linter / type-checker before opening a PR:

```bash
# from approach-a or webapp
uv run ruff check .
uv run mypy .
```

---

## Running Tests and Benchmarks

### Generate test fixtures

```bash
cd approach-a
uv run python scripts/gen_test_audio.py
# Creates: tests/audio/short_10s.wav, medium_60s.wav, long_30min.wav (+ .txt refs)
```

### Benchmark (Approach A)

Start the ASR service first (docker or local), then:

```bash
cd approach-a
uv run python benchmark.py --runs 5 --concurrency 5
# Output: results/approach-a.json + results/approach-a.md
```

---

## Pull Requests

### Branch naming

```
feat/short-description
fix/short-description
bench/short-description
docs/short-description
```

### Commit messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
feat(approach-a): add SSE streaming endpoint
fix(webapp): handle empty transcript segments gracefully
bench: update approach-a results after GPU run
docs: document POLYSCHNACK_INFER_WORKERS memory behaviour
```

Types: `feat`, `fix`, `refactor`, `test`, `bench`, `docs`, `chore`, `ci`.

### Checklist before opening a PR

- [ ] `uv run ruff check .` passes (no errors)
- [ ] `uv run mypy .` passes (or new errors are justified in the PR description)
- [ ] Docker build succeeds: `docker compose build`
- [ ] Benchmark re-run if the change affects inference, chunking, or the job queue
- [ ] `RESULTS.md` updated if benchmark numbers changed
- [ ] No secrets, model weights, or large binaries committed
- [ ] PR description includes a rollback plan for any infrastructure change

---

## Project Scope

This is a PoC benchmarking three approaches (A: Python/FastAPI, B: Rust/sherpa-onnx,
C: NeMo baseline). Contributions that implement or improve any of those three paths
are most welcome. Changes that introduce new frameworks or significantly expand scope
should be discussed in an issue first.
