export type MessagingMode = "mock" | "live";

export interface PhotonConfig {
  baseUrl: string;
  apiKey: string;
  projectId: string;
  agentUserId: string;
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

// A local photo that can be sent with an alert or on request.
// Only JPEG and PNG are supported. localPath never reaches a farmer message.
export interface AlertEvidence {
  localPath: string;
  contentType: "image/jpeg" | "image/png";
  filename: string;
  sizeBytes: number;
  sourceLabel: string;
}

// A clean snapshot of what the camera system saw for one pen.
export interface AlertSnapshot {
  id: string;
  penId: string;
  penName: string;
  observationCount: number;
  windowMinutes: number;
  confidence: number;
  cameraSecondsAgo: number;
  sensorHealthy: boolean;
  suspectedIllness?: string;
  evidence?: AlertEvidence;
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

export interface UploadAttachmentArgs {
  contentType: "image/jpeg" | "image/png";
  data: Uint8Array;
  filename: string;
  idempotencyKey: string;
}

export interface SendAttachmentArgs {
  spaceId: string;
  senderId: string;
  attachmentId: string;
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

export interface MockEvidence {
  contentType: string;
  filename: string;
  sourceLabel: string;
}

export interface MockOutbound {
  id: string;
  kind: "alert" | "reply" | "vet-handoff" | "evidence";
  to: string;
  text: string;
  at: string;
  alertId?: string;
  inReplyTo?: string;
  evidence?: MockEvidence;
}

export interface MessagingState {
  processedInbound: string[];
  latestAlerts: Record<string, AlertSnapshot>;
  turns: Record<string, Turn[]>;
  vetHandoffs: Record<string, VetHandoff>;
  pendingVetConsent: Record<string, PendingVetConsent>;
  activeFarmerByVet: Record<string, string>;
  mockOutbox: MockOutbound[];
  agentUserId: string | null;
  lastPollAt: string | null;
}

export interface PendingVetConsent {
  alertId: string;
  askedAt: string;
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
  | "not-received-imessage"
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
