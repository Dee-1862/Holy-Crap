import type { TimelinePoint } from "../types";

interface TimelineChartProps {
  points: TimelinePoint[];
  selectedTime: number;
  onSelectTime: (time: number) => void;
  alertThreshold?: number;
}

const WIDTH = 900;
const HEIGHT = 280;
const LEFT = 44;
const RIGHT = 16;
const TOP = 18;
const SCORE_HEIGHT = 112;
const COUNTS_TOP = 168;
const COUNTS_HEIGHT = 78;

function pathFor(
  points: TimelinePoint[],
  value: (point: TimelinePoint) => number,
  maxTime: number,
  maxValue: number,
  top: number,
  height: number,
): string {
  return points
    .map((point, index) => {
      const x = LEFT + (point.t_s / maxTime) * (WIDTH - LEFT - RIGHT);
      const y = top + height - (value(point) / maxValue) * height;
      return `${index === 0 ? "M" : "L"}${x.toFixed(2)} ${y.toFixed(2)}`;
    })
    .join(" ");
}

export function TimelineChart({ points, selectedTime, onSelectTime, alertThreshold }: TimelineChartProps) {
  if (!points.length) {
    return <div className="chart-empty">Timeline data will appear after a run completes.</div>;
  }

  const maxTime = Math.max(points.at(-1)?.t_s ?? 1, 1);
  const maxCount = Math.max(...points.map((point) =>
    point.susceptible + point.exposed + point.infectious + point.clinical), 1);
  const selectedX = LEFT + (selectedTime / maxTime) * (WIDTH - LEFT - RIGHT);

  function selectFromPointer(event: React.PointerEvent<SVGSVGElement>) {
    const bounds = event.currentTarget.getBoundingClientRect();
    const viewX = ((event.clientX - bounds.left) / bounds.width) * WIDTH;
    const ratio = Math.max(0, Math.min(1, (viewX - LEFT) / (WIDTH - LEFT - RIGHT)));
    onSelectTime(ratio * maxTime);
  }

  return (
    <svg
      className="timeline-svg"
      viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
      role="img"
      aria-label="Truth and predicted anomaly scores, followed by bird health-state counts over time"
      onPointerDown={selectFromPointer}
    >
      <g className="chart-guides" aria-hidden="true">
        {[0, 0.5, 1].map((tick) => {
          const y = TOP + SCORE_HEIGHT - tick * SCORE_HEIGHT;
          return <line key={tick} x1={LEFT} y1={y} x2={WIDTH - RIGHT} y2={y} />;
        })}
        <line x1={LEFT} y1={COUNTS_TOP} x2={WIDTH - RIGHT} y2={COUNTS_TOP} />
        <line x1={LEFT} y1={COUNTS_TOP + COUNTS_HEIGHT} x2={WIDTH - RIGHT} y2={COUNTS_TOP + COUNTS_HEIGHT} />
      </g>
      <g className="chart-axis" aria-hidden="true">
        <text x="8" y={TOP + 4}>1.0</text>
        <text x="8" y={TOP + SCORE_HEIGHT + 4}>0.0</text>
        <text x="8" y={COUNTS_TOP + 4}>{maxCount}</text>
        <text x="8" y={COUNTS_TOP + COUNTS_HEIGHT + 4}>0</text>
        <text x={LEFT} y="270">0 s</text>
        <text x={WIDTH - RIGHT} y="270" textAnchor="end">{maxTime.toFixed(0)} s</text>
      </g>
      {alertThreshold == null ? null : (
        <line
          className="chart-threshold"
          x1={LEFT}
          y1={TOP + SCORE_HEIGHT - alertThreshold * SCORE_HEIGHT}
          x2={WIDTH - RIGHT}
          y2={TOP + SCORE_HEIGHT - alertThreshold * SCORE_HEIGHT}
        />
      )}
      <path className="chart-line chart-line--truth" d={pathFor(points, (p) => p.truth_score, maxTime, 1, TOP, SCORE_HEIGHT)} />
      <path className="chart-line chart-line--prediction" d={pathFor(points, (p) => p.predicted_score, maxTime, 1, TOP, SCORE_HEIGHT)} />
      <path className="chart-line chart-line--susceptible" d={pathFor(points, (p) => p.susceptible, maxTime, maxCount, COUNTS_TOP, COUNTS_HEIGHT)} />
      <path className="chart-line chart-line--exposed" d={pathFor(points, (p) => p.exposed, maxTime, maxCount, COUNTS_TOP, COUNTS_HEIGHT)} />
      <path className="chart-line chart-line--infectious" d={pathFor(points, (p) => p.infectious, maxTime, maxCount, COUNTS_TOP, COUNTS_HEIGHT)} />
      <path className="chart-line chart-line--clinical" d={pathFor(points, (p) => p.clinical, maxTime, maxCount, COUNTS_TOP, COUNTS_HEIGHT)} />
      <line className="chart-cursor" x1={selectedX} x2={selectedX} y1={TOP} y2={COUNTS_TOP + COUNTS_HEIGHT} />
    </svg>
  );
}
