import type { AlertSnapshot } from "./types";

export const MAX_REPLY_CHARS = 480;

const DISEASE_NAME_OR_CLAIM =
  /coccid|salmonella|newcastle|avian flu|bird flu|influenza|pathogen identified|camera (?:shows|found|confirmed|detected) (?:an )?infection/i;
const UNSAFE_GENERATED_DIRECTIVE = /\b(?:cull|euthan|isolate|quarantine|treat|prescrib|medicat|antibiotic)\w*\b/i;
const SAFETY_DECISION_QUESTION = /\b(?:diagnos|disease|infection|pathogen|cull|euthan|isolate|quarantine|treat|prescrib|medicat|antibiotic)\w*\b/i;

export function normalizeUsPhone(input: string): string | null {
  const cleaned = input.replace(/[^\d+]/g, "");
  if (!cleaned) return null;
  if (cleaned.startsWith("+")) {
    return /^\+1[2-9]\d{9}$/.test(cleaned) ? cleaned : null;
  }
  if (/^1[2-9]\d{9}$/.test(cleaned)) return `+${cleaned}`;
  if (/^[2-9]\d{9}$/.test(cleaned)) return `+1${cleaned}`;
  return null;
}

export function maskPhone(phone: string): string {
  if (phone.length <= 5) return "•••••";
  return `${phone.slice(0, 5)}•••••${phone.slice(-2)}`;
}

export function parseAllowlist(raw: string, name = "MESSAGING_ALLOWED_NUMBERS"): string[] {
  const out: string[] = [];
  for (const part of raw.split(",")) {
    const trimmed = part.trim();
    if (!trimmed) continue;
    const normalized = normalizeUsPhone(trimmed);
    if (!normalized) {
      throw new Error(`Invalid phone number in ${name}: ${maskPhone(trimmed)}`);
    }
    out.push(normalized);
  }
  return [...new Set(out)];
}

export function isAllowedNumber(phone: string, allowlist: string[]): boolean {
  const normalized = normalizeUsPhone(phone);
  return normalized !== null && allowlist.includes(normalized);
}

export const SYSTEM_RULES = [
  "You are the SMS responder for a poultry barn camera system. Your only role is explainable anomaly triage for a farmer.",
  "Hard limits: you never diagnose disease, never name a disease as a conclusion, never claim pathogen identification, never prescribe treatment, and never recommend isolation or culling. Laboratory testing and a veterinarian confirm any disease; the camera never does.",
  "If the farmer asks for a diagnosis, treatment, isolation, or culling, explain the limit and recommend veterinary/animal-health guidance.",
  "Message style: plain text only, no Markdown, at most 480 characters, factual and calm, explicit about uncertainty.",
  "Surface the observations, how long the pattern has persisted, model confidence, data freshness, and sensor health, and always end with the next human review step.",
].join("\n");

export const VET_SYSTEM_RULES = [
  SYSTEM_RULES,
  "You are speaking with a veterinarian after the farmer explicitly approved this handoff.",
  "Share only the recorded observation context. Do not imply that the camera made a diagnosis or replace the veterinarian's judgment.",
].join("\n");

export const APPROVE_VET_COMMAND = "APPROVE VET";
export const CANCEL_VET_COMMAND = "CANCEL VET";

export function normalizedCommand(text: string): string {
  return text.trim().replace(/\s+/g, " ").toUpperCase();
}

export function safetyBoundaryReply(question: string): string | null {
  if (!SAFETY_DECISION_QUESTION.test(question)) return null;
  return (
    "The camera cannot diagnose disease, identify a pathogen, prescribe treatment, recommend isolation, or make culling decisions. " +
    "Review the birds and evidence, then contact a veterinarian or animal-health authority and follow their guidance."
  );
}

export function vetApprovalPrompt(hasVet: boolean): string {
  if (!hasVet) return "Vet messaging is not configured yet. Ask the team to add a verified veterinarian number.";
  return "I can share this camera alert with the verified veterinarian. Reply APPROVE VET to consent. Nothing will be sent until you do.";
}

export function vetHandoffText(alert: AlertSnapshot): string {
  return sanitizeReply(
    `Farmer-approved Holy-Crap handoff for ${alert.penName}: ${alert.observationCount} unusual dropping appearances within ${alert.windowMinutes} minutes. ` +
      `Model confidence ${Math.round(alert.confidence * 100)}%. Camera data is ${alert.cameraSecondsAgo} seconds old; ` +
      `${alert.sensorHealthy ? "sensors report healthy" : "sensor status needs review"}. This is camera triage, not a diagnosis. Reply with questions for the agent.`,
  );
}

export function contextBlock(alert: AlertSnapshot | null): string {
  if (!alert) return "Current pen context: no current camera alert.";
  return (
    "Current pen context: " +
    JSON.stringify({
      pen: alert.penName,
      unusualObservations: alert.observationCount,
      windowMinutes: alert.windowMinutes,
      confidence: Math.round(alert.confidence * 100) / 100,
      cameraSecondsAgo: alert.cameraSecondsAgo,
      sensorHealthy: alert.sensorHealthy,
    })
  );
}

export function alertText(snapshot: AlertSnapshot): string {
  const pct = Math.round(snapshot.confidence * 100);
  const sensor = snapshot.sensorHealthy ? "sensors report healthy" : "sensor status needs a check";
  return (
    `Holy-Crap camera alert for ${snapshot.penName}: ${snapshot.observationCount} unusual dropping appearances ` +
    `within the last ${snapshot.windowMinutes} minutes. Model confidence ${pct}%. ` +
    `Camera footage is ${snapshot.cameraSecondsAgo} seconds old and ${sensor}. ` +
    `This is an anomaly flag for human review, not a medical finding. ` +
    `Review the recorded evidence and contact a veterinarian if the pattern persists or birds show concerning signs.`
  );
}

export function fallbackReply(alert: AlertSnapshot | null): string {
  if (!alert) {
    return (
      "No current camera alerts for your pen. Send the pen name or your question and the team will review. " +
      "For animal-health concerns, contact a veterinarian."
    );
  }
  const pct = Math.round(alert.confidence * 100);
  const sensor = alert.sensorHealthy ? "sensors healthy" : "sensor status needs a check";
  return (
    `Heads-up from your barn camera: ${alert.penName} shows ${alert.observationCount} unusual dropping ` +
    `appearances within the last ${alert.windowMinutes} minutes. Confidence ${pct}%, ` +
    `camera footage ${alert.cameraSecondsAgo} seconds old, ${sensor}. This is an anomaly flag for human ` +
    `review, not a medical finding. Review the recorded evidence and contact a veterinarian if the pattern ` +
    `persists or birds show concerning signs.`
  );
}

export function sanitizeReply(raw: string): string {
  let text = raw
    .replace(/\[([^\]]*)\]\([^)]*\)/g, "$1")
    .replace(/[#*_>`~|]/g, "")
    .replace(/\s+/g, " ")
    .trim();
  text = text.replace(/[^\x20-\x7E]/g, "");
  if (text.length <= MAX_REPLY_CHARS) return text;
  const cut = text.slice(0, MAX_REPLY_CHARS);
  const lastSpace = cut.lastIndexOf(" ");
  return (lastSpace > MAX_REPLY_CHARS * 0.6 ? cut.slice(0, lastSpace) : cut).trim();
}

export function isSafeWording(text: string): boolean {
  return text.length <= MAX_REPLY_CHARS && !DISEASE_NAME_OR_CLAIM.test(text) && !UNSAFE_GENERATED_DIRECTIVE.test(text);
}
