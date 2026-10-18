import { FormEvent, useCallback, useEffect, useState } from "react";
import { api } from "./api";
import { HelpDrawer } from "./components/HelpDrawer";
import { MediaViewport } from "./components/MediaViewport";
import type { AdapterCapability, ClipAssessment, ClipAssessmentModule, DatasetClip, DatasetClipStatus, MediaAssetInfo, ModelArtifact, Scenario, SystemCapabilities } from "./types";

const STAGES = [
  { id: "activity", label: "Activity / energy", description: "Measures motion across the pen and summarizes zone-level flock energy." },
  { id: "appearance", label: "Flock appearance", description: "Summarizes visible flock-level appearance without requiring bird identity." },
  { id: "feces_candidates", label: "Feces candidates", description: "Finds likely droppings and records candidate regions and timestamps." },
  { id: "feces_classifier", label: "Feces disease classifier", description: "Classifies each candidate crop. The incoming feces model will plug in here." },
] as const;

const DATASET_GROUPS: Array<{ status: DatasetClipStatus; label: string }> = [
  { status: "ready", label: "Ready locally" },
  { status: "cataloged", label: "Cataloged — mock example available" },
  { status: "reference_only", label: "Reference only" },
  { status: "rejected", label: "Rejected for whole-pen assessment" },
];

function formatDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }).format(date);
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatTime(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  return `${minutes}:${Math.round(seconds % 60).toString().padStart(2, "0")}`;
}

function scorePercent(value: number): number {
  return value <= 1 ? value * 100 : value;
}

function distributionPercent(value: number, distribution: Record<string, number>): number {
  const total = Object.values(distribution).reduce((sum, count) => sum + count, 0);
  return total > 0 ? (value / total) * 100 : 0;
}

function qnxCapability(capabilities: SystemCapabilities | null): AdapterCapability | undefined {
  return capabilities?.executors?.find((item) => item.id === "qnx");
}

function moduleFor(stageId: string, modules: ClipAssessmentModule[]): ClipAssessmentModule | undefined {
  const aliases: Record<string, string[]> = {
    activity: ["activity", "motion", "energy"], appearance: ["appearance", "flock"],
    feces_candidates: ["feces_candidates", "feces-candidates", "candidate", "detector"],
    feces_classifier: ["feces_classifier", "feces-classifier", "classifier", "disease"],
  };
  return modules.find((module) => aliases[stageId]?.some((alias) => module.id.toLowerCase().includes(alias)));
}

function ScoreCard({ label, score, category, detail }: { label: string; score: number; category: string; detail: string }) {
  return <article className="score-card"><span>{label}</span><div><strong>{Math.round(scorePercent(score))}</strong><small>/ 100</small></div><b>{category}</b><p>{detail}</p></article>;
}

async function settleAssessment(initial: ClipAssessment): Promise<ClipAssessment> {
  let assessment = initial;
  for (let attempt = 0; attempt < 40 && ["queued", "running"].includes(assessment.status); attempt += 1) {
    await new Promise((resolve) => window.setTimeout(resolve, 750));
    assessment = await api.clipAssessment(assessment.id);
  }
  return assessment;
}

