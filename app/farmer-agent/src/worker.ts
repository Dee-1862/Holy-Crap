import { loadConfig } from "./config";
import { createRuntime } from "./service";

function log(line: string): void {
  console.log(`[worker] ${new Date().toISOString()} ${line}`);
}

async function main(): Promise<void> {
  const config = loadConfig(process.env);
  const { service } = createRuntime(config);

  log(`started (mode=${config.mode}, poll=${config.pollMs}ms)`);
  if (config.mode === "mock") {
    log("mock mode: no inbound polling, no network calls");
  }

  let delay = config.pollMs;
  let timer: NodeJS.Timeout | undefined;
  let wake: (() => void) | undefined;
  let shuttingDown = false;

  const shutdown = (signal: string) => {
    if (shuttingDown) return;
    shuttingDown = true;
    log(`received ${signal}, stopping`);
    if (timer) clearTimeout(timer);
    wake?.();
  };

  process.on("SIGINT", () => shutdown("SIGINT"));
  process.on("SIGTERM", () => shutdown("SIGTERM"));

  while (!shuttingDown) {
    try {
      const result = await service.pollOnce();
      if (config.mode === "live") {
        log(`polled ${result.pages} page(s), handled ${result.processed} message(s)`);
      }
      delay = config.pollMs;
    } catch (err) {
      const message = err instanceof Error ? err.message : "unknown error";
      log(`poll failed: ${message}; retrying in ${delay}ms`);
      delay = Math.min(delay * 2, 60_000);
    }
    if (shuttingDown) break;
    await new Promise<void>((resolve) => {
      wake = resolve;
      timer = setTimeout(() => {
        wake = undefined;
        resolve();
      }, delay);
    });
  }

  log("stopped");
}

const invoked = process.argv[1] && import.meta.url.endsWith(process.argv[1].replace(/^\.\//, ""));
if (invoked) {
  main().catch((err) => {
    console.error("[worker] fatal:", err instanceof Error ? err.message : err);
    process.exit(1);
  });
}
