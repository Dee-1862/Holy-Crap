import { createHash } from "node:crypto";
import type { PhotonErrorShape, PhotonMessage, PhotonPage, PhotonSpace, PhotonUser, SendTextArgs } from "./types";

export interface PhotonClientDeps {
  baseUrl: string;
  apiKey: string;
  projectId: string;
  timeoutMs: number;
  fetch: typeof globalThis.fetch;
}

export class PhotonError extends Error implements PhotonErrorShape {
  readonly name = "PhotonError";
  readonly status: number | null;
  readonly requestId: string | null;

  constructor(status: number | null, requestId: string | null, message: string) {
    super(message);
    this.status = status;
    this.requestId = requestId;
  }
}

function spaceKey(participantIds: string[]): string {
  const sorted = [...participantIds].sort();
  return `space:${createHash("sha256").update(sorted.join(":"), "utf8").digest("hex")}`;
}

export class PhotonClient {
  private readonly baseUrl: string;
  private readonly apiKey: string;
  private readonly projectId: string;
  private readonly timeoutMs: number;
  private readonly fetchImpl: typeof globalThis.fetch;

  constructor(deps: PhotonClientDeps) {
    this.baseUrl = deps.baseUrl;
    this.apiKey = deps.apiKey;
    this.projectId = deps.projectId;
    this.timeoutMs = deps.timeoutMs;
    this.fetchImpl = deps.fetch;
  }

  private async request(
    method: string,
    path: string,
    body?: unknown,
    idempotencyKey?: string,
  ): Promise<{ status: number; requestId: string | null; body: unknown }> {
    const headers: Record<string, string> = {
      Authorization: `Bearer ${this.apiKey}`,
      Accept: "application/json",
    };
    if (body !== undefined) headers["Content-Type"] = "application/json";
    if (idempotencyKey) headers["Idempotency-Key"] = idempotencyKey;

    let response: Response;
    try {
      response = await this.fetchImpl(`${this.baseUrl}${path}`, {
        method,
        headers,
        body: body !== undefined ? JSON.stringify(body) : undefined,
        signal: AbortSignal.timeout(this.timeoutMs),
      });
    } catch (err) {
      if (err instanceof DOMException && err.name === "TimeoutError") {
        throw new PhotonError(null, null, "Photon request timed out");
      }
      if (err instanceof Error && err.name === "TimeoutError") {
        throw new PhotonError(null, null, "Photon request timed out");
      }
      throw new PhotonError(null, null, "Photon request could not be completed");
    }

    const requestId = response.headers.get("x-request-id") ?? response.headers.get("request-id");
    if (!response.ok) {
      throw new PhotonError(response.status, requestId, `Photon request failed (status ${response.status})`);
    }
    let parsed: unknown = null;
    try {
      parsed = await response.json();
    } catch {
      parsed = null;
    }
    return { status: response.status, requestId, body: parsed };
  }

  async createOrGetUser(handle: string): Promise<PhotonUser> {
    const { body } = await this.request(
      "POST",
      `/projects/${encodeURIComponent(this.projectId)}/users`,
      { platform: "sms", handle },
    );
    const user = body as PhotonUser | null;
    if (!user || typeof user.id !== "string") {
      throw new PhotonError(null, null, "Photon returned an unexpected create-user response");
    }
    return user;
  }

  async createOrGetSpace(participantIds: string[]): Promise<PhotonSpace> {
    const { body } = await this.request(
      "POST",
      `/projects/${encodeURIComponent(this.projectId)}/spaces`,
      { platform: "sms", participantIds },
      spaceKey(participantIds),
    );
    const space = body as PhotonSpace | null;
    if (!space || typeof space.id !== "string") {
      throw new PhotonError(null, null, "Photon returned an unexpected create-space response");
    }
    return space;
  }

  async sendTextMessage(args: SendTextArgs): Promise<{ id: string }> {
    const payload = {
      spaceId: args.spaceId,
      senderId: args.senderId,
      parentMessageId: args.parentMessageId ?? undefined,
      content: { type: "text", format: "plain", text: args.text },
    };
    const { body } = await this.request(
      "POST",
      `/projects/${encodeURIComponent(this.projectId)}/messages`,
      payload,
      args.idempotencyKey,
    );
    const message = body as { id?: string } | null;
    if (!message || typeof message.id !== "string") {
      throw new PhotonError(null, null, "Photon returned an unexpected send-message response");
    }
    return { id: message.id };
  }

  async listReceivedMessages(opts: { createdSince: string; pageToken?: string }): Promise<PhotonPage> {
    const params = new URLSearchParams({
      direction: "received",
      platform: "sms",
      order: "asc",
      pageSize: "100",
      createdSince: opts.createdSince,
    });
    if (opts.pageToken) params.set("pageToken", opts.pageToken);
    const { body } = await this.request(
      "GET",
      `/projects/${encodeURIComponent(this.projectId)}/messages?${params.toString()}`,
    );
    const page = body as { items?: PhotonMessage[]; nextPageToken?: string | null } | null;
    return {
      items: Array.isArray(page?.items) ? page.items : [],
      nextPageToken: page?.nextPageToken ?? null,
    };
  }
}
