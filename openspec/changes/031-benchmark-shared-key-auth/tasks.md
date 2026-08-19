# Tasks — Change 031

1. [ ] config.py: `BENCHMARK_API_KEYS` (kommasepariert) ergänzen
2. [ ] routers/benchmark.py: Guard (401, timing-safe) für package/sha256/submit
3. [ ] routers/benchmark.py: Signatur-Verifikation bei Submit (roher Body)
4. [ ] benchmark_selfservice.py: Bearer-Header + Submit-Signatur
5. [ ] run_container.py: `BENCHMARK_API_KEY` durchreichen
6. [ ] Tests: 401/200 package+sha256, Signatur ok/falsch, bestehende Tests grün
7. [ ] Commit + Push + CI grün
8. [ ] Box-Deploy-Hinweis (`.env`: `BENCHMARK_API_KEYS=<key>`, compose-Env)
