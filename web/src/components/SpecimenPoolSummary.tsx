import type { ClipAssessment, DemoSpecimenClass, FecesCandidate, ProxySpecimenPoolSummary, ProxySpecimenReference } from "../types";

const DEMO_CLASS_ORDER: readonly DemoSpecimenClass[] = ["cocci", "healthy", "ncd", "salmo", "unknown_abnormal"];

const DEMO_CLASS_LABELS: Record<DemoSpecimenClass, string> = {
  cocci: "Coccidiosis",
  healthy: "Healthy",
  ncd: "Newcastle disease",
  salmo: "Salmonella",
  unknown_abnormal: "Unknown abnormal",
};

interface SpecimenPoolSummaryProps {
  summary: ProxySpecimenPoolSummary | null;
  assessment: ClipAssessment | null;
}

interface AssessmentSampleStats {
  candidateCount: number;
  proxyUses: number;
  uniqueProxyIds: number;
  datasetCounts: Array<{ dataset: string; count: number }>;
  classCounts: Partial<Record<DemoSpecimenClass, number>>;
}

function proxyFor(candidate: FecesCandidate): ProxySpecimenReference | null {
  return candidate.proxy_specimen ?? candidate.proxy ?? candidate.proxy_crop ?? null;
}

function proxyId(proxy: ProxySpecimenReference): string {
  return proxy.id ?? proxy.asset_id ?? proxy.sample_id ?? "";
}

function deriveSampleStats(assessment: ClipAssessment): AssessmentSampleStats | null {
  const candidates = assessment.summary.feces.candidates;
  if (!candidates.length) return null;
  const ids = new Set<string>();
  const datasets = new Map<string, number>();
  const classCounts: Partial<Record<DemoSpecimenClass, number>> = {};
  let proxyUses = 0;
  for (const candidate of candidates) {
    const proxy = proxyFor(candidate);
    if (!proxy) continue;
    proxyUses += 1;
    const id = proxyId(proxy);
    if (id) ids.add(id);
    const dataset = proxy.source_dataset ?? proxy.source;
    if (dataset && dataset.trim()) datasets.set(dataset, (datasets.get(dataset) ?? 0) + 1);
    const demoClass = proxy.expected_demo_class;
    if (demoClass) classCounts[demoClass] = (classCounts[demoClass] ?? 0) + 1;
  }
  return {
    candidateCount: candidates.length,
    proxyUses,
    uniqueProxyIds: ids.size,
    datasetCounts: [...datasets.entries()].map(([dataset, count]) => ({ dataset, count })).sort((a, b) => a.dataset.localeCompare(b.dataset)),
    classCounts,
  };
}

function classEntries(counts: Partial<Record<DemoSpecimenClass, number>>): Array<{ label: string; count: number }> {
  return DEMO_CLASS_ORDER
    .filter((demoClass) => (counts[demoClass] ?? 0) > 0)
    .map((demoClass) => ({ label: DEMO_CLASS_LABELS[demoClass], count: counts[demoClass] ?? 0 }));
}

function ClassBreakdown({ counts }: { counts: Partial<Record<DemoSpecimenClass, number>> }) {
  const entries = classEntries(counts);
  if (!entries.length) return <p className="pool-note">No expected demo classes reported.</p>;
  const total = entries.reduce((sum, entry) => sum + entry.count, 0);
  return (
    <div className="distribution-list pool-class-list">
      {entries.map((entry) => (
        <div className="distribution-row" key={entry.label}>
          <span>{entry.label}</span>
          <div><i style={{ width: `${total > 0 ? (entry.count / total) * 100 : 0}%` }} /></div>
          <strong>{entry.count}</strong>
        </div>
      ))}
    </div>
  );
}

function DatasetList({ datasets }: { datasets: Array<{ dataset: string; count: number }> }) {
  if (!datasets.length) return <p className="pool-note">No source datasets reported.</p>;
  return (
    <p className="pool-dataset-list">
      {datasets.map((entry) => (
        <span className="pool-dataset" key={entry.dataset}><span>{entry.dataset}</span><strong>{entry.count}</strong></span>
      ))}
    </p>
  );
}

function PoolView({ summary }: { summary: ProxySpecimenPoolSummary }) {
  const selectableTotal = summary.selectable_total ?? summary.total;
  const selectableClasses = summary.selectable_by_expected_class ?? summary.by_expected_class;
  return (
    <section className="pool-summary" aria-labelledby="pool-summary-title">
      <div className="subheading">
        <div><span className="eyebrow">Evidence context</span><h3 id="pool-summary-title">Proxy specimen pool</h3></div>
        <span className="pool-badge pool-badge--pool">INDEXED POOL</span>
      </div>
      <dl className="pool-stat-grid">
        <div><dt>Selectable photos</dt><dd>{selectableTotal}</dd></div>
        <div><dt>Indexed rows</dt><dd>{summary.total}</dd></div>
        <div><dt>Local images</dt><dd>{summary.bytes_present}</dd></div>
        <div><dt>Verified this session</dt><dd>{summary.verified_cached}</dd></div>
      </dl>
      <p className="pool-section-label">Source datasets</p>
      <DatasetList datasets={summary.by_dataset} />
      <p className="pool-section-label">Selectable expected classes</p>
      <ClassBreakdown counts={selectableClasses} />
    </section>
  );
}

function SampleView({ stats }: { stats: AssessmentSampleStats }) {
  return (
    <section className="pool-summary" aria-labelledby="pool-summary-title">
      <div className="subheading">
        <div><span className="eyebrow">Evidence context</span><h3 id="pool-summary-title">Proxy specimen pool</h3></div>
        <span className="pool-badge pool-badge--sample">ASSESSMENT SAMPLE</span>
      </div>
      <dl className="pool-stat-grid">
        <div><dt>Candidate rows</dt><dd>{stats.candidateCount}</dd></div>
        <div><dt>Proxy uses</dt><dd>{stats.proxyUses}</dd></div>
        <div><dt>Unique specimens</dt><dd>{stats.uniqueProxyIds}</dd></div>
        <div><dt>Source datasets</dt><dd>{stats.datasetCounts.length}</dd></div>
      </dl>
      <p className="pool-section-label">Source datasets in this assessment</p>
      <DatasetList datasets={stats.datasetCounts} />
      <p className="pool-section-label">Expected demo classes</p>
      <ClassBreakdown counts={stats.classCounts} />
    </section>
  );
}

export function SpecimenPoolSummary({ summary, assessment }: SpecimenPoolSummaryProps) {
  if (summary) return <PoolView summary={summary} />;
  if (assessment) {
    const stats = deriveSampleStats(assessment);
    if (stats) return <SampleView stats={stats} />;
  }
  return null;
}
