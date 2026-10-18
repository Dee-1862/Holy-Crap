"use client";

import { GROUPS, SPECIMENS } from "@/lib/data";
import { ago, pct, resultOf, tone } from "@/lib/insight";
import { stateOf } from "@/lib/store";

// Short list of the droppings found in one pen. Tapping a row opens the specimen sheet.
export default function PenDroppings({ groupId, onOpen }: { groupId: string; onOpen: (specimenId: string) => void }) {
  const group = GROUPS.find((g) => g.id === groupId) ?? GROUPS[0];
  const list = SPECIMENS.filter((s) => s.group === group.id);

  return (
    <section className="glass list" aria-label={`Droppings in ${group.name}`}>
      <h3 className="eyebrow list-h" style={{ margin: 0 }}>Droppings in {group.name}</h3>
      {list.map((s) => (
        <button key={s.id} className="row" style={{ gridTemplateColumns: "34px 1fr auto" }} onClick={() => onOpen(s.id)}>
          <b className={`num tone-${stateOf(s.id) === "normal" ? "" : tone(s.grade)}`} style={{ fontSize: 22, fontWeight: 500, textAlign: "center" }}>{s.grade}</b>
          <span>
            <b style={{ display: "block", fontWeight: 600, fontSize: 16 }}>{resultOf(s)}</b>
            <small className="foot">{ago(s.minsAgo)}{stateOf(s.id) === "checking" ? ", being checked" : stateOf(s.id) === "normal" ? ", marked normal" : ""}</small>
          </span>
          <span className="foot num">{pct(s.probs[s.type])}%</span>
        </button>
      ))}
    </section>
  );
}
