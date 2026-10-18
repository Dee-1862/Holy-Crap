export type ScenarioMode = "healthy" | "outbreak" | string;
export type RunStatus = "queued" | "running" | "completed" | "failed" | string;

export interface ScenarioRenderer {
  kind: string;
  version: string;
  observation_artifact?: string | null;
  observation_sha256?: string | null;
  metadata?: Record<string, unknown>;
}

export interface Scenario {
  id: string;
  name: string;
  description: string;
  bird_count: number;
  fps: number;
  duration_s: number;
  seed: number;
  mode: ScenarioMode;
  pen_width_m?: number;
  pen_height_m?: number;
  observation?: { alert_threshold?: number; [key: string]: unknown };
  renderer?: ScenarioRenderer;
}

export interface ModelArtifact {
  id: string;
  name: string;
  version: string;
  format: string;
  source: string;
  sha256: string | null;
  size_bytes: number;
  created_at: string;
}

export interface RunMetrics {
  detection_delay_s?: number | null;
  false_alerts?: number;
  mean_fps?: number;
  p95_latency_ms?: number;
  dropped_frames?: number;
  alert_triggered?: boolean;
}

export interface RunSummary {
  id: string;
  status: RunStatus;
  scenario_id: string;
  model_id: string;
  executor: string;
  created_at: string;
  metrics?: RunMetrics | null;
}

export interface TimelinePoint {
  t_s: number;
  susceptible: number;
  exposed: number;
  infectious: number;
  clinical: number;
  abnormal_droppings: number;
  truth_score: number;
  predicted_score: number;
  alert: boolean;
}

export interface BirdSnapshot {
  id: string;
  x: number;
  y: number;
  heading: number;
  truth_state: string;
  predicted_abnormal: boolean;
}

export interface Snapshot {
  t_s: number;
  birds: BirdSnapshot[];
}

export type CapabilityStatus =
  | "ready"
  | "probe_only"
  | "unreachable"
  | "runtime_missing"
  | "not_configured"
  | string;

export interface AdapterCapability {
  id: string;
  kind: "executor" | "importer" | string;
  status: CapabilityStatus;
  description: string;
  details?: Record<string, unknown>;
}

export type CapabilityValue = boolean | string | number | null | Record<string, unknown> | unknown[];

export interface SystemCapabilities {
  schema_version?: number;
  executors?: AdapterCapability[];
  importers?: AdapterCapability[];
  [key: string]: CapabilityValue | undefined;
}

export interface CreateRunRequest {
  scenario_id: string;
  model_id: string;
  executor: string;
}

export interface MediaAssetInfo {
  id: string;
  title: string;
  description: string;
  media_type: string;
  width: number;
  height: number;
  filename: string;
  sha256: string;
  expected_size_bytes: number;
  installed: boolean;
  verified: boolean;
  size_bytes: number;
  duration_s: number | null;
  frame_rate_fps: number | null;
  frame_count: number | null;
  codec: string | null;
  content_url: string;
  source_url: string;
  dataset_url: string;
  doi: string;
  license: string;
  license_url: string;
  attribution: string;
  creators: string[];
  limitations: string[];
}

export type ClipAssessmentStatus = "queued" | "running" | "completed" | "failed" | string;
export type ClipModuleMode = "mock" | "real";

export interface ClipAssessmentVideo {
  name: string;
  sha256: string;
  size_bytes: number;
  duration_s: number | null;
  width: number | null;
  height: number | null;
  fps: number | null;
  source: string;
}

export interface ClipAssessmentModule {
  id: string;
  label: string;
  mode: ClipModuleMode;
  version: string;
  status: string;
}

export interface FecesCandidateClassification {
  label: string;
  confidence: number;
  mode: ClipModuleMode;
}

export interface FecesCandidate {
  id: string;
  timestamp_s: number;
  bbox: { x: number; y: number; width: number; height: number };
  classification: FecesCandidateClassification;
}

export interface ClipAssessment {
  id: string;
  status: ClipAssessmentStatus;
  created_at: string;
  video: ClipAssessmentVideo;
  modules: ClipAssessmentModule[];
  summary: {
    activity: {
      score: number;
      category: string;
      motion_coverage: number;
      zone_scores: Record<string, number>;
    };
    appearance: {
      score: number;
      category: string;
      notes: string[];
    };
    feces: {
      candidate_count: number;
      class_distribution: Record<string, number>;
      candidates: FecesCandidate[];
    };
    overall: {
      review_state: string;
      notes: string[];
    };
  };
  non_diagnostic_notice: string;
}

export type DatasetClipStatus = "ready" | "cataloged" | "reference_only" | "rejected";

export interface DatasetClip {
  schema_version: number;
  id: string;
  title: string;
  dataset_name: string;
  status: DatasetClipStatus;
  review_verdict: string;
  camera_fit: string;
  best_use: string[];
  limitations: string[];
  source_url: string;
  dataset_url: string;
  license: string;
  doi: string | null;
  media_kind: "video" | "images";
  media_type: string | null;
  filename: string | null;
  duration_s: number | null;
  width: number | null;
  height: number | null;
  fps: number | null;
  expected_size_bytes: number | null;
  byte_range_start: number | null;
  byte_range_end: number | null;
  demo_asset_id: string | null;
  assessable: boolean;
  bytes_available: boolean;
  content_url: string | null;
}

export type EvaluationKind = "prediction" | "target_probe" | string;

export interface ResultModelReference {
  name: string;
  version: string;
  sha256: string;
}

export interface ResultScenarioReference {
  id: string;
  sha256: string;
  seed: number;
}

export interface ResultExecutorReference {
  name: string;
  version: string;
  target?: string | null;
  runtime?: string | null;
}

export interface RunArtifact {
  kind: string;
  path: string;
  sha256: string;
  media_type: string;
  size_bytes?: number;
}

export interface RunResult {
  schema_version?: number;
  run_id: string;
  evaluation_kind: EvaluationKind;
  model: ResultModelReference;
  scenario: ResultScenarioReference;
  executor: ResultExecutorReference;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  status: string;
  metrics: RunMetrics | null;
  artifacts: RunArtifact[];
  error?: { code?: string; message?: string } | null;
}
