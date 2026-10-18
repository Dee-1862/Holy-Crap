import type {
  CreateRunRequest,
  ModelArtifact,
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
  scenarios: () => request<Scenario[]>("/scenarios"),
  models: () => request<ModelArtifact[]>("/models"),
  runs: () => request<RunSummary[]>("/runs"),
  createRun: (payload: CreateRunRequest) =>
    request<RunSummary>("/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  timeline: (id: string) => request<TimelinePoint[]>(`/runs/${encodeURIComponent(id)}/timeline`),
  snapshots: (id: string) => request<Snapshot[]>(`/runs/${encodeURIComponent(id)}/snapshots`),
  uploadModel: (file: File, name: string, version: string, source?: string) => {
    const body = new FormData();
    body.append("file", file);
    body.append("name", name);
    body.append("version", version);
    if (source) body.append("source", source);
    return request<ModelArtifact>("/models/upload", { method: "POST", body });
  },
};
