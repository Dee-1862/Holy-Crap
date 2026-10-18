import { bridgeStatus, DIRECT, EDGE_URL } from "@/server/edge";

// Status of the QNX Pi edge pipeline (target/qnx/edge/uplink.py). Fetched on the server so the browser never needs
// a route to the Pi. A deployed console reads what the laptop bridge last pushed instead.
export const dynamic = "force-dynamic";

export async function GET() {
  if (DIRECT) {
    try {
      const r = await fetch(`${EDGE_URL}/status`, { cache: "no-store", signal: AbortSignal.timeout(2500) });
      return Response.json({ online: true, url: EDGE_URL, via: "direct", ...(await r.json()) });
    } catch { /* fall through to the bridge */ }
  }
  const b = await bridgeStatus();
  if (b) return Response.json({ online: true, url: "laptop bridge", via: "bridge", ...b.status });
  return Response.json({ online: false, url: DIRECT ? EDGE_URL : "laptop bridge", via: DIRECT ? "direct" : "bridge" });
}
