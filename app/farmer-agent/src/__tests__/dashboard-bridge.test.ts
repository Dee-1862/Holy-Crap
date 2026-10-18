import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { createDashboardAlertServer } from "../dashboard-bridge";
import { createRuntime } from "../service";
import type { MessagingConfig } from "../types";

const FARMER = "+12025550123";

test("dashboard bridge sends the plain simulation alert and saves its context", async (t) => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "holy-crap-dashboard-bridge-"));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const config: MessagingConfig = {
    mode: "mock",
    statePath: path.join(dir, "state.json"),
    pollMs: 1_000,
    timeoutMs: 1_000,
    farmerNumbers: [FARMER],
    vetNumbers: [],
    defaultVetNumber: null,
    photon: { baseUrl: "https://api.photon.codes/v1", apiKey: "", projectId: "", agentUserId: "" },
    deepseek: { baseUrl: "https://api.deepseek.com/chat/completions", apiKey: "", model: "deepseek-flash", maxTokens: 180 },
  };
  const { service, store } = createRuntime(config);
  const server = createDashboardAlertServer(service, config.farmerNumbers);
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  t.after(() => server.close());
  const address = server.address();
  assert.ok(address && typeof address === "object");

  const response = await fetch(`http://127.0.0.1:${address.port}/simulation-alerts`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      eventId: "clip-demo-1",
      penName: "Pen 6",
      observationCount: 3,
      windowMinutes: 2,
      confidence: 0.81,
      suspectedIllness: "Salmonella",
      createdAt: "2026-10-18T12:00:00.000Z",
    }),
  });

  assert.equal(response.status, 202);
  assert.deepEqual(await response.json(), {
    status: "sent",
    deliveries: [{ status: "queued", alertId: "clip-demo-1" }],
  });
  assert.equal(store.snapshot.latestAlerts[FARMER]?.id, "clip-demo-1");
  assert.equal(store.snapshot.latestAlerts[FARMER]?.source, "simulation-dashboard");
  assert.equal(
    store.snapshot.mockOutbox[0]?.text,
    "Simulation alert: We found 3 droppings in Pen 6 that looked unusual during the 2-minute clip. The model's closest match was Salmonella, with an 81% score. This is not a lab test. What else would help you decide what to do next?",
  );
});

test("dashboard bridge rejects incomplete alerts", async (t) => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "holy-crap-dashboard-bridge-"));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const config: MessagingConfig = {
    mode: "mock", statePath: path.join(dir, "state.json"), pollMs: 1_000, timeoutMs: 1_000,
    farmerNumbers: [FARMER], vetNumbers: [], defaultVetNumber: null,
    photon: { baseUrl: "https://api.photon.codes/v1", apiKey: "", projectId: "", agentUserId: "" },
    deepseek: { baseUrl: "", apiKey: "", model: "deepseek-flash", maxTokens: 180 },
  };
  const { service } = createRuntime(config);
  const server = createDashboardAlertServer(service, config.farmerNumbers);
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  t.after(() => server.close());
  const address = server.address();
  assert.ok(address && typeof address === "object");
  const response = await fetch(`http://127.0.0.1:${address.port}/simulation-alerts`, {
    method: "POST", headers: { "content-type": "application/json" }, body: "{}",
  });
  assert.equal(response.status, 400);
});
