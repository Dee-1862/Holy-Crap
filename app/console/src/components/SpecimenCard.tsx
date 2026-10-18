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
        </div>
      </div>

      <div className={`next ${next.level}`}>{next.head}<small>{next.note}</small></div>

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
