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

// Status over the last 15 minutes. Three abnormal specimens in that window is an alert.
export function groupStatus(g: Group): GroupStatus {
  const recent = SPECIMENS.filter((s) => s.group === g.id && s.minsAgo <= 15);
  const bad = recent.filter((s) => s.type !== "healthy").length;
  const mean = recent.length ? recent.reduce((a, s) => a + s.grade, 0) / recent.length : null;
  return { bad, mean, level: bad >= 3 ? "bad" : bad >= 1 ? "warn" : "good" };
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

export function summary() {
  const hot = ranked().filter((r) => r.status.level === "bad").map((r) => r.group.name);
  const abnormal = SPECIMENS.filter((s) => s.type !== "healthy").length;
  const mean = (SPECIMENS.reduce((a, s) => a + s.grade, 0) / SPECIMENS.length).toFixed(1);
  const headline = hot.length ? `${hot.join(" and ")} ${hot.length > 1 ? "need" : "needs"} attention` : "Everything looks calm";
  return { hot, abnormal, mean, headline, total: SPECIMENS.length };
}
