"use client";

import { useState } from "react";
import Clock from "@/components/Clock";
import PenDroppings from "@/components/PenDroppings";
import Readout from "@/components/Readout";
import SiteMap, { type MapFilter } from "@/components/SiteMap";
import SpecimenSheet from "@/components/SpecimenSheet";
import ThemeToggle from "@/components/ThemeToggle";
import { useBarn } from "@/lib/store";
import ViewSwitch from "@/components/ViewSwitch";
import { GROUPS, SPECIMENS } from "@/lib/data";
import { barnIndex, penLevels, ranked, tone } from "@/lib/insight";
import styles from "./dashboard.module.css";

const FILTERS: { id: MapFilter; label: string }[] = [
  { id: "all", label: "All" },
  { id: "watch", label: "Needs a look" },
  { id: "action", label: "Urgent" },
];

// Main dashboard. Three widgets, the barn floor plan, and the readout for the chosen pen.
export default function Dashboard() {
  useBarn();
  const worst = ranked().at(-1)?.group.id ?? GROUPS[0].id;
  const [selected, setSelected] = useState(worst);
  const [filter, setFilter] = useState<MapFilter>("all");
  const [openId, setOpenId] = useState<string | null>(null);
  const open = SPECIMENS.find((s) => s.id === openId) ?? null;
  const index = barnIndex();
  const pens = penLevels();

  return (
    <div className={styles.shell}>
      <header className={styles.top}>
        <h1 className="title">Barn</h1>
        <ViewSwitch current="map" />
        <span className={styles.grow} />
        <span className="pill"><i />Demo data</span>
        <ThemeToggle />
        <Clock />
      </header>

      <section className={styles.widgets} aria-label="Summary">
        <div className={`glass ${styles.widget}`}>
          <span className="eyebrow">Barn health</span>
          <b className={`${styles.big} num tone-${tone(Math.round(index / 10))}`}>{index}<small>/100</small></b>
          <span className="foot">Average grade, last 15 minutes</span>
        </div>
        <div className={`glass ${styles.widget}`}>
          <span className="eyebrow">Healthy pens</span>
          <b className={`${styles.big} num tone-good`}>{pens.healthy.length}<small>of {pens.total}</small></b>
          <span className="foot">Normal droppings</span>
        </div>
        <div className={`glass ${styles.widget}`}>
          <span className="eyebrow">Need attention</span>
          <b className={`${styles.big} num ${pens.look.some((x) => x.status.level === "bad") ? "tone-bad" : pens.look.length ? "tone-warn" : "tone-good"}`}>{pens.look.length}</b>
          <span className="foot">
            {pens.look.length ? pens.look.slice(0, 3).map((x) => x.group.name).join(", ") : "Nothing right now"}
          </span>
        </div>
      </section>

      <main className={styles.grid}>
        <div className={styles.left}>
        <section className={`glass ${styles.map}`} aria-label="Barn site map">
          <div className={styles.mapHead}>
            <h2 className="headline">Floor plan</h2>
            <div className="seg" role="group" aria-label="Filter pens">
              {FILTERS.map((f) => (
                <button key={f.id} aria-pressed={filter === f.id} onClick={() => setFilter(f.id)}>{f.label}</button>
              ))}
            </div>
          </div>
          <div className={styles.plan}>
            <SiteMap selected={selected} filter={filter} onSelect={setSelected} />
          </div>
          <p className={`foot ${styles.legend}`}>
            <span><i style={{ background: "var(--good)" }} />Healthy</span>
            <span><i style={{ background: "var(--warn)" }} />Needs a look</span>
            <span><i style={{ background: "var(--bad)" }} />Urgent</span>
          </p>
        </section>
        <PenDroppings key={selected} groupId={selected} onOpen={setOpenId} />
        </div>

        <aside className={`glass ${styles.side}`} aria-label="Pen readout">
          <Readout key={selected} groupId={selected} />
        </aside>
      </main>

      {open && <SpecimenSheet specimen={open} onClose={() => setOpenId(null)} />}
    </div>
  );
}
