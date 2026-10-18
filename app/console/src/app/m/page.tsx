"use client";

import { useState } from "react";
import Clock from "@/components/Clock";
import SpecimenCard from "@/components/SpecimenCard";
import { SPECIMENS } from "@/lib/data";
import { ago, groupName, pct, ranked, resultOf, summary, tone } from "@/lib/insight";
import styles from "./mobile.module.css";

type Tab = "over" | "alerts" | "card";
const TABS: { id: Tab; label: string }[] = [
  { id: "over", label: "Overview" },
  { id: "alerts", label: "Alerts" },
  { id: "card", label: "Specimen" },
];

// Phone console, three tabs. Desktop version lives at /.
export default function Mobile() {
  const [tab, setTab] = useState<Tab>("over");
  const [selectedId, setSelectedId] = useState(SPECIMENS[0].id);
  const selected = SPECIMENS.find((s) => s.id === selectedId) ?? SPECIMENS[0];
  const sum = summary();
  const abnormal = SPECIMENS.filter((s) => s.type !== "healthy").length;

  const open = (id: string) => { setSelectedId(id); setTab("card"); window.scrollTo(0, 0); };

  return (
    <div className={styles.wrap}>
      <header className={styles.top}>
        <div className={styles.brand}>holy crap</div>
        <Clock />
      </header>

      <main>
        {tab === "over" && (
          <section>
            <div className={`glass ${styles.hero}`}>
              <div className="eyebrow">Barn status</div>
              <div className={styles.big}>{sum.headline}</div>
              <div className={styles.stats}>
                <div><b className="num">{sum.total}</b><span>Specimens</span></div>
                <div><b className="num tone-warn">{sum.abnormal}</b><span>Abnormal</span></div>
                <div><b className="num tone-good">{sum.mean}</b><span>Mean grade</span></div>
              </div>
            </div>
            <div className={`glass ${styles.list}`}>
              <h2 className="eyebrow">Health board</h2>
              {ranked().map(({ group, status }, i) => (
                <button
                  key={group.id} className={styles.row}
                  onClick={() => { const s = SPECIMENS.find((x) => x.group === group.id); if (s) open(s.id); }}
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
            </div>
          </section>
        )}

        {tab === "alerts" && (
          <section className={`glass ${styles.list}`}>
            <h2 className="eyebrow">Latest specimens</h2>
            {SPECIMENS.map((s) => (
              <button key={s.id} className={`${styles.row} ${styles.ev}`} onClick={() => open(s.id)}>
                <span className={`${styles.gr} num tone-${tone(s.grade)}`}>{s.grade}</span>
                <span>
                  <div className={styles.nm}>{resultOf(s)}</div>
                  <div className={styles.sb}>{groupName(s.group)}, {ago(s.minsAgo)}</div>
                </span>
                <span className={`${styles.sb} num`}>{pct(s.probs[s.type])}%</span>
              </button>
            ))}
          </section>
        )}

        {tab === "card" && (
          <section className={`glass ${styles.card}`}>
            <SpecimenCard key={selected.id} specimen={selected} />
          </section>
        )}
      </main>

      <nav className={`glass ${styles.nav}`} role="tablist" aria-label="Sections">
        {TABS.map((t) => (
          <button key={t.id} role="tab" aria-selected={tab === t.id} onClick={() => setTab(t.id)}>
            {t.label}{t.id === "alerts" && <span className={styles.badge}>{abnormal}</span>}
          </button>
        ))}
      </nav>
    </div>
  );
}
