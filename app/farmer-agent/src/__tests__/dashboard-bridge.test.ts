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
  const evidencePath = path.join(dir, "pen6.jpg");
  fs.writeFileSync(evidencePath, Buffer.from([0xff, 0xd8, 0xff, 0xd9]));
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
      windowSeconds: 12,
      confidence: 0.81,
      suspectedIllness: "Salmonella",
      createdAt: "2026-10-18T12:00:00.000Z",
      evidence: { localPath: evidencePath, sourceLabel: "Frame from Pen 6." },
    }),
  });

  assert.equal(response.status, 202);
  assert.deepEqual(await response.json(), {
    status: "sent",
    deliveries: [{ status: "queued", alertId: "clip-demo-1" }],
  });
  assert.equal(store.snapshot.latestAlerts[FARMER]?.id, "clip-demo-1");
  assert.equal(store.snapshot.latestAlerts[FARMER]?.source, "simulation-dashboard");
  assert.equal(store.snapshot.latestAlerts[FARMER]?.windowSeconds, 12);
  assert.equal(store.snapshot.latestAlerts[FARMER]?.evidence?.filename, "pen6.jpg");
  assert.equal(
    store.snapshot.mockOutbox[0]?.text,
    "We found 3 droppings in Pen 6 that looked unusual in the 12-second clip. The closest visual match was Salmonella at 81%. This is not a lab test. I saved a frame from the clip.",
  );
  assert.equal(store.snapshot.mockOutbox[1]?.evidence?.filename, "pen6.jpg");
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
