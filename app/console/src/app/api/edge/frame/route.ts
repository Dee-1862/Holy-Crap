import { liveFrame, markWatching, storeFrame, type LiveFrame } from "@/server/edge";

// The newest picture from the Pi's own camera, pushed by its site section (target/qnx/edge/sitelink.py).
//   GET            the picture, null when the Pi has not sent one lately. ?watch=1 asks the Pi for pictures back to back.
//   POST           from the Pi. Answers whether someone is watching, so the Pi knows how fast to send.
export const dynamic = "force-dynamic";

export async function GET(req: Request) {
  const watch = new URL(req.url).searchParams.get("watch") === "1";
  const [frame] = await Promise.all([liveFrame(), watch ? markWatching() : null]);
  return Response.json({ frame }, { headers: { "cache-control": "no-store" } });
}

export async function POST(req: Request) {
  const token = process.env.EDGE_TOKEN;
  if (token && req.headers.get("x-edge-token") !== token) return Response.json({ error: "bad token" }, { status: 401 });
  const frame = (await req.json().catch(() => null)) as Omit<LiveFrame, "at"> | null;
  if (!frame?.jpeg) return Response.json({ error: "need jpeg" }, { status: 400 });
  return Response.json({ watching: await storeFrame(frame) });
}
