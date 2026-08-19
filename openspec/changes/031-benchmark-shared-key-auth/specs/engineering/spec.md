# Spec — Shared-Key-Auth für Benchmark-Self-Service (Change 031)

## REQ-BEN-044 — Key-Konfiguration

- Webapp liest `BENCHMARK_API_KEYS` (env, kommasepariert, optional; leer =
  Endpunkte deaktiviert mit 503 „benchmark api not configured").
- Runner (`benchmark_selfservice.py`, `run_container.py`) liest
  `BENCHMARK_API_KEY` (env) — muss zum Webapp-Key passen.
- Keys sind zufällig erzeugt (`openssl rand -hex 32`), liegen in der Box-`.env`
  (Compose: `BENCHMARK_API_KEYS: ${BENCHMARK_API_KEYS}`), nie in Git/Image/Logs.

## REQ-BEN-045 — Authentifizierung der Endpunkte

- `GET /api/benchmark/package` und `GET /api/benchmark/package/sha256`:
  erfordern `Authorization: Bearer <key>`; 401 bei fehlend/falsch.
- `POST /api/benchmark/submit`: erfordert zusätzlich
  `X-Benchmark-Signature: hex(hmac_sha256(<authentifizierter Key>, raw body))`;
  401 bei fehlender/falscher Signatur. Signatur wird über den **rohen**
  Request-Body geprüft (vor Pydantic-Parsing reicht der gecachte Body).
- Vergleich aller Secrets ausschließlich mit `hmac.compare_digest`.
- Fehlerantworten enthalten keine Key-Anteile; Requests werden nicht mit
  Key-Headern geloggt.

## REQ-BEN-046 — Runner-Verhalten

- `benchmark_selfservice.py` sendet den Bearer-Header bei sha256/package/submit;
  bei Submit wird der Body vor dem Senden mit dem Key signiert.
- `run_container.py` reicht `BENCHMARK_API_KEY` an den Runner durch
  (env `BENCH_SUBMIT_KEY`-Äquivalent bleibt kompatibel: Key gewinnt, wenn beide
  gesetzt sind).
- Ohne gesetzten Key: klare Fehlermeldung (Exit-Code ≠ 0) statt stiller 401.

## REQ-BEN-047 — Tests

- 401 ohne Header, 401 mit falschem Key, 200 mit korrektem Key (package/sha256).
- Submit: 401 ohne/falsche Signatur; 200 mit korrekter Signatur; manipulierte
  Payload → Signatur-Mismatch.
- Bestehende 030-Tests bleiben grün (Header werden mitgesendet).
