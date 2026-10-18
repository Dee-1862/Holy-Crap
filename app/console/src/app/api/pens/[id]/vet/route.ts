import { clearVet, knownPen, requestVet } from "@/server/store";

export const dynamic = "force-dynamic";

export async function POST(req: Request, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  if (!knownPen(id)) return Response.json({ error: "Unknown pen" }, { status: 404 });
  let specimenId: string | undefined;
  try {
    const body = (await req.json()) as { specimenId?: unknown };
    if (typeof body.specimenId === "string" && body.specimenId.length < 20) specimenId = body.specimenId;
  } catch { /* no body is fine */ }
  const { call, duplicate, state } = await requestVet(id, specimenId);
  return Response.json({ ok: true, duplicate, call, states: state.states, vet: state.vet.slice(0, 10) });
}

// Clear the pen's termination (the vet came, or it was a mistake).
export async function DELETE(_req: Request, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  if (!knownPen(id)) return Response.json({ error: "Unknown pen" }, { status: 404 });
  const state = await clearVet(id);
  return Response.json({ ok: true, states: state.states, vet: state.vet.slice(0, 10) });
}
