import { SUB_AXES } from "@/lib/insight";

interface Props {
  group: number[];       // 0 to 10 per axis
  barn: number[];        // dashed reference series
  color: string;         // css color for the group series
}

const SIZE = 360;
const C = SIZE / 2;
const R = 108;

const point = (i: number, v: number) => {
  const a = -Math.PI / 2 + (i * 2 * Math.PI) / SUB_AXES.length;
  const r = (R * v) / 10;
  return [C + Math.cos(a) * r, C + Math.sin(a) * r] as const;
};
const poly = (vals: number[]) => vals.map((v, i) => point(i, v).join(",")).join(" ");

// Five axis radar. Solid shape is this group, dashed shape is the barn average.
export default function Radar({ group, barn, color }: Props) {
  const weakest = group.indexOf(Math.min(...group));
  return (
    <svg viewBox={`0 0 ${SIZE} ${SIZE}`} role="img" aria-label={`Radar of sub scores. Weakest is ${SUB_AXES[weakest].label}.`} style={{ width: "100%", height: "auto" }}>
      {[0.25, 0.5, 0.75, 1].map((f) => (
        <polygon key={f} points={poly(SUB_AXES.map(() => f * 10))} fill="none" style={{ stroke: "var(--sep)" }} />
      ))}
      {SUB_AXES.map((a, i) => {
        const [x, y] = point(i, 10);
        const [lx, ly] = point(i, 12.9);
        return (
          <g key={a.key}>
            <line x1={C} y1={C} x2={x} y2={y} style={{ stroke: "var(--sep)" }} />
            <text x={lx} y={ly} textAnchor="middle" dominantBaseline="middle" fontSize="12" fill="var(--label-2)" fontWeight="600">{a.label}</text>
          </g>
        );
      })}
      <polygon points={poly(barn)} fill="none" stroke="var(--label-2)" strokeDasharray="4 4" strokeWidth="1.3" />
      <polygon points={poly(group)} fill={color} fillOpacity=".2" stroke={color} strokeWidth="2" strokeLinejoin="round" />
      {group.map((v, i) => {
        const [x, y] = point(i, v);
        return <circle key={i} cx={x} cy={y} r="3.6" fill="#fff" stroke={color} strokeWidth="2" />;
      })}
    </svg>
  );
}
