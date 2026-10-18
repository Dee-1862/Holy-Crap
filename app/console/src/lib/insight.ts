import { GROUPS, TYPES, type Group, type Specimen } from "./data";
import { penStats } from "./rules";
import { getSpecimens, isOnlinePen } from "./store";

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
  return penStats(getSpecimens().filter((s) => s.group === g.id));
}

// Groups ranked healthiest first.
export function ranked(): { group: Group; status: GroupStatus }[] {
  return GROUPS.filter((g) => isOnlinePen(g.id)).map((group) => ({ group, status: groupStatus(group) })).sort(
    (a, b) => (b.status.mean ?? -1) - (a.status.mean ?? -1),
  );
}

// What the person should do next for a specimen.
export function nextStep(s: Specimen): { level: Tone; head: string; note: string } {
  const name = groupName(s.group);
  const bad = getSpecimens().filter((x) => x.group === s.group && x.type !== "healthy" && x.minsAgo <= 15).length;
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

export const specimensOf = (groupId: string) => getSpecimens().filter((s) => s.group === groupId);

export const SUB_AXES: { key: keyof Specimen["sub"]; label: string }[] = [
  { key: "color", label: "Color" },
  { key: "consistency", label: "Consistency" },
  { key: "urates", label: "Urate cap" },
  { key: "blood", label: "Blood or mucus" },
  { key: "foam", label: "Foam" },
];

// Mean sub-scores (0 to 10) for one group, or for the whole barn when no id is given.
export function radarOf(groupId?: string): number[] {
  const list = groupId ? specimensOf(groupId) : getSpecimens();
  if (!list.length) return SUB_AXES.map(() => 0);
  return SUB_AXES.map(({ key }) => list.reduce((a, s) => a + s.sub[key], 0) / list.length);
}

// Barn index out of 100, the mean grade of the last 15 minutes scaled up.
export function barnIndex(): number {
  const all = getSpecimens();
  const recent = all.filter((s) => s.minsAgo <= 15);
  const list = recent.length ? recent : all;
  if (!list.length) return 0;
  return Math.round((list.reduce((a, s) => a + s.grade, 0) / list.length) * 10);
}

export const openAlerts = () => GROUPS.filter((g) => isOnlinePen(g.id) && groupStatus(g).level !== "good").length;

// Pens split by whether they need a look. Used for the dashboard widgets.
export function penLevels() {
  const r = ranked();
  return { healthy: r.filter((x) => x.status.level === "good"), look: r.filter((x) => x.status.level !== "good").reverse(), total: r.length };
}

export function summary() {
  const hot = ranked().filter((r) => r.status.level === "bad").map((r) => r.group.name);
  const all = getSpecimens();
  const abnormal = all.filter((s) => s.type !== "healthy").length;
  const mean = all.length ? (all.reduce((a, s) => a + s.grade, 0) / all.length).toFixed(1) : "0.0";
  const headline = hot.length ? `${hot.join(" and ")} ${hot.length > 1 ? "need" : "needs"} attention` : "All pens look calm";
  // One plain sentence under the headline. Names the worst group and what to do.
  const worst = ranked().filter((r) => r.status.level === "bad").map((r) => r.group)[0];
  const n = worst ? groupStatus(worst).bad : 0;
  const detail = worst
    ? `${worst.name} has ${n} abnormal specimens in the last 15 minutes. Check the birds on site and call the vet if it continues.`
    : "No pen has repeated abnormal specimens in the last 15 minutes.";
  return { hot, abnormal, mean, headline, detail, total: all.length };
}

// ----- plain language checks -----
// The five things the model looks at, in words a farmer would use. Scores are 0 to 10 where 10 is
// perfectly normal. 8 or more reads as normal, 5 to 7 as a bit off, under 5 as a problem.
export const CHECKS: { key: keyof Specimen["sub"]; label: string; words: [string, string, string] }[] = [
  { key: "color", label: "Color", words: ["Normal", "A bit off", "Unusual"] },
  { key: "consistency", label: "Firmness", words: ["Firm", "Soft", "Watery"] },
  { key: "urates", label: "White cap", words: ["Present", "Thin", "Missing"] },
  { key: "blood", label: "Blood or mucus", words: ["None seen", "Some", "Seen"] },
  { key: "foam", label: "Foam", words: ["None", "Some", "Foamy"] },
];
export const checkLevel = (score: number): 0 | 1 | 2 => (score >= 8 ? 0 : score >= 5 ? 1 : 2);

// "Mostly blood or mucus and firmness are off." or "All five checks look normal."
export function checksSentence(values: number[]): string {
  const off = CHECKS.map((c, i) => ({ label: c.label.toLowerCase(), v: values[i] })).filter((x) => checkLevel(x.v) > 0).sort((a, b) => a.v - b.v);
  if (!off.length) return "All five checks look normal.";
  const names = off.slice(0, 2).map((x) => x.label);
  return `${names.length > 1 ? `Mostly ${names[0]} and ${names[1]} are` : `Mostly ${names[0]} is`} off.`;
}

// How sure the model is, in words. The number stays available for people who want it.
export const sureness = (confPercent: number) => (confPercent >= 80 ? "Very sure" : confPercent >= 60 ? "Fairly sure" : "Not sure");
