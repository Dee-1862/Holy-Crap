import type { ClipAssessmentModule, FecesCandidate, ProxySpecimenReference, VideoAnnotation } from "../types";
import {
  appearanceInput,
  classificationSource,
  classifierModelLabel,
  classifierScoreReadout,
  cropContentUrl,
  cropDimensions,
  cropIsPrimaryEvidence,
  cropMaterialized,
  cropSha256,
  cropSource,
  detectorArtifactId,
  detectorModelId,
  detectorRuntime,
  detectorSource,
  droppingPersistence,
  fallbackReasonLabel,
  inputHashLabel,
  locationSourceLabel,
  moduleArtifactId,
  moduleModelId,
  moduleRuntime,
  scorePercent,
  totalDroppingSampleFrames,
} from "../evidence";
import { ModeBadge } from "./ModeBadge";

interface CandidateEvidenceProps {
  candidate: FecesCandidate;
  detectorModule?: ClipAssessmentModule;
  classifierModule?: ClipAssessmentModule;
  annotations?: VideoAnnotation[] | null;
}

function proxyFor(candidate: FecesCandidate): ProxySpecimenReference | null {
  return candidate.proxy_specimen ?? candidate.proxy ?? candidate.proxy_crop ?? null;
}

function illustrativeProxyFor(candidate: FecesCandidate): ProxySpecimenReference | null {
  return candidate.proxy_crop ?? candidate.proxy ?? candidate.proxy_specimen ?? null;
}

function proxyId(proxy: ProxySpecimenReference): string {
  return proxy.id ?? proxy.asset_id ?? proxy.sample_id ?? "proxy specimen";
}

function proxyExpectedLabel(proxy: ProxySpecimenReference): string | null {
  const value = proxy.expected_label ?? proxy.expected_demo_class;
  return typeof value === "string" && value.trim() ? value : null;
}

function proxySource(proxy: ProxySpecimenReference): string | null {
  const value = proxy.source ?? proxy.source_dataset;
  return typeof value === "string" && value.trim() ? value : null;
}

function formatTime(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  return `${minutes}:${Math.round(seconds % 60).toString().padStart(2, "0")}`;
}

function appearanceInputLabel(candidate: FecesCandidate): string {
  const input = appearanceInput(candidate);
  if (input === "curated_proxy") return "Curated proxy specimen";
  if (input === "observed_crop") return "Observed crop";
  return "Not reported";
}

function classificationSourceLabel(candidate: FecesCandidate): string {
  const source = classificationSource(candidate);
  if (source === "live_model_run") return "Live model run";
  if (source === "deterministic_mock") return "Deterministic mock";
  return "Source not reported";
}

function ObservedCropCard({ candidate, isModelInput }: { candidate: FecesCandidate; isModelInput: boolean }) {
  const cropUrl = cropContentUrl(candidate);
  const cropHash = cropSha256(candidate);
  const dimensions = cropDimensions(candidate);
  const source = cropSource(candidate);
  const materialized = cropMaterialized(candidate);
  return (
    <article className="evidence-card evidence-card--observed">
      <span className="evidence-card__label">Observed crop — {isModelInput ? "classifier input" : "detector evidence"}</span>
      {cropUrl ? (
        <figure className="proxy-figure">
          <div className="proxy-image-wrap">
            <img
              src={cropUrl}
              alt={`Observed feces crop for ${candidate.id}${isModelInput ? ", classifier input" : ""}`}
              loading="lazy"
            />
            <span className="observed-input-label">OBSERVED CROP{isModelInput ? " · MODEL INPUT" : " · DETECTOR EVIDENCE"}</span>
          </div>
          <figcaption>
            <dl className="evidence-detail-list">
              {cropHash ? <div><dt>Crop sha256</dt><dd><code>{cropHash}</code></dd></div> : null}
              {dimensions.width !== null || dimensions.height !== null ? <div><dt>Dimensions</dt><dd>{dimensions.width ?? "?"}×{dimensions.height ?? "?"}</dd></div> : null}
              {source ? <div><dt>Source</dt><dd>{source}</dd></div> : null}
            </dl>
          </figcaption>
        </figure>
      ) : (
        <div className="proxy-unavailable" role="status">
          <strong>Crop preview unavailable</strong>
          <span>{materialized ? "Crop materialized; no preview URL returned." : "Observed crop; no preview URL returned."}</span>
        </div>
      )}
    </article>
  );
}

