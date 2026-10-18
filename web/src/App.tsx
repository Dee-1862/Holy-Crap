import { FormEvent, useCallback, useEffect, useState } from "react";
import { api } from "./api";
import { AssessmentVideoViewport } from "./components/AssessmentVideoViewport";
import { BirdObservationCard } from "./components/BirdObservationCard";
import { CandidateEvidence } from "./components/CandidateEvidence";
import { DatasetClipPreview } from "./components/DatasetClipPreview";
import { HelpDrawer } from "./components/HelpDrawer";
import { MediaViewport } from "./components/MediaViewport";
import { ModeBadge } from "./components/ModeBadge";
import { QnxEvidencePanel } from "./components/QnxEvidencePanel";
import { SpecimenPoolSummary } from "./components/SpecimenPoolSummary";
import { StageProvenance } from "./components/StageProvenance";
import { activityEvidence, assessmentAnnotations, locationSourceShortLabel, moduleFor, orderedBehaviorDistribution } from "./evidence";
import type { AdapterCapability, AssessmentExecutor, ClipAssessment, ClipAssessmentJob, ClipPenAssessment, ClipTelemetrySample, DatasetClip, DatasetClipStatus, DemoProfile, FecesCandidate, MediaAssetInfo, ModelArtifact, ProxySpecimenPoolSummary, QnxEvidencePayload, Scenario, SystemCapabilities, VideoAnnotation } from "./types";

const STAGES = [
  { id: "activity", label: "Activity / energy" },
  { id: "appearance", label: "Flock appearance" },
  { id: "feces_candidates", label: "Feces candidates" },
  { id: "feces_classifier", label: "Feces appearance classifier" },
] as const;

const PROFILE_OPTIONS: Array<{ value: DemoProfile; label: string }> = [
  { value: "healthy", label: "Healthy" },
  { value: "mixed", label: "Mixed" },
  { value: "concerning", label: "Concerning" },
];

const DATASET_GROUPS: Array<{ status: DatasetClipStatus; label: string }> = [
  { status: "ready", label: "Ready locally" },
  { status: "cataloged", label: "Cataloged" },
  { status: "reference_only", label: "Reference only" },
  { status: "rejected", label: "Rejected for whole-pen assessment" },
];

const EXECUTOR_OPTIONS: Array<{ value: AssessmentExecutor; label: string }> = [
  { value: "local", label: "Local Mac" },
  { value: "qnx", label: "QNX Pi" },
];

const DEFAULT_SEGMENT_SECONDS = 20;

function defaultSegmentEnd(duration: number | null | undefined): number {
  return duration != null && Number.isFinite(duration)
    ? Math.min(DEFAULT_SEGMENT_SECONDS, duration)
    : DEFAULT_SEGMENT_SECONDS;
}

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

