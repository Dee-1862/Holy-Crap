import { getState } from "@/server/store";

export const dynamic = "force-dynamic";

// Everything the clients need to draw action state: which specimens are being checked or were
// marked normal, and the latest vet requests.
export async function GET() {
  const s = getState();
  return Response.json({ states: s.states, vet: s.vet.slice(0, 10) });
}
