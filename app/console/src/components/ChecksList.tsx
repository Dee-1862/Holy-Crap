import { CHECKS, checkLevel, checksSentence } from "@/lib/insight";

const DOT = ["var(--good)", "var(--warn)", "var(--bad)"] as const;

// The five checks as plain words, each with a colored dot. Replaces the radar chart.
// values are scores from 0 to 10 in the order of CHECKS.
export default function ChecksList({ values, title = "What we checked" }: { values: number[]; title?: string }) {
  return (
    <section aria-label={title}>
      <h3 className="eyebrow list-h" style={{ margin: 0, padding: "6px 4px 8px" }}>{title}</h3>
      <div className="list on-glass">
        {CHECKS.map((c, i) => {
          const lv = checkLevel(values[i]);
          return (
            <div key={c.key} className="row check">
              <span className="headline">{c.label}</span>
              <span className="verdictword" style={{ color: lv ? DOT[lv] : "var(--label-2)" }}>
                {c.words[lv]}
              </span>
              <i className="cdot" style={{ background: DOT[lv] }} />
            </div>
          );
        })}
      </div>
      <p className="ro-weak">{checksSentence(values)}</p>
    </section>
  );
}
