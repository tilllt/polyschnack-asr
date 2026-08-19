# Change 031 — Benchmark-Self-Service absichern (Shared-Key-Auth)

## Problem

`GET /api/benchmark/package`, `/package/sha256` und `POST /api/benchmark/submit`
(Change 030) sind **ungeschützt**: Jeder, der die Webapp erreicht, kann das
Benchmark-Paket herunterladen oder (gefütterte) Ergebnisse einspielen.
Referenztexte/Audio sind zwar held-out, aber ein Angreifer könnte das Paket
ziehen und WER-Werte injizieren, die die Rangliste verfälschen.

## Ziel

Nur Clients, die das Shared Secret kennen (Betreiber-Box: Webapp + vast.ai-Runner),
dürfen Paket und Hash abrufen und Ergebnisse submitten. UI-Browser bleiben über
das bestehende OIDC abgesichert — der Shared Key gilt ausschließlich für die
Backend↔Webapp-Kommunikation.

## Entscheidungen

- **Statisches Shared Secret** (`BENCHMARK_API_KEYS`, kommasepariert) in der
  Box-`.env`; Webapp und Runner lesen denselben Wert. Rotation = alt+neu parallel.
- **Übertragung nur per Header** (`Authorization: Bearer <key>`), nie in URL/Body.
- **Timing-sicherer Vergleich** via `hmac.compare_digest`; 401 bei fehlend/falsch.
- **Body-Signatur bei Submit**: `X-Benchmark-Signature: HMAC-SHA256(key, raw body)`
  — verhindert Manipulation/Replay von Ergebnis-Payloads.
- Kein Key in Logs, Fehlermeldungen oder onstart-Skripten; Key nicht ins Image.
- vast-Instanzen erhalten den Key **nur** bei Bedarf über die Miet-`env`
  (Option für `/benchmark/run`-Flow); im aktuellen Runner-Flow (Box) nicht nötig.

## Nicht-Ziele

- Kein mTLS, kein OIDC-Token-Flow für Backends (Overkill für Service-to-Service).
- Kein `POST /benchmark/run` auf Backend-Seite in diesem Change (dokumentiert,
  späterer Change).
