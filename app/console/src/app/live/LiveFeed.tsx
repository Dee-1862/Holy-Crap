"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import styles from "./live.module.css";

interface Clip {
  id: string; pen: string; title: string; view: string; source: string; sourceUrl: string; license: string; bytes: number; test?: boolean;
}
type Box = [number, number, number, number, string, number];       // x1, y1, x2, y2 as shares of the frame, class, score
interface Spot { t: number; box: [number, number, number, number]; cls: string; score: number; crop: string }
interface Truth { t: number; box: [number, number, number, number]; cls: string; foundAt: number | null }
interface Evaluation { heldOut: boolean; recall: number; precision: number; realBoxesPerTile: number; note: string }
interface Analysis {
  id: string; width: number; height: number; duration: number; rate: number; times: number[];
  model: string; conf: number; activity: number[]; raw?: number[]; detections: Box[][]; spots?: Spot[];
  evaluation?: Evaluation; truth?: Truth[];
  summary: { samples: number; meanRawBoxesPerFrame?: number; meanBoxesPerFrame: number; spots?: number; meanActivity: number };
}

const LONG = 600;   // seconds, longer clips play as a continuous feed

// The last sample at or before time t.
function indexAt(times: number[], t: number) {
  let lo = 0, hi = times.length - 1;
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1;
    if (times[mid] <= t) lo = mid; else hi = mid - 1;
  }
  return lo;
}

function clock(s: number) {
  const m = Math.floor(s / 60), r = Math.floor(s % 60);
  return m >= 60 ? `${Math.floor(m / 60)}:${String(m % 60).padStart(2, "0")}:${String(r).padStart(2, "0")}` : `${m}:${String(r).padStart(2, "0")}`;
}

