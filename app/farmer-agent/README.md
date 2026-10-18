# Holy-Crap farmer messaging agent

This is a standalone service for the farmer and veterinarian messaging workflow over Photon 2.0 shared iMessage. It does not run inside the simulation dashboard and does not add a dashboard API route.

The agent uses Photon 2.0 shared iMessage for two-way messaging and DeepSeek for short, plain-language replies. Mock mode is the default, so a fresh checkout cannot send a real message by accident.

## What it does

1. A pen alert is sent only to a farmer number in `FARMER_ALLOWED_NUMBERS`.
2. The farmer can reply with questions. The worker reads incoming Photon messages and answers with the latest alert context.
3. The farmer can send a JPEG or PNG. DeepSeek looks at the photo and answers in the same plain language. The next question can still refer to that photo.
4. The alert offers to tell the vet. The farmer can answer normally with messages such as `yes please`, `go ahead`, or `tell the vet`.
5. An unclear question about a vet gets a simple follow-up question. The agent does not contact the vet until the farmer clearly says to do it.
6. That veterinarian must also be in `VET_ALLOWED_NUMBERS`. Their replies are accepted only while an approved handoff is active.
7. The farmer can say `no thanks`, `don't contact the vet`, or `stop talking to the vet` at any time.

DeepSeek does not decide whether the farmer gave permission. A small, tested set of natural replies is checked in application code before any message to a veterinarian is created. A bare `yes` works only when the agent has just asked about contacting the vet.

## Safety boundary

Messages use short, everyday words. An alert states the exact facts the camera recorded: the number of droppings, the pen, the time window, the model's closest match, and its score as a whole number, such as `The model's closest match was salmonella, with an 81% score.` The single safety boundary is one plain sentence: `This is not a lab test.` The score is never described as a diagnosis, and stacked hedging is avoided.

Common fact questions are answered deterministically in application code, before DeepSeek runs: why the model picked the match, what was seen, the score, and when it happened. If there is no current alert, the farmer is told so directly.

The agent does not choose medicine or tell the farmer to isolate or kill birds. Those choices go to the vet. Replies are plain text and capped at 480 characters. If DeepSeek is unavailable or returns unsafe wording, the agent uses a deterministic response built from the recorded alert.

## Sending a photo with an alert

An alert can carry one photo as evidence. The photo is a local `.jpg` or `.png` file of at most 5 MB, uploaded to Photon as a multipart/related attachment. The agent sends the alert text, then a plain source label such as `Attached: Close-up from Pen 6.`, then the photo. Attachment metadata is intentionally omitted because iMessage rejects attachment captions.

With a real camera frame:

```sh
npm run simulate -- --pen=6 --image=/path/to/pen6-camera.jpg --image-label="Close-up from Pen 6."
```

With a demo or reference image, the label must say it is a sample, not a live camera frame:

```sh
npm run simulate -- --pen=6 --image=/path/to/demo-pen6.jpg --image-label="Sample image, not a live camera frame"
```

No image is attached unless `--image` is given. In mock mode the file is checked locally, but nothing is uploaded or sent; the planned send is recorded in `mockOutbox`. In live mode, retries reuse stable idempotency keys, so a retry does not duplicate the text or the photo.

A farmer can ask for the photo with plain messages such as `show me the photo`, `send the image`, or `can I see the poop`. If the alert has a photo, the agent sends a short reply and the same photo in the existing conversation with no DeepSeek call. If there is no photo, it says so directly.

Completed dashboard assessments now create this photo automatically. When the result needs review, the simulation service saves a JPEG frame from the strongest unusual-dropping moment and sends it with the alert. Clean results do not send an alert.

## Photos from the farmer

An allowlisted farmer can send a JPEG or PNG up to 5 MB. The worker downloads it from Photon, checks its type and size, and sends it to DeepSeek's `deepseek-flash` vision input. It keeps only the Photon attachment ID and basic file details in local state, not the photo bytes or base64 data. That lets a follow-up such as `What disease is this?` refer to the same photo for up to 24 hours, including after a worker restart.

The reply describes what is visible and compares it with the current alert. A photo can support a visual match, but it is never presented as a lab result and the agent does not give treatment, separation, or culling instructions.

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

The simulation queues one Pen B2 alert in `.data/messaging-state.json`. It does not call Photon or DeepSeek. Inspect `mockOutbox` to see the message that would have been sent. Use `--image` and `--image-label` to include a photo (see "Sending a photo with an alert").

Run the checks with:

```sh
npm test
npm run check
```

## Switch to live iMessage

Live mode needs all of the following:

- a Photon 2.0 project and project API key with `project:read`, `project:write`, `platforms:read`, and `platforms:write`;
- an existing agent Photon user that owns your shared iMessage assignment. Put that user's Photon user ID (`pho_usr_...`) in `PHOTON_AGENT_USER_ID`; the service never creates the agent user from a phone number;
- every farmer and vet recipient activated and assigned to the shared iMessage in Photon before live messaging. The service creates or gets only the human user by phone handle, then creates a space with the agent user first;
- at least one verified farmer in `FARMER_ALLOWED_NUMBERS`;
- a DeepSeek API key;
- an always-on Node process for the inbound worker.

Set `MESSAGING_MODE=live`, then start:

```sh
npm run worker
```

The worker polls received iMessage messages, processes them oldest first, checkpoints handled message IDs, and uses a one-minute overlap on later polls so an eventually consistent result is not silently skipped. Photon calls use stable idempotency keys, so retrying the same alert or reply does not create a second logical message.

iMessage assignment and billing are intentionally not part of application startup. Create the agent user and assign the shared iMessage in Photon first, then add the agent user ID and recipient numbers to the local secret configuration.

## Add the veterinarian test number

The checked-in `+1555...` values are placeholders. Replace them locally only after your teammate confirms the number and agrees to receive test messages:

```sh
VET_ALLOWED_NUMBERS=+1XXXXXXXXXX
DEFAULT_VET_NUMBER=+1XXXXXXXXXX
```

No veterinarian message is sent with the first alert. It is sent only after the farmer clearly agrees in their own words.

## Voice

`src/voice.ts` is a disabled adapter boundary. It reports whether provider settings exist but never places a call. A real voice integration still needs a chosen SIP or voice provider, credentials, and a reviewed implementation.
