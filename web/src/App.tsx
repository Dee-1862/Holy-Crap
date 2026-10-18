import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { api } from "./api";
import { PenViewport } from "./components/PenViewport";
import { TimelineChart } from "./components/TimelineChart";
import type {
  CapabilityValue,
  ModelArtifact,
  RunMetrics,
  RunSummary,
  Scenario,
  Snapshot,
  SystemCapabilities,
  TimelinePoint,
} from "./types";

interface CapabilityDisplay {
  configured: boolean;
  detail: string;
}

function describeCapability(value: CapabilityValue | undefined): CapabilityDisplay {
  if (value === undefined || value === null) return { configured: false, detail: "Not configured" };
  if (typeof value === "boolean") return { configured: value, detail: value ? "Ready" : "Not configured" };
  if (typeof value === "string") {
    const configured = !/not.?configured|unavailable|disabled|missing/i.test(value);
    return { configured, detail: value.replaceAll("_", " ") };
  }
  if (typeof value === "number") return { configured: value > 0, detail: String(value) };
  if (Array.isArray(value)) return { configured: value.length > 0, detail: `${value.length} reported` };
  const record = value;
  const status = typeof record.status === "string" ? record.status.toLowerCase() : "";
  const configured = record.configured === true || record.available === true ||
    ["ready", "configured", "available"].includes(status);
  const detailValue = record.detail ?? record.status;
  return {
    configured,
    detail: typeof detailValue === "string" ? detailValue.replaceAll("_", " ") : configured ? "Ready" : "Not configured",
  };
}

function findCapability(capabilities: SystemCapabilities | null, needles: string[]): CapabilityDisplay {
  if (!capabilities) return { configured: false, detail: "Not reported" };
  const queue: Array<[string, unknown]> = Object.entries(capabilities);
  while (queue.length) {
    const [key, value] = queue.shift()!;
    const recordId = value && typeof value === "object" && !Array.isArray(value)
      ? String((value as Record<string, unknown>).id ?? "")
      : "";
    if (needles.some((needle) => key.toLowerCase().includes(needle) || recordId.toLowerCase().includes(needle))) {
      return describeCapability(value as CapabilityValue);
    }
    if (Array.isArray(value)) {
      value.forEach((item, index) => queue.push([`${key}.${index}`, item]));
    } else if (value && typeof value === "object") {
      queue.push(...Object.entries(value as Record<string, unknown>));
    }
  }
  return { configured: false, detail: "Not reported" };
}

function formatDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat(undefined, {
    month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
  }).format(date);
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function Metric({ label, value, hint, tone }: { label: string; value: string; hint: string; tone?: "good" | "alert" }) {
  return (
    <div className={`metric ${tone ? `metric--${tone}` : ""}`}>
      <span className="metric__label">{label}</span>
      <strong>{value}</strong>
      <small>{hint}</small>
    </div>
  );
}

function Metrics({ metrics }: { metrics?: RunMetrics | null }) {
  if (!metrics) return <p className="empty-copy">Metrics are not available for this run yet.</p>;
  const delay = metrics.detection_delay_s;
  return (
    <div className="metrics-grid">
      <Metric label="Detection delay" value={delay == null ? "Not observed" : `${delay.toFixed(1)} s`} hint="From first true signal" />
      <Metric label="False alerts" value={String(metrics.false_alerts ?? 0)} hint="Outside truth window" tone={(metrics.false_alerts ?? 0) === 0 ? "good" : "alert"} />
      <Metric label="Mean throughput" value={metrics.mean_fps == null ? "—" : `${metrics.mean_fps.toFixed(1)} FPS`} hint="11 FPS target" tone={(metrics.mean_fps ?? 0) >= 11 ? "good" : undefined} />
      <Metric label="P95 latency" value={metrics.p95_latency_ms == null ? "—" : `${metrics.p95_latency_ms.toFixed(0)} ms`} hint="End-to-end inference" />
      <Metric label="Dropped frames" value={String(metrics.dropped_frames ?? 0)} hint="During evaluation" tone={(metrics.dropped_frames ?? 0) > 0 ? "alert" : "good"} />
      <Metric label="Alert state" value={metrics.alert_triggered ? "Triggered" : "Clear"} hint="Run-level output" tone={metrics.alert_triggered ? "alert" : "good"} />
    </div>
  );
}

