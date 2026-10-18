export type MessagingMode = "mock" | "live";

export interface PhotonConfig {
  baseUrl: string;
  apiKey: string;
  projectId: string;
  agentPhone: string;
}

export interface DeepSeekConfig {
  baseUrl: string;
  apiKey: string;
  model: string;
  maxTokens: number;
}

export interface MessagingConfig {
  mode: MessagingMode;
  statePath: string;
  pollMs: number;
  timeoutMs: number;
  farmerNumbers: string[];
  vetNumbers: string[];
  defaultVetNumber: string | null;
  photon: PhotonConfig;
  deepseek: DeepSeekConfig;
}

// A clean, safe snapshot of one camera anomaly, built from observations only.
// Synthetic disease labels from other modules are deliberately absent.
export interface AlertSnapshot {
  id: string;
  penId: string;
  penName: string;
  observationCount: number;
  windowMinutes: number;
  confidence: number;
  cameraSecondsAgo: number;
  sensorHealthy: boolean;
  createdAt: string;
}

export interface PhotonUser {
  id: string;
  handle: string;
  platform: string;
}

export interface PhotonSpace {
  id: string;
  platform: string;
  participantIds: string[];
}

export interface PhotonContent {
  type: string;
  format?: string;
  text?: string;
}

export interface PhotonUserSnapshot {
  id: string;
  platform: string;
  handle: string;
  kind: string;
}

export interface PhotonMessage {
  id: string;
  platform: string;
  status: string;
  space: { id: string; platform: string; kind: string };
  sentBy: PhotonUserSnapshot;
  receivedBy?: PhotonUserSnapshot;
  parentMessageId?: string | null;
  content: PhotonContent;
  createdAt: string;
}

export interface PhotonPage {
  items: PhotonMessage[];
  nextPageToken?: string | null;
}

export interface PhotonErrorShape {
  name: "PhotonError";
  status: number | null;
  requestId: string | null;
  message: string;
}

export interface SendTextArgs {
  spaceId: string;
  senderId: string;
  text: string;
  parentMessageId?: string | null;
  idempotencyKey: string;
}

export type DeliveryStatus = "queued" | "accepted" | "refused" | "failed";

export interface DeliverySummary {
  recipient: string;
  status: DeliveryStatus;
  alertId: string;
  error?: string;
}

export interface Turn {
  role: "farmer" | "agent";
  text: string;
  at: string;
}

export interface MockOutbound {
  id: string;
  kind: "alert" | "reply" | "vet-handoff";
  to: string;
  text: string;
  at: string;
  alertId?: string;
  inReplyTo?: string;
}

export interface MessagingState {
  processedInbound: string[];
  latestAlerts: Record<string, AlertSnapshot>;
  turns: Record<string, Turn[]>;
  vetHandoffs: Record<string, VetHandoff>;
  activeFarmerByVet: Record<string, string>;
  mockOutbox: MockOutbound[];
  agentUserId: string | null;
  lastPollAt: string | null;
}

export interface VetHandoff {
  farmerPhone: string;
  vetPhone: string;
  alertId: string;
  approvedAt: string;
  status: "approved" | "cancelled";
}

export type ProcessReason =
  | "not-plain-text"
  | "unauthorized"
  | "duplicate"
  | "not-for-agent"
  | "not-received-sms"
  | "no-space"
  | "vet-not-configured"
  | "send-failed";

export interface ProcessResult {
  handled: boolean;
  reason?: ProcessReason;
  reply?: string;
}

export interface PollResult {
  pages: number;
  processed: number;
}

export interface ChatMessage {
  role: "system" | "user" | "assistant";
  content: string;
}