function IllustrativeReferenceCard({ candidate, proxy }: { candidate: FecesCandidate; proxy: ProxySpecimenReference }) {
  return (
    <article className="evidence-card evidence-card--illustrative">
      <span className="evidence-card__label">Illustrative reference — close-up</span>
      {proxy.content_url && proxy.bytes_available !== false ? (
        <figure className="proxy-figure">
          <div className="proxy-image-wrap">
            <img
              src={proxy.content_url}
              alt={`Curated close-up photo for ${candidate.id}. Not the detected dropping or model input.`}
              loading="lazy"
            />
            <span className="illustrative-input-label">ILLUSTRATIVE REFERENCE · NOT MODEL INPUT</span>
          </div>
          <figcaption>
            <dl className="evidence-detail-list">
              <div><dt>Specimen</dt><dd><code>{proxyId(proxy)}</code></dd></div>
              {proxyExpectedLabel(proxy) ? <div><dt>Expected demo class (dataset label)</dt><dd className="reference-class">{proxyExpectedLabel(proxy)}</dd></div> : null}
              {proxySource(proxy) ? <div><dt>Source dataset</dt><dd>{proxySource(proxy)}</dd></div> : null}
              {proxy.attribution ? <div><dt>Attribution</dt><dd>{proxy.attribution}</dd></div> : null}
            </dl>
          </figcaption>
        </figure>
      ) : (
        <div className="proxy-unavailable" role="status">
          <strong>Illustrative close-up unavailable</strong>
          <span>Specimen <code>{proxyId(proxy)}</code> has no verified image URL.</span>
        </div>
      )}
    </article>
  );
}

function SimulatedInputCard({ candidate, proxy }: { candidate: FecesCandidate; proxy: ProxySpecimenReference }) {
  return (
    <article className="evidence-card">
      <span className="evidence-card__label">Simulated input — proxy specimen</span>
      {proxy.content_url && proxy.bytes_available !== false ? (
        <figure className="proxy-figure">
          <div className="proxy-image-wrap">
            <img
              src={proxy.content_url}
              alt={`Curated proxy specimen photo used as simulated input for ${candidate.id}. Not from the assessed video.`}
              loading="lazy"
            />
            <span className="simulated-input-label">SIMULATED INPUT</span>
          </div>
          <figcaption>
            <dl className="evidence-detail-list">
              <div><dt>Specimen</dt><dd><code>{proxyId(proxy)}</code></dd></div>
              {proxyExpectedLabel(proxy) ? <div><dt>Expected demo class (dataset label)</dt><dd className="reference-class">{proxyExpectedLabel(proxy)}</dd></div> : null}
              {proxySource(proxy) ? <div><dt>Source dataset</dt><dd>{proxySource(proxy)}</dd></div> : null}
              {proxy.attribution ? <div><dt>Attribution</dt><dd>{proxy.attribution}</dd></div> : null}
            </dl>
            {proxy.substitution_reason ? <p className="proxy-note"><strong>Why a proxy:</strong> {proxy.substitution_reason}</p> : null}
          </figcaption>
        </figure>
      ) : (
        <div className="proxy-unavailable" role="status">
          <strong>Proxy image bytes unavailable</strong>
          <span>Specimen <code>{proxyId(proxy)}</code> has no verified image URL.</span>
        </div>
      )}
    </article>
  );
}

