// The barn layout and the droppings the cameras found. Droppings come from the camera analyses
// (app/live-feed/export_camera_droppings.py writes lib/camera-droppings.json), so the website and the watch
// show the same droppings, with the same pictures, as the camera view.
import PHOTOS from "./specimen-photos.json";

export type TypeKey = "healthy" | "coccidiosis" | "salmonella" | "ncd";
export interface Group {
  id: string;
  name: string;
}
export interface SubScores {
  color: number;
  consistency: number;
  urates: number;
  blood: number;
  foam: number;
}
// Where a dropping was seen: its camera, the moment in the feed, the crop the camera view shows and the detector's
// box on it, and for the A1 feed (known droppings added at known times) the original photo the reading comes from.
export interface CameraSighting {
  n: number;
  clip: string;
  at: number;
  crop: string;
  box: [number, number, number, number] | null;
  closeup: string | null;
  closeupBox: [number, number, number, number] | null;
  added: boolean;
}
export interface Specimen {
  id: string;
  minsAgo: number;
  group: string;
  type: TypeKey;
  probs: Record<TypeKey, number>;
  grade: number;
  sub?: SubScores;            // the five appearance checks, only where something measures them
  region: [number, number];
  why: string[];
  cam?: CameraSighting;
}
export const TYPES: Record<TypeKey, { name: string; color: string }> = {
  healthy: { name: "Healthy", color: "#7a4a22" },
  coccidiosis: { name: "Coccidiosis", color: "#4a2418" },
  salmonella: { name: "Salmonella", color: "#c9b24a" },
  ncd: { name: "Newcastle disease", color: "#4fae4a" },
};
export const GROUPS: Group[] = [
  { id: "A1", name: "Pen A1" },
  { id: "A2", name: "Pen A2" },
  { id: "B1", name: "Pen B1" },
  { id: "B2", name: "Pen B2" },
  { id: "C1", name: "Cage row C1" },
  { id: "C2", name: "Cage row C2" },
];

// Training photos the close-up model reads as each type, shown as reference examples.
export const referencePhotos = (t: TypeKey): string[] => (PHOTOS.refs as Record<string, string[]>)[t] ?? [];

// ----- the camera set -----
export interface CameraClip { id: string; pen: string; duration: number; added: boolean; times: number[]; birds: number[] }
interface CameraDropping {
  id: string; n: number; group: string; clip: string; at: number; type: TypeKey; probs: Record<TypeKey, number>; grade: number;
  crop: string; box: [number, number, number, number] | null; closeup: string | null; closeupBox: [number, number, number, number] | null; why: string[];
}
export interface CameraSet { clips: CameraClip[]; droppings: CameraDropping[] }

// Droppings as specimens. They are all in the camera loop playing now, so they all count as recent.
export function specimensFrom(set: CameraSet): Specimen[] {
  const added = new Set(set.clips.filter((c) => c.added).map((c) => c.id));
  return set.droppings.map((d) => ({
    id: d.id, minsAgo: 0, group: d.group, type: d.type, probs: d.probs, grade: d.grade, why: d.why,
    region: d.box ? [(d.box[0] + d.box[2]) / 2, (d.box[1] + d.box[3]) / 2] : [0.5, 0.5],
    cam: { n: d.n, clip: d.clip, at: d.at, crop: d.crop, box: d.box, closeup: d.closeup, closeupBox: d.closeupBox, added: added.has(d.clip) },
  }));
}

// Birds the camera sees at this moment: the behaviour models' count at the point the loop is playing.
export function birdsNow(clip: CameraClip | undefined, nowMs: number): number | null {
  if (!clip?.birds.length) return null;
  const t = (nowMs / 1000) % clip.duration;
  let i = 0;
  while (i + 1 < clip.times.length && clip.times[i + 1] <= t) i++;
  return clip.birds[i] ?? null;
}
