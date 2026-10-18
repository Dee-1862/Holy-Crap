"use client";

import Clock from "@/components/Clock";
import ThemeToggle from "@/components/ThemeToggle";
import ViewSwitch from "@/components/ViewSwitch";
import EdgeView from "./EdgeView";
import styles from "../live/live.module.css";

// The QNX Pi running the edge pipeline, see target/qnx/edge.
export default function Edge() {
  return (
    <div className={styles.shell}>
      <header className={styles.top}>
        <h1 className="title">Pi</h1>
        <ViewSwitch current="edge" />
        <span className={styles.grow} />
        <ThemeToggle />
        <Clock />
      </header>
      <EdgeView />
    </div>
  );
}
