import type { VideoAnnotation } from "../types";
import { scorePercent } from "../evidence";

interface BirdObservationCardProps {
  annotation: VideoAnnotation;
  onDismiss: () => void;
}

function formatTime(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  return `${minutes}:${Math.round(seconds % 60).toString().padStart(2, "0")}`;
}

function orderedScores(annotation: VideoAnnotation): Array<[string, number]> {
  const scores = annotation.scores;
  if (!scores) return [];
  return Object.entries(scores)
    .filter((entry): entry is [string, number] => typeof entry[1] === "number" && Number.isFinite(entry[1]))
    .sort((a, b) => b[1] - a[1]);
}

export function BirdObservationCard({ annotation, onDismiss }: BirdObservationCardProps) {
  const scores = orderedScores(annotation);
  const detectionPercent = Math.round(scorePercent(annotation.detection_confidence));
  const labelConfidencePercent = typeof annotation.label_confidence === "number" ? Math.round(scorePercent(annotation.label_confidence)) : null;
  return (
    <article className="bird-observation" aria-labelledby="bird-observation-title">
      <div className="subheading">
        <div>
          <span className="eyebrow">Selected bird observation</span>
          <h3 id="bird-observation-title">One sampled chicken frame</h3>
        </div>
        <button type="button" className="bird-observation__close" onClick={onDismiss} aria-label="Close the selected bird observation card">Clear</button>
      </div>
      <dl className="bird-observation__facts">
        <div><dt>Behavior label</dt><dd>{annotation.label ? annotation.label.replaceAll("_", " ") : "Not reported"}</dd></div>
        <div><dt>Detector confidence</dt><dd>{detectionPercent}%</dd></div>
        <div><dt>Behavior confidence</dt><dd>{labelConfidencePercent === null ? "Not reported" : `${labelConfidencePercent}%`}</dd></div>
        <div><dt>Sampled timestamp</dt><dd>{formatTime(annotation.timestamp_s)} ({annotation.timestamp_s.toFixed(3)} s)</dd></div>
        {annotation.sample_index !== null && annotation.sample_index !== undefined ? <div><dt>Sample index</dt><dd>{annotation.sample_index}</dd></div> : null}
      </dl>
      {scores.length ? (
        <div className="bird-observation__scores" aria-label="Behavior score distribution for this sampled frame">
          {scores.map(([label, value]) => (
            <div className="distribution-row" key={label}>
              <span>{label.replaceAll("_", " ")}</span>
              <div><i style={{ width: `${Math.max(0, Math.min(100, scorePercent(value)))}%` }} /></div>
              <strong>{Math.round(scorePercent(value))}%</strong>
            </div>
          ))}
        </div>
      ) : null}
    </article>
  );
}
