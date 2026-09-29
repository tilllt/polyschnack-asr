# Change 235 — Naiver Zeitstempel in `_purge_expired` legt die CI lahm

**Status:** Fix fertig, Invariante drin, CI-Nachweis läuft
**Datum:** 29.09.2026
**Bezug:** blockiert den Rollout von Change 234 (OpenAI-Proxy)

## Symptom

Pipeline `5699` (Commit `38485f9`, Change 234) scheiterte in `test-webapp`, und
zwar **nicht** an den geänderten Dateien: Jeder Test starb bereits beim Aufbau
des TestClient.

```
app/main.py:81: in lifespan
    init_db()
app/db.py:435: in init_db
    _purge_expired()
app/db.py:71: in _purge_expired
sqlalchemy.exc.StatementError: (builtins.ValueError)
  Datetime values must have timezone information. Use datetime.now(timezone.utc),
  or annotate the field with NaiveDatetime for naive storage.
```

## Ursache (gemessen, nicht geschlossen)

- `db.py:74` verglich `_Recording.created_at < datetime.utcnow() - …` — **naiv**.
  Alle Spalten werden dagegen tz-aware geschrieben
  (`Field(default_factory=lambda: dt.datetime.now(dt.timezone.utc))`).
- SQLModel/SQLAlchemy tolerierten den naiven Bind bis **0.0.39**; ab **0.0.40**
  wird er serverseitig abgelehnt. Die CI installiert ihre Pakete **ohne Pin**
  (`pip install … "sqlmodel>=0.0.16" "pydantic>=2" …`) und zog deshalb 0.0.47.
  Lokal lag noch 0.0.39 in der venv → lokal 1426 grün, CI rot.

Nachweis: Reproduktions-Umgebung nach CI-Vorbild gebaut (Python 3.13, uv):

```
uv venv --python 3.13 /opt/data/cache/scratch/psenv
VIRTUAL_ENV=… uv pip install pytest httpx fastapi "sqlmodel>=0.0.16" "pydantic>=2" \
   python-multipart numpy cryptography authlib itsdangerous pyyaml pycrdt pycrdt-websocket jinja2
# → sqlmodel 0.0.47, sqlalchemy 2.0.54, pydantic 2.13.5
python -m pytest tests/test_admin_vacuum.py -q    # → ERROR at setup, dieselbe Meldung
```
Die Deprecation-Warnung nannte die Zeile zusätzlich selbst:
`app/db.py:74: DeprecationWarning: datetime.datetime.utcnow() is deprecated`.

## Fix

1. `app/db.py`: `datetime.now(timezone.utc) - timedelta(minutes=ret)` statt
   `datetime.utcnow() …`; `timezone` importiert. Damit ist der Vergleich
   tz-aware wie die gespeicherten Werte.
2. `tests/test_eta.py`: der Test „naiv wird als UTC gelesen" baut den naiven
   Wert jetzt aus `datetime.now(timezone.utc).replace(tzinfo=None)` — die
   Absicht bleibt, die Deprecation ist weg.
3. **Invariante** `tests/test_datetime_tz_invariant.py`: das Backend darf keine
   naiven Zeitstempel konstruieren (`utcnow(`, `datetime.now()` ohne tz,
   `date.today()`). Kommentare ausgenommen, Treffer werden mit Datei:Zeile
   gemeldet. Rote Gegenprobe: die alte Zeile künstlich zurückgesetzt → Test rot
   mit `app/db.py:77: datetime.utcnow() …`.
4. **Zweite Fundstelle (derselbe Lauf, dieselbe Ursache):**
   `tests/test_share_link.py` schrieb **bewusst naive** Zeitstempel
   („SQLite speichert naive datetimes", „naive (SQLite-Stil)") in `shared_at`
   und in zwei `TranscriptVersion.created_at`. Unter 0.0.47 kippt schon der
   INSERT: 7 Tests der Datei starben mit „ERROR at setup". Jetzt tz-aware
   (`tzinfo=dt.timezone.utc`), Kommentare korrigiert — die Annahme „SQLite
   speichert naiv" war der eigentliche Irrtum.
5. Die Invariante prüft deshalb **auch `tests/`** (Datetime-Literale mit Datum,
   aber ohne `tzinfo`) — Fixtures schreiben echte Zeilen und fallen sonst erst
   beim INSERT um. Einzige Ausnahme mit Marker `# tz-invariant-ok`:
   `tests/test_timeutil.py`, wo der naive Wert die *Eingabe* für `iso_utc` ist.
   Die Invariantendatei selbst ist von der Prüfung ausgenommen (sie enthält die
   Muster als Strings).

## Prüfstand

