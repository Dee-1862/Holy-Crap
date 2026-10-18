import { loadConfig } from "./config";
import { normalizeUsPhone } from "./rules";
import { createRuntime } from "./service";
import type { AlertSnapshot, DeliverySummary, MessagingConfig } from "./types";

export function demoAlert(penId = "B2"): AlertSnapshot {
  return {
    id: `demo:${penId}:${Date.now()}`,
    penId,
    penName: `Pen ${penId}`,
    observationCount: 3,
    windowMinutes: 15,
    confidence: 0.81,
    cameraSecondsAgo: 8,
    sensorHealthy: true,
    createdAt: new Date().toISOString(),
  };
}

export interface SimulateOptions {
  penId?: string;
  recipients?: string[];
}

export interface SimulateResult {
  mode: string;
  alertId: string;
  deliveries: DeliverySummary[];
}

export async function runSimulation(
  config: MessagingConfig,
  options: SimulateOptions = {},
): Promise<SimulateResult> {
  const { service } = createRuntime(config);
  const alert = demoAlert(options.penId);
  const rawRecipients =
    options.recipients && options.recipients.length > 0 ? options.recipients : [...config.farmerNumbers];
  const normalized = rawRecipients.map((r) => normalizeUsPhone(r) ?? r);
  const deliveries = await service.sendAlert(alert, normalized);
  return { mode: config.mode, alertId: alert.id, deliveries };
}

function parseArgs(argv: string[]): SimulateOptions {
  const options: SimulateOptions = { recipients: [] };
  for (const arg of argv) {
    if (arg.startsWith("--pen=")) options.penId = arg.slice("--pen=".length);
    else if (arg.startsWith("--to=")) options.recipients!.push(...arg.slice("--to=".length).split(",").filter(Boolean));
    else if (arg.startsWith("--")) continue;
    else options.recipients!.push(arg);
  }
  return options;
}

async function main(): Promise<void> {
  const config = loadConfig(process.env);
  const options = parseArgs(process.argv.slice(2));
  const result = await runSimulation(config, options);
  console.log(`[simulate] mode=${result.mode} alert=${result.alertId}`);
  for (const delivery of result.deliveries) {
    console.log(
      `[simulate] ${delivery.status.padEnd(7)} ${delivery.recipient}${delivery.error ? ` (${delivery.error})` : ""}`,
    );
  }
}

const invoked = process.argv[1] && import.meta.url.endsWith(process.argv[1].replace(/^\.\//, ""));
if (invoked) {
  main().catch((err) => {
    console.error("[simulate] fatal:", err instanceof Error ? err.message : err);
    process.exit(1);
  });
}