// Replays public barn footage as a feed. It is a replay, not a camera, and the page says so.
// Long feeds start where the wall clock says they should, so every viewer sees the same moment.
export default function LiveFeed() {
  const [clips, setClips] = useState<Clip[] | null>(null);
  const [hint, setHint] = useState("");
  const [id, setId] = useState("");
  const [data, setData] = useState<Analysis | null>(null);
  const [boxes, setBoxes] = useState(false);
  const [now, setNow] = useState(0);
  const video = useRef<HTMLVideoElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    fetch("/api/live/clips", { cache: "no-store" })
      .then((r) => r.json())
      .then((d: { clips: Clip[]; hint: string | null }) => { setClips(d.clips); setHint(d.hint ?? "");
        // optional deep links: /live?clip=pio-0002&boxes=1 or /live?pen=A1
        const q = new URLSearchParams(window.location.search);
        setBoxes(q.get("boxes") === "1");
        const pick = d.clips.find((c) => c.id === q.get("clip")) ?? d.clips.find((c) => c.pen === q.get("pen")) ?? d.clips[0];
        setId(pick?.id ?? ""); })
      .catch(() => { setClips([]); setHint("The clip service did not answer. Is the console running?"); });
  }, []);

  useEffect(() => {
    if (!id) return;
    setData(null); setNow(0);
    fetch(`/api/live/analysis/${id}`, { cache: "no-store" }).then((r) => (r.ok ? r.json() : null)).then(setData).catch(() => setData(null));
  }, [id]);

  // a long feed joins at the wall clock position once its length is known
  const onLoaded = useCallback(() => {
    const v = video.current;
    if (!v) return;
    const t = Number(new URLSearchParams(window.location.search).get("t"));   // a link from a spot on the map
    if (t > 0 && t < v.duration) v.currentTime = t;
    else if (v.duration > LONG) v.currentTime = (Date.now() / 1000) % v.duration;
  }, []);

  useEffect(() => {
    const timer = window.setInterval(() => { if (video.current) setNow(video.current.currentTime); }, 200);
    return () => window.clearInterval(timer);
  }, []);

  // draw spots found so far, and optionally this moment's filtered boxes
  useEffect(() => {
    let raf = 0;
    const draw = () => {
      const c = canvas.current, v = video.current;
      if (c && v) {
        const w = c.clientWidth * devicePixelRatio, h = c.clientHeight * devicePixelRatio;
        if (c.width !== w || c.height !== h) { c.width = w; c.height = h; }
        const g = c.getContext("2d");
        if (g) {
          g.clearRect(0, 0, w, h);
          if (data?.times.length) {
            g.lineWidth = 2 * devicePixelRatio;
            if (boxes) {
              g.strokeStyle = "rgba(255, 214, 10, 0.9)";
              for (const [x1, y1, x2, y2] of data.detections[indexAt(data.times, v.currentTime)] ?? []) {
                g.strokeRect(x1 * w, y1 * h, (x2 - x1) * w, (y2 - y1) * h);
              }
            }
            // answer key on test clips: a dashed ring where a dropping was pasted in
            g.setLineDash([5 * devicePixelRatio, 4 * devicePixelRatio]);
            g.strokeStyle = "rgba(255, 255, 255, 0.55)";
            for (const t of data.truth ?? []) {
              if (t.t > v.currentTime) continue;
              const [x1, y1, x2, y2] = t.box;
              g.beginPath();
              g.arc(((x1 + x2) / 2) * w, ((y1 + y2) / 2) * h, 22 * devicePixelRatio, 0, Math.PI * 2);
              g.stroke();
            }
            g.setLineDash([]);
            g.strokeStyle = "#30d158";
            for (const s of data.spots ?? []) {
              if (s.t > v.currentTime || s.t < v.currentTime - 120) continue;    // a spot stays marked for two minutes
              const [x1, y1, x2, y2] = s.box;
              g.beginPath();
              g.arc(((x1 + x2) / 2) * w, ((y1 + y2) / 2) * h, Math.max(14 * devicePixelRatio, ((x2 - x1) * w) * 1.2), 0, Math.PI * 2);
              g.stroke();
            }
          }
        }
      }
      raf = requestAnimationFrame(draw);
    };
    raf = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(raf);
  }, [boxes, data]);

  const seek = useCallback((e: React.MouseEvent<SVGSVGElement>) => {
    if (!video.current || !data) return;
    const r = e.currentTarget.getBoundingClientRect();
    video.current.currentTime = ((e.clientX - r.left) / r.width) * data.duration;
  }, [data]);

  if (clips === null) return <p className="sub">Loading clips</p>;
  if (!clips.length) {
    return (
      <div className={`glass ${styles.empty}`}>
        <h2 className="headline">No clips installed</h2>
        <p className="sub">The live feed replays public barn footage that is not stored in the repository. {hint}</p>
        <pre className={styles.code}>python app/live-feed/fetch_clips.py{"\n"}python app/live-feed/analyze_clips.py</pre>
      </div>
    );
  }

  const clip = clips.find((c) => c.id === id) ?? clips[0];
  const i = data ? indexAt(data.times, now) : 0;
  const recent = data ? data.activity.slice(Math.max(0, i - 2), i + 1) : [];
  const motion = recent.length ? recent.reduce((a, b) => a + b, 0) / recent.length : 0;
  const max = data ? Math.max(5, ...data.activity) : 5;
  const path = data
    ? data.activity.map((a, k) => `${k ? "L" : "M"}${((data.times[k] / data.duration) * 300).toFixed(1)},${(60 - (a / max) * 56).toFixed(1)}`).join(" ")
    : "";
  const spots = data?.spots ?? [];
  const seen = spots.filter((s) => s.t <= now);
  const ev = data?.evaluation;
  const truth = (data?.truth ?? []).filter((t) => t.t <= now);
  const found = truth.filter((t) => t.foundAt !== null && t.foundAt <= now).length;

  return (
    <div className={styles.grid}>
      <section className={`glass ${styles.stage}`} aria-label="Replayed camera feed">
        <div className={styles.stageHead}>
          <span className={styles.badge}><i />{clip.test ? "Test clip" : "Replay"}</span>
          <span className={styles.pen}>Pen {clip.pen}</span>
          <h2 className="headline">{clip.title}</h2>
          <span className="foot">{clip.view}</span>
        </div>
        <div className={styles.frame} style={{ aspectRatio: data ? `${data.width} / ${data.height}` : "16 / 9" }}>
          <video ref={video} key={clip.id} src={`/api/live/clip/${clip.id}`} autoPlay muted loop playsInline controls={false} onLoadedMetadata={onLoaded} />
          <canvas ref={canvas} />
          {data && <span className={styles.time}>{clock(now)} / {clock(data.duration)}</span>}
        </div>
        <div className={styles.controls}>
          <div className="seg" role="group" aria-label="Choose a camera">
            {clips.map((c) => (
              <button key={c.id} aria-pressed={c.id === clip.id} onClick={() => setId(c.id)}>{c.test ? `${c.pen} test` : c.pen}</button>
            ))}
          </div>
          <label className="switch">
            <input type="checkbox" checked={boxes} onChange={(e) => setBoxes(e.target.checked)} />
            Show every detector box
          </label>
        </div>
        <p className="foot">
          Replay of a public dataset video, not a live camera. Source: <a href={clip.sourceUrl} target="_blank" rel="noreferrer">{clip.source}</a>, {clip.license}.
          {ev?.heldOut ? " This video was kept out of training." : ""}
        </p>
      </section>

      <aside className={styles.side}>
        <section className={`glass ${styles.card}`} aria-label="Flock motion">
          <span className="eyebrow">Flock motion</span>
          <div className={`${styles.big} num`}>{motion.toFixed(1)}<small>%</small></div>
          <p className="foot">Share of the picture that changed in the last few seconds.</p>
          <svg viewBox="0 0 300 64" className={styles.spark} onClick={seek} role="img" aria-label="Motion over the video, click to jump">
            {data && <path d={`${path} L300,60 L0,60 Z`} className={styles.area} />}
            {data && <path d={path} className={styles.line} />}
            {data && spots.map((s, k) => <circle key={k} cx={(s.t / data.duration) * 300} cy="61" r="2" className={styles.dot} />)}
            {data && <line x1={(now / data.duration) * 300} x2={(now / data.duration) * 300} y1="0" y2="64" className={styles.head} />}
          </svg>
          <p className="foot">Dots mark flagged spots. Click the chart to jump.</p>
        </section>

        {data?.truth && (
          <section className={`glass ${styles.card}`} aria-label="Answer key">
            <span className="eyebrow">Answer key</span>
            <div className={`${styles.big} num`}>{found}<small>of {truth.length} found</small></div>
            <p className="foot">Dashed rings are droppings pasted into this held out video at known times. Green rings are what the detector flagged. Droppings a bird is sitting on cannot be seen.</p>
          </section>
        )}

        <section className={`glass ${styles.card}`} aria-label="Flagged spots">
          <span className="eyebrow">Flagged spots</span>
          <div className={`${styles.big} num`}>{seen.length}<small>of {spots.length}</small></div>
          <p className="foot">Places where the detector kept finding something small and still on the litter. Each one is a lead to check, not a confirmed dropping.</p>
          {seen.length > 0 && (
            <div className={styles.spots}>
              {seen.slice(-8).reverse().map((s, k) => (
                <button key={k} onClick={() => { if (video.current) video.current.currentTime = s.t; }} title={`Jump to ${clock(s.t)}`}>
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={s.crop} alt={`Spot at ${clock(s.t)}`} />
                  <span>{clock(s.t)}</span>
                </button>
              ))}
            </div>
          )}
        </section>

        <section className={`glass ${styles.card}`} aria-label="How far to trust this">
          <span className="eyebrow">How far to trust this</span>
          {ev ? (
            <>
              <p className={styles.verdict}>Finds about {Math.round(ev.recall * 100)} in 100 droppings, {Math.round(ev.precision * 100)}% of flags correct</p>
              <p className="sub">{ev.note}</p>
            </>
          ) : (
            <>
              <p className={styles.verdict}>Not measured on this camera yet</p>
              <p className="sub">The detector learned from close-up photos. Here it runs zoomed in, keeps only small boxes on bare litter, and flags a spot only when it stays put.</p>
            </>
          )}
          {data && <p className="foot">{data.summary.meanRawBoxesPerFrame ?? "?"} raw boxes a frame before filtering, {data.summary.meanBoxesPerFrame} after. Not used for alerts.</p>}
        </section>
      </aside>
    </div>
  );
}
