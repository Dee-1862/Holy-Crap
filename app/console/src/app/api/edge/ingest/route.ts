import { ingest, latestIngest } from "@/server/edge";

// The Pi's cloud section (target/qnx/edge/cloudlink.py) posts batches here, so a deployed console (Vercel)
// sees the Pi without a route to it. Set EDGE_TOKEN to require the same token from the Pi.
export const dynamic = "force-dynamic";

export async function POST(req: Request) {
  const token = process.env.EDGE_TOKEN;
  if (token && req.headers.get("x-edge-token") !== token) return Response.json({ error: "bad token" }, { status: 401 });
  const body = (await req.json().catch(() => null)) as { device?: string; events?: unknown[] } | null;
  if (!body || !Array.isArray(body.events)) return Response.json({ error: "need events" }, { status: 400 });
  return Response.json(ingest(body.device ?? "pi", body.events));
}

export async function GET() {
  return Response.json(latestIngest());
}
