// E2E Phase 2: Persistenz nach ECHTEM Server-Neustart (Change 053).
// Läuft NACH Phase 1 (client.mjs) + Server-Restart mit gleichem DATA_DIR.
// Ein frischer Client muss den gespeicherten Zustand aus dem Snapshot laden.
import { Doc } from "yjs";
import { WebsocketProvider } from "y-websocket";

const WS = "ws://localhost:12347";
const ROOM = "e2e-room";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const docC = new Doc();
const provC = new WebsocketProvider(WS, ROOM, docC, { connect: true });

const t0 = Date.now();
while (!provC.wsconnected && Date.now() - t0 < 5000) await sleep(50);
if (!provC.wsconnected) throw new Error("keine Verbindung");
await sleep(700); // Sync aus dem Snapshot

const segC = docC.getMap("segments");
console.log("C nach Server-Neustart:", segC.get("0")?.toString(), "|", segC.get("1")?.toString());
if (segC.get("0")?.toString() !== "Erster Text — geändert") {
  console.error("FAIL: Snapshot-Persistenz nach Server-Neustart nicht geladen");
  process.exit(1);
}

provC.disconnect();
console.log("E2E Phase 2 OK: Persistenz nach Server-Neustart verifiziert");
process.exit(0);
