import { tone } from "@/lib/insight";

const R = 48;
const C = 2 * Math.PI * R;
const COLOR = { good: "var(--good)", warn: "var(--warn)", bad: "var(--bad)" } as const;

// Circular grade gauge. The ring fills in proportion to grade out of 10.
export default function Gauge({ grade }: { grade: number }) {
  return (
    <div className="gauge" role="img" aria-label={`Grade ${grade} out of 10`}>
      <svg viewBox="0 0 112 112" aria-hidden="true">
        <circle className="trk" cx="56" cy="56" r={R} fill="none" strokeWidth="7" />
        <circle
          className="val" cx="56" cy="56" r={R} fill="none" stroke={COLOR[tone(grade)]}
          strokeWidth="7" strokeLinecap="round" strokeDasharray={C} strokeDashoffset={C * (1 - grade / 10)}
        />
      </svg>
      <div className="n"><div><b>{grade}</b><span>GRADE</span></div></div>
    </div>
  );
}
