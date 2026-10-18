"use client";

import { useEffect, useState } from "react";
import CameraLoop from "@/components/CameraLoop";
import Clock from "@/components/Clock";
import PenDroppings from "@/components/PenDroppings";
import PenFolder from "@/components/PenFolder";
import Readout from "@/components/Readout";
import SpecimenSheet from "@/components/SpecimenSheet";
import ThemeToggle from "@/components/ThemeToggle";
import { useBarn } from "@/lib/store";
import ViewSwitch from "@/components/ViewSwitch";
import { GROUPS, SPECIMENS } from "@/lib/data";
import { barnIndex, penLevels, ranked, tone } from "@/lib/insight";
import styles from "./dashboard.module.css";

// Main dashboard. Three widgets, a big camera view for the chosen pen, and the pens as folders on the side.
export default function Dashboard() {
  useBarn();
  const worst = ranked().at(-1)?.group.id ?? GROUPS[0].id;
  const [selected, setSelected] = useState(worst);
  const [openId, setOpenId] = useState<string | null>(null);
  const open = SPECIMENS.find((s) => s.id === openId) ?? null;
  const index = barnIndex();
  const pens = penLevels();
  // pens that have a camera feed, and start on one of them
  const [cams, setCams] = useState<string[]>([]);
  useEffect(() => {
    fetch("/api/live/clips", { cache: "no-store" }).then((r) => r.json())
      .then((d: { clips: { pen: string }[] }) => {
        const pens = [...new Set(d.clips.map((c) => c.pen))].sort();
        setCams(pens);
        if (pens.length) setSelected((cur) => (pens.includes(cur) ? cur : pens[0]));
      })
      .catch(() => setCams([]));
  }, []);

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
        <aside className={styles.side} aria-label="Pens and readout">
          <PenFolder selected={selected} cams={cams} onSelect={setSelected} />
          <div className={`glass ${styles.readout}`}>
            <Readout key={selected} groupId={selected} />
          </div>
        </aside>
        <div className={styles.main}>
          <CameraLoop pen={selected} />
          <PenDroppings key={selected} groupId={selected} onOpen={setOpenId} />
        </div>
      </main>

      {open && <SpecimenSheet specimen={open} onClose={() => setOpenId(null)} />}
    </div>
  );
}
