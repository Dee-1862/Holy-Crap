import { getState, knownSpecimen, setSpecimenState, type SpecState } from "@/server/store";

export const dynamic = "force-dynamic";

const ACTIONS: Record<string, SpecState> = {
  check: "checking",   // "I'll check it"
  normal: "normal",    // "Looks normal", removes it from alerts
  reset: "new",
};

export async function POST(_req: Request, ctx: { params: Promise<{ id: string; action: string }> }) {
  const { id, action } = await ctx.params;
  if (!knownSpecimen(id)) return Response.json({ error: "Unknown specimen" }, { status: 404 });
  const st = ACTIONS[action];
  if (!st) return Response.json({ error: "Unknown action" }, { status: 400 });
  const s = setSpecimenState(id, st);
  return Response.json({ ok: true, states: s.states, vet: s.vet.slice(0, 10) });
}
