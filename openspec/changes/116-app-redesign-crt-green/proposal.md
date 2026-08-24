# Change 116 — App-Redesign (CRT-Grün) + Recording-Card UX v7

## Proposal

### Problem (User-Auftrag, 24.08.)

„Wir haben die recording card jetzt so viel geändert, das wir das gesamte
Design der App auf die neuen Entwürfe anpassen müssen. Bitte mache ein
redesign der ganzen App angelehnt an die Session zur recording card die wir
hatten. Bitte nimm als Highlight Farbe nicht das blau sondern ein dunkelgrün,
wie von einem alten grünen Röhrenmonitor."

Ist-Zustand:
- Die App nutzt das Blau-Design (`accent #5b8cff`, Flächen `#0c0e14`…).
- Die Recording-Card-UX wurde in den Mockups v1–v7 neu entworfen
  (`sketches/menu-redesign-v5.html`): Aktions-Tabs oben (Transkribieren ·
  Sprecher suchen · Neue Wortzeiten), darunter ausklappbare Options-Tabs
  (Vorbereitung · Sprechererkennung · Nachbearbeitung) mit „?"-Hilfen
  (inkl. Modell/Technik), nicht verfügbare Optionen ausgegraut, Start-Button,
  Export = Button mit Formatwahl im Export-Moment, 2 LLM-Wege.
- Die Implementierung der Card steht noch aus; das App-Design ist nicht
  angeglichen.

### Design

**1. Design-Tokens (ganze App):** `tailwind.config.js` + `index.css` auf
grünes CRT-Theme — dunkle grünschwarze Flächen, dunkelgrüner Akzent
(`accent #2ea043`), grüner Fokus-/Scrollbar-/Audio-Akzent, sehr dezenter
Scanline-Hauch im Body-Hintergrund. Semantische Marker bleiben (Karaoke
gelb, Suche grün, Annotation lila). Hartkodierte Blau-Stellen
(`accent-[#5b8cff]`) werden ersetzt.

**2. RecordingCard v7 (Frontend):**
- Aktions-Tabs-Reihe über dem Transkript: `Transkribieren` (nach erstem Lauf
  `Neu transkribieren`) · `Sprecher suchen` · `Neue Wortzeiten`; vor der
  ersten Transkription sind die letzten beiden ausgegraut.
- Rechts in derselben Reihe: `Optionen ▾` klappt das Options-Panel auf/zu.
- Options-Panel (ersetzt die beiden Inline-FeatureToggles-Blöcke):
  - 3 Tabs: `Vorbereitung` (Stille entfernen, Rauschfilter, Klang verbessern,
    Musik entfernen, Sprachmodell), `Sprechererkennung` (Sprecher erkennen,
    Anzahl, Empfindlichkeit, Verfahren), `Nachbearbeitung` (Zeichensetzung,
    ASR-Fehler korrigieren, Vorlage, KI-Server, Senden an).
  - Jede Option mit „?"-Popover: verständliche Erklärung + Modell/Technik-
    Zeile (Silero VAD, noisereduce, ffmpeg-Kette, htdemucs/mel-band-roformer,
    Parakeet, pyannote/foxnose/Energie, Qwen3-Aligner, LiteLLM/DeepSeek).
  - Optionen, die zur gewählten Aktion nicht passen, sind ausgegraut
    („?" bleibt lesbar): `Sprecher suchen` → nur Diar-Optionen aktiv;
    `Neue Wortzeiten` → nur „Musik entfernen" aktiv.
- `Start`-Button unter dem Panel: startet die oben gewählte Aktion mit den
  ausgewählten Optionen (Transkribieren / Re-Align / Re-Diarize über die
  bestehenden Handler).
- Fußleiste: `Export ▾` (bestehendes Download-Menü, Formatwahl im
  Export-Moment inkl. Export-Templates = „Umwandlung"), Kopieren, Teilen,
  Versionen, Löschen; Abbrechen während processing/queued.
- 2 LLM-Wege: „Zeichensetzung" und „ASR-Fehler korrigieren" (exakter Text
  bleibt erhalten) in der Nachbearbeitung; „Umwandlung" (z. B. Meeting →
  Bullet-Point-Protokoll) über die bestehenden Export-Templates im
  Export-Menü.

**3. i18n:** neue Labels (Aktions-Tabs, Start, Optionen, Gruppen, Hilfen) in
de/en/pt-BR.

### Nicht-Ziel

- Keine Backend-Logik-Änderung (keine neuen Endpunkte, keine neuen Spalten).
- Kein Umbau der Transkript-View, Queue, Admin- oder Benchmark-Seite
  (nur Farbtokens wirken dort).
- Kein Fake-Progress; Progress-Anzeigen bleiben wie sie sind.

### Verifikation

- `cd webapp/frontend && npm run build` (tsc + vite) grün.
- `npm test` (vitest) grün.
- Browser-Check gegen `vite preview`: Theme + Aktions-Tabs + Ausgrauen +
  Start + Export-Menü funktionieren.
- CI nach Push prüfen und melden.
