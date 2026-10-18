import fs from "node:fs";
import path from "node:path";

// Where the QNX Pi edge uplink answers (target/qnx/edge/uplink.py). Default is the direct cable address.
export const EDGE_URL = process.env.EDGE_URL ?? "http://169.254.237.143:8088";

// What the Pi's cloud section pushed. In memory, mirrored to .data/edge.json like the barn state.
interface Ingested { device: string; lastSeen: number; results: unknown[]; actions: unknown[]; health: unknown | null; received: number }
const FILE = path.join(process.cwd(), ".data", "edge.json");
const g = globalThis as unknown as { __edge?: Ingested };

function load(): Ingested {
  try {
    return JSON.parse(fs.readFileSync(FILE, "utf8")) as Ingested;
  } catch {
    return { device: "", lastSeen: 0, results: [], actions: [], health: null, received: 0 };
  }
}

export function latestIngest(): Ingested {
  if (!g.__edge) g.__edge = load();
  return g.__edge;
}

export function ingest(device: string, events: unknown[]) {
  const s = latestIngest();
  for (const e of events as { kind?: string }[]) {
    if (e?.kind === "explained") s.results = [e, ...s.results].slice(0, 50);
    else if (e?.kind === "action" || e?.kind === "vet") s.actions = [e, ...s.actions].slice(0, 50);
    else if (e?.kind === "health") s.health = e;
  }
  s.device = device;
  s.lastSeen = Date.now();
  s.received += events.length;
  try {
    fs.mkdirSync(path.dirname(FILE), { recursive: true });
    fs.writeFileSync(FILE, JSON.stringify(s));
  } catch { /* read only disk on Vercel, keep in memory */ }
  return { ok: true, received: events.length };
}
