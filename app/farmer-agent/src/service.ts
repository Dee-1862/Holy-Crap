import { DeepSeekClient } from "./deepseek";
import { readEvidenceBytes } from "./media";
import { PhotonClient, PHOTON_PLATFORM, PhotonError } from "./photon";
import { createHash } from "node:crypto";
import {
  SYSTEM_RULES,
  VET_SYSTEM_RULES,
  alertText,
  contextBlock,
  factAnswer,
  factQuestionKind,
  fallbackReply,
  imageRequestReply,
  isImageRequest,
  isSafeWording,
  maskPhone,
  normalizeUsPhone,
  sanitizeReply,
  safetyBoundaryReply,
  vetApprovalPrompt,
  vetHandoffText,
  vetIntent,
} from "./rules";
import { MessagingStore } from "./state";
import type {
  AlertEvidence,
  AlertSnapshot,
  ChatMessage,
  DeliverySummary,
  MessagingConfig,
  PhotonMessage,
  PollResult,
  ProcessResult,
  Turn,
} from "./types";

export interface ServiceDeps {
  photon: PhotonClient;
  deepseek: DeepSeekClient;
  store: MessagingStore;
  clock: () => Date;
}

export interface RuntimeDeps {
  fetch?: typeof globalThis.fetch;
  deepseekFetch?: typeof globalThis.fetch;
  clock?: () => Date;
  store?: MessagingStore;
}

function sanitizedError(err: unknown): string {
  if (err instanceof PhotonError) {
    const id = err.requestId ? `, request ${err.requestId}` : "";
    return `${err.message}${id}`;
  }
  if (err instanceof Error) return err.message;
  return "unknown messaging error";
}

function stableKey(kind: string, ...parts: string[]): string {
  const digest = createHash("sha256").update(parts.join("\u0000"), "utf8").digest("hex");
  return `${kind}:${digest}`;
}

export class MessagingService {
  private readonly config: MessagingConfig;
  private readonly photon: PhotonClient;
  private readonly deepseek: DeepSeekClient;
  private readonly store: MessagingStore;
  private readonly clock: () => Date;

  constructor(config: MessagingConfig, deps: ServiceDeps) {
    this.config = config;
    this.photon = deps.photon;
    this.deepseek = deps.deepseek;
    this.store = deps.store;
    this.clock = deps.clock;
  }

  async sendAlert(snapshot: AlertSnapshot, recipients: string[]): Promise<DeliverySummary[]> {
    const canContactVet = Boolean(
      this.config.defaultVetNumber && this.config.vetNumbers.includes(this.config.defaultVetNumber),
    );
    const text = sanitizeReply(alertText(snapshot, canContactVet));
    const evidence = snapshot.evidence ?? null;
    const sourceLabel = evidence ? sanitizeReply(evidence.sourceLabel) : null;
    const results: DeliverySummary[] = [];

    for (const raw of recipients) {
      const phone = normalizeUsPhone(raw);
      if (!phone || !this.config.farmerNumbers.includes(phone)) {
        results.push({ recipient: maskPhone(phone ?? raw), status: "refused", alertId: snapshot.id });
        continue;
      }

      try {
        if (this.config.mode === "live") {
          await this.sendLive(snapshot, phone, text, sourceLabel);
          results.push({ recipient: maskPhone(phone), status: "accepted", alertId: snapshot.id });
        } else {
          const at = this.clock().toISOString();
          this.store.update((s) => {
            const alertEntry = {
              id: `alert:${snapshot.id}:${phone}`,
              kind: "alert" as const,
              to: phone,
              text,
              at,
              alertId: snapshot.id,
            };
            if (!s.mockOutbox.some((m) => m.id === alertEntry.id)) s.mockOutbox.push(alertEntry);
            if (evidence && sourceLabel) {
              const imageEntry = {
                id: `alert-img:${snapshot.id}:${phone}`,
                kind: "alert" as const,
                to: phone,
                text: sourceLabel,
                at,
                alertId: snapshot.id,
                evidence: {
                  contentType: evidence.contentType,
                  filename: evidence.filename,
                  sourceLabel: evidence.sourceLabel,
                },
              };
              if (!s.mockOutbox.some((m) => m.id === imageEntry.id)) s.mockOutbox.push(imageEntry);
            }
          });
          results.push({ recipient: maskPhone(phone), status: "queued", alertId: snapshot.id });
          console.log(`[messaging] mock alert queued for ${maskPhone(phone)}`);
        }

        this.store.update((s) => {
          s.latestAlerts[phone] = snapshot;
          if (canContactVet) {
            s.pendingVetConsent[phone] = {
              alertId: snapshot.id,
              askedAt: this.clock().toISOString(),
            };
          } else {
            delete s.pendingVetConsent[phone];
          }
        });
      } catch (err) {
        results.push({
          recipient: maskPhone(phone),
          status: "failed",
          alertId: snapshot.id,
          error: sanitizedError(err),
        });
      }
    }

    this.store.checkpoint();
    return results;
  }

