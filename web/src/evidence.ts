import type {
  ClipAssessment,
  ClipAssessmentModule,
  ClipModuleArtifact,
  FecesCandidate,
  VideoAnnotation,
} from "./types";

export function firstString(...values: unknown[]): string | null {
  for (const value of values) {
    if (typeof value === "string" && value.trim().length > 0) return value;
  }
  return null;
}

export function firstNumber(...values: unknown[]): number | null {
  for (const value of values) {
    if (typeof value === "number" && Number.isFinite(value)) return value;
  }
  return null;
}

export function firstBoolean(...values: unknown[]): boolean | null {
  for (const value of values) {
    if (typeof value === "boolean") return value;
  }
  return null;
}

export function firstRecord(...values: unknown[]): Record<string, unknown> | null {
  for (const value of values) {
    if (typeof value === "object" && value !== null && !Array.isArray(value)) {
      return value as Record<string, unknown>;
    }
  }
  return null;
}

export function moduleFor(stageId: string, modules: ClipAssessmentModule[]): ClipAssessmentModule | undefined {
  const aliases: Record<string, string[]> = {
    activity: ["activity", "motion", "energy"], appearance: ["appearance", "flock"],
    feces_candidates: ["feces_candidates", "feces-candidates", "candidate", "detector"],
    feces_classifier: ["feces_classifier", "feces-classifier", "classifier", "disease"],
  };
  return modules.find((module) => aliases[stageId]?.some((alias) => module.id.toLowerCase().includes(alias)));
}

function moduleArtifactRecord(module: ClipAssessmentModule | undefined): ClipModuleArtifact | null {
  if (!module || typeof module.artifact !== "object" || module.artifact === null) return null;
  return module.artifact;
}

function moduleDetails(module: ClipAssessmentModule | undefined): Record<string, unknown> | null {
  return module?.details && typeof module.details === "object" ? module.details : null;
}

export function moduleModelId(module: ClipAssessmentModule | undefined): string | null {
  if (!module) return null;
  const artifact = moduleArtifactRecord(module);
  const details = moduleDetails(module);
  return firstString(
    module.model_id,
    artifact?.model_id,
    artifact?.id,
    details?.model_id,
    details?.model,
  );
}

export function moduleArtifactId(module: ClipAssessmentModule | undefined): string | null {
  if (!module) return null;
  const artifact = moduleArtifactRecord(module);
  const details = moduleDetails(module);
  return firstString(module.artifact_id, artifact?.artifact_id, artifact?.id, details?.artifact_id);
}

export function moduleRuntime(module: ClipAssessmentModule | undefined): string | null {
  if (!module) return null;
  const artifact = moduleArtifactRecord(module);
  const details = moduleDetails(module);
  return firstString(module.runtime, artifact?.runtime, details?.runtime);
}

export function moduleFallbackReason(module: ClipAssessmentModule | undefined): string | null {
  if (!module) return null;
  const details = moduleDetails(module);
  return firstString(module.fallback_reason, module.reason, details?.fallback_reason, details?.reason);
}

export function moduleInferencePerformed(module: ClipAssessmentModule | undefined): boolean | null {
  if (!module) return null;
  const details = moduleDetails(module);
  return firstBoolean(module.inference_performed, details?.inference_performed);
}

export function moduleNotice(module: ClipAssessmentModule | undefined): string | null {
  return firstString(module?.notice, moduleDetails(module)?.notice);
}

export function stageRuntimeLine(module: ClipAssessmentModule | undefined): string {
  if (!module) return "deterministic placeholder · ready";
  const modelId = moduleModelId(module);
  const artifactId = moduleArtifactId(module);
  const runtime = moduleRuntime(module);
  const parts = [
    modelId,
    artifactId && artifactId !== modelId ? `artifact ${artifactId}` : null,
    `${module.version} · ${module.status}`,
    runtime ? `runtime ${runtime}` : null,
  ].filter((part): part is string => part !== null);
  return parts.join(" · ");
}

export interface ActivityEvidence {
  sampledFrames: number | null;
  behaviorObservations: number | null;
  detectedBirds: number | null;
  modelCoverage: number | null;
  behaviorDistribution: Record<string, number> | null;
}

export function activityEvidence(assessment: ClipAssessment | null): ActivityEvidence | null {
  const activity = assessment?.summary.activity;
  if (!activity) return null;
  const nested = firstRecord(activity.evidence);
  const sampledFrames = firstNumber(activity.sampled_frames, nested?.sampled_frames);
  const behaviorObservations = firstNumber(
    activity.bird_observations, activity.behavior_observations,
    nested?.bird_observations, nested?.behavior_observations,
  );
  const detectedBirds = firstNumber(activity.detected_birds, nested?.detected_birds);
  const modelCoverage = firstNumber(activity.model_coverage, activity.behavior_coverage, nested?.model_coverage, nested?.behavior_coverage);
  const rawDistribution = firstRecord(activity.behavior_distribution, nested?.behavior_distribution);
  const distribution = rawDistribution ? numericRecord(rawDistribution) : null;
  if (sampledFrames === null && behaviorObservations === null && detectedBirds === null && modelCoverage === null && !distribution) return null;
  return { sampledFrames, behaviorObservations, detectedBirds, modelCoverage, behaviorDistribution: distribution };
}

