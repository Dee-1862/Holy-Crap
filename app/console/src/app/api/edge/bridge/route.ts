import { bridgePush } from "@/server/edge";

// The laptop bridge (scripts/edge_bridge.py) posts the Pi's status here about once a second and gets back any
// Crash presses made on this site. Set EDGE_TOKEN on the site and on the laptop to keep others out.
export const dynamic = "force-dynamic";

export async function POST(req: Request) {
  const token = process.env.EDGE_TOKEN;
  if (token && req.headers.get("x-edge-token") !== token) return Response.json({ error: "bad token" }, { status: 401 });
  const body = (await req.json().catch(() => null)) as { status?: unknown } | null;
  if (!body?.status) return Response.json({ error: "need status" }, { status: 400 });
  return Response.json({ commands: await bridgePush(body.status) });
}
