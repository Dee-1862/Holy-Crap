"use client";

import { useEffect, useState } from "react";
import CameraLoop from "@/components/CameraLoop";
import CameraPulse from "@/components/CameraPulse";
import LiveCam, { LIVE_CAM, useLiveFrame } from "@/components/LiveCam";
import Clock from "@/components/Clock";
import PenActions from "@/components/PenActions";
import PenFolder from "@/components/PenFolder";
import Readout from "@/components/Readout";
import SpecimenSheet from "@/components/SpecimenSheet";
import ThemeToggle from "@/components/ThemeToggle";
import { isOnlinePen, setOnlinePens, useBarn, specimens } from "@/lib/store";
import ViewSwitch from "@/components/ViewSwitch";
import { GROUPS } from "@/lib/data";
import { barnIndex, penLevels, ranked, tone } from "@/lib/insight";
import styles from "./dashboard.module.css";

// Main dashboard. Four widgets from the cameras, a big camera view for the chosen pen, and the pens as folders on the side.
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
  const piCam = selected === LIVE_CAM;
  const frame = useLiveFrame(piCam);
  useEffect(() => {
    let active = true;
    const known = new Set(GROUPS.map((g) => g.id));
    fetch("/api/live/clips", { cache: "no-store" }).then((r) => r.json())
      .then((d: unknown) => {
        if (!active) return;
        const clips = typeof d === "object" && d !== null && "clips" in d && Array.isArray(d.clips) ? d.clips : [];
        const pens = [...new Set(clips.flatMap((clip) => {
          if (typeof clip !== "object" || clip === null || !("pen" in clip) || typeof clip.pen !== "string") return [];
          return known.has(clip.pen) ? [clip.pen] : [];
        }))].sort();
        setCams(pens);
        setOnlinePens(pens.length ? pens : null);             // pens without a camera are offline, unless no cameras are known at all
        if (pens.length) setSelected((cur) => (pens.includes(cur) ? cur : pens[0]));
      })
      .catch(() => {
        if (!active) return;
        setCams([]);
        setOnlinePens([]);
      });
    return () => {
      active = false;
      setOnlinePens(null);                                  // other views count every pen
    };
  }, []);

  return (
    <div className={styles.shell}>
      <header className={styles.top}>
        <h1 className="title">Barn</h1>
        <ViewSwitch current="map" />
        <span className={styles.grow} />
        <ThemeToggle />
        <Clock />
      </header>

      <section className={styles.widgets} aria-label="Summary">
        <div className={`glass ${styles.widget}`}>
          <span className="eyebrow">Barn health</span>
          <b className={`${styles.big} num tone-${tone(Math.round(index / 10))}`}>{index}<small>/100</small></b>
          <span className="foot">Average dropping score from the cameras</span>
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
              <PenActions key={`act-${selected}`} groupId={selected} onOpen={setOpenId} />
            </div>
          )}
        </aside>
        <div className={styles.main}>
          {piCam ? <LiveCam frame={frame} /> : <CameraLoop pen={selected} />}
        </div>
      </main>

      {open && <SpecimenSheet specimen={open} onClose={() => setOpenId(null)} />}
    </div>
  );
}