function numericRecord(record: Record<string, unknown>): Record<string, number> | null {
  const entries: Array<[string, number]> = [];
  for (const [key, value] of Object.entries(record)) {
    if (typeof value === "number" && Number.isFinite(value)) entries.push([key, value]);
  }
  return entries.length ? Object.fromEntries(entries) : null;
}

const BEHAVIOR_ORDER = ["drinking", "eating", "inactive", "moving", "other", "panting", "preening"];

export function orderedBehaviorDistribution(distribution: Record<string, number> | null): Array<[string, number]> {
  if (!distribution) return [];
  const entries = Object.entries(distribution);
  const ordered = BEHAVIOR_ORDER.filter((label) => distribution[label] !== undefined).map((label) => [label, distribution[label]] as [string, number]);
  const known = new Set(ordered.map(([label]) => label));
  return [...ordered, ...entries.filter(([label]) => !known.has(label))];
}

function detectorRecord(candidate: FecesCandidate): Record<string, unknown> | null {
  return firstRecord(candidate.detector);
}

export function detectorModelId(candidate: FecesCandidate): string | null {
  const detector = detectorRecord(candidate);
  return firstString(candidate.detector_model_id, detector?.model_id, detector?.id);
}

export function detectorArtifactId(candidate: FecesCandidate): string | null {
  const detector = detectorRecord(candidate);
  return firstString(candidate.detector_artifact_id, detector?.artifact_id, detector?.id);
}

export function detectorRuntime(candidate: FecesCandidate): string | null {
  return firstString(detectorRecord(candidate)?.runtime);
}

export function detectorSource(candidate: FecesCandidate): string | null {
  return firstString(candidate.detection_source, detectorRecord(candidate)?.source);
}

export function locationSource(candidate: FecesCandidate): string | null {
  return firstString(candidate.provenance?.location_source, candidate.detection_source, detectorRecord(candidate)?.source);
}

export function locationSourceLabel(candidate: FecesCandidate): string {
  const source = locationSource(candidate);
  if (source === "observed_video" || source === "observed" || source === "real_detection") return "Observed in the assessed whole-pen video.";
  if (source === "deterministic_overlay" || source === "overlay" || source === "simulated") return "Deterministic overlay position; not observed in footage.";
  return "Location source not reported by this assessment.";
}

export function locationSourceShortLabel(candidate: FecesCandidate): string {
  const source = locationSource(candidate);
  if (source === "observed_video" || source === "observed" || source === "real_detection") return "observed";
  if (source === "deterministic_overlay" || source === "overlay" || source === "simulated") return "overlay";
  return "not reported";
}

export function appearanceInput(candidate: FecesCandidate): string | null {
  return firstString(candidate.provenance?.appearance_input);
}

export function classificationSource(candidate: FecesCandidate): string | null {
  return firstString(candidate.provenance?.classification_source);
}

export function classifierModelId(candidate: FecesCandidate): string | null {
  const model = candidate.classification.model;
  return firstString(candidate.classification.model_id, model?.model_id, model?.id);
}

export function classifierArtifactId(candidate: FecesCandidate): string | null {
  const model = candidate.classification.model;
  return firstString(candidate.classification.artifact_id, model?.artifact_id);
}

export function classifierRuntime(candidate: FecesCandidate): string | null {
  const model = candidate.classification.model;
  return firstString(candidate.classification.runtime, model?.runtime);
}

export function classifierModelLabel(candidate: FecesCandidate): string | null {
  const modelId = classifierModelId(candidate);
  const artifactId = classifierArtifactId(candidate);
  const version = candidate.classification.model?.version ?? null;
  const runtime = classifierRuntime(candidate);
  const parts = [
    modelId,
    artifactId && artifactId !== modelId ? `artifact ${artifactId}` : null,
    version && !modelId ? `v${version}` : null,
    runtime ? `runtime ${runtime}` : null,
  ].filter((part): part is string => part !== null);
  return parts.length ? parts.join(" · ") : null;
}

export function cropContentUrl(candidate: FecesCandidate): string | null {
  return firstString(candidate.crop?.content_url);
}

export function cropSha256(candidate: FecesCandidate): string | null {
  return firstString(candidate.crop?.sha256);
}

export function cropDimensions(candidate: FecesCandidate): { width: number | null; height: number | null } {
  const width = firstNumber(candidate.crop?.width);
  const height = firstNumber(candidate.crop?.height);
  if (width === null && height === null && candidate.crop?.target_width !== undefined && candidate.crop?.target_height !== undefined) {
    return { width: firstNumber(candidate.crop.target_width), height: firstNumber(candidate.crop.target_height) };
  }
  return { width, height };
}

