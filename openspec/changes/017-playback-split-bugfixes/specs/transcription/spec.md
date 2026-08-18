## ADDED Requirements

### Requirement: Playback-Start terminiert immer (kein Endlos-Loading)

- **Ablauf:** Der Player (`WaveformPlayer`) leitet „abspielbar“ NICHT aus
  einem zweiten `fetch` der Audio-URL ab, sondern pollt den echten
  decodierten Buffer (`ws.getDecodedData()`, 300-ms-Intervall). Zusätzlich
  läuft ein 90-s-Timeout: wird `canPlay` nie true (Netz hängt, Datei
  fehlt, Decode schlägt fehl), zeigt der Player einen sichtbaren Fehler
  („Waveform data corrupted“) statt eines Endlos-Spinners.
- **Warum:** Der alte `readyFetch` lud die Audio-URL ein zweites Mal
  (kein Cache-Treffer, weil WaveSurfer parallel lädt) und schluckte
  Fehler im leeren `catch` → `canPlay` blieb false und „Loading audio“
  drehte sich scheinbar ewig, ohne jede Rückmeldung.
- **Sichtbarkeit:** Stille Fehler inakzeptabel — jeder nicht terminierende
  Ladepfad endet in einer sichtbaren Fehlermeldung.

#### Scenario: Audio lädt korrekt

- **Akteure:** User öffnet eine fertige Aufnahme mit Peaks.
- **Eingaben:** Player mountet, Audio-URL wird geladen.
- **Ergebnis:** Play-Button erscheint, sobald der Decode fertig ist;
  „Loading audio“ verschwindet.

#### Scenario: Audio-Datei fehlt / Netz hängt

- **Eingaben:** Player mountet, Fetch kommt nie zurück oder liefert 4xx.
- **Ergebnis:** Nach spätestens 90 s sichtbarer Fehlerhinweis statt
  Endlos-Spinner.

### Requirement: Playback nutzt immer die 64-kbps-Preview (volle WAV nur als Fallback)

- **Ablauf:** Die Audio-URL wird deterministisch gebaut
  (`/api/recordings/{uid}/audio/preview`, `resolveAudioUrl()` in
  RecordingCard). Der Server (`get_audio_preview`) generiert ein fehlendes
  64-kbps-MP3-Sidecar beim ersten Zugriff synchron (ffmpeg, best-effort)
  statt 410. Erst wenn die Preview fehlschlägt, fällt der Player EINMAL auf
  die volle Datei zurück (`previewFailed`-State).
- **Warum:** `audio_preview_url` war nur gesetzt, wenn das Sidecar schon
  existierte; sonst lud der Player die volle WAV (bei langen Aufnahmen
  mehrere hundert MB, teils doppelt).
- **Architektur:** Frontend `RecordingCard.tsx` (`resolveAudioUrl`,
  `previewFailed`), Backend `app/routers/recordings.py`
  (`get_audio_preview`).

#### Scenario: Alte Aufnahme ohne Preview-Sidecar

- **Akteure:** User öffnet eine Aufnahme, die vor dem Preview-Feature
  entstand.
- **Eingaben:** Player mountet.
- **Ergebnis:** Erster Zugriff generiert die MP3 (Request dauert einmalig
  länger), danach lädt jeder Player die kleine Datei; keine volle WAV im
  Playback.

### Requirement: Karaoke-Markierung — genau ein aktives Wort, im aktiven Segment

- **Ablauf:** `activeWordIndex()` liefert -1, sobald `currentTime` nach dem
  Ende des letzten Wortes liegt (kein „Kleben“ des letzten Wortes). Die
  Highlight-Berechnung gilt nur für das aktive Segment (`i === activeIdx`);
  andere Segmente markieren nie. Der Autoscroll findet damit genau ein
  `data-active-word` — im richtigen Segment.
- **Warum:** Segmente vor der Abspielposition markierten fälschlich ihr
  letztes Wort (Doppel-Highlight), und der Autoscroll sprang zum ersten
  Treffer im DOM (= nach oben).
- **Randfall:** Die Tastatur-Navigation (`nextWordTarget`) behandelt
  „nach dem Segment-Ende“ weiterhin als „letztes Wort aktiv“, damit
  Pfeil-rechts ins nächste Segment springt.

#### Scenario: Wort in einem späteren Segment anklicken

