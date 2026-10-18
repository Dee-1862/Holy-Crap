import fs from "node:fs";
import path from "node:path";
import type { MessagingState } from "./types";

const MAX_PROCESSED = 500;
const MAX_TURNS_PER_PHONE = 10;
const MAX_OUTBOX = 200;

function emptyState(): MessagingState {
  return {
    processedInbound: [],
    latestAlerts: {},
    turns: {},
    recentFarmerImages: {},
    vetHandoffs: {},
    pendingVetConsent: {},
    activeFarmerByVet: {},
    mockOutbox: [],
    agentUserId: null,
    lastPollAt: null,
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export class MessagingStore {
  private state: MessagingState;

  constructor(private readonly filePath: string) {
    this.state = this.load();
  }

  get snapshot(): MessagingState {
    return this.state;
  }

  update(fn: (s: MessagingState) => void): void {
    fn(this.state);
  }

  private trim(): void {
    this.state.processedInbound = this.state.processedInbound.slice(-MAX_PROCESSED);
    this.state.mockOutbox = this.state.mockOutbox.slice(-MAX_OUTBOX);
    for (const phone of Object.keys(this.state.turns)) {
      const turns = this.state.turns[phone];
      if (!turns || turns.length === 0) delete this.state.turns[phone];
      else this.state.turns[phone] = turns.slice(-MAX_TURNS_PER_PHONE);
    }
  }

  checkpoint(): void {
    this.trim();
    const dir = path.dirname(this.filePath);
    fs.mkdirSync(dir, { recursive: true });
    const tmp = `${this.filePath}.${process.pid}.tmp`;
    fs.writeFileSync(tmp, JSON.stringify(this.state, null, 2));
    fs.renameSync(tmp, this.filePath);
  }

  private load(): MessagingState {
    try {
      const raw = fs.readFileSync(this.filePath, "utf8");
      const parsed: unknown = JSON.parse(raw);
      if (!isRecord(parsed)) return emptyState();
      return {
        processedInbound: Array.isArray(parsed.processedInbound)
          ? parsed.processedInbound.filter((x): x is string => typeof x === "string")
          : [],
        latestAlerts: isRecord(parsed.latestAlerts) ? (parsed.latestAlerts as MessagingState["latestAlerts"]) : {},
        turns: isRecord(parsed.turns) ? (parsed.turns as MessagingState["turns"]) : {},
        recentFarmerImages: isRecord(parsed.recentFarmerImages)
          ? (parsed.recentFarmerImages as MessagingState["recentFarmerImages"])
          : {},
        vetHandoffs: isRecord(parsed.vetHandoffs)
          ? (parsed.vetHandoffs as MessagingState["vetHandoffs"])
          : {},
        pendingVetConsent: isRecord(parsed.pendingVetConsent)
          ? (parsed.pendingVetConsent as MessagingState["pendingVetConsent"])
          : {},
        activeFarmerByVet: isRecord(parsed.activeFarmerByVet)
          ? (parsed.activeFarmerByVet as MessagingState["activeFarmerByVet"])
          : {},
        mockOutbox: Array.isArray(parsed.mockOutbox)
          ? (parsed.mockOutbox as MessagingState["mockOutbox"]).filter((x) => isRecord(x) && typeof x.to === "string")
          : [],
        agentUserId: typeof parsed.agentUserId === "string" ? parsed.agentUserId : null,
        lastPollAt: typeof parsed.lastPollAt === "string" ? parsed.lastPollAt : null,
      };
    } catch {
      return emptyState();
    }
  }
}
