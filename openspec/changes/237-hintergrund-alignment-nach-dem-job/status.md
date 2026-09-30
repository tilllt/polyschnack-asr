# Change 237 — Hintergrund-Alignment lief nicht mehr (Folge-Auftrag nach dem Job)

**Status:** Fix fertig, Prüfungen laufen
**Datum:** 30.09.2026
**Bezug:** Change 236 (Empfehlung nach dem Rollout), Nutzer-Antwort im Thread:

> ja

Freigabe der Nutzer-Vorgaben aus dem Thread (Börsenspiel-Fragen, hier nur der
Auftrag für diesen Change):

> Soll ich nach dem Rollout direkt Change 237 (Ausrichtungs-Wettlauf) angehen —
> inklusive Prüfung, ob es noch andere Aufnahmen gibt, bei denen der zweite
> Anlauf entfallen ist? Das 404 und die Sprachzeile würde ich in denselben
> Change legen, wenn du einverstanden bist.

## Symptom

Auf der KI-Box wurde im 24-Stunden-Protokoll der Webapp siebenmal gemeldet:

```
bg-align: enqueue fehlgeschlagen rec_id=360: recording 360 already has an active job (queued/processing)
```

Zeitlich genau am Ende jedes erfolgreichen Transkriptionslaufs (rec 336, 357,
359, 360 ×2, 361, 362). Der Nutzer merkte davon nichts — es gab keine
Fehlermeldung in der Oberfläche, sondern nur feinere Wortzeiten, die nicht
mehr kamen.

## Befund (gemessen an der laufenden Anlage, 30.09.2026)

- **Kein `align`-Job seit dem 19.09.2026, 19:11** (`jobs`-Tabelle: 49 erledigte
  align-Jobs, der jüngste `align-341`). In derselben Zeit liefen 30+
  Transkriptionen.
- **103 von 116 Aufnahmen haben überhaupt keinen `align`-Job.** Die 13 mit
  einem solchen Job sind die, bei denen jemand im Transkriptionsfenster
  „Ausrichten" von Hand gedrückt hat (mehrfach dieselbe Aufnahme: 328 ×6,
  341 ×2, 329 ×2).
- Die Spalte `alignment` der Aufnahmen steht trotzdem auf `done` (111) bzw.
  `skipped` (5) — dieser Zustand entsteht im Transkriptionslauf selbst
  (Backend-Wortzeiten bzw. lineare Verteilung, `_build_word_stream`). Das
  präzise Forced-Alignment ist die **zweite**, ausgelagerte Stufe und genau
  die fiel aus.
- Protokoll-Belege der letzten 24 h: 7× die Meldung oben, sonst keine
  `bg-align`-Meldung — es gab also keinen Folge-Auftrag, der es bis in die
  Warteschlange geschafft hätte.

## Ursache

`service.process_recording` reihte den Folge-Auftrag **direkt aus dem
laufenden Job heraus** ein (`queue_manager.enqueue(..., kind="align",
key=f"align-{rec_id}")`). Zu diesem Zeitpunkt steht der eigene Job aber noch in
`QueueManager._jobs` — der Worker meldet ihn erst in seinem `finally` ab
(`self._jobs.pop(key)`), und der `finally` läuft nach der Rückkehr von
`process_recording`.

Der Ein-Job-Wächter (Change 173) lehnt jeden zweiten Job derselben Aufnahme
ab, solange einer aktiv ist:

```python
if kind != "peaks" and any(
    j.rec_id == rec_id and getattr(j, "kind", "transcribe") != "peaks"
    for j in self._jobs.values()
):
    raise QueueError(f"recording {rec_id} already has an active job (queued/processing)")
```

