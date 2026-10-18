"use client";

import { useEffect, useState } from "react";
import styles from "./camera.module.css";

export const LIVE_CAM = "CAM4";

interface Frame { jpeg: string; t: number; w: number; h: number; source: string; spots: { id: string; cx: number; cy: number; t: number }[]; at: number }

// Cam 4: the Pi's own Camera Module 3. The Pi runs the spot finder and the detector on it at 2 frames a second and
// sends a small picture here every couple of seconds. Nothing from this camera feeds the demo numbers on this page.
export function useLiveFrame(): Frame | null | undefined {
  const [frame, setFrame] = useState<Frame | null | undefined>(undefined);
  useEffect(() => {
    let alive = true;
    const get = () => fetch("/api/edge/frame", { cache: "no-store" }).then((r) => r.json())
      .then((d: { frame: Frame | null }) => { if (alive) setFrame(d.frame); })
      .catch(() => { if (alive) setFrame(null); });
    get();
    const t = window.setInterval(get, 2000);
    return () => { alive = false; window.clearInterval(t); };
  }, []);
  return frame;
}

const ago = (s: number) => (s < 60 ? `${Math.max(0, Math.round(s))} s ago` : `${Math.round(s / 60)} min ago`);

export default function LiveCam({ frame }: { frame: Frame | null | undefined }) {
  if (frame === undefined) return <section className={`glass ${styles.card} ${styles.empty}`} aria-label="Cam 4" />;
  if (!frame) {
    return (
      <section className={`glass ${styles.card} ${styles.empty}`} aria-label="Cam 4">
        <h2 className="headline">Cam 4 · Pi camera</h2>
        <p className="sub">The Pi has not sent a picture in the last 15 seconds. It shows here again once the Pi is back on Wi-Fi.</p>
      </section>
    );
  }
  const live = frame.source === "camera";
  const now = frame.t;
  const recent = frame.spots.filter((s) => now - s.t < 600);
  return (
    <section className={`glass ${styles.card}`} aria-label="Cam 4">
      <div className={styles.head}>
        <h2 className="headline">Cam 4 · Pi camera</h2>
        <span className="pill">{live ? <><i />Live</> : "Recorded footage"}</span>
        <span className={styles.grow} />
      </div>
      <div className={styles.frame} style={{ aspectRatio: `${frame.w} / ${frame.h}` }}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img className={styles.still} src={`data:image/jpeg;base64,${frame.jpeg}`} alt="Newest picture from the Pi camera" />
        {recent.map((s, i) => (
          <span key={s.id ?? i} className={styles.liveSpot} style={{ left: `${s.cx * 100}%`, top: `${s.cy * 100}%` }} title={`Spot found ${ago(now - s.t)}`} />
        ))}
        <span className={styles.label}>{recent.length ? `${recent.length} still ${recent.length === 1 ? "spot" : "spots"} in the last 10 min` : "Nothing flagged yet"}</span>
      </div>
      <p className="foot">
        {live ? "Raspberry Pi Camera Module 3 on the QNX Pi" : "The Pi is playing recorded footage"}. The Pi finds still spots and runs the
        detector on them itself, 2 frames a second, and sends a picture here every 2 seconds. Readings from this camera are
        not part of the demo numbers above.
      </p>
    </section>
  );
}
