"use client";

import { useState } from "react";
import Clock from "@/components/Clock";
import Readout from "@/components/Readout";
import SpecimenSheet from "@/components/SpecimenSheet";
import SiteMap, { type MapFilter } from "@/components/SiteMap";
import ThemeToggle from "@/components/ThemeToggle";
import ViewSwitch from "@/components/ViewSwitch";
import { GROUPS, SPECIMENS } from "@/lib/data";
import { barnIndex, openAlerts, ranked, tone } from "@/lib/insight";
import styles from "./dashboard.module.css";

const FILTERS: { id: MapFilter; label: string }[] = [
  { id: "all", label: "All" },
  { id: "watch", label: "Watch" },
  { id: "action", label: "Action" },
];

// Main dashboard. Three widgets, the barn floor plan, and the readout for the chosen pen.
export default function Dashboard() {
  const worst = ranked().at(-1)?.group.id ?? GROUPS[0].id;
  const [selected, setSelected] = useState(worst);
  const [filter, setFilter] = useState<MapFilter>("all");
  const [openId, setOpenId] = useState<string | null>(null);
  const open = SPECIMENS.find((s) => s.id === openId) ?? null;
  const index = barnIndex();
  const alerts = openAlerts();

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
          <span className="eyebrow">Barn index</span>
          <b className={`${styles.big} num tone-${tone(Math.round(index / 10))}`}>{index}</b>
          <span className="foot">Mean grade of the last 15 minutes, out of 100</span>
        </div>
        <div className={`glass ${styles.widget}`}>
          <span className="eyebrow">Pens</span>
          <b className={`${styles.big} num`}>{GROUPS.length}</b>
          <span className="foot">Two rows of three</span>
        </div>
        <div className={`glass ${styles.widget}`}>
          <span className="eyebrow">Open alerts</span>
          <b className={`${styles.big} num ${alerts ? "tone-bad" : "tone-good"}`}>{alerts}</b>
          <span className="foot">{alerts ? "Pens that need a look" : "Nothing needs a look"}</span>
        </div>
      </section>

      <main className={styles.grid}>
        <section className={`glass ${styles.map}`} aria-label="Barn site map">
          <div className={styles.mapHead}>
            <h2 className="headline">Floor plan</h2>
            <div className="seg" role="group" aria-label="Filter pens">
              {FILTERS.map((f) => (
                <button key={f.id} aria-pressed={filter === f.id} onClick={() => setFilter(f.id)}>{f.label}</button>
              ))}
            </div>
          </div>
          <SiteMap selected={selected} filter={filter} onSelect={setSelected} />
          <p className={`foot ${styles.legend}`}>
            <span><i style={{ background: "var(--good)" }} />Healthy</span>
            <span><i style={{ background: "var(--warn)" }} />Watch</span>
            <span><i style={{ background: "var(--bad)" }} />Action</span>
          </p>
        </section>

        <aside className={`glass ${styles.side}`} aria-label="Pen readout">
          <Readout key={selected} groupId={selected} onOpen={setOpenId} />
        </aside>
      </main>

      {open && <SpecimenSheet specimen={open} onClose={() => setOpenId(null)} />}
    </div>
  );
}
