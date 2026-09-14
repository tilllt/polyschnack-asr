# Change 188 — Optionale Backends startbar/auswählbar machen (Compose-Container-Namen)

**Status:** Implemented (2026-09-14, gleiche Session wie die Diagnose)

## Befund (Live, Prod KI-Box, 2026-09-14)

User: „Ich habe versucht mit den Anweisungen die gezeigt werden crispr-canary zu
starten, aber es gab Fehler."

Aufgenommen in der Produktion:

- Der Container **existierte** (`polyschnack-crispr-canary-1`, `Exited (137)`),
  das Image lag lokal (4,15 GB) und das Modell war vorhanden
  (`DATA/models/canary-1b-v2-q4_k.gguf`). Ein Start mit dem Overlay-Set, das die
  laufende Installation benutzt (`compose.yml` + `compose.backends.yml` +
  `compose.gpu.yml` + `compose.oidc.yml`), lief sofort sauber hoch
  („Up (healthy)", `runtime=nvidia`, Modelle geladen, Port 5097).
- Die Webapp sah ihn trotzdem **nicht**: `/api/models/matrix` meldete für
  `crispr-canary` `reachable: false`, obwohl
  `http://crispr-canary:5097/health` aus dem Webapp-Container 200 lieferte.

**Root Cause:** `service_registry.container_name()` gibt den **logischen**
Namen zurück (`crispr-canary`). Compose benennt Container aber
`<projekt>-<service>-<index>` (`polyschnack-crispr-canary-1`) — ein explizites
`container_name` setzen nur einzelne Services (z. B. `docker-proxy`). Der
docker-socket-proxy antwortet auf `GET /containers/crispr-canary/json` mit
**404** → `container_state()` → `None` → Matrix `reachable: false` → das Backend
wird nicht angeboten; dieselbe Auflösung nutzen die Admin-Aktionen
`/api/admin/services/{name}/start|stop|restart` → dort ebenfalls 404. Betroffen
sind **alle** optionalen Backends (crispr-pk-cpp, -qwen3, -ark, -moonshine-de,
-canary, -voxtral, -whisper); die Kern-Services umgehen die Prüfung
(`compose_profile == "default"` → immer `reachable`).

**Zweiter Befund (Doku):** Die gezeigten Befehle
(`docs/configuration/admin.md`, Kopf von `compose.yml`) nennen nur
`-f compose.yml -f compose.backends.yml`. Die laufende Installation nutzt laut
Container-Labels vier Dateien inkl. `compose.gpu.yml` — ohne dieses Overlay
starten die Backends **auf der CPU** (`runtime: nvidia` wird ausschließlich dort
vergeben). Wer den Befehl aus der Doku nimmt, erzeugt/startet die Backends also
nicht nur anders als die Installation, sondern ohne GPU.

## Was sich ändert (Verhaltens-Delta)

1. **Container-Auflösung:** Vor jeder Statusabfrage und jeder Aktion wird der
   logische Service-Name auf den echten Container aufgelöst — exakter Name
   zuerst, sonst Suche über das Compose-Label
   `com.docker.compose.service=<name>` (`DockerProxyClient.resolve_container`,
   genutzt von `container_state`, `start`, `stop`, `restart`, `logs`).
   Ergebnis: Ein laufender Backend-Container ist in der Modell-Matrix
   `reachable: true` und per Admin-Endpoint start-/stoppbar.
2. **Ehrlicher Fehlerfall:** Bleibt die Auflösung erfolglos, wird der rohe Name
   verwendet — die Aktion liefert dann weiterhin den 404 „container not created
   — run the --no-start setup first" statt eines irreführenden Fehlers.
3. **Keine Schema-/API-Änderung**, keine neuen Felder; rein client-seitige
   Auflösung.

## Specs-Delta

- `MODIFIED` **model-matrix**: „reachable" wird über den echten
  Compose-Container bestimmt (Label-Auflösung), nicht über den Service-Namen.

## Risiken / Trade-offs

- Zusätzlicher `GET /containers/json` nur im Fall „exakter Name trifft nicht"
  (ein Request, gecacht wird nicht — die Matrix wird ohnehin selten geladen).
- Mehrfach laufende Container desselben Service (Skalierung) sind in diesem
  Stack ausgeschlossen (Concurrency = 1 je selbstgehostetem Service).

## Offener Punkt (Doku, separat)

Die Setup-Befehle in `docs/configuration/admin.md` und im Kopf von
`compose.yml` müssen das Overlay-Set der Installation nennen
(`compose.gpu.yml`, bei OIDC zusätzlich `compose.oidc.yml`) oder auf
`./polyschnack-manage.sh backends <namen>` verweisen — sonst startet der User
CPU-Container. Änderung ist bewusst nicht Teil dieses Changes (Doku-Repo-Teil),
sondern als Folgeaufgabe notiert.
