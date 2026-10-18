import { useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties } from "react";
import type { ClipAssessment, NormalizedBBox, VideoAnnotation } from "../types";
import { annotationGroups, assessmentAnnotations, nearestAnnotationGroup, scorePercent } from "../evidence";

interface AssessmentVideoViewportProps {
  assessment: ClipAssessment;
  selectedCandidateId: string | null;
  selectedBirdId?: string | null;
  onSelectCandidate?: (candidateId: string) => void;
  onSelectBird?: (annotation: VideoAnnotation) => void;
}

const SAMPLE_VISIBILITY_WINDOW_S = 0.45;

function formatTime(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  return `${minutes}:${Math.round(seconds % 60).toString().padStart(2, "0")}`;
}

function finite(value: number, fallback: number): number {
  return Number.isFinite(value) ? value : fallback;
}

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.min(Math.max(value, minimum), maximum);
}

function bboxStyle(bbox: NormalizedBBox): CSSProperties {
  const x = clamp(finite(bbox.x, 0), 0, 1);
  const y = clamp(finite(bbox.y, 0), 0, 1);
  const width = clamp(finite(bbox.width, 0), 0, 1 - x);
  const height = clamp(finite(bbox.height, 0), 0, 1 - y);
  return {
    left: `${x * 100}%`,
    top: `${y * 100}%`,
    width: `${width * 100}%`,
    height: `${height * 100}%`,
  };
}

function chickenLabel(annotation: VideoAnnotation): string {
  const parts = [
    `Chicken observation at ${formatTime(annotation.timestamp_s)}`,
    annotation.label ? `detected behavior ${annotation.label.replaceAll("_", " ")}` : null,
    `detector confidence ${Math.round(scorePercent(annotation.detection_confidence))}%`,
    typeof annotation.label_confidence === "number" ? `behavior confidence ${Math.round(scorePercent(annotation.label_confidence))}%` : null,
  ].filter((part): part is string => part !== null);
  return parts.join(", ");
}

function droppingLabel(annotation: VideoAnnotation): string {
  const isCarried = annotation.observation_state === "carried_forward";
  const parts = [
    isCarried
      ? `Persistent dropping location from ${formatTime(annotation.active_from_s ?? annotation.timestamp_s)}`
      : `Dropping observation at ${formatTime(annotation.timestamp_s)}`,
    annotation.candidate_id ? `candidate ${annotation.candidate_id}` : null,
    `detector confidence ${Math.round(scorePercent(annotation.detection_confidence))}%`,
  ].filter((part): part is string => part !== null);
  return parts.join(", ");
}

