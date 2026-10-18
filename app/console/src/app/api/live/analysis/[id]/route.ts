import fs from "node:fs";
import { analysisFile } from "@/server/media";

export const dynamic = "force-dynamic";

export async function GET(_req: Request, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  const file = analysisFile(id);
  if (!file || !fs.existsSync(file)) return Response.json({ error: "No analysis for that clip" }, { status: 404 });
  return new Response(fs.readFileSync(file), { headers: { "content-type": "application/json", "cache-control": "no-store" } });
}
