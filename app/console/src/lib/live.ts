// Shapes of the live feed files written by app/live-feed (clips.json and analysis/<id>.json).

export interface Clip {
  id: string; pen: string; title: string; view: string; source: string; sourceUrl: string; license: string; bytes: number; test?: boolean;
}

export type ClassKey = "cocci" | "healthy" | "ncd" | "salmo";

export interface Spot {
  t: number;
  box: [number, number, number, number];             // shares of the frame
  cls: ClassKey;
  score: number;
  crop: string;                                       // zoomed crop as a data URL
  cropBox: [number, number, number, number];         // where the box sits in the crop, shares of the crop
  sizePx: number;                                     // longest side in a 1280 wide frame
  darker: number;                                     // percent darker than the litter around it
  colourShift: number;
  vsBackground: number;                               // mean change from the empty floor image, 0 to 255
  seen: number;
  window: number;
  scores: Record<ClassKey, number>;
  truth?: {                                          // answer key on test clips
    cls: ClassKey; photo: string;
    closeup: { img: string; box: [number, number, number, number] | null; scores: Record<ClassKey, number> | null } | null;
  };
}

export interface Analysis {
  id: string; width: number; height: number; duration: number; times: number[];
  spots?: Spot[];
  behaviour?: { classes: string[]; times: number[]; shares: number[][]; birds: number[]; classified: number[] } | null;
  truth?: { t: number; box: [number, number, number, number]; cls: ClassKey; foundAt: number | null }[];
}

export const CLASS_NAME: Record<ClassKey, string> = {
  cocci: "Coccidiosis", healthy: "Healthy", ncd: "Newcastle disease", salmo: "Salmonella",
};

export function clock(s: number) {
  const m = Math.floor(s / 60), r = Math.floor(s % 60);
  return m >= 60 ? `${Math.floor(m / 60)}:${String(m % 60).padStart(2, "0")}:${String(r).padStart(2, "0")}` : `${m}:${String(r).padStart(2, "0")}`;
}
