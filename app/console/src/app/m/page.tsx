"use client";

import { useState } from "react";
import SpecimenCard from "@/components/SpecimenCard";
import ThemeToggle from "@/components/ThemeToggle";
import { stateOf, useBarn, specimens } from "@/lib/store";
import { ago, groupName, pct, ranked, resultOf, summary, tone } from "@/lib/insight";
import styles from "./mobile.module.css";

type Tab = "over" | "alerts" | "card";

// Simple line icons for the tab bar. 24 px grid, 1.8 stroke, like SF Symbols at regular weight.
const ICON: Record<Tab, React.ReactNode> = {
  over: <path d="M4 11l8-7 8 7v8a1 1 0 0 1-1 1h-4v-6H9v6H5a1 1 0 0 1-1-1z" />,
  alerts: <path d="M6 10a6 6 0 1 1 12 0c0 5 2 6 2 6H4s2-1 2-6zM10 19a2 2 0 0 0 4 0" />,
  card: <path d="M5 4h14a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1zM8 9h8M8 13h8M8 17h5" />,
};
const TABS: { id: Tab; label: string }[] = [
  { id: "over", label: "Barn" },
  { id: "alerts", label: "Alerts" },
  { id: "card", label: "Droppings" },
];

// Phone version. Large title, grouped lists and a bottom tab bar. Desktop is at /.
export default function Mobile() {
  useBarn();
  const [tab, setTab] = useState<Tab>("over");
  const [selectedId, setSelectedId] = useState(specimens()[0].id);
  const selected = specimens().find((s) => s.id === selectedId) ?? specimens()[0];
  const sum = summary();
  const abnormal = specimens().filter((s) => s.type !== "healthy").length;

  const open = (id: string) => { setSelectedId(id); setTab("card"); window.scrollTo(0, 0); };

  return (
    <div className={styles.wrap}>
      <header className={styles.top}>
        <h1 className="title">{tab === "over" ? "Barn" : tab === "alerts" ? "Alerts" : "Specimen"}</h1>
        <ThemeToggle />
      </header>

      <main>
        {tab === "over" && (
          <section>
            <div className={`glass ${styles.hero}`} data-level={sum.hot.length ? "bad" : "good"}>
              <div className={`eyebrow ${styles.state}`}>
                <i className={sum.hot.length ? styles.alert : styles.calm} />
                {sum.hot.length ? "Needs attention" : "All clear"}
              </div>
              <h2 className={styles.headline}>{sum.headline}</h2>
              <p className={`sub ${styles.detail}`}>{sum.detail}</p>
              <dl className={styles.stats}>
                <div><dd className="num">{sum.total}</dd><dt>Droppings checked</dt></div>
                <div><dd className={`num ${sum.abnormal ? "tone-bad" : ""}`}>{sum.abnormal}</dd><dt>Abnormal</dt></div>
                <div><dd className="num">{sum.mean}</dd><dt>Average grade</dt></div>
              </dl>
            </div>
            <h3 className="eyebrow list-h">Health board</h3>
            <div className="list">
              {ranked().map(({ group, status }, i) => (
                <button
                  key={group.id} className={`row ${styles.board}`}
                  onClick={() => { const s = specimens().find((x) => x.group === group.id); if (s) open(s.id); }}
                >
                  <span className={`${styles.rk} num`}>{i + 1}</span>
                  <span className="headline">{group.name}</span>
                  <span className={`${styles.gr} num ${status.mean === null ? "" : `tone-${status.level}`}`}>
                    {status.mean === null ? "n/a" : status.mean.toFixed(1)}
                  </span>
                </button>
              ))}
            </div>
          </section>
        )}

        {tab === "alerts" && (
          <section>
            <div className="list">
              {specimens().map((s) => (
                <button key={s.id} className={`row ${styles.item}`} onClick={() => open(s.id)}>
                  <span className={`${styles.grade} num tone-${tone(s.grade)}`}>{s.grade}</span>
                  <span className={styles.what}>
                    <b>{resultOf(s)}</b>
                    <small>{groupName(s.group)}, {ago(s.minsAgo)}{stateOf(s.id) === "checking" ? ", being checked" : stateOf(s.id) === "normal" ? ", marked normal" : ""}</small>
                  </span>
                  <span className={`${styles.conf} num`}>{pct(s.probs[s.type])}%</span>
                </button>
              ))}
            </div>
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
            <svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{ICON[t.id]}</svg>
            <span>{t.label}</span>
            {t.id === "alerts" && abnormal > 0 && <em className={styles.badge}>{abnormal}</em>}
          </button>
        ))}
      </nav>
    </div>
  );
}
