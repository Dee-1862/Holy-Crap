"use client";

import { useState } from "react";
import { GROUPS, SPECIMENS } from "@/lib/data";
import { SUB_AXES, ago, groupStatus, nextStep, radarOf, resultOf } from "@/lib/insight";
import Radar from "./Radar";
import SpecimenCard from "./SpecimenCard";

type Tab = "latest" | "history";
const COLOR = { good: "var(--good)", warn: "var(--warn)", bad: "var(--bad)" } as const;

// Side panel for the selected group: radar, plan and the specimens behind it.
export default function Readout({ groupId }: { groupId: string }) {
  const [tab, setTab] = useState<Tab>("latest");
  const [pick, setPick] = useState(0);
  const group = GROUPS.find((g) => g.id === groupId) ?? GROUPS[0];
  const status = groupStatus(group);
  const list = SPECIMENS.filter((s) => s.group === group.id);
  const current = list[Math.min(pick, list.length - 1)];
  const mine = radarOf(group.id);
  const weakest = mine.indexOf(Math.min(...mine));
  const plan = nextStep(list[0]);

  return (
    <div className="readout">
      <div className="ro-head">
        <span className="eyebrow">Group readout</span>
        <span className="eyebrow">{group.name}, {group.n} birds</span>
      </div>

      <Radar group={mine} barn={radarOf()} color={COLOR[status.level]} />
      <div className="ro-legend">
        <span><i style={{ background: COLOR[status.level] }} />This group</span>
        <span><i className="dash" />Barn average</span>
      </div>
      <p className="ro-weak">Weakest signal: <b>{SUB_AXES[weakest].label}</b> at {mine[weakest].toFixed(1)} out of 10</p>

      <span className="eyebrow sec">Recommended plan</span>
      <div className={`next ${plan.level}`}><div>{plan.head}<small>{plan.note}</small></div></div>

      <div className="ro-tabs" role="tablist" aria-label="Readout sections">
        {(["latest", "history"] as Tab[]).map((t) => (
          <button key={t} role="tab" aria-selected={tab === t} onClick={() => setTab(t)}>{t === "latest" ? "Specimen" : "History"}</button>
        ))}
      </div>

      {tab === "latest" && (
        <>
          {list.length > 1 && (
            <div className="ro-pick" role="group" aria-label="Choose specimen">
              {list.map((s, i) => (
                <button key={s.id} aria-pressed={i === pick} onClick={() => setPick(i)}>{s.id.slice(2)}</button>
              ))}
            </div>
          )}
          <SpecimenCard key={current.id} specimen={current} />
        </>
      )}

      {tab === "history" && (
        <ul className="ro-hist">
          {list.map((s) => (
            <li key={s.id}>
              <b className={`num tone-${s.grade >= 8 ? "good" : s.grade >= 5 ? "warn" : "bad"}`}>{s.grade}</b>
              <span>{resultOf(s)}<small>{ago(s.minsAgo)}</small></span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
