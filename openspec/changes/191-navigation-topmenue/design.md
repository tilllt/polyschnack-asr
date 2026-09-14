# Design — Change 191

## Ansichts-Zustand

```
view: "main" | "settings" | "benchmark" | "admin"     (Default: "main")
```

- `main` = Transkribieren (Upload, Queue, Suche, Aufnahmeliste) — unverändert
  in der Funktion, aber **ohne** `<AdminPanel />`.
- `settings` = `UserSettingsPage` (wie bisher).
- `benchmark` = `BenchmarkPageContent`. Der Pfad `/benchmark` schaltet
  zusätzlich diese Ansicht ein (`showBenchmark = isBenchmark || view ===
  "benchmark"`), damit alte Links weiter funktionieren.
- `admin` = `AdminPanel`, gerendert **nur** wenn `user?.is_admin`; der
  Menüpunkt wird Nicht-Admins gar nicht angeboten.

Anon-Share (`/r/:uid`) und die Benchmark-Route bleiben vorgeschaltet: sie
übersteuern den Menüzustand wie bisher.

## Login/Logout-Symbol

| Zustand | Anzeige |
|---|---|
| `user.oidc_enabled && !user.authenticated` | Symbol „Anmelden" → `/auth/login` |
| `user.authenticated` | `user.name` + Symbol „Abmelden" → `/auth/logout` |
| `user.anonymous` | wie bisher `🎭 name` (Share-Link-Kontext) |

Symbol: `LogIn` / `LogOut` aus `lucide-react` (bereits im Projekt), `size=14`,
`title` + `aria-label` aus der Lokalisierung (`login` / `logout`), damit es
auch ohne Text verständlich bleibt.

## Menü

Ein `<nav>` in der Kopfzeile mit vier Knöpfen; aktiver Eintrag mit
`bg-accent/20 text-accent` (bestehende Muster), inaktive `text-muted
hover:text-txt hover:bg-[rgba(255,255,255,.05)]`. Auf schmalen Bildschirmen
bricht die Zeile um (bestehende `flex-wrap`-Logik), der Nutzerbereich bleibt
rechts (`ml-auto`).

## Tests

- `tsc --noEmit` sauber.
- Vitest: Menüpunkte vorhanden, aktiver Zustand markiert; Admin-Menüpunkt nur
  bei `is_admin`; Admin-Panel erscheint **nicht** in der Hauptansicht; das
  Symbol wechselt Login/Logout je nach Zustand.
