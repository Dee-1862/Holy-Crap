"use client";

import { GROUPS } from "@/lib/data";
import { nextStep, radarOf } from "@/lib/insight";
import { getSpecimens, lastVet, specimens } from "@/lib/store";
import ChecksList from "./ChecksList";

// Side panel for the selected pen. The plan and the radar.
export default function Readout({ groupId }: { groupId: string }) {
  const group = GROUPS.find((g) => g.id === groupId);

  // A stale clip manifest can refer to a pen that is no longer in the configured barn.
  // Do not silently show the first pen's data for that camera.
  if (!group) {
    return (
      <div className="readout">
        <div className="ro-head"><span className="eyebrow">Unknown pen</span></div>
        <div className="next" style={{ margin: "8px 0" }}>
          Pen data unavailable
          <small>This camera is not linked to a configured pen.</small>
        </div>
      </div>
    );
  }

  const all = specimens().filter((s) => s.group === group.id);
  const list = getSpecimens().filter((s) => s.group === group.id);
  const mine = radarOf(group.id);
  const latest = list[0];
  const plan = latest ? nextStep(latest) : null;

  return (
    <div className="readout">
      <div className="ro-head">
        <span className="eyebrow">{group.name}</span>
        <span className="eyebrow">{group.n} birds</span>
      </div>

      {plan ? (
        <div className={`next ${plan.level}`} style={{ margin: "8px 0 8px" }}><b />{plan.head}<small>{plan.note}</small></div>
      ) : (
        <div className="next" style={{ margin: "8px 0" }}>
          {all.length ? "No active specimens" : "No recent specimens"}
          <small>{all.length ? "Recent specimens were marked normal. Waiting for the next detection." : "Waiting for the next detection from this camera."}</small>
        </div>
      )}

      {lastVet(group.id) && (
        <p className="foot" style={{ margin: "0 0 8px" }}>
          <span style={{ display: "inline-block", width: 7, height: 7, borderRadius: "50%", background: "var(--good)", marginRight: 7 }} />
          Vet requested {Math.max(0, Math.round((Date.now() - lastVet(group.id)!.ts) / 60000))} min ago
        </p>
      )}

      {latest && <ChecksList values={mine} title="What we checked in this pen" />}

    </div>
  );
}
