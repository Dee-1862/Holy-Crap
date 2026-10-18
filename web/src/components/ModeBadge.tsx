import type { ClipModuleMode } from "../types";

interface ModeBadgeProps {
  mode: ClipModuleMode | string | undefined | null;
  compact?: boolean;
}

export function ModeBadge({ mode, compact = false }: ModeBadgeProps) {
  const normalized: ClipModuleMode = mode === "real" || mode === "partial" ? mode : "mock";
  const label = compact
    ? normalized === "real" ? "REAL" : normalized === "partial" ? "PARTIAL" : "MOCK"
    : normalized === "real" ? "REAL MODEL" : normalized === "partial" ? "PARTIAL" : "MOCK";
  return <span className={`mode-badge mode-badge--${normalized}`}>{label}</span>;
}
