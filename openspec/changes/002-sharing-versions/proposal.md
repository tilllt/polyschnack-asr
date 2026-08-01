# Change Proposal 002 — Sharing, Versionen & Export

**Status:** Implemented (retroaktiv)

## Why
- Transkriptionen im Team teilen (abgestuft), Änderungen nachvollziehbar
  machen, Ergebnisse in gängigen Formaten herausgeben.

## What
- `RecordingShare` (recording_id, shared_with, level read|write|full;
  UniqueConstraint).
- Zentrale `ensure_access`/`get_access_level` (Besitzer > Share > öffentlich);
  alle Routen auf zentrale Zugriffsprüfung umgestellt.
- `TranscriptVersion`: Voll-Snapshot je Änderung; Versions-API mit Diff und
  Restore; Export txt/srt/vtt/json.

## Changes
- Neu: `permissions.py`, `routers/shares.py`, `routers/versions.py`,
  `versions.py`, `export.py`; Tests `test_access_in_routes.py`,
  `test_listing_shares.py`, `test_versions*.py`.
- Geändert: `models.py`, `routers/recordings.py` (include_shares,
  access_level, Deep-Copy-Fix für JSON-Spalten).

## Downgrade
- Shares/Versionen entfernen → Direktzugriff nur Besitzer; Export nur txt.
