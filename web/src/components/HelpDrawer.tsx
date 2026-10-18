import { useEffect, useRef } from "react";

interface HelpDrawerProps {
  open: boolean;
  onClose: () => void;
}

const TERMS: Array<[string, string]> = [
  ["Whole-pen clip", "A video where the camera sees the flock as a group. Approximately five minutes is the target observation window, but the API records the actual duration."],
  ["Dataset library", "Reviewed clips grouped as ready locally, cataloged, reference-only, or rejected. Each entry keeps its camera notes, license, and source links visible."],
  ["Generate mock example", "Creates and persists deterministic aggregate output for a cataloged clip whose video bytes are not installed. The viewer explicitly shows that no video was played."],
  ["Aggregate assessment", "One summary for the full clip: flock activity, visible appearance, feces candidates, and the classifier distribution. It is not a bird-by-bird report."],
  ["Individual tracking", "Not required. Zone-level motion and clip-level averages are intentionally useful even when birds overlap, leave view, or cannot be consistently identified."],
  ["Activity / energy", "A clip-level movement score plus spatial zone averages. It describes observed motion during this recording, not a disease state."],
  ["Flock appearance", "A clip-level summary of visible posture and appearance. The current deterministic placeholder is explicitly marked MOCK until a real model is connected."],
  ["Feces candidates", "Likely dropping regions located in the video. Each candidate retains a timestamp and bounding box so a classifier can operate on the crop."],
  ["Feces disease classifier", "The final stage that labels candidate crops. The model trained from the chicken fecal-image dataset can replace this stage without changing activity or appearance modules."],
  ["MOCK", "A deterministic fake stage used to exercise the pipeline before trained models arrive. Mock output is visibly labeled, versioned, persisted, and non-diagnostic."],
  ["REAL MODEL", "A stage result reported by an installed model adapter. Its version and status are shown alongside the stage."],
  ["Recent assessments", "Persisted API results. Choosing one reloads its aggregate summary and exact module provenance; the browser does not synthesize replacement results."],
  ["Advanced runtime", "A collapsed area for uploading model artifacts, checking the QNX Pi, and using synthetic scenarios to validate runtime plumbing."],
  ["Validate on QNX", "In validation-only mode, stages and hashes selected model and scenario bytes on the physical Pi. It does not claim that inference ran."],
  ["Model artifact", "A registered model file plus name, version, source, and SHA-256. Uploading catalogs bytes but does not prove runtime compatibility."],
  ["Short-clip boundary", "A short video can describe what was visible during its observation window, but cannot establish infection progression over time."],
  ["Non-diagnostic boundary", "This lab produces evidence for human review. It is not a veterinary diagnosis, treatment recommendation, or clinical claim."],
];

export function HelpDrawer({ open, onClose }: HelpDrawerProps) {
  const closeRef = useRef<HTMLButtonElement>(null);
  const returnFocusRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!open) return;
    returnFocusRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    closeRef.current?.focus();
    function handleKey(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key !== "Tab") return;
      const drawer = closeRef.current?.closest<HTMLElement>("[role='dialog']");
      if (!drawer) return;
      const focusable = Array.from(drawer.querySelectorAll<HTMLElement>(
        "button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex='-1'])",
      )).filter((element) => element.getAttribute("aria-hidden") !== "true");
      if (!focusable.length) {
        event.preventDefault();
        closeRef.current?.focus();
        return;
      }
      const first = focusable[0];
      const last = focusable.at(-1)!;
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }
    window.addEventListener("keydown", handleKey);
    return () => {
      window.removeEventListener("keydown", handleKey);
      returnFocusRef.current?.focus();
      returnFocusRef.current = null;
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="help-overlay" onMouseDown={(event) => {
      if (event.target === event.currentTarget) onClose();
    }}>
      <section
        className="help-drawer"
        id="help-drawer"
        role="dialog"
        aria-modal="true"
        aria-labelledby="help-title"
        aria-describedby="help-summary"
      >
        <div className="panel-heading">
          <div><span className="eyebrow">Lab guide</span><h2 id="help-title">How it works</h2></div>
          <button ref={closeRef} className="help-close" onClick={onClose} aria-label="Close help drawer">×</button>
        </div>
        <p className="help-summary" id="help-summary">A guide to turning one whole-pen video into a versioned, flock-level observation report.</p>
        <dl className="help-terms">
          {TERMS.map(([term, definition]) => (
            <div key={term}>
              <dt>{term}</dt>
              <dd>{definition}</dd>
            </div>
          ))}
        </dl>
      </section>
    </div>
  );
}
