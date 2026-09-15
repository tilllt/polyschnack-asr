# Change 195 — Implementation

## Tasks

- [x] OpenSpec-Change 195 angelegt
- [x] **`registerActivePlayer` eingeführt**: Neue exportierte Funktion, die nur `activePlayer = me` setzt (kein Pause). Ersetzt mount-time `claimExclusivePlayback` (Zeile 923).
- [x] **`claimExclusivePlayback` VOR `ws.play()` im `onContainerClick`**: Direkter claim vor ensureAudioContext/ws.play — unabhängig vom WS7-Event-Timing.
- [x] **Test für `registerActivePlayer`**: Verifiziert, dass Mount nicht pausiert. 12 Tests grün.
- [x] **Build + Tests**: Exclusive-Tests (12) pass; Peaks/Lazyload-Tests (13) pre-existing failures (jsdom).
- [ ] **Push auf main**
- [ ] **Deploy auf KI-Box** (docker pull + compose up -d ps-webapp)