  private async sendLive(
    snapshot: AlertSnapshot,
    phone: string,
    text: string,
    sourceLabel: string | null,
  ): Promise<void> {
    const agentId = this.config.photon.agentUserId;
    const human = await this.photon.createOrGetUser(phone);
    const space = await this.photon.createOrGetSpace([agentId, human.id]);
    this.store.update((s) => {
      s.agentUserId = agentId;
    });
    await this.photon.sendTextMessage({
      spaceId: space.id,
      senderId: agentId,
      text,
      idempotencyKey: stableKey("alert", snapshot.id, phone),
    });
    if (sourceLabel && snapshot.evidence) {
      await this.photon.sendTextMessage({
        spaceId: space.id,
        senderId: agentId,
        text: sourceLabel,
        idempotencyKey: stableKey("alert-label", snapshot.id, phone),
      });
      const bytes = await readEvidenceBytes(snapshot.evidence);
      const uploaded = await this.photon.uploadAttachment({
        contentType: snapshot.evidence.contentType,
        data: bytes,
        filename: snapshot.evidence.filename,
        idempotencyKey: stableKey("alert-attach-upload", snapshot.id, phone),
      });
      await this.photon.sendAttachmentMessage({
        spaceId: space.id,
        senderId: agentId,
        attachmentId: uploaded.id,
        idempotencyKey: stableKey("alert-attach", snapshot.id, phone),
      });
    }
    console.log(`[messaging] message accepted for ${maskPhone(phone)} (space ${space.id})`);
  }

  private async sendDirectText(phone: string, text: string, idempotencyKey: string): Promise<void> {
    const agentId = this.config.photon.agentUserId;
    const human = await this.photon.createOrGetUser(phone);
    const space = await this.photon.createOrGetSpace([agentId, human.id]);
    await this.photon.sendTextMessage({
      spaceId: space.id,
      senderId: agentId,
      text,
      idempotencyKey,
    });
    this.store.update((s) => {
      s.agentUserId = agentId;
    });
    console.log(`[messaging] message accepted for ${maskPhone(phone)} (space ${space.id})`);
  }

  async processInbound(message: PhotonMessage): Promise<ProcessResult> {
    if (message.platform !== PHOTON_PLATFORM || message.status !== "received") {
      return { handled: false, reason: "not-received-imessage" };
    }
    const content = message.content;
    if (content.type !== "text" || content.format !== "plain" || typeof content.text !== "string") {
      return { handled: false, reason: "not-plain-text" };
    }

    const sender = normalizeUsPhone(message.sentBy.handle);
    const isFarmer = sender ? this.config.farmerNumbers.includes(sender) : false;
    const isVet = sender ? this.config.vetNumbers.includes(sender) : false;
    if (message.sentBy.kind !== "human" || !sender || (!isFarmer && !isVet)) {
      return { handled: false, reason: "unauthorized" };
    }

    if (this.store.snapshot.processedInbound.includes(message.id)) {
      return { handled: false, reason: "duplicate" };
    }

    const recipient = message.receivedBy;
    if (!recipient || recipient.kind !== "agent" || recipient.platform !== PHOTON_PLATFORM) {
      return { handled: false, reason: "not-for-agent" };
    }
    const configuredAgentId = this.config.photon.agentUserId;
    if (!configuredAgentId || recipient.id !== configuredAgentId) {
      return { handled: false, reason: "not-for-agent" };
    }

    const incoming = content.text;
    if (isVet) return this.processVetInbound(message, sender, incoming, recipient);
    return this.processFarmerInbound(message, sender, incoming, recipient);
  }

