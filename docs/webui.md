# Web UI & Features

Die Web UI (`:8088`) ist eine React-SPA. Diese Seite beschreibt **alle**
Features — von Upload bis Kollaboration. Die dahinterliegende Code-Struktur
steht im [Code-Guide](development/code-guide.md).

## Aufnahmen erstellen

| Weg | Beschreibung |
|---|---|
| **Datei-Upload** | Drag & Drop oder Klick — MP3, WAV, OGG, OPUS, M4A, FLAC, WEBM (native Formate unkonvertiert gespeichert) |
| **Mikrofon** | Direkt in der GUI aufnehmen (Desktop + Mobile; Push-to-Record-Gesten auf Touch, Daueraufnahme per Swipe) |
| **URL-Import (🔗)** | YouTube oder direkte Audio-URLs via yt-dlp; bei Bot-Erkennung automatischer Tor-Fallback (Change 043); Duplikat-Erkennung |

Beim Upload wählbar (ImportToggles): VAD, Diarization, Live, Noise-Reduction,
Enhance.

## Transkribieren

- **Feature-Toggles docken an der Transcribe-Zeile** an (nicht global):
  VAD, 🎙 Speaker (mit Tuning-Dropdown: Sprecherzahl, Sensitivität, Methode),
  ⚡ Live, 🔇 NR, Enhance — plus Backend-Auswahl.
- **Backend-Auswahl:** Anon-User sehen nur **laufende** Backends; Admins alle
  (nicht laufende werden automatisch gestartet, nach Ressourcen-Check).
- **Bereich transkribieren:** blauen Griff in der Wellenform ziehen →
  nur dieser Ausschnitt wird transkribiert.
- **Queue & ETA:** Jobs werden pro Backend serialisiert; Position, Warte-ETA
  und Fortschritts-Phasen (Upload → ASR → Align → Diar → Post) zeigt die
  Karte live (2-s-Polling, Change 035/036).
- **Abbrechen:** laufende/queued Jobs können gestoppt werden.
- **Re-Transkribieren:** Klick auf „Re-transcribe" klappt die Optionen auf
  und wird zum ▶-Button (kein Bestätigungsdialog); auch nach `failed`
  möglich.
- **Re-Align / Re-Diarize (Change 057):** einzelne Phasen erneut ausführen,
  ohne die ganze Transkription zu wiederholen.

## Playback & Wellenform

- **WaveSurfer-Player** mit Zoom (1×–50×), Klick auf Segment/Wort springt
  zur Stelle.
- **Karaoke-Wort-Highlight:** aktives Wort wird während der Wiedergabe
  mitverfolgt (0,5×/1×/2× Geschwindigkeit).
- **MP3-Preview:** das Playback lädt eine schlanke 64-kbps-Preview statt der
  vollen WAV (Fallback bei Fehler).
- **Lazy-Loading (Change 052/059):** Player + Transkription laden erst, wenn
  die Karte aufgeklappt ist bzw. in die Nähe scrollt; die Liste selbst
  (Karten-Shell) kommt sofort — im langsamen Netz zeigt die Karte
  **„Transkription wird geladen…"**, bis das Detail nachgeladen ist.
- **Annotation-Marker** auf der Timeline (Change 056); läuft das Playback
  über eine Annotation, erscheint eine Bubble.

## Transkript bearbeiten

| Feature | Bedienung |
|---|---|
| Segment-Text editieren | Doppelklick auf Text, `Ctrl+Enter` speichert |
| Segment **teilen** (Insert Segment) | Text markieren → ✂-Symbol → Sprecher wählen → bestätigen |
| Segment löschen | −-Symbol vor dem Segment |
| Grenzen verschieben | Timecode-Marker ziehen (Wort-genau, nie Wörter teilen) |
| Sprecher umbenennen | ✎-Symbol; neue Sprecher manuell ergänzbar |
| Segmentlänge | freies Zahlenfeld (Sekunden) → Auto-Re-Segmentierung als Vorschau |
| Suchen & Ersetzen | 🔍-Button: Treffer-Sprünge + Ersetzen (einzeln/alle) |
| **Vollbild-Edit (Change 040)** | ⛶-Button: nur diese Transkription, maximale Fläche; Escape/✕ verlässt |
| **Kollaboration (Change 053)** | mehrere User bearbeiten gleichzeitig (Yjs, Cursor-Awareness); wird als Version persistiert |

## Versionen & Diff

Jede Änderung (Transkription, Edit, Post-Processing, Restore) legt eine
**Version** an. Das 🕘-Menü zeigt die History mit Diff (GitHub-Stil) zwischen
zwei Versionen und **Restore** auf einen beliebigen Stand.

## Teilen

| Share-Art | Details |
|---|---|
| **User-Share** | Einladung per User/E-Mail/ID mit Level `read` / `write` / `full` (Backend erzwingt `full` für Bearbeitung) |
| **Anon-Link** | Öffentlicher Read-only-Link (`/r/<uid>`); Generierung kopiert den Link **automatisch in die Zwischenablage** + Toast (Change 058); Ablauf nach Anon-Retention (Default 15 Min.), Hinweis für anonyme Nutzer |

Geteilte Aufnahmen sind in der Liste markiert („🔗 Geteilt"-Badge).

## Annotate — zeitgebundene Kommentare (Change 056)

Text markieren → 💬 öffnet den Kommentar-Dialog. Kommentare hängen an der
**Zeitposition**, erscheinen als Marker auf der Timeline und als Threads
unter der Transkription (Markdown + `@name`-Mentions). Andere User können
antworten. Klick auf eine Annotation springt zur Stelle.

## Export & Download

- **Formate:** TXT, SRT, VTT (mit Sprecher-Labels, wenn Diarization aktiv);
  Formatliste kommt dynamisch vom Server (Export-Templates, Change 015).
- **Backup-ZIP (Change 015):** Audio + Transkript + Word-Timings + Versionen
  + Manifest (nur Owner/Full).
- **Text kopieren** (mit Fehler-Toast bei leer).

## Liste, Sortierung & Tags (Change 054)

- Sortierung: Datum / zuletzt bearbeitet / Name / Dateiname / Länge (asc/desc)
- Freie **Tags** pro Aufnahme (≤ 20, ≤ 40 Zeichen), Filter per Klick
- Suche durchsucht Titel + Transkript (serverseitig)

## Weitere UI-Features

- **i18n:** Deutsch · Englisch · Portugiesisch (umschaltbar, Change 003)
- **PWA/Install-Banner** (Change 037); **Offline-Queue**: Aufnahmen puffern
  bei fehlender Verbindung und werden beim Wiederverbinden hochgeladen
- **API-Keys** (Account-Bereich) für programmatischen Zugriff
- **Stats-Leiste** (Header): Aufnahmen, verarbeitete Minuten, GPU/CPU-Badge
- **Konsistente Popover/Modals (Change 058):** alle Dialoge schließen bei
  Klick außerhalb + Escape; Split-Popover erscheint neben dem Symbol;
  Dialoge sind viewport-begrenzt (max-h + Scroll) — nichts „wächst" über den
  Bildschirm

## Admin-Bereich (`🛠 Admin`, nur Admins)

Siehe [Admin-Bereich](configuration/admin.md) — Backends on demand starten/
stoppen, Ressourcen-Reports, Default-Backend, Modell-Matrix, VACUUM.
