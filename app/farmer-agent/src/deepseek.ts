import type { ChatMessage, DeepSeekConfig } from "./types";

export interface DeepSeekDeps {
  config: DeepSeekConfig;
  timeoutMs: number;
  fetch: typeof globalThis.fetch;
}

// Thin client for the official DeepSeek OpenAI-compatible chat endpoint.
// Returns null on any failure so callers can use the deterministic fallback.
export class DeepSeekClient {
  private readonly config: DeepSeekConfig;
  private readonly timeoutMs: number;
  private readonly fetchImpl: typeof globalThis.fetch;

  constructor(deps: DeepSeekDeps) {
    this.config = deps.config;
    this.timeoutMs = deps.timeoutMs;
    this.fetchImpl = deps.fetch;
  }

  async chat(messages: ChatMessage[]): Promise<string | null> {
    if (!this.config.apiKey) return null;
    let response: Response;
    try {
      response = await this.fetchImpl(this.config.baseUrl, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${this.config.apiKey}`,
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: JSON.stringify({
          model: this.config.model,
          messages,
          stream: false,
          max_tokens: this.config.maxTokens,
          temperature: 0,
          thinking: { type: "disabled" },
        }),
        signal: AbortSignal.timeout(this.timeoutMs),
      });
    } catch {
      return null;
    }
    if (!response.ok) return null;
    try {
      const body = (await response.json()) as {
        choices?: { message?: { content?: unknown } }[];
      };
      const content = body.choices?.[0]?.message?.content;
      return typeof content === "string" && content.trim() ? content.trim() : null;
    } catch {
      return null;
    }
  }
}
