"use client";

import { useState } from "react";
import Clock from "@/components/Clock";
import SpecimenCard from "@/components/SpecimenCard";
import { SPECIMENS } from "@/lib/data";
import { ago, groupName, pct, ranked, resultOf, summary, tone } from "@/lib/insight";
import styles from "./page.module.css";

// Specimen list view. The dashboard lives at / and the phone version at /m.
export default function Specimens() {
  const [selectedId, setSelectedId] = useState(SPECIMENS[0].id);
  const [filter, setFilter] = useState<string | null>(null);
  const selected = SPECIMENS.find((s) => s.id === selectedId) ?? SPECIMENS[0];
  const sum = summary();
  const board = ranked();
  const rows = SPECIMENS.filter((s) => !filter || s.group === filter);

  return (
    <div className={styles.shell}>
      <header className={styles.top}>
        <div className={styles.brand}>holy crap</div>
        <span className="pill"><i />Demo farm</span>
        <span className="pill">Pi 01 online</span>
        <span className={styles.grow} />
        <Clock />
      </header>

      <aside className={`glass ${styles.board}`} aria-label="Health board">
        <h2 className="eyebrow">Health board</h2>
        {board.map(({ group, status }, i) => (
          <button
            key={group.id} className={styles.row} aria-pressed={filter === group.id}
            onClick={() => setFilter(filter === group.id ? null : group.id)}
          >
            <span className={`${styles.rk} num`}>{i + 1}</span>
            <span>
              <div className={styles.nm}>{group.name}</div>
              <div className={styles.sb}>{group.n} birds, {status.bad} abnormal</div>
            </span>
            <span className={`${styles.gr} num ${status.mean === null ? "" : `tone-${tone(Math.round(status.mean))}`}`}>
              {status.mean === null ? "n/a" : status.mean.toFixed(1)}
            </span>
          </button>
        ))}
      </aside>

      <main>
        <section className={`glass ${styles.summary}`} aria-live="polite">
          <div className="eyebrow">Barn status</div>
          <div className={styles.big}>{sum.headline}</div>
          <div className={styles.stats}>
            <div><b className="num">{sum.total}</b><span>Specimens today</span></div>
            <div><b className="num tone-warn">{sum.abnormal}</b><span>Abnormal</span></div>
            <div><b className="num tone-good">{sum.mean}</b><span>Mean grade</span></div>
          </div>
        </section>

        {sum.hot.length > 0 && (
          <div className={`glass ${styles.banner}`} role="status">
            <b>{sum.hot.join(", ")}</b> has 3 or more abnormal specimens in 15 minutes. Check on site and call the vet if it holds up.
          </div>
        )}

        <section className={`glass ${styles.feed}`}>
          <h2 className="eyebrow">Latest specimens</h2>
          <table className={styles.table}>
            <thead><tr><th>Time</th><th>Group</th><th>Grade</th><th>Result</th><th>Conf.</th></tr></thead>
            <tbody>
              {rows.map((s) => (
                <tr
                  key={s.id} className={styles.ev} tabIndex={0} aria-selected={s.id === selectedId}
                  onClick={() => setSelectedId(s.id)}
                  onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setSelectedId(s.id); } }}
                >
                  <td className="num">{ago(s.minsAgo)}</td>
                  <td>{groupName(s.group)}</td>
                  <td className={`${styles.grade} num tone-${tone(s.grade)}`}>{s.grade}</td>
                  <td>{resultOf(s)}</td>
                  <td className="num">{pct(s.probs[s.type])}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      </main>

      <aside className={`glass ${styles.card}`} aria-label="Specimen detail">
        <SpecimenCard key={selected.id} specimen={selected} />
      </aside>
    </div>
  );
}
