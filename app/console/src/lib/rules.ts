import type { Specimen } from "./data";

export type Level = "good" | "warn" | "bad";

// One rule set for every client. The web app, the phone page and the watch endpoint all use it,
// so a pen is never red on one screen and yellow on another.
//   bad    three or more abnormal specimens in the last 15 minutes
//   warn   one or two abnormal, or an average grade under 5
//   good   everything else
export function penStats(list: Specimen[]): { bad: number; mean: number | null; level: Level } {
  const bad = list.filter((s) => s.minsAgo <= 15 && s.type !== "healthy").length;
  const hour = list.filter((s) => s.minsAgo <= 60);
  const pool = hour.length ? hour : list;
  const mean = pool.length ? pool.reduce((a, s) => a + s.grade, 0) / pool.length : null;
  const level: Level = bad >= 3 ? "bad" : bad >= 1 || (mean !== null && mean < 5) ? "warn" : "good";
  return { bad, mean, level };
}

// A termination (vet request) holds its pen for an hour, or until someone clears it. server/store.ts uses the same.
export const VET_ACTIVE_MS = 60 * 60_000;

// The pen's most critical specimen, the one the watch shows: still on alert before marked normal, a suspected
// disease before healthy, then the lowest grade, then the newest.
export function mostCritical(list: Specimen[], isNormal: (s: Specimen) => boolean): Specimen | undefined {
  return [...list].sort((a, b) =>
    Number(isNormal(a)) - Number(isNormal(b)) ||
    Number(a.type === "healthy") - Number(b.type === "healthy") ||
    a.grade - b.grade || a.minsAgo - b.minsAgo)[0];
}

