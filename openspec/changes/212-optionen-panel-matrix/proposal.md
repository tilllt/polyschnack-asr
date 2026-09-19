# Change 212 — Ein Optionen-Panel für alle drei Quellen, Verfügbarkeit aus einer Matrix

## Status
Entwurf (19.09.2026). Wartet auf Nutzer-Freigabe, dann Umsetzung.

## Ausgangslage / Befund
Die Optionen hängen heute an den Tabs, nicht an der Sache:

- **Datei-Upload** (`UploadZone.tsx:407`) nutzt `ImportToggles`.
- **Aufnahme** nutzt dasselbe `ImportToggles`-Panel.
- **URL-Import** (`UploadZone.tsx:1403`) nutzt ebenfalls `ImportToggles`.
- **Recording-Ansicht** (`RecordingCard.tsx:1632`) nutzt dagegen `OptionsPanel`
  (Change 116, App-Redesign v7) mit Klartext-Beschriftungen.

`ImportToggles.tsx` ist die Oberfläche **vor** dem Redesign: Chips mit
Fachbegriffen (`VAD`, `🎙 Speaker`) und ein Diarisierungs-Popover mit
„Speaker-Anzahl"/„Sensitivity". Folge: dieselbe Option hat drei Darstellungen,
und im URL-Tab stehen Elemente, die dort nichts bewirken.

Nutzer-Befund 19.09.2026: „Im URL tab sind noch uralte ui Elemente drin
Checkbox vad usw."

Nutzer-Entscheid 19.09.2026: „Wir sollten die Optionen einfach von den drei Tabs
trennen und immer das gleiche Panel nehmen, anhand einer Matrix ableiten welche
Optionen eine Funktion haben und welche nicht."

## Entscheidung
1. **Optionen von den Tabs trennen.** Der Zustand (Werte, Flags,
   Nachbearbeitung, Aktion) liegt einmal oberhalb der Tabs und wird von allen
   drei Quellen geteilt. Es gibt genau **ein** Optionen-Panel im Programm.
2. **Verfügbarkeit aus einer Matrix ableiten**, nicht pro Tab von Hand pflegen.
   Die Matrix ist eine deklarative Tabelle (eine Zeile je Option), aus der
   hervorgeht, ob die Option für die gewählte Quelle und das gewählte Backend
   überhaupt eine Wirkung hat.
3. **`ImportToggles` entfällt** samt Fachbegriff-Chips. Damit verschwinden die
   Alt-Elemente im URL-Tab nicht durch Umbenennen, sondern durch Ersetzen der
   Komponente.

## Entwurf

### Eine Zustandsquelle
Der v7-Zustand (`values`, `flags`, `pp`, `action`) wandert aus dem Tab in den
gemeinsamen Bereich. Die Tabs bekommen nur noch: Quelle (Datei/Aufnahme/URL),
Auswahl und den Startknopf. Keine Option rendert mehr ein Tab selbst.

### Eine Matrix
`webapp/frontend/src/optionMatrix.ts` — eine Zeile je Option:

| Feld | Bedeutung |
|---|---|
| `id` | Optionsschlüssel (z. B. `vad`) |
| `sources` | Quellen, in denen die Option wirkt: `upload` / `record` / `url` |
| `requires` | Voraussetzung: `backend` (Fähigkeit nötig), `diarize` (nur mit Sprechererkennung), `streaming` |
| `note` | Klartext-Erklärung (aus den Sprachschlüsseln, de/en/pt) |

Die **Backend**-Fähigkeiten kommen ausschließlich aus der API
(`/api/backends`: `streaming_supported`, `streaming_by_backend`,
`native_punctuation`) — nicht zusätzlich im Frontend hartkodiert. Es gibt also
genau eine Wahrheit je Fähigkeit.

### Darstellungsregeln (eine Regel, nicht je Tab)
- Option wirkt in dieser Quelle und ist vom Backend gedeckt → **bedienbar**.
- Option wirkt, aber das Backend kann sie nicht → **nicht angeboten**; wenn sie
  zum Verständnis wichtig ist, sichtbar mit Klartext-Begründung, aber ohne
  Bedienelement. Niemals ein Knopf ohne Funktion (Nutzer-Regel).
- Option wirkt in dieser Quelle grundsätzlich nicht → **ausgeblendet**.
- Fachbegriffe sind verboten; angezeigt wird der Klartext aus den
  Sprachschlüsseln (VAD = „Stille entfernen", NR = „Rauschfilter").

## Abnahme
- In allen drei Quellen erscheint dasselbe Panel mit denselben Beschriftungen.
- Im URL-Tab existieren keine `ImportToggles`-Reste (Chips „VAD"/„Speaker")
  mehr; die Komponente ist gelöscht.
- Für jede Option belegt ein Test, ob sie bei gegebener Quelle und gegebenem
  Backend angeboten wird oder nicht (Matrix-Unit-Test + je ein UI-Test pro
  Quelle).
- Auf dem Handy bleiben die Optionen erreichbar (kein Überlaufen).

