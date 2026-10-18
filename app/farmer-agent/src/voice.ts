export interface VoiceConfig {
  provider: string | null;
  providerUrl: string | null;
  providerToken: string | null;
}

export interface VoiceCallResult {
  status: "unconfigured" | "pending-implementation";
  reason: string;
}

export function loadVoiceConfig(env: NodeJS.ProcessEnv = process.env): VoiceConfig {
  return {
    provider: env.VOICE_PROVIDER?.trim() || null,
    providerUrl: env.VOICE_PROVIDER_URL?.trim() || null,
    providerToken: env.VOICE_PROVIDER_TOKEN?.trim() || null,
  };
}

// Scaffold only. No provider is implemented and no call is ever placed.
// A future provider implementation may use providerUrl/providerToken once
// VOICE_PROVIDER is set, but nothing in this class touches the network.
export class VoiceAdapter {
  private readonly config: VoiceConfig;

  constructor(config: VoiceConfig = loadVoiceConfig()) {
    this.config = config;
  }

  get configured(): boolean {
    return Boolean(this.config.provider && this.config.providerUrl && this.config.providerToken);
  }

  async placeCall(recipient: string, message: string): Promise<VoiceCallResult> {
    if (!this.configured) {
      return {
        status: "unconfigured",
        reason:
          "Voice is not configured. Set VOICE_PROVIDER, VOICE_PROVIDER_URL and VOICE_PROVIDER_TOKEN before any call can be placed. No call was attempted.",
      };
    }
    return {
      status: "pending-implementation",
      reason: `Voice provider "${this.config.provider}" is configured, but no provider implementation is wired up yet. No call was placed.`,
    };
  }
}
