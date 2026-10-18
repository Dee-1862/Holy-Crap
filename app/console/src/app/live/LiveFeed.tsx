"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import styles from "./live.module.css";

interface Clip {
  id: string; title: string; view: string; source: string; sourceUrl: string; license: string; bytes: number;
}
type Box = [number, number, number, number, string, number];       // x1, y1, x2, y2 as shares of the frame, class, score
interface Analysis {
  id: string; width: number; height: number; duration: number; rate: number; times: number[];
  tile: number; conf: number; activity: number[]; detections: Box[][];
  summary: { samples: number; meanBoxesPerFrame: number; meanActivity: number };
}

// The last sample at or before time t.
function indexAt(times: number[], t: number) {
  let lo = 0, hi = times.length - 1;
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1;
    if (times[mid] <= t) lo = mid; else hi = mid - 1;
  }
  return lo;
}

// Replays public barn footage as a feed. It is a replay, not a camera, and the page says so.
// Flock motion is measured from the pixels. The detector boxes are experimental and off by default,
// because on these clips they land on birds and equipment, not on droppings.
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
        // optional deep links: /live?clip=pen-dense&boxes=1
        const q = new URLSearchParams(window.location.search);
        setBoxes(q.get("boxes") === "1");
        setId(d.clips.find((c) => c.id === q.get("clip"))?.id ?? d.clips[0]?.id ?? ""); })
      .catch(() => { setClips([]); setHint("The clip service did not answer. Is the console running?"); });
  }, []);

  useEffect(() => {
    if (!id) return;
    setData(null); setNow(0);
    fetch(`/api/live/analysis/${id}`, { cache: "no-store" }).then((r) => (r.ok ? r.json() : null)).then(setData).catch(() => setData(null));
  }, [id]);

  // current time for the numbers and the playhead, a few times a second
  useEffect(() => {
    const timer = window.setInterval(() => { if (video.current) setNow(video.current.currentTime); }, 150);
    return () => window.clearInterval(timer);
  }, []);

  // draw the experimental boxes on top of the video in step with playback
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
          if (boxes && data?.times.length) {
            g.lineWidth = 2 * devicePixelRatio;
            g.strokeStyle = "#ffd60a";
            for (const [x1, y1, x2, y2] of data.detections[indexAt(data.times, v.currentTime)] ?? []) {
              g.strokeRect(x1 * w, y1 * h, (x2 - x1) * w, (y2 - y1) * h);
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
    ? data.activity.map((a, k) => `${k ? "L" : "M"}${(data.times[k] / data.duration) * 300},${60 - (a / max) * 56}`).join(" ")
    : "";

  return (
    <div className={styles.grid}>
      <section className={`glass ${styles.stage}`} aria-label="Replayed camera feed">
        <div className={styles.stageHead}>
          <span className={styles.badge}><i />Replay</span>
          <h2 className="headline">{clip.title}</h2>
          <span className="foot">{clip.view}</span>
        </div>
        <div className={styles.frame} style={{ aspectRatio: data ? `${data.width} / ${data.height}` : "16 / 9" }}>
          <video ref={video} key={clip.id} src={`/api/live/clip/${clip.id}`} autoPlay muted loop playsInline controls={false} />
          <canvas ref={canvas} />
          {boxes && <div className={styles.warn}>Experimental. These boxes are unverified and mostly sit on birds and equipment.</div>}
        </div>
        <div className={styles.controls}>
          <div className="seg" role="group" aria-label="Choose a clip">
            {clips.map((c) => (
              <button key={c.id} aria-pressed={c.id === clip.id} onClick={() => setId(c.id)}>{c.title}</button>
            ))}
          </div>
          <label className="switch">
            <input type="checkbox" checked={boxes} onChange={(e) => setBoxes(e.target.checked)} />
            Show raw detector boxes (experimental)
          </label>
        </div>
        <p className="foot">
          Replay of a public dataset clip, not a live camera. Source: <a href={clip.sourceUrl} target="_blank" rel="noreferrer">{clip.source}</a>, {clip.license}.
        </p>
      </section>

      <aside className={styles.side}>
        <section className={`glass ${styles.card}`} aria-label="Flock motion">
          <span className="eyebrow">Flock motion</span>
          <div className={`${styles.big} num`}>{motion.toFixed(1)}<small>%</small></div>
          <p className="foot">Share of the picture that changed in the last second. Higher means more movement.</p>
          <svg viewBox="0 0 300 64" className={styles.spark} onClick={seek} role="img" aria-label="Motion over the clip, click to jump">
            {data && <path d={`${path} L300,60 L0,60 Z`} className={styles.area} />}
            {data && <path d={path} className={styles.line} />}
            {data && <line x1={(now / data.duration) * 300} x2={(now / data.duration) * 300} y1="0" y2="64" className={styles.head} />}
          </svg>
          <p className="foot">Measured from the video itself. Click the chart to jump.</p>
        </section>

        <section className={`glass ${styles.card}`} aria-label="Detector check">
          <span className="eyebrow">Droppings detector on this footage</span>
          <p className={styles.verdict}>Not reliable on this view</p>
          <p className="sub">
            {data ? <>It put about {data.summary.meanBoxesPerFrame} boxes on each frame of this clip. </> : null}
            Looking at sample frames from these clips, the boxes land on hens, feeders, drinkers and wire mesh, not on droppings.
            The detector learned from close-up photos, where a dropping fills a tenth of the picture. In a pen camera it is a few pixels.
          </p>
          <p className="foot">No dropping labels exist for these clips, so accuracy cannot be measured here. The boxes are not used for alerts.</p>
        </section>
      </aside>
    </div>
  );
}
