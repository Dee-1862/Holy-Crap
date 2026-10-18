import { liveFrame } from "@/server/edge";

// The newest picture from the Pi's own camera, pushed by its site section. Null when the Pi has not sent one lately.
export const dynamic = "force-dynamic";

export async function GET() {
  return Response.json({ frame: await liveFrame() }, { headers: { "cache-control": "no-store" } });
}
