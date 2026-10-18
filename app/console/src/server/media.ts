import fs from "node:fs";
import path from "node:path";
import DEMO from "@/lib/demo-clips.json";

// Where the live feed keeps its clips. They are downloaded by app/live-feed/fetch_clips.py and are
// never committed to git. On a host without them (for example a fresh Vercel deploy) the list is empty.
export const MEDIA = process.env.HC_MEDIA_DIR || path.join(/* turbopackIgnore: true */ process.cwd(), "media");

export interface ClipInfo {
  id: string;
  pen: string;
  title: string;
  view: string;
  source: string;
  sourceUrl: string;
  license: string;
  bytes: number;
}

const clipPath = (id: string) => path.join(MEDIA, "clips", `${id}.mp4`);
const analysisPath = (id: string) => path.join(MEDIA, "analysis", `${id}.json`);

function isUsableFile(file: string): boolean {
  try {
    const stat = fs.statSync(file);
    return stat.isFile() && stat.size > 0;
  } catch {
    return false;
  }
}

function isClipInfo(value: unknown): value is ClipInfo {
  if (typeof value !== "object" || value === null) return false;
  const clip = value as Record<string, unknown>;
  return typeof clip.id === "string" && /^[a-zA-Z0-9_-]+$/.test(clip.id)
    && typeof clip.pen === "string"
    && typeof clip.title === "string"
    && typeof clip.view === "string"
    && typeof clip.source === "string"
    && typeof clip.sourceUrl === "string"
    && typeof clip.license === "string"
    && typeof clip.bytes === "number";
}

// A small demo set ships in public/demo-media (app/live-feed/export_demo_media.py) for a deployed console,
// which has no media folder. The full local media wins whenever it is there.
export const DEMO_CLIPS = DEMO as ClipInfo[];

function localManifest(): ClipInfo[] | null {
  try {
    const parsed: unknown = JSON.parse(fs.readFileSync(path.join(MEDIA, "clips.json"), "utf8"));
    if (!Array.isArray(parsed)) return null;
    // A manifest records intended clips, but the UI should only call a camera online once
    // both artifacts it consumes are present. Downloads and analysis can finish separately.
    return parsed.filter((clip): clip is ClipInfo => isClipInfo(clip)
      && isUsableFile(clipPath(clip.id))
      && isUsableFile(analysisPath(clip.id)));
  } catch {
    return null;
  }
}

export function readManifest(): ClipInfo[] {
  return localManifest() ?? DEMO_CLIPS;
}

// Where the browser can fetch a demo file when there is no local copy, or null.
export function demoUrl(kind: "clips" | "analysis", id: string): string | null {
  if (localManifest() || !DEMO_CLIPS.some((c) => c.id === id)) return null;
  return `/demo-media/${kind}/${id}.${kind === "clips" ? "mp4" : "json"}`;
}

// Only ids that are in the manifest resolve to a file, so a request can never reach another path.
export function clipFile(id: string): string | null {
  return readManifest().some((c) => c.id === id) ? clipPath(id) : null;
}

export function analysisFile(id: string): string | null {
  return readManifest().some((c) => c.id === id) ? analysisPath(id) : null;
}