  private async processFarmerInbound(
    message: PhotonMessage,
    sender: string,
    incoming: string,
    recipient: NonNullable<PhotonMessage["receivedBy"]>,
  ): Promise<ProcessResult> {
    const alert = this.store.snapshot.latestAlerts[sender] ?? null;
    const vet = this.config.defaultVetNumber;
    const hasVet = Boolean(vet && this.config.vetNumbers.includes(vet));
    const currentHandoff = this.store.snapshot.vetHandoffs[sender];
    const activeForAlert = Boolean(
      alert && currentHandoff?.status === "approved" && currentHandoff.alertId === alert.id,
    );
    const pendingQuestion = Boolean(
      alert && this.store.snapshot.pendingVetConsent[sender]?.alertId === alert.id,
    );
    const intent = vetIntent(incoming, pendingQuestion, activeForAlert);
    let reply: string;
    let pendingHandoff: { vet: string; alert: AlertSnapshot } | null = null;
    let closeVetChat = false;
    let askForVetConsent = false;
    let sendImage = false;

    if (intent === "approve") {
      if (!alert || !vet || !hasVet) {
        reply = vetApprovalPrompt(false);
      } else if (activeForAlert) {
        reply = "Your vet is already in this chat. I didn't send the same message again.";
      } else {
        pendingHandoff = { vet, alert };
        reply = "Okay. I told your vet what we saw. You can keep asking me questions here.";
      }
    } else if (intent === "decline") {
      closeVetChat = true;
      reply = activeForAlert
        ? "Okay. I stopped sending new messages to your vet."
        : "Okay. I won't contact your vet.";
    } else if (intent === "mention") {
      askForVetConsent = Boolean(alert && hasVet);
      reply = vetApprovalPrompt(hasVet);
    } else {
      const boundary = safetyBoundaryReply(incoming, hasVet);
      if (boundary) {
        askForVetConsent = Boolean(alert && hasVet);
        reply = boundary;
      } else if (isImageRequest(incoming)) {
        reply = sanitizeReply(imageRequestReply(alert));
        sendImage = Boolean(alert?.evidence);
      } else {
        const fact = factQuestionKind(incoming);
        reply = fact ? sanitizeReply(factAnswer(fact, alert)) : await this.buildReply(sender, incoming, false);
      }
    }

    try {
      if (pendingHandoff) {
        const handoffText = vetHandoffText(pendingHandoff.alert);
        if (this.config.mode === "live") {
          await this.sendDirectText(pendingHandoff.vet, handoffText, stableKey("vet-handoff", message.id));
        } else {
          this.store.update((s) =>
            s.mockOutbox.push({
              id: `vet-handoff:${message.id}`,
              kind: "vet-handoff",
              to: pendingHandoff!.vet,
              text: handoffText,
              at: this.clock().toISOString(),
              alertId: pendingHandoff!.alert.id,
            }),
          );
        }
      }
      await this.replyToInbound(message, sender, recipient.id, reply);
      if (sendImage && alert?.evidence) {
        await this.sendImageToInbound(message, sender, recipient.id, alert.evidence);
      }
    } catch {
      return { handled: false, reason: "send-failed" };
    }

    this.store.update((s) => {
      s.processedInbound.push(message.id);
      if (closeVetChat) {
        const current = s.vetHandoffs[sender];
        if (current) {
          current.status = "cancelled";
          delete s.activeFarmerByVet[current.vetPhone];
        }
        delete s.pendingVetConsent[sender];
      }
      if (pendingHandoff) {
        s.vetHandoffs[sender] = {
          farmerPhone: sender,
          vetPhone: pendingHandoff.vet,
          alertId: pendingHandoff.alert.id,
          approvedAt: this.clock().toISOString(),
          status: "approved",
        };
        s.activeFarmerByVet[pendingHandoff.vet] = sender;
        delete s.pendingVetConsent[sender];
      } else if (askForVetConsent && alert) {
        s.pendingVetConsent[sender] = {
          alertId: alert.id,
          askedAt: this.clock().toISOString(),
        };
      }
      this.appendTurns(s.turns, sender, incoming, reply, message.createdAt);
    });
    this.store.checkpoint();
    return { handled: true, reply };
  }

  private async processVetInbound(
    message: PhotonMessage,
    vet: string,
    incoming: string,
    recipient: NonNullable<PhotonMessage["receivedBy"]>,
  ): Promise<ProcessResult> {
    const farmer = this.store.snapshot.activeFarmerByVet[vet];
    const handoff = farmer ? this.store.snapshot.vetHandoffs[farmer] : null;
    if (!farmer || !handoff || handoff.status !== "approved") {
      return { handled: false, reason: "unauthorized" };
    }
    const reply = await this.buildReply(farmer, incoming, true, vet);
    try {
      await this.replyToInbound(message, vet, recipient.id, reply);
    } catch {
      return { handled: false, reason: "send-failed" };
    }
    this.store.update((s) => {
      s.processedInbound.push(message.id);
      this.appendTurns(s.turns, vet, incoming, reply, message.createdAt);
    });
    this.store.checkpoint();
    return { handled: true, reply };
  }

  private async replyToInbound(
    message: PhotonMessage,
    recipientPhone: string,
    agentUserId: string,
    reply: string,
  ): Promise<void> {
    if (this.config.mode === "live") {
      if (!message.space?.id) throw new Error("Inbound message has no space");
      await this.photon.sendTextMessage({
        spaceId: message.space.id,
        senderId: agentUserId,
        text: reply,
        idempotencyKey: stableKey("reply", message.id),
      });
    } else {
      this.store.update((s) =>
        s.mockOutbox.push({
          id: `reply:${message.id}`,
          kind: "reply",
          to: recipientPhone,
          text: reply,
          at: this.clock().toISOString(),
          inReplyTo: message.id,
        }),
      );
    }
  }

