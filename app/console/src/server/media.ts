import fs from "node:fs";
import path from "node:path";

// Where the live feed keeps its clips. They are downloaded by app/live-feed/fetch_clips.py and are
// never committed to git. On a host without them (for example a fresh Vercel deploy) the list is empty.
export const MEDIA = path.join(process.cwd(), "media");

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

export function readManifest(): ClipInfo[] {
  try {
    const parsed: unknown = JSON.parse(fs.readFileSync(path.join(MEDIA, "clips.json"), "utf8"));
    if (!Array.isArray(parsed)) return [];
    // A manifest records intended clips, but the UI should only call a camera online once
    // both artifacts it consumes are present. Downloads and analysis can finish separately.
    return parsed.filter((clip): clip is ClipInfo => isClipInfo(clip)
      && isUsableFile(clipPath(clip.id))
      && isUsableFile(analysisPath(clip.id)));
  } catch {
    return [];
  }
}

// Only ids that are in the manifest resolve to a file, so a request can never reach another path.
export function clipFile(id: string): string | null {
  return readManifest().some((c) => c.id === id) ? clipPath(id) : null;
}

export function analysisFile(id: string): string | null {
  return readManifest().some((c) => c.id === id) ? analysisPath(id) : null;
}
