import { createServer, type IncomingMessage, type Server, type ServerResponse } from "node:http";
import type { MessagingService } from "./service";
import type { AlertSnapshot } from "./types";
import { loadEvidenceImage } from "./media";

const MAX_BODY_BYTES = 64 * 1024;

export interface DashboardAlertPayload {
  eventId: string;
  penName: string;
  observationCount: number;
  windowMinutes: number;
  windowSeconds?: number;
  confidence: number;
  suspectedIllness: string;
  createdAt: string;
  evidence?: {
    localPath: string;
    sourceLabel: string;
  };
}

function json(response: ServerResponse, status: number, body: unknown): void {
  response.writeHead(status, { "content-type": "application/json" });
  response.end(JSON.stringify(body));
}

function asPayload(value: unknown): DashboardAlertPayload | null {
  if (!value || typeof value !== "object") return null;
  const item = value as Record<string, unknown>;
  if (
    typeof item.eventId !== "string" || !item.eventId.trim() ||
    typeof item.penName !== "string" || !item.penName.trim() ||
    typeof item.observationCount !== "number" || !Number.isInteger(item.observationCount) || item.observationCount < 1 ||
    typeof item.windowMinutes !== "number" || !Number.isFinite(item.windowMinutes) || item.windowMinutes <= 0 ||
    (item.windowSeconds !== undefined &&
      (typeof item.windowSeconds !== "number" || !Number.isFinite(item.windowSeconds) || item.windowSeconds <= 0)) ||
    typeof item.confidence !== "number" || item.confidence < 0 || item.confidence > 1 ||
    typeof item.suspectedIllness !== "string" || !item.suspectedIllness.trim() ||
    typeof item.createdAt !== "string" || !item.createdAt.trim() ||
    (item.evidence !== undefined && (
      !item.evidence || typeof item.evidence !== "object" ||
      typeof (item.evidence as Record<string, unknown>).localPath !== "string" ||
      typeof (item.evidence as Record<string, unknown>).sourceLabel !== "string"
    ))
  ) return null;
  return item as unknown as DashboardAlertPayload;
}

async function readBody(request: IncomingMessage): Promise<unknown> {
  const chunks: Buffer[] = [];
  let size = 0;
  for await (const chunk of request) {
    const buffer = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk);
    size += buffer.length;
    if (size > MAX_BODY_BYTES) throw new Error("request too large");
    chunks.push(buffer);
  }
  return JSON.parse(Buffer.concat(chunks).toString("utf8"));
}

export function toAlertSnapshot(payload: DashboardAlertPayload): AlertSnapshot {
  let evidence: AlertSnapshot["evidence"];
  if (payload.evidence) {
    try {
      evidence = loadEvidenceImage(payload.evidence.localPath, payload.evidence.sourceLabel);
    } catch {
      evidence = undefined;
    }
  }
  return {
    id: payload.eventId,
    penId: payload.penName.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, ""),
    penName: payload.penName,
    observationCount: payload.observationCount,
    windowMinutes: payload.windowMinutes,
    windowSeconds: payload.windowSeconds,
    confidence: payload.confidence,
    cameraSecondsAgo: 0,
    sensorHealthy: true,
    suspectedIllness: payload.suspectedIllness,
    source: "simulation-dashboard",
    evidence,
    createdAt: payload.createdAt,
  };
}

export function createDashboardAlertServer(
  service: MessagingService,
  farmerNumbers: string[],
): Server {
  return createServer(async (request, response) => {
    if (request.method === "GET" && request.url === "/health") {
      json(response, 200, { status: "ok" });
      return;
    }
    if (request.method !== "POST" || request.url !== "/simulation-alerts") {
      json(response, 404, { error: "not found" });
      return;
    }
    try {
      const payload = asPayload(await readBody(request));
      if (!payload) {
        json(response, 400, { error: "invalid simulation alert" });
        return;
      }
      const deliveries = await service.sendAlert(toAlertSnapshot(payload), farmerNumbers);
      const delivered = deliveries.some((item) => item.status === "accepted" || item.status === "queued");
      json(response, delivered ? 202 : 502, {
        status: delivered ? "sent" : "failed",
        deliveries: deliveries.map(({ status, alertId }) => ({ status, alertId })),
      });
    } catch {
      json(response, 500, { error: "could not send farmer alert" });
    }
  });
}

export async function listenForDashboardAlerts(
  service: MessagingService,
  farmerNumbers: string[],
  port: number,
): Promise<Server> {
  const server = createDashboardAlertServer(service, farmerNumbers);
  await new Promise<void>((resolve, reject) => {
    server.once("error", reject);
    server.listen(port, "127.0.0.1", () => {
      server.off("error", reject);
      resolve();
    });
  });
  return server;
}