Der Transkriptions-Job war damit sein eigener Blocker. Die Ausnahme wurde
gefangen und nur protokolliert („nie ein Job-Fail") — deshalb blieb der Fehler
unbemerkt. Die Wächter-Ausnahme für `peaks` (Change 231, 21.09.) hat das
Problem nicht verursacht, aber auch nicht sichtbarer gemacht.

## Fix

Der Folge-Auftrag wird jetzt **vorgemerkt und nach dem Abmelden eingereiht**:

- `queue.py`: `Job.deferred` (Liste), `QueueManager.enqueue_after_current(job,
  …)` (merkt den Auftrag am laufenden Job vor; ohne Job-Objekt — Direktaufruf
  außerhalb der Warteschlange — wird sofort eingereiht), `_run_deferred(job)`
  wird vom Worker **nach** `self._jobs.pop(key)` aufgerufen.
- `service.py`: `process_recording` ruft `enqueue_after_current(job, rec_id,
  backend=rec.backend, kind="align", key=f"align-{rec_id}")` statt des
  direkten `enqueue`.

Damit gilt weiterhin: höchstens **ein** Job je Aufnahme. Nur der Zeitpunkt des
Einreihens ändert sich — der Wächter bleibt unverändert scharf, es wird keine
zweite parallele Ausführung möglich (der Worker ist zu diesem Zeitpunkt mit
dem Abmelden beschäftigt, nicht mit einem neuen Job).

## Weitere Punkte im selben Change

- **Weiches 404.** Der SPA-Rückfall lieferte für **jeden** unbekannten Pfad die
  Startseite mit `200 OK` — auch für `/.env`, `/.aws/credentials`, `/wp-login.php`.
  Ein Scanner hat am 30.09. um 01:55 für 41 solcher Pfade „200" protokolliert
  (kein Leck: es kam die 1261-Byte-SPA-Hülle, kein Dateiinhalt — aber ein
  irreführender Treffer für Scans und Fehlersuche). Neu entscheidet
  `_looks_like_file()`: Datei-Endung oder verstecktes Segment → **404**;
  echte Client-Routen (`/r/<uid>`, `/benchmark`, `/recording/123`) → weiterhin
  die SPA.
- **Sprachkennung.** `index.html` stand fest auf `lang="pt-br"`, obwohl Deutsch
  die Hauptsprache ist — jetzt `lang="de"`, und `LocaleProvider` schreibt die
  aktive Sprache zusätzlich ins `<html>` (Bildschirmleser, automatische
  Übersetzung, Silbentrennung). Dabei mitbehoben: die Startsprache war fest
  Englisch (`useState("en")`) und die Wahl im Sprachmenü war nach jedem
  Neuladen weg. Neu: gespeicherte Wahl → Browsersprache (pt → `pt-BR`,
  en → `en`) → Deutsch, und die Wahl wird im Browserspeicher gemerkt
  (`polyschnack.lang`).
- **Vorgemerkt, nicht Teil dieses Change:** die 103 Aufnahmen ohne align-Job
  nachziehen (das wäre Last auf der Box und braucht eine bewusste Entscheidung,
  z. B. nur die letzten N oder nur die ohne Sprecher-Trennung).

## Prüfungen

**Vollständige Läufe (KI-Box, 30.09.2026, vor dem Commit):**

- Backend: `.venv/bin/python -m pytest tests/ -q` → **1436 passed** (20:29 min).
- Frontend: `npx vitest run` → **54 Dateien / 617 Tests passed** (72 s).
- Typen: `npx tsc -p tsconfig.json --noEmit` → ohne Befund.
- CI: `test-frontend`, `test-webapp`, `build-webapp` (Ergebnis wird nachgetragen —
  Projektregel: ohne grünen Bau kein Rollout).

Neue Prüfungen:

- `webapp/tests/test_bg_align_defer_237.py` — Wächter bleibt scharf, Auftrag
  wartet auf das Abmelden, nur einmal eingereiht, Direktaufruf sofort,
  Fehler wird gemeldet statt geworfen, **Ende-zu-Ende** über einen echten
  Worker (Transkription merkt vor → align läuft danach).
- `webapp/tests/test_spa_fallback.py` — erweitert: `/.env`,
  `/.aws/credentials`, `/.git/config`, `/wp-login.php`, `/index.php`, `/foo.txt`
  → 404; `/r/<uid>`, `/benchmark`, `/recording/123`, unbekannte Route → SPA;
  die Regel `_looks_like_file()` direkt.
- `webapp/frontend/src/useLocale.lang.test.tsx` — Startsprache aus
  Browserspeicher/Browsersprache, Rückfall Deutsch, `<html lang>` folgt der
  Sprache und der Sprachwechsel wird gemerkt.

## Rollout

Erst nach grünem CI-Job `build-webapp` (Projektregel: ohne grünen Bau kein
Rollout). Rollout-Werkzeug: `ps_kibox.sh @box_deploy_…` (Image ziehen,
`ps-webapp` neu erstellen), Nachprüfung über ausgeliefertes Bündel und
`https://whisper.cia-spandau.de/`.
