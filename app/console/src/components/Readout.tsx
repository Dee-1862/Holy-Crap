"use client";

import { GROUPS } from "@/lib/data";
import { nextStep, radarOf } from "@/lib/insight";
import { lastVet, specimens } from "@/lib/store";
import ChecksList from "./ChecksList";

// Side panel for the selected pen. The plan and the radar.
export default function Readout({ groupId }: { groupId: string }) {
  const group = GROUPS.find((g) => g.id === groupId) ?? GROUPS[0];
  const list = specimens().filter((s) => s.group === group.id);
  const mine = radarOf(group.id);
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

      <ChecksList values={mine} title="What we checked in this pen" />

    </div>
  );
}
