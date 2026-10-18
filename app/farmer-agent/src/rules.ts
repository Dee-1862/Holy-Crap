import type { AlertSnapshot } from "./types";

export const MAX_REPLY_CHARS = 480;

const CERTAIN_DISEASE_CLAIM =
  /\b(?:confirmed|definitely|certainly|proven|no doubt)\b|(?<!may )(?<!might )(?<!could )\b(?:has|have)\s+(?:coccid\w*|salmonella|newcastle|avian flu|bird flu|influenza)\b|\bis infected with\s+(?:coccid\w*|salmonella|newcastle|avian flu|bird flu|influenza)\b/i;
const UNSAFE_GENERATED_DIRECTIVE =
  /\b(?:cull|euthanize|kill|isolate|quarantine|treat|prescribe|medicate|give (?:them|the birds)|use an? antibiotic)\b/i;
const FARMER_JARGON =
  /\b(?:anomal(?:y|ies)|triage|pathogen|confidence|sensor|handoff|classification|evidence|data freshness|medical finding)\b/i;
const SAFETY_DECISION_QUESTION =
  /\b(?:what|which|should|can|do|how)\b[^?.!]{0,80}\b(?:cull|euthanize|kill|isolate|quarantine|treat|medicine|medication|antibiotic)\w*\b/i;

export type VetIntent = "approve" | "decline" | "mention" | "none";

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
  "You text farmers about what a chicken-pen camera saw.",
  "Use short, common words. Do not use jargon such as anomaly, triage, pathogen, confidence, sensor health, handoff, classification, or evidence context.",
  "You may name the illness in the current alert, but always say it may be wrong. Say things like 'we think it may be salmonella,' never that it is confirmed or certain.",
  "Do not choose medicine, tell the farmer to isolate birds, or tell the farmer to kill birds. A vet makes those choices.",
  "Use plain text only, no Markdown, and no more than 480 characters. Be calm, direct, and helpful.",
  "Explain what the camera saw in simple words and suggest checking the birds. If useful, ask whether the farmer wants you to tell the vet.",
].join("\n");

export const VET_SYSTEM_RULES = [
  SYSTEM_RULES,
  "You are speaking with a vet after the farmer asked you to contact them.",
  "Share only what the camera recorded and make clear that the illness guess may be wrong.",
].join("\n");

function simpleWords(text: string): string {
  return text
    .toLowerCase()
    .replace(/[’]/g, "'")
    .replace(/[^a-z0-9'\s]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

export function vetIntent(text: string, pendingQuestion: boolean, activeChat: boolean): VetIntent {
  const words = simpleWords(text);
  const namesVet = /\bvet(?:erinarian)?\b/.test(words);
  const declines =
    /\b(?:do not|don't|dont|no|no thanks|not now|never mind|nevermind|stop|cancel)\b/.test(words);
  if (declines && (pendingQuestion || activeChat || namesVet)) return "decline";

  const directRequest =
    /\b(?:please\s+)?(?:tell|text|message|call|contact|ask)\s+(?:the\s+|my\s+|our\s+)?vet(?:erinarian)?\b/.test(words) ||
    /\b(?:send|share)\s+(?:this|it|that|the alert|the message)?\s*(?:to|with)\s+(?:the\s+|my\s+|our\s+)?vet(?:erinarian)?\b/.test(words) ||
    /\bcan you\s+(?:tell|text|message|call|contact|ask)\s+(?:the\s+|my\s+|our\s+)?vet(?:erinarian)?\b/.test(words) ||
    /\b(?:let\s+(?:the\s+|my\s+|our\s+)?vet(?:erinarian)?\s+know|bring\s+(?:the\s+|my\s+|our\s+)?vet(?:erinarian)?\s+in|talk\s+to\s+(?:the\s+|my\s+|our\s+)?vet(?:erinarian)?)\b/.test(words);
  const shortApproval =
    /^(?:yes|yes please|yeah|yep|sure|ok|okay|(?:yes |yeah )?go ahead|(?:yes |yeah )?please do|do it|sounds good|that works|absolutely)$/.test(words);
  if (directRequest || (pendingQuestion && shortApproval)) return "approve";
  return namesVet ? "mention" : "none";
}

export function safetyBoundaryReply(question: string, canContactVet: boolean): string | null {
  if (!SAFETY_DECISION_QUESTION.test(question)) return null;
  const offer = canContactVet ? " Want me to tell your vet?" : " Please ask a vet what to do next.";
  return `I can't choose medicine or tell you to separate or kill birds. Please check the birds.${offer}`;
}

export function vetApprovalPrompt(hasVet: boolean): string {
  if (!hasVet) return "I don't have a vet number yet. Ask the team to add one.";
  return "Do you want me to tell your vet what we saw? You can answer in your own words.";
}

export function vetHandoffText(alert: AlertSnapshot): string {
  const illness = alert.suspectedIllness ? `We think it may be ${alert.suspectedIllness}, but that may be wrong. ` : "";
  return sanitizeReply(
    `The farmer asked us to contact you about ${alert.penName}. ${illness}` +
      `The camera saw ${alert.observationCount} unusual droppings in ${alert.windowMinutes} minutes. ` +
      `The latest video was ${alert.cameraSecondsAgo} seconds old. Reply if you need more details.`,
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
      suspectedIllness: alert.suspectedIllness ?? null,
    })
  );
}

export function alertText(snapshot: AlertSnapshot, canContactVet = false): string {
  const opening = snapshot.suspectedIllness
    ? `Hi. We think ${snapshot.penName} may have ${snapshot.suspectedIllness}.`
    : `Hi. Something may be wrong in ${snapshot.penName}.`;
  const offer = canContactVet ? " Want me to tell your vet?" : "";
  return `${opening} We saw ${snapshot.observationCount} droppings that looked unusual in the last ${snapshot.windowMinutes} minutes. Please check the birds.${offer}`;
}

export function fallbackReply(alert: AlertSnapshot | null): string {
  if (!alert) {
    return (
      "I don't have a new warning for your pen. Send the pen name and your question. If a bird looks sick, please ask a vet."
    );
  }
  return alertText(alert);
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
  return (
    text.length <= MAX_REPLY_CHARS &&
    !CERTAIN_DISEASE_CLAIM.test(text) &&
    !UNSAFE_GENERATED_DIRECTIVE.test(text) &&
    !FARMER_JARGON.test(text)
  );
}
