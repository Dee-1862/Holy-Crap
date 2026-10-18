import type { FecesCandidate, ProxySpecimenReference } from "../types";

interface CandidateEvidenceProps {
  candidate: FecesCandidate;
}

function proxyFor(candidate: FecesCandidate): ProxySpecimenReference | null {
  return candidate.proxy_specimen ?? candidate.proxy ?? candidate.proxy_crop ?? null;
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

function locationSourceLabel(candidate: FecesCandidate): string {
  const source = candidate.provenance?.location_source;
  if (source === "observed_video") return "Observed in the assessed whole-pen video.";
  if (source === "deterministic_overlay") return "Deterministic overlay position; not observed in footage.";
  return "Location source not reported by this assessment.";
}

function appearanceInputLabel(candidate: FecesCandidate): string {
  const input = candidate.provenance?.appearance_input;
  if (input === "curated_proxy") return "Curated proxy specimen (never an observed crop).";
  if (input === "observed_crop") return "Crop observed in the assessed video.";
  return "Appearance input not reported by this assessment.";
}

function modelLabel(candidate: FecesCandidate): string | null {
  const model = candidate.classification.model;
  if (!model) return null;
  const parts = [model.id ?? null, model.version ?? null].filter((part): part is string => part !== null);
  if (!parts.length && !model.runtime) return null;
  return [parts.join(" "), model.runtime ? `runtime ${model.runtime}` : null]
    .filter((part): part is string => part !== null)
    .join(" · ");
}

function fallbackReasonLabel(reason: FecesCandidate["classification"]["fallback_reason"]): string | null {
  if (!reason) return null;
  return {
    specimen_unavailable: "Specimen bytes unavailable",
    runtime_unavailable: "Model runtime unavailable",
    image_decode_failed: "Image decode failed",
    model_inference_failed: "Model inference failed",
  }[reason];
}

export function CandidateEvidence({ candidate }: CandidateEvidenceProps) {
  const proxy = proxyFor(candidate);
  const expectedLabel = proxy ? proxyExpectedLabel(proxy) : null;
  const classification = candidate.classification;
  const confidencePercent = Math.round(classification.confidence * 100);
  const detection = candidate.detection_confidence;
  const model = modelLabel(candidate);
  const fallbackReason = fallbackReasonLabel(classification.fallback_reason);

  return (
    <section className="candidate-evidence" aria-labelledby="candidate-evidence-title">
      <div className="subheading">
        <div>
          <span className="eyebrow">Selected candidate</span>
          <h3 id="candidate-evidence-title">Evidence for {candidate.id}</h3>
        </div>
        <span className={`mode-badge mode-badge--${classification.mode}`}>
          {classification.mode === "real" ? "REAL MODEL" : "MOCK"}
        </span>
      </div>
      <div className="candidate-evidence-grid">
        <article className="evidence-card">
          <span className="evidence-card__label">Observed video location</span>
          <dl className="evidence-detail-list">
            <div><dt>Timestamp</dt><dd>{formatTime(candidate.timestamp_s)} ({candidate.timestamp_s.toFixed(3)} s)</dd></div>
            <div><dt>Normalized bbox</dt><dd><code>x {candidate.bbox.x.toFixed(3)} · y {candidate.bbox.y.toFixed(3)} · {candidate.bbox.width.toFixed(3)}×{candidate.bbox.height.toFixed(3)}</code></dd></div>
            <div><dt>Detection confidence</dt><dd>{typeof detection === "number" ? `${Math.round(detection * 100)}%` : "Not reported"}</dd></div>
          </dl>
          <p className="evidence-card__note">{locationSourceLabel(candidate)} This location is an observation on the whole-pen video, not a cropped image.</p>
        </article>
        <article className="evidence-card">
          <span className="evidence-card__label">Simulated input — proxy specimen</span>
          {proxy?.content_url && proxy.bytes_available !== false ? (
            <figure className="proxy-figure">
              <div className="proxy-image-wrap">
                <img
                  src={proxy.content_url}
                  alt={`Curated proxy specimen photo used as simulated input for ${candidate.id}. It did not come from the assessed video.`}
                  loading="lazy"
                />
                <span className="simulated-input-label">SIMULATED INPUT</span>
              </div>
              <figcaption>
                <dl className="evidence-detail-list">
                  <div><dt>Specimen</dt><dd><code>{proxyId(proxy)}</code></dd></div>
                  {expectedLabel ? <div><dt>Expected demo class</dt><dd className="reference-class">{expectedLabel}</dd></div> : null}
                  {proxySource(proxy) ? <div><dt>Source dataset</dt><dd>{proxySource(proxy)}</dd></div> : null}
                  {proxy.attribution ? <div><dt>Attribution</dt><dd>{proxy.attribution}</dd></div> : null}
                </dl>
                <p className="proxy-note">This curated photo stands in for a feces crop that was never cut from the video. It is explicitly simulated input, not an observed crop.</p>
                {proxy.substitution_reason ? <p className="proxy-note"><strong>Why a proxy:</strong> {proxy.substitution_reason}</p> : null}
              </figcaption>
            </figure>
          ) : (
            <div className="proxy-unavailable" role="status">
              <strong>Proxy image bytes unavailable</strong>
              {proxy ? <span>Specimen <code>{proxyId(proxy)}</code> remains indexed for provenance, but it has no verified image URL.</span> : <span>This assessment does not reference a proxy specimen.</span>}
            </div>
          )}
        </article>
      </div>
      <article className="evidence-card evidence-card--model-output">
        <span className="evidence-card__label">Model output</span>
        <dl className="evidence-detail-list">
          <div><dt>Label</dt><dd>{classification.label ?? "No label reported"}</dd></div>
          <div><dt>Confidence</dt><dd>{confidencePercent}%</dd></div>
          <div><dt>Mode</dt><dd>{classification.mode === "real" ? "Real model run" : "Deterministic mock"}</dd></div>
          {model ? <div><dt>Model / runtime</dt><dd>{model}</dd></div> : null}
          <div><dt>Inference performed</dt><dd>{classification.inference_performed === true ? "Yes — reported by the model adapter" : classification.inference_performed === false ? "No — reported by the adapter" : "Not reported by this assessment"}</dd></div>
          {fallbackReason ? <div><dt>Fallback reason</dt><dd>{fallbackReason}</dd></div> : null}
        </dl>
        <p className="evidence-card__note">{appearanceInputLabel(candidate)} The label above is the model output; the expected demo class is a dataset reference and is never presented as the prediction.</p>
      </article>
    </section>
  );
}
