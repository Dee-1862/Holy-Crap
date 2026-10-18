import fs from "node:fs";
import path from "node:path";

// Where the live feed keeps its clips. They are downloaded by app/live-feed/fetch_clips.py and are
// never committed to git. On a host without them (for example a fresh Vercel deploy) the list is empty.
export const MEDIA = path.join(/* turbopackIgnore: true */ process.cwd(), "media");

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

export function readManifest(): ClipInfo[] {
  try {
    return JSON.parse(fs.readFileSync(path.join(MEDIA, "clips.json"), "utf8")) as ClipInfo[];
  } catch {
    return [];
  }
}

// Only ids that are in the manifest resolve to a file, so a request can never reach another path.
export function clipFile(id: string): string | null {
  return readManifest().some((c) => c.id === id) ? path.join(MEDIA, "clips", `${id}.mp4`) : null;
}

export function analysisFile(id: string): string | null {
  return readManifest().some((c) => c.id === id) ? path.join(MEDIA, "analysis", `${id}.json`) : null;
}
