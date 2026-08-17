## ADDED Requirements

### Requirement: Fortschritts-Anzeige mit ETA, Heartbeat und Queue (Change 011)

- **Ablauf:** Der Progress-Block der `RecordingCard` (bisher nur bei
  `status == "processing"`) zeigt jetzt in JEDEM aktiven Zustand
  Phase + Fortschritt + Zeitangabe:
  - **`queued`:** „Warteschlange · Position {n} · ~{eta} · {backend}" —
    Werte aus der Recording-API (`queue_position`, `queue_eta_s`,
    `queue_backend`), kein Spinner.
  - **`processing`:** Spinner/Phase wie bisher, aber die ETA-Zeile wird
    NIE mehr ausgeblendet: `{pct}% · {eta}` auch bei gesetztem
    `phaseDetail` (Alignment zeigt also weiterhin „Gruppe 3/12 — aktiv
    seit 42s" UND die ETA daneben).
- **ETA-Quellen-Hierarchie** (erste verfügbare gewinnt):
  1. `queue_eta_s` (queued, serverseitig),
  2. Rate-Extrapolation aus echten Poll-Sprüngen (bestehende
     `updateEta`/`etaFromRate`),
  3. Phasen-Fallback: „seit {Xs}" aus `phase_started_at` (statt „…").
  „…" erscheint nur noch, wenn weder Rate noch Phasenstart bekannt sind
  (kurzer Anlauf < 2 s).
- **Heartbeat-Puls:** Ist `last_heartbeat_at` jünger als ~8 s und
  `progress_pct` unverändert → Füllbalken bekommt eine Puls-Animation
  (`animate-pulse`) und die Zeile zeigt „aktiv seit {Xs}" (aus
  `phase_started_at` bzw. Heartbeat-Alter). Das macht sichtbar: Job lebt,
  nur kein messbarer Fortschritt (Sync-ASR, Diarization, Alignment).
- **Stall-Warnung:** Ist `last_heartbeat_at` älter als ~45 s bei
  `status == "processing"` → gelbe Zeile „keine Aktivität seit {Xs}"
  (kein Fake-Fehler, kein Rot). Ein hängender Job ist damit erkennbar,
  bevor der Job-Timeout greift.
- **Architektur:** `RecordingCard.tsx` (Progress-Render, ETA-Logik,
  Puls/Warnung), `api.ts` (Recording-Interface: `queue_position`,
  `queue_eta_s`, `queue_backend`, `phase_started_at`, `last_heartbeat_at`).

#### Scenario: Alignment zeigt ETA UND Detail

- **Akteure:** Besitzer mit langer Aufnahme in der Alignment-Phase.
- **Eingaben:** `progress_pct=97`, `progress_note="alignment 3/12 — aktiv
  seit 42s — CLI 45%"`, Rate bekannt.
- **Ergebnis:** Zeile: „⚙ aligning · Gruppe 3/12 — aktiv seit 42s — CLI
  45%" und rechts „97% · ~4m". Vor Change 011 fehlte „~4m".

#### Scenario: Sync-ASR ohne Fortschritt — Puls statt Einfrieren

- **Akteure:** Besitzer; CrispASR-Backend transkribiert (kein
  Job-Progress), `progress_pct` bleibt 21.
- **Eingaben:** `last_heartbeat_at` alle 5 s aktualisiert; Poll alle 3 s.
- **Ergebnis:** Balken pulsiert, Zeile „transcribing · aktiv seit 2m" —
  kein „21% …" als Dauerzustand.

#### Scenario: Hängender Job wird erkannt

- **Akteure:** Besitzer; Worker hängt (Netzwerk-Timeout im Backend-Call).
- **Eingaben:** `last_heartbeat_at` bleibt > 45 s zurück.
- **Ergebnis:** Gelbe Warnung „keine Aktivität seit 48s" auf der Karte —
  der Nutzer weiß, dass etwas nicht stimmt, statt auf ewig „Processing"
  zu sehen.

#### Scenario: Warteschlange sichtbar

- **Akteure:** Registrierter User, dessen Aufnahme an Position 3 wartet.
- **Eingaben:** `status="queued"`, `queue_position=3`,
  `queue_eta_s=270`, `queue_backend="ps-pk-onnx"`.
- **Ergebnis:** Karte zeigt „Warteschlange · Position 3 · ~5m ·
  ps-pk-onnx" — der Nutzer weiß, dass sein Job nicht verloren ist und
  wie lange es dauert.
