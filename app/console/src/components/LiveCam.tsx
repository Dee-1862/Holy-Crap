"use client";

import { useEffect, useState } from "react";
import styles from "./camera.module.css";

export const LIVE_CAM = "CAM4";

interface Bundle { frames: { jpeg: string; t: number }[]; w: number; h: number; source: string; at: number }

// Cam 4: the Pi's own Camera Module 3. While this view is open the Pi takes 4 small pictures a second and uploads
// them as one bundle a second; this page plays each bundle back at the pace it was taken, about a second behind live.
// Otherwise it checks every 10 s, enough for the Live tag. Nothing from this camera feeds the demo numbers.
export function useLiveFrame(watching: boolean): Bundle | null | undefined {
  const [bundle, setBundle] = useState<Bundle | null | undefined>(undefined);
  useEffect(() => {
    let alive = true, timer = 0;
    const get = async () => {
      const t0 = Date.now();
      try {
        const d = (await (await fetch(`/api/edge/frame${watching ? "?watch=1" : ""}`, { cache: "no-store" })).json()) as { frame: Bundle | null };
        if (alive) setBundle((cur) => (cur && d.frame && last(d.frame) <= last(cur) ? cur : d.frame));
      } catch {
        if (alive) setBundle(null);
      }
      // one request at a time: the next one starts when this one is back
      if (alive) timer = window.setTimeout(get, Math.max(0, (watching ? 1000 : 10000) - (Date.now() - t0)));
    };
    get();
    return () => { alive = false; window.clearTimeout(timer); };
  }, [watching]);
  return bundle;
}

const last = (b: Bundle) => b.frames[b.frames.length - 1]?.t ?? 0;

// Shows each picture of a new bundle at the moment it was taken, counted from the first one.
function usePlayback(bundle: Bundle | null | undefined): string | null {
  const [shown, setShown] = useState<string | null>(null);
  useEffect(() => {
    if (!bundle?.frames.length) return;
    const t0 = bundle.frames[0].t;
    const timers = bundle.frames.map((f) => window.setTimeout(() => setShown(f.jpeg), (f.t - t0) * 1000));
    return () => timers.forEach(window.clearTimeout);
  }, [bundle]);
  return shown;
}

export default function LiveCam({ frame }: { frame: Bundle | null | undefined }) {
  const jpeg = usePlayback(frame);
  if (frame === undefined) return <section className={`glass ${styles.card} ${styles.empty}`} aria-label="Cam 4" />;
  if (!frame) {
    return (
      <section className={`glass ${styles.card} ${styles.empty}`} aria-label="Cam 4">
        <h2 className="headline">Cam 4 · Pi camera</h2>
        <p className="sub">The Pi has not sent a picture in the last 15 seconds. It shows here again once the Pi is back on Wi-Fi.</p>
      </section>
    );
  }
  return (
    <section className={`glass ${styles.card}`} aria-label="Cam 4">
      <div className={styles.head}>
        <h2 className="headline">Cam 4 · Pi camera</h2>
        <span className="pill">{frame.source === "camera" ? <><i />Live</> : "Recorded footage"}</span>
        <span className={styles.grow} />
      </div>
      <div className={styles.frame} style={{ aspectRatio: `${frame.w} / ${frame.h}` }}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        {jpeg && <img className={styles.still} src={`data:image/jpeg;base64,${jpeg}`} alt="Live picture from the Pi camera" />}
      </div>
    </section>
  );
}
