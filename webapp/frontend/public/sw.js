/* PolySchnack Service Worker — PWA-Installierbarkeit + App-Shell-Cache.
 *
 * Strategie:
 *  - Statische Assets (JS/CSS-Bundles, Bilder, Fonts): Cache-First mit
 *    Netzwerk-Fallback. Vite hasht die Dateinamen (index-XXXX.js), daher
 *    ist eine neue Version automatisch ein neuer Cache-Eintrag.
 *  - index.html: Network-First (immer frische Shell), Fallback auf Cache.
 *  - /api/* und /health: NIE cachen — Netzwerk-only (frische Daten,
 *    Uploads, Queues). Offline schlägt die API fehl, aber die lokale
 *    Aufnahme (IndexedDB-Puffer) funktioniert weiter.
 */
const CACHE = "polyschnack-v1";
const SHELL = ["/", "/index.html"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(SHELL)).catch(() => {})
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return; // POST/Uploads nie anfassen
  const url = new URL(req.url);
  if (url.pathname.startsWith("/api/") || url.pathname === "/health") return;

  // Asset mit Hash → Cache-First
  if (url.pathname.includes("/assets/")) {
    event.respondWith(
      caches.match(req).then((hit) => hit || fetch(req).then((res) => {
        const copy = res.clone();
        caches.open(CACHE).then((c) => c.put(req, copy));
        return res;
      }))
    );
    return;
  }

  // index.html / Navigation → Network-First, Fallback Cache
  event.respondWith(
    fetch(req).then((res) => {
      const copy = res.clone();
      caches.open(CACHE).then((c) => c.put(req, copy));
      return res;
    }).catch(() => caches.match(req).then((hit) => hit || caches.match("/index.html")))
  );
});
