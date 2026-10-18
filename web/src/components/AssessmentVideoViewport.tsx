import { useEffect, useRef, useState } from "react";
import type { ClipAssessment, FecesCandidate } from "../types";

interface AssessmentVideoViewportProps {
  assessment: ClipAssessment;
  selectedCandidateId: string | null;
}

function formatTime(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  return `${minutes}:${Math.round(seconds % 60).toString().padStart(2, "0")}`;
}

function candidateLabel(candidate: FecesCandidate): string {
  const bbox = candidate.bbox;
  const left = Math.round(bbox.x * 1000) / 10;
  const top = Math.round(bbox.y * 1000) / 10;
  const width = Math.round(bbox.width * 1000) / 10;
  const height = Math.round(bbox.height * 1000) / 10;
  return (
    `Candidate ${candidate.id} observed location: ${formatTime(candidate.timestamp_s)} into the video, ` +
    `bounding box ${left}% from the left edge, ${top}% from the top edge, ${width}% of the frame wide and ` +
    `${height}% of the frame tall.`
  );
}

export function AssessmentVideoViewport({ assessment, selectedCandidateId }: AssessmentVideoViewportProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [metadataReady, setMetadataReady] = useState(false);
  const contentUrl = assessment.video.content_url ?? null;
  const candidates = assessment.summary.feces.candidates;
  const selectedCandidate = candidates.find((candidate) => candidate.id === selectedCandidateId) ?? null;

  useEffect(() => {
    setMetadataReady(false);
  }, [contentUrl]);

  useEffect(() => {
    if (!selectedCandidate) return;
    const video = videoRef.current;
    if (!video || !metadataReady) return;
    const duration = Number.isFinite(video.duration) ? video.duration : 0;
    video.currentTime = Math.min(Math.max(selectedCandidate.timestamp_s, 0), Math.max(duration, 0));
  }, [selectedCandidate, metadataReady]);

  if (!contentUrl) {
    return (
      <div className="avv-unavailable" role="status">
        <span aria-hidden="true">MOCK</span>
        <strong>No playable video bytes for this assessment</strong>
        <p>
          {assessment.video.source === "catalog_mock"
            ? "This catalog mock was generated without video bytes, so no video was decoded or analyzed. Candidate locations are deterministic overlay data, not observed footage."
            : "This persisted assessment does not carry a playable video content URL. The clip library preview remains available before an assessment is selected."}
        </p>
      </div>
    );
  }

  const candidateExists = selectedCandidate != null;
  return (
    <div className="avv">
      <div className="avv-frame">
        <video
          ref={videoRef}
          src={contentUrl}
          controls
          preload="metadata"
          playsInline
          onLoadedMetadata={() => setMetadataReady(true)}
          aria-label={`Assessed whole-pen video: ${assessment.video.name}`}
        >
          Your browser cannot play the assessed video.
        </video>
        {candidateExists ? (
          <div
            className="avv-overlay"
            role="img"
            aria-label={candidateLabel(selectedCandidate)}
          >
            <div
              className="avv-bbox"
              style={{
                left: `${selectedCandidate.bbox.x * 100}%`,
                top: `${selectedCandidate.bbox.y * 100}%`,
                width: `${selectedCandidate.bbox.width * 100}%`,
                height: `${selectedCandidate.bbox.height * 100}%`,
              }}
            />
          </div>
        ) : null}
      </div>
      <div className="avv-caption">
        {candidateExists ? (
          <p>
            <strong>Observed location overlay:</strong> {selectedCandidate.id} at{" "}
            {formatTime(selectedCandidate.timestamp_s)} — normalized bbox{" "}
            <code>
              x {selectedCandidate.bbox.x.toFixed(3)} · y {selectedCandidate.bbox.y.toFixed(3)} ·{" "}
              {selectedCandidate.bbox.width.toFixed(3)}×{selectedCandidate.bbox.height.toFixed(3)}
            </code>
            . The box marks where the candidate was located in this whole-pen video; it is not a crop.
          </p>
        ) : (
          <p>Select a candidate below to seek the video to its timestamp and overlay its observed location.</p>
        )}
      </div>
      <p className="avv-boundary">The assessed video is the authoritative viewer source for this assessment. Any earlier dataset or upload preview is not shown instead of it.</p>
    </div>
  );
}