function ExplainabilityCard({ candidate, annotations, modelLabel, inputLabel }: { candidate: FecesCandidate; annotations: VideoAnnotation[]; modelLabel: string | null; inputLabel: string }) {
  const classification = candidate.classification;
  const readout = classifierScoreReadout(candidate);
  const persistence = droppingPersistence(candidate, annotations);
  const totalSampleFrames = totalDroppingSampleFrames(annotations);
  const detection = candidate.detection_confidence;
  return (
    <article className="evidence-card evidence-card--explainability">
      <span className="evidence-card__label">Explainability — returned facts only</span>
      <dl className="evidence-detail-list evidence-detail-list--explain">
        <div>
          <dt>Detector confidence</dt>
          <dd>{typeof detection === "number" ? `${Math.round(scorePercent(detection))}%` : "Not reported"}</dd>
        </div>
        <div>
          <dt>Persistence</dt>
          <dd>
            {persistence
              ? `${persistence.observations} observation${persistence.observations === 1 ? "" : "s"} across ${persistence.sampleFrames} sampled frame${persistence.sampleFrames === 1 ? "" : "s"}${totalSampleFrames > 0 ? ` of ${totalSampleFrames} dropping sample frame${totalSampleFrames === 1 ? "" : "s"} returned` : ""}`
              : "No sampled-frame observations were returned for this candidate."}
          </dd>
        </div>
        <div>
          <dt>Top classifier score</dt>
          <dd>{readout.top ? `${readout.top[0].replaceAll("_", " ")} · ${Math.round(scorePercent(readout.top[1]))}%` : "No scores returned"}</dd>
        </div>
        <div>
          <dt>Runner-up</dt>
          <dd>{readout.runnerUp ? `${readout.runnerUp[0].replaceAll("_", " ")} · ${Math.round(scorePercent(readout.runnerUp[1]))}%` : "Not reported"}</dd>
        </div>
        <div>
          <dt>Margin</dt>
          <dd>{readout.margin === null ? "Not reported" : `${Math.round(scorePercent(readout.margin))} points`}</dd>
        </div>
        <div>
          <dt>Model / runtime</dt>
          <dd>{modelLabel ?? "Not reported by this assessment"}</dd>
        </div>
        <div>
          <dt>Input provenance</dt>
          <dd>{inputLabel}</dd>
        </div>
      </dl>
      {readout.entries.length ? (
        <div className="explainability-scores" aria-label="Classifier score distribution for this candidate">
          {readout.entries.map(([label, value]) => (
            <div className="distribution-row" key={label}>
              <span>{label.replaceAll("_", " ")}</span>
              <div><i style={{ width: `${Math.max(0, Math.min(100, scorePercent(value)))}%` }} /></div>
              <strong>{Math.round(scorePercent(value))}%</strong>
            </div>
          ))}
        </div>
      ) : null}
      {classification.label === null ? (
        <p className="explainability-note">
          <strong>No label assigned.</strong>{" "}
          {readout.entries.length
            ? "No class passed the configured threshold."
            : "No classifier label returned for this candidate."}
        </p>
      ) : null}
    </article>
  );
}

