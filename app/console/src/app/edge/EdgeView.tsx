"use client";

import { useEffect, useRef, useState } from "react";
import styles from "../live/live.module.css";

interface Proc { pid: number | null; priority?: number; restarts: number; started: number; lastExit: number | null; downFor: number | null }
interface Spot { cx: number; cy: number; t: number }
interface Result {
  id: string; t: number; cx: number; cy: number; checked: boolean; verdict: "alert" | "normal" | "dismissed"; because: string;
  cls: string | null; score: number; why: string[]; patch: string; side: number;
}
interface Status {
  online: boolean; url: string; procs?: Record<string, Proc>; frames?: number; fps?: number; ms?: number; dropped?: number;
  thumb?: string | null; w?: number; h?: number; warm?: boolean; spots?: Spot[]; total?: number; results?: Result[];
  source?: string; full?: [number, number] | null; now?: number; nativeIpc?: boolean; lastFrame?: number;
  modelStats?: { patches: number; checked: number; unreachable: number; skipped: number; stale: number } | null;
}

// The sections running on the Pi, highest priority first. Each is its own process.
const SECTIONS: { id: string; name: string; role: string }[] = [
  { id: "watch", name: "Stopwatch link", role: "Alerts to the farmer's watch, works without internet" },
  { id: "camera", name: "Camera", role: "Full frames into shared memory, small grey copy onward" },
  { id: "spotter", name: "Spot finder", role: "New things that appeared and stayed still" },
  { id: "uplink", name: "Dashboard link", role: "This page" },
  { id: "cloud", name: "Cloud link", role: "Results to the console or Vercel, waits on disk when offline" },
  { id: "explain", name: "Explainability", role: "Measures each patch and decides alert or dismiss" },
  { id: "model", name: "Model", role: "Cuts a full resolution patch, gets the detector's verdict" },
];

// Paints raw pixels (base64), grey or RGB, onto a canvas.
function Pixels({ data, w, h, rgb, className }: { data: string; w: number; h: number; rgb?: boolean; className?: string }) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const g = ref.current?.getContext("2d");
    if (!g) return;
    const px = Uint8Array.from(atob(data), (ch) => ch.charCodeAt(0));
    const img = g.createImageData(w, h);
    for (let i = 0; i < w * h; i++) {
      if (rgb) img.data.set([px[i * 3], px[i * 3 + 1], px[i * 3 + 2], 255], i * 4);
      else img.data.set([px[i], px[i], px[i], 255], i * 4);
    }
    g.putImageData(img, 0, 0);
  }, [data, w, h, rgb]);
  return <canvas ref={ref} width={w} height={h} className={className} />;
}

const ago = (s: number) => (s < 60 ? `${Math.round(s)} s` : s < 3600 ? `${Math.round(s / 60)} min` : `${(s / 3600).toFixed(1)} h`);
const VERDICT = { alert: "Alert", normal: "Looks normal", dismissed: "Dismissed" } as const;

