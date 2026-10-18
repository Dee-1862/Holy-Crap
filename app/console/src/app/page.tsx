"use client";

import Link from "next/link";
import { useState } from "react";
import Clock from "@/components/Clock";
import Readout from "@/components/Readout";
import SiteMap, { type MapFilter } from "@/components/SiteMap";
import ThemeToggle from "@/components/ThemeToggle";
import Ticker from "@/components/Ticker";
import { GROUPS } from "@/lib/data";
import { barnIndex, openAlerts, ranked, tone } from "@/lib/insight";
import styles from "./dashboard.module.css";

const FILTERS: { id: MapFilter; label: string }[] = [
  { id: "all", label: "All" },
  { id: "watch", label: "Watch and up" },
  { id: "action", label: "Needs action" },
];

// Main dashboard. Barn floor plan on the left, readout for the chosen group on the right.
export default function Dashboard() {
  const worst = ranked().at(-1)?.group.id ?? GROUPS[0].id;
  const [selected, setSelected] = useState(worst);
  const [filter, setFilter] = useState<MapFilter>("all");
  const index = barnIndex();

  return (
    <div className={styles.shell}>
      <header className={styles.top}>
        <div className={styles.brand}>holy crap</div>
        <nav className={styles.tabs} aria-label="Views">
          <span aria-current="page">Site map</span>
          <Link href="/specimens">Specimens</Link>
          <Link href="/m">Mobile</Link>
        </nav>
        <div className={styles.grow} />
        <div className={styles.kpis}>
          <div><b className={`num tone-${tone(Math.round(index / 10))}`}>{index}</b><span>Barn index</span></div>
          <div><b className="num">{GROUPS.length}</b><span>Groups</span></div>
          <div><b className="num tone-bad">{openAlerts()}</b><span>Open alerts</span></div>
        </div>
        <span className="pill"><i />Demo data</span>
        <ThemeToggle />
        <Clock />
      </header>

      <main className={styles.grid}>
        <section className={`glass ${styles.map}`} aria-label="Barn site map">
          <div className={styles.mapHead}>
            <span className="eyebrow">Barn site map</span>
            <span className="eyebrow">Demo farm</span>
          </div>
          <div className={styles.chips} role="group" aria-label="Filter pens">
            {FILTERS.map((f) => (
              <button key={f.id} aria-pressed={filter === f.id} onClick={() => setFilter(f.id)}>{f.label}</button>
            ))}
          </div>
          <SiteMap selected={selected} filter={filter} onSelect={setSelected} />
          <div className={styles.legend}>
            <span><i style={{ background: "var(--good)" }} />Healthy</span>
            <span><i style={{ background: "var(--warn)" }} />Normal but watch</span>
            <span><i style={{ background: "var(--bad)" }} />Action required</span>
            <span className={styles.hint}>Dots are birds. Pins are specimens from the last hour.</span>
          </div>
        </section>

        <aside className={`glass ${styles.side}`} aria-label="Group readout">
          <Readout key={selected} groupId={selected} />
        </aside>
      </main>

      <Ticker />
    </div>
  );
}
