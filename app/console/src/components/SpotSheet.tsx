"use client";

import Link from "next/link";
import { useEffect } from "react";
import { CLASS_NAME, clock, type Clip, type ClassKey, type Spot } from "@/lib/live";
import styles from "./camera.module.css";

// One flagged spot, zoomed in. The numbers on the picture match the numbered reasons below it.
// Every reason is measured from the video or read from the model, see explain() in app/live-feed/analyze_clips.py.
export default function SpotSheet({ spot, n, clip, onClose }: { spot: Spot; n: number; clip: Clip; onClose: () => void }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const [x1, y1, x2, y2] = spot.cropBox;
  const pad = 10 / 96;                                  // the litter ring measured around the box, 10 pixels wide
  const ranked = (Object.entries(spot.scores) as [ClassKey, number][]).sort((a, b) => b[1] - a[1]);

  return (
    <>
      <button className="scrim" aria-label="Close spot" onClick={onClose} />
      <aside className="glass sheet" aria-label={`Spot ${n}`}>
        <button className="sheet-close" onClick={onClose}>Done</button>
        <div className="head">
          <span className="eyebrow">Pen {clip.pen} · {clip.test ? "test clip" : "replay"} · {clock(spot.t)}</span>
          <h2 className="headline" style={{ margin: "4px 0 12px" }}>Spot {n}</h2>
        </div>

        <div className={styles.zoom}>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={spot.crop} alt={`Zoomed view of spot ${n}`} />
          <svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden>
            <rect x={(x1 - pad) * 100} y={(y1 - pad) * 100} width={(x2 - x1 + 2 * pad) * 100} height={(y2 - y1 + 2 * pad) * 100} className={styles.ringArea} />
            <rect x={x1 * 100} y={y1 * 100} width={(x2 - x1) * 100} height={(y2 - y1) * 100} className={styles.boxArea} />
          </svg>
          <span className={styles.marker} style={{ left: `${x2 * 100}%`, top: `${y1 * 100}%` }}>1</span>
          <span className={styles.marker} style={{ left: `${(x1 - pad) * 100}%`, top: `${(y2 + pad) * 100}%` }}>2</span>
        </div>
        <p className="foot" style={{ marginTop: 6 }}>Shown three times larger than the camera sees it. The camera sees this spot as about {spot.sizePx} pixels across.</p>

        <ol className={styles.reasons}>
          <li>
            <b>Small and staying put.</b> The box is {spot.sizePx} pixels long, the size of a dropping in this camera (8 to 30).
            It was found in {spot.seen} of the last {spot.window} checks, so it did not walk away like a bird.
          </li>
          <li>
            <b>Stands out from the litter around it.</b> {spot.darker > 0 ? `${spot.darker}% darker` : `${-spot.darker}% lighter`} than the
            ring of litter marked 2, with a colour shift of {spot.colourShift}.
          </li>
          <li>
            <b>New on the floor.</b> It differs from the empty floor image of this camera by {spot.vsBackground} on a 0 to 255 scale.
          </li>
          <li>
            <b>What the model thinks it is.</b> Scores for each class, highest first. They are separate scores, not shares that add up to 100.
            <div className={styles.scores}>
              {ranked.map(([k, p]) => (
                <div key={k} className={styles.scoreRow}>
                  <span>{CLASS_NAME[k]}</span>
                  <i><s style={{ width: `${Math.round(p * 100)}%` }} /></i>
                  <b className="num">{p.toFixed(2)}</b>
                </div>
              ))}
            </div>
            At this size the disease guess is weak (0.65 mAP50 on the pen test). Use it to find the spot, then take a close-up to judge it.
          </li>
          {spot.truth && (
            <li>
              <b>Answer key.</b> This is a test dropping pasted from a {CLASS_NAME[spot.truth.cls]} photo the model never trained on.
              The model guessed {CLASS_NAME[spot.cls]}{spot.cls === spot.truth.cls ? ", which is right." : ", which is wrong."}
            </li>
          )}
        </ol>

        <section className={styles.closeup} aria-label="Close-up check">
          <span className="eyebrow">Close-up check</span>
          {spot.truth?.closeup ? (() => {
            const c = spot.truth.closeup;
            const top = c.scores ? (Object.entries(c.scores) as [ClassKey, number][]).sort((a, b) => b[1] - a[1])[0] : null;
            return (
              <>
                <div className={styles.closeImg}>
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={c.img} alt="Close-up photo this test dropping was cut from" />
                  {c.box && <span className={styles.closeBox} style={{ left: `${c.box[0] * 100}%`, top: `${c.box[1] * 100}%`, width: `${(c.box[2] - c.box[0]) * 100}%`, height: `${(c.box[3] - c.box[1]) * 100}%` }} />}
                </div>
                <p className="sub" style={{ margin: "8px 0 0" }}>
                  {top ? <>The close-up model reads this as <b>{CLASS_NAME[top[0]]}</b> ({top[1].toFixed(2)}){top[0] === spot.truth.cls ? ", which matches the answer key." : ", which does not match the answer key."}</> : "The close-up model found nothing here."}
                </p>
                <p className="foot">This is the real close-up photo this test dropping was cut from, not what the pen camera saw. It shows the second step: the camera finds a spot, a close-up judges it. The close-up model never trained on this photo.</p>
              </>
            );
          })() : <p className="foot">No close-up yet. On a farm the Pi would zoom in here or a worker would take a photo, and the close-up model would judge it.</p>}
        </section>

        <Link href={`/live?clip=${clip.id}&t=${Math.max(0, spot.t - 3).toFixed(1)}`} className={styles.open}>Watch this moment in Live</Link>
      </aside>
    </>
  );
}
