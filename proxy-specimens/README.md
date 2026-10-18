# Proxy specimens

The four committed photos are small, offline-safe fallbacks. Demo-scale pools
with thousands of photos are generated under the gitignored `.simlab/datasets/`
directory. The pipeline selects a photo deterministically for each simulated
feces candidate and runs the committed classifier on its actual bytes.

## Files

| manifest        | asset id  | expected demo class |
|-----------------|-----------|---------------------|
| `healthy.json`  | `healthy` | `healthy`           |
| `cocci.json`    | `cocci`    | `cocci`             |
| `ncd.json`      | `ncd`      | `ncd`               |
| `salmo.json`    | `salmo`    | `salmo`             |

The matching, resized JPEG photos are committed beside these manifests.

## Build the full Kaggle pool

The Kaggle mirror does not declare a reuse license, so its images remain local
and are never committed. With a manually downloaded ZIP or extracted folder:

```bash
python scripts/proxy_specimen_dataset.py ingest \
  --input /path/to/chicken-disease-1.zip \
  --output .simlab/datasets/feces/proxy-pools/kaggle
```

Or use an authenticated official Kaggle CLI after accepting its terms:

```bash
python scripts/proxy_specimen_dataset.py fetch-kaggle \
  --output .simlab/datasets/feces/kaggle-download \
  --ingest-output .simlab/datasets/feces/proxy-pools/kaggle
```

If Kaggle credentials or terms prevent the download, the command stops with
manual-download instructions. It never stores credentials or bypasses TLS.
`scripts/dev.py` automatically uses the generated Kaggle pool at
`.simlab/datasets/feces/proxy-pools/kaggle`. To use a different root explicitly:

```bash
export HOLY_CRAP_PROXY_SPECIMENS_DIR="$PWD/path/to/another/proxy-pool"
```

Reruns produce byte-identical sorted catalog JSON for the same input. Each
`*.catalog.json` entry includes the original filename, SHA-256, class mapping,
farm-versus-PCR label evidence, and source/license provenance. Image bytes are
preserved rather than recompressed. The catalog is published atomically after
all referenced images have been written.

ZIP ingestion also rejects unsafe paths, members over 50 MiB, archives over
1 GiB uncompressed, and individual compression ratios over 200:1 before
reading image payloads. The `ingest --help` options allow deliberate overrides
for a verified larger source without weakening the defaults globally.

Exact-byte duplicates stay in the catalog so their provenance remains
auditable. The catalog reports duplicate and conflicting-label counts. When
one digest has multiple class labels, every row in that digest group is marked
`selection_eligible: false`; the simulator never chooses ambiguous bytes. For
same-label duplicates, only the lexicographically smallest asset ID is an
eligible canonical row. The other rows reference that ID and remain available
for provenance and direct serving without overweighting repeated image bytes.

## Optional Nigeria poultry-health research pool

Install the optional Parquet reader, then extract the already downloaded
Hugging Face distribution into its inactive, research-only location:

```bash
pip install -e '.[datasets]'
python scripts/ingest_hf_poultry_health.py
```

The default output is `.simlab/datasets/feces/optional-pools/nigeria`. It is not
loaded by `scripts/dev.py`; normal simulations use the Kaggle pool only. Its
binary unhealthy label maps to `unknown_abnormal`, so it is retained for
research but is not presented as a specific disease class. To inspect it
intentionally, set `HOLY_CRAP_PROXY_SPECIMENS_DIR` to that directory before
starting the service.

## How loading works

- Each manifest records the exact photo SHA-256. The repository re-hashes
  bytes before serving anything; a missing file or digest mismatch is treated
  as unavailable, not served.
- Placeholder digests remain supported for development fixtures, but none of
  the committed specimens uses one.
- `expected_demo_class` only steers which photo is selected for a demo profile
  (healthy / mixed / concerning). It is never written into the classification
  output, and it is not a laboratory or PCR-confirmed label.

## Provenance and licensing

The four committed fallback photos come from the farm-labelled Poultry
Diseases Dataset by Machuve et al., published on Zenodo:

- DOI: <https://doi.org/10.5281/zenodo.4628934>
- License: CC BY 4.0 (credit required)
- Attribution: Machuve, D., Nwankwo, E., Mduma, N., Mbelwa, J. (2021).
  Poultry Diseases Dataset [Data set]. Zenodo.

The original dataset filenames are not preserved here and no PCR-confirmed
labels are claimed. The photos did **not** come from any assessed video.

The full Kaggle mirror is recorded as `Unknown / local-use only`; its apparent
relationship to the Zenodo records is not treated as a license grant. PCR
filename prefixes are retained as label provenance, but neither PCR nor farm
labels make a model result a clinical diagnosis. Independently sourced pools
must keep their own primary-source license and attribution in their catalog.

## API

- `GET /api/v1/proxy-specimens/{asset_id}/content` serves verified JPEG or PNG
  bytes with the manifest media type and returns 404 for unknown ids, path-like
  ids, placeholder digests, or failed hash checks.
