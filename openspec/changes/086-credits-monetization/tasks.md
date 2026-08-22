# Change 086 — Tasks: Credits & Monetarisierung

Reihenfolge: Backend (Modelle → pricing → Ledger → Endpunkte → Tests) →
Frontend (User-Kosten → Admin-Tab) → CI.

## 1. Datenmodell + Migration
- [ ] User: `credits_cents` (int, 0), `tier` (str, "test") — Auto-Migration
      (db._auto_migrate ergänzt Spalten automatisch).
- [ ] Neue Tabelle `CreditLedger` (user_id, delta_cents, reason, ref_id,
      created_at, created_by) — models.py + init_db.
- [ ] Recording: `cost_cents` (Optional[int]) + `reserved_cents`
      (Optional[int]) — Auto-Migration.
- [ ] TDD: Migration läuft auf bestehender DB (Spalten erscheinen),
      Ledger-Tabelle existiert.

## 2. pricing.py (pure, testbar)
- [ ] `calculate_job_cost(phase_times_ms, duration_s, backend, *,
      llm_seconds, align_ms) -> int` (Cent, nie negativ, min. 1 Cent bei
      Aufwand) — Sätze aus backends.yaml (cost_per_minute_eur) +
      Konstanten LLM/ALIGN.
- [ ] `reserve_cents(duration_s, backend, factor_estimate) -> int` —
      Vorschuss aus geschätzter Gesamtzeit (ehrliche Obergrenze:
      p90-Spanne des Learners, Fallback ±50 %).
- [ ] TDD: Kostenrechnung (0-Sätze → 0), Rundung, LLM-Anteil,
      Reserve-Obergrenze.

## 3. Ledger + Buchen (crud/ledger.py)
- [ ] `topup(user_id, amount_cents, reason, created_by)` — Saldo +
      Ledger-Zeile (append-only).
- [ ] `book_job_cost(user_id, rec_id, cost_cents)` — Delta-Buchung
      (Reserve ausgleichen), Saldo aktualisieren; nie unter 0 drücken
      (clamp + Warnung).
- [ ] `ledger_for_user(user_id, limit)` / `ledger_all(limit)`.
- [ ] TDD: Buchungen, Saldo-Konsistenz, Clamp, append-only.

## 4. Job-Fluss (service.py)
- [ ] set_processing/set_queued: Reserve berechnen + `reserved_cents`
      speichern (nie blockierend; Fehler → log + weiter).
- [ ] update_result (status done): `cost_cents` berechnen
      (phase_times_ms + duration + llm_seconds aus punc_truecase-Zeit),
      `book_job_cost` aufrufen. Fehler im Buchen darf den Job-Abschluss
      nicht brechen (try/except + log).
- [ ] TDD: Job mit phase_times → Recording.cost_cents + Ledger-Zeile.

## 5. Endpunkte
- [ ] Admin: GET /credits/users, POST /credits/topup,
      POST /credits/tier, GET /credits/ledger, GET /costing/summary
      (require_admin, Validierung 422).
- [ ] User: GET /api/me/credits (Saldo + letzte 20 Buchungen);
      `cost_cents`/`reserved_cents` in _recording_to_dict.
- [ ] Router-Tests (Admin-Auth, TopUp wirkt, User sieht nur eigene).

## 6. Frontend
- [ ] User: Kontostand in Kopfzeile + Buchungs-Detail; Job-Karte/Detail
      zeigt „Kosten: X,XX €" (+ „reserviert" während processing).
- [ ] Admin-Tab „Monetarisierung": User-Tabelle (Tier-Dropdown, TopUp-
      Button), Kostenübersicht (Balken Einnahmen vs. Instanzkosten,
      Budget-Rest), Journal (letzte 100, filterbar).
- [ ] Frontend-Tests (Komponenten + Build + tsc).

## 7. Abschluss
- [ ] Commit + Push (main), CI-Checks prüfen + melden.
- [ ] Manueller GUI-Test auf der Box (Admin-Tab + User-Sicht).
