# Admin-Bereich

Der Admin-Bereich (`🛠 Admin` in der GUI, nur für Admins) steuert die
ASR-Services on demand — die Webapp spricht dafür **niemals direkt** den
Docker-Socket an, sondern den restriktiven Proxy-Container
[`tecnativa/docker-socket-proxy`](https://github.com/Tecnicality/docker-socket-proxy)
(nur Container-/Info-Routen + POST freigeschaltet; Exec/Create/Events deaktiviert).

## Funktionen

- **Services** — alle Backends mit Live-Status, Modell, Ressourcen-Report
  (VRAM/RAM/Disk), aktiven Jobs und Start/Stop/Neustart. Stop nur ohne
  laufende Jobs (sonst 409 mit Anzahl).
- **Ressourcen-Check vor Start** — RAM/Disk werden vor dem Start geprüft
  (VRAM exakt nur bei eigenen Servern über deren `/health`; bei Fremd-Images
  eine Warnung statt Blockade). Bei Mangel: 409 mit Report.
- **Config** — Default-Backend für neue Transkriptionen. Wechsel auf ein
  nicht-laufendes Backend startet es automatisch (nach Ressourcen-Check),
  persistiert in `DATA_DIR/config.json`.
- **Modell-Matrix** — Feature-Übersicht aller Backends, auch als
  `GET /api/models/matrix`.

## Concurrency

**Bewusst nicht konfigurierbar:** Jeder Endpunkt hat eine Kapazität
(selbstgehostete Services = 1), die Gesamt-Kapazität ist die Summe der
verfügbaren Endpunkte. Die Queue (`GET /api/queue`) zeigt eigene Jobs mit
Position/ETA, fremde anonymisiert (nur `#id`).

## Einmaliger Setup-Befehl

Erstellt alle Container, startet aber nichts — die GUI startet dann
on demand:

```
docker compose -f compose.yml -f compose.backends.yml -f compose.gpu.yml \
  --profile crispr-pk-cpp --profile crispr-qwen3 --profile crispr-ark \
  --profile crispr-moonshine-de --profile crispr-canary up -d --no-start
```

**Wichtig (Change 188):** Läuft die Installation mit GPU, gehört
`-f compose.gpu.yml` dazu — **nur dieses Overlay vergibt `runtime: nvidia`**;
ohne es starten alle Backends auf der CPU. Bei aktiver OIDC-Anmeldung zusätzlich
`-f compose.oidc.yml`. Am einfachsten das Set gar nicht selbst bauen:

```
./polyschnack-manage.sh start     # Kern + alle Backends, richtige Overlays, --no-start
./polyschnack-manage.sh status    # was liegt an Containern da
```

Das Skript nimmt genau die Overlays der Installation, kennt die Profile aus
`backends.yaml` und erzeugt die Backend-Container mit `--no-start`; gestartet
werden sie dann on demand über die Admin-GUI (oder gezielt per
`docker compose -f compose.yml -f compose.backends.yml -f compose.gpu.yml
--profile crispr-canary start crispr-canary`). Die Modell-Matrix zeigt ein
Backend erst als auswählbar (`reachable: true`), wenn sein Container läuft.
