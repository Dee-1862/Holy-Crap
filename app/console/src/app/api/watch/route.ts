import { GROUPS, liveSpecimens, type TypeKey } from "@/lib/data";
import { penStats } from "@/lib/rules";
import { getState } from "@/server/store";

export const dynamic = "force-dynamic";

const KEYS: TypeKey[] = ["healthy", "coccidiosis", "salmonella", "ncd"];
const ST = { new: 0, checking: 1, normal: 2 } as const;

// Compact snapshot for the StopWatch. Short keys keep it small enough for the ESP32 to parse.
//   pens   id, name, birds, average grade (last hour), level 0 good 1 look 2 urgent, abnormal count
//   specs  id, pen, type key, grade, confidence, minutes ago, state 0 new 1 checking 2 normal,
//          class probabilities in percent (healthy, coccidiosis, salmonella, ncd),
//          five scores, photo focus point in percent, evidence lines
//   vet    most recent vet request, pen and minutes ago
export async function GET() {
  const st = await getState();
  const SPECIMENS = liveSpecimens(Math.floor(Date.now() / 60000));   // same demo clock as the web app
  const active = SPECIMENS.filter((s) => st.states[s.id] !== "normal");
  const pens = GROUPS.map((g) => {
    const p = penStats(active.filter((s) => s.group === g.id));
    return { id: g.id, name: g.name, n: g.n, mean: p.mean === null ? null : Math.round(p.mean * 10) / 10, lvl: p.level === "bad" ? 2 : p.level === "warn" ? 1 : 0, bad: p.bad };
  });
  const specs = SPECIMENS.map((s) => ({
    id: s.id, pen: s.group, k: s.type, grade: s.grade, conf: Math.round(s.probs[s.type] * 100), mins: s.minsAgo,
    st: ST[st.states[s.id] ?? "new"],
    p: KEYS.map((k) => Math.round(s.probs[k] * 100)),
    sub: [s.sub.color, s.sub.consistency, s.sub.urates, s.sub.blood, s.sub.foam],
    rg: [Math.round(s.region[0] * 100), Math.round(s.region[1] * 100)],
    why: s.why.slice(0, 3),
  }));
  const v = st.vet[0];
  return Response.json({
    pens, specs,
    vet: v ? { pen: v.pen, ago: Math.max(0, Math.round((Date.now() - v.ts) / 60000)) } : null,
  });
}
