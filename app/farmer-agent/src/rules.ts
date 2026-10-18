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
  "Use only the exact alert facts you are given. Do not invent numbers, times, names, or lab results.",
  "Answer the question immediately in at most 3 short sentences. No greeting, no filler, no extra questions.",
  "The top match is a camera guess, not a lab test. State the match and score as given. Do not add hedges or repeat disclaimers.",
  "Do not choose medicine, isolation, or killing. A vet makes those choices.",
  "Use short, common words. Do not use jargon such as anomaly, triage, pathogen, confidence, sensor, handoff, classification, or evidence context.",
  "Use plain text only, no Markdown, and no more than 480 characters.",
].join("\n");

export const VET_SYSTEM_RULES = [
  SYSTEM_RULES,
  "You are speaking with a vet after the farmer asked you to contact them.",
  "Share only the recorded alert facts and make clear that the top match is not a lab test.",
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

export function scorePercent(confidence: number): number {
  return Math.round(confidence * 100);
}

export function vetHandoffText(alert: AlertSnapshot): string {
  const score = scorePercent(alert.confidence);
  const match = alert.suspectedIllness
    ? ` The model's closest match was ${alert.suspectedIllness}, with an ${score}% score.`
    : "";
  return sanitizeReply(
    `The farmer asked us to contact you about ${alert.penName}. We found ${alert.observationCount} droppings that looked unusual in ${alert.windowMinutes} minutes.${match} This is not a lab test. The latest camera picture was ${alert.cameraSecondsAgo} seconds old. Reply if you need more details.`,
  );
}

export function contextBlock(alert: AlertSnapshot | null): string {
  if (!alert) return "Current pen context: no current camera alert.";
  return (
    "Current pen context: " +
    JSON.stringify({
      pen: alert.penName,
      droppings: alert.observationCount,
      windowMinutes: alert.windowMinutes,
      topMatch: alert.suspectedIllness ?? null,
      score: scorePercent(alert.confidence),
      cameraSecondsAgo: alert.cameraSecondsAgo,
      hasPhoto: Boolean(alert.evidence),
    })
  );
}

export function alertText(snapshot: AlertSnapshot, canContactVet = false): string {
  const score = scorePercent(snapshot.confidence);
  const match = snapshot.suspectedIllness
    ? ` The model's closest match was ${snapshot.suspectedIllness}, with an ${score}% score.`
    : "";
  const vetOffer = canContactVet ? " I can also send this to your vet if you want." : "";
  return (
    `Hey, we found ${snapshot.observationCount} droppings in ${snapshot.penName} that looked unusual ` +
    `in the last ${snapshot.windowMinutes} minutes.${match} This is not a lab test. ` +
    `What else would help you decide what to do next?${vetOffer}`
  );
}

export function fallbackReply(alert: AlertSnapshot | null): string {
  if (!alert) {
    return (
      "There is no current alert for your pen. Send the pen name and your question. If a bird looks sick, please ask a vet."
    );
  }
  const score = scorePercent(alert.confidence);
  const match = alert.suspectedIllness
    ? ` The model's closest match was ${alert.suspectedIllness}, with an ${score}% score.`
    : "";
  return (
    `We found ${alert.observationCount} droppings in ${alert.penName} that looked unusual ` +
    `in the last ${alert.windowMinutes} minutes.${match} This is not a lab test.`
  );
}

export type FactQuestion = "why" | "seen" | "score" | "when";

// Plain questions about the current alert get deterministic answers in
// application code, before DeepSeek ever runs.
export function factQuestionKind(text: string): FactQuestion | null {
  const words = simpleWords(text);
  if (
    /\b(top|closest|best) match\b/.test(words) ||
    /(which|what) (illness|disease|sickness)/.test(words) ||
    /\bwhy\b/.test(words) && /(think|match|guess|illness|disease|sick|salmonella|that|this)/.test(words)
  ) {
    return "why";
  }
  if (/\bwhat (did|do) you see\b|\bwhat was seen\b|\bwhat happened\b|\bwhat did the camera see\b|\bwhat('s| is) (this|it)\b/.test(words)) {
    return "seen";
  }
  if (/\bhow (sure|confident|certain|likely)\b|\bare you sure\b|\bscore\b|\bwhat percent(age)?\b/.test(words)) {
    return "score";
  }
  if (/\bhow (recent|long ago|old)\b|\bwhen (did|was)\b/.test(words)) {
    return "when";
  }
  return null;
}

// Deterministic answers built only from AlertSnapshot facts.
export function factAnswer(kind: FactQuestion, alert: AlertSnapshot | null): string {
  if (!alert) return "There is no current alert for your pen.";
  const score = scorePercent(alert.confidence);
  const count = alert.observationCount;
  const pen = alert.penName;
  const window = alert.windowMinutes;
  const ago = alert.cameraSecondsAgo;
  switch (kind) {
    case "why": {
      if (!alert.suspectedIllness) {
        return `We found ${count} droppings in ${pen} that looked unusual during ${window} minutes. This comes from the camera images, not a lab test.`;
      }
      return (
        `We found ${count} droppings in ${pen} that looked unusual during ${window} minutes. ` +
        `The model's closest match for those droppings was ${alert.suspectedIllness}, with an ${score}% score. ` +
        `This comes from the images, not a lab test.`
      );
    }
    case "seen":
      return `We found ${count} droppings in ${pen} that looked unusual in the last ${window} minutes. The camera picture was ${ago} seconds old.`;
    case "score": {
      if (!alert.suspectedIllness) {
        return `The camera found ${count} unusual droppings in ${pen}. There is no illness match yet. This is not a lab test.`;
      }
      return `The model's closest match was ${alert.suspectedIllness}, with an ${score}% score. This is not a lab test.`;
    }
    case "when":
      return `This happened in the last ${window} minutes. The camera picture was ${ago} seconds old.`;
  }
}

// Plain requests for the saved photo. Answered deterministically, never by DeepSeek.
export function isImageRequest(text: string): boolean {
  const words = simpleWords(text);
  return /\b(show me( the)?|send( me)?( the)?|can (?:i see|you send)( me)?( the)?|i want to see( the)?|got (a|the)) (photo|picture|image|poop|pic)\b/.test(
    words,
  );
}

export function imageRequestReply(alert: AlertSnapshot | null): string {
  if (!alert?.evidence) return "There is no photo to send right now.";
  return `Here is the photo. ${alert.evidence.sourceLabel}`;
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