  // Resends the saved alert photo in the inbound message's existing space,
  // never creating a new user or space. Runs only after a deterministic
  // image-request reply; DeepSeek is not involved.
  private async sendImageToInbound(
    message: PhotonMessage,
    recipientPhone: string,
    agentUserId: string,
    evidence: AlertEvidence,
  ): Promise<void> {
    if (this.config.mode === "live") {
      if (!message.space?.id) throw new Error("Inbound message has no space");
      const bytes = await readEvidenceBytes(evidence);
      const uploaded = await this.photon.uploadAttachment({
        contentType: evidence.contentType,
        data: bytes,
        filename: evidence.filename,
        idempotencyKey: stableKey("reply-attach-upload", message.id),
      });
      await this.photon.sendAttachmentMessage({
        spaceId: message.space.id,
        senderId: agentUserId,
        attachmentId: uploaded.id,
        idempotencyKey: stableKey("reply-attach", message.id),
      });
    } else {
      this.store.update((s) =>
        s.mockOutbox.push({
          id: `reply-img:${message.id}`,
          kind: "reply",
          to: recipientPhone,
          text: evidence.sourceLabel,
          at: this.clock().toISOString(),
          inReplyTo: message.id,
          evidence: {
            contentType: evidence.contentType,
            filename: evidence.filename,
            sourceLabel: evidence.sourceLabel,
          },
        }),
      );
    }
  }

  private appendTurns(
    turnsByPhone: Record<string, Turn[]>,
    phone: string,
    incoming: string,
    reply: string,
    incomingAt: string,
  ): void {
    turnsByPhone[phone] = [
      ...(turnsByPhone[phone] ?? []),
      { role: "farmer", text: incoming, at: incomingAt },
      { role: "agent", text: reply, at: this.clock().toISOString() },
    ];
  }

  private async buildReply(
    farmerPhone: string,
    incoming: string,
    forVet: boolean,
    conversationPhone = farmerPhone,
  ): Promise<string> {
    const alert = this.store.snapshot.latestAlerts[farmerPhone] ?? null;
    const recent: Turn[] = (this.store.snapshot.turns[conversationPhone] ?? []).slice(-8);
    const messages: ChatMessage[] = [
      { role: "system", content: forVet ? VET_SYSTEM_RULES : SYSTEM_RULES },
      { role: "system", content: contextBlock(alert) },
      ...recent.map((t) => ({
        role: t.role === "farmer" ? ("user" as const) : ("assistant" as const),
        content: t.text,
      })),
      { role: "user", content: incoming },
    ];
    const raw = await this.deepseek.chat(messages);
    const text = raw ? sanitizeReply(raw) : fallbackReply(alert);
    return isSafeWording(text) ? text : sanitizeReply(fallbackReply(alert));
  }

  async pollOnce(): Promise<PollResult> {
    if (this.config.mode !== "live") return { pages: 0, processed: 0 };
    let pageToken: string | undefined;
    let pages = 0;
    let processed = 0;
    const previous = this.store.snapshot.lastPollAt;
    const createdSince = previous
      ? new Date(Math.max(0, Date.parse(previous) - 60_000)).toISOString()
      : new Date(this.clock().getTime() - 5_000).toISOString();
    do {
      const page = await this.photon.listReceivedMessages({ createdSince, pageToken });
      pages += 1;
      for (const message of page.items) {
        const result = await this.processInbound(message);
        if (result.handled) processed += 1;
      }
      pageToken = page.nextPageToken ?? undefined;
    } while (pageToken);
    this.store.update((s) => {
      s.lastPollAt = this.clock().toISOString();
    });
    this.store.checkpoint();
    return { pages, processed };
  }
}

export function createRuntime(config: MessagingConfig, deps: RuntimeDeps = {}) {
  const fetchImpl = deps.fetch ?? globalThis.fetch;
  const deepseekFetchImpl = deps.deepseekFetch ?? fetchImpl;
  const clock = deps.clock ?? (() => new Date());
  const store = deps.store ?? new MessagingStore(config.statePath);
  const photon = new PhotonClient({
    baseUrl: config.photon.baseUrl,
    apiKey: config.photon.apiKey,
    projectId: config.photon.projectId,
    timeoutMs: config.timeoutMs,
    fetch: fetchImpl,
  });
  const deepseek = new DeepSeekClient({
    config: config.deepseek,
    timeoutMs: config.timeoutMs,
    fetch: deepseekFetchImpl,
  });
  const service = new MessagingService(config, { photon, deepseek, store, clock });
  return { config, store, photon, deepseek, service };
}
