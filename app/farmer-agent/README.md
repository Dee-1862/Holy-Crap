# Holy-Crap farmer messaging agent

This is a standalone service for the farmer and veterinarian SMS workflow. It does not run inside the simulation dashboard and does not add a dashboard API route.

The agent uses Photon 2.0 Beta for two-way SMS and DeepSeek for short, plain-language replies. Mock mode is the default, so a fresh checkout cannot send a real message by accident.

## What it does

1. A pen alert is sent only to a farmer number in `FARMER_ALLOWED_NUMBERS`.
2. The farmer can reply with questions. The worker reads incoming Photon messages and answers with the latest alert context.
3. Mentioning a vet only returns a consent prompt. It does not contact anyone.
4. The farmer must reply exactly `APPROVE VET` before the agent shares the current camera observations with `DEFAULT_VET_NUMBER`.
5. That veterinarian must also be in `VET_ALLOWED_NUMBERS`. Their replies are accepted only while an approved handoff is active.
6. The farmer can reply `CANCEL VET` to close the handoff. A later handoff requires a new approval.

The LLM never decides whether consent exists. The exact command check happens in application code before any veterinarian message is created.

## Safety boundary

Messages describe camera observations, persistence, confidence, data freshness, and sensor health. They do not diagnose a disease, identify a pathogen, prescribe treatment, or recommend isolation or culling. A veterinarian and, when needed, laboratory testing make those determinations.

Replies are plain text and capped at 480 characters. If DeepSeek is unavailable or returns unsafe wording, the agent uses a deterministic response built from the recorded alert.

## Run it in mock mode

```sh
cd app/farmer-agent
npm install
cp .env.example .env.local
set -a
source .env.local
set +a
npm run simulate
```

The simulation queues one Pen B2 alert in `.data/messaging-state.json`. It does not call Photon or DeepSeek. Inspect `mockOutbox` to see the message that would have been sent.

Run the checks with:

```sh
npm test
npm run check
```

## Switch to live SMS

Live mode needs all of the following:

- a Photon 2.0 Beta project and project API key with `project:read`, `project:write`, `platforms:read`, and `platforms:write`;
- one SMS-capable Photon number, including an active payment method and whatever messaging registration Photon requires;
- that number in `PHOTON_AGENT_PHONE`;
- at least one verified farmer in `FARMER_ALLOWED_NUMBERS`;
- a DeepSeek API key;
- an always-on Node process for the inbound worker.

Set `MESSAGING_MODE=live`, then start:

```sh
npm run worker
```

The worker polls received SMS messages, processes them oldest first, checkpoints handled message IDs, and uses a one-minute overlap on later polls so an eventually consistent result is not silently skipped. Photon calls use stable idempotency keys, so retrying the same alert or reply does not create a second logical message.

Number purchase and billing are intentionally not part of application startup. Provision the number in Photon first, then add the assigned number to the local secret configuration.

## Add the veterinarian test number

The checked-in `+1555...` values are placeholders. Replace them locally only after your teammate confirms the number and agrees to receive test messages:

```sh
VET_ALLOWED_NUMBERS=+1XXXXXXXXXX
DEFAULT_VET_NUMBER=+1XXXXXXXXXX
```

No veterinarian message is sent during the initial alert or ordinary farmer conversation. The first one is created only after the farmer's exact `APPROVE VET` reply.

## Voice

`src/voice.ts` is a disabled adapter boundary. It reports whether provider settings exist but never places a call. A real voice integration still needs a chosen SIP or voice provider, credentials, and a reviewed implementation.
