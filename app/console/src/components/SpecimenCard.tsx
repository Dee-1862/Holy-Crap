"use client";

import { useEffect, useRef, useState } from "react";
import { TYPES, type Specimen } from "@/lib/data";
import { ago, groupName, nextStep, pct, resultOf, sortedProbs, topTwo, uncertainty } from "@/lib/insight";
import Gauge from "./Gauge";
import SpecimenCanvas from "./SpecimenCanvas";

const HOLD_MS = 1500;
const SUBS: [string, keyof Specimen["sub"]][] = [
  ["Color", "color"], ["Consistency", "consistency"], ["Urate cap", "urates"], ["Blood or mucus", "blood"], ["Foam", "foam"],
];
const meterClass = (v: number) => (v >= 8 ? "" : v >= 5 ? "w" : "b");

// One specimen: verdict, next step, photo, evidence, scores and actions.
// Mount with key={specimen.id} so local state resets when the specimen changes.
export default function SpecimenCard({ specimen: s }: { specimen: Specimen }) {
  const [heat, setHeat] = useState(true);
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

  const startHold = () => {
    started.current = Date.now();
    timer.current = window.setInterval(() => {
      const p = Math.min(1, (Date.now() - started.current) / HOLD_MS);
      setProgress(p);
      if (p >= 1) {
        stop();
        setMsg(`Vet called for ${groupName(s.group)} (demo, nothing was sent).`);
      }
    }, 30);
  };

  const next = nextStep(s);
  const order = sortedProbs(s);
  const unc = uncertainty(s);

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
          <div className="s">Confidence {pct(s.probs[s.type])}%. Screening result, not a diagnosis.</div>
        </div>
      </div>

      <div className={`next ${next.level}`}><div>{next.head}<small>{next.note}</small></div></div>

      <div className="photo">
        <SpecimenCanvas type={s.type} region={s.region} heat={heat} seed={s.id} label="Illustrated specimen" />
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
        {s.why.slice(0, 3).map((w, i) => <li key={w}><b>{i + 1}</b><span>{w}</span></li>)}
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
        <summary>Model confidence</summary>
        <div className="top2">{topTwo(s)}</div>
        {order.map((k, i) => (
          <div className="prob" key={k}>
            <span>{TYPES[k].name}</span>
            <div className="meter"><i className={i === 0 ? "w" : ""} style={{ width: `${pct(s.probs[k])}%` }} /></div>
            <b className="num">{pct(s.probs[k])}%</b>
          </div>
        ))}
        <div className="note"><b>{unc.text}</b> Margin between the top two is {pct(unc.margin)} points.</div>
      </details>

      <details>
        <summary>Closest reference examples</summary>
        <div className="refs">
          {[0, 1, 2].map((i) => (
            <SpecimenCanvas key={i} type={s.type} region={[0.5, 0.5]} heat={false} seed={`${s.id}r${i}`} width={120} height={90} label={`Reference example ${i + 1}`} />
          ))}
        </div>
        <div className="note">Placeholders. In production these come from the labeled training set.</div>
      </details>

      <details>
        <summary>How the grade works</summary>
        <div className="note">
          Grade runs from 1 to 10, where 10 is a textbook healthy dropping. In this demo it comes from the model&apos;s healthy
          probability, lowered when color, moisture, blood or foam look abnormal. It has not been validated against a veterinary
          scale. Disease names are suspicions from appearance only, and a lab test confirms a diagnosis.
        </div>
      </details>

      <div className="actions">
        <button className="btn go" onClick={() => setMsg("Acknowledged. The watch has been told.")}>Acknowledge</button>
        <button className="btn" onClick={() => setMsg("Marked as false alarm and saved as a training label.")}>False alarm</button>
        <button
          className="btn hold" onPointerDown={startHold} onPointerUp={stop} onPointerLeave={stop} onPointerCancel={stop}
          aria-label="Hold to call the vet"
        >
          Hold to call vet<span className="fill" style={{ width: `${progress * 100}%` }} />
        </button>
      </div>
      <div className="status" role="status">{msg}</div>
    </div>
  );
}
