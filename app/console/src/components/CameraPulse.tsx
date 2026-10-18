"use client";

import { useEffect, useState } from "react";
import type { Analysis, Clip } from "@/lib/live";

interface Feed { clip: Clip; data: Analysis & { activity: number[] } }

// Live numbers from the camera feeds, read at the point each feed is playing now (feeds run on the clock).
// Spots are counted over the last 15 minutes of each feed. Measured from the video, not demo data.
export default function CameraPulse({ className, bigClass }: { className: string; bigClass: string }) {
  const [feeds, setFeeds] = useState<Feed[]>([]);
  const [now, setNow] = useState<number | null>(null);

  useEffect(() => {
    fetch("/api/live/clips", { cache: "no-store" }).then((r) => r.json())
      .then((d: { clips: Clip[] }) => Promise.all(d.clips.filter((c) => !c.test).map((clip) =>
        fetch(`/api/live/analysis/${clip.id}`, { cache: "no-store" }).then((r) => (r.ok ? r.json() : null)).then((data) => (data ? { clip, data } : null)))))
      .then((all) => setFeeds(all.filter((x): x is Feed => !!x)))
      .catch(() => setFeeds([]));
    setNow(Date.now());
    const t = window.setInterval(() => setNow(Date.now()), 2000);
    return () => window.clearInterval(t);
  }, []);

  let spots = 0, motion = 0;
  if (now !== null) {
    for (const { data } of feeds) {
      const t = (now / 1000) % data.duration;                 // where this feed is playing right now
      let i = 0;
      while (i + 1 < data.times.length && data.times[i + 1] <= t) i++;
      motion += data.activity[i] ?? 0;
      spots += (data.spots ?? []).filter((s) => s.t <= t && s.t > t - 900).length;
    }
  }
  const cams = new Set(feeds.map((f) => f.clip.pen)).size;

  return (
    <div className={className}>
      <span className="eyebrow">Cameras</span>
      <b className={`${bigClass} num`}>{spots}<small>spots in 15 min</small></b>
      <span className="foot">{cams ? `${cams} cameras, flock motion ${(motion / Math.max(1, feeds.length)).toFixed(1)}% now` : "No camera feeds installed"}</span>
    </div>
  );
}
