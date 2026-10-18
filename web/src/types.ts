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
export type ClipAssessmentJobStatus = "queued" | "running" | "completed" | "failed";
export type ClipModuleMode = "mock" | "partial" | "real";
export type DemoProfile = "healthy" | "mixed" | "concerning";

export type AssessmentExecutor = "local" | "qnx";

export interface ClipAssessmentTarget {
  executor: AssessmentExecutor;
  hostname: string | null;
  system: string | null;
  release: string | null;
  machine: string | null;
  runtime: string | null;
  verified: boolean;
  detail: string | null;
}

export interface ClipTelemetrySample {
  captured_at: string;
  source: AssessmentExecutor;
  cpu_percent: number | null;
  ram_used_bytes: number | null;
  ram_total_bytes: number | null;
  process_cpu_percent: number | null;
  process_ram_bytes: number | null;
  detail: string | null;
}

export interface ClipAssessmentJob {
  schema_version: 1;
  id: string;
  status: ClipAssessmentJobStatus;
  progress_percent: number;
  stage: string;
  message: string;
  assessment_id: string | null;
  created_at: string;
  updated_at: string;
  executor: AssessmentExecutor;
  requested_executor: AssessmentExecutor;
  effective_executor: AssessmentExecutor | null;
  target?: ClipAssessmentTarget | null;
  telemetry?: ClipTelemetrySample | null;
  telemetry_history?: ClipTelemetrySample[];
}

export interface NormalizedBBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface ClipAssessmentVideo {
  name: string;
  sha256: string;
  size_bytes: number;
  duration_s: number | null;
  segment_start_s?: number;
  segment_end_s?: number | null;
  width: number | null;
  height: number | null;
  fps: number | null;
  source: string;
  media_type?: string;
  bytes_available?: boolean;
  content_url?: string | null;
  demo_asset_id?: string | null;
  catalog_clip_id?: string | null;
  metadata_source?: string;
  metadata_warnings?: string[];
}

export interface ClipModuleArtifact {
  id?: string;
  model_id?: string;
  artifact_id?: string;
  version?: string;
  sha256?: string | null;
  format?: string;
  runtime?: string;
  source?: string;
  status?: string;
  [key: string]: unknown;
}

export interface VideoAnnotation {
  id: string;
  kind: "chicken" | "dropping";
  timestamp_s: number;
  bbox: NormalizedBBox;
  detection_confidence: number;
  label?: string | null;
  label_confidence?: number | null;
  scores?: Record<string, number> | null;
  candidate_id?: string | null;
  sample_index?: number | null;
  observation_state?: "observed" | "carried_forward";
  active_from_s?: number | null;
  active_until_s?: number | null;
}

export interface ClipAssessmentModule {
  id: string;
  label: string;
  mode: ClipModuleMode;
  version: string;
  status: string;
  adapter?: string;
  model_id?: string | null;
  artifact_id?: string | null;
  artifact?: ClipModuleArtifact | string | null;
  runtime?: string | null;
  details?: Record<string, unknown> | null;
  notice?: string | null;
  reason?: string | null;
  fallback_reason?: string | null;
  inference_performed?: boolean;
}

export interface ClipActivityEvidence {
  sampled_frames?: number | null;
  bird_observations?: number | null;
  behavior_observations?: number | null;
  detected_birds?: number | null;
  model_coverage?: number | null;
  behavior_coverage?: number | null;
  behavior_distribution?: Record<string, number> | null;
  [key: string]: unknown;
}

export interface ClipActivitySummary {
  score: number;
  category: string;
  motion_coverage: number;
  zone_scores: Record<string, number>;
  sampled_frames?: number | null;
  bird_observations?: number | null;
  behavior_observations?: number | null;
  detected_birds?: number | null;
  model_coverage?: number | null;
  behavior_coverage?: number | null;
  behavior_distribution?: Record<string, number> | null;
  evidence?: ClipActivityEvidence | null;
}

export interface FecesClassifierModelReference {
  id?: string;
  model_id?: string;
  artifact_id?: string;
  version?: string;
  sha256?: string | null;
  format?: string;
  input_size?: number[];
  runtime?: string;
}

export interface FecesCandidateClassification {
  label: string | null;
  confidence: number;
  mode: ClipModuleMode | string;
  product_label?: string | null;
  scores?: Record<string, number>;
  input_sha256?: string | null;
  model?: FecesClassifierModelReference | null;
  model_id?: string | null;
  artifact_id?: string | null;
  runtime?: string | null;
  inference_performed?: boolean;
  model_detection_bbox?: NormalizedBBox | null;
  fallback_reason?: "no_observed_crop" | "specimen_unavailable" | "runtime_unavailable" | "image_decode_failed" | "model_inference_failed" | null;
}

export interface FecesDetectorReference {
  id?: string;
  model_id?: string;
  artifact_id?: string;
  version?: string;
  sha256?: string | null;
  runtime?: string;
  source?: string;
  [key: string]: unknown;
}

