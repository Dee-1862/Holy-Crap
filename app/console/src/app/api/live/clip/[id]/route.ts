import fs from "node:fs";
import { Readable } from "node:stream";
import { clipFile, demoUrl } from "@/server/media";

export const dynamic = "force-dynamic";

// Serves a clip with HTTP range support, which the browser needs to start playing quickly and to loop.
export async function GET(req: Request, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  const demo = demoUrl("clips", id);
  if (demo) return Response.redirect(new URL(demo, req.url), 307);     // static file, served with ranges by the host
  const file = clipFile(id);
  if (!file || !fs.existsSync(file)) return Response.json({ error: "Unknown clip" }, { status: 404 });

  const size = fs.statSync(file).size;
  const range = /^bytes=(\d*)-(\d*)$/.exec(req.headers.get("range") ?? "");
  const base = { "content-type": "video/mp4", "accept-ranges": "bytes", "cache-control": "no-store" };

  if (!range) {
    return new Response(Readable.toWeb(fs.createReadStream(file)) as ReadableStream, { headers: { ...base, "content-length": String(size) } });
  }
  const start = range[1] ? Number(range[1]) : Math.max(0, size - Number(range[2]));
  const end = range[1] && range[2] ? Math.min(Number(range[2]), size - 1) : size - 1;
  if (start >= size || start > end) return new Response(null, { status: 416, headers: { "content-range": `bytes */${size}` } });
  return new Response(Readable.toWeb(fs.createReadStream(file, { start, end })) as ReadableStream, {
    status: 206,
    headers: { ...base, "content-range": `bytes ${start}-${end}/${size}`, "content-length": String(end - start + 1) },
  });
}