export function cropSource(candidate: FecesCandidate): string | null {
  return firstString(candidate.crop?.source);
}

export function cropMaterialized(candidate: FecesCandidate): boolean {
  return candidate.crop?.materialized === true;
}

export function cropIsPrimaryEvidence(candidate: FecesCandidate): boolean {
  return appearanceInput(candidate) === "observed_crop" || cropMaterialized(candidate);
}

export function inputHashLabel(candidate: FecesCandidate): string | null {
  return firstString(cropSha256(candidate), candidate.classification.input_sha256);
}

export function fallbackReasonLabel(reason: string | null | undefined): string | null {
  if (!reason) return null;
  return {
    no_observed_crop: "No observed crop available",
    specimen_unavailable: "Specimen bytes unavailable",
    runtime_unavailable: "Model runtime unavailable",
    image_decode_failed: "Image decode failed",
    model_inference_failed: "Model inference failed",
  }[reason] ?? reason.replaceAll("_", " ");
}

export function conciseModuleNotice(module: ClipAssessmentModule | undefined): string | null {
  const notice = moduleNotice(module);
  if (!notice) return null;
  const firstSentence = notice.match(/^.*?[.!?](?:\s|$)/)?.[0]?.trim() ?? notice;
  return firstSentence.length > 150 ? `${firstSentence.slice(0, 147).trimEnd()}…` : firstSentence;
}

export function stageModeWords(module: ClipAssessmentModule | undefined): string {
  if (!module) return "unreported";
  return module.mode === "real" ? "real" : module.mode === "partial" ? "partial" : "mock";
}

export function scorePercent(value: number): number {
  return value <= 1 ? value * 100 : value;
}

export function assessmentAnnotations(assessment: ClipAssessment | null): VideoAnnotation[] {
  return Array.isArray(assessment?.video_annotations) ? assessment.video_annotations : [];
}

export interface AnnotationGroup {
  timestamp_s: number;
  annotations: VideoAnnotation[];
}

export function annotationGroups(annotations: VideoAnnotation[]): AnnotationGroup[] {
  const groups = new Map<number, VideoAnnotation[]>();
  for (const annotation of annotations) {
    if (!annotation || !Number.isFinite(annotation.timestamp_s)) continue;
    const key = Math.round(annotation.timestamp_s * 1000) / 1000;
    const group = groups.get(key);
    if (group) group.push(annotation);
    else groups.set(key, [annotation]);
  }
  return [...groups.entries()]
    .map(([timestamp_s, items]) => ({ timestamp_s, annotations: items }))
    .sort((a, b) => a.timestamp_s - b.timestamp_s);
}

export function nearestAnnotationGroup(groups: AnnotationGroup[], time: number | null): AnnotationGroup | null {
  if (!groups.length) return null;
  if (time === null || !Number.isFinite(time)) return groups[0];
  let nearest = groups[0];
  let distance = Number.POSITIVE_INFINITY;
  for (const group of groups) {
    const candidate = Math.abs(group.timestamp_s - time);
    if (candidate < distance) {
      nearest = group;
      distance = candidate;
    }
  }
  return nearest;
}

export interface DroppingPersistence {
  observations: number;
  sampleFrames: number;
}

export function droppingPersistence(candidate: FecesCandidate, annotations: VideoAnnotation[]): DroppingPersistence | null {
  const related = annotations.filter((annotation) => annotation.kind === "dropping"
    && annotation.candidate_id === candidate.id
    && annotation.observation_state !== "carried_forward");
  if (!related.length) return null;
  const frames = new Set(related.map((annotation) => annotation.sample_index ?? Math.round(annotation.timestamp_s * 1000)));
  return { observations: related.length, sampleFrames: frames.size };
}

export function totalDroppingSampleFrames(annotations: VideoAnnotation[]): number {
  const frames = new Set(
    annotations
      .filter((annotation) => annotation.kind === "dropping")
      .filter((annotation) => annotation.observation_state !== "carried_forward")
      .map((annotation) => annotation.sample_index ?? Math.round(annotation.timestamp_s * 1000)),
  );
  return frames.size;
}

export interface ClassifierScoreReadout {
  entries: Array<[string, number]>;
  top: [string, number] | null;
  runnerUp: [string, number] | null;
  margin: number | null;
}

export function classifierScoreReadout(candidate: FecesCandidate): ClassifierScoreReadout {
  const scores = candidate.classification.scores;
  const entries = scores
    ? Object.entries(scores)
        .filter((entry): entry is [string, number] => typeof entry[1] === "number" && Number.isFinite(entry[1]))
        .sort((a, b) => b[1] - a[1])
    : [];
  const top = entries[0] ?? null;
  const runnerUp = entries[1] ?? null;
  const margin = top && runnerUp ? top[1] - runnerUp[1] : null;
  return { entries, top, runnerUp, margin };
}
