import type { MediaAssetInfo } from "../types";

interface MediaViewportProps {
  assets: MediaAssetInfo[];
}

function AssetMetadata({ asset }: { asset: MediaAssetInfo }) {
  const hasDoi = asset.doi.trim().toLowerCase() !== "not-assigned";
  const videoDetails = asset.media_type.startsWith("video/")
    ? [
        `${asset.width}×${asset.height}`,
        asset.duration_s == null ? null : `${asset.duration_s.toFixed(1)} s`,
        asset.frame_rate_fps == null ? null : `${asset.frame_rate_fps.toFixed(2).replace(/\.00$/, "")} FPS`,
        asset.frame_count == null ? null : `${asset.frame_count.toLocaleString()} frames`,
        asset.codec?.toUpperCase() ?? null,
      ].filter((value): value is string => value !== null)
    : [];
  return (
    <figcaption className="media-caption">
      <strong>{asset.title}</strong>
      <span className="media-badge">{asset.license}</span>
      {videoDetails.length ? <p>{videoDetails.join(" · ")}</p> : null}
      <p>{asset.attribution}</p>
      {asset.creators.length ? <p>Creators: {asset.creators.join(", ")}</p> : null}
      <ul className="media-links">
        <li><a href={asset.source_url} target="_blank" rel="noreferrer">Source media</a></li>
        <li><a href={asset.dataset_url} target="_blank" rel="noreferrer">Dataset</a></li>
        {hasDoi ? <li><a href={asset.doi.startsWith("http") ? asset.doi : `https://doi.org/${asset.doi}`} target="_blank" rel="noreferrer">{asset.doi}</a></li> : null}
        <li><a href={asset.license_url} target="_blank" rel="noreferrer">License</a></li>
      </ul>
      <p className="media-description">{asset.description}</p>
      <ul className="media-limitations">
        {asset.limitations.map((limitation) => <li key={limitation}>{limitation}</li>)}
      </ul>
      <p className="media-note">Reference media only — not simulation output and not captured by this lab. Simulated bird positions and outbreak timing are not aligned to this asset.</p>
    </figcaption>
  );
}

export function MediaViewport({ assets }: MediaViewportProps) {
  if (!assets.length) {
    return (
      <div className="media-missing" role="status">
        <span className="viewport-empty__mark" aria-hidden="true" />
        <strong>No reference media reported</strong>
        <span>The media API returned no committed reference assets. Run <code>make demo-assets</code> to fetch and verify the reference media into the lab home.</span>
      </div>
    );
  }

  return (
    <div className="media-viewport">
      {assets.map((asset) => {
        const ready = asset.installed && asset.verified;
        return (
          <figure className="media-figure" key={asset.id}>
            {ready ? (
              <div className="media-frame">
                {asset.media_type.startsWith("video/") ? (
                  <video
                    src={asset.content_url}
                    aria-label={`${asset.title}. Reference video; not aligned with simulated birds.`}
                    width={asset.width}
                    height={asset.height}
                    controls
                    preload="metadata"
                    playsInline
                  >
                    Your browser does not support embedded video. Use the source link below to open the reference clip.
                  </video>
                ) : (
                  <img
                    src={asset.content_url}
                    alt={`${asset.title}. Reference imagery; not aligned with simulated birds.`}
                    width={asset.width}
                    height={asset.height}
                    loading="lazy"
                  />
                )}
              </div>
            ) : (
              <div className="media-missing" role="status">
                <span className="viewport-empty__mark" aria-hidden="true" />
                <strong>Reference media not installed</strong>
                <span>This asset is not fetched into the lab home, so it is never hotlinked. Run <code>make demo-assets</code> to download and SHA-256-verify it, then reload.</span>
              </div>
            )}
            <AssetMetadata asset={asset} />
          </figure>
        );
      })}
    </div>
  );
}