export function AssessmentVideoViewport({ assessment, selectedCandidateId, selectedBirdId, onSelectCandidate, onSelectBird }: AssessmentVideoViewportProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [metadataReady, setMetadataReady] = useState(false);
  const [currentTime, setCurrentTime] = useState<number | null>(null);
  const contentUrl = assessment.video.content_url ?? null;
  const annotations = useMemo(() => assessmentAnnotations(assessment), [assessment]);
  const observedAnnotations = useMemo(
    () => annotations.filter((annotation) => annotation.observation_state !== "carried_forward"),
    [annotations],
  );
  const carriedAnnotations = useMemo(
    () => annotations.filter((annotation) => annotation.kind === "dropping" && annotation.observation_state === "carried_forward"),
    [annotations],
  );
  const groups = useMemo(() => annotationGroups(observedAnnotations), [observedAnnotations]);
  const nearestGroup = nearestAnnotationGroup(groups, currentTime);
  const visibleGroup = nearestGroup && currentTime !== null && Math.abs(nearestGroup.timestamp_s - currentTime) <= SAMPLE_VISIBILITY_WINDOW_S
    ? nearestGroup
    : null;
  const selectedCandidate = assessment.summary.feces.candidates.find((candidate) => candidate.id === selectedCandidateId) ?? null;

  useEffect(() => {
    setMetadataReady(false);
    setCurrentTime(null);
  }, [assessment.id, contentUrl]);

  useEffect(() => {
    if (!selectedCandidate) return;
    const video = videoRef.current;
    if (!video || !metadataReady) return;
    const matchingObservation = observedAnnotations
      .filter((annotation) => annotation.kind === "dropping" && annotation.candidate_id === selectedCandidate.id)
      .sort((left, right) => Math.abs(left.timestamp_s - selectedCandidate.timestamp_s) - Math.abs(right.timestamp_s - selectedCandidate.timestamp_s))[0];
    const targetTime = matchingObservation?.timestamp_s ?? selectedCandidate.timestamp_s;
    const duration = Number.isFinite(video.duration) ? video.duration : targetTime;
    const boundedTime = Math.min(Math.max(targetTime, 0), Math.max(duration, 0));
    video.pause();
    video.currentTime = boundedTime;
    setCurrentTime(boundedTime);
  }, [observedAnnotations, selectedCandidate, metadataReady]);

  function syncTime() {
    const video = videoRef.current;
    if (!video) return;
    setCurrentTime(video.currentTime);
  }

  function selectDropping(annotation: VideoAnnotation) {
    const observedTarget = annotation.observation_state === "carried_forward"
      ? observedAnnotations
          .filter((item) => item.kind === "dropping" && item.candidate_id === annotation.candidate_id)
          .sort((left, right) => Math.abs(left.timestamp_s - annotation.timestamp_s) - Math.abs(right.timestamp_s - annotation.timestamp_s))[0]
      : annotation;
    const targetTime = observedTarget?.timestamp_s ?? annotation.timestamp_s;
    const video = videoRef.current;
    if (video && metadataReady) {
      const duration = Number.isFinite(video.duration) ? video.duration : targetTime;
      const boundedTime = Math.min(Math.max(targetTime, 0), Math.max(duration, 0));
      video.pause();
      video.currentTime = boundedTime;
      setCurrentTime(boundedTime);
    }
    if (annotation.candidate_id) onSelectCandidate?.(annotation.candidate_id);
  }

  function selectChicken(annotation: VideoAnnotation) {
    const video = videoRef.current;
    if (video && metadataReady) {
      const duration = Number.isFinite(video.duration) ? video.duration : annotation.timestamp_s;
      const boundedTime = Math.min(Math.max(annotation.timestamp_s, 0), Math.max(duration, 0));
      video.pause();
      video.currentTime = boundedTime;
      setCurrentTime(boundedTime);
    }
    onSelectBird?.(annotation);
  }

  if (!contentUrl) {
    return (
      <div className="avv-unavailable" role="status">
        <span aria-hidden="true">MOCK</span>
        <strong>No playable video bytes for this assessment</strong>
        <p>
          {assessment.video.source === "catalog_mock"
            ? "Generated without video bytes. Candidate locations are deterministic overlay data."
            : "This persisted assessment does not carry a playable video content URL."}
        </p>
      </div>
    );
  }

  const exactAnnotations = visibleGroup?.annotations ?? [];
  const exactCandidateIds = new Set(
    exactAnnotations
      .filter((annotation) => annotation.kind === "dropping")
      .map((annotation) => annotation.candidate_id)
      .filter((candidateId): candidateId is string => typeof candidateId === "string"),
  );
  const activeCarried = currentTime === null ? [] : carriedAnnotations.filter((annotation) => {
    const activeFrom = annotation.active_from_s ?? annotation.timestamp_s;
    const activeUntil = annotation.active_until_s ?? activeFrom;
    return currentTime >= activeFrom && currentTime <= activeUntil
      && (!annotation.candidate_id || !exactCandidateIds.has(annotation.candidate_id));
  });
  const visibleAnnotations = [...exactAnnotations, ...activeCarried];
  const observedChickens = exactAnnotations.filter((annotation) => annotation.kind === "chicken");
  const observedDroppings = exactAnnotations.filter((annotation) => annotation.kind === "dropping");
  return (
    <div className="avv">
      <div className="avv-frame">
        <video
          ref={videoRef}
          src={contentUrl}
          controls
          preload="metadata"
          playsInline
          onLoadedMetadata={() => {
            setMetadataReady(true);
            const video = videoRef.current;
            if (!video) return;
            const matchingObservation = selectedCandidate
              ? observedAnnotations
                  .filter((annotation) => annotation.kind === "dropping" && annotation.candidate_id === selectedCandidate.id)
                  .sort((left, right) => Math.abs(left.timestamp_s - selectedCandidate.timestamp_s) - Math.abs(right.timestamp_s - selectedCandidate.timestamp_s))[0]
              : null;
            const targetTime = matchingObservation?.timestamp_s ?? groups[0]?.timestamp_s;
            if (targetTime === undefined) {
              syncTime();
              return;
            }
            const duration = Number.isFinite(video.duration) ? video.duration : targetTime;
            const boundedTime = Math.min(Math.max(targetTime, 0), Math.max(duration, 0));
            video.pause();
            video.currentTime = boundedTime;
            setCurrentTime(boundedTime);
          }}
          onTimeUpdate={syncTime}
          onSeeked={syncTime}
          aria-label={`Assessed whole-pen video: ${assessment.video.name}`}
        >
          Your browser cannot play the assessed video.
        </video>
        {visibleAnnotations.length ? (
          <div className="avv-overlay">
            {visibleAnnotations.map((annotation) => {
              const isDropping = annotation.kind === "dropping";
              const isCarried = annotation.observation_state === "carried_forward";
              const isSelectedCandidate = isDropping && annotation.candidate_id != null && annotation.candidate_id === selectedCandidateId;
              const isSelectedBird = !isDropping && annotation.id === selectedBirdId;
              const tagLabel = isDropping
                ? `${isCarried ? "PERSISTENT" : "OBSERVED"} ${annotation.candidate_id ?? ""}`.trim()
                : `CHICKEN ${annotation.label ? annotation.label.replaceAll("_", " ").toUpperCase() : ""}`.trim();
              return (
                <button
                  key={annotation.id}
                  type="button"
                  className={[
                    "avv-annotation",
                    isDropping ? "avv-annotation--dropping" : "avv-annotation--chicken",
                    isCarried ? "avv-annotation--carried" : "",
                    isSelectedCandidate || isSelectedBird ? "avv-annotation--selected" : "",
                  ].filter(Boolean).join(" ")}
                  style={bboxStyle(annotation.bbox)}
                  aria-label={isDropping ? droppingLabel(annotation) : chickenLabel(annotation)}
                  aria-pressed={isSelectedCandidate || isSelectedBird}
                  onClick={() => (isDropping ? selectDropping(annotation) : selectChicken(annotation))}
                >
                  <span className="avv-annotation__tag">{tagLabel}</span>
                </button>
              );
            })}
          </div>
        ) : null}
      </div>
      <div className="avv-caption">
        {visibleGroup ? (
          <p className="avv-sample-status">
            <strong>Analyzed {formatTime(visibleGroup.timestamp_s)} ({visibleGroup.timestamp_s.toFixed(3)} s):</strong> {observedChickens.length} chicken{observedChickens.length === 1 ? "" : "s"}, {observedDroppings.length} dropping{observedDroppings.length === 1 ? "" : "s"}{activeCarried.length ? `, ${activeCarried.length} carried forward` : ""}.
          </p>
        ) : activeCarried.length ? (
          <p>{activeCarried.length} confirmed stationary dropping location{activeCarried.length === 1 ? "" : "s"} carried forward at this playback time.</p>
        ) : annotations.length ? (
          <p>No analyzed frame near this position. Seek to a sampled timestamp.</p>
        ) : (
          <p>No detection boxes were returned with this assessment.</p>
        )}
      </div>
    </div>
  );
}
