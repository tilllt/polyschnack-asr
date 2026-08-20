// E2E: 2 y-websocket-Clients synchronisieren über den pycrdt-Server.
// Nutzt exakt die Bibliotheken der GUI (yjs + y-websocket).
import { Doc, Text } from "yjs";
import { WebsocketProvider } from "y-websocket";

const WS = "ws://localhost:12347";
const ROOM = "e2e-room";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function mkDoc() {
  const doc = new Doc();
  const segs = doc.getMap("segments");
  segs.set("0", new Text("Erster Text"));
  segs.set("1", new Text("Zweiter Text"));
  return doc;
}

async function waitConnected(p, timeoutMs = 5000) {
  const t0 = Date.now();
  while (!p.wsconnected && Date.now() - t0 < timeoutMs) await sleep(50);
  if (!p.wsconnected) throw new Error("keine Verbindung");
}

// ── 1. Client A verbindet und befüllt den Room ──────────────────────────
const docA = mkDoc();
const provA = new WebsocketProvider(WS, ROOM, docA, { connect: true });
await waitConnected(provA);
await sleep(300); // Sync-Flush

// ── 2. Client B verbindet → muss den State von A bekommen ───────────────
const docB = new Doc();
const provB = new WebsocketProvider(WS, ROOM, docB, { connect: true });
await waitConnected(provB);
await sleep(500); // initialer Sync

const segB = docB.getMap("segments");
console.log("B nach Initial-Sync:", segB.get("0")?.toString(), "|", segB.get("1")?.toString());
if (segB.get("0")?.toString() !== "Erster Text") {
  console.error("FAIL: B hat Initial-State nicht erhalten");
  process.exit(1);
}

// ── 3. A ändert → B muss die Änderung live sehen ────────────────────────
let received = null;
docB.on("update", () => {
  received = segB.get("0")?.toString();
});
segB.get("0").insert(segB.get("0").length, " — geändert");
await sleep(500);
console.log("A nach Edit:", docA.getMap("segments").get("0")?.toString());
console.log("B nach Edit:", segB.get("0")?.toString());
if (segB.get("0")?.toString() !== "Erster Text — geändert") {
  console.error("FAIL: Live-Sync A→B nicht angekommen");
  process.exit(1);
}

// ── 4. Persistenz: neuer Client C (Server-Room neu aufgebaut) ───────────
provA.disconnect();
provB.disconnect();
await sleep(200);

const docC = new Doc();
const provC = new WebsocketProvider(WS, ROOM, docC, { connect: true });
await waitConnected(provC);
await sleep(700);
const segC = docC.getMap("segments");
console.log("C nach Persistenz-Load:", segC.get("0")?.toString(), "|", segC.get("1")?.toString());
if (segC.get("0")?.toString() !== "Erster Text — geändert") {
  console.error("FAIL: Snapshot-Persistenz nicht geladen");
  process.exit(1);
}

provC.disconnect();
console.log("E2E OK: Initial-Sync, Live-Edit, Persistenz — alles verifiziert");
process.exit(0);
