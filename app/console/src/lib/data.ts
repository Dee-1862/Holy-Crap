// Filler data for the UI prototypes. Synthetic, not real model output.
// Keep in step with app/watch/console/console.ino until the backend feeds every client.

export type TypeKey = "healthy" | "coccidiosis" | "salmonella" | "ncd";

export interface Group {
  id: string;
  name: string;
  n: number;
}

export interface SubScores {
  color: number;
  consistency: number;
  urates: number;
  blood: number;
  foam: number;
}

export interface Specimen {
  id: string;
  minsAgo: number;
  group: string;
  type: TypeKey;
  probs: Record<TypeKey, number>;
  grade: number;
  sub: SubScores;
  region: [number, number];
  why: string[];
}

export const TYPES: Record<TypeKey, { name: string; color: string }> = {
  healthy: { name: "Healthy", color: "#7a4a22" },
  coccidiosis: { name: "Coccidiosis", color: "#4a2418" },
  salmonella: { name: "Salmonella", color: "#c9b24a" },
  ncd: { name: "Newcastle disease", color: "#4fae4a" },
};

export const GROUPS: Group[] = [
  { id: "A1", name: "Pen A1", n: 24 },
  { id: "A2", name: "Pen A2", n: 24 },
  { id: "B1", name: "Pen B1", n: 18 },
  { id: "B2", name: "Pen B2", n: 18 },
  { id: "C1", name: "Cage row C1", n: 12 },
  { id: "C2", name: "Cage row C2", n: 12 },
];

export const SPECIMENS: Specimen[] = [
  {
    id: "E-0412", minsAgo: 2, group: "B2", type: "coccidiosis",
    probs: { healthy: 0.06, coccidiosis: 0.81, salmonella: 0.09, ncd: 0.04 }, grade: 2,
    sub: { color: 2, consistency: 3, urates: 4, blood: 1, foam: 8 }, region: [0.42, 0.55],
    why: ["Dark red-brown streaking across the lower third", "Wet, mucus-like outline instead of a firm shape", "White urate cap is thin or missing", "Pattern repeated in 3 events from this group in 10 min"],
  },
  {
    id: "E-0411", minsAgo: 6, group: "B2", type: "coccidiosis",
    probs: { healthy: 0.12, coccidiosis: 0.7, salmonella: 0.14, ncd: 0.04 }, grade: 3,
    sub: { color: 3, consistency: 4, urates: 5, blood: 2, foam: 8 }, region: [0.55, 0.48],
    why: ["Dark brown with red tint near the center", "Soft edges, moderate moisture"],
  },
  {
    id: "E-0410", minsAgo: 9, group: "A1", type: "healthy",
    probs: { healthy: 0.93, coccidiosis: 0.03, salmonella: 0.03, ncd: 0.01 }, grade: 9,
    sub: { color: 9, consistency: 9, urates: 9, blood: 10, foam: 10 }, region: [0.5, 0.42],
    why: ["Uniform brown body", "Firm shape with a distinct white urate cap", "No blood, foam or abnormal color"],
  },
  {
    id: "E-0413", minsAgo: 11, group: "B2", type: "coccidiosis",
    probs: { healthy: 0.1, coccidiosis: 0.66, salmonella: 0.18, ncd: 0.06 }, grade: 3,
    sub: { color: 3, consistency: 4, urates: 4, blood: 2, foam: 8 }, region: [0.47, 0.52],
    why: ["Dark brown with red streaks", "Loose, watery edge", "Third abnormal specimen from this group in 15 minutes"],
  },
  {
    id: "E-0409", minsAgo: 14, group: "C1", type: "salmonella",
    probs: { healthy: 0.22, coccidiosis: 0.08, salmonella: 0.6, ncd: 0.1 }, grade: 4,
    sub: { color: 4, consistency: 3, urates: 6, blood: 9, foam: 3 }, region: [0.46, 0.6],
    why: ["Yellowish tint over most of the area", "Foamy texture with small bubbles", "Watery spread beyond the normal footprint"],
  },
  {
    id: "E-0408", minsAgo: 21, group: "A2", type: "healthy",
    probs: { healthy: 0.88, coccidiosis: 0.05, salmonella: 0.05, ncd: 0.02 }, grade: 8,
    sub: { color: 8, consistency: 8, urates: 9, blood: 10, foam: 10 }, region: [0.48, 0.5],
    why: ["Brown body, slightly moist", "White cap present"],
  },
  {
    id: "E-0407", minsAgo: 33, group: "B1", type: "ncd",
    probs: { healthy: 0.2, coccidiosis: 0.05, salmonella: 0.15, ncd: 0.52 }, grade: 3,
    sub: { color: 2, consistency: 3, urates: 5, blood: 9, foam: 7 }, region: [0.52, 0.46],
    why: ["Green tint across the specimen", "Watery consistency", "Low confidence, a second look is advised"],
  },
  {
    id: "E-0406", minsAgo: 47, group: "C2", type: "healthy",
    probs: { healthy: 0.96, coccidiosis: 0.02, salmonella: 0.01, ncd: 0.01 }, grade: 10,
    sub: { color: 10, consistency: 10, urates: 9, blood: 10, foam: 10 }, region: [0.5, 0.5],
    why: ["Textbook example of a firm brown dropping with a white cap"],
  },
  {
    id: "E-0405", minsAgo: 62, group: "A1", type: "healthy",
    probs: { healthy: 0.9, coccidiosis: 0.04, salmonella: 0.04, ncd: 0.02 }, grade: 8,
    sub: { color: 8, consistency: 9, urates: 8, blood: 10, foam: 10 }, region: [0.44, 0.52],
    why: ["Brown, firm", "White cap slightly smeared"],
  },
];

// The demo stream runs on the clock. Every specimen ages in real time and comes round again as a new one
// every DEMO_PERIOD minutes, each time in a different pen, so the time windows, pen grades and alerts keep changing.
// clockMin is minutes since 1970, or 0 for the fixed layout above.
export const DEMO_PERIOD = 90;
export function liveSpecimens(clockMin: number): Specimen[] {
  return SPECIMENS.map((s) => {
    const t = s.minsAgo + clockMin;
    const lap = Math.floor(t / DEMO_PERIOD);
    const g = GROUPS.findIndex((x) => x.id === s.group);
    return { ...s, minsAgo: t % DEMO_PERIOD, group: GROUPS[(g + lap * 2) % GROUPS.length].id };
  }).sort((a, b) => a.minsAgo - b.minsAgo);
}
