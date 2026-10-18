import { EDGE_URL } from "@/server/edge";

// Kills one edge process on the Pi so the supervisor's restart can be watched. Demo only.
const PROCS = new Set(["camera", "spotter", "uplink", "model", "explain", "watch", "cloud"]);

export async function POST(req: Request) {
  const proc = new URL(req.url).searchParams.get("proc") ?? "";
  if (!PROCS.has(proc)) return Response.json({ error: "unknown process" }, { status: 400 });
  try {
    const r = await fetch(`${EDGE_URL}/crash?proc=${proc}`, { method: "POST", signal: AbortSignal.timeout(2500) });
    return Response.json(await r.json().catch(() => ({ killed: proc })));
  } catch {
    return Response.json({ killed: proc, note: "no answer, expected when the uplink kills itself" });
  }
}
