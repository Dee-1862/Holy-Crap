"use client";

import { useEffect, useState } from "react";
import CameraLoop from "@/components/CameraLoop";
import CameraPulse from "@/components/CameraPulse";
import LiveCam, { LIVE_CAM, useLiveFrame } from "@/components/LiveCam";
import Clock from "@/components/Clock";
import PenDroppings from "@/components/PenDroppings";
import PenFolder from "@/components/PenFolder";
import Readout from "@/components/Readout";
import SpecimenSheet from "@/components/SpecimenSheet";
import ThemeToggle from "@/components/ThemeToggle";
import { isOnlinePen, setOnlinePens, useBarn, specimens } from "@/lib/store";
import ViewSwitch from "@/components/ViewSwitch";
import { GROUPS } from "@/lib/data";
import { barnIndex, penLevels, ranked, tone } from "@/lib/insight";
import styles from "./dashboard.module.css";

// Main dashboard. Four widgets (three from the demo stream, one from the cameras), a big camera view for the chosen pen, and the pens as folders on the side.
export default function Dashboard() {
  useBarn();
  const worst = ranked().at(-1)?.group.id ?? GROUPS[0].id;
  const [selected, setSelected] = useState(worst);
  const [openId, setOpenId] = useState<string | null>(null);
  const open = specimens().find((s) => s.id === openId) ?? null;
  const index = barnIndex();
  const pens = penLevels();
  // pens that have a camera feed, and start on one of them
  const [cams, setCams] = useState<string[]>([]);
  const frame = useLiveFrame();
  const piCam = selected === LIVE_CAM;
  useEffect(() => {
    fetch("/api/live/clips", { cache: "no-store" }).then((r) => r.json())
      .then((d: { clips: { pen: string }[] }) => {
        const pens = [...new Set(d.clips.map((c) => c.pen))].sort();
        setCams(pens);
        setOnlinePens(pens.length ? pens : null);             // pens without a camera are offline, unless no cameras are known at all
        if (pens.length) setSelected((cur) => (pens.includes(cur) ? cur : pens[0]));
      })
      .catch(() => setCams([]));
    return () => setOnlinePens(null);                       // other views count every pen
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
        <CameraPulse className={`glass ${styles.widget}`} bigClass={styles.big} />
      </section>

      <main className={styles.grid}>
        <aside className={styles.side} aria-label="Pens and readout">
          <PenFolder selected={selected} cams={cams} live={frame === undefined ? null : !!frame && frame.source === "camera"} onSelect={setSelected} />
          {!piCam && isOnlinePen(selected) && (
            <div className={`glass ${styles.readout}`}>
              <Readout key={selected} groupId={selected} />
            </div>
          )}
        </aside>
        <div className={styles.main}>
          {piCam ? <LiveCam frame={frame} /> : <CameraLoop pen={selected} />}
          {!piCam && isOnlinePen(selected) && <PenDroppings key={selected} groupId={selected} onOpen={setOpenId} />}
        </div>
      </main>

      {open && <SpecimenSheet specimen={open} onClose={() => setOpenId(null)} />}
    </div>
  );
}
