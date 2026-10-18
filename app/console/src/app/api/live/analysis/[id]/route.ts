import fs from "node:fs";
import { analysisFile, demoUrl } from "@/server/media";

export const dynamic = "force-dynamic";

export async function GET(req: Request, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  const demo = demoUrl("analysis", id);
  if (demo) return Response.redirect(new URL(demo, req.url), 307);
  const file = analysisFile(id);
  if (!file || !fs.existsSync(file)) return Response.json({ error: "No analysis for that clip" }, { status: 404 });
  return new Response(fs.readFileSync(file), { headers: { "content-type": "application/json", "cache-control": "no-store" } });
}
