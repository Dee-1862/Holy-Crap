"use client";

import { useEffect, useSyncExternalStore } from "react";
import { liveSpecimens, type Specimen } from "./data";

// Client side view of the actions people have taken. It follows the server (/api/state) and applies
// each action locally first, so buttons respond at once and still work if the API is unreachable.

export type SpecState = "new" | "checking" | "normal";
export interface VetCall { id: string; pen: string; specimenId?: string; ts: number; delivered: "sent" | "logged" | "failed" | "local" }

let states: Record<string, SpecState> = {};
let vet: VetCall[] = [];
let online = true;
let version = 0;
let clockMin = 0;          // demo clock in minutes, 0 until mounted so server and first client render match
let lastJson = "";
const listeners = new Set<() => void>();

const emit = () => { version++; listeners.forEach((l) => l()); };
function apply(d: { states?: Record<string, SpecState>; vet?: VetCall[] }) {
  const next = JSON.stringify([d.states ?? states, d.vet ?? vet]);
  if (next === lastJson) return;
  lastJson = next;
  states = d.states ?? states;
  vet = d.vet ?? vet;
  emit();
}

// Specimens that still count toward alerts and averages. Ones marked "Looks normal" drop out.
// Pens whose camera is online. Null means every pen counts (views that do not know about cameras).
let onlinePens: string[] | null = null;
export function setOnlinePens(pens: string[] | null) { onlinePens = pens; emit(); }
export const isOnlinePen = (id: string) => !onlinePens || onlinePens.includes(id);
export const specimens = (): Specimen[] => liveSpecimens(clockMin).filter((s) => isOnlinePen(s.group));
export const getSpecimens = (): Specimen[] => specimens().filter((s) => states[s.id] !== "normal");
export const stateOf = (id: string): SpecState => states[id] ?? "new";
export const lastVet = (pen: string): VetCall | undefined => vet.filter((v) => v.pen === pen).sort((a, b) => b.ts - a.ts)[0];
export const isOnline = () => online;

async function refresh() {
  try {
    const r = await fetch("/api/state", { cache: "no-store" });
    if (!r.ok) throw new Error(String(r.status));
    online = true;
    apply(await r.json());
  } catch {
    if (online) { online = false; emit(); }
  }
}

let timer: number | undefined;
function tickClock() {
  const m = Math.floor(Date.now() / 60000);
  if (m !== clockMin) { clockMin = m; emit(); }
}
let refs = 0;
const subscribe = (l: () => void) => { listeners.add(l); return () => { listeners.delete(l); }; };

// Call once near the top of a page. Re-renders when the barn state changes and keeps polling.
export function useBarn() {
  useSyncExternalStore(subscribe, () => version, () => 0);
  useEffect(() => {
    if (refs++ === 0) {
      void refresh();
      timer = window.setInterval(() => { void refresh(); tickClock(); }, 4000);
      tickClock();
    }
    return () => { if (--refs === 0) window.clearInterval(timer); };
  }, []);
}

async function post(url: string, body?: unknown) {
  const r = await fetch(url, { method: "POST", headers: { "content-type": "application/json" }, body: body ? JSON.stringify(body) : undefined });
  if (!r.ok) throw new Error(String(r.status));
  return r.json();
}

// "I'll check it"
export async function markChecking(id: string) {
  apply({ states: { ...states, [id]: "checking" } });
  try { apply(await post(`/api/specimens/${id}/check`)); } catch { online = false; emit(); }
}
// "Looks normal"
export async function markNormal(id: string) {
  apply({ states: { ...states, [id]: "normal" } });
  try { apply(await post(`/api/specimens/${id}/normal`)); } catch { online = false; emit(); }
}
// "Call the vet". Returns what happened so the button can say it.
export async function callVet(pen: string, specimenId?: string): Promise<{ duplicate: boolean; call: VetCall }> {
  try {
    const d = await post(`/api/pens/${pen}/vet`, { specimenId });
    apply(d);
    return { duplicate: !!d.duplicate, call: d.call as VetCall };
  } catch {
    const call: VetCall = { id: `L-${Date.now()}`, pen, specimenId, ts: Date.now(), delivered: "local" };
    apply({ vet: [call, ...vet] });
    online = false; emit();
    return { duplicate: false, call };
  }
}

// Undo "I'll check it" or "Looks normal".
export async function resetState(id: string) {
  const next = { ...states }; delete next[id];
  apply({ states: next });
  try { apply(await post(`/api/specimens/${id}/reset`)); } catch { online = false; emit(); }
}
