# Retention & Limits

## Purpose

Anonyme Daten automatisch löschen (DSGVO-freundlicher Shared Space) und
anonyme Nutzung hart begrenzen.

## Requirements

### Req 1: Sliding-Retention (anonym)

- **Ablauf:** Jede anon-Aktivität verlängert die Lebensdauer
  (`last_seen_at`, Update max. alle 60 s). Nach
  `POLYSCHNACK_ANON_RETENTION_MINUTES` (Default **15**) Inaktivität löscht der
  Sweep den anon-User **komplett**: Recordings inkl. Audiodateien, Shares,
  Versionen.
- **Architektur:** `anon_session.py` (last_seen), `retention.py`
  (Sweep-Thread alle 5 min, gestartet im Startup `main.py`).
- **Wichtig (SQLite):** DB-Werte sind naive datetimes → vor aware-Vergleich
  `tzinfo` ergänzen (`replace(tzinfo=timezone.utc)`).

#### Scenario: 15-Minuten-Regel

- **Akteure:** Anonymer User, der um 12:00 hochlädt und 12:10 nochmal lädt.
- **Eingaben:** Keine weitere Aktivität.
- **Ergebnis:** Sweep um 12:25+ löscht User + alle Daten (Sliding ab letzter
  Aktivität 12:10).

### Req 2: Harte Limits (anonym)

- **Ablauf:** `anon_limits.py` prüft beim Upload: maximale Audiodauer
  (`POLYSCHNACK_ANON_MAX_DURATION_S`), maximale Upload-Größe
  (`POLYSCHNACK_ANON_MAX_UPLOAD_MB`), Disk-Quota
  (`POLYSCHNACK_ANON_MAX_DISK_MB`) → HTTPException (403/413).
- **Ergebnis:** Überschreitung → klare Fehlermeldung, kein Upload.

#### Scenario: Limit-Überschreitung

- **Akteure:** Anonymer User.
- **Eingaben:** 20-Minuten-Audio bei 15-Minuten-Limit.
- **Ergebnis:** 403/413 mit Meldung; kein Job.

### Req 3: Legacy-Public

- **Ablauf:** Aufnahmen ohne `user_id` sind „öffentlich" (read für anonyme);
  gehören aber keinem anon-User → nicht vom Retention-Sweep betroffen,
  sondern nur durch Admin/Delete löschbar.

#### Scenario: Alte öffentliche Aufnahme

- **Akteure:** Anonymer User.
- **Eingaben:** GET auf legacy-public-Aufnahme.
- **Ergebnis:** read-Zugriff; Löschen nur durch Owner/Admin (kein
  Retentions-Zugriff).
