import type { ClipAssessmentModule } from "../types";
import { conciseModuleNotice, fallbackReasonLabel, moduleFallbackReason, moduleInferencePerformed, moduleNotice, stageRuntimeLine } from "../evidence";
import { ModeBadge } from "./ModeBadge";

interface StageProvenanceProps {
  module: ClipAssessmentModule | undefined;
}

export function StageProvenance({ module }: StageProvenanceProps) {
  const fallback = fallbackReasonLabel(moduleFallbackReason(module));
  const inference = moduleInferencePerformed(module);
  const notice = conciseModuleNotice(module);
  const fullNotice = moduleNotice(module);
  return (
    <div className="stage-runtime">
      <ModeBadge mode={module?.mode} />
      <small>{stageRuntimeLine(module)}</small>
      {module && fallback ? <small className="stage-runtime__note stage-runtime__note--fallback">fallback · {fallback}</small> : null}
      {module && inference !== null ? <small className="stage-runtime__note stage-runtime__note--inference">{inference ? "inference performed" : "inference not performed"}</small> : null}
      {module && notice ? <small className="stage-runtime__notice" title={fullNotice ?? undefined}>{notice}</small> : null}
    </div>
  );
}
