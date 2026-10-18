"use client";

import { useEffect, useState } from "react";
import type { Analysis, Clip } from "@/lib/live";

interface Feed { clip: Clip; data: Analysis & { activity: number[] } }

// Numbers from the same camera feeds the big camera view shows (per pen, the feed with the most spots).
// Droppings only count on the test clip, where test droppings were pasted in at known times: on real whole-pen
// footage the pen model found 0 real droppings in 34 boxes (docs/audits/dropping4-pen-real-frames.md), so those
// feeds are used for behaviour only. Motion is read where each feed is playing now. Measured from the video.
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
  const tests = feeds.filter((f) => f.clip.test && f.data.truth?.length);
  const keyed = tests.reduce((a, f) => a + (f.data.truth?.length ?? 0), 0);
  const found = tests.reduce((a, f) => a + (f.data.truth?.filter((t) => t.foundAt !== null).length ?? 0), 0);

  return (
    <div className={className}>
      <span className="eyebrow">Cameras</span>
      {keyed
        ? <b className={`${bigClass} num`}>{found}<small>of {keyed} test droppings found</small></b>
        : <b className={`${bigClass} num`}>{feeds.length}<small>cameras</small></b>}
      <span className="foot">
        {feeds.length
          ? `${keyed ? `Pasted into the ${tests.map((f) => f.clip.pen).join(", ")} test clip. ` : ""}Real pen footage is read for behaviour. Flock motion ${(motion / feeds.length).toFixed(1)}% now`
          : "No camera feeds installed"}
      </span>
    </div>
  );
}
