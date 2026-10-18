import fs from "node:fs";
import path from "node:path";
import { GROUPS, SPECIMENS } from "@/lib/data";
import { kvEnabled, kvGet, kvSet } from "./kv";

// Server side state for the actions people take. With a KV store connected (Vercel) it lives there, so every
// instance and the watch see the same state. Otherwise in memory, mirrored to .data/state.json on this machine.

export type SpecState = "new" | "checking" | "normal";
export type Delivery = "sent" | "logged" | "failed";
export interface VetCall { id: string; pen: string; specimenId?: string; ts: number; delivered: Delivery }
export interface State { states: Record<string, SpecState>; vet: VetCall[] }

const FILE = path.join(process.cwd(), ".data", "state.json");
const g = globalThis as unknown as { __barn?: State };

function load(): State {
  try {
    const raw = JSON.parse(fs.readFileSync(FILE, "utf8")) as Partial<State>;
    return { states: raw.states ?? {}, vet: raw.vet ?? [] };
  } catch {
    return { states: {}, vet: [] };
  }
}
const KEY = "hc:state";

async function save(s: State) {
  if (kvEnabled) { await kvSet(KEY, s); return; }
  try {
    fs.mkdirSync(path.dirname(FILE), { recursive: true });
    fs.writeFileSync(FILE, JSON.stringify(s));
  } catch { /* read only disk, keep in memory */ }
}

export async function getState(): Promise<State> {
  if (kvEnabled) {
    const raw = await kvGet<Partial<State>>(KEY);
    return { states: raw?.states ?? {}, vet: raw?.vet ?? [] };
  }
  if (!g.__barn) g.__barn = load();
  return g.__barn;
}

export const knownSpecimen = (id: string) => SPECIMENS.some((s) => s.id === id);
export const knownPen = (id: string) => GROUPS.some((p) => p.id === id);

export async function setSpecimenState(id: string, st: SpecState): Promise<State> {
  const s = await getState();
  if (st === "new") delete s.states[id]; else s.states[id] = st;
  await save(s);
  return s;
}

const DUPLICATE_WINDOW_MS = 60_000;

// Records a vet request and, when VET_WEBHOOK_URL is set, sends it there as JSON with both
// "text" and "content" so Slack and Discord style webhooks work. Without a webhook the
// request is only logged. Placing a real phone call needs a provider account (for example Twilio).
export async function requestVet(pen: string, specimenId?: string): Promise<{ call: VetCall; duplicate: boolean; state: State }> {
  const s = await getState();
  const recent = s.vet.find((v) => v.pen === pen && Date.now() - v.ts < DUPLICATE_WINDOW_MS);
  if (recent) return { call: recent, duplicate: true, state: s };

  const name = GROUPS.find((p) => p.id === pen)?.name ?? pen;
  const url = process.env.VET_WEBHOOK_URL;
  let delivered: Delivery = "logged";
  if (url) {
    try {
      const text = `Vet requested for ${name}${specimenId ? ` (specimen ${specimenId})` : ""}. Please call the farm.`;
      const r = await fetch(url, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ text, content: text, pen, specimenId }),
        signal: AbortSignal.timeout(5000),
      });
      delivered = r.ok ? "sent" : "failed";
    } catch {
      delivered = "failed";
    }
  }
  const call: VetCall = { id: `V-${Date.now().toString(36)}`, pen, specimenId, ts: Date.now(), delivered };
  s.vet.unshift(call);
  s.vet = s.vet.slice(0, 20);
  await save(s);
  return { call, duplicate: false, state: s };
}
