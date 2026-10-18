import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { loadConfig } from "../config";
import { DeepSeekClient } from "../deepseek";
import { PhotonClient } from "../photon";
import {
  alertText,
  isSafeWording,
  normalizeUsPhone,
  sanitizeReply,
  vetHandoffText,
} from "../rules";
import { createRuntime } from "../service";
import { demoAlert, runSimulation } from "../simulate";
import type { MessagingConfig, PhotonMessage } from "../types";

const FARMER = "+12025550123";
const VET = "+12155550199";
const AGENT = "+12675550123";
const NOW = new Date("2026-10-18T12:00:00.000Z");

function tempState(): { dir: string; file: string } {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "holy-crap-agent-test-"));
  return { dir, file: path.join(dir, "state.json") };
}

function config(file: string, overrides: Partial<MessagingConfig> = {}): MessagingConfig {
  const base: MessagingConfig = {
    mode: "mock",
    statePath: file,
    pollMs: 1_000,
    timeoutMs: 1_000,
    farmerNumbers: [FARMER],
    vetNumbers: [VET],
    defaultVetNumber: VET,
    photon: {
      baseUrl: "https://api.photon.codes/v1",
      apiKey: "",
      projectId: "pho_prj_test",
      agentPhone: AGENT,
    },
    deepseek: {
      baseUrl: "https://api.deepseek.com/chat/completions",
      apiKey: "test-only",
      model: "deepseek-flash",
      maxTokens: 180,
    },
  };
  return { ...base, ...overrides };
}

function inbound(id: string, from: string, text: string): PhotonMessage {
  return {
    id,
    platform: "sms",
    status: "received",
    space: { id: "pho_spc_test", platform: "sms", kind: "direct" },
    sentBy: { id: `human-${id}`, platform: "sms", handle: from, kind: "human" },
    receivedBy: { id: "agent-user", platform: "sms", handle: AGENT, kind: "agent" },
    content: { type: "text", format: "plain", text },
    createdAt: NOW.toISOString(),
  };
}

function jsonResponse(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "content-type": "application/json", "x-request-id": "pho_req_test" },
  });
}

test("normalizes US numbers and keeps farmer/vet allowlists separate", () => {
  assert.equal(normalizeUsPhone("202-555-0123"), FARMER);
  assert.equal(normalizeUsPhone("1 (202) 555-0123"), FARMER);
  assert.equal(normalizeUsPhone("555"), null);
  const loaded = loadConfig({
    MESSAGING_MODE: "mock",
    FARMER_ALLOWED_NUMBERS: "202-555-0123",
    VET_ALLOWED_NUMBERS: VET,
    DEFAULT_VET_NUMBER: VET,
  });
  assert.deepEqual(loaded.farmerNumbers, [FARMER]);
  assert.deepEqual(loaded.vetNumbers, [VET]);
  assert.throws(
    () =>
      loadConfig({
        MESSAGING_MODE: "mock",
        VET_ALLOWED_NUMBERS: VET,
        DEFAULT_VET_NUMBER: "+12025550111",
      }),
    /must also appear/,
  );
  assert.throws(
    () =>
      loadConfig({
        MESSAGING_MODE: "mock",
        FARMER_ALLOWED_NUMBERS: FARMER,
        VET_ALLOWED_NUMBERS: FARMER,
      }),
    /must not overlap/,
  );
});

test("demo alert and vet handoff stay non-diagnostic", () => {
  const alert = demoAlert("B2");
  for (const text of [alertText(alert), vetHandoffText(alert)]) {
    assert.equal(isSafeWording(text), true);
    assert.doesNotMatch(text, /coccid|salmonella|newcastle|avian flu/i);
    assert.match(text, /not (?:a medical finding|a diagnosis)/i);
  }
});

test("unauthorized inbound never calls DeepSeek or sends a reply", async (t) => {
  const tmp = tempState();
  t.after(() => fs.rmSync(tmp.dir, { recursive: true, force: true }));
  let calls = 0;
  const neverFetch = async () => {
    calls += 1;
    throw new Error("network must not be called");
  };
  const { service, store } = createRuntime(config(tmp.file), {
    fetch: neverFetch as typeof fetch,
    deepseekFetch: neverFetch as typeof fetch,
    clock: () => NOW,
  });
  const result = await service.processInbound(inbound("pho_msg_unauthorized", "+12025550111", "What happened?"));
  assert.deepEqual(result, { handled: false, reason: "unauthorized" });
  assert.equal(calls, 0);
  assert.equal(store.snapshot.mockOutbox.length, 0);
});

