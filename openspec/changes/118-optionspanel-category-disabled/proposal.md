# Change 118 — OptionsPanel: schwächere Ausgrauung + Kategorie-Tabs

## Problem

User-Feedback (2026-08-24, nach Deploy-Freigabe von Change 116):
1. Nicht verfügbare Optionen sind noch zu stark sichtbar
   (aktuell `opacity-40` pro Row).
2. Wenn ALLE Optionen einer Kategorie (Options-Tab: Vorbereitung /
   Sprechererkennung / Nachbearbeitung) bei der gewählten Aktion nicht
   verfügbar sind, soll der ganze Tab ausgegraut und nicht klickbar sein.

## Lösung (OptionsPanel.tsx)

- Row-Ausgrauung `opacity-40` → `opacity-25` (deutlich schwächer).
- Neue Berechnung `tabDis(tabId)`: ein Tab ist disabled, wenn **alle**
  seine Rows disabled sind (rowDis je Aktion + Flags wie vadOk/diarOk/
  oidc/backends/streamingSupported). Mapping der Rows pro Tab als
  `{id, extra}`-Liste.
- Tab-Button: `disabled={tabDis(...)}`, `data-testid="opt-tab-<id>"`,
  Optik `text-muted2 opacity-30 cursor-not-allowed` (kein Hover), Tooltip
  „Für diese Aktion nicht verfügbar."
- Auto-Switch: wird der aktuell aktive Tab durch einen Aktion-Wechsel
  disabled (z. B. „Neue Wortzeiten" bei offenem Nachbearbeitungs-Tab),
  springt das Panel zum ersten verfügbaren Tab (useEffect).

## Tests

- Neu (RecordingCard.test.tsx, Change 118): bei Aktion „Neue Wortzeiten"
  ist `opt-tab-post` disabled, `opt-tab-pre` aktiv; Auto-Switch von post
  auf pre beim Aktion-Wechsel.
- Bestehende Change-116-Tests (data-opt="separate") bleiben gültig.

## Verifikation

- tsc --noEmit, npm test (alle), Build, Push, CI (nur betroffene Jobs —
  Positiv-Test für Change 117)
