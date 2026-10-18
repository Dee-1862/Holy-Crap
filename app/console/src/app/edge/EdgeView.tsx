"use client";

import { useEffect, useRef, useState } from "react";
import styles from "./edge.module.css";

interface Proc { pid: number | null; priority?: number; restarts: number; started: number; lastExit: number | null; downFor: number | null }
interface Status {
  online: boolean; url: string; procs?: Record<string, Proc>; frames?: number; fps?: number; dropped?: number;
  now?: number; nativeIpc?: boolean; total?: number;
  modelStats?: { patches: number; checked: number; unreachable: number } | null;
  crashes?: { proc: string; pid: number; t: number }[];
}
interface Incident {
  proc: string; at: number;                    // when the button was pressed, browser clock
  oldPid: number | null; newPid: number | null; restartMs: number | null;
  pidsBefore: Record<string, number | null>;   // every section's pid at the moment of the crash
  backAt: number | null;                        // first poll that saw the new process
  framesStoppedMs: number | null;              // camera output gap, measured from the frame counter
  kept: string[];                              // sections whose pid never changed
  waited: string[];                            // downstream sections that had nothing to work on meanwhile
  done: boolean;
}

// The pipeline in the order data flows. Each box is its own process on the Pi.
const SECTIONS: { id: string; name: string; does: string; after: string[] }[] = [
  { id: "camera", name: "Camera", does: "Puts each frame in shared memory", after: [] },
  { id: "spotter", name: "Spot finder", does: "Finds small new still things", after: ["camera"] },
  { id: "model", name: "Model", does: "Cuts a patch, gets the detector's verdict", after: ["spotter"] },
  { id: "explain", name: "Explainability", does: "Measures the patch, says alert or dismiss", after: ["model"] },
  { id: "watch", name: "Watch link", does: "Alerts to the StopWatch, no internet needed", after: ["explain"] },
  { id: "cloud", name: "Cloud link", does: "Results to the console, waits on disk offline", after: ["explain"] },
  { id: "uplink", name: "Dashboard link", does: "Serves this page", after: [] },
];
const NAME = Object.fromEntries(SECTIONS.map((s) => [s.id, s.name]));
const downstream = (id: string): string[] => {
  const out = SECTIONS.filter((s) => s.after.includes(id)).map((s) => s.id);
  return out.flatMap((x) => [x, ...downstream(x)]);
};
const clock = (ms: number) => new Date(ms).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });

// The QNX Pi's seven sections and what happens when one is killed. No camera picture here on purpose:
// the point is the processes. Polls the Pi through /api/edge, faster for a few seconds after a crash.
export default function EdgeView() {
  const [s, setS] = useState<Status | null>(null);
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [fast, setFast] = useState(false);
  const frameGap = useRef<{ lastChange: number; frames: number; longest: number }>({ lastChange: 0, frames: 0, longest: 0 });

  useEffect(() => {
    let alive = true;
    const tick = () => fetch("/api/edge", { cache: "no-store" }).then((r) => r.json()).then((d: Status) => {
      if (!alive) return;
      const at = Date.now();
      const g = frameGap.current;                                  // how long the frame counter stood still
      if (d.frames !== undefined) {
        if (d.frames !== g.frames) { g.longest = Math.max(g.longest, at - g.lastChange); g.frames = d.frames; g.lastChange = at; }
      }
      // finish open incidents once the killed section is back with a new pid and frames are moving again
      setIncidents((list) => list.map((inc) => {
        if (inc.done || !d.procs) return inc;
        const p = d.procs[inc.proc];
        if (!inc.backAt) return p && p.pid !== inc.oldPid ? { ...inc, backAt: at } : inc;
        // done once frames flow again after the new process appeared; held at least 1.5 s so the change can be seen
        const framesOk = g.lastChange > inc.backAt || (inc.proc !== "camera" && inc.proc !== "uplink");
        if (!framesOk || at - inc.at < 1500) return inc;
        const kept = SECTIONS.filter((x) => x.id !== inc.proc && d.procs?.[x.id]?.pid === inc.pidsBefore[x.id]).map((x) => x.id);
        return { ...inc, newPid: p.pid, restartMs: p.downFor, framesStoppedMs: inc.proc === "camera" || inc.proc === "uplink" ? g.longest : null,
                 kept, waited: downstream(inc.proc), done: true };
      }));
      setS(d);
    }).catch(() => {});
    tick();
    const t = window.setInterval(tick, fast ? 200 : 900);
    return () => { alive = false; window.clearInterval(t); };
  }, [fast]);

  const crash = async (proc: string) => {
    const oldPid = s?.procs?.[proc]?.pid ?? null;
    frameGap.current.longest = 0;
    const pidsBefore = Object.fromEntries(SECTIONS.map((x) => [x.id, s?.procs?.[x.id]?.pid ?? null]));
    setIncidents((l) => [{ proc, at: Date.now(), oldPid, newPid: null, restartMs: null, pidsBefore, backAt: null, framesStoppedMs: null, kept: [], waited: [], done: false }, ...l].slice(0, 6));
    setFast(true);
    window.setTimeout(() => setFast(false), 8000);
    await fetch(`/api/edge/crash?proc=${proc}`, { method: "POST" }).catch(() => {});
  };

  if (!s) return <p className="sub">Looking for the Pi</p>;
  if (!s.online) {
    return (
      <div className={`glass ${styles.card}`}>
        <h2 className="headline">The Pi is not answering</h2>
        <p className="sub">Tried {s.url}. Check the cable, then start the pipeline on the Pi.</p>
        <pre className={styles.code}>python scripts/pi_win.py{"\n"}ssh qnxpi-win{"\n"}cd hc-edge && python3 supervisor.py --camera replay</pre>
      </div>
    );
  }

  const open = incidents.find((i) => !i.done);
  const hurt = open ? [open.proc, ...downstream(open.proc)] : [];

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
            const state = open?.proc === x.id && !open.backAt ? "down" : hurt.includes(x.id) ? "waiting" : "up";
            return (
              <article key={x.id} className={styles.node} data-state={state} data-branch={x.id === "watch" || x.id === "cloud" || undefined}>
                <div className={styles.nodeHead}><i />{x.name}</div>
                <span className="foot">{x.does}</span>
                <span className="foot num">pid {p?.pid ?? "?"} · priority {p?.priority ?? "?"}{p?.restarts ? ` · restarted ${p.restarts}x` : ""}</span>
                <button className="pill" disabled={!!open} onClick={() => crash(x.id)}>{state === "down" ? "Restarting" : state === "waiting" ? "Waiting" : "Crash"}</button>
              </article>
            );
          })}
        </div>
        <p className="foot">Data flows left to right, and explainability fans out to the watch and cloud links. Crash sends SIGKILL to that one process, no clean shutdown, like a real fault.</p>
      </section>

      <section className={`glass ${styles.card}`} aria-label="What happened">
        <span className="eyebrow">What happened</span>
        {incidents.length === 0 && <p className="sub">Press Crash on any section. This shows what the rest of the Pi did while it was gone.</p>}
        {incidents.map((i, k) => (
          <div key={k} className={styles.incident}>
            <b>{clock(i.at)} · {NAME[i.proc]} killed</b>
            {!i.done ? <p className="sub">Waiting for the supervisor to bring it back</p> : (
              <ul>
                <li>The supervisor started a new {NAME[i.proc]} in <b className="num">{i.restartMs ?? "?"} ms</b> (pid {i.oldPid} → {i.newPid}).</li>
                {i.framesStoppedMs !== null && <li>Frames stopped for about <b className="num">{(i.framesStoppedMs / 1000).toFixed(1)} s</b> while it opened the camera again, then carried on.</li>}
                {i.waited.length > 0 && <li>{i.waited.map((w) => NAME[w]).join(", ")} had nothing new to work on for that moment, and picked up again by themselves.</li>}
                <li>{i.kept.length ? i.kept.map((w) => NAME[w]).join(", ") : "No other section"} kept the same process the whole time{i.kept.includes("watch") ? ", so the farmer's watch never lost its alerts" : ""}.</li>
              </ul>
            )}
          </div>
        ))}
        {(s.crashes?.length ?? 0) > 0 && <p className="foot">Kills since the Pi pipeline started: {s.crashes!.length}. Every one came back on its own.</p>}
      </section>

      <section className={`glass ${styles.card}`} aria-label="Why QNX">
        <span className="eyebrow">Why this is the QNX way, and how Linux differs</span>
        <div className={styles.compare}>
          <div>
            <h3>On this QNX Pi</h3>
            <ul>
              <li>Each section is an ordinary process with its own memory. A fault cannot write into another section.</li>
              <li>The camera driver, USB, network stack and file system are ordinary processes too. That is the microkernel: the kernel only schedules and passes messages.</li>
              <li>So the same kill and restart you just saw works for a crashed driver. The rest of the Pi keeps running.</li>
              <li>The real time scheduler runs higher priority first: watch 21, camera 20, model 8. The model can never delay an alert.</li>
            </ul>
          </div>
          <div>
            <h3>On a typical Linux box</h3>
            <ul>
              <li>Our seven sections could also be separate processes restarted by systemd. At this level it looks alike.</li>
              <li>The difference is underneath. Drivers, the network stack and file systems run inside the kernel, sharing its memory.</li>
              <li>A bug in the camera or USB driver can freeze or panic the whole kernel. Every section stops and the Pi has to reboot, about half a minute to a minute.</li>
              <li>The default scheduler shares time fairly, so a busy model can slow the alerts unless real time priorities are set up by hand.</li>
            </ul>
          </div>
        </div>
        <p className="foot">What this demo kills is our own application sections. Killing the QNX camera driver itself is the next test to run on the Pi.</p>
      </section>
    </div>
  );
}
