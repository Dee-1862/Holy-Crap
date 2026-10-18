import assert from "node:assert/strict";
import { createHash } from "node:crypto";
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
  vetIntent,
} from "../rules";
import { createRuntime } from "../service";
import { demoAlert, runSimulation } from "../simulate";
import { MessagingStore } from "../state";
import type { MessagingConfig, PhotonMessage } from "../types";

const FARMER = "+12025550123";
const VET = "+12155550199";
const AGENT = "+12675550123";
const AGENT_USER_ID = "pho_usr_agent_test";
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
      agentUserId: AGENT_USER_ID,
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
    platform: "imessage",
    status: "received",
    space: { id: "pho_spc_test", platform: "imessage", kind: "direct" },
    sentBy: { id: `pho_usr_human_${id}`, platform: "imessage", handle: from, kind: "human" },
    receivedBy: { id: AGENT_USER_ID, platform: "imessage", handle: AGENT, kind: "agent" },
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

test("live config requires a plausible Photon agent user ID, not a phone number", () => {
  const base = {
    MESSAGING_MODE: "live",
    FARMER_ALLOWED_NUMBERS: FARMER,
    PHOTON_API_KEY: "test-only",
    PHOTON_PROJECT_ID: "pho_prj_test",
    DEEPSEEK_API_KEY: "test-only",
  };
  assert.throws(() => loadConfig({ ...base }), /PHOTON_AGENT_USER_ID/);
  assert.throws(() => loadConfig({ ...base, PHOTON_AGENT_USER_ID: "" }), /PHOTON_AGENT_USER_ID/);
  assert.throws(() => loadConfig({ ...base, PHOTON_AGENT_USER_ID: AGENT }), /PHOTON_AGENT_USER_ID/);
  assert.throws(() => loadConfig({ ...base, PHOTON_AGENT_USER_ID: "pho_usr_" }), /PHOTON_AGENT_USER_ID/);
  assert.throws(() => loadConfig({ ...base, PHOTON_AGENT_PHONE: AGENT }), /PHOTON_AGENT_USER_ID/);
  const loaded = loadConfig({ ...base, PHOTON_AGENT_USER_ID: AGENT_USER_ID });
  assert.equal(loaded.photon.agentUserId, AGENT_USER_ID);
  assert.ok(!("agentPhone" in loaded.photon));
});

test("demo alert names the suspected illness in simple, uncertain words", () => {
  const alert = demoAlert("6");
  const farmerText = alertText(alert, true);
  const vetText = vetHandoffText(alert);
  assert.equal(isSafeWording(farmerText), true);
  assert.equal(isSafeWording(vetText), true);
  assert.match(farmerText, /We think Pen 6 may have salmonella/);
  assert.match(farmerText, /Want me to tell your vet\?/);
  assert.doesNotMatch(farmerText, /anomaly|triage|pathogen|confidence|sensor|handoff|classification|medical finding/i);
  assert.match(vetText, /may be salmonella, but that may be wrong/i);
});

