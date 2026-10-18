"use client";

import { useEffect, useRef, useState } from "react";
import { TYPES, type Specimen } from "@/lib/data";
import { ago, groupName, nextStep, pct, resultOf, sortedProbs, topTwo, uncertainty } from "@/lib/insight";
import { callVet, lastVet, markChecking, markNormal, resetState, stateOf } from "@/lib/store";
import Gauge from "./Gauge";
import SpecimenCanvas from "./SpecimenCanvas";

const HOLD_MS = 1500;
const SUBS: [string, keyof Specimen["sub"]][] = [
  ["Color", "color"], ["Consistency", "consistency"], ["Urate cap", "urates"], ["Blood or mucus", "blood"], ["Foam", "foam"],
];
// Scores stay neutral. Only a middling or low score picks up a color.
const meterClass = (v: number) => (v >= 8 ? "" : v >= 5 ? "w" : "b");
// Where each numbered marker sits relative to the specimen. Demo layout. In production
// the explainability model returns a region for every evidence line.
const MARKER_OFFSETS: [number, number][] = [[-0.13, -0.1], [0.15, 0.04], [-0.02, 0.2]];
const clamp = (v: number) => Math.min(0.94, Math.max(0.06, v));

// One specimen. Verdict, plan, photo with evidence markers, scores and actions.
// Mount with key={specimen.id} so local state resets when the specimen changes.
export default function SpecimenCard({ specimen: s }: { specimen: Specimen }) {
  const [heat, setHeat] = useState(true);
  const [on, setOn] = useState<number | null>(null);
  const [msg, setMsg] = useState("");
  const [progress, setProgress] = useState(0);
  const timer = useRef<number | null>(null);
  const started = useRef(0);
  const state = stateOf(s.id);

  const stop = () => {
    if (timer.current !== null) window.clearInterval(timer.current);
    timer.current = null;
    setProgress(0);
  };
  useEffect(() => () => { if (timer.current !== null) window.clearInterval(timer.current); }, []);

  // Hold the button for 1.5 seconds to call the vet, so a stray tap never does it.
  const startHold = () => {
    started.current = Date.now();
    timer.current = window.setInterval(() => {
      const p = Math.min(1, (Date.now() - started.current) / HOLD_MS);
      setProgress(p);
      if (p >= 1) {
        stop();
        void callVet(s.group, s.id).then(({ duplicate, call }) => {
          const name = groupName(s.group);
          if (duplicate) setMsg(`The vet was already requested for ${name} ${Math.max(1, Math.round((Date.now() - call.ts) / 60000))} min ago.`);
          else if (call.delivered === "sent") setMsg(`Vet notified for ${name}.`);
          else if (call.delivered === "failed") setMsg(`Saved for ${name}, but the message did not go out. Check the webhook.`);
          else setMsg(`Request saved for ${name}. No phone or message service is connected yet.`);
        });
      }
    }, 30);
  };

  const next = nextStep(s);
  const order = sortedProbs(s);
  const unc = uncertainty(s);
  const evidence = s.why.slice(0, 3);

  return (
    <div className="card">
      <div className="head">
        <span className="eyebrow">Specimen {s.id}</span>
        <span className="eyebrow">{groupName(s.group)}, {ago(s.minsAgo)}</span>
      </div>

      <div className="verdict">
        <Gauge grade={s.grade} />
        <div>
          <div className="t">{resultOf(s)}</div>
          <div className="s">{pct(s.probs[s.type])}% confident. Screening only, not a diagnosis.</div>
          {state !== "new" && <div className="chip">{state === "checking" ? "Someone is checking this" : "Marked normal, no longer counts toward alerts"}<button onClick={() => resetState(s.id)}>Undo</button></div>}
        </div>
      </div>

      <div className={`next ${next.level}`}><b />{next.head}<small>{next.note}</small></div>

      <div className="photo">
        <SpecimenCanvas type={s.type} region={s.region} heat={heat} seed={s.id} label="Illustrated specimen" />
        {heat && evidence.map((_, i) => (
          <button
            key={i} className="mk" data-on={on === i} aria-label={`Evidence ${i + 1}`}
            style={{ left: `${clamp(s.region[0] + MARKER_OFFSETS[i][0]) * 100}%`, top: `${clamp(s.region[1] + MARKER_OFFSETS[i][1]) * 100}%` }}
            onMouseEnter={() => setOn(i)} onMouseLeave={() => setOn(null)} onFocus={() => setOn(i)} onBlur={() => setOn(null)}
          >{i + 1}</button>
        ))}
      </div>
      <div className="tools">
        <label className="switch">
          <input type="checkbox" checked={heat} onChange={(e) => setHeat(e.target.checked)} />
          Show where the model looked
        </label>
        <span>Placeholder image</span>
      </div>

      <span className="eyebrow sec">What the model saw</span>
      <ul className="saw">
        {evidence.map((w, i) => (
          <li key={w}>
            <button data-on={on === i} onMouseEnter={() => setOn(i)} onMouseLeave={() => setOn(null)} onFocus={() => setOn(i)} onBlur={() => setOn(null)}>
              <b>{i + 1}</b><span>{w}</span>
            </button>
          </li>
        ))}
      </ul>

      <span className="eyebrow sec">Scores</span>
      <div className="subs">
        {SUBS.map(([label, k]) => (
          <div key={k}>
            {label} <span className="v num">{s.sub[k]}</span>
            <div className="meter"><i className={meterClass(s.sub[k])} style={{ width: `${s.sub[k] * 10}%` }} /></div>
          </div>
        ))}
      </div>

      <details>
        <summary>Model details</summary>
        <div className="top2">{topTwo(s)}</div>
        {order.map((k) => (
          <div className="prob" key={k}>
            <span>{TYPES[k].name}</span>
            <div className="meter"><i style={{ width: `${pct(s.probs[k])}%` }} /></div>
            <b className="num">{pct(s.probs[k])}%</b>
          </div>
        ))}
        <div className="note"><b>{unc.text}</b> Margin between the top two is {pct(unc.margin)} points.</div>
        <div className="refs">
          {[0, 1, 2].map((i) => (
            <SpecimenCanvas key={i} type={s.type} region={[0.5, 0.5]} heat={false} seed={`${s.id}r${i}`} width={120} height={90} label={`Reference example ${i + 1}`} />
          ))}
        </div>
        <div className="note">Reference examples are placeholders. In production they come from the labeled training set.</div>
      </details>

      <div className="actions">
        <button className="btn go" onClick={() => { void markChecking(s.id); setMsg("The team can see you are checking this."); }} disabled={state === "checking"}>
          <span className="b-t">{state === "checking" ? "Checking" : "I'll check it"}</span>
          <small>Tells the team you are on it</small>
        </button>
        <button className="btn" onClick={() => { void markNormal(s.id); setMsg("Marked normal. It no longer counts toward alerts."); }} disabled={state === "normal"}>
          <span className="b-t">Looks normal</span>
          <small>Removes it from alerts</small>
        </button>
        <button
          className="btn hold" onPointerDown={startHold} onPointerUp={stop} onPointerLeave={stop} onPointerCancel={stop}
          aria-label="Hold to call the vet"
        >
          <span className="b-t">Call the vet</span>
          <small>Hold to send</small>
          <span className="fill" style={{ width: `${progress * 100}%` }} />
        </button>
      </div>
      <div className="status" role="status">{msg || (lastVet(s.group) ? `Vet requested for ${groupName(s.group)} ${Math.max(0, Math.round((Date.now() - lastVet(s.group)!.ts) / 60000))} min ago.` : "")}</div>
    </div>
  );
}