export default function App() {
  const [capabilities, setCapabilities] = useState<SystemCapabilities | null>(null);
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [models, setModels] = useState<ModelArtifact[]>([]);
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [scenarioId, setScenarioId] = useState("");
  const [modelId, setModelId] = useState("");
  const [executor, setExecutor] = useState("mock");
  const [activeRun, setActiveRun] = useState<RunSummary | null>(null);
  const [timeline, setTimeline] = useState<TimelinePoint[]>([]);
  const [snapshots, setSnapshots] = useState<Snapshot[]>([]);
  const [snapshotIndex, setSnapshotIndex] = useState(0);
  const [showTruth, setShowTruth] = useState(true);
  const [showPredictions, setShowPredictions] = useState(true);
  const [loading, setLoading] = useState(true);
  const [runPending, setRunPending] = useState(false);
  const [uploadPending, setUploadPending] = useState(false);
  const [error, setError] = useState("");
  const [uploadMessage, setUploadMessage] = useState("");

  const selectedScenario = scenarios.find((scenario) => scenario.id === scenarioId);
  const selectedModel = models.find((model) => model.id === modelId);
  const activeScenario = scenarios.find((scenario) => scenario.id === activeRun?.scenario_id);
  const currentSnapshot = snapshots[snapshotIndex];
  const selectedTime = currentSnapshot?.t_s ?? timeline[0]?.t_s ?? 0;

  const loadRun = useCallback(async (run: RunSummary) => {
    setActiveRun(run);
    setScenarioId(run.scenario_id);
    setModelId(run.model_id);
    setExecutor(run.executor);
    setTimeline([]);
    setSnapshots([]);
    setSnapshotIndex(0);
    setError("");
    try {
      const [nextTimeline, nextSnapshots] = await Promise.all([api.timeline(run.id), api.snapshots(run.id)]);
      setTimeline(nextTimeline);
      setSnapshots(nextSnapshots);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Could not load run data.");
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    Promise.all([api.capabilities(), api.scenarios(), api.models(), api.runs()])
      .then(([nextCapabilities, nextScenarios, nextModels, nextRuns]) => {
        if (cancelled) return;
        setCapabilities(nextCapabilities);
        setScenarios(nextScenarios);
        setModels(nextModels);
        setRuns(nextRuns);
        setScenarioId(nextScenarios[0]?.id ?? "");
        setModelId(nextModels[0]?.id ?? "");
        if (nextRuns.length) void loadRun(nextRuns[0]);
      })
      .catch((requestError: unknown) => {
        if (!cancelled) setError(requestError instanceof Error ? requestError.message : "Could not connect to the local API.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [loadRun]);

  const capabilityList = useMemo(() => [
    { label: "Local API", value: capabilities ? { configured: true, detail: "Connected" } : { configured: false, detail: loading ? "Connecting" : "Unavailable" } },
    { label: "Veri artifacts", value: findCapability(capabilities, ["veri"]) },
    { label: "QNX target", value: findCapability(capabilities, ["qnx"]) },
  ], [capabilities, loading]);

  function selectTime(time: number) {
    if (!snapshots.length) return;
    const nearest = snapshots.reduce((best, snapshot, index) =>
      Math.abs(snapshot.t_s - time) < Math.abs(snapshots[best].t_s - time) ? index : best, 0);
    setSnapshotIndex(nearest);
  }

  async function handleRun(event: FormEvent) {
    event.preventDefault();
    if (!scenarioId || !modelId) return;
    setRunPending(true);
    setError("");
    try {
      const created = await api.createRun({ scenario_id: scenarioId, model_id: modelId, executor });
      const nextRuns = await api.runs();
      setRuns(nextRuns);
      await loadRun(nextRuns.find((run) => run.id === created.id) ?? created);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "The run could not be started.");
    } finally {
      setRunPending(false);
    }
  }

  async function handleUpload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    const file = data.get("artifact");
    const name = String(data.get("name") ?? "").trim();
    const version = String(data.get("version") ?? "").trim();
    const source = String(data.get("source") ?? "").trim();
    if (!(file instanceof File) || !file.size || !name || !version) return;
    setUploadPending(true);
    setUploadMessage("");
    setError("");
    try {
      const uploaded = await api.uploadModel(file, name, version, source || undefined);
      const nextModels = await api.models();
      setModels(nextModels);
      setModelId(uploaded.id);
      setUploadMessage(`${uploaded.name} ${uploaded.version} is ready for local runs.`);
      form.reset();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "The model could not be uploaded.");
    } finally {
      setUploadPending(false);
    }
  }

  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="brand-lockup">
          <span className="brand-mark" aria-hidden="true">HC</span>
          <div>
            <h1>Holy-Crap</h1>
            <p>Simulation Lab</p>
          </div>
        </div>
        <div className="capabilities" aria-label="System capabilities">
          {capabilityList.map(({ label, value }) => (
            <span className={`capability ${value.configured ? "capability--ready" : "capability--off"}`} key={label} title={value.detail}>
              <i aria-hidden="true" /> {label} <small>{value.configured ? "ready" : "not configured"}</small>
            </span>
          ))}
        </div>
      </header>

      {error ? <div className="error-banner" role="alert"><strong>Lab request failed.</strong> {error}</div> : null}

      <main className="workspace">
        <aside className="experiment-rail panel" aria-label="Experiment controls">
          <div className="panel-heading">
            <div><span className="eyebrow">Experiment</span><h2>Configure run</h2></div>
            <span className="index-label">01</span>
          </div>
          {loading ? <p className="loading-copy" role="status">Loading lab configuration…</p> : (
            <form className="run-form" onSubmit={handleRun}>
              <label>Scenario
                <select value={scenarioId} onChange={(event) => setScenarioId(event.target.value)} disabled={!scenarios.length}>
                  {scenarios.map((scenario) => <option key={scenario.id} value={scenario.id}>{scenario.name}</option>)}
                </select>
              </label>
              <label>Model artifact
                <select value={modelId} onChange={(event) => setModelId(event.target.value)} disabled={!models.length}>
                  {models.map((model) => <option key={model.id} value={model.id}>{model.name} / {model.version}</option>)}
                </select>
              </label>
              <label>Executor
                <select value={executor} onChange={(event) => setExecutor(event.target.value)}>
                  <option value="mock">Local deterministic mock</option>
                  <option value="qnx">QNX Pi target</option>
                </select>
              </label>
              {selectedScenario ? (
                <div className="scenario-summary">
                  <p>{selectedScenario.description}</p>
                  <dl className="scenario-specs">
                    <div><dt>Mode</dt><dd>{selectedScenario.mode}</dd></div>
                    <div><dt>Birds</dt><dd>{selectedScenario.bird_count}</dd></div>
                    <div><dt>Capture</dt><dd>{selectedScenario.fps} FPS</dd></div>
                    <div><dt>Duration</dt><dd>{selectedScenario.duration_s} s</dd></div>
                    <div><dt>Seed</dt><dd>{selectedScenario.seed}</dd></div>
                  </dl>
                </div>
              ) : <p className="empty-copy">No scenarios reported by the API.</p>}
              <button className="primary-button" disabled={runPending || !scenarioId || !modelId}>
                {runPending ? "Running evaluation…" : "Run evaluation"}
              </button>
            </form>
          )}

          <section className="upload-section" aria-labelledby="upload-title">
            <div className="section-rule"><span id="upload-title">Add model artifact</span></div>
            <form className="upload-form" onSubmit={handleUpload}>
              <label>Name<input name="name" required placeholder="S11 detector" /></label>
              <div className="field-row">
                <label>Version<input name="version" required placeholder="0.4.1" /></label>
                <label>Source<input name="source" placeholder="veri" /></label>
              </div>
              <label className="file-control">Artifact<input name="artifact" type="file" required /></label>
              <button className="secondary-button" disabled={uploadPending}>{uploadPending ? "Uploading…" : "Upload to lab"}</button>
              {uploadMessage ? <p className="success-copy" role="status">{uploadMessage}</p> : null}
            </form>
          </section>
        </aside>

        <div className="analysis-column">
          <section className="panel viewport-panel" aria-labelledby="viewport-title">
            <div className="panel-heading viewport-heading">
              <div><span className="eyebrow">Pen monitor</span><h2 id="viewport-title">Overhead simulation</h2></div>
              <div className="telemetry">
                <span>T+ {selectedTime.toFixed(1)} S</span>
                <span>{currentSnapshot?.birds.length ?? 0} HEAD</span>
              </div>
            </div>
            <div className="viewport-frame"><PenViewport snapshot={currentSnapshot} showTruth={showTruth} showPredictions={showPredictions} penWidthM={activeScenario?.pen_width_m} penHeightM={activeScenario?.pen_height_m} /></div>
            <div className="viewport-controls">
              <div className="overlay-controls" aria-label="Pen overlays">
                <label><input type="checkbox" checked={showTruth} onChange={(event) => setShowTruth(event.target.checked)} /> Truth overlay</label>
                <label><input type="checkbox" checked={showPredictions} onChange={(event) => setShowPredictions(event.target.checked)} /> Predictions</label>
              </div>
              <input
                className="time-scrubber"
                aria-label="Simulation time"
                type="range"
                min="0"
                max={Math.max(snapshots.length - 1, 0)}
                value={Math.min(snapshotIndex, Math.max(snapshots.length - 1, 0))}
                onChange={(event) => setSnapshotIndex(Number(event.target.value))}
                disabled={!snapshots.length}
              />
              <div className="legend" aria-label="Pen legend">
                <span><i className="legend-dot legend-dot--baseline" /> Baseline</span>
                <span><i className="legend-dot legend-dot--exposed" /> Exposed</span>
                <span><i className="legend-dot legend-dot--clinical" /> Infectious / clinical</span>
                <span><i className="legend-ring" /> Model flag</span>
              </div>
            </div>
          </section>

          <section className="panel timeline-panel" aria-labelledby="timeline-title">
            <div className="panel-heading">
              <div><span className="eyebrow">Signal review</span><h2 id="timeline-title">Run timeline</h2></div>
              <span className="run-identifier">{activeRun ? `RUN ${activeRun.id.slice(0, 8)}` : "NO RUN"}</span>
            </div>
            <div className="chart-legend">
              <span className="key key--truth">Truth score</span><span className="key key--prediction">Predicted score</span>
              <span className="key key--threshold">Alert reference {activeScenario?.observation?.alert_threshold?.toFixed(2) ?? "not reported"}</span>
              <span className="key key--susceptible">Susceptible</span><span className="key key--exposed">Exposed</span>
              <span className="key key--infectious">Infectious</span><span className="key key--clinical">Clinical</span>
            </div>
            <TimelineChart points={timeline} selectedTime={selectedTime} onSelectTime={selectTime} alertThreshold={activeScenario?.observation?.alert_threshold} />
          </section>

          <section className="panel metrics-panel" aria-labelledby="metrics-title">
            <div className="panel-heading">
              <div><span className="eyebrow">Evaluation</span><h2 id="metrics-title">Performance readout</h2></div>
              {activeRun ? <span className={`status-pill status-pill--${activeRun.status}`}>{activeRun.status}</span> : null}
            </div>
            <Metrics metrics={activeRun?.metrics} />
          </section>
        </div>

        <aside className="history-panel panel" aria-labelledby="history-title">
          <div className="panel-heading">
            <div><span className="eyebrow">Run log</span><h2 id="history-title">Recent evaluations</h2></div>
            <span className="index-label">{runs.length.toString().padStart(2, "0")}</span>
          </div>
          {!runs.length ? <p className="empty-copy">No simulation runs yet.</p> : (
            <ol className="run-list">
              {runs.map((run) => {
                const scenario = scenarios.find((item) => item.id === run.scenario_id);
                const model = models.find((item) => item.id === run.model_id);
                return (
                  <li key={run.id}>
                    <button className={activeRun?.id === run.id ? "run-card run-card--active" : "run-card"} onClick={() => void loadRun(run)}>
                      <span className="run-card__top"><b>{run.id.slice(0, 8)}</b><i className={`run-state run-state--${run.status}`}>{run.status}</i></span>
                      <strong>{scenario?.name ?? run.scenario_id}</strong>
                      <span>{model ? `${model.name} / ${model.version}` : run.model_id}</span>
                      <span className="run-card__meta"><time>{formatDate(run.created_at)}</time><code>{run.executor}</code></span>
                    </button>
                  </li>
                );
              })}
            </ol>
          )}
          {selectedModel ? (
            <div className="artifact-detail">
              <span className="section-rule">Selected artifact</span>
              <strong>{selectedModel.name} / {selectedModel.version}</strong>
              <dl><div><dt>Format</dt><dd>{selectedModel.format}</dd></div><div><dt>Size</dt><dd>{formatBytes(selectedModel.size_bytes)}</dd></div><div><dt>SHA-256</dt><dd title={selectedModel.sha256 ?? "Not reported"}>{selectedModel.sha256 ? `${selectedModel.sha256.slice(0, 12)}…` : "Not reported"}</dd></div></dl>
            </div>
          ) : null}
        </aside>
      </main>
    </div>
  );
}
