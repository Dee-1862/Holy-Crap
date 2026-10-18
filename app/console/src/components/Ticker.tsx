import { feedLines } from "@/lib/insight";

// Scrolling live feed. The list is repeated once so the loop has no jump.
// Motion stops on hover and for people who prefer reduced motion.
export default function Ticker() {
  const lines = feedLines();
  return (
    <div className="ticker glass" role="marquee" aria-label="Live feed">
      <span className="tk-label eyebrow">Live feed</span>
      <div className="tk-track">
        <div className="tk-run">
          {[...lines, ...lines].map((l, i) => <span key={i} className="tk-item">{l}</span>)}
        </div>
      </div>
    </div>
  );
}
