"use client";

import { useState } from "react";
import { GROUPS } from "@/lib/data";
import { groupStatus } from "@/lib/insight";
import styles from "./folder.module.css";

interface Props {
  selected: string;
  cams: string[];                          // pens with a camera feed
  onSelect: (groupId: string) => void;
}

// The barn as two folders: pens with a camera first and open, the rest folded away and shown offline.
export default function PenFolder({ selected, cams, onSelect }: Props) {
  const [othersOpen, setOthersOpen] = useState(false);
  const withCam = GROUPS.filter((g) => cams.includes(g.id));
  const others = GROUPS.filter((g) => !cams.includes(g.id));

  const row = (g: (typeof GROUPS)[number], cam: boolean) => {
    const st = groupStatus(g);
    return (
      <li key={g.id}>
        <button aria-pressed={selected === g.id} onClick={() => onSelect(g.id)}>
          <i className={cam ? styles[st.level] : styles.off} />
          <span className={styles.name}>{g.name}</span>
          {cam ? <span className={styles.cam}>Camera</span> : <span className={styles.offline}>Offline</span>}
          {cam && <b className="num">{st.mean === null ? "n/a" : st.mean.toFixed(1)}</b>}
        </button>
      </li>
    );
  };

  return (
    <nav className={`glass ${styles.folder}`} aria-label="Pens">
      <div className={styles.group}>
        <div className={styles.label}><span aria-hidden>▾</span>Cameras <small>{withCam.length}</small></div>
        <ul>{withCam.map((g) => row(g, true))}</ul>
      </div>
      <div className={styles.group}>
        <button className={styles.label} aria-expanded={othersOpen} onClick={() => setOthersOpen((o) => !o)}>
          <span aria-hidden>{othersOpen ? "▾" : "▸"}</span>Offline <small>{others.length}</small>
        </button>
        {othersOpen && <ul>{others.map((g) => row(g, false))}</ul>}
      </div>
    </nav>
  );
}
