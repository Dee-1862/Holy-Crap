import type { QnxEvidenceEntry, QnxEvidencePayload } from "../types";

interface QnxEvidencePanelProps {
  evidence: QnxEvidencePayload | null;
  error: string;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function documentFrom(payload: QnxEvidencePayload | null): QnxEvidencePayload | null {
  if (!payload) return null;
  return isRecord(payload.evidence) ? { ...payload, ...payload.evidence } : payload;
}

function entriesFrom(payload: QnxEvidencePayload | null): QnxEvidenceEntry[] {
  const document = documentFrom(payload);
  if (!document) return [];
  const entries = document.claims ?? document.cards ?? document.entries ?? [];
  return Array.isArray(entries) ? entries.filter(isRecord) as QnxEvidenceEntry[] : [];
}

function targetIdentity(payload: QnxEvidencePayload | null): string {
  const document = documentFrom(payload);
  if (!document) return "";
  const target = isRecord(document.target) ? document.target : document.platform;
  if (isRecord(target)) {
    return [target.system ?? target.id, target.release, target.hardware, target.machine]
      .filter((part): part is string => typeof part === "string" && part.trim().length > 0)
      .join(" · ");
  }
  return typeof document.target === "string" ? document.target : "";
}

function statusKey(entry: QnxEvidenceEntry): "verified" | "supported" | "planned" | "constraint" {
  if (entry.status === "verified") return "verified";
  if (entry.status === "os_supported" || entry.status === "os_supported_only") return "supported";
  if (entry.status === "planned") return "planned";
  return "constraint";
}

function titleFor(entry: QnxEvidenceEntry): string {
  return entry.title ?? entry.label ?? entry.id?.replaceAll("-", " ") ?? "Evidence item";
}

export function QnxEvidencePanel({ evidence, error }: QnxEvidencePanelProps) {
  const document = documentFrom(evidence);
  if (!document) {
    return (
      <section className="panel qnx-evidence-panel" aria-labelledby="qnx-evidence-title">
        <div className="subheading">
          <div><span className="eyebrow">Target evidence</span><h3 id="qnx-evidence-title">QNX evidence</h3></div>
          <span className="mode-badge mode-badge--mock">UNAVAILABLE</span>
        </div>
        <p className="empty-copy">{error || "The evidence endpoint did not return a payload."}</p>
      </section>
    );
  }

  const entries = entriesFrom(evidence);
  const counts = {
    verified: entries.filter((entry) => statusKey(entry) === "verified").length,
    supported: entries.filter((entry) => statusKey(entry) === "supported").length,
    planned: entries.filter((entry) => statusKey(entry) === "planned").length,
  };
  return (
    <section className="panel qnx-evidence-panel" aria-labelledby="qnx-evidence-title">
      <div className="subheading">
        <div><span className="eyebrow">Target evidence</span><h3 id="qnx-evidence-title">QNX evidence</h3></div>
        {document.verified_at ? <time className="qnx-verified-at">{document.verified_at}</time> : null}
      </div>
      <p className="qnx-target-identity">{targetIdentity(evidence)}</p>
      <dl className="qnx-status-counts" aria-label="QNX evidence status counts">
        <div><dt>Verified</dt><dd>{counts.verified}</dd></div>
        <div><dt>OS supported</dt><dd>{counts.supported}</dd></div>
        <div><dt>Planned</dt><dd>{counts.planned}</dd></div>
      </dl>
      <p className="qnx-boundary"><strong>Probe-only</strong> · inference verified separately · RT controls not configured</p>
      <details className="qnx-details">
        <summary>All evidence states</summary>
        <ul>
          {entries.map((entry) => (
            <li key={entry.id ?? entry.summary}>
              <span className={`qnx-state-dot qnx-state-dot--${statusKey(entry)}`} aria-hidden="true" />
              <div><strong>{titleFor(entry)}</strong><span>{entry.summary}</span></div>
            </li>
          ))}
        </ul>
      </details>
    </section>
  );
}
