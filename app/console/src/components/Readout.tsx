"use client";

import { GROUPS, SPECIMENS } from "@/lib/data";
import { SUB_AXES, ago, groupStatus, nextStep, pct, radarOf, resultOf, tone } from "@/lib/insight";
import Radar from "./Radar";

const COLOR = { good: "var(--good)", warn: "var(--warn)", bad: "var(--bad)" } as const;

// Side panel for the selected pen. Plan, radar and a short list. Tapping a row opens the specimen sheet.
export default function Readout({ groupId, onOpen }: { groupId: string; onOpen: (specimenId: string) => void }) {
  const group = GROUPS.find((g) => g.id === groupId) ?? GROUPS[0];
  const status = groupStatus(group);
  const list = SPECIMENS.filter((s) => s.group === group.id);
  const mine = radarOf(group.id);
  const weakest = mine.indexOf(Math.min(...mine));
  const plan = nextStep(list[0]);

  return (
    <div className="readout">
      <div className="ro-head">
        <span className="eyebrow">{group.name}</span>
        <span className="eyebrow">{group.n} birds</span>
      </div>

      <div className={`next ${plan.level}`} style={{ margin: "8px 0 8px" }}><b />{plan.head}<small>{plan.note}</small></div>

      <div className="ro-radar"><Radar group={mine} barn={radarOf()} color={COLOR[status.level]} /></div>
      <div className="ro-legend">
        <span><i style={{ background: COLOR[status.level] }} />This pen</span>
        <span><i className="dash" />Barn average</span>
      </div>
      <p className="ro-weak">Weakest signal is {SUB_AXES[weakest].label.toLowerCase()} at {mine[weakest].toFixed(1)} of 10</p>

      <h3 className="eyebrow list-h" style={{ padding: "18px 4px 8px" }}>Specimens</h3>
      <div className="list on-glass">
        {list.map((s) => (
          <button key={s.id} className="row" style={{ gridTemplateColumns: "34px 1fr auto" }} onClick={() => onOpen(s.id)}>
            <b className={`num tone-${tone(s.grade)}`} style={{ fontSize: 22, textAlign: "center" }}>{s.grade}</b>
            <span><b style={{ display: "block", fontWeight: 600, fontSize: 15 }}>{resultOf(s)}</b><small className="foot">{ago(s.minsAgo)}</small></span>
            <span className="foot num">{pct(s.probs[s.type])}%</span>
          </button>
        ))}
      </div>
    </div>
  );
}
