# OpenSpec-Spezifikation

Die App ist retroaktiv in [OpenSpec-Format](https://openspec.dev/) spezifiziert:

- `openspec/project.md` — Projekt-Überblick + External Systems
- `openspec/specs/*/spec.md` — Capabilities (Transcription, Transcription
  View, Identity & Access, Sharing, Backend & Queue, Post-Processing,
  Retention & Limits, Model Matrix, Versioning)
- `openspec/changes/<NNN>-<slug>/proposal.md` — **jede** Feature-Änderung
  als Change-Proposal (numeriert; archivierte unter `changes/archive/`)

## Ablauf

1. **Neues Feature → Change-Proposal anlegen** (`openspec/changes/<NNN>-…/`
   mit `proposal.md` + `tasks.md`), im **selben Commit** wie der Code.
2. Spec-Abschnitt (`openspec/specs/`) bei Bedarf aktualisieren.
3. Erledigte Tasks im `tasks.md` abhaken — die Change-Historie bleibt
   nachvollziehbar.

So bleibt die Doku mit dem Code synchron und Architektur-Entscheidungen
sind nachvollziehbar. Der [Code-Guide](code-guide.md) erklärt, welche Dateien
dahinterstehen.