export function CandidateEvidence({ candidate, detectorModule, classifierModule, annotations }: CandidateEvidenceProps) {
  const proxy = proxyFor(candidate);
  const illustrative = illustrativeProxyFor(candidate);
  const appearance = appearanceInput(candidate);
  const observedCropAvailable = cropIsPrimaryEvidence(candidate);
  const observedCropIsInput = appearance === "observed_crop";
  const classification = candidate.classification;
  const confidencePercent = Math.round(classification.confidence * 100);
  const detection = candidate.detection_confidence;
  const classifierModuleModel = moduleModelId(classifierModule);
  const classifierModuleArtifact = moduleArtifactId(classifierModule);
  const classifierModuleRuntime = moduleRuntime(classifierModule);
  const classifierModuleLabel = [
    classifierModuleModel,
    classifierModuleArtifact && classifierModuleArtifact !== classifierModuleModel ? `artifact ${classifierModuleArtifact}` : null,
    classifierModuleRuntime ? `runtime ${classifierModuleRuntime}` : null,
  ].filter((part): part is string => part !== null).join(" · ");
  const model = (classifierModelLabel(candidate) ?? classifierModuleLabel) || null;
  const fallbackReason = fallbackReasonLabel(classification.fallback_reason);
  const inputHash = inputHashLabel(candidate);
  const detectorModel = detectorModelId(candidate) ?? moduleModelId(detectorModule);
  const detectorArtifact = detectorArtifactId(candidate) ?? moduleArtifactId(detectorModule);
  const detectorRuntimeValue = detectorRuntime(candidate) ?? moduleRuntime(detectorModule);
  const detectorSourceValue = detectorSource(candidate);
  const showIllustrative = illustrative != null && appearance !== "curated_proxy";

  return (
    <section className="candidate-evidence" aria-labelledby="candidate-evidence-title">
      <div className="subheading">
        <div>
          <span className="eyebrow">Selected candidate</span>
          <h3 id="candidate-evidence-title">Evidence for {candidate.id}</h3>
        </div>
        <ModeBadge mode={classification.mode} />
      </div>
      <div className="candidate-evidence-grid">
        <article className="evidence-card">
          <span className="evidence-card__label">Detected location</span>
          <dl className="evidence-detail-list">
            <div><dt>Timestamp</dt><dd>{formatTime(candidate.timestamp_s)} ({candidate.timestamp_s.toFixed(3)} s)</dd></div>
            <div><dt>Normalized bbox</dt><dd><code>x {candidate.bbox.x.toFixed(3)} · y {candidate.bbox.y.toFixed(3)} · {candidate.bbox.width.toFixed(3)}×{candidate.bbox.height.toFixed(3)}</code></dd></div>
            <div><dt>Detection confidence</dt><dd>{typeof detection === "number" ? `${Math.round(detection * 100)}%` : "Not reported"}</dd></div>
            {detectorModel ? <div><dt>Detector model</dt><dd><code>{detectorModel}{detectorArtifact && detectorArtifact !== detectorModel ? ` · artifact ${detectorArtifact}` : ""}</code></dd></div> : null}
            {detectorRuntimeValue ? <div><dt>Detector runtime</dt><dd><code>{detectorRuntimeValue}</code></dd></div> : null}
            {detectorSourceValue ? <div><dt>Detector source</dt><dd>{detectorSourceValue}</dd></div> : null}
            <div><dt>Location source</dt><dd>{locationSourceLabel(candidate)}</dd></div>
          </dl>
        </article>
        {observedCropAvailable ? <ObservedCropCard candidate={candidate} isModelInput={observedCropIsInput} /> : null}
        {appearance === "curated_proxy" && proxy ? <SimulatedInputCard candidate={candidate} proxy={proxy} /> : null}
        {!observedCropAvailable && appearance !== "curated_proxy" && !showIllustrative ? (
          <article className="evidence-card">
            <span className="evidence-card__label">Appearance input</span>
            <div className="proxy-unavailable" role="status">
              <strong>No appearance input reported</strong>
              <span>Neither an observed crop nor a curated proxy specimen for {candidate.id}.</span>
            </div>
          </article>
        ) : null}
        {showIllustrative ? <IllustrativeReferenceCard candidate={candidate} proxy={illustrative} /> : null}
      </div>
      <article className="evidence-card evidence-card--model-output">
        <span className="evidence-card__label">Model output</span>
        <dl className="evidence-detail-list">
          <div><dt>Label</dt><dd>{classification.label ?? "No label reported"}</dd></div>
          <div><dt>Confidence</dt><dd>{confidencePercent}%</dd></div>
          <div><dt>Mode</dt><dd>{classification.mode === "real" ? "Real model run" : classification.mode === "partial" ? "Partial model run" : "Deterministic mock"}</dd></div>
          {model ? <div><dt>Model / runtime</dt><dd>{model}</dd></div> : null}
          <div><dt>Inference performed</dt><dd>{classification.inference_performed === true ? "Yes — reported by the model adapter" : classification.inference_performed === false ? "No — reported by the adapter" : "Not reported by this assessment"}</dd></div>
          {inputHash ? <div><dt>Input sha256</dt><dd><code>{inputHash}</code></dd></div> : null}
          {fallbackReason ? <div><dt>Fallback reason</dt><dd>{fallbackReason}</dd></div> : null}
        </dl>
        <p className="evidence-card__note">Input: {appearanceInputLabel(candidate)} · {classificationSourceLabel(candidate)}</p>
      </article>
      <ExplainabilityCard
        candidate={candidate}
        annotations={annotations ?? []}
        modelLabel={model}
        inputLabel={appearanceInputLabel(candidate)}
      />
    </section>
  );
}
