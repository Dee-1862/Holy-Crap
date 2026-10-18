import { readManifest } from "@/server/media";

export const dynamic = "force-dynamic";

export async function GET() {
  const clips = readManifest();
  return Response.json({
    clips,
    hint: clips.length ? null : "No clips installed. From the repo root run: python app/live-feed/fetch_clips.py and then python app/live-feed/analyze_clips.py",
  });
}