function formatClock(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : new Intl.DateTimeFormat(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit" }).format(date);
}

function latestTelemetry(job: ClipAssessmentJob): ClipTelemetrySample | null {
  if (job.telemetry) return job.telemetry;
  const history = job.telemetry_history;
  return history && history.length > 0 ? history[history.length - 1] : null;
}

type TargetBadgeKind = "local" | "qnx" | "unknown";

function targetBadgeState(job: ClipAssessmentJob): { label: string; status: string; kind: TargetBadgeKind } {
  const target = job.target;
  if (target) {
    const isQnx = job.requested_executor === "qnx" || target.executor === "qnx";
    if (isQnx) {
      const label = target.hostname ? `QNX Pi · ${target.hostname}` : "QNX Pi";
      if (!target.verified || job.effective_executor !== "qnx") return { label, status: "execution not verified", kind: "qnx" };
      return { label, status: "execution verified on QNX", kind: "qnx" };
    }
    return { label: target.hostname ? `Local Mac · ${target.hostname}` : "Local Mac", status: target.verified ? "local execution verified" : "identity not verified", kind: "local" };
  }
  if (job.requested_executor === "qnx") return { label: "QNX Pi", status: "execution not verified", kind: "qnx" };
  if (job.requested_executor === "local") return { label: "Local Mac", status: "target not reported", kind: "local" };
  return { label: "Executor", status: "not reported", kind: "unknown" };
}

function TargetBadge({ job }: { job: ClipAssessmentJob }) {
  const state = targetBadgeState(job);
  const osArch = job.target
    ? [job.target.system, job.target.release, job.target.machine].filter(Boolean).join(" · ")
    : null;
  return <div className={`target-badge target-badge--${state.kind}`} role="status">
    <strong>{state.label}</strong><span>{state.status}</span>{osArch ? <small>{osArch}</small> : null}
  </div>;
}

function JobTelemetry({ job }: { job: ClipAssessmentJob }) {
  const sample = latestTelemetry(job);
  return <div className="job-telemetry-block">
    {sample ? <span className="job-telemetry-block__sampled">{sample.source} sample · {formatClock(sample.captured_at)}</span> : null}
    <dl className="job-telemetry">
      <div><dt>CPU</dt><dd>{sample?.cpu_percent != null ? `${Math.round(sample.cpu_percent)}%` : "—"}</dd></div>
      <div><dt>RAM used / total</dt><dd>{sample?.ram_used_bytes != null && sample.ram_total_bytes != null ? `${formatBytes(sample.ram_used_bytes)} / ${formatBytes(sample.ram_total_bytes)}` : "—"}</dd></div>
      <div><dt>Process RSS</dt><dd>{sample?.process_ram_bytes != null ? formatBytes(sample.process_ram_bytes) : "—"}</dd></div>
    </dl>
  </div>;
}

function ScoreCard({ label, score, category, detail }: { label: string; score: number; category: string; detail: string }) {
  return <article className="score-card"><span>{label}</span><div><strong>{Math.round(scorePercent(score))}</strong><small>/ 100</small></div><b>{category}</b>{detail ? <p>{detail}</p> : null}</article>;
}

function PenAssessment({ assessment }: { assessment: ClipAssessment }) {
  const state = penState(assessment);
  const pen = penAssessment(assessment);
  return <section className="pen-assessment" aria-labelledby="pen-assessment-title">
    <div className="subheading"><div><span className="eyebrow">Pen-level assessment</span><h3 id="pen-assessment-title">Operational state</h3></div><span className={`pen-state pen-state--${state.kind}`}>{state.label}</span></div>
    <dl className="pen-signal-grid">
      <div><dt>Policy score</dt><dd>{typeof pen?.score === "number" ? Math.round(scorePercent(pen.score)) : "—"}</dd></div>
      <div><dt>Activity</dt><dd>{typeof pen?.activity_contribution === "number" ? Math.round(pen.activity_contribution * 100) : "—"}%</dd></div>
      <div><dt>Feces</dt><dd>{typeof pen?.feces_contribution === "number" ? Math.round(pen.feces_contribution * 100) : "—"}%</dd></div>
    </dl>
  </section>;
}

function ActivityEvidenceSection({ assessment }: { assessment: ClipAssessment }) {
  const evidence = activityEvidence(assessment);
  if (!evidence) return null;
  const distribution = orderedBehaviorDistribution(evidence.behaviorDistribution);
  const module = moduleFor("activity", assessment.modules);
  return <section className="activity-evidence" aria-labelledby="activity-evidence-title">
    <div className="subheading"><div><span className="eyebrow">Activity model evidence</span><h3 id="activity-evidence-title">Sampled inference</h3></div><ModeBadge mode={module?.mode} compact /></div>
    <dl className="activity-evidence-stats">
      <div><dt>Sampled frames</dt><dd>{evidence.sampledFrames ?? "—"}</dd></div>
      <div><dt>Behavior observations</dt><dd>{evidence.behaviorObservations ?? "—"}</dd></div>
      <div><dt>Detected birds</dt><dd>{evidence.detectedBirds ?? "—"}</dd></div>
      <div><dt>Model coverage</dt><dd>{evidence.modelCoverage !== null ? `${Math.round(evidence.modelCoverage * 100)}%` : "—"}</dd></div>
    </dl>
    {distribution.length ? <div className="distribution-list activity-evidence-distribution">{distribution.map(([label, value]) => {
      const percent = distributionPercent(value, evidence.behaviorDistribution ?? {});
      return <div className="distribution-row" key={label}><span>{label.replaceAll("_", " ")}</span><div><i style={{ width: `${percent}%` }} /></div><strong>{Math.round(percent)}%</strong></div>;
    })}</div> : null}
  </section>;
}

async function settleAssessmentJob(initial: ClipAssessmentJob, onUpdate: (job: ClipAssessmentJob) => void): Promise<ClipAssessmentJob> {
  let job = initial;
  onUpdate(job);
  while (job.status === "queued" || job.status === "running") {
    await new Promise((resolve) => window.setTimeout(resolve, 750));
    job = await api.clipAssessmentJob(job.id);
    onUpdate(job);
  }
  return job;
}

type PenStateKind = "routine" | "watch" | "review" | "demo" | "other";

function penAssessment(assessment: ClipAssessment | null): ClipPenAssessment | null {
  return assessment?.summary.pen_assessment ?? null;
}

function penState(assessment: ClipAssessment | null): { label: string; kind: PenStateKind } {
  const pen = penAssessment(assessment);
  if (pen?.state) {
    if (pen.state === "normal") return { label: "routine", kind: "routine" };
    if (pen.state === "watch") return { label: "watch", kind: "watch" };
    if (pen.state === "review") return { label: "review", kind: "review" };
    return { label: pen.state.replaceAll("_", " "), kind: "other" };
  }
  const reviewState = assessment?.summary.overall.review_state;
  if (reviewState === "synthetic-demo-only") return { label: "demo", kind: "demo" };
  return { label: reviewState?.replaceAll("_", " ") ?? "not reported", kind: "other" };
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
  const [uploadDuration, setUploadDuration] = useState<number | null>(null);
  const [segmentStart, setSegmentStart] = useState(0);
  const [segmentEnd, setSegmentEnd] = useState(DEFAULT_SEGMENT_SECONDS);
  const [sourceMode, setSourceMode] = useState<"library" | "upload">("library");
  const [processing, setProcessing] = useState(false);
  const [assessmentJob, setAssessmentJob] = useState<ClipAssessmentJob | null>(null);
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
  const [profile, setProfile] = useState<DemoProfile>("mixed");
  const [executor, setExecutor] = useState<AssessmentExecutor>("local");
  const [selectedCandidateId, setSelectedCandidateId] = useState<string | null>(null);
  const [selectedBird, setSelectedBird] = useState<VideoAnnotation | null>(null);
  const [qnxEvidence, setQnxEvidence] = useState<QnxEvidencePayload | null>(null);
  const [qnxEvidenceError, setQnxEvidenceError] = useState("");
  const [proxyPoolSummary, setProxyPoolSummary] = useState<ProxySpecimenPoolSummary | null>(null);

  const selectedDataset = datasetClips.find((clip) => clip.id === selectedDatasetId) ?? datasetClips[0];
  const selectedDemo = selectedDataset?.demo_asset_id
    ? mediaAssets.find((asset) => asset.id === selectedDataset.demo_asset_id && asset.media_type.startsWith("video/") && asset.installed && asset.verified)
    : undefined;
  const selectedCandidate: FecesCandidate | null = assessment?.summary.feces.candidates.find((candidate) => candidate.id === selectedCandidateId) ?? null;
  const assessmentAnnotationsList = assessmentAnnotations(assessment);
  const assessmentAllowed = selectedDataset?.assessable ?? false;
  const qnx = qnxCapability(capabilities);
  const qnxEnabled = qnx?.status === "probe_only" || qnx?.status === "ready";
  const qnxBlocked = executor === "qnx" && (qnx?.status === "not_configured" || qnx?.status === "unreachable" || qnx?.status === "runtime_missing");
  const selectedModel = models.find((model) => model.id === modelId);
  const modelBlockedForQnx = !selectedModel || selectedModel.format === "mock" || selectedModel.size_bytes === 0;
  const sourceDuration = sourceMode === "upload" ? uploadDuration : selectedDataset?.duration_s ?? null;
  const segmentValid = sourceDuration != null
    && segmentStart >= 0
    && segmentEnd > segmentStart
    && segmentEnd <= sourceDuration;
  const selectedSegment = segmentValid ? { start_s: segmentStart, end_s: segmentEnd } : undefined;

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
    void api.qnxEvidence()
      .then((evidence) => {
        if (!cancelled) {
          setQnxEvidence(evidence);
          setQnxEvidenceError("");
        }
      })
      .catch((requestError: unknown) => {
        if (!cancelled) setQnxEvidenceError(requestError instanceof Error ? requestError.message : "The QNX evidence endpoint is unavailable.");
      });
    void api.proxySpecimens()
      .then((pool) => {
        if (!cancelled) setProxyPoolSummary(pool);
      })
      .catch(() => {
        // The pool inventory endpoint may not exist on older backends; fall back to assessment-derived counts.
      });
    return () => { cancelled = true; };
  }, [refreshAssessments]);

  useEffect(() => {
    if (!uploadFile) { setUploadPreview(""); return; }
    const url = URL.createObjectURL(uploadFile); setUploadPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [uploadFile]);

  useEffect(() => {
    if (sourceMode !== "library" || !selectedDatasetId) return;
    const duration = datasetClips.find((clip) => clip.id === selectedDatasetId)?.duration_s;
    setSegmentStart(0);
    setSegmentEnd(defaultSegmentEnd(duration));
  }, [datasetClips, selectedDatasetId, sourceMode]);

  async function handleAssess() {
    setProcessing(true); setError(""); setAssessmentApiError("");
    setAssessmentJob(null);
    setAssessment(null); setSelectedCandidateId(null); setSelectedBird(null);
    try {
      let created: ClipAssessmentJob;
      if (sourceMode === "upload") {
        if (!uploadFile) throw new Error("Choose a whole-pen video before starting the assessment.");
        if (!selectedSegment) throw new Error("Choose a valid video segment before starting the assessment.");
        created = await api.uploadClipAssessment(uploadFile, executor, profile, selectedSegment);
      } else {
        if (!selectedDataset) throw new Error("Choose a dataset-library clip before starting an assessment.");
        if (selectedDataset.status === "ready") {
          if (!selectedDataset.demo_asset_id || !selectedDemo) throw new Error("This ready clip does not have verified local video bytes available.");
          if (!selectedSegment) throw new Error("Choose a valid video segment before starting the assessment.");
          created = await api.assessDemoClip(selectedDataset.demo_asset_id, executor, profile, selectedSegment);
        } else if (selectedDataset.status === "cataloged") {
          if (!selectedSegment) throw new Error("Choose a valid video segment before starting the assessment.");
          created = await api.assessCatalogClip(selectedDataset.id, executor, profile, selectedSegment);
        } else {
          throw new Error(`This ${selectedDataset.status.replaceAll("_", " ")} reference is not eligible for clip assessment.`);
        }
      }
      const completedJob = await settleAssessmentJob(created, setAssessmentJob);
      if (completedJob.status === "failed") throw new Error(completedJob.message || "The assessment job failed.");
      if (!completedJob.assessment_id) throw new Error("The completed assessment job did not return an assessment ID.");
      const completed = await api.clipAssessment(completedJob.assessment_id);
      setAssessment(completed); setSelectedCandidateId(null); setSelectedBird(null); await refreshAssessments();
      void api.proxySpecimens().then(setProxyPoolSummary).catch(() => {
        // Preserve the current inventory or assessment-derived fallback on older backends.
      });
      if (completed.status === "failed") setError("The assessment was stored but did not complete. Review its status and server logs.");
    } catch (requestError) {
      setAssessmentApiError(requestError instanceof Error ? requestError.message : "The clip assessment could not be started.");
    } finally { setAssessmentJob(null); setProcessing(false); }
  }

  function selectAssessment(next: ClipAssessment) {
    setAssessment(next);
    setSelectedCandidateId(null);
    setSelectedBird(null);
  }

  function selectSourceMode(nextMode: "library" | "upload") {
    setSourceMode(nextMode);
    setAssessment(null);
    setSelectedBird(null);
    const duration = nextMode === "upload" ? uploadDuration : selectedDataset?.duration_s;
    setSegmentStart(0);
    setSegmentEnd(defaultSegmentEnd(duration));
  }

  function selectDataset(nextId: string) {
    setSelectedDatasetId(nextId);
    setAssessment(null);
    setSelectedBird(null);
    const duration = datasetClips.find((clip) => clip.id === nextId)?.duration_s;
    setSegmentStart(0);
    setSegmentEnd(defaultSegmentEnd(duration));
  }

  function selectUpload(file: File | null) {
    setUploadFile(file);
    setAssessment(null);
    setSelectedBird(null);
    setUploadDuration(null);
    setSegmentStart(0);
    setSegmentEnd(DEFAULT_SEGMENT_SECONDS);
  }

  function learnUploadDuration(duration: number) {
    if (!Number.isFinite(duration) || duration <= 0) return;
    setUploadDuration(duration);
    setSegmentStart(0);
    setSegmentEnd(defaultSegmentEnd(duration));
  }

  function selectCandidate(candidateId: string) {
    setSelectedCandidateId(candidateId);
    setSelectedBird(null);
  }

  function selectBird(annotation: VideoAnnotation) {
    setSelectedBird(annotation);
    setSelectedCandidateId(null);
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
    {error ? <div className="error-banner" role="alert"><strong>Request failed.</strong> {error}</div> : null}

    <main className="clip-workspace">
      <aside className="panel source-panel" aria-labelledby="source-title">
        <div className="panel-heading"><div><span className="eyebrow">Step 01</span><h2 id="source-title">Choose a whole-pen clip</h2></div><span className="index-label">VIDEO</span></div>
        <div className="source-tabs" role="tablist" aria-label="Video source">
          <button role="tab" aria-selected={sourceMode === "library"} className={sourceMode === "library" ? "source-tab source-tab--active" : "source-tab"} onClick={() => selectSourceMode("library")}>Dataset library</button>
          <button role="tab" aria-selected={sourceMode === "upload"} className={sourceMode === "upload" ? "source-tab source-tab--active" : "source-tab"} onClick={() => selectSourceMode("upload")}>Upload video</button>
        </div>
        <div className="profile-picker" role="group" aria-label="Demo profile">
          <span className="profile-picker__label">Demo profile</span>
          <div className="profile-picker__options">
            {PROFILE_OPTIONS.map((option) => (
              <button key={option.value} type="button" aria-pressed={profile === option.value} className={profile === option.value ? "profile-option profile-option--active" : "profile-option"} onClick={() => setProfile(option.value)}>{option.label}</button>
            ))}
          </div>
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
            <p>{selectedDataset.duration_s == null ? "Duration unknown" : formatTime(selectedDataset.duration_s)} · {selectedDataset.fps ?? "?"} FPS{selectedDataset.installed_size_bytes != null ? ` · ${formatBytes(selectedDataset.installed_size_bytes)} installed` : ""}</p>
            <div className="dataset-links"><a href={selectedDataset.source_url} target="_blank" rel="noreferrer">Source clip</a><a href={selectedDataset.dataset_url} target="_blank" rel="noreferrer">Dataset</a>{selectedDataset.doi ? <a href={`https://doi.org/${selectedDataset.doi}`} target="_blank" rel="noreferrer">DOI</a> : null}</div>
            {!assessmentAllowed ? <p className="dataset-disabled">{selectedDataset.status === "rejected" ? "Rejected during camera review; retained for provenance." : "Reference only; not assessable."}</p> : selectedDataset.status === "ready" && !selectedDemo ? <p className="dataset-disabled">{selectedDataset.bytes_available ? <>Demo asset not hash-verified. Run <code>make demo-assets</code> before assessment.</> : <>Verified video bytes not installed. Run <code>make demo-assets</code> before assessment.</>}</p> : null}
          </article> : <p className="source-guidance">No reviewed dataset clips were returned by the API.</p>}
        </div> : <div className="source-content upload-clip-content source-controls">
          <label className="clip-dropzone"><span>Whole-pen video</span><strong>{uploadFile?.name ?? "Choose an MP4, MOV, or WebM file"}</strong><input type="file" accept="video/mp4,video/quicktime,video/webm,video/*" onChange={(event) => selectUpload(event.target.files?.[0] ?? null)} /></label>
        </div>}
        <div className="segment-picker" aria-label="Assessment segment">
          <div className="segment-picker__heading"><strong>Video segment</strong><span>{sourceDuration == null ? "Load video metadata to choose a segment" : `${formatTime(sourceDuration)} source · ${segmentValid ? formatTime(segmentEnd - segmentStart) : "invalid range"} selected`}</span></div>
          <div className="segment-picker__fields">
            <label>Start (seconds)<input type="number" min="0" max={sourceDuration ?? undefined} step="0.1" value={segmentStart} disabled={sourceDuration == null} onChange={(event) => setSegmentStart(Number(event.target.value))} /></label>
            <label>End (seconds)<input type="number" min="0.001" max={sourceDuration ?? undefined} step="0.1" value={segmentEnd} disabled={sourceDuration == null} onChange={(event) => setSegmentEnd(Number(event.target.value))} /></label>
          </div>
        </div>
        <div className="assessment-action">
          <fieldset className="executor-picker">
            <legend className="executor-picker__legend">Run assessment on</legend>
            <div className="executor-picker__options">
              {EXECUTOR_OPTIONS.map((option) => (
                <label key={option.value} className={executor === option.value ? "executor-option executor-option--active" : "executor-option"}>
                  <input type="radio" name="assessment-executor" value={option.value} checked={executor === option.value} disabled={loading || processing} onChange={() => setExecutor(option.value)} />
                  <span><strong>{option.label}</strong></span>
                </label>
              ))}
            </div>
            {executor === "qnx" ? <p className={qnxBlocked ? "executor-note executor-note--blocked" : "executor-note"}>
              {qnxBlocked
                ? `QNX target: ${qnx?.status?.replaceAll("_", " ") ?? "unavailable"}. No local fallback.`
                : qnx?.status === "probe_only"
                  ? "QNX target: probe-only, readiness not established. No local fallback."
                  : "No local fallback."}
            </p> : null}
          </fieldset>
          <button className="primary-button" onClick={handleAssess} disabled={processing || loading || qnxBlocked || !segmentValid || (sourceMode === "library" ? !assessmentAllowed || (selectedDataset?.status === "ready" && !selectedDemo) : !uploadFile)}>{processing ? "Assessing clip…" : sourceMode === "upload" ? "Upload & assess clip" : selectedDataset?.status === "cataloged" ? selectedDataset.bytes_available ? "Assess installed clip" : "Generate deterministic example" : selectedDataset?.status === "ready" ? "Assess installed clip" : "Unavailable for assessment"}</button>
          {assessmentJob ? <div className="assessment-progress" aria-live="polite">
            <div className="assessment-progress__heading"><strong>{assessmentJob.stage.replaceAll("_", " ")}</strong><span>{Math.round(Math.max(0, Math.min(100, assessmentJob.progress_percent)))}%</span></div>
            <div className="assessment-progress__track" role="progressbar" aria-label="Clip assessment progress" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.max(0, Math.min(100, assessmentJob.progress_percent))} aria-valuetext={`${Math.round(Math.max(0, Math.min(100, assessmentJob.progress_percent)))} percent — ${assessmentJob.stage}`}>
              <span style={{ width: `${Math.max(0, Math.min(100, assessmentJob.progress_percent))}%` }} />
            </div>
            <p>{assessmentJob.message}</p>
          </div> : null}
          {assessmentJob ? <div className="assessment-run">
            <TargetBadge job={assessmentJob} />
            <JobTelemetry job={assessmentJob} />
          </div> : null}
        </div>
        {assessmentApiError ? <div className="wiring-error" role="alert"><strong>Clip assessment error</strong><span>{assessmentApiError}</span></div> : null}
      </aside>

      <section className="panel viewer-panel" aria-labelledby="viewer-title">
        <div className="panel-heading"><div><span className="eyebrow">Clip viewer</span><h2 id="viewer-title">Whole-pen observation window</h2></div><span className="index-label">{assessment ? `ASSESSED · ${assessment.id.slice(0, 8)}` : sourceMode === "library" ? selectedDataset?.status.replaceAll("_", " ") ?? "LIBRARY" : "UPLOAD"}</span></div>
        {assessment ? <AssessmentVideoViewport assessment={assessment} selectedCandidateId={selectedCandidateId} selectedBirdId={selectedBird?.id ?? null} onSelectCandidate={selectCandidate} onSelectBird={selectBird} />
          : sourceMode === "library"
          ? selectedDataset?.bytes_available && selectedDataset.content_url ? <DatasetClipPreview clip={selectedDataset} />
            : selectedDemo ? <MediaViewport assets={[selectedDemo]} /> : <div className="viewer-empty viewer-empty--catalog"><span aria-hidden="true">{selectedDataset?.status === "cataloged" ? "MOCK" : "—"}</span><strong>{selectedDataset?.status === "cataloged" ? "No local video bytes" : "Playback unavailable"}</strong><p>{selectedDataset?.status === "cataloged" ? "Generate a persisted deterministic example from this catalog entry." : selectedDataset?.status === "ready" ? "Not installed locally. Run make demo-assets before assessment." : "Retained for provenance; not assessable."}</p>{selectedDataset ? <div className="viewer-source-links"><a href={selectedDataset.source_url} target="_blank" rel="noreferrer">Open source</a><a href={selectedDataset.dataset_url} target="_blank" rel="noreferrer">Open dataset</a></div> : null}</div>
          : uploadPreview ? <div className="upload-preview-wrap"><video className="upload-preview" src={uploadPreview} controls preload="metadata" onLoadedMetadata={(event) => learnUploadDuration(event.currentTarget.duration)}>Your browser cannot preview this video.</video></div> : <div className="viewer-empty"><span aria-hidden="true">▶</span><strong>Select a whole-pen video</strong></div>}
        {assessment && selectedBird ? <BirdObservationCard annotation={selectedBird} onDismiss={() => setSelectedBird(null)} /> : null}
      </section>

      <section className="panel pipeline-panel" aria-labelledby="pipeline-title">
        <div className="panel-heading"><div><span className="eyebrow">Step 02</span><h2 id="pipeline-title">Assessment pipeline</h2></div><span className="index-label">4 STAGES</span></div>
        <ol className="pipeline-list">{STAGES.map((stage, index) => {
          const module = assessment ? moduleFor(stage.id, assessment.modules) : undefined;
          return <li key={stage.id} className="pipeline-stage"><span className="stage-number">{String(index + 1).padStart(2, "0")}</span><div><strong>{stage.label}</strong></div><StageProvenance module={module} /></li>;
        })}</ol>
      </section>

      <section className="panel results-panel" aria-labelledby="results-title">
        <div className="panel-heading"><div><span className="eyebrow">Step 03</span><h2 id="results-title">Aggregate clip summary</h2></div>{assessment ? <span className={`status-pill status-pill--${assessment.status}`}>{assessment.status}</span> : <span className="index-label">AWAITING CLIP</span>}</div>
        {!assessment ? <div className="results-empty results-empty--compact"><span aria-hidden="true">◎</span><strong>No result yet</strong><p>Assess the selected whole-pen clip to populate this summary.</p></div> : <div className="assessment-results aggregate-results">
          <div className="score-grid">
            <ScoreCard label="Activity / energy" score={assessment.summary.activity.score} category={assessment.summary.activity.category} detail={`${Math.round(assessment.summary.activity.motion_coverage * 100)}% motion coverage`} />
            <ScoreCard label="Flock appearance" score={assessment.summary.appearance.score} category={assessment.summary.appearance.category} detail="" />
            <article className="score-card score-card--count"><span>Feces candidates</span><div><strong>{assessment.summary.feces.candidate_count}</strong></div><b>regions for review</b></article>
          </div>
          <ActivityEvidenceSection assessment={assessment} />
          <section className="aggregate-distribution" aria-labelledby="distribution-title"><div className="subheading"><div><span className="eyebrow">Classifier output</span><h3 id="distribution-title">Candidate distribution</h3></div><ModeBadge mode={moduleFor("feces_classifier", assessment.modules)?.mode} compact /></div><div className="distribution-list">
            {Object.entries(assessment.summary.feces.class_distribution).map(([label, value]) => <div className="distribution-row" key={label}><span>{label}</span><div><i style={{ width: `${distributionPercent(value, assessment.summary.feces.class_distribution)}%` }} /></div><strong>{value}</strong></div>)}
          </div></section>
          <div className="overall-review"><div><span className="eyebrow">Overall review state</span><strong>{assessment.summary.overall.review_state.replaceAll("_", " ")}</strong></div></div>
          <PenAssessment assessment={assessment} />
          <p className="non-diagnostic"><strong>Non-diagnostic</strong></p>
        </div>}
      </section>

      <section className="panel review-panel" aria-labelledby="review-title">
        <div className="panel-heading"><div><span className="eyebrow">Clip review</span><h2 id="review-title">Evidence & candidate rows</h2></div>{assessment ? <span className="index-label">{assessment.summary.feces.candidates.length} CANDIDATES</span> : <span className="index-label">NO RESULT</span>}</div>
        {!assessment ? <><SpecimenPoolSummary summary={proxyPoolSummary} assessment={null} /><div className="results-empty"><span aria-hidden="true">⌁</span><strong>Evidence will appear here</strong><p>Run the selected video to review zone movement and feces candidates.</p></div></> : <div className="assessment-results">
          <div className="assessment-provenance"><div><strong>{assessment.video.name}</strong><span>{formatBytes(assessment.video.size_bytes)} · source {assessment.video.duration_s == null ? "duration unknown" : formatTime(assessment.video.duration_s)} · segment {formatTime(assessment.video.segment_start_s ?? 0)} to {assessment.video.segment_end_s == null ? "end unknown" : formatTime(assessment.video.segment_end_s)}{assessment.video.segment_end_s == null ? "" : ` (${formatTime(assessment.video.segment_end_s - (assessment.video.segment_start_s ?? 0))})`} · {assessment.video.width ?? "?"}×{assessment.video.height ?? "?"} · {assessment.video.fps ?? "?"} FPS</span></div><code title={assessment.video.sha256}>#{assessment.id.slice(0, 12)} · sha256 {assessment.video.sha256.slice(0, 12)}… · {formatDate(assessment.created_at)}</code></div>
          <section className="review-zones" aria-labelledby="zones-title"><div className="subheading"><div><span className="eyebrow">Spatial context</span><h3 id="zones-title">Activity by pen zone</h3></div><ModeBadge mode={moduleFor("activity", assessment.modules)?.mode} /></div><dl className="zone-list">{Object.entries(assessment.summary.activity.zone_scores).map(([zone, value]) => <div key={zone}><dt>{zone.replaceAll("_", " ")}</dt><dd>{Math.round(scorePercent(value))}</dd></div>)}</dl></section>
          <SpecimenPoolSummary summary={proxyPoolSummary} assessment={assessment} />
          <section className="candidate-section" aria-labelledby="candidate-title"><div className="subheading"><div><span className="eyebrow">Review queue</span><h3 id="candidate-title">Feces candidate rows</h3></div><span>{assessment.summary.feces.candidates.length} shown</span></div><div className="candidate-table-wrap"><table className="candidate-table"><thead><tr><th>Candidate</th><th>Time</th><th>Location</th><th>Source</th><th>Model output</th><th>Confidence</th><th>Mode</th></tr></thead><tbody>{assessment.summary.feces.candidates.map((candidate) => <tr key={candidate.id} role="button" tabIndex={0} aria-pressed={selectedCandidateId === candidate.id} className={selectedCandidateId === candidate.id ? "candidate-row candidate-row--active" : "candidate-row"} onClick={() => selectCandidate(candidate.id)} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); selectCandidate(candidate.id); } }}><td><code>{candidate.id}</code></td><td>{formatTime(candidate.timestamp_s)}</td><td><code>{candidate.bbox.x.toFixed(2)}, {candidate.bbox.y.toFixed(2)} · {candidate.bbox.width.toFixed(2)}×{candidate.bbox.height.toFixed(2)}</code></td><td className="candidate-source">{locationSourceShortLabel(candidate)}</td><td>{candidate.classification.label ?? "—"}</td><td>{Math.round(candidate.classification.confidence * 100)}%</td><td><ModeBadge mode={candidate.classification.mode} compact /></td></tr>)}</tbody></table></div>{selectedCandidate ? <CandidateEvidence candidate={selectedCandidate} detectorModule={moduleFor("feces_candidates", assessment.modules)} classifierModule={moduleFor("feces_classifier", assessment.modules)} annotations={assessmentAnnotationsList} /> : <p className="candidate-evidence-empty">Select a candidate row to inspect its evidence and seek the video to its timestamp.</p>}</section>
        </div>}
      </section>

      <section className="panel history-strip" aria-labelledby="history-title"><div className="panel-heading"><div><span className="eyebrow">Saved evidence</span><h2 id="history-title">Recent clip assessments</h2></div><span className="index-label">{assessments.length}</span></div>{assessments.length ? <div className="assessment-history">{assessments.map((item) => <button key={item.id} className={assessment?.id === item.id ? "assessment-history-card assessment-history-card--active" : "assessment-history-card"} aria-current={assessment?.id === item.id ? "true" : undefined} onClick={() => selectAssessment(item)}><strong>{item.video.name}</strong><span>{formatDate(item.created_at)} · {item.status}</span><small>{Math.round(scorePercent(item.summary.activity.score))} activity · {item.summary.feces.candidate_count} feces candidates</small></button>)}</div> : <p className="empty-copy">No persisted clip assessments yet.</p>}</section>

      <details className="panel runtime-panel"><summary><span><span className="eyebrow">Advanced</span><strong>Model artifacts, QNX target & synthetic engine</strong></span><small>Open runtime controls</small></summary><div className="runtime-content">
        <section><h3>QNX target validation</h3><div className="runtime-actions"><button className="secondary-button" onClick={handleTargetCheck} disabled={runtimePending}>{runtimePending ? "Working…" : "Check target"}</button></div><div className="runtime-grid"><label>Model artifact<select value={modelId} onChange={(event) => setModelId(event.target.value)}>{models.map((model) => <option key={model.id} value={model.id}>{model.name} / {model.version}</option>)}</select></label><label>Synthetic scenario<select value={scenarioId} onChange={(event) => setScenarioId(event.target.value)}>{scenarios.map((scenario) => <option key={scenario.id} value={scenario.id}>{scenario.name}</option>)}</select></label></div>{modelBlockedForQnx ? <p className="blocked-copy">Choose a real, non-empty model artifact.</p> : null}<button className="primary-button" onClick={handleQnxValidation} disabled={runtimePending || !qnxEnabled || modelBlockedForQnx || !scenarioId}>{qnx?.status === "probe_only" ? "Validate artifact on QNX" : "Run on QNX"}</button></section>
        <section><h3>Add a model artifact</h3><form className="runtime-upload" onSubmit={handleModelUpload}><label>Name<input name="name" required placeholder="Feces classifier" /></label><label>Version<input name="version" required placeholder="0.1.0" /></label><label>Source<input name="source" placeholder="Veri / Kaggle chicken-disease-1" /></label><label>Artifact<input name="artifact" type="file" required /></label><button className="secondary-button" disabled={modelUploadPending}>{modelUploadPending ? "Uploading…" : "Upload to catalog"}</button></form></section>
      </div>{runtimeMessage ? <p className="runtime-message" role="status">{runtimeMessage}</p> : null}</details>
      <QnxEvidencePanel evidence={qnxEvidence} error={qnxEvidenceError} />
    </main>
    <HelpDrawer open={helpOpen} onClose={closeHelp} />
  </div>;
}
