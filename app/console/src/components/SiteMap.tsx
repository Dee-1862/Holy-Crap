import { GROUPS, SPECIMENS } from "@/lib/data";
import { groupStatus, tone, type Tone } from "@/lib/insight";

export type MapFilter = "all" | "watch" | "action";

interface Props {
  selected: string;
  filter: MapFilter;
  onSelect: (groupId: string) => void;
}

const COLOR: Record<Tone, string> = { good: "var(--good)", warn: "var(--warn)", bad: "var(--bad)" };
const PEN_W = 236;
const PEN_H = 196;
const GAP = 34;
const X0 = 70;
const Y0 = 70;

// Pens sit in a grid. The letter picks the column and the number picks the row, so B2 is column B, row 2.
const slot = (id: string) => ({ col: id.charCodeAt(0) - 65, row: Number(id.slice(1)) - 1 });
const passes = (level: Tone, f: MapFilter) => f === "all" || (f === "watch" ? level !== "good" : level === "bad");

// Floor plan of the barn. Each pen shows its birds as dots, its camera with a view cone,
// and a pin for every specimen found in the last hour, colored by grade.
export default function SiteMap({ selected, filter, onSelect }: Props) {
  const W = X0 * 2 + 3 * PEN_W + 2 * GAP;
  const H = Y0 * 2 + 2 * PEN_H + GAP;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} role="group" aria-label="Barn floor plan" style={{ width: "100%", height: "auto", display: "block" }}>
      <rect x="14" y="14" width={W - 28} height={H - 28} rx="34" fill="rgba(255,255,255,.28)" stroke="rgba(255,255,255,.8)" />
      <text x="44" y="46" fontSize="11" letterSpacing="2.4" fill="var(--ink-3)" fontWeight="700">BARN FLOOR</text>
      <line x1={X0 + PEN_W + GAP / 2} x2={X0 + PEN_W + GAP / 2} y1="60" y2={H - 40} stroke="rgba(13,43,51,.12)" strokeDasharray="3 7" />
      <line x1={X0 + 2 * PEN_W + 1.5 * GAP} x2={X0 + 2 * PEN_W + 1.5 * GAP} y1="60" y2={H - 40} stroke="rgba(13,43,51,.12)" strokeDasharray="3 7" />

      {GROUPS.map((g) => {
        const { col, row } = slot(g.id);
        const x = X0 + col * (PEN_W + GAP);
        const y = Y0 + row * (PEN_H + GAP);
        const st = groupStatus(g);
        const on = selected === g.id;
        const dim = !passes(st.level, filter);
        const color = COLOR[st.level];
        const birds = Array.from({ length: g.n }, (_, i) => ({
          bx: x + 26 + ((i * 53) % (PEN_W - 52)),
          by: y + 70 + ((i * 37) % (PEN_H - 100)),
        }));
        return (
          <g
            key={g.id} transform="translate(0,0)" opacity={dim ? 0.28 : 1} style={{ cursor: "pointer", transition: "opacity .2s" }}
            role="button" tabIndex={0} aria-label={`${g.name}, ${st.bad} abnormal`} aria-pressed={on}
            onClick={() => onSelect(g.id)}
            onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onSelect(g.id); } }}
          >
            <rect x={x} y={y} width={PEN_W} height={PEN_H} rx="22" fill={on ? "rgba(255,255,255,.78)" : "rgba(255,255,255,.5)"} stroke={color} strokeWidth={on ? 2.6 : 1.4} />
            {on && <rect x={x - 5} y={y - 5} width={PEN_W + 10} height={PEN_H + 10} rx="26" fill="none" stroke={color} strokeOpacity=".35" strokeWidth="1.5" />}
            {/* camera and view cone */}
            <polygon points={`${x + PEN_W / 2},${y + 26} ${x + 24},${y + PEN_H - 14} ${x + PEN_W - 24},${y + PEN_H - 14}`} fill={color} fillOpacity=".06" />
            <circle cx={x + PEN_W / 2} cy={y + 22} r="6" fill="var(--ink)" />
            {birds.map((b, i) => <circle key={i} cx={b.bx} cy={b.by} r="2.6" fill="rgba(13,43,51,.28)" />)}
            {/* specimen pins */}
            {SPECIMENS.filter((s) => s.group === g.id && s.minsAgo <= 60).map((s) => (
              <circle key={s.id} cx={x + 20 + s.region[0] * (PEN_W - 40)} cy={y + 50 + s.region[1] * (PEN_H - 80)} r="7" fill={COLOR[tone(s.grade)]} stroke="#fff" strokeWidth="2" />
            ))}
            <text x={x + 18} y={y + 28} fontSize="13" fontWeight="700" fill="var(--ink)">{g.name}</text>
            <text x={x + PEN_W - 18} y={y + 28} fontSize="13" fontWeight="700" textAnchor="end" fill={color}>
              {st.mean === null ? "n/a" : st.mean.toFixed(1)}
            </text>
            <text x={x + 18} y={y + PEN_H - 14} fontSize="11" fill="var(--ink-3)" fontWeight="600">{g.n} birds, {st.bad} abnormal</text>
          </g>
        );
      })}
    </svg>
  );
}
