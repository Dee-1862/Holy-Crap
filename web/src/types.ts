export type ScenarioMode = "healthy" | "outbreak" | string;
export type RunStatus = "queued" | "running" | "completed" | "failed" | string;

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

export interface AdapterCapability {
  id: string;
  kind: "executor" | "importer" | string;
  status: "ready" | "not_configured" | string;
  description: string;
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