export interface FecesProvenance {
  location_source?: string;
  appearance_input?: string;
  classification_source?: string;
}

export interface FecesCropReference {
  source_video_sha256?: string;
  timestamp_s?: number;
  bbox?: NormalizedBBox;
  target_width?: number;
  target_height?: number;
  materialized?: boolean;
  content_url?: string | null;
  sha256?: string | null;
  width?: number | null;
  height?: number | null;
  source?: string;
}

export type DemoSpecimenClass = "cocci" | "healthy" | "ncd" | "salmo" | "unknown_abnormal";

export interface ProxySpecimenReference {
  id?: string;
  asset_id?: string;
  sample_id?: string;
  sha256?: string;
  content_url?: string | null;
  expected_label?: string;
  expected_demo_class?: DemoSpecimenClass;
  source?: string;
  source_dataset?: string;
  source_url?: string;
  license?: string;
  attribution?: string;
  mapping_method?: string;
  substitution_reason?: string;
  bytes_available?: boolean;
}

export interface FecesCandidate {
  id: string;
  timestamp_s: number;
  bbox: NormalizedBBox;
  classification: FecesCandidateClassification;
  detection_confidence?: number | null;
  crop?: FecesCropReference | null;
  provenance?: FecesProvenance | null;
  proxy_specimen?: ProxySpecimenReference | null;
  proxy?: ProxySpecimenReference | null;
  proxy_crop?: ProxySpecimenReference | null;
  detector?: FecesDetectorReference | null;
  detection_source?: string | null;
  detector_model_id?: string | null;
  detector_artifact_id?: string | null;
  lifecycle?: {
    first_observed_s: number;
    confirmed_s: number;
    last_observed_s: number;
    active_until_s: number;
    canonical_bbox: NormalizedBBox;
    observation_count: number;
    persistence_basis: "stationary_recurrence_across_sampled_frames";
  } | null;
}

export interface ProxySpecimenDatasetCount {
  dataset: string;
  count: number;
}

export interface ProxySpecimenPoolSummary {
  total: number;
  selectable_total?: number;
  bytes_present: number;
  verified_cached: number;
  by_expected_class: Partial<Record<DemoSpecimenClass, number>>;
  selectable_by_expected_class?: Partial<Record<DemoSpecimenClass, number>>;
  by_dataset: ProxySpecimenDatasetCount[];
  catalogs_supported: boolean;
}

export interface ClipPenAssessment {
  state?: string;
  score?: number | null;
  policy_id?: string;
  reasons?: string[];
  basis?: string[] | string;
  signals?: unknown;
  notes?: string[];
  activity_contribution?: number | null;
  feces_contribution?: number | null;
  evidence_mode?: string;
  non_diagnostic?: boolean;
}

export interface ClipOverallSummary {
  review_state: string;
  notes: string[];
  basis?: string[] | string;
  signals?: unknown;
}

export interface ClipAssessment {
  id: string;
  status: ClipAssessmentStatus;
  created_at: string;
  video: ClipAssessmentVideo;
  modules: ClipAssessmentModule[];
  summary: {
    activity: ClipActivitySummary;
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
    overall: ClipOverallSummary;
    pen_assessment?: ClipPenAssessment | null;
  };
  non_diagnostic_notice: string;
  profile?: string;
  video_annotations?: VideoAnnotation[] | null;
}

export type QnxEvidenceStatus =
  | "verified"
  | "os_supported"
  | "os_supported_only"
  | "planned"
  | "unsupported_guard"
  | string;

export interface QnxEvidenceEntry {
  id?: string;
  status?: QnxEvidenceStatus;
  summary?: string;
  title?: string;
  label?: string;
  category?: string;
  measured?: boolean;
  metrics?: Record<string, unknown> | unknown[];
  values?: Record<string, unknown> | unknown[];
  detail?: Record<string, unknown> | unknown[] | null;
  details?: Record<string, unknown> | unknown[] | null;
  [key: string]: unknown;
}

export interface QnxEvidenceTarget {
  id?: string;
  system?: string;
  release?: string;
  machine?: string;
  hardware?: string;
  python_version?: string;
  [key: string]: unknown;
}

export interface QnxEvidenceDocument {
  schema_version?: number;
  evidence_id?: string;
  verified_at?: string;
  thesis?: string;
  platform?: Record<string, unknown> | null;
  claims?: QnxEvidenceEntry[];
}

export interface QnxEvidencePayload {
  schema_version?: number;
  evidence_id?: string;
  verified_at?: string;
  thesis?: string;
  target?: QnxEvidenceTarget | Record<string, unknown> | string | null;
  platform?: Record<string, unknown> | null;
  claims?: QnxEvidenceEntry[];
  cards?: QnxEvidenceEntry[];
  entries?: QnxEvidenceEntry[];
  evidence?: QnxEvidenceDocument | null;
  [key: string]: unknown;
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
  installed_size_bytes?: number | null;
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
