import { createHash, randomUUID } from "node:crypto";
import type {
  PhotonErrorShape,
  PhotonMessage,
  PhotonPage,
  PhotonSpace,
  PhotonUser,
  SendAttachmentArgs,
  SendTextArgs,
  UploadAttachmentArgs,
} from "./types";

export interface PhotonClientDeps {
  baseUrl: string;
  apiKey: string;
  projectId: string;
  timeoutMs: number;
  fetch: typeof globalThis.fetch;
}

export const PHOTON_PLATFORM = "imessage";

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

  private async perform(
    method: string,
    path: string,
    headers: Record<string, string>,
    body?: BodyInit,
  ): Promise<{ status: number; requestId: string | null; body: unknown }> {
    let response: Response;
    try {
      response = await this.fetchImpl(`${this.baseUrl}${path}`, {
        method,
        headers,
        body,
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
    return this.perform(method, path, headers, body !== undefined ? JSON.stringify(body) : undefined);
  }

  // Official Photon v1 attachment upload: multipart/related with exactly two
  // parts, JSON metadata followed by the raw file bytes. iMessage rejects
  // metadata captions, so no metadata is sent at all.
  async uploadAttachment(args: UploadAttachmentArgs): Promise<{ id: string }> {
    const boundary = `photon-${randomUUID().replace(/-/g, "")}`;
    const meta = {
      contentType: args.contentType,
      sizeBytes: args.data.length,
      ...(args.filename ? { filename: args.filename } : {}),
    };
    const head = Buffer.from(
      `--${boundary}\r\nContent-Type: application/json\r\n\r\n${JSON.stringify(meta)}\r\n` +
        `--${boundary}\r\nContent-Type: ${args.contentType}\r\n\r\n`,
      "utf8",
    );
    const tail = Buffer.from(`\r\n--${boundary}--\r\n`, "utf8");
    const body = Buffer.concat([head, Buffer.from(args.data), tail]);
    const headers: Record<string, string> = {
      Authorization: `Bearer ${this.apiKey}`,
      Accept: "application/json",
      "Content-Type": `multipart/related; boundary=${boundary}`,
      "Content-Length": String(body.length),
      "Idempotency-Key": args.idempotencyKey,
    };
    const res = await this.perform(
      "POST",
      `/projects/${encodeURIComponent(this.projectId)}/attachments`,
      headers,
      body,
    );
    const attachment = res.body as { id?: string } | null;
    if (!attachment || typeof attachment.id !== "string") {
      throw new PhotonError(null, null, "Photon returned an unexpected attachment response");
    }
    return { id: attachment.id };
  }

  async createOrGetUser(handle: string): Promise<PhotonUser> {
    const { body } = await this.request(
      "POST",
      `/projects/${encodeURIComponent(this.projectId)}/users`,
      { platform: PHOTON_PLATFORM, handle },
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
      { platform: PHOTON_PLATFORM, participantIds },
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

  // Sends an uploaded attachment by ID. iMessage rejects attachment caption
  // metadata, so the content carries no metadata beyond the attachment ID.
  async sendAttachmentMessage(args: SendAttachmentArgs): Promise<{ id: string }> {
    const payload = {
      spaceId: args.spaceId,
      senderId: args.senderId,
      parentMessageId: args.parentMessageId ?? undefined,
      content: { type: "attachment", attachmentId: args.attachmentId },
    };
    const { body } = await this.request(
      "POST",
      `/projects/${encodeURIComponent(this.projectId)}/messages`,
      payload,
      args.idempotencyKey,
    );
    const message = body as { id?: string } | null;
    if (!message || typeof message.id !== "string") {
      throw new PhotonError(null, null, "Photon returned an unexpected send-attachment response");
    }
    return { id: message.id };
  }

  async listReceivedMessages(opts: { createdSince: string; pageToken?: string }): Promise<PhotonPage> {
    const params = new URLSearchParams({
      direction: "received",
      platform: PHOTON_PLATFORM,
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
