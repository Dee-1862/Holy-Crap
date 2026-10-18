"use client";

import { useEffect, useState } from "react";
import styles from "./edge.module.css";

interface Proc { pid: number | null; priority?: number; restarts: number; started: number; lastExit: number | null; downFor: number | null }
interface Status {
  online: boolean; url: string; via?: "direct" | "bridge"; procs?: Record<string, Proc>; frames?: number; fps?: number;
  now?: number; nativeIpc?: boolean; started?: number;
  modelStats?: { checked: number } | null;
  crashes?: { proc: string; pid: number; t: number }[];
}
// One crash the viewer pressed: red until the Pi reports a new process, then green with the measured time.
interface Kill { proc: string; at: number; oldPid: number | null; newPid: number | null; ms: number | null; backAt: number | null }

// The pipeline in the order data flows. Each box is its own process on the Pi.
const SECTIONS: { id: string; name: string; does: string }[] = [
  { id: "camera", name: "Camera", does: "Captures frames" },
  { id: "spotter", name: "Spot finder", does: "Finds still spots" },
  { id: "model", name: "Model", does: "Checks each spot" },
  { id: "explain", name: "Explainability", does: "Explains the verdict" },
  { id: "watch", name: "Watch link", does: "Alerts the watch" },
  { id: "cloud", name: "Cloud link", does: "Syncs to the cloud" },
  { id: "uplink", name: "Dashboard", does: "Serves this page" },
];
const RED_AT_LEAST = 1200;     // ms the killed box stays red, so a 20 ms restart can still be seen
const GREEN_FOR = 6000;        // ms the "back" note stays on the box

const uptime = (s: number) => (s < 3600 ? `${Math.round(s / 60)} min` : `${(s / 3600).toFixed(1)} h`);

