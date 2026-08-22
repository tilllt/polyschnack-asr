# Change 086 — Design: Credits & Monetarisierung

## Datenmodell

### User (bestehende Tabelle, neue Spalten)
- `credits_cents: int = 0` — Kontostand in Cent (virtuell, Integer statt
  Float → keine Rundungsfehler).
- `tier: str = "test"` — `free` | `paid` | `test` (test = virtuelles
  Startguthaben für Erprobung).

### CreditLedger (neue Tabelle)
Eine Zeile je Buchung — vollständiges Journal, nichts wird gelöscht.

| Feld | Typ | Bedeutung |
|---|---|---|
| id | int PK | |
| user_id | int FK user | |
| delta_cents | int | +TopUp / −Job-Kosten / +Gutschrift |
| reason | str | topup \| job_cost \| refund \| signup_bonus |
| ref_id | int? | Recording/Job-ID (bei job_cost) |
| created_at | datetime | |
| created_by | int? | Admin-User-ID (bei topup/refund) |

### Recording (bestehende Tabelle, neue Spalten)
- `cost_cents: Optional[int]` — Endabrechnung des Jobs (nach Abschluss),
  in `_recording_to_dict` als `cost_cents` ausgeliefert (User sichtbar).

## Kostenschicht (`pricing.py`)

Zwei getrennte Schichten (Design 085: „Learner lernt ZEIT, Costing liefert
PREISE"):

- **Zeit** kommt aus `phase_times_ms` (Change 085, Messpunkte je Job).
- **Sätze** (`app/backends.yaml`, je Backend `cost_per_minute_eur`,
  Default 0.0) + `pricing.py`-Konstanten:
  - `LLM_COST_PER_MINUTE_EUR` (LLM-Post-Processing, konfigurierbar)
  - `ALIGN_COST_PER_MINUTE_EUR` (Aligner läuft lokal → Strom/Abschreibung)

```python
def calculate_job_cost(phase_times_ms, duration_s, backend,
                       llm_seconds=0.0) -> int:  # Cent
    # asr/diar/enhance/vad: phase_ms/60000 × cost_per_minute_eur(backend)
    # punc_truecase/llm:    llm_seconds/60 × LLM_COST_PER_MINUTE_EUR
    # align (Hintergrund):  align_ms/60000 × ALIGN_COST_PER_MINUTE_EUR
    # Rückgabe: max(0, ceil(cent)) — nie negativ, nie gerundet auf 0
    #   bei messbarem Aufwand (min. 1 Cent, wenn > 0 Aufwand)
```

Kostensätze kommen aus backends.yaml (Single Source of Truth, Change 085)
und werden NUR vom Admin über `/api/admin/costing/...` gepflegt — nie im UI
für User.

### Reserve-System (Delta-Buchung)
1. **Job-Start** (set_processing/set_queued): erwartete Kosten reservieren
   (`reserve = ceil(duration_s × geschätzter Faktor × Satz)`), als
   `reserved_cents` an der Recording, NICHT buchen (User-Saldo unangetastet,
   Sicht: „reserviert").
2. **Job-Ende** (update_result, status done): Ist-Kosten `cost_cents`
   berechnen → Delta = Ist − Reserve → Ledger-Buchung
   `job_cost` (delta_cents = −Ist) + Saldo aktualisieren.
3. Negativ-Konto unmöglich, solange TopUp ≥ Reserve-Vorschuss — bei
   `tier=test` reicht das Startguthaben (10 €) für viele Jobs.

## Endpunkte

### Admin (`/api/admin`, require_admin — bestehender Router)
- `GET /credits/users` — Liste: user_id, name, tier, credits_cents,
  verbraucht (Σ negativer Buchungen), letzte Aktivität.
- `POST /credits/topup` `{user_id, amount_cents, reason?}` — Guthaben
  erhöhen; Ledger-Buchung `topup` (created_by = Admin).
- `POST /credits/tier` `{user_id, tier}` — free/paid/test setzen.
- `GET /credits/ledger?user_id=&limit=` — Journal (Admin-Einsicht).
- `GET /costing/summary` — Einnahmen (Σ topup) vs. Instanzkosten (Σ
  job_cost) + Budget-Cap-Fortschritt (085-Baustein, hier nur Anzeige).

### User
- `GET /api/me/credits` — eigener Kontostand + letzte 20 Buchungen.
- Job-Kosten: `cost_cents` im Recording-Dict (jeder Job zeigt seine
  Kosten; noch keine Abrechnung → null).

## GUI

### User (Webapp)
- Job-Karte/Detail: „Kosten: X,XX €" (cost_cents), bei laufendem Job
  „reserviert"-Hinweis; Kontostand in der Kopfzeile (Klick → Detail
  mit Buchungsliste).

### Admin (neuer Tab „Monetarisierung")
- User-Tabelle: Name, Tier (Dropdown), Guthaben, Verbrauch, TopUp-Button
  (+ Betrag) → gleiche UX wie bestehende Admin-Tabs (Tabelle + Aktionen,
  keine Tabellen-Breite > 1200 px).
- Kostenübersicht: Einnahmen vs. Instanzkosten (Balken statt Tabelle —
  User-Vorgabe „Stats grafisch"), Budget-Rest.
- Journal-Ansicht (letzte 100 Buchungen, filterbar nach User).

## Sicherheit

- Keine Secrets im UI; nur Admin-Endpunkte schreiben Guthaben/Tier.
- `amount_cents` Validierung: 1..1.000.000 (422 bei Unsinn).
- Ledger ist append-only (kein Löschen; Datenschutz: User-Löschung
  anonymisiert die Ledger-Zeilen, behält aber die Summen — Historie).