- **Akteure:** User, Transkription mit mehreren Segmenten.
- **Eingaben:** Klick auf ein Wort in einem weiter unten liegenden Segment.
- **Ergebnis:** Scrollt nach unten zu diesem Wort; nur dieses eine Wort ist
  markiert.

### Requirement: iOS gibt das Mikrofon nach der Aufnahme vollständig frei

- **Ablauf:** Auf WebKit (Erkennung: `navigator.audioSession` existiert
  nur in Safari) wird das Mikrofon NICHT vorgewärmt (`prewarmMic()` ist
  dort deaktiviert) — der Stream wird erst beim echten Record-Start
  geholt. Nach Stop/Upload/Unmount stoppt die App den Stream UND setzt die
  AudioSession auf `playback` zurück
  (`restoreAudioSessionAfterRecording()`).
- **Warum:** Der Prewarm hielt den Mikrofon-Stream auf iOS dauerhaft offen
  (Indikator in der Statusleiste), und die `play-and-record`-Session wurde
  nie zurückgesetzt.
- **Nicht-Ziele:** Desktop/Android behalten das Prewarm-Verhalten (schneller
  Record-Start).

#### Scenario: Aufnahme auf iOS beenden

- **Akteure:** iOS-Safari-User, Record-Tab.
- **Eingaben:** Aufnahme starten, stoppen.
- **Ergebnis:** Mikrofon-Indikator verschwindet; die nächste Aufnahme
  funktioniert trotzdem (Session wird vor jedem Start erneut gesetzt,
  Change 016).

### Requirement: Split-Markierung bleibt bis zum Symbol-Klick (Desktop) — Symbol mittig und sichtbar

- **Ablauf:** Desktop (Maus): Nach dem Loslassen bleibt die native
  Textauswahl sichtbar (kein `removeAllRanges` im Mouse-Pfad); das
  Split-Symbol erscheint links VERTIKAL MITTIG zur Auswahl
  (`rangeRect.top + height/2`), innerhalb der Zeile geclampt. Erst der
  Klick aufs Symbol (oder `confirmSplit`) entfernt die Markierung. Geht die
  Auswahl woanders hin oder kollabiert sie, verschwindet der Anker mit
  (`selectionchange`-Guard, kein Geister-Icon). Das Symbol ist ein
  26-px-Outline-Kreis mit 18-px-Icon und kräftigen Strichen.
- **Warum:** Die Markierung verschwand sofort (removeAllRanges nach
  mouseup), das Symbol hing am Auswahl-Start, ragte unten aus der Zeile
  und war im Kreis zu klein/zu fein.

#### Scenario: Text mit der Maus markieren (Firefox)

- **Akteure:** Desktop-User, Segment-Text.
- **Eingaben:** Text markieren (Drag), loslassen.
- **Ergebnis:** Markierung bleibt sichtbar, Symbol erscheint links mittig;
  Klick aufs Symbol öffnet den Split-Dialog und räumt die Markierung.

### Requirement: Markieren löst kein Playback aus — Play nur bei einfachem Wort-Klick (ab dem Wort)

- **Ablauf:** Der Wort-`onClick` bricht ab, wenn eine Auswahl aktiv ist
  (native Selection nicht kollabiert ODER Touch-Drag mit
  `startWord !== endWord`). Ein Touch-TAP auf ein Wort ist ein Klick
  (Play ab dem Wort) und setzt KEINEN Split-Anker; erst ein Drag über 2+
  Wörter markiert.
- **Warum:** Nach einer Textauswahl feuert der Browser zusätzlich ein
  `click` auf dem Start-Wort → das Playback startete beim Markieren vom
  Auswahl-Anfang (Symptom: nach Stop stand die Markierung am
  Playback-Start statt an der Stop-Position).
- **Ablauf (Play):** Einfacher Klick auf ein Wort → Play AB diesem Wort
  (Seek auf `w.start` + Play), unverändert.

#### Scenario: Text markieren für Split

- **Akteure:** Desktop- oder Tablet-User.
- **Eingaben:** Text über mehrere Wörter markieren, loslassen.
- **Ergebnis:** Nur Split-Symbol + Markierung; kein Audio-Playback.

#### Scenario: Einfacher Klick auf ein Wort

- **Eingaben:** Klick auf ein einzelnes Wort (keine Auswahl).
- **Ergebnis:** Playback startet ab diesem Wort.
