"use client";

import { GROUPS, SPECIMENS } from "@/lib/data";
import { SUB_AXES, groupStatus, nextStep, radarOf } from "@/lib/insight";
import { lastVet } from "@/lib/store";
import Radar from "./Radar";

const COLOR = { good: "var(--good)", warn: "var(--warn)", bad: "var(--bad)" } as const;

// Side panel for the selected pen. The plan and the radar.
export default function Readout({ groupId }: { groupId: string }) {
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

      {lastVet(group.id) && (
        <p className="foot" style={{ margin: "0 0 8px" }}>
          <span style={{ display: "inline-block", width: 7, height: 7, borderRadius: "50%", background: "var(--good)", marginRight: 7 }} />
          Vet requested {Math.max(0, Math.round((Date.now() - lastVet(group.id)!.ts) / 60000))} min ago
        </p>
      )}

      <div className="ro-radar"><Radar group={mine} barn={radarOf()} color={COLOR[status.level]} /></div>
      <div className="ro-legend">
        <span><i style={{ background: COLOR[status.level] }} />This pen</span>
        <span><i className="dash" />Barn average</span>
      </div>
      <p className="ro-weak">Weakest signal is {SUB_AXES[weakest].label.toLowerCase()} at {mine[weakest].toFixed(1)} of 10</p>

    </div>
  );
}