export default function App() {
  const [capabilities, setCapabilities] = useState<SystemCapabilities | null>(null);
  const [mediaAssets, setMediaAssets] = useState<MediaAssetInfo[]>([]);
  const [datasetClips, setDatasetClips] = useState<DatasetClip[]>([]);
  const [assessments, setAssessments] = useState<ClipAssessment[]>([]);
  const [assessment, setAssessment] = useState<ClipAssessment | null>(null);
  const [selectedDatasetId, setSelectedDatasetId] = useState("");
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadPreview, setUploadPreview] = useState("");
  const [sourceMode, setSourceMode] = useState<"library" | "upload">("library");
  const [processing, setProcessing] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [assessmentApiError, setAssessmentApiError] = useState("");
  const [libraryError, setLibraryError] = useState("");
  const [helpOpen, setHelpOpen] = useState(false);
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [models, setModels] = useState<ModelArtifact[]>([]);
  const [scenarioId, setScenarioId] = useState("");
  const [modelId, setModelId] = useState("");
  const [runtimePending, setRuntimePending] = useState(false);
  const [runtimeMessage, setRuntimeMessage] = useState("");
  const [modelUploadPending, setModelUploadPending] = useState(false);

  const selectedDataset = datasetClips.find((clip) => clip.id === selectedDatasetId) ?? datasetClips[0];
  const selectedDemo = selectedDataset?.demo_asset_id
    ? mediaAssets.find((asset) => asset.id === selectedDataset.demo_asset_id && asset.media_type.startsWith("video/") && asset.installed && asset.verified)
    : undefined;
  const assessmentAllowed = selectedDataset?.assessable ?? false;
  const qnx = qnxCapability(capabilities);
  const qnxEnabled = qnx?.status === "probe_only" || qnx?.status === "ready";
  const selectedModel = models.find((model) => model.id === modelId);
  const modelBlockedForQnx = !selectedModel || selectedModel.format === "mock" || selectedModel.size_bytes === 0;

  const refreshAssessments = useCallback(async () => {
    try {
      const next = await api.clipAssessments();
      setAssessments(next);
      setAssessmentApiError("");
      return next;
    } catch (requestError) {
      setAssessmentApiError(requestError instanceof Error ? requestError.message : "The clip assessment API is unavailable.");
      return [];
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    Promise.all([api.capabilities(), api.media(), api.scenarios(), api.models()])
      .then(([nextCapabilities, nextMedia, nextScenarios, nextModels]) => {
        if (cancelled) return;
        setCapabilities(nextCapabilities); setMediaAssets(nextMedia); setScenarios(nextScenarios); setModels(nextModels);
        setScenarioId(nextScenarios[0]?.id ?? ""); setModelId(nextModels[0]?.id ?? "");
      })
      .catch((requestError: unknown) => { if (!cancelled) setError(requestError instanceof Error ? requestError.message : "Could not connect to the local API."); })
      .finally(() => { if (!cancelled) setLoading(false); });
    void refreshAssessments();
    void api.datasetClips()
      .then((clips) => {
        if (cancelled) return;
        setDatasetClips(clips);
        setSelectedDatasetId(clips.find((clip) => clip.status === "ready")?.id ?? clips.find((clip) => clip.status === "cataloged")?.id ?? clips[0]?.id ?? "");
        setLibraryError("");
      })
      .catch((requestError: unknown) => {
        if (!cancelled) setLibraryError(requestError instanceof Error ? requestError.message : "The dataset library API is unavailable.");
      });
    return () => { cancelled = true; };
  }, [refreshAssessments]);

  useEffect(() => {
    if (!uploadFile) { setUploadPreview(""); return; }
    const url = URL.createObjectURL(uploadFile); setUploadPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [uploadFile]);

  async function handleAssess() {
    setProcessing(true); setError(""); setAssessmentApiError("");
    try {
      let created: ClipAssessment;
      if (sourceMode === "upload") {
        if (!uploadFile) throw new Error("Choose a whole-pen video before starting the assessment.");
        created = await api.uploadClipAssessment(uploadFile);
      } else {
        if (!selectedDataset) throw new Error("Choose a dataset-library clip before starting an assessment.");
        if (selectedDataset.status === "ready") {
          if (!selectedDataset.demo_asset_id || !selectedDemo) throw new Error("This ready clip does not have verified local video bytes available.");
          created = await api.assessDemoClip(selectedDataset.demo_asset_id);
        } else if (selectedDataset.status === "cataloged") {
          created = await api.assessCatalogClip(selectedDataset.id);
        } else {
          throw new Error(`This ${selectedDataset.status.replaceAll("_", " ")} reference is not eligible for clip assessment.`);
        }
      }
      const completed = await settleAssessment(created); setAssessment(completed); await refreshAssessments();
      if (completed.status === "failed") setError("The assessment was stored but did not complete. Review its status and server logs.");
    } catch (requestError) {
      setAssessmentApiError(requestError instanceof Error ? requestError.message : "The clip assessment could not be started.");
    } finally { setProcessing(false); }
  }

  function selectSourceMode(nextMode: "library" | "upload") {
    setSourceMode(nextMode);
    setAssessment(null);
  }

  function selectDataset(nextId: string) {
    setSelectedDatasetId(nextId);
    setAssessment(null);
  }

  function selectUpload(file: File | null) {
    setUploadFile(file);
    setAssessment(null);
  }

  async function handleTargetCheck() {
    setRuntimePending(true); setRuntimeMessage(""); setError("");
    try {
      const fresh = await api.probeQnx(); setCapabilities(await api.capabilities());
      setRuntimeMessage(`Target check: ${fresh.status.replaceAll("_", " ")} — ${fresh.description}`);
    } catch (requestError) { setError(requestError instanceof Error ? requestError.message : "The QNX target check failed."); }
    finally { setRuntimePending(false); }
  }

  async function handleQnxValidation() {
    if (!scenarioId || !modelId) return;
    setRuntimePending(true); setRuntimeMessage(""); setError("");
    try {
      const run = await api.createRun({ scenario_id: scenarioId, model_id: modelId, executor: "qnx" });
      setRuntimeMessage(`QNX run ${run.id.slice(0, 12)} created. ${qnx?.status === "probe_only" ? "Artifact validation only; inference was not run." : "Target executor accepted the run."}`);
    } catch (requestError) { setError(requestError instanceof Error ? requestError.message : "The QNX validation could not be started."); }
    finally { setRuntimePending(false); }
  }

  async function handleModelUpload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget; const data = new FormData(form); const file = data.get("artifact");
    const name = String(data.get("name") ?? "").trim(); const version = String(data.get("version") ?? "").trim(); const source = String(data.get("source") ?? "").trim();
    if (!(file instanceof File) || !file.size || !name || !version) return;
    setModelUploadPending(true); setRuntimeMessage("");
    try {
      const uploaded = await api.uploadModel(file, name, version, source || undefined); setModels(await api.models()); setModelId(uploaded.id);
      setRuntimeMessage(`${uploaded.name} ${uploaded.version} cataloged. Runtime compatibility has not been assumed.`); form.reset();
    } catch (requestError) { setError(requestError instanceof Error ? requestError.message : "The model could not be uploaded."); }
    finally { setModelUploadPending(false); }
  }

  const closeHelp = useCallback(() => setHelpOpen(false), []);

  return <div className="app-shell clip-app">
    <header className="app-header clip-header">
      <div className="brand-lockup"><span className="brand-mark" aria-hidden="true">HC</span><div><h1>Holy-Crap</h1><p>Whole-pen clip assessment</p></div></div>
      <div className="header-actions">
        <span className="capability capability--ready"><i aria-hidden="true" /> Local API <small>{capabilities ? "ready" : "connecting"}</small></span>
        <span className={`capability ${qnxEnabled ? "capability--ready" : "capability--off"}`} title={qnx?.description}><i aria-hidden="true" /> QNX target <small>{qnx?.status?.replaceAll("_", " ") ?? "not reported"}</small></span>
        <button className="help-button" aria-expanded={helpOpen} aria-controls="help-drawer" onClick={() => setHelpOpen(true)}>How it works</button>
      </div>
    </header>

    <section className="clip-intro" aria-labelledby="clip-intro-title">
      <div><span className="eyebrow">One video → one flock-level report</span><h2 id="clip-intro-title">What did this pen look like during the clip?</h2><p>Upload a whole-pen video—around five minutes is the target—and summarize flock energy, visible appearance, and feces candidates across the clip.</p></div>
      <aside><strong>Scope boundary</strong><p>Individual bird identity and persistent tracking are not required. A short clip cannot establish infection progression, and this report is not a veterinary diagnosis.</p></aside>
    </section>
    {error ? <div className="error-banner" role="alert"><strong>Request failed.</strong> {error}</div> : null}

    <main className="clip-workspace">
      <aside className="panel source-panel" aria-labelledby="source-title">
        <div className="panel-heading"><div><span className="eyebrow">Step 01</span><h2 id="source-title">Choose a whole-pen clip</h2></div><span className="index-label">VIDEO</span></div>
        <div className="source-tabs" role="tablist" aria-label="Video source">
          <button role="tab" aria-selected={sourceMode === "library"} className={sourceMode === "library" ? "source-tab source-tab--active" : "source-tab"} onClick={() => selectSourceMode("library")}>Dataset library</button>
          <button role="tab" aria-selected={sourceMode === "upload"} className={sourceMode === "upload" ? "source-tab source-tab--active" : "source-tab"} onClick={() => selectSourceMode("upload")}>Upload video</button>
        </div>
        {sourceMode === "library" ? <div className="source-content source-controls">
          <label className="clip-field">Reviewed dataset clip<select value={selectedDatasetId} onChange={(event) => selectDataset(event.target.value)} disabled={!datasetClips.length}>
            {DATASET_GROUPS.map((group) => {
              const clips = datasetClips.filter((clip) => clip.status === group.status);
              return clips.length ? <optgroup key={group.status} label={group.label}>{clips.map((clip) => <option key={clip.id} value={clip.id}>{clip.dataset_name} — {clip.title}</option>)}</optgroup> : null;
            })}
          </select></label>
          {libraryError ? <p className="blocked-copy" role="alert">Dataset library unavailable: {libraryError}</p> : null}
          {selectedDataset ? <article className="dataset-card">
            <div className="dataset-card__top"><span className={`dataset-status dataset-status--${selectedDataset.status}`}>{selectedDataset.status.replaceAll("_", " ")}</span><small>{selectedDataset.license}</small></div>
            <strong>{selectedDataset.dataset_name}</strong><b>{selectedDataset.title}</b>
            <p>{selectedDataset.duration_s == null ? "Duration unknown" : formatTime(selectedDataset.duration_s)} · {selectedDataset.width ?? "?"}×{selectedDataset.height ?? "?"} · {selectedDataset.fps ?? "?"} FPS</p>
            {[selectedDataset.review_verdict, selectedDataset.camera_fit, ...selectedDataset.limitations].slice(0, 3).map((note) => <p key={note}>{note}</p>)}
            <div className="dataset-links"><a href={selectedDataset.source_url} target="_blank" rel="noreferrer">Source clip</a><a href={selectedDataset.dataset_url} target="_blank" rel="noreferrer">Dataset</a>{selectedDataset.doi ? <a href={`https://doi.org/${selectedDataset.doi}`} target="_blank" rel="noreferrer">DOI</a> : null}</div>
            {!assessmentAllowed ? <p className="dataset-disabled">{selectedDataset.status === "rejected" ? "Rejected during camera-angle review; retained for provenance only." : "Reference material only; no compatible whole-pen assessment input."}</p> : selectedDataset.status === "ready" && !selectedDemo ? <p className="dataset-disabled">Approved demo clip, but its verified video bytes are not installed locally. Run <code>make demo-assets</code> before assessment.</p> : null}
          </article> : <p className="source-guidance">No reviewed dataset clips were returned by the API.</p>}
        </div> : <div className="source-content upload-clip-content source-controls">
          <label className="clip-dropzone"><span>Whole-pen video</span><strong>{uploadFile?.name ?? "Choose an MP4, MOV, or WebM file"}</strong><small>Target length: approximately 5 minutes. The flock should remain visible as a group.</small><input type="file" accept="video/mp4,video/quicktime,video/webm,video/*" onChange={(event) => selectUpload(event.target.files?.[0] ?? null)} /></label>
        </div>}
        <div className="assessment-action"><div><strong>Aggregate the full clip</strong><span>No individual bird identity or cross-clip tracking.</span></div><button className="primary-button" onClick={handleAssess} disabled={processing || loading || (sourceMode === "library" ? !assessmentAllowed || (selectedDataset?.status === "ready" && !selectedDemo) : !uploadFile)}>{processing ? "Assessing clip…" : sourceMode === "upload" ? "Upload & assess clip" : selectedDataset?.status === "cataloged" ? "Generate mock example" : selectedDataset?.status === "ready" ? "Assess installed clip" : "Unavailable for assessment"}</button></div>
        {assessmentApiError ? <div className="wiring-error" role="alert"><strong>Clip assessment API unavailable</strong><span>{assessmentApiError} No browser-generated result was substituted; the dashboard only renders persisted API assessments.</span></div> : null}
      </aside>

      <section className="panel viewer-panel" aria-labelledby="viewer-title">
        <div className="panel-heading"><div><span className="eyebrow">Clip viewer</span><h2 id="viewer-title">Whole-pen observation window</h2></div><span className="index-label">{sourceMode === "library" ? selectedDataset?.status.replaceAll("_", " ") ?? "LIBRARY" : "UPLOAD"}</span></div>
        {sourceMode === "library"
          ? selectedDemo ? <MediaViewport assets={[selectedDemo]} /> : <div className="viewer-empty viewer-empty--catalog"><span aria-hidden="true">{selectedDataset?.status === "cataloged" ? "MOCK" : "—"}</span><strong>{selectedDataset?.status === "cataloged" ? "No local video bytes" : "Playback unavailable"}</strong><p>{selectedDataset?.status === "cataloged" ? "Generate a persisted deterministic example from this catalog entry. Results remain clearly marked MOCK; the dashboard will not pretend a video was played." : selectedDataset?.status === "ready" ? "This approved clip is not installed locally. Run make demo-assets to fetch and verify its bytes before assessment." : "This entry is retained for research provenance and cannot be assessed from the dashboard."}</p>{selectedDataset ? <div className="viewer-source-links"><a href={selectedDataset.source_url} target="_blank" rel="noreferrer">Open source</a><a href={selectedDataset.dataset_url} target="_blank" rel="noreferrer">Open dataset</a></div> : null}</div>
          : uploadPreview ? <div className="upload-preview-wrap"><video className="upload-preview" src={uploadPreview} controls preload="metadata">Your browser cannot preview this video.</video></div> : <div className="viewer-empty"><span aria-hidden="true">▶</span><strong>Select a whole-pen video</strong><p>The selected clip will remain visible here while you review its aggregate assessment.</p></div>}
        <p className="viewer-boundary">This is a clip-level observation. Bird identities do not need to persist, and the video does not establish infection progression.</p>
      </section>

      <section className="panel pipeline-panel" aria-labelledby="pipeline-title">
        <div className="panel-heading"><div><span className="eyebrow">Step 02</span><h2 id="pipeline-title">Assessment pipeline</h2></div><span className="index-label">4 STAGES</span></div>
        <ol className="pipeline-list">{STAGES.map((stage, index) => {
          const module = assessment ? moduleFor(stage.id, assessment.modules) : undefined; const mode = module?.mode ?? "mock";
          return <li key={stage.id} className="pipeline-stage"><span className="stage-number">{String(index + 1).padStart(2, "0")}</span><div><strong>{stage.label}</strong><p>{stage.description}</p></div><div className="stage-runtime"><span className={`mode-badge mode-badge--${mode}`}>{mode === "real" ? "REAL MODEL" : "MOCK"}</span><small>{module ? `${module.version} · ${module.status}` : "deterministic placeholder · ready"}</small></div></li>;
        })}</ol>
        <p className="pipeline-note"><strong>Current boundary:</strong> mock stages are deterministic and non-diagnostic. Each stage records its mode and version so a real activity, appearance, detector, or feces classifier can replace it independently.</p>
      </section>

      <section className="panel results-panel" aria-labelledby="results-title">
        <div className="panel-heading"><div><span className="eyebrow">Step 03</span><h2 id="results-title">Aggregate clip summary</h2></div>{assessment ? <span className={`status-pill status-pill--${assessment.status}`}>{assessment.status}</span> : <span className="index-label">AWAITING CLIP</span>}</div>
        {!assessment ? <div className="results-empty results-empty--compact"><span aria-hidden="true">◎</span><strong>No result yet</strong><p>Assess the selected whole-pen clip to populate this summary.</p></div> : <div className="assessment-results aggregate-results">
          <div className="score-grid">
            <ScoreCard label="Activity / energy" score={assessment.summary.activity.score} category={assessment.summary.activity.category} detail={`${Math.round(assessment.summary.activity.motion_coverage * 100)}% motion coverage across the pen`} />
            <ScoreCard label="Flock appearance" score={assessment.summary.appearance.score} category={assessment.summary.appearance.category} detail={assessment.summary.appearance.notes[0] ?? "No aggregate appearance note reported."} />
            <article className="score-card score-card--count"><span>Feces candidates</span><div><strong>{assessment.summary.feces.candidate_count}</strong></div><b>regions for review</b><p>Candidates are clip-level detections, not confirmed droppings or diagnoses.</p></article>
          </div>
          <section className="aggregate-distribution" aria-labelledby="distribution-title"><div className="subheading"><div><span className="eyebrow">Classifier output</span><h3 id="distribution-title">Candidate distribution</h3></div><span className={`mode-badge mode-badge--${moduleFor("feces_classifier", assessment.modules)?.mode ?? "mock"}`}>{moduleFor("feces_classifier", assessment.modules)?.mode === "real" ? "REAL" : "MOCK"}</span></div><div className="distribution-list">
            {Object.entries(assessment.summary.feces.class_distribution).map(([label, value]) => <div className="distribution-row" key={label}><span>{label}</span><div><i style={{ width: `${distributionPercent(value, assessment.summary.feces.class_distribution)}%` }} /></div><strong>{value}</strong></div>)}
          </div></section>
          <div className="overall-review"><div><span className="eyebrow">Overall review state</span><strong>{assessment.summary.overall.review_state.replaceAll("_", " ")}</strong></div><ul>{assessment.summary.overall.notes.map((note) => <li key={note}>{note}</li>)}</ul></div>
          <p className="non-diagnostic"><strong>Non-diagnostic:</strong> {assessment.non_diagnostic_notice}</p>
        </div>}
      </section>

      <section className="panel review-panel" aria-labelledby="review-title">
        <div className="panel-heading"><div><span className="eyebrow">Clip review</span><h2 id="review-title">Evidence & candidate rows</h2></div>{assessment ? <span className="index-label">{assessment.summary.feces.candidates.length} CANDIDATES</span> : <span className="index-label">NO RESULT</span>}</div>
        {!assessment ? <div className="results-empty"><span aria-hidden="true">⌁</span><strong>Evidence will appear here</strong><p>Run the selected video to review pen-zone movement and feces candidate timestamps without tracking individual birds.</p></div> : <div className="assessment-results">
          <div className="assessment-provenance"><div><strong>{assessment.video.name}</strong><span>{formatBytes(assessment.video.size_bytes)} · {assessment.video.duration_s == null ? "duration unknown" : formatTime(assessment.video.duration_s)} · {assessment.video.width ?? "?"}×{assessment.video.height ?? "?"} · {assessment.video.fps ?? "?"} FPS</span></div><code title={assessment.video.sha256}>#{assessment.id.slice(0, 12)} · sha256 {assessment.video.sha256.slice(0, 12)}… · {formatDate(assessment.created_at)}</code></div>
          <section className="review-zones" aria-labelledby="zones-title"><div className="subheading"><div><span className="eyebrow">Spatial context</span><h3 id="zones-title">Activity by pen zone</h3></div><span className={`mode-badge mode-badge--${moduleFor("activity", assessment.modules)?.mode ?? "mock"}`}>{moduleFor("activity", assessment.modules)?.mode === "real" ? "REAL MODEL" : "MOCK"}</span></div><dl className="zone-list">{Object.entries(assessment.summary.activity.zone_scores).map(([zone, value]) => <div key={zone}><dt>{zone.replaceAll("_", " ")}</dt><dd>{Math.round(scorePercent(value))}</dd></div>)}</dl><p className="zone-note">Zone averages tolerate occlusion and birds entering or leaving view. Persistent individual tracking is not required.</p></section>
          <section className="candidate-section" aria-labelledby="candidate-title"><div className="subheading"><div><span className="eyebrow">Review queue</span><h3 id="candidate-title">Feces candidate rows</h3></div><span>{assessment.summary.feces.candidates.length} shown</span></div><div className="candidate-table-wrap"><table className="candidate-table"><thead><tr><th>Candidate</th><th>Time</th><th>Crop box</th><th>Classification</th><th>Confidence</th><th>Mode</th></tr></thead><tbody>{assessment.summary.feces.candidates.map((candidate) => <tr key={candidate.id}><td><code>{candidate.id}</code></td><td>{formatTime(candidate.timestamp_s)}</td><td><code>{candidate.bbox.x.toFixed(2)}, {candidate.bbox.y.toFixed(2)} · {candidate.bbox.width.toFixed(2)}×{candidate.bbox.height.toFixed(2)}</code></td><td>{candidate.classification.label}</td><td>{Math.round(candidate.classification.confidence * 100)}%</td><td><span className={`mode-badge mode-badge--${candidate.classification.mode}`}>{candidate.classification.mode === "real" ? "REAL" : "MOCK"}</span></td></tr>)}</tbody></table></div></section>
        </div>}
      </section>

      <section className="panel history-strip" aria-labelledby="history-title"><div className="panel-heading"><div><span className="eyebrow">Saved evidence</span><h2 id="history-title">Recent clip assessments</h2></div><span className="index-label">{assessments.length}</span></div>{assessments.length ? <div className="assessment-history">{assessments.map((item) => <button key={item.id} className={assessment?.id === item.id ? "assessment-history-card assessment-history-card--active" : "assessment-history-card"} onClick={() => setAssessment(item)}><strong>{item.video.name}</strong><span>{formatDate(item.created_at)} · {item.status}</span><small>{Math.round(scorePercent(item.summary.activity.score))} activity · {item.summary.feces.candidate_count} feces candidates</small></button>)}</div> : <p className="empty-copy">No persisted clip assessments yet.</p>}</section>

      <details className="panel runtime-panel"><summary><span><span className="eyebrow">Advanced</span><strong>Model artifacts, QNX target & synthetic engine</strong></span><small>Open runtime controls</small></summary><div className="runtime-content">
        <section><h3>QNX target validation</h3><p>{qnx?.description ?? "The QNX executor has not reported a capability yet."}</p><div className="runtime-actions"><button className="secondary-button" onClick={handleTargetCheck} disabled={runtimePending}>{runtimePending ? "Working…" : "Check target"}</button></div><div className="runtime-grid"><label>Model artifact<select value={modelId} onChange={(event) => setModelId(event.target.value)}>{models.map((model) => <option key={model.id} value={model.id}>{model.name} / {model.version}</option>)}</select></label><label>Synthetic scenario<select value={scenarioId} onChange={(event) => setScenarioId(event.target.value)}>{scenarios.map((scenario) => <option key={scenario.id} value={scenario.id}>{scenario.name}</option>)}</select></label></div>{modelBlockedForQnx ? <p className="blocked-copy">Choose a real, non-empty model artifact for QNX staging.</p> : null}<button className="primary-button" onClick={handleQnxValidation} disabled={runtimePending || !qnxEnabled || modelBlockedForQnx || !scenarioId}>{qnx?.status === "probe_only" ? "Validate artifact on QNX" : "Run on QNX"}</button><p className="form-note">When the target reports validation-only, this stages and verifies bytes but does not run inference. Synthetic scenarios are test plumbing, not the primary clip workflow.</p></section>
        <section><h3>Add a model artifact</h3><form className="runtime-upload" onSubmit={handleModelUpload}><label>Name<input name="name" required placeholder="Feces classifier" /></label><label>Version<input name="version" required placeholder="0.1.0" /></label><label>Source<input name="source" placeholder="Veri / Kaggle chicken-disease-1" /></label><label>Artifact<input name="artifact" type="file" required /></label><button className="secondary-button" disabled={modelUploadPending}>{modelUploadPending ? "Uploading…" : "Upload to catalog"}</button></form><p className="form-note">The incoming feces classifier belongs after candidate localization. Uploading catalogs model bytes and provenance; it does not prove runtime compatibility.</p></section>
      </div>{runtimeMessage ? <p className="runtime-message" role="status">{runtimeMessage}</p> : null}</details>
    </main>
    <HelpDrawer open={helpOpen} onClose={closeHelp} />
  </div>;
}
