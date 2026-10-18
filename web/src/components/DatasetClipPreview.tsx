import type { DatasetClip } from "../types";

interface DatasetClipPreviewProps {
  clip: DatasetClip;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function DatasetClipPreview({ clip }: DatasetClipPreviewProps) {
  if (!clip.bytes_available || !clip.content_url) return null;
  return (
    <figure className="dataset-clip-preview">
      {clip.media_kind === "video" ? (
        <video
          src={clip.content_url}
          aria-label={`${clip.dataset_name} — ${clip.title}`}
          controls
          preload="metadata"
          playsInline
        >
          Your browser does not support embedded video. Use the source link below to open the clip.
        </video>
      ) : (
        <img
          src={clip.content_url}
          alt={`${clip.dataset_name} — ${clip.title}`}
          loading="lazy"
        />
      )}
      <figcaption className="dataset-clip-preview__caption">
        <div className="dataset-clip-preview__row">
          <span className={`dataset-status dataset-status--${clip.status}`}>{clip.status.replaceAll("_", " ")}</span>
          <strong>{clip.filename ?? clip.title}</strong>
          {clip.installed_size_bytes != null ? <small>{formatBytes(clip.installed_size_bytes)} installed</small> : null}
        </div>
        <div className="viewer-source-links">
          <a href={clip.source_url} target="_blank" rel="noreferrer">Open source</a>
          <a href={clip.dataset_url} target="_blank" rel="noreferrer">Open dataset</a>
        </div>
      </figcaption>
    </figure>
  );
}