- Betroffene Dateien unter **sqlmodel 0.0.47 / Python 3.13**: `test_admin_vacuum`,
  `test_eta`, `test_datetime_tz_invariant`, `test_timeutil`, `test_share_link`
  → **42 grün** (vorher ERROR beim Setup bzw. 7 Fehler).
- Rote Gegenprobe der Invariante: Marker `tz-invariant-ok` entfernt →
  `test_keine_naiven_zeitstempel_in_den_tests` **rot** mit
  `tests/test_timeutil.py:8: Datetime-Literal ohne tzinfo`; Marker zurück →
  grün.
- Volle Suite in derselben Umgebung: **1402 passed, 19 skipped, 7 errors** (vor
  dem Fix) → zweiter Lauf nach dem Fix (Ergebnis unten eingetragen).
- Lokale venv (sqlmodel 0.0.39) bleibt kompatibel: der Fix ist für beide
  Versionen gültig, der Test prüft nur die Quelle.

## Nachtrag nach dem Fix-Lauf

- Volle Suite (CI-gleiche Umgebung, Python 3.13/sqlmodel 0.0.47):
  **1410 passed, 19 skipped, 0 errors, Exit 0 in 1033,93 s (17:13)** — vorher
  `1402 passed, 19 skipped, 7 errors in 959 s`. Die 7 Fehler der
  `test_share_link`-Fixtures sind damit weg, die 19 Skips sind
  Umgebungs-Skips (u. a. `onnxruntime` fehlt in der Repro-venv → Silero-VAD
  deaktiviert).

## Offener Punkt (nicht Teil dieses Changes)

Die CI installiert die Abhängigkeiten ohne Pin. Solange das so ist, entscheidet
der Tag des Pipeline-Starts, welche Bibliotheksversionen geprüft werden — genau
daraus entstand dieser rote Lauf. Saubere Lösung wäre die Installation aus
`webapp/uv.lock` (im Repo vorhanden) statt der handgepflegten Liste; das ist ein
eigener Change, weil er die Bauumgebung der gesamten CI umstellt.

## Learnings

- Ein grüner lokaler Lauf beweist bei ungepinnten CI-Abhängigkeiten **nichts**
  über die CI. Bei einem roten Lauf zuerst die Bibliotheksversionen beider
  Umgebungen vergleichen, dann den Code.
- Naive Zeitstempel sind kein Stilproblem: sie brechen ab einer SQLModel-Version
  hart, und zwar im Startup-Pfad (`init_db`) — dann ist die ganze Suite rot,
  ohne dass eine einzige Zusicherung des geänderten Themas verletzt wäre.
- **Zeitstempel in Fixtures gehören zur Produktionsfläche.** `test_share_link.py`
  schrieb naive Werte mit dem Kommentar „SQLite speichert naive datetimes" —
  genau diese Annahme hat SQLModel selbst getroffen, und zwar anders. Ein
  Kommentar, der das Verhalten einer Bibliothek erklärt, ist ein Warnsignal:
  nachmessen statt glauben. Aufgefallen sind die 7 Fehler nur, weil der volle
  Lauf **in der CI-gleichen Umgebung** wiederholt wurde — einzelne Dateien waren
  vorher schon grün.
- **Eine Invariante, die nur `app/` prüft, deckt die halbe Wahrheit.** Die
  Fixtures schreiben echte Zeilen; deshalb prüft der Test jetzt auch `tests/`,
  mit genau einer dokumentierten Ausnahme (`tz-invariant-ok`) dort, wo ein
  naiver Wert die *Eingabe* eines Tests ist.

## Ausgerollt (29.09.2026)

- Pipeline 5701 für `8b8ca096`: **success** (alle Jobs grün, inkl. `mirror-ghcr`).
- Rollout KI-Box (.140) über `ps_kibox.sh @skript`: **REV_VOR=b3c09f75 → REV_NACH=8b8ca096**,
  Container `polyschnack-ps-webapp-1` neu erstellt, `Up`.
- Gegenprobe lebendes System: `/health` HTTP 200 (`asr_url: http://ps-pk-onnx:5092`);
  `POST /v1/audio/transcriptions` **ohne** `language` → 200,
  **mit** `language=de` → 200 (vorher 502 — der Pfad, den Change 234 repariert).
- Beleg, dass der Wert wirklich beim Adapter ankommt: Live-Log zeigt
  `openai_proxy.py:184 return client.transcribe(raw, filename, mime, language=language)`
  ohne Fehler; das wäre vor dem Fix ein `TypeError` gewesen.
- Offen: Wirkung des Werts beim *Modell* nicht live messbar — Parakeet ignoriert den
  Sprachhinweis (de/en/zz liefern identischen Text), Qwen3-Container läuft nicht
  (`crispr-qwen3` nicht erreichbar, sauberer 502 mit Klartextmeldung).
