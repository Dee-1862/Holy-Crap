"use client";

import { useEffect, useRef, useState } from "react";
import styles from "../live/live.module.css";

interface Proc { pid: number | null; restarts: number; started: number; lastExit: number | null; downFor: number | null }
interface Spot { cx: number; cy: number; w: number; h: number; area: number; t: number; crop: string }
interface Status {
  online: boolean; url: string; procs?: Record<string, Proc>; frames?: number; fps?: number; ms?: number; dropped?: number;
  thumb?: string | null; w?: number; h?: number; warm?: boolean; spots?: Spot[]; total?: number; crashes?: { proc: string; pid: number; t: number }[];
  now?: number; nativeIpc?: boolean; lastFrame?: number;
}

const PROCS: { id: string; name: string; role: string }[] = [
  { id: "camera", name: "Camera", role: "Sends frames" },
  { id: "spotter", name: "Spot finder", role: "Flags new still spots" },
  { id: "uplink", name: "Uplink", role: "Reports to this page" },
];

// Paints raw 8 bit grey pixels (base64) onto a canvas.
function Gray({ data, w, h, className }: { data: string; w: number; h: number; className?: string }) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const c = ref.current;
    const g = c?.getContext("2d");
    if (!c || !g) return;
    const px = Uint8Array.from(atob(data), (ch) => ch.charCodeAt(0));
    const img = g.createImageData(w, h);
    for (let i = 0; i < w * h; i++) {
      img.data.set([px[i], px[i], px[i], 255], i * 4);
    }
    g.putImageData(img, 0, 0);
  }, [data, w, h]);
  return <canvas ref={ref} width={w} height={h} className={className} />;
}

const ago = (s: number) => (s < 60 ? `${Math.round(s)} s` : s < 3600 ? `${Math.round(s / 60)} min` : `${(s / 3600).toFixed(1)} h`);

// Live view of the QNX Pi edge pipeline: its picture, its three processes and the spots it flagged.
// The crash buttons kill a process with SIGKILL so the restart can be watched.
export default function EdgeView() {
  const [s, setS] = useState<Status | null>(null);
  const [busy, setBusy] = useState("");

  useEffect(() => {
    let alive = true;
    const tick = () => fetch("/api/edge", { cache: "no-store" }).then((r) => r.json()).then((d) => alive && setS(d)).catch(() => {});
    tick();
    const t = window.setInterval(tick, 700);
    return () => { alive = false; window.clearInterval(t); };
  }, []);

  const crash = async (proc: string) => {
    setBusy(proc);
    await fetch(`/api/edge/crash?proc=${proc}`, { method: "POST" }).catch(() => {});
    window.setTimeout(() => setBusy(""), 1500);
  };

  if (!s) return <p className="sub">Looking for the Pi</p>;
  if (!s.online) {
    return (
      <div className={`glass ${styles.empty}`}>
        <h2 className="headline">The Pi is not answering</h2>
        <p className="sub">Tried {s.url}. Check the cable, then start the pipeline on the Pi.</p>
        <pre className={styles.code}>python scripts/pi_win.py{"\n"}ssh qnxpi-win{"\n"}cd hc-edge && python3 supervisor.py --replay ../hc-replay/pio.gray</pre>
      </div>
    );
  }

  const now = s.now ?? Date.now() / 1000;
  const recent = (s.spots ?? []).filter((x) => now - x.t < 60);
  const spots = [...(s.spots ?? [])].reverse();
  const stale = now - (s.lastFrame ?? 0) > 3;

  return (
    <div className={styles.grid}>
      <section className={`glass ${styles.stage}`} aria-label="Pi camera">
        <div className={styles.stageHead}>
          <span className={styles.badge}><i style={{ background: stale ? "var(--warn)" : "var(--good)" }} />{stale ? "No frames" : "Running"}</span>
          <h2 className="headline">QNX on Raspberry Pi 5</h2>
          <span className="foot num">{s.fps} frames a second{s.warm ? `, ${s.ms} ms of work each` : ""}, {s.dropped} dropped</span>
        </div>
        <div className={styles.frame} style={{ aspectRatio: s.w && s.h ? `${s.w} / ${s.h}` : "16 / 9" }}>
          {s.thumb && s.w && s.h && <Gray data={s.thumb} w={s.w} h={s.h} className={styles.smooth} />}
          <svg viewBox="0 0 1 1" preserveAspectRatio="none" className={styles.marks}>
            {recent.map((x, k) => (
              <rect key={k} x={x.cx - 0.02} y={x.cy - 0.035} width="0.04" height="0.07" className={styles.mark} />
            ))}
          </svg>
          {!s.warm && <div className={styles.warn}>Learning the empty floor, a few seconds after a start or restart</div>}
        </div>
        <p className="foot">
          The Pi replays recorded barn footage as grey 320 by 180 frames, standing in for the camera until live capture is wired up.
          Boxes mark candidates from the last minute. Everything shown is computed on the Pi.
        </p>
      </section>

      <aside className={styles.side}>
        <section className={`glass ${styles.card}`} aria-label="Processes">
          <span className="eyebrow">Processes on the Pi</span>
          <ul className={styles.procs}>
            {PROCS.map((p) => {
              const i = s.procs?.[p.id];
              return (
                <li key={p.id}>
                  <div>
                    <b>{p.name}</b>
                    <span className="foot num">pid {i?.pid ?? "?"}, up {i ? ago(now - i.started) : "?"}{i?.restarts ? `, restarted ${i.restarts}x in ${i.downFor} ms` : ""}</span>
                  </div>
                  <button className="pill" disabled={!!busy} onClick={() => crash(p.id)}>{busy === p.id ? "Killed" : "Crash"}</button>
                </li>
              );
            })}
          </ul>
          <p className="foot">
            Separate processes with their own memory that only talk by QNX message passing{s.nativeIpc ? "" : " (socket fallback, not QNX)"}.
            Crash one and the others keep running while it is restarted. QNX runs its own drivers the same way, which is the microkernel difference from Linux.
          </p>
        </section>

        <section className={`glass ${styles.card}`} aria-label="Flagged spots">
          <span className="eyebrow">Candidate spots</span>
          <div className={`${styles.big} num`}>{s.total ?? 0}</div>
          <p className="foot">Small things that appeared and stayed still. A cheap first filter, not a dropping detector. In this dense broiler house most are birds resting in place, which the trained model still has to rule out.</p>
          <div className={styles.spots}>
            {spots.slice(0, 12).map((x, k) => (
              <div key={k}><Gray data={x.crop} w={24} h={24} className={styles.pixel} /><span className="foot">{ago(now - x.t)} ago</span></div>
            ))}
          </div>
        </section>
      </aside>
    </div>
  );
}
