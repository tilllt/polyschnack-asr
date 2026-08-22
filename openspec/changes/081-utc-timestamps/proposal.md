# Change 081 — Eindeutige UTC-Zeitstempel (Progress-Heartbeat-Fehlalarm)

## Problem

Die GUI zeigt bei **jedem** Recording in `processing` sofort die Warnung
„⚠ möglicherweise hängend · keine Aktivität seit 120m" — auch für frisch
hochgeladene Dateien mit tickendem Backend-Heartbeat (verifiziert
22.08.2026, Recording 297: `last_heartbeat_at` aktuell, Warnung trotzdem).

**Root Cause (reproduziert, TZ=Europe/Berlin):**
1. SQLite liefert naive UTC-Datetimes; die API serialisiert sie via
   `.isoformat()` **ohne Zeitzonen-Suffix** (`"2026-08-22T11:48:59.589231"`).
2. Das Frontend parst mit `new Date(iso)` — Offset-lose Strings gelten per
   ES-Spec als **Lokalezeit**.
3. In UTC+2 (Berlin) entsteht ein konstanter Skew von exakt 2 h:
   `secondsSince()` liefert `7200 + echteSekunden` → `stalled` (> 45 s)
   ist sofort wahr → „seit 120m" bei frischem Heartbeat.
4. Change 047 (Job-weiter Heartbeat) hat nur die Server-Lücke
   (heartbeat-lose Phasen) behoben — der Client-Skew blieb; deshalb
   „funktioniert immer noch nicht".

Betroffen sind alle Datums-Differenz-Berechnungen der UI (Heartbeat,
Phasen-Dauer, ETA-Fallback, Share-Ablauf) und Zeitanzeigen (6 Router,
16 Serialisierungs-Stellen).

## Ziele

- API liefert ausschließlich **eindeutige UTC-Zeitstempel** (`…Z`).
- Frontend behandelt naive Strings defensiv als UTC.
- Bestandsdaten (naive Strings in SQLite) bleiben korrekt darstellbar.

## Nicht-Ziele

- Kein Umstieg auf `TIMESTAMPTZ`/aware Spalten (Schema-Stabilität).
- Kein Zeitzonen-Picker in der UI.
