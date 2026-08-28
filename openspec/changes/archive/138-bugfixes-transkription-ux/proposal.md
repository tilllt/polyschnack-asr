# Change 138: Bugfix-Runde — Speaker-Rename, Punctuation-Option, Transkript-Update nach done

**Status:** Archived (auf specs/ angewendet, 2026-08-28)

## Problem

Drei User-Befunde (2026-08-28) nach dem Deploy von Change 137:

1. **Speaker-Rename schlägt fehl (400).** „Wenn man Diarization macht und '01'
   in einen anderen Namen umbenennen will, erscheint ein Fehler 400
   'SPEAKER_01 not found in Segments'." Root-Cause-Analyse: Das Frontend
   sendet den VOLLEN Namen aus dem Segment (`seg.speaker`); das Backend
   vergleicht EXAKT (`s.get("speaker") == from_speaker` nach `strip()`).
   400 heißt zwingend: kein DB-Segment trägt exakt `from_speaker` — obwohl
   die Anzeige den Namen zeigt. Ursachen: Formatabweichungen in der DB
   (`_normalise_speaker` lässt bereits `SPEAKER_`-präfixierte Labels
   unverändert durch — `SPEAKER_1` bleibt einstellig; Whitespace/Case) oder
   Anzeige ≠ DB-Stand (Yjs/Cache). Der Vergleich ist zu starr für die
   Formate, die Diarization-Server real liefern.

2. **Punctuation-Option ist irreführend.** Die Option ist default aus, aber
   die Transkription kommt trotzdem punktuiert + großgeschrieben zurück.
   Grund: Alle CrispASR-Backends und die Whisper-Familie haben
   `native_punctuation=True` — die Satzzeichen + Groß-/Kleinschreibung
   erzeugen RESIDENTE Server-Modelle (`--punc-model fullstop
   --truecase-model lstm`) bei JEDEM Request, unabhängig vom Toggle. Der
   Toggle steuert nur den LLM-Punct-Fallback für Backends ohne
   native_punctuation (ONNX-Referenz). Die UI zeigt nicht, wann die Option
   wirkt — ein funktionsloser Toggle im Regelfall (Verstoß gegen
   „keine funktionslosen Buttons").

3. **Kein Text nach abgeschlossener Transkription (erst Reload hilft).**
   `useRecordingDetail` ist nur bei `status === "done" || "processing"`
   aktiv; der Listen-Poll nur solange irgendeine Recording `processing` ist.
   Startet der Job mit `queued`, frieren beide ein → nach `done` bleibt die
   Karte leer, bis ein Reload den Cache frisch lädt.

## Ziel

1. **Speaker-Rename tolerant:** `from_speaker` matcht unabhängig vom Format
   (`SPEAKER_01` ↔ `SPEAKER_1` ↔ `01` ↔ `1` ↔ `speaker_1` ↔ Buchstabe),
   solange eindeutig eine Sprecher-Nummer extrahierbar ist. Keine
   stillen Teil-Matches; `renamed`-Count bleibt ehrlich.
2. **Punctuation-Option ehrlich:** Bei Backends mit `native_punctuation`
   zeigt die UI die Option als „nativ aktiv" (Toggle ausgegraut/gesetzt mit
   Erklärung), bei Backends ohne native Punct bleibt sie schaltbar
   (LLM-Punctuation). Kein funktionsloser Toggle.
3. **Transkript nach done ohne Reload:** Der Detail-Poll läuft auch während
   `queued` → der Übergang `queued → processing → done` wird mitgenommen,
   die Karte zeigt den Text, sobald der Job fertig ist.

## Nicht-Ziel

- Kein neuer Recorder-Pfad für abgebrochene Aufnahmen (Szenario unklar —
  gesondert klären, s. design.md).
- Keine Änderung an den ASR-/Diar-Backends selbst (native Punctuation bleibt
  resident — das ist gewollt und die schnellste Qualitätsstufe).
- Kein Text/Wort-Desync-Fix (Segment-Text vs. Aligner-Wörter, Befund
  ec98bfdf…) — braucht die konkrete Recording + Box-Logs; wird separat
  verfolgt.

## Kontext

- `segments.py rename_speaker` (Change 057/126): exakter `==`-Vergleich.
- `diarize.py _normalise_speaker`: normalisiert Roh-Labels, lässt
  `SPEAKER_`-präfixierte Werte unverändert (Z. 50: `return s`).
- `service.py` Z. 2173–2191: `native_punctuation`-Capability steuert den
  LLM-Punct-Fallback; Matrix liefert das Feld bereits
  (`routers/models.py` Z. 210/244).
- `hooks.ts useRecordingDetail` (Z. 67–77): enabled nur done/processing;
  `useRecordings`-Poll nur bei processing.
- Frontend: `OptionsPanel.tsx` (Punctuation-Toggle + Erklärtexte de/en/pt-BR),
  `RecordingCard.tsx` reicht Backend-Capabilities durch (`streamingByBackend`-Muster).

## Changes

- **Backend — `rename_speaker` (segments.py):** Vergleich über eine strikte
  Key-Funktion `_speaker_key(s)` — trimmt, uppercaset, extrahiert die
  Sprecher-Nummer (ein-/zweistellig, mit/ohne `SPEAKER_`-Präfix, Buchstabe
  A–Z → Nummer). Kein Key (leer/unbekannt) → kein Match. Der Ersatzwert ist
  `to_speaker` unverändert. Tests nach Muster `test_speaker_rename.py`:
  Formate-Dreh (`SPEAKER_01`/`SPEAKER_1`/`01`/`1`/`speaker_1`), kein
  Match ohne Nummer, `renamed`-Count, 400 nur wenn NICHTS matcht.
- **Frontend — Punctuation-Option (OptionsPanel/FeatureToggles):** neue Prop
  `nativePunctuation` (für das aktuell gewählte Backend). Wenn true:
  Toggle deaktiviert + gesetzt, Label-Hinweis „aktiv (Server)" + Erklärtext
  „Der ASR-Server setzt Satzzeichen und Groß-/Kleinschreibung automatisch —
  diese Option ist nicht nötig."; wenn false: Toggle normal (LLM-Punctuation).
  `RecordingCard` berechnet das Flag aus der Backend-Matrix (Muster
  `streamingByBackend`). i18n-Keys de/en/pt-BR.
- **Frontend — Detail-Poll (hooks.ts):** `useRecordingDetail` aktiv bei
  `done | processing | queued`; `refetchInterval` bei `processing | queued`
  (2 s). Pure Helfer `shouldPollDetail(status)` + `detailEnabled(status)`
  exportieren und testen. Die Karte zeigt den Text damit nach `done` ohne
  Reload (der letzte 2-s-Poll liefert die Segmente).
- **OpenSpec:** Req-Deltas in `transcription-view` (Speaker-Rename + Req 1
  Anzeige) und `transcription` (Req 3 Opt-in-Toggles).

## Downgrade

- `_speaker_key` entfernen → exakter Vergleich (Stand vor 138).
- `nativePunctuation`-Prop + Hinweis entfernen → Toggle wie vor 138.
- `useRecordingDetail`-enabled/Intervall auf done/processing zurücksetzen.
