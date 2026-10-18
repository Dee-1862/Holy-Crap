import { GROUPS, SPECIMENS } from "@/lib/data";
import { groupStatus, tone, type Tone } from "@/lib/insight";

export type MapFilter = "all" | "watch" | "action";

interface Props {
  selected: string;
  filter: MapFilter;
  onSelect: (groupId: string) => void;
}

const COLOR: Record<Tone, string> = { good: "var(--good)", warn: "var(--warn)", bad: "var(--bad)" };
const PEN_W = 200;
const PEN_H = 132;
const GAP = 14;

// Spread birds with a small hash so they look scattered, and the same on every render.
const hash = (n: number) => { const v = Math.sin(n * 127.1 + 311.7) * 43758.5453; return v - Math.floor(v); };

// Pens sit in a grid. The letter picks the column and the number picks the row, so B2 is column B, row 2.
const slot = (id: string) => ({ col: id.charCodeAt(0) - 65, row: Number(id.slice(1)) - 1 });
const passes = (level: Tone, f: MapFilter) => f === "all" || (f === "watch" ? level !== "good" : level === "bad");

// Floor plan as a grid of tiles. Each tile shows its birds as faint dots and a pin for every
// specimen found in the last hour, colored by grade. The selected tile gets a white outline.
export default function SiteMap({ selected, filter, onSelect }: Props) {
  const W = 3 * PEN_W + 2 * GAP;
  const H = 2 * PEN_H + GAP;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} role="group" aria-label="Barn floor plan" style={{ width: "100%", height: "auto", display: "block" }}>
      {GROUPS.map((g) => {
        const { col, row } = slot(g.id);
        const x = col * (PEN_W + GAP);
        const y = row * (PEN_H + GAP);
        const st = groupStatus(g);
        const on = selected === g.id;
        const color = COLOR[st.level];
        const birds = Array.from({ length: g.n }, (_, i) => ({
          bx: x + 16 + hash(i + g.n * 3) * (PEN_W - 32),
          by: y + 42 + hash(i * 1.7 + 9 + g.n) * (PEN_H - 78),
        }));
        return (
          <g
            key={g.id} opacity={passes(st.level, filter) ? 1 : 0.3} style={{ cursor: "pointer", transition: "opacity .2s" }}
            role="button" tabIndex={0} aria-label={`${g.name}, ${st.bad} abnormal`} aria-pressed={on}
            onClick={() => onSelect(g.id)}
            onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onSelect(g.id); } }}
          >
            <rect x={x} y={y} width={PEN_W} height={PEN_H} rx="20" style={{ fill: "var(--card)", stroke: on ? "var(--label)" : "transparent", strokeWidth: 2 }} />
            {birds.map((b, i) => <circle key={i} cx={b.bx} cy={b.by} r="2" style={{ fill: "var(--label-3)" }} />)}
            {SPECIMENS.filter((s) => s.group === g.id && s.minsAgo <= 60).map((s) => (
              <circle key={s.id} cx={x + 16 + s.region[0] * (PEN_W - 32)} cy={y + 40 + s.region[1] * (PEN_H - 70)} r="6" fill={COLOR[tone(s.grade)]} style={{ stroke: "var(--card)", strokeWidth: 2 }} />
            ))}
            <circle cx={x + 18} cy={y + 22} r="4.5" fill={color} />
            <text x={x + 30} y={y + 27} fontSize="15" fontWeight="600" style={{ fill: "var(--label)" }}>{g.name}</text>
            <text x={x + PEN_W - 16} y={y + 27} fontSize="14" fontWeight="600" textAnchor="end" fill={color}>
              {st.mean === null ? "n/a" : st.mean.toFixed(1)}
            </text>
            <text x={x + 16} y={y + PEN_H - 13} fontSize="13" fontWeight="500" fill={st.bad ? COLOR.bad : undefined} style={st.bad ? undefined : { fill: "var(--label-2)" }}>{st.bad ? `${st.bad} abnormal` : "All normal"}</text>
            <text x={x + PEN_W - 16} y={y + PEN_H - 13} fontSize="13" textAnchor="end" style={{ fill: "var(--label-3)" }}>{g.n} birds</text>
          </g>
        );
      })}
    </svg>
  );
}
