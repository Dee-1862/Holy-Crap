"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { clock, type Analysis, type Clip, type Spot } from "@/lib/live";
import SpotSheet from "./SpotSheet";
import styles from "./camera.module.css";

const BEFORE = 3, AFTER = 5;   // seconds of video shown around each spot

// The selected pen's camera, playing only the short snips where the detector flagged a spot, one after another.
// A ring marks the spot. Tapping the ring or a thumbnail opens the zoomed explanation.
export default function CameraLoop({ pen }: { pen: string }) {
  const [feed, setFeed] = useState<{ clip: Clip; data: Analysis } | "nocam" | undefined>(undefined);   // undefined while loading
  const [k, setK] = useState(0);
  const [open, setOpen] = useState<number | null>(null);
  const video = useRef<HTMLVideoElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);

  // the camera for this pen with the most spots (the test clip when there is one)
  useEffect(() => {
    let live = true;
    setFeed(undefined); setK(0); setOpen(null);
    fetch("/api/live/clips", { cache: "no-store" }).then((r) => r.json())
      .then(async (d: { clips: Clip[] }) => {
        const mine = d.clips.filter((c) => c.pen === pen);
        const all = await Promise.all(mine.map((clip) => fetch(`/api/live/analysis/${clip.id}`, { cache: "no-store" })
          .then((r) => (r.ok ? r.json() : null)).then((data: Analysis | null) => (data ? { clip, data } : null)).catch(() => null)));
        const best = all.filter((x): x is { clip: Clip; data: Analysis } => !!x)
          .sort((a, b) => ((b.data.spots?.length ?? 0) - (a.data.spots?.length ?? 0)))[0];
        if (live) setFeed(best ?? "nocam");
      })
      .catch(() => { if (live) setFeed("nocam"); });
    return () => { live = false; };
  }, [pen]);

  const spots: Spot[] = (typeof feed === "object" && feed.data.spots) || [];
  const spot = spots[k];

  // hold the picture still while a spot is open, so the loop does not move on behind the sheet
  useEffect(() => {
    const v = video.current;
    if (!v) return;
    if (open !== null) v.pause(); else v.play().catch(() => {});
  }, [open]);

  const jump = useCallback(() => {
    const v = video.current;
    if (v && spot) v.currentTime = Math.max(0, spot.t - BEFORE);
  }, [spot]);
  useEffect(() => { jump(); }, [jump]);

  // move to the next snip once this one has played, and draw the ring
  useEffect(() => {
    let raf = 0;
    const tick = () => {
      const v = video.current, c = canvas.current;
      if (v && spot) {
        if (v.currentTime > spot.t + AFTER || v.currentTime < spot.t - BEFORE - 1) {
          if (spots.length > 1 && v.currentTime > spot.t + AFTER) setK((x) => (x + 1) % spots.length);
          else v.currentTime = Math.max(0, spot.t - BEFORE);
        }
        if (c) {
          const w = c.clientWidth * devicePixelRatio, h = c.clientHeight * devicePixelRatio;
          if (c.width !== w || c.height !== h) { c.width = w; c.height = h; }
          const g = c.getContext("2d");
          if (g) {
            g.clearRect(0, 0, w, h);
            if (v.currentTime >= spot.t - 0.3) {
              const [x1, y1, x2, y2] = spot.box;
              g.lineWidth = 2.5 * devicePixelRatio;
              g.strokeStyle = "#30d158";
              g.beginPath();
              g.arc(((x1 + x2) / 2) * w, ((y1 + y2) / 2) * h, 18 * devicePixelRatio, 0, Math.PI * 2);
              g.stroke();
            }
          }
        }
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [spot, spots.length]);

  if (feed === undefined) return <section className={`glass ${styles.card} ${styles.empty}`} aria-label={`Pen ${pen} camera`} />;
  if (feed === "nocam") {
    return (
      <section className={`glass ${styles.card} ${styles.empty}`} aria-label={`Pen ${pen} camera`}>
        <h2 className="headline">Pen {pen}</h2>
        <p className="sub">Camera offline right now. No video or readings from this pen until it reconnects.</p>
      </section>
    );
  }

  const { clip, data } = feed;
  const keyed = data.truth?.length ?? 0;
  const found = data.truth?.filter((t) => t.foundAt !== null).length ?? 0;

  return (
    <section className={`glass ${styles.card}`} aria-label={`Pen ${pen} camera`}>
      <div className={styles.head}>
        <h2 className="headline">Pen {pen} camera</h2>
        <span className="pill">{clip.test ? "Test clip" : "Replay"}</span>
        <span className={styles.grow} />
        <Link href={`/live?clip=${clip.id}`} className={styles.open}>Open in Live</Link>
      </div>
      <div className={styles.frame} style={{ aspectRatio: `${data.width} / ${data.height}` }}>
        <video ref={video} src={`/api/live/clip/${clip.id}`} autoPlay muted playsInline loop={!spot} onLoadedMetadata={jump} />
        <canvas ref={canvas} />
        {spot && <button className={styles.hit} aria-label={`Explain spot ${k + 1}`} onClick={() => setOpen(k)}
          style={{ left: `${((spot.box[0] + spot.box[2]) / 2) * 100}%`, top: `${((spot.box[1] + spot.box[3]) / 2) * 100}%` }} />}
        <span className={styles.label}>{spot ? `Spot ${k + 1} of ${spots.length} · ${clock(spot.t)}` : "Nothing flagged on this camera"}</span>
      </div>
      <div className={styles.thumbs}>
        {spots.map((s, i) => (
          <button key={i} aria-pressed={i === k} onClick={() => { setK(i); setOpen(i); }} title={`Spot ${i + 1} at ${clock(s.t)}`}>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={s.crop} alt={`Spot ${i + 1}`} />
            <span>{i + 1}</span>
            {clip.test && !s.truth && <em className={styles.falseTag}>False flag</em>}
          </button>
        ))}
      </div>
      <p className="foot">
        {spot ? "Only the moments where the detector flagged a spot, looped. Tap a spot for the zoomed view and the reasons." : "The detector found nothing it was sure of, so the whole video plays."}
        {keyed ? ` Answer key on this test clip: ${found} of ${keyed} pasted droppings found.` : " Spots are leads to check, not confirmed droppings."}
      </p>
      {open !== null && spots[open] && <SpotSheet spot={spots[open]} n={open + 1} clip={clip} onClose={() => setOpen(null)} />}
    </section>
  );
}
