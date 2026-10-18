"use client";

import { useEffect, useRef, useState } from "react";
import { GROUPS } from "@/lib/data";
import { resultOf, seenAt, tone } from "@/lib/insight";
import { mostCritical } from "@/lib/rules";
import { callVet, clearVet, lastVet, markChecking, markNormal, resetState, specimens, stateOf } from "@/lib/store";

const HOLD_MS = 1500;

// The same controls the watch has, for the selected pen: its most critical dropping with "I'll check it",
// "Looks normal" and a held "Terminate" that calls the vet. A terminated pen says so and stays locked until it
// is cleared here or an hour passes, on the website and the watch alike.
export default function PenActions({ groupId, onOpen }: { groupId: string; onOpen: (specimenId: string) => void }) {
  const group = GROUPS.find((g) => g.id === groupId) ?? GROUPS[0];
  const list = specimens().filter((s) => s.group === group.id);
  const s = mostCritical(list, (x) => stateOf(x.id) === "normal");
  const vet = lastVet(group.id);
  const [msg, setMsg] = useState("");
  const [progress, setProgress] = useState(0);
  const timer = useRef<number | null>(null);
  const started = useRef(0);

  const stop = () => {
    if (timer.current !== null) window.clearInterval(timer.current);
    timer.current = null;
    setProgress(0);
  };
  useEffect(() => () => { if (timer.current !== null) window.clearInterval(timer.current); }, []);

  // Hold for 1.5 seconds, like the watch, so a stray click never terminates a pen.
  const startHold = () => {
    if (vet) return;
    started.current = Date.now();
    timer.current = window.setInterval(() => {
      const p = Math.min(1, (Date.now() - started.current) / HOLD_MS);
      setProgress(p);
      if (p >= 1) {
        stop();
        void callVet(group.id, s?.id).then(({ duplicate, call }) => {
          if (duplicate) setMsg(`${group.name} was already terminated ${Math.max(1, Math.round((Date.now() - call.ts) / 60000))} min ago.`);
          else if (call.delivered === "sent") setMsg(`${group.name} terminated. The vet was notified.`);
          else if (call.delivered === "failed") setMsg(`${group.name} terminated, but the message did not go out. Check the webhook.`);
          else setMsg(`${group.name} terminated. No phone or message service is connected yet.`);
        });
      }
    }, 30);
  };

  const state = s ? stateOf(s.id) : "new";
  return (
    <div style={{ marginTop: 14 }}>
      {vet && (
        <div className="chip" style={{ marginTop: 0, marginBottom: 10, color: "var(--bad)" }}>
          Terminated {Math.max(0, Math.round((Date.now() - vet.ts) / 60000))} min ago, vet called
          <button onClick={() => { void clearVet(group.id); setMsg(`${group.name} cleared. It can be terminated again.`); }}>Clear</button>
        </div>
      )}

      <span className="eyebrow">Most critical{list.length > 1 ? ` of ${list.length} droppings` : ""}</span>
      {s ? (
        <div className="list on-glass" style={{ marginTop: 6 }}>
        <button className="row" style={{ gridTemplateColumns: "34px 1fr auto" }} onClick={() => onOpen(s.id)}>
          <b className={`num tone-${state === "normal" ? "" : tone(s.grade)}`} style={{ fontSize: 22, fontWeight: 500, textAlign: "center" }}>{s.grade}</b>
          <span>
            <b style={{ display: "block", fontWeight: 600, fontSize: 16 }}>{resultOf(s)}</b>
            <small className="foot">{s.cam ? `Dropping ${s.cam.n}, ${seenAt(s).toLowerCase()}` : seenAt(s)}{state === "checking" ? ", being checked" : state === "normal" ? ", marked normal" : ""}</small>
          </span>
          <span className="foot">View details</span>
        </button>
        </div>
      ) : (
        <p className="foot" style={{ margin: "6px 0 0" }}>No droppings in this pen right now.</p>
      )}

      <div className="actions" style={{ marginTop: 10 }}>
        {state === "new" || !s ? (
          <button className="btn go" disabled={!s} onClick={() => { if (s) { void markChecking(s.id); setMsg("The team can see you are checking this."); } }}>
            <span className="b-t">I&apos;ll check it</span>
          </button>
        ) : (
          <button className="btn" onClick={() => { void resetState(s.id); setMsg("Undone."); }}>
            <span className="b-t">Undo</span><small>{state === "checking" ? "Being checked" : "Marked normal"}</small>
          </button>
        )}
        <button className="btn" disabled={!s || state === "normal"} onClick={() => { if (s) { void markNormal(s.id); setMsg("Marked normal. The next most critical takes its place."); } }}>
          <span className="b-t">Looks normal</span>
        </button>
        <button
          className="btn hold" disabled={!!vet} onPointerDown={startHold} onPointerUp={stop} onPointerLeave={stop} onPointerCancel={stop}
          aria-label={vet ? `${group.name} is already terminated` : `Hold to terminate ${group.name} and call the vet`}
        >
          <span className="b-t">{vet ? "Terminated" : "Terminate"}</span>
          <small>{vet ? "Clear to redo" : "Hold, calls the vet"}</small>
          <span className="fill" style={{ width: `${progress * 100}%` }} />
        </button>
      </div>
      <div className="status" role="status">{msg}</div>
    </div>
  );
}