test("authorized farmer gets a concise same-conversation reply and duplicates are ignored", async (t) => {
  const tmp = tempState();
  t.after(() => fs.rmSync(tmp.dir, { recursive: true, force: true }));
  let llmCalls = 0;
  const llmFetch = async () => {
    llmCalls += 1;
    return jsonResponse({ choices: [{ message: { content: "**Three unusual observations** were recorded. Review the evidence clip; the camera cannot diagnose disease." } }] });
  };
  const { service, store } = createRuntime(config(tmp.file), {
    fetch: (async () => {
      throw new Error("Photon should not run in mock mode");
    }) as typeof fetch,
    deepseekFetch: llmFetch as typeof fetch,
    clock: () => NOW,
  });
  await service.sendAlert(demoAlert("B2"), [FARMER]);
  const message = inbound("pho_msg_farmer_1", FARMER, "What is this?");
  const first = await service.processInbound(message);
  const second = await service.processInbound(message);
  assert.equal(first.handled, true);
  assert.equal(second.reason, "duplicate");
  assert.equal(llmCalls, 1);
  const reply = store.snapshot.mockOutbox.find((item) => item.inReplyTo === message.id);
  assert.equal(reply?.to, FARMER);
  assert.ok(reply && reply.text.length <= 480);
  assert.doesNotMatch(reply?.text ?? "", /[*#`]/);
});

test("treatment or culling questions use a deterministic boundary without calling the LLM", async (t) => {
  const tmp = tempState();
  t.after(() => fs.rmSync(tmp.dir, { recursive: true, force: true }));
  let llmCalls = 0;
  const { service } = createRuntime(config(tmp.file), {
    fetch: (async () => {
      throw new Error("Photon should not run in mock mode");
    }) as typeof fetch,
    deepseekFetch: (async () => {
      llmCalls += 1;
      throw new Error("LLM should not be called for this decision");
    }) as typeof fetch,
    clock: () => NOW,
  });
  const result = await service.processInbound(
    inbound("pho_msg_safety_boundary", FARMER, "Should I treat or cull these birds?"),
  );
  assert.equal(result.handled, true);
  assert.equal(llmCalls, 0);
  assert.match(result.reply ?? "", /cannot diagnose disease/);
  assert.match(result.reply ?? "", /contact a veterinarian/);
});

test("unsafe generated instructions are discarded for the deterministic fallback", async (t) => {
  const tmp = tempState();
  t.after(() => fs.rmSync(tmp.dir, { recursive: true, force: true }));
  const { service } = createRuntime(config(tmp.file), {
    fetch: (async () => {
      throw new Error("Photon should not run in mock mode");
    }) as typeof fetch,
    deepseekFetch: (async () =>
      jsonResponse({ choices: [{ message: { content: "Cull the affected birds immediately." } }] })) as typeof fetch,
    clock: () => NOW,
  });
  await service.sendAlert(demoAlert("B2"), [FARMER]);
  const result = await service.processInbound(inbound("pho_msg_unsafe_llm", FARMER, "What happened?"));
  assert.equal(result.handled, true);
  assert.doesNotMatch(result.reply ?? "", /cull/i);
  assert.match(result.reply ?? "", /anomaly flag/i);
});

test("vet is contacted only after the farmer sends the exact approval command", async (t) => {
  const tmp = tempState();
  t.after(() => fs.rmSync(tmp.dir, { recursive: true, force: true }));
  let llmCalls = 0;
  const llmFetch = async () => {
    llmCalls += 1;
    return jsonResponse({ choices: [{ message: { content: "Review the current evidence and sensor status." } }] });
  };
  const { service, store } = createRuntime(config(tmp.file), {
    fetch: (async () => {
      throw new Error("Photon should not run in mock mode");
    }) as typeof fetch,
    deepseekFetch: llmFetch as typeof fetch,
    clock: () => NOW,
  });
  await service.sendAlert(demoAlert("B2"), [FARMER]);

  const request = await service.processInbound(inbound("pho_msg_vet_request", FARMER, "Can you ask the vet?"));
  assert.equal(request.handled, true);
  assert.match(request.reply ?? "", /Reply APPROVE VET/);
  assert.equal(store.snapshot.mockOutbox.filter((item) => item.kind === "vet-handoff").length, 0);
  assert.equal(llmCalls, 0);

  const approvalMessage = inbound("pho_msg_vet_approval", FARMER, "APPROVE VET");
  const approval = await service.processInbound(approvalMessage);
  assert.equal(approval.handled, true);
  const handoffs = store.snapshot.mockOutbox.filter((item) => item.kind === "vet-handoff");
  assert.equal(handoffs.length, 1);
  assert.equal(handoffs[0].to, VET);
  assert.equal(store.snapshot.vetHandoffs[FARMER].status, "approved");
  assert.equal(llmCalls, 0);

  const duplicate = await service.processInbound(approvalMessage);
  assert.equal(duplicate.reason, "duplicate");
  assert.equal(store.snapshot.mockOutbox.filter((item) => item.kind === "vet-handoff").length, 1);

  const secondApproval = await service.processInbound(inbound("pho_msg_vet_approval_again", FARMER, "APPROVE VET"));
  assert.equal(secondApproval.handled, true);
  assert.match(secondApproval.reply ?? "", /already active/);
  assert.equal(store.snapshot.mockOutbox.filter((item) => item.kind === "vet-handoff").length, 1);
});

test("vet inbound is ignored before approval and answered after approval", async (t) => {
  const tmp = tempState();
  t.after(() => fs.rmSync(tmp.dir, { recursive: true, force: true }));
  let llmCalls = 0;
  const llmFetch = async () => {
    llmCalls += 1;
    return jsonResponse({ choices: [{ message: { content: "The camera recorded three repeated appearance anomalies; sensor health is normal." } }] });
  };
  const { service, store } = createRuntime(config(tmp.file), {
    fetch: (async () => {
      throw new Error("Photon should not run in mock mode");
    }) as typeof fetch,
    deepseekFetch: llmFetch as typeof fetch,
    clock: () => NOW,
  });
  await service.sendAlert(demoAlert("B2"), [FARMER]);
  const early = await service.processInbound(inbound("pho_msg_vet_early", VET, "What did the camera see?"));
  assert.equal(early.reason, "unauthorized");
  assert.equal(llmCalls, 0);

  await service.processInbound(inbound("pho_msg_vet_approve2", FARMER, "APPROVE VET"));
  const after = await service.processInbound(inbound("pho_msg_vet_after", VET, "What did the camera see?"));
  assert.equal(after.handled, true);
  assert.equal(llmCalls, 1);
  assert.ok(store.snapshot.mockOutbox.some((item) => item.to === VET && item.inReplyTo === "pho_msg_vet_after"));
});

test("DeepSeek request disables thinking and reply sanitization is bounded", async () => {
  const bodies: Record<string, unknown>[] = [];
  const client = new DeepSeekClient({
    config: config("unused").deepseek,
    timeoutMs: 1_000,
    fetch: (async (_url: string | URL | Request, init?: RequestInit) => {
      bodies.push(JSON.parse(String(init?.body)) as Record<string, unknown>);
      return jsonResponse({ choices: [{ message: { content: `# ${"word ".repeat(200)}` } }] });
    }) as typeof fetch,
  });
  const raw = await client.chat([{ role: "user", content: "hello" }]);
  assert.deepEqual(bodies[0]?.thinking, { type: "disabled" });
  const safe = sanitizeReply(raw ?? "");
  assert.ok(safe.length <= 480);
  assert.doesNotMatch(safe, /#/);
});

test("Photon client follows Beta items and nested message contract", async () => {
  const requests: { url: string; init?: RequestInit }[] = [];
  const client = new PhotonClient({
    baseUrl: "https://api.photon.codes/v1",
    apiKey: "test-only",
    projectId: "pho_prj_test",
    timeoutMs: 1_000,
    fetch: (async (url: string | URL | Request, init?: RequestInit) => {
      requests.push({ url: String(url), init });
      return jsonResponse({ items: [inbound("pho_msg_contract", FARMER, "hi")], nextPageToken: null });
    }) as typeof fetch,
  });
  const page = await client.listReceivedMessages({ createdSince: NOW.toISOString() });
  assert.equal(page.items[0].space.id, "pho_spc_test");
  assert.match(requests[0].url, /direction=received/);
  assert.match(requests[0].url, /platform=sms/);
  assert.equal(requests[0].init?.headers && (requests[0].init.headers as Record<string, string>).Authorization, "Bearer test-only");
});

test("mock simulation queues only the configured farmer recipient", async (t) => {
  const tmp = tempState();
  t.after(() => fs.rmSync(tmp.dir, { recursive: true, force: true }));
  const result = await runSimulation(config(tmp.file));
  assert.equal(result.mode, "mock");
  assert.deepEqual(result.deliveries.map((item) => item.status), ["queued"]);
  const saved = JSON.parse(fs.readFileSync(tmp.file, "utf8")) as { mockOutbox: { to: string }[] };
  assert.deepEqual(saved.mockOutbox.map((item) => item.to), [FARMER]);
});
