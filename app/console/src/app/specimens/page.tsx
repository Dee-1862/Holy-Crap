"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import Clock from "@/components/Clock";
import SpecimenCard from "@/components/SpecimenCard";
import ThemeToggle from "@/components/ThemeToggle";
import { SPECIMENS } from "@/lib/data";
import { ago, groupName, pct, ranked, resultOf, summary, tone } from "@/lib/insight";
import styles from "./page.module.css";

const SHOWN = 5;

// Specimen list view. The detail card opens in a drawer so only one thing is on screen at a time.
// The dashboard lives at / and the phone version at /m.
export default function Specimens() {
  const [openId, setOpenId] = useState<string | null>(null);
  const [filter, setFilter] = useState<string | null>(null);
  const [all, setAll] = useState(false);
  const sum = summary();
  const board = ranked();
  const rows = SPECIMENS.filter((s) => !filter || s.group === filter);
  const shown = all ? rows : rows.slice(0, SHOWN);
  const open = SPECIMENS.find((s) => s.id === openId) ?? null;

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpenId(null); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <div className={styles.shell}>
      <header className={styles.top}>
        <div className={styles.brand}>holy crap</div>
        <nav className={styles.nav} aria-label="Views">
          <Link href="/">Site map</Link>
          <span aria-current="page">Specimens</span>
          <Link href="/m">Mobile</Link>
        </nav>
        <span className={styles.grow} />
        <ThemeToggle />
        <Clock />
      </header>

      <div className={styles.grid}>
        <aside className={`glass ${styles.board}`} aria-label="Health board">
          <h2 className="eyebrow">Health board</h2>
          {board.map(({ group, status }, i) => (
            <button
              key={group.id} className={styles.row} aria-pressed={filter === group.id}
              onClick={() => { setFilter(filter === group.id ? null : group.id); setAll(false); }}
            >
              <span className={`${styles.rk} num`}>{i + 1}</span>
              <span className={styles.nm}>{group.name}</span>
              <span className={`${styles.gr} num ${status.mean === null ? "" : `tone-${tone(Math.round(status.mean))}`}`}>
                {status.mean === null ? "n/a" : status.mean.toFixed(1)}
              </span>
            </button>
          ))}
        </aside>

        <main className={styles.main}>
          <section className={`glass ${styles.status}`} aria-live="polite">
            <div className={`eyebrow ${styles.state}`}>
              <i className={sum.hot.length ? styles.alert : styles.calm} />
              {sum.hot.length ? "Needs attention" : "All clear"}
            </div>
            <h1 className={styles.headline}>{sum.headline}</h1>
            <p className={styles.detail}>{sum.detail}</p>
            <div className={styles.stats}>
              <div><b className="num">{sum.total}</b><span>Specimens</span></div>
              <div><b className="num">{sum.abnormal}</b><span>Abnormal</span></div>
              <div><b className="num">{sum.mean}</b><span>Mean grade</span></div>
            </div>
          </section>

          <section className={`glass ${styles.list}`}>
            <h2 className="eyebrow">{filter ? groupName(filter) : "Latest specimens"}</h2>
            {shown.map((s) => (
              <button key={s.id} className={styles.item} onClick={() => setOpenId(s.id)}>
                <span className={`${styles.grade} num tone-${tone(s.grade)}`}>{s.grade}</span>
                <span className={styles.what}>
                  <b>{resultOf(s)}</b>
                  <small>{groupName(s.group)}, {ago(s.minsAgo)}</small>
                </span>
                <span className={`${styles.conf} num`}>{pct(s.probs[s.type])}%</span>
              </button>
            ))}
            {rows.length > SHOWN && (
              <button className={styles.more} onClick={() => setAll(!all)}>{all ? "Show fewer" : `Show all ${rows.length}`}</button>
            )}
          </section>
        </main>
      </div>

      {open && (
        <>
          <button className={styles.scrim} aria-label="Close specimen" onClick={() => setOpenId(null)} />
          <aside className={`glass ${styles.drawer}`} aria-label="Specimen detail">
            <button className={styles.close} onClick={() => setOpenId(null)} aria-label="Close">Close</button>
            <SpecimenCard key={open.id} specimen={open} />
          </aside>
        </>
      )}
    </div>
  );
}
