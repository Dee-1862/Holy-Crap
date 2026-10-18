"use client";

import { useEffect, useState } from "react";
import type { Analysis, Clip } from "@/lib/live";

interface Feed { clip: Clip; data: Analysis & { activity: number[] } }

// Numbers from the same camera feeds the big camera view shows (per pen, the feed with the most spots).
// Spots are what the detector flagged in those feeds. Motion is read where each feed is playing now.
// Measured from the video, not demo data.
export default function CameraPulse({ className, bigClass }: { className: string; bigClass: string }) {
  const [feeds, setFeeds] = useState<Feed[]>([]);
  const [now, setNow] = useState<number | null>(null);

  useEffect(() => {
    fetch("/api/live/clips", { cache: "no-store" }).then((r) => r.json())
      .then((d: { clips: Clip[] }) => Promise.all(d.clips.map((clip) =>
        fetch(`/api/live/analysis/${clip.id}`, { cache: "no-store" }).then((r) => (r.ok ? r.json() : null)).then((data) => (data ? { clip, data } : null)))))
      .then((all) => {
        const best = new Map<string, Feed>();
        for (const f of all.filter((x): x is Feed => !!x)) {
          const cur = best.get(f.clip.pen);
          if (!cur || (f.data.spots?.length ?? 0) > (cur.data.spots?.length ?? 0)) best.set(f.clip.pen, f);
        }
        setFeeds([...best.values()].sort((a, b) => a.clip.pen.localeCompare(b.clip.pen)));
      })
      .catch(() => setFeeds([]));
    setNow(Date.now());
    const t = window.setInterval(() => setNow(Date.now()), 2000);
    return () => window.clearInterval(t);
  }, []);

  let motion = 0;
  if (now !== null) {
    for (const { data } of feeds) {
      const t = (now / 1000) % data.duration;
      let i = 0;
      while (i + 1 < data.times.length && data.times[i + 1] <= t) i++;
      motion += data.activity[i] ?? 0;
    }
  }
  const spots = feeds.reduce((a, f) => a + (f.data.spots?.length ?? 0), 0);

  return (
    <div className={className}>
      <span className="eyebrow">Cameras</span>
      <b className={`${bigClass} num`}>{spots}<small>spots flagged</small></b>
      <span className="foot">
        {feeds.length
          ? `${feeds.map((f) => `${f.clip.pen} ${f.data.spots?.length ?? 0}`).join(", ")}. Flock motion ${(motion / feeds.length).toFixed(1)}% now`
          : "No camera feeds installed"}
      </span>
    </div>
  );
}