test("common farmer replies map to clear vet choices", () => {
  for (const text of ["yes", "yes, please do", "sure", "go ahead", "sounds good"]) {
    assert.equal(vetIntent(text, true, false), "approve", text);
  }
  for (const text of ["tell the vet", "let my vet know", "please talk to the veterinarian"]) {
    assert.equal(vetIntent(text, false, false), "approve", text);
  }
  for (const text of ["no thanks", "don't contact the vet", "stop talking to the vet"]) {
    assert.equal(vetIntent(text, true, true), "decline", text);
  }
  assert.equal(vetIntent("yes", false, false), "none");
  assert.equal(vetIntent("Do I need a vet?", false, false), "mention");
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
    return jsonResponse({ choices: [{ message: { content: "**We saw three unusual droppings.** Please check the birds." } }] });
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
  assert.match(result.reply ?? "", /can't choose medicine/);
  assert.match(result.reply ?? "", /Want me to tell your vet\?/);
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
  assert.match(result.reply ?? "", /may have salmonella/i);
});

test("a short natural yes approves only after the agent asked about the vet", async (t) => {
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
  const noContext = await service.processInbound(inbound("pho_msg_yes_without_prompt", FARMER, "yes"));
  assert.equal(noContext.handled, true);
  assert.equal(store.snapshot.mockOutbox.filter((item) => item.kind === "vet-handoff").length, 0);
  assert.equal(llmCalls, 1);

  await service.sendAlert(demoAlert("B2"), [FARMER]);
  const approvalMessage = inbound("pho_msg_vet_approval", FARMER, "yes please");
  const approval = await service.processInbound(approvalMessage);
  assert.equal(approval.handled, true);
  const handoffs = store.snapshot.mockOutbox.filter((item) => item.kind === "vet-handoff");
  assert.equal(handoffs.length, 1);
  assert.equal(handoffs[0].to, VET);
  assert.equal(store.snapshot.vetHandoffs[FARMER].status, "approved");
  assert.equal(llmCalls, 1);

  const duplicate = await service.processInbound(approvalMessage);
  assert.equal(duplicate.reason, "duplicate");
  assert.equal(store.snapshot.mockOutbox.filter((item) => item.kind === "vet-handoff").length, 1);

  const secondApproval = await service.processInbound(
    inbound("pho_msg_vet_approval_again", FARMER, "please tell the vet again"),
  );
  assert.equal(secondApproval.handled, true);
  assert.match(secondApproval.reply ?? "", /already in this chat/);
  assert.equal(store.snapshot.mockOutbox.filter((item) => item.kind === "vet-handoff").length, 1);
});

test("a direct natural request contacts the vet without a command", async (t) => {
  const tmp = tempState();
  t.after(() => fs.rmSync(tmp.dir, { recursive: true, force: true }));
  const { service, store } = createRuntime(config(tmp.file), {
    fetch: (async () => { throw new Error("Photon should not run in mock mode"); }) as typeof fetch,
    deepseekFetch: (async () => { throw new Error("LLM should not decide permission"); }) as typeof fetch,
    clock: () => NOW,
  });
  await service.sendAlert(demoAlert("B2"), [FARMER]);
  store.update((state) => { delete state.pendingVetConsent[FARMER]; });
  const result = await service.processInbound(
    inbound("pho_msg_direct_vet", FARMER, "please tell the vet"),
  );
  assert.equal(result.handled, true);
  assert.match(result.reply ?? "", /told your vet/i);
  assert.equal(store.snapshot.mockOutbox.filter((item) => item.kind === "vet-handoff").length, 1);
});

test("an unclear vet question asks for permission and a natural no closes it", async (t) => {
  const tmp = tempState();
  t.after(() => fs.rmSync(tmp.dir, { recursive: true, force: true }));
  const { service, store } = createRuntime(config(tmp.file), {
    fetch: (async () => { throw new Error("Photon should not run in mock mode"); }) as typeof fetch,
    deepseekFetch: (async () => jsonResponse({ choices: [{ message: { content: "Okay." } }] })) as typeof fetch,
    clock: () => NOW,
  });
  await service.sendAlert(demoAlert("B2"), [FARMER]);
  store.update((state) => { delete state.pendingVetConsent[FARMER]; });
  const question = await service.processInbound(inbound("pho_msg_vet_question", FARMER, "Do I need a vet?"));
  assert.match(question.reply ?? "", /Do you want me to tell your vet/);
  assert.equal(store.snapshot.mockOutbox.filter((item) => item.kind === "vet-handoff").length, 0);
  assert.ok(store.snapshot.pendingVetConsent[FARMER]);

  const decline = await service.processInbound(inbound("pho_msg_vet_no", FARMER, "no thanks"));
  assert.match(decline.reply ?? "", /won't contact your vet/);
  assert.equal(store.snapshot.pendingVetConsent[FARMER], undefined);
  const laterYes = await service.processInbound(inbound("pho_msg_later_yes", FARMER, "yes"));
  assert.equal(laterYes.handled, true);
  assert.equal(store.snapshot.mockOutbox.filter((item) => item.kind === "vet-handoff").length, 0);
});

test("the farmer can naturally stop an active vet chat", async (t) => {
  const tmp = tempState();
  t.after(() => fs.rmSync(tmp.dir, { recursive: true, force: true }));
  const { service, store } = createRuntime(config(tmp.file), {
    fetch: (async () => { throw new Error("Photon should not run in mock mode"); }) as typeof fetch,
    deepseekFetch: (async () => { throw new Error("LLM should not decide permission"); }) as typeof fetch,
    clock: () => NOW,
  });
  await service.sendAlert(demoAlert("B2"), [FARMER]);
  await service.processInbound(inbound("pho_msg_start_vet", FARMER, "go ahead"));
  const stopped = await service.processInbound(
    inbound("pho_msg_stop_vet", FARMER, "stop talking to the vet"),
  );
  assert.match(stopped.reply ?? "", /stopped sending new messages/);
  assert.equal(store.snapshot.vetHandoffs[FARMER].status, "cancelled");
  assert.equal(store.snapshot.activeFarmerByVet[VET], undefined);
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

  await service.processInbound(inbound("pho_msg_vet_approve2", FARMER, "sure"));
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

test("wording check allows uncertain illness guesses but rejects certainty and orders", () => {
  assert.equal(isSafeWording("We think Pen 6 may have salmonella."), true);
  assert.equal(isSafeWording("Pen 6 definitely has salmonella."), false);
  assert.equal(isSafeWording("Cull the birds now."), false);
  assert.equal(isSafeWording("The model confidence shows an anomaly."), false);
});

test("old state files load with no pending vet question", (t) => {
  const tmp = tempState();
  t.after(() => fs.rmSync(tmp.dir, { recursive: true, force: true }));
  fs.writeFileSync(tmp.file, JSON.stringify({ processedInbound: [], latestAlerts: {}, turns: {} }));
  const store = new MessagingStore(tmp.file);
  assert.deepEqual(store.snapshot.pendingVetConsent, {});
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
  assert.match(requests[0].url, /platform=imessage/);
  assert.equal(requests[0].init?.headers && (requests[0].init.headers as Record<string, string>).Authorization, "Bearer test-only");
});

test("Photon client sends imessage payloads for users, spaces, and messages", async () => {
  const requests: { url: string; init?: RequestInit }[] = [];
  const client = new PhotonClient({
    baseUrl: "https://api.photon.codes/v1",
    apiKey: "test-only",
    projectId: "pho_prj_test",
    timeoutMs: 1_000,
    fetch: (async (url: string | URL | Request, init?: RequestInit) => {
      requests.push({ url: String(url), init });
      const target = String(url);
      if (target.includes("/users")) {
        return jsonResponse({ id: "pho_usr_human1", handle: FARMER, platform: "imessage" });
      }
      if (target.includes("/spaces")) {
        return jsonResponse({
          id: "pho_spc_out",
          platform: "imessage",
          participantIds: [AGENT_USER_ID, "pho_usr_human1"],
        });
      }
      if (target.includes("/messages") && init?.method === "POST") {
        return jsonResponse({ id: "pho_msg_out" });
      }
      return jsonResponse({ items: [], nextPageToken: null });
    }) as typeof fetch,
  });

  const user = await client.createOrGetUser(FARMER);
  assert.equal(user.id, "pho_usr_human1");
  assert.equal(user.platform, "imessage");
  const userBody = JSON.parse(String(requests[0].init?.body)) as { platform: string; handle: string };
  assert.equal(userBody.platform, "imessage");
  assert.equal(userBody.handle, FARMER);

  const space = await client.createOrGetSpace([AGENT_USER_ID, user.id]);
  assert.equal(space.platform, "imessage");
  const spaceBody = JSON.parse(String(requests[1].init?.body)) as {
    platform: string;
    participantIds: string[];
  };
  assert.equal(spaceBody.platform, "imessage");
  assert.deepEqual(spaceBody.participantIds, [AGENT_USER_ID, user.id]);
  const spaceHeaders = requests[1].init?.headers as Record<string, string>;
  assert.match(spaceHeaders["Idempotency-Key"] ?? "", /^space:/);

  const sent = await client.sendTextMessage({
    spaceId: space.id,
    senderId: AGENT_USER_ID,
    text: "hi",
    idempotencyKey: "stable:key",
  });
  assert.equal(sent.id, "pho_msg_out");
  const sendBody = JSON.parse(String(requests[2].init?.body)) as { senderId: string; spaceId: string };
  assert.equal(sendBody.senderId, AGENT_USER_ID);
  assert.equal(sendBody.spaceId, space.id);
  const sendHeaders = requests[2].init?.headers as Record<string, string>;
  assert.equal(sendHeaders["Idempotency-Key"], "stable:key");

  await client.listReceivedMessages({ createdSince: NOW.toISOString() });
  assert.match(requests[3].url, /platform=imessage/);
});

test("live sendDirectText uses the configured agent user ID and never creates an agent user", async (t) => {
  const tmp = tempState();
  t.after(() => fs.rmSync(tmp.dir, { recursive: true, force: true }));
  const requests: { url: string; init?: RequestInit }[] = [];
  const photonFetch = async (url: string | URL | Request, init?: RequestInit) => {
    requests.push({ url: String(url), init });
    const target = String(url);
    if (target.includes("/users")) {
      const body = JSON.parse(String(init?.body)) as { handle: string };
      if (body.handle === AGENT) throw new Error("the agent user must not be created from a phone number");
      return jsonResponse({ id: "pho_usr_human1", handle: body.handle, platform: "imessage" });
    }
    if (target.includes("/spaces")) {
      return jsonResponse({
        id: "pho_spc_out",
        platform: "imessage",
        participantIds: [AGENT_USER_ID, "pho_usr_human1"],
      });
    }
    if (target.includes("/messages") && init?.method === "POST") {
      return jsonResponse({ id: "pho_msg_out" });
    }
    return jsonResponse({ items: [], nextPageToken: null });
  };
  const { service } = createRuntime(
    config(tmp.file, {
      mode: "live",
      photon: {
        baseUrl: "https://api.photon.codes/v1",
        apiKey: "test-only",
        projectId: "pho_prj_test",
        agentUserId: AGENT_USER_ID,
      },
    }),
    {
      fetch: photonFetch as typeof fetch,
      deepseekFetch: (async () => {
        throw new Error("DeepSeek must not run");
      }) as typeof fetch,
      clock: () => NOW,
    },
  );
  const alert = demoAlert("B2");
  const first = await service.sendAlert(alert, [FARMER]);
  assert.deepEqual(first.map((d) => d.status), ["accepted"]);
  const second = await service.sendAlert(alert, [FARMER]);
  assert.deepEqual(second.map((d) => d.status), ["accepted"]);

  const userCreates = requests.filter((r) => r.url.includes("/users"));
  assert.equal(userCreates.length, 2);
  for (const req of userCreates) {
    const body = JSON.parse(String(req.init?.body)) as { platform: string; handle: string };
    assert.equal(body.platform, "imessage");
    assert.equal(body.handle, FARMER);
  }

  const spaceReqs = requests.filter((r) => r.url.includes("/spaces"));
  assert.equal(spaceReqs.length, 2);
  for (const req of spaceReqs) {
    const body = JSON.parse(String(req.init?.body)) as { platform: string; participantIds: string[] };
    assert.equal(body.platform, "imessage");
    assert.deepEqual(body.participantIds, [AGENT_USER_ID, "pho_usr_human1"]);
  }

  const sendReqs = requests.filter((r) => r.url.includes("/messages") && r.init?.method === "POST");
  assert.equal(sendReqs.length, 2);
  const keys: string[] = [];
  for (const req of sendReqs) {
    const body = JSON.parse(String(req.init?.body)) as { senderId: string };
    assert.equal(body.senderId, AGENT_USER_ID);
    keys.push((req.init?.headers as Record<string, string>)["Idempotency-Key"] ?? "");
  }
  assert.match(keys[0], /^alert:/);
  assert.equal(keys[0], keys[1]);
});

test("live inbound iMessage replies omit parentMessageId and reuse the inbound space", async (t) => {
  const tmp = tempState();
  t.after(() => fs.rmSync(tmp.dir, { recursive: true, force: true }));
  const requests: { url: string; init?: RequestInit }[] = [];
  const photonFetch = async (url: string | URL | Request, init?: RequestInit) => {
    requests.push({ url: String(url), init });
    const target = String(url);
    if (target.includes("/messages") && init?.method === "POST") {
      return jsonResponse({ id: "pho_msg_out" });
    }
    return jsonResponse({ items: [], nextPageToken: null });
  };
  const { service } = createRuntime(
    config(tmp.file, {
      mode: "live",
      photon: {
        baseUrl: "https://api.photon.codes/v1",
        apiKey: "test-only",
        projectId: "pho_prj_test",
        agentUserId: AGENT_USER_ID,
      },
    }),
    {
      fetch: photonFetch as typeof fetch,
      deepseekFetch: (async () =>
        jsonResponse({
          choices: [{ message: { content: "We saw three unusual droppings. Please check the birds." } }],
        })) as typeof fetch,
      clock: () => NOW,
    },
  );
  const message = inbound("pho_msg_reply_no_parent", FARMER, "What is this?");
  message.space = { id: "pho_spc_farmer_direct", platform: "imessage", kind: "direct" };
  const result = await service.processInbound(message);
  assert.equal(result.handled, true);
  const sendReqs = requests.filter((r) => r.url.includes("/messages") && r.init?.method === "POST");
  assert.equal(sendReqs.length, 1);
  const body = JSON.parse(String(sendReqs[0].init?.body)) as Record<string, unknown>;
  assert.equal(body.spaceId, "pho_spc_farmer_direct");
  assert.equal(body.senderId, AGENT_USER_ID);
  assert.ok(!("parentMessageId" in body));
  const headers = sendReqs[0].init?.headers as Record<string, string>;
  const replyKey = `reply:${createHash("sha256").update(message.id, "utf8").digest("hex")}`;
  assert.equal(headers["Idempotency-Key"], replyKey);
});

test("inbound rejects sms platform and messages received by a different agent user", async (t) => {
  const tmp = tempState();
  t.after(() => fs.rmSync(tmp.dir, { recursive: true, force: true }));
  let llmCalls = 0;
  const { service } = createRuntime(config(tmp.file), {
    fetch: (async () => {
      throw new Error("Photon should not run in mock mode");
    }) as typeof fetch,
    deepseekFetch: (async () => {
      llmCalls += 1;
      throw new Error("LLM must not run for filtered messages");
    }) as typeof fetch,
    clock: () => NOW,
  });

  const smsPlatform = inbound("pho_msg_sms_platform", FARMER, "hi");
  smsPlatform.platform = "sms";
  assert.deepEqual(await service.processInbound(smsPlatform), {
    handled: false,
    reason: "not-received-imessage",
  });

  const wrongAgent = inbound("pho_msg_wrong_agent", FARMER, "hi");
  wrongAgent.receivedBy = { id: "pho_usr_other_agent", platform: "imessage", handle: AGENT, kind: "agent" };
  assert.deepEqual(await service.processInbound(wrongAgent), { handled: false, reason: "not-for-agent" });

  const smsRecipient = inbound("pho_msg_sms_recipient", FARMER, "hi");
  smsRecipient.receivedBy = { id: AGENT_USER_ID, platform: "sms", handle: AGENT, kind: "agent" };
  assert.deepEqual(await service.processInbound(smsRecipient), { handled: false, reason: "not-for-agent" });

  const notText = inbound("pho_msg_not_text", FARMER, "hi");
  notText.content = { type: "image" };
  assert.deepEqual(await service.processInbound(notText), { handled: false, reason: "not-plain-text" });
  assert.equal(llmCalls, 0);
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
