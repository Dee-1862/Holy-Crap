import path from "node:path";
import type { DeepSeekConfig, MessagingConfig, MessagingMode, PhotonConfig } from "./types";
import { normalizeUsPhone, parseAllowlist } from "./rules";

const DEFAULT_STATE_PATH = path.resolve(process.cwd(), ".data", "messaging-state.json");

function modeOf(raw: string | undefined): MessagingMode {
  const value = (raw ?? "mock").trim().toLowerCase();
  if (value === "mock" || value === "live") return value;
  throw new Error(`Invalid MESSAGING_MODE value "${value}" (expected mock or live)`);
}

function intOf(raw: string | undefined, fallback: number, name: string, min: number): number {
  if (raw === undefined || raw === "") return fallback;
  const value = Number(raw);
  if (!Number.isFinite(value) || value < min) {
    throw new Error(`Invalid ${name} value "${raw}" (expected an integer >= ${min})`);
  }
  return Math.floor(value);
}

export function isPlausiblePhotonUserId(value: string): boolean {
  return /^pho_usr_[A-Za-z0-9_-]{6,}$/.test(value);
}

export function loadConfig(env: NodeJS.ProcessEnv = process.env): MessagingConfig {
  const mode = modeOf(env.MESSAGING_MODE);
  const statePath = env.MESSAGING_STATE_PATH?.trim() || DEFAULT_STATE_PATH;
  const pollMs = intOf(env.MESSAGING_POLL_MS, 10_000, "MESSAGING_POLL_MS", 1_000);
  const timeoutMs = intOf(env.MESSAGING_TIMEOUT_MS, 10_000, "MESSAGING_TIMEOUT_MS", 1_000);

  const rawFarmers = env.FARMER_ALLOWED_NUMBERS?.trim() ?? env.MESSAGING_ALLOWED_NUMBERS?.trim() ?? "";
  const farmerNumbers = rawFarmers ? parseAllowlist(rawFarmers, "FARMER_ALLOWED_NUMBERS") : [];
  const rawVets = env.VET_ALLOWED_NUMBERS?.trim() ?? "";
  const vetNumbers = rawVets ? parseAllowlist(rawVets, "VET_ALLOWED_NUMBERS") : [];
  const defaultVetNumber = env.DEFAULT_VET_NUMBER?.trim()
    ? normalizeUsPhone(env.DEFAULT_VET_NUMBER.trim())
    : null;
  if (env.DEFAULT_VET_NUMBER?.trim() && !defaultVetNumber) {
    throw new Error("DEFAULT_VET_NUMBER must be a valid US phone number");
  }
  if (defaultVetNumber && !vetNumbers.includes(defaultVetNumber)) {
    throw new Error("DEFAULT_VET_NUMBER must also appear in VET_ALLOWED_NUMBERS");
  }
  const overlap = farmerNumbers.find((phone) => vetNumbers.includes(phone));
  if (overlap) throw new Error("Farmer and veterinarian allowlists must not overlap");

  const photon: PhotonConfig = {
    baseUrl: (env.PHOTON_BASE_URL ?? "https://api.photon.codes/v1").replace(/\/+$/, ""),
    apiKey: env.PHOTON_API_KEY?.trim() ?? "",
    projectId: env.PHOTON_PROJECT_ID?.trim() ?? "",
    agentUserId: env.PHOTON_AGENT_USER_ID?.trim() ?? "",
  };
  const deepseek: DeepSeekConfig = {
    baseUrl: env.DEEPSEEK_BASE_URL ?? "https://api.deepseek.com/chat/completions",
    apiKey: env.DEEPSEEK_API_KEY?.trim() ?? "",
    model: env.DEEPSEEK_MODEL?.trim() || "deepseek-flash",
    maxTokens: intOf(env.DEEPSEEK_MAX_TOKENS, 180, "DEEPSEEK_MAX_TOKENS", 16),
  };

  if (mode === "live") {
    const missing: string[] = [];
    if (!photon.apiKey) missing.push("PHOTON_API_KEY");
    if (!photon.projectId) missing.push("PHOTON_PROJECT_ID");
    const agent = isPlausiblePhotonUserId(photon.agentUserId);
    if (!agent) missing.push("PHOTON_AGENT_USER_ID (must look like a Photon user ID, e.g. pho_usr_)");
    if (!deepseek.apiKey) missing.push("DEEPSEEK_API_KEY");
    if (farmerNumbers.length === 0) missing.push("FARMER_ALLOWED_NUMBERS (must not be empty in live mode)");
    if (missing.length) {
      throw new Error(`Live messaging mode is missing required configuration: ${missing.join(", ")}`);
    }
  }

  return {
    mode,
    statePath,
    pollMs,
    timeoutMs,
    farmerNumbers,
    vetNumbers,
    defaultVetNumber,
    photon,
    deepseek,
  };
}
