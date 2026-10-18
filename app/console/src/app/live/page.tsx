"use client";

import Clock from "@/components/Clock";
import ThemeToggle from "@/components/ThemeToggle";
import ViewSwitch from "@/components/ViewSwitch";
import LiveFeed from "./LiveFeed";
import styles from "./live.module.css";

// Camera feed view. It replays public whole-pen footage, see app/live-feed.
export default function Live() {
  return (
    <div className={styles.shell}>
      <header className={styles.top}>
        <h1 className="title">Live</h1>
        <ViewSwitch current="live" />
        <span className={styles.grow} />
        <ThemeToggle />
        <Clock />
      </header>
      <LiveFeed />
    </div>
  );
}
