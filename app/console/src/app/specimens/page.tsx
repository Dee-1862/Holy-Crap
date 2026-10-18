"use client";

import { useState } from "react";
import Clock from "@/components/Clock";
import SpecimenSheet from "@/components/SpecimenSheet";
import ThemeToggle from "@/components/ThemeToggle";
import ViewSwitch from "@/components/ViewSwitch";
import { SPECIMENS } from "@/lib/data";
import { ago, groupName, pct, ranked, resultOf, summary, tone } from "@/lib/insight";
import styles from "./page.module.css";

const SHOWN = 5;

// Specimen list. Grouped lists like iOS Settings, and the detail opens as a sheet so only one
// thing is on screen at a time. The dashboard lives at / and the phone version at /m.
export default function Specimens() {
  const [openId, setOpenId] = useState<string | null>(null);
  const [filter, setFilter] = useState<string | null>(null);
  const [all, setAll] = useState(false);
  const sum = summary();
  const board = ranked();
  const rows = SPECIMENS.filter((s) => !filter || s.group === filter);
  const shown = all ? rows : rows.slice(0, SHOWN);
  const open = SPECIMENS.find((s) => s.id === openId) ?? null;


  return (
    <div className={styles.shell}>
      <header className={styles.top}>
        <h1 className="title">Specimens</h1>
        <ViewSwitch current="specimens" />
        <span className={styles.grow} />
        <ThemeToggle />
        <Clock />
      </header>

      <section className={`glass ${styles.status}`} aria-live="polite">
        <div className={`eyebrow ${styles.state}`}>
          <i className={sum.hot.length ? styles.alert : styles.calm} />
          {sum.hot.length ? "Needs attention" : "All clear"}
        </div>
        <h2 className={styles.headline}>{sum.headline}</h2>
        <p className={`sub ${styles.detail}`}>{sum.detail}</p>
        <dl className={styles.stats}>
          <div><dd className="num">{sum.total}</dd><dt>Specimens</dt></div>
          <div><dd className="num">{sum.abnormal}</dd><dt>Abnormal</dt></div>
          <div><dd className="num">{sum.mean}</dd><dt>Mean grade</dt></div>
        </dl>
      </section>

      <div className={styles.columns}>
        <div>
          <h3 className={`eyebrow list-h`}>Health board</h3>
          <div className="list">
            {board.map(({ group, status }, i) => (
              <button
                key={group.id} className={`row ${styles.board}`} aria-pressed={filter === group.id}
                onClick={() => { setFilter(filter === group.id ? null : group.id); setAll(false); }}
              >
                <span className={`${styles.rk} num`}>{i + 1}</span>
                <span className="headline">{group.name}</span>
                <span className={`${styles.gr} num ${status.mean === null ? "" : `tone-${status.level}`}`}>
                  {status.mean === null ? "n/a" : status.mean.toFixed(1)}
                </span>
              </button>
            ))}
          </div>
        </div>

        <div>
          <h3 className={`eyebrow list-h`}>{filter ? groupName(filter) : "Latest"}</h3>
          <div className="list">
            {shown.map((s) => (
              <button key={s.id} className={`row ${styles.item}`} onClick={() => setOpenId(s.id)}>
                <span className={`${styles.grade} num tone-${tone(s.grade)}`}>{s.grade}</span>
                <span className={styles.what}>
                  <b>{resultOf(s)}</b>
                  <small>{groupName(s.group)}, {ago(s.minsAgo)}</small>
                </span>
                <span className={`${styles.conf} num`}>{pct(s.probs[s.type])}%</span>
              </button>
            ))}
            {rows.length > SHOWN && (
              <button className={`row ${styles.more}`} onClick={() => setAll(!all)}>{all ? "Show fewer" : `Show all ${rows.length}`}</button>
            )}
          </div>
        </div>
      </div>

      {open && <SpecimenSheet specimen={open} onClose={() => setOpenId(null)} />}
    </div>
  );
}
