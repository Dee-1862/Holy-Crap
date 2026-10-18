import type {
  AdapterCapability,
  AssessmentExecutor,
  BenchmarkEvidenceResponse,
  ClipAssessment,
  ClipAssessmentJob,
  DatasetClip,
  CreateRunRequest,
  MediaAssetInfo,
  ModelArtifact,
  QnxEvidencePayload,
  QnxFaultTestResponse,
  QnxRuntimeResponse,
  ProxySpecimenPoolSummary,
  RunResult,
  RunSummary,
  Scenario,
  Snapshot,
  SystemCapabilities,
  TimelinePoint,
} from "./types";

const API_ROOT = "/api/v1";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

interface AssessmentSegment {
  start_s: number;
  end_s: number;
}

function assessmentQuery(profile?: string, segment?: AssessmentSegment, executor?: AssessmentExecutor): string {
  const query = new URLSearchParams();
  if (profile) query.set("profile", profile);
  if (segment) {
    query.set("segment_start_s", String(segment.start_s));
    query.set("segment_end_s", String(segment.end_s));
  }
  if (executor) query.set("executor", executor);
  const encoded = query.toString();
  return encoded ? `?${encoded}` : "";
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_ROOT}${path}`, init);
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = (await response.json()) as { detail?: string; error?: { message?: string } };
      detail = body.detail ?? body.error?.message ?? detail;
    } catch {
      // The status line is still useful when the body is not JSON.
    }
    throw new ApiError(detail || "Request failed", response.status);
  }
  return (await response.json()) as T;
}

export const api = {
  capabilities: () => request<SystemCapabilities>("/system/capabilities"),
  probeQnx: () => request<AdapterCapability>("/system/qnx/probe", { method: "POST" }),
  scenarios: () => request<Scenario[]>("/scenarios"),
  models: () => request<ModelArtifact[]>("/models"),
  runs: () => request<RunSummary[]>("/runs"),
  createRun: (payload: CreateRunRequest) =>
    request<RunSummary>("/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  result: (id: string) => request<RunResult>(`/runs/${encodeURIComponent(id)}/result`),
  timeline: (id: string) => request<TimelinePoint[]>(`/runs/${encodeURIComponent(id)}/timeline`),
  snapshots: (id: string) => request<Snapshot[]>(`/runs/${encodeURIComponent(id)}/snapshots`),
  media: () => request<MediaAssetInfo[]>("/media"),
  clipAssessments: () => request<ClipAssessment[]>("/clip-assessments"),
  clipAssessment: (id: string) => request<ClipAssessment>(`/clip-assessments/${encodeURIComponent(id)}`),
  uploadClipAssessment: (file: File, executor: AssessmentExecutor, profile?: string, segment?: AssessmentSegment) => {
    const body = new FormData();
    body.append("file", file);
    body.append("executor", executor);
    if (profile) body.append("profile", profile);
    if (segment) {
      body.append("segment_start_s", String(segment.start_s));
      body.append("segment_end_s", String(segment.end_s));
    }
    return request<ClipAssessmentJob>("/clip-assessment-jobs/upload", { method: "POST", body });
  },
  assessDemoClip: (assetId: string, executor: AssessmentExecutor, profile?: string, segment?: AssessmentSegment) => {
    const query = assessmentQuery(profile, segment, executor);
    return request<ClipAssessmentJob>(`/clip-assessment-jobs/demo/${encodeURIComponent(assetId)}${query}`, { method: "POST" });
  },
  datasetClips: () => request<DatasetClip[]>("/dataset-clips"),
  datasetClip: (id: string) => request<DatasetClip>(`/dataset-clips/${encodeURIComponent(id)}`),
  assessCatalogClip: (clipId: string, executor: AssessmentExecutor, profile?: string, segment?: AssessmentSegment) => {
    const query = assessmentQuery(profile, segment, executor);
    return request<ClipAssessmentJob>(`/clip-assessment-jobs/catalog/${encodeURIComponent(clipId)}${query}`, { method: "POST" });
  },
  clipAssessmentJob: (id: string) => request<ClipAssessmentJob>(`/clip-assessment-jobs/${encodeURIComponent(id)}`),
  qnxEvidence: () => request<QnxEvidencePayload>("/system/qnx/evidence"),
  benchmarkEvidence: () => request<BenchmarkEvidenceResponse>("/system/benchmark-evidence"),
  qnxRuntime: () => request<QnxRuntimeResponse>("/system/qnx/runtime"),
  runQnxFaultTest: (process: "infer" | "model" | "cloud" | "site") =>
    request<QnxFaultTestResponse>(`/system/qnx/fault-tests/${process}`, {
      method: "POST",
      headers: { "X-Holy-Crap-Fault-Test": "confirm" },
    }),
  proxySpecimens: () => request<ProxySpecimenPoolSummary>("/proxy-specimens"),
  uploadModel: (file: File, name: string, version: string, source?: string) => {
    const body = new FormData();
    body.append("file", file);
    body.append("name", name);
    body.append("version", version);
    if (source) body.append("source", source);
    return request<ModelArtifact>("/models/upload", { method: "POST", body });
  },
};
