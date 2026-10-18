import type {
  AdapterCapability,
  ClipAssessment,
  DatasetClip,
  CreateRunRequest,
  MediaAssetInfo,
  ModelArtifact,
  QnxEvidencePayload,
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
  uploadClipAssessment: (file: File, profile?: string) => {
    const body = new FormData();
    body.append("file", file);
    if (profile) body.append("profile", profile);
    return request<ClipAssessment>("/clip-assessments/upload", { method: "POST", body });
  },
  assessDemoClip: (assetId: string, profile?: string) => {
    const query = profile ? `?profile=${encodeURIComponent(profile)}` : "";
    return request<ClipAssessment>(`/clip-assessments/demo/${encodeURIComponent(assetId)}${query}`, { method: "POST" });
  },
  datasetClips: () => request<DatasetClip[]>("/dataset-clips"),
  datasetClip: (id: string) => request<DatasetClip>(`/dataset-clips/${encodeURIComponent(id)}`),
  assessCatalogClip: (clipId: string, profile?: string) => {
    const query = profile ? `?profile=${encodeURIComponent(profile)}` : "";
    return request<ClipAssessment>(`/clip-assessments/catalog/${encodeURIComponent(clipId)}${query}`, { method: "POST" });
  },
  qnxEvidence: () => request<QnxEvidencePayload>("/system/qnx/evidence"),
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
