import { tone } from "@/lib/insight";

const R = 46;
const C = 2 * Math.PI * R;
const COLOR = { good: "var(--good)", warn: "var(--warn)", bad: "var(--bad)" } as const;

// Circular grade gauge. A thin ring fills in proportion to grade out of 10.
// The number sits in the middle with the label tucked underneath so nothing overlaps the ring.
export default function Gauge({ grade }: { grade: number }) {
  return (
    <div className="gauge" role="img" aria-label={`Grade ${grade} out of 10`}>
      <svg viewBox="0 0 104 104" aria-hidden="true">
        <circle className="trk" cx="52" cy="52" r={R} fill="none" strokeWidth="4" />
        <circle
          className="val" cx="52" cy="52" r={R} fill="none" stroke={COLOR[tone(grade)]}
          strokeWidth="4" strokeLinecap="round" strokeDasharray={C} strokeDashoffset={C * (1 - grade / 10)}
        />
      </svg>
      <div className="n"><b>{grade}</b><span>GRADE</span></div>
    </div>
  );
}
