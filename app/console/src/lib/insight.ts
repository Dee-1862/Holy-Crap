import { GROUPS, SPECIMENS, TYPES, type Group, type Specimen } from "./data";

export type Tone = "good" | "warn" | "bad";

export const pct = (x: number) => Math.round(x * 100);
export const tone = (grade: number): Tone => (grade >= 8 ? "good" : grade >= 5 ? "warn" : "bad");
export const ago = (mins: number) => `${mins} min ago`;
export const groupName = (id: string) => GROUPS.find((g) => g.id === id)?.name ?? id;
export const resultOf = (s: Specimen) => (s.type === "healthy" ? "Normal" : `Suspected ${TYPES[s.type].name}`);

export interface GroupStatus {
  bad: number;
  mean: number | null;
  level: Tone;
}

// Abnormal count uses the last 15 minutes (three of them is an alert). The grade is the mean over the
// last hour so a quiet pen still shows a number, and a low grade alone is enough to ask for a look.
export function groupStatus(g: Group): GroupStatus {
  const all = SPECIMENS.filter((s) => s.group === g.id);
  const bad = all.filter((s) => s.minsAgo <= 15 && s.type !== "healthy").length;
  const hour = all.filter((s) => s.minsAgo <= 60);
  const pool = hour.length ? hour : all;
  const mean = pool.length ? pool.reduce((a, s) => a + s.grade, 0) / pool.length : null;
  const level: Tone = bad >= 3 ? "bad" : bad >= 1 || (mean !== null && mean < 5) ? "warn" : "good";
  return { bad, mean, level };
}

// Groups ranked healthiest first.
export function ranked(): { group: Group; status: GroupStatus }[] {
  return GROUPS.map((group) => ({ group, status: groupStatus(group) })).sort(
    (a, b) => (b.status.mean ?? -1) - (a.status.mean ?? -1),
  );
}

// What the person should do next for a specimen.
export function nextStep(s: Specimen): { level: Tone; head: string; note: string } {
  const name = groupName(s.group);
  const bad = SPECIMENS.filter((x) => x.group === s.group && x.type !== "healthy" && x.minsAgo <= 15).length;
  if (s.type === "healthy") return { level: "good", head: "No action needed", note: `This specimen looks normal for ${name}.` };
  if (bad >= 3) return { level: "bad", head: `Inspect ${name} now`, note: `${bad} abnormal specimens in 15 minutes. Check the birds and call the vet if it holds up.` };
  return { level: "warn", head: `Keep watching ${name}`, note: "One or two abnormal specimens so far. Acknowledge, or mark a false alarm if it looks fine." };
}

export function sortedProbs(s: Specimen) {
  return (Object.keys(s.probs) as (keyof Specimen["probs"])[]).sort((a, b) => s.probs[b] - s.probs[a]);
}

export function topTwo(s: Specimen) {
  const [a, b] = sortedProbs(s);
  return `${TYPES[a].name} ${pct(s.probs[a])}%, then ${TYPES[b].name} ${pct(s.probs[b])}%`;
}

export function uncertainty(s: Specimen) {
  const [a, b] = sortedProbs(s);
  const margin = s.probs[a] - s.probs[b];
  const text = margin < 0.25 ? "High uncertainty, a person should review." : margin < 0.5 ? "Moderate uncertainty." : "Low uncertainty.";
  return { text, margin };
}

export const specimensOf = (groupId: string) => SPECIMENS.filter((s) => s.group === groupId);

export const SUB_AXES: { key: keyof Specimen["sub"]; label: string }[] = [
  { key: "color", label: "Color" },
  { key: "consistency", label: "Consistency" },
  { key: "urates", label: "Urate cap" },
  { key: "blood", label: "Blood or mucus" },
  { key: "foam", label: "Foam" },
];

// Mean sub-scores (0 to 10) for one group, or for the whole barn when no id is given.
export function radarOf(groupId?: string): number[] {
  const list = groupId ? specimensOf(groupId) : SPECIMENS;
  if (!list.length) return SUB_AXES.map(() => 0);
  return SUB_AXES.map(({ key }) => list.reduce((a, s) => a + s.sub[key], 0) / list.length);
}

// Barn index out of 100, the mean grade of the last 15 minutes scaled up.
export function barnIndex(): number {
  const recent = SPECIMENS.filter((s) => s.minsAgo <= 15);
  const list = recent.length ? recent : SPECIMENS;
  return Math.round((list.reduce((a, s) => a + s.grade, 0) / list.length) * 10);
}

export const openAlerts = () => GROUPS.filter((g) => groupStatus(g).level !== "good").length;

export function summary() {
  const hot = ranked().filter((r) => r.status.level === "bad").map((r) => r.group.name);
  const abnormal = SPECIMENS.filter((s) => s.type !== "healthy").length;
  const mean = (SPECIMENS.reduce((a, s) => a + s.grade, 0) / SPECIMENS.length).toFixed(1);
  const headline = hot.length ? `${hot.join(" and ")} ${hot.length > 1 ? "need" : "needs"} attention` : "All pens look calm";
  // One plain sentence under the headline. Names the worst group and what to do.
  const worst = ranked().filter((r) => r.status.level === "bad").map((r) => r.group)[0];
  const n = worst ? groupStatus(worst).bad : 0;
  const detail = worst
    ? `${worst.name} has ${n} abnormal specimens in the last 15 minutes. Check the birds on site and call the vet if it continues.`
    : "No pen has repeated abnormal specimens in the last 15 minutes.";
  return { hot, abnormal, mean, headline, detail, total: SPECIMENS.length };
}
