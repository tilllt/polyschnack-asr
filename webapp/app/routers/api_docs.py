"""Zentrale API-Dokumentation für ALLE PolySchnack-Container (2026-08-15).

GET /api/specs/<name>.json  → OpenAPI-Spec des jeweiligen Containers
GET /api-docs              → Swagger-UI mit Container-Auswahl (alle Backends)

Die Specs leben in app/api_specs.py (versioniert im Repo). Der Aligner
liefert sein /openapi.json zusätzlich selbst im Container aus.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse

from ..api_specs import build_specs

router = APIRouter()

_SPECS = build_specs()

_SWAGGER_UI = """<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <meta name="robots" content="noindex, nofollow" />
  <title>PolySchnack — API-Dokumentation</title>
  <link rel="icon" type="image/svg+xml" href="/logo.svg" />
  <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css" />
  <style>
    body { margin: 0; background: #0f172a; font-family: system-ui, sans-serif; }
    .topbar { background: #1a2333; color: #e2e8f0; padding: 10px 18px;
              display: flex; align-items: center; gap: 14px; flex-wrap: wrap;
              border-bottom: 1px solid #2d3a52; }
    .topbar h1 { font-size: 15px; margin: 0; font-weight: 700; }
    .topbar a { color: #91b4ff; text-decoration: none; font-size: 13px; }
    .topbar select { background: #0f172a; color: #e2e8f0; border: 1px solid #2d3a52;
                     border-radius: 6px; padding: 5px 8px; font-size: 13px; }
    .topbar .direct { font-size: 11px; color: #7c8db5; }
    .swagger-wrap { padding: 6px 18px 30px; }
  </style>
</head>
<body>
  <div class="topbar">
    <h1>📡 PolySchnack — API-Dokumentation</h1>
    <label>Container:
      <select id="specSelect"></select>
    </label>
    <span class="direct" id="directHint"></span>
    <a href="/">← zurück zur App</a>
  </div>
  <div class="swagger-wrap" id="swaggerContainer"></div>

  <script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
  <script>
    const SPECS = %SPECS_JSON%;
    const NAMES = Object.keys(SPECS);
    const sel = document.getElementById("specSelect");
    NAMES.forEach((n) => {
      const o = document.createElement("option");
      o.value = n; o.textContent = n;
      sel.appendChild(o);
    });
    const hint = document.getElementById("directHint");
    let ui = null;
    function render() {
      const name = sel.value;
      const spec = SPECS[name];
      const url = spec.servers && spec.servers[0] ? spec.servers[0].url : "";
      hint.textContent = url ? "Direkt erreichbar unter: " + url : "";
      document.title = "PolySchnack API — " + name;
      if (ui) { ui.destroy(); }
      ui = SwaggerUIBundle({
        spec: spec,
        dom_id: "#swaggerContainer",
        deepLinking: true,
        persistAuthorization: true,
      });
    }
    sel.addEventListener("change", render);
    render();
  </script>
</body>
</html>
"""


@router.get("/api/specs/{name}.json")
def get_spec(name: str) -> JSONResponse:
    """OpenAPI-Spec eines einzelnen Containers."""
    spec = _SPECS.get(name)
    if spec is None:
        raise HTTPException(status_code=404, detail=f"unknown spec: {name}")
    return JSONResponse(spec)


@router.get("/api-docs", response_class=HTMLResponse, include_in_schema=False)
def api_docs() -> HTMLResponse:
    """Swagger-UI mit Auswahl für alle Container."""
    import json

    html = _SWAGGER_UI.replace("%SPECS_JSON%", json.dumps(_SPECS, ensure_ascii=False))
    return HTMLResponse(html)