// The QNX Pi's seven sections. Crash one and only that one restarts, the rest keep running.
export default function EdgeView() {
  const [s, setS] = useState<Status | null>(null);
  const [kills, setKills] = useState<Kill[]>([]);
  const [now, setNow] = useState(Date.now());

  useEffect(() => {
    let alive = true;
    const tick = () => fetch("/api/edge", { cache: "no-store" }).then((r) => r.json()).then((d: Status) => {
      if (!alive) return;
      const at = Date.now();
      setNow(at);
      setKills((list) => list.map((k) => {
        const p = d.procs?.[k.proc];
        return !k.backAt && p && p.pid !== k.oldPid ? { ...k, newPid: p.pid, ms: p.downFor, backAt: at } : k;
      }));
      setS(d);
    }).catch(() => {});
    tick();
    const t = window.setInterval(tick, 400);
    return () => { alive = false; window.clearInterval(t); };
  }, []);

  const crash = async (proc: string) => {
    setKills((l) => [...l.filter((k) => k.proc !== proc), { proc, at: Date.now(), oldPid: s?.procs?.[proc]?.pid ?? null, newPid: null, ms: null, backAt: null }]);
    await fetch(`/api/edge/crash?proc=${proc}`, { method: "POST" }).catch(() => {});
  };

  if (!s) return <p className="sub">Looking for the Pi</p>;
  if (!s.online) {
    return (
      <div className={`glass ${styles.card}`}>
        <h2 className="headline">The Pi is not answering</h2>
        {s.via === "bridge" ? (
          <>
            <p className="sub">This site is online and the Pi sits on a cable to a laptop, so the laptop passes its status along. Start the bridge on that laptop:</p>
            <pre className={styles.code}>python scripts/edge_bridge.py --site {typeof window !== "undefined" ? window.location.origin : "https://your-site"}</pre>
          </>
        ) : (
          <>
            <p className="sub">Tried {s.url}. Check the cable, then start the pipeline on the Pi.</p>
            <pre className={styles.code}>python scripts/pi_win.py{"\n"}ssh qnxpi-win{"\n"}cd hc-edge && python3 supervisor.py --camera replay</pre>
          </>
        )}
      </div>
    );
  }

  const restarts = Object.values(s.procs ?? {}).map((p) => p.downFor).filter((x): x is number => x !== null);
  const avgMs = restarts.length ? restarts.reduce((a, b) => a + b, 0) / restarts.length : null;
  // every restart the supervisor counted, so it goes up by one with each crash
  const killsTotal = Object.values(s.procs ?? {}).reduce((a, p) => a + (p.restarts ?? 0), 0);
  const up = s.now && s.started ? s.now - s.started : null;
  const prio = (id: string) => s.procs?.[id]?.priority ?? "?";

  return (
    <div className={styles.page}>
      <section className={`glass ${styles.card}`} aria-label="Sections">
        <div className={styles.head}>
          <h2 className="headline">Seven sections, seven processes</h2>
          <span className="foot num">{s.fps} frames a second · {s.modelStats?.checked ?? 0} patches checked · {s.nativeIpc ? "QNX message passing" : "socket fallback, not QNX"}</span>
        </div>
        <div className={styles.flow}>
          {SECTIONS.map((x) => {
            const p = s.procs?.[x.id];
            const k = kills.find((y) => y.proc === x.id);
            const red = !!k && (!k.backAt || now - k.at < RED_AT_LEAST);
            const back = !!k && !red && !!k.backAt && now - k.backAt < GREEN_FOR;
            return (
              <article key={x.id} className={styles.node} data-state={red ? "down" : back ? "back" : "up"}
                data-branch={x.id === "watch" || x.id === "cloud" || undefined}>
                <div className={styles.nodeHead}><i />{x.name}</div>
                <span className={styles.does}>{x.does}</span>
                <dl className={styles.facts}>
                  <dt>PID</dt><dd className="num">{p?.pid ?? "?"}</dd>
                  <dt>Priority</dt><dd className="num">{p?.priority ?? "?"}</dd>
                  <dt>Restarts</dt><dd className="num">{p?.restarts ?? 0}</dd>
                </dl>
                <span className={styles.note}>{red ? "Killed, restarting" : back ? `Back in ${k!.ms ?? "?"} ms` : "Running"}</span>
                <button className="pill" disabled={red} onClick={() => crash(x.id)}>{red ? "Restarting" : "Crash"}</button>
              </article>
            );
          })}
        </div>
        <p className="foot">Crash sends SIGKILL to that one process, no clean shutdown, like a real fault. Only that box changes, with a new PID. Every other section keeps its PID and keeps working.</p>
      </section>

      <section className={`glass ${styles.card}`} aria-label="Why QNX">
        <span className="eyebrow">Why QNX for a barn</span>
        <div className={styles.tiles}>
          <div className={styles.tile}>
            <b className="num">{killsTotal}</b>
            <h3>Faults stay in their box</h3>
            <p>Kills survived on this Pi{up ? ` in ${uptime(up)}` : ""}, every one restarted on its own{avgMs !== null ? `, in ${avgMs.toFixed(0)} ms on average` : ""}. On QNX even drivers and the network stack are processes like these, so one fault never takes the whole box down.</p>
          </div>
          <div className={styles.tile}>
            <b className="num">{prio("watch")} &gt; {prio("model")}</b>
            <h3>The alert always goes first</h3>
            <p>A real time scheduler, not a fair share one. The watch link runs at priority {prio("watch")} and the camera at {prio("camera")}, the model at {prio("model")}. However busy the model gets, an alert is never kept waiting.</p>
          </div>
          <div className={styles.tile}>
            <b>Offline</b>
            <h3>No internet, still working</h3>
            <p>The Pi finds, checks and explains droppings by itself and serves the farmer&apos;s watch directly. Results for the dashboard wait on disk and go out when the line is back.</p>
          </div>
          <div className={styles.tile}>
            <b>Unattended</b>
            <h3>Made for places no one is watching</h3>
            <p>QNX runs car dashboards and driver assistance, medical devices, rail signalling and factory control, where a crash or a reboot is not acceptable. A dusty, hot barn with flaky power is the same kind of job.</p>
          </div>
          <div className={styles.tile}>
            <b className="num">{s.fps}</b>
            <h3>Small hardware, real time</h3>
            <p>Frames a second through the whole pipeline on a Raspberry Pi 5, the kind of board that fits in a sealed box on a barn wall, with no cloud bill.</p>
          </div>
        </div>
      </section>
    </div>
  );
}
