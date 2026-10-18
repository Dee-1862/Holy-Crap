import type { Snapshot } from "../types";

interface PenViewportProps {
  snapshot?: Snapshot;
  showTruth: boolean;
  showPredictions: boolean;
  penWidthM?: number;
  penHeightM?: number;
}

const gridLines = Array.from({ length: 11 }, (_, index) => index * 100);

function stateClass(state: string): string {
  const normalized = state.toLowerCase();
  if (normalized.includes("clinical") || normalized.includes("infectious")) return "bird--clinical";
  if (normalized.includes("exposed")) return "bird--exposed";
  return "bird--baseline";
}

export function PenViewport({ snapshot, showTruth, showPredictions, penWidthM = 10, penHeightM = 7 }: PenViewportProps) {
  if (!snapshot) {
    return (
      <div className="viewport-empty" role="status">
        <span className="viewport-empty__mark" aria-hidden="true" />
        <strong>No simulation frame loaded</strong>
        <span>Run an experiment or select a completed run to inspect the pen.</span>
      </div>
    );
  }

  return (
    <svg
      className="pen-svg"
      viewBox="0 0 1000 700"
      role="img"
      aria-label={`Top-down pen view at ${snapshot.t_s} seconds with ${snapshot.birds.length} birds`}
    >
      <rect className="pen-floor" x="1" y="1" width="998" height="698" rx="4" />
      <g className="pen-grid" aria-hidden="true">
        {gridLines.slice(1, -1).map((coordinate) => (
          <line key={`v-${coordinate}`} x1={coordinate} y1="0" x2={coordinate} y2="700" />
        ))}
        {gridLines.slice(1, 7).map((coordinate) => (
          <line key={`h-${coordinate}`} x1="0" y1={coordinate} x2="1000" y2={coordinate} />
        ))}
      </g>
      <g className="pen-labels" aria-hidden="true">
        <text x="18" y="28">CAM 01 / OVERHEAD</text>
        <text x="982" y="28" textAnchor="end">{penWidthM.toFixed(1)} × {penHeightM.toFixed(1)} M</text>
      </g>
      <g>
        {snapshot.birds.map((bird) => {
          const x = (bird.x / penWidthM) * 1000;
          const y = (bird.y / penHeightM) * 700;
          const headingDegrees = Math.abs(bird.heading) <= Math.PI * 2
            ? (bird.heading * 180) / Math.PI
            : bird.heading;
          const truthClass = showTruth ? stateClass(bird.truth_state) : "bird--baseline";
          return (
            <g
              className={`bird ${truthClass}`}
              key={bird.id}
              transform={`translate(${x} ${y}) rotate(${headingDegrees})`}
            >
              {showPredictions && bird.predicted_abnormal ? (
                <circle className="bird__prediction" r="13" />
              ) : null}
              <ellipse className="bird__body" rx="7.2" ry="4.4" />
              <circle className="bird__head" cx="8.4" r="2.7" />
              <line className="bird__heading" x1="10" x2="15" />
            </g>
          );
        })}
      </g>
    </svg>
  );
}