// Live view of the QNX Pi: its picture, its sections and what they decided. The crash buttons kill a
// section with SIGKILL so the restart can be watched.
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
        <pre className={styles.code}>python scripts/pi_win.py{"\n"}ssh qnxpi-win{"\n"}cd hc-edge && python3 supervisor.py --camera replay</pre>
      </div>
    );
  }

  const now = s.now ?? Date.now() / 1000;
  const recent = (s.spots ?? []).filter((x) => now - x.t < 60);
  const results = s.results ?? [];
  const passed = results.filter((r) => r.verdict !== "dismissed").length;
  const stale = now - (s.lastFrame ?? 0) > 3;
  const ms = s.modelStats;

  return (
    <div className={styles.grid}>
      <div className={styles.side}>
        <section className={`glass ${styles.stage}`} aria-label="Pi camera">
          <div className={styles.stageHead}>
            <span className={styles.badge}><i style={{ background: stale ? "var(--warn)" : "var(--good)" }} />{stale ? "No frames" : "Running"}</span>
            <h2 className="headline">QNX on Raspberry Pi 5</h2>
            <span className="foot num">{s.fps} frames a second{s.warm ? `, ${s.ms} ms of spot finding each` : ""}, {s.dropped} dropped</span>
          </div>
          <div className={styles.frame} style={{ aspectRatio: s.w && s.h ? `${s.w} / ${s.h}` : "16 / 9" }}>
            {s.thumb && s.w && s.h && <Pixels data={s.thumb} w={s.w} h={s.h} className={styles.smooth} />}
            <svg viewBox="0 0 1 1" preserveAspectRatio="none" className={styles.marks}>
              {recent.map((x, k) => <rect key={k} x={x.cx - 0.02} y={x.cy - 0.035} width="0.04" height="0.07" className={styles.mark} />)}
            </svg>
            {!s.warm && <div className={styles.warn}>Learning the empty floor, a few seconds after a start or restart</div>}
          </div>
          <p className="foot">
            {s.source === "camera" ? "Live from the QNX camera service" : "Recorded barn footage played as the camera"}
            {s.full?.[0] ? `, kept at ${s.full[0]} by ${s.full[1]} in shared memory. ` : ". "}
            Shown is the small grey copy the spot finder uses. Boxes are candidates from the last minute.
          </p>
        </section>

        <section className={`glass ${styles.card}`} aria-label="Checked patches">
          <span className="eyebrow">What the model and explainability decided</span>
          <p className="foot">
            {ms ? `${ms.checked} full resolution patches checked by the model${ms.unreachable ? `, ${ms.unreachable} not reachable` : ""}${ms.skipped ? `, ${ms.skipped} skipped while busy` : ""}. ` : ""}
            {passed} of the last {results.length} passed every check and went to the watch.
            The detector learned on close-up photos and still scores birds at this distance, so the checks dismiss most of what it says.
          </p>
          <div className={styles.results}>
            {results.slice(0, 8).map((r) => (
              <article key={r.id} className={styles.result}>
                <Pixels data={r.patch} w={r.side} h={r.side} rgb className={styles.pixel} />
                <div>
                  <b className={r.verdict === "alert" ? "tone-bad" : r.verdict === "normal" ? "tone-good" : undefined}>{VERDICT[r.verdict] ?? "Checked"}</b>
                  <span className="foot">{r.because}</span>
                  <ul>{r.why.map((w, k) => <li key={k} className="foot">{w}</li>)}</ul>
                  <span className="foot num">{ago(now - r.t)} ago</span>
                </div>
              </article>
            ))}
          </div>
        </section>
      </div>

      <aside className={styles.side}>
        <section className={`glass ${styles.card}`} aria-label="Sections">
          <span className="eyebrow">Sections on the Pi</span>
          <ul className={styles.procs}>
            {SECTIONS.map((p) => {
              const i = s.procs?.[p.id];
              return (
                <li key={p.id}>
                  <div>
                    <b>{p.name} <span className="foot num">priority {i?.priority ?? "?"}</span></b>
                    <span className="foot">{p.role}</span>
                    <span className="foot num">pid {i?.pid ?? "?"}, up {i ? ago(now - i.started) : "?"}{i?.restarts ? `, restarted ${i.restarts}x, back in ${i.downFor} ms` : ""}</span>
                  </div>
                  <button className="pill" disabled={!!busy} onClick={() => crash(p.id)}>{busy === p.id ? "Killed" : "Crash"}</button>
                </li>
              );
            })}
          </ul>
          <p className="foot">
            Each section is its own process with its own memory, talking only by QNX message passing{s.nativeIpc ? "" : " (socket fallback, not QNX)"}.
            Higher priority runs first, so the watch and the camera are never held up by the model. Crash any one and the rest keep going while it restarts.
            QNX runs its own drivers the same way, which is the microkernel difference from Linux.
          </p>
        </section>

        <section className={`glass ${styles.card}`} aria-label="Candidate spots">
          <span className="eyebrow">Candidate spots</span>
          <div className={`${styles.big} num`}>{s.total ?? 0}</div>
          <p className="foot">Small things that appeared and stayed still. A cheap first filter on the Pi, the model and the checks come after it.</p>
        </section>
      </aside>
    </div>
  );
}
