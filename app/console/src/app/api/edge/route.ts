import { EDGE_URL } from "@/server/edge";

// Status of the QNX Pi edge pipeline (target/qnx/edge/uplink.py), fetched on the server so the browser
// never needs a route to the Pi.
export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const r = await fetch(`${EDGE_URL}/status`, { cache: "no-store", signal: AbortSignal.timeout(2500) });
    return Response.json({ online: true, url: EDGE_URL, ...(await r.json()) });
  } catch {
    return Response.json({ online: false, url: EDGE_URL });
  }
}