## Entscheidung des Nutzers (19.09.2026)
**Weg A**, verbunden mit einer zusätzlichen Forderung: „aber dann muss der Auftrag
auch direkt starten wenn man ihn 'abschickt' im Moment wird er ja nur als
'wartender' job zur recording karte hinzugefügt."

Daraus folgt:
1. Das gemeinsame Panel erscheint in den Quellen **und** in der
   Recording-Ansicht — in beiden Fällen dieselbe Komponente, dieselbe Matrix,
   dieselben Klartext-Beschriftungen.
2. **Abschicken startet den Auftrag.** Wer in einer Quelle Dateien/URLs absendet,
   startet damit die Transkription; es entsteht kein Eintrag, der nur „wartend"
   auf der Recording-Karte liegt und auf einen zweiten Klick wartet.
3. Zu klären ist, wie sich das zu den vorhandenen `enqueue`-Aufrufen im
   Upload-Pfad verhält (`app/routers/recordings.py`: Zeilen 469, 2098, 2228).
   Zwei Fälle sind denkbar und müssen getrennt behandelt werden:
   - Der Auftrag **ist** eingereiht und wartet nur, weil die Verarbeitung
     bewusst auf **einen gleichzeitigen Job** begrenzt ist → kein Fehler,
     sondern Betriebszustand. Dann ist die Anzeige die Baustelle: sie muss in
     Klartext sagen, dass gewartet wird, warum (ein Job gleichzeitig) und an
     welcher Stelle man steht.
   - Der Auftrag wird beim Upload **nicht** eingereiht und wartet auf einen
     zweiten Klick → Fehler, wird behoben (Abschicken reiht ein).
   Diese Unterscheidung wird vor der Umsetzung am Code belegt, nicht geraten.

## Messbelege zur Parallelität (19.09.2026, gemessen auf der GPU-Kiste)
Frage des Nutzers: „Was passiert wenn wir mehrere Transkription auf dem onnx
Backend parallel starten". Gemessen wurde direkt gegen den Endpunkt
(`POST {ASR_URL}/v1/audio/transcriptions`, dieselbe Datei je Reihe, alle Läufe
HTTP 200, identische Ausgabe), nicht über die Queue.

Kurzes Audio (2,36 MB):
- 1 gleichzeitig: 2,6 s gesamt (0,38 Aufträge/s, Ausgangswert)
- 2 gleichzeitig: 3,7 s → 1,41× Durchsatz
- 3 gleichzeitig: 5,3 s → 1,50×
- 4 gleichzeitig: 6,9 s → 1,51× (sättigt), Einzellaufzeit 2,6 s → 6,9 s

Langes Audio (62,5 MB):
- 1 gleichzeitig: 24,3 s
- 4 gleichzeitig: 97,7 s (einzeln 97,1–97,7 s) → 4 × 24,3 = 97,2 s
  hintereinander. **Kein Durchsatzgewinn**, nur vierfache Wartezeit je Auftrag.

Speicher (Container `polyschnack-ps-pk-onnx-1`, Limit 8 GiB aus `ram_gb: 8`):
- 1 Lauf: 2,80 GiB · 4 Läufe: 4,38 GiB → rund **0,5 GiB pro zusätzlichem Lauf**
- Kein OOM-Ereignis im Kernel-Log, kein Auslagerungs-Kill, keine Fehler

GPU-Zuordnung (`nvidia-smi --query-compute-apps`): 380 MiB `/venv/bin/python`,
13,3 GiB `python` (ComfyUI), 9,9 GiB `/app/llama-server`. **Der ONNX-Dienst
erscheint nicht** — er rechnet auf der CPU. Das erklärt die flache Skalierung
beim langen Audio (reine CPU-Serialisierung).

**Entscheidung: `concurrency: 1` bleibt.** Es gibt für echte Aufnahmen keinen
Durchsatzgewinn, der Dienst rechnet ohnehin auf der CPU, und der Rechner lagert
im Leerlauf bereits 6,9 GB aus. Mehr Durchsatz für Stapel wäre über mehr
CPU-Threads für den Dienst zu holen (oder GPU, sobald dort Platz ist), nicht
über parallele Aufträge.

Hinweis zur Messmethodik: Die geplante Host-Speicher-Auswertung schlug fehl
(`free` ist deutsch beschriftet, das Muster `Mem:` trifft nicht); die
belastbaren Zahlen sind die Container-Messung und die Leerlauf-Ausgabe.

## Offene Fragen an den Nutzer
1. Nicht anwendbare Optionen **ausblenden** oder **sichtbar gesperrt mit
   Begründung**? (Regel gilt dann einheitlich; Vorschlag: ausblenden, außer die
   Option erklärt dem Nutzer etwas Wichtiges.)
2. ~~Backend-Wahl im URL-Import?~~ **Entschieden (19.09.2026): Ja, der
   URL-Import bietet die Backend-Wahl an** — wie die anderen Quellen, aus
   derselben Matrix und mit den Fähigkeiten aus `/api/backends`.
