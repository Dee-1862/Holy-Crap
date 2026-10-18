import fs from "node:fs";
import path from "node:path";

import { kvDrain, kvEnabled, kvGet, kvPush, kvSet } from "./kv";

// Where the QNX Pi edge uplink answers (target/qnx/edge/uplink.py). Default is the direct cable address.
export const EDGE_URL = process.env.EDGE_URL ?? "http://169.254.237.143:8088";
// A deployed console (Vercel) cannot reach a Pi on a cable to a laptop, so it does not try. The laptop runs
// scripts/edge_bridge.py, which pushes the Pi's status here and carries Crash presses back to the Pi.
export const DIRECT = !process.env.VERCEL || !!process.env.EDGE_URL;

const STATUS_KEY = "hc:edge:status", CMD_KEY = "hc:edge:cmds", FRAME_KEY = "hc:edge:frame", WATCH_KEY = "hc:edge:watching", FRESH_MS = 8000;
const mem = globalThis as unknown as { __bridge?: { status: unknown; at: number }; __cmds?: unknown[]; __frame?: LiveFrame; __watching?: number };

// The Pi's live camera picture (target/qnx/edge/sitelink.py), a small JPEG every couple of seconds with recent spots.
export interface LiveFrame { jpeg: string; t: number; w: number; h: number; source: string; spots: { id: string; cx: number; cy: number; t: number }[]; at: number }
export async function liveFrame(): Promise<LiveFrame | null> {
  const f = (await kvGet<LiveFrame>(FRAME_KEY)) ?? mem.__frame ?? null;
  return f && Date.now() - f.at < 15000 ? f : null;
}
// The Pi sends pictures back to back only while someone has the camera view open, every 10 s otherwise.
export async function storeFrame(frame: Omit<LiveFrame, "at">): Promise<boolean> {
  mem.__frame = { ...frame, at: Date.now() };
  const [, w] = await Promise.all([kvSet(FRAME_KEY, mem.__frame, 30), kvEnabled ? kvGet<number>(WATCH_KEY) : mem.__watching]);
  return !!w && Date.now() - w < 8000;
}
export async function markWatching() {
  mem.__watching = Date.now();
  await kvSet(WATCH_KEY, mem.__watching, 10);
}

export async function bridgeStatus(): Promise<{ status: Record<string, unknown>; at: number } | null> {
  const b = (await kvGet<{ status: Record<string, unknown>; at: number }>(STATUS_KEY)) ?? (mem.__bridge as { status: Record<string, unknown>; at: number } | undefined) ?? null;
  return b && Date.now() - b.at < FRESH_MS ? b : null;
}
export async function bridgePush(status: unknown): Promise<unknown[]> {
  const b = { status, at: Date.now() };
  mem.__bridge = b;
  await kvSet(STATUS_KEY, b, 60);
  // one queue only: the shared store when there is one, this instance's memory otherwise
  if (kvEnabled) return kvDrain<unknown>(CMD_KEY);
  const local = mem.__cmds ?? [];
  mem.__cmds = [];
  return local;
}
export async function queueCrash(proc: string) {
  if (kvEnabled) await kvPush(CMD_KEY, { proc, at: Date.now() });
  else mem.__cmds = [...(mem.__cmds ?? []), { proc, at: Date.now() }];
}

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
