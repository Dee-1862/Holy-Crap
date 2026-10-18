# QNX sparse video decode and four-model evaluation

## Result

The QNX Pi ran all four current ONNX stages over three real frames from the
approved Big Broiler 090 view. This is the first target-side evidence that the
chicken detector, behavior classifier, pen-scale feces detector, and feces crop
model can execute together from decoded video pixels. It is not a full clip
assessment.

The main blocker is now specific: QNX's official FFmpeg 8.0 package deliberately
disables its H.264 decoder. It can inspect the project's normal MP4 files, but it
cannot decode their video stream. A temporary MPEG-4 Part 2 transcode decoded on
the Pi and supplied the sparse frames used for this evaluation. Production must
either emit a codec this image can decode, add an approved H.264 path, or pass raw
camera frames directly to inference.

## Safe FFmpeg installation

The package came from QNX's official 8.0.5 extra repository. The captured index
identified `ffmpeg-8.0-r5` for aarch64 at 250,456 bytes. The downloaded APK SHA-256
was `92e1d40d4b821b464a0827245b3f9cb61de2eca4cbb3dee6120215b9fcc7de2e`.

Before installation, the exact target-local APK was passed to:

```sh
apk add --simulate --no-network /data/home/qnxuser/hc-four-model-20261018-7778ee0/stage/ffmpeg-8.0-r5.apk
```

The simulation proposed one new install and no upgrade, downgrade, or removal.
Runner job `job-20261018-102801-4fa462ad` then installed that exact file with
network repositories disabled. The package inventory grew from 756 to 757; the
only new exact entry was `ffmpeg-8.0-r5`, and no old entry disappeared. The APK
itself is not retained in repository evidence because the official URL, byte
size, index stanza, and SHA-256 are enough to reproduce and verify it.

## Video decode

The input was the existing 30-second Pi-balanced Big Broiler 090 segment:

- H.264, 960x540, 11 FPS, 330 frames
- 2,675,019 bytes
- SHA-256 `92a5c5124d9d6708ea66631b48f2c38fa39ed044f9175fcbb3014510c007e653`

QNX `ffprobe` parsed its metadata. Decode job
`job-20261018-102912-fdf2a581` then failed truthfully with
`Decoding requested, but no decoder found for: h264`. The package's recorded
build configuration includes `--disable-decoder='h264,hevc,vc1,prores_raw'`.

For feasibility testing only, the same bounded segment was transcoded on the
Mac to MPEG-4 Part 2 in an MP4 container. The compatible file was 4,041,146
bytes with SHA-256
`3e7eac34c28fdc8c4382191a2ee70d681c736cf04afce69b4efa90be52578efc`.
QNX decode job `job-20261018-102933-3a598faf` sampled it at 0.1 FPS and wrote
three 960x540 RGB24 frames. The 4,665,600-byte output had SHA-256
`c045d24122f9c00161c78f4adc6a6e1b57013f28cec3e7f44f4f32475e638569`.
FFmpeg reported 0.493 seconds wall time and 1.030 seconds user CPU time.

## Four-model sparse run

Runner job `job-20261018-103626-5a0dd151` executed 12 serial model calls under
`on -L vmem:8589934592`, using two ONNX Runtime threads per session. It completed
successfully in 6,314.702 ms including all four session loads, NumPy
preprocessing, crop handoffs, and JSON output. Process CPU time was 8,321.893
ms, or 1.318 CPU-seconds per wall-second during this bounded run.

| Stage | Model SHA-256 | Input | Output | Load ms | Mean run ms | Max run ms |
|---|---|---:|---:|---:|---:|---:|
| Chicken detector | `fdb0a991...91dfb848` | `[1,3,640,640]` | `[1,5,8400]` | 870.403 | 356.011 | 358.049 |
| Behavior classifier | `7d9765fc...4e1f8b7` | `[1,3,224,224]` | `[1,7]` | 53.191 | 19.911 | 19.998 |
| Pen feces detector | `bfe181bd...7653ba18` | `[1,3,640,640]` | `[1,8,8400]` | 112.091 | 358.404 | 360.449 |
| Feces crop model | `3906fe0f...e69053e` | `[1,3,640,640]` | `[1,8,8400]` | 107.267 | 356.768 | 362.203 |

Each frame's highest chicken candidate produced a real crop for the behavior
model. The raw behavior outputs selected indices 0, 4, and 6, corresponding to
drinking, other, and preening in the repository's documented class order. Each
frame's highest pen-feces candidate likewise produced a real crop for the final
four-class model. Those outputs prove model execution and crop handoff only.
They do not prove that the selected regions were feces, and they are not a
diagnosis.

## Limits and next step

- Only three frames were sampled. There was no temporal association, stationary
  candidate confirmation, NMS, complete-video pass, pen-level aggregation, or
  fault-recovery exercise.
- The harness deliberately took one top candidate from each detector without a
  confidence gate. A high score is not validation of the object or disease.
- The behavior export already emits non-negative values summing to one. The
  executed harness mistakenly applied softmax again in its derived
  `softmax_probabilities` field. Use `raw_output`, which is preserved verbatim;
  the summary's top indices come from that raw output.
- The 8 GiB address-space cap was applied, but the target disconnected before a
  `pidin` memory snapshot and a reviewed harness correction could be rerun. No
  memory value is inferred.
- Full clip-worker deployment remains undone. The next target session should
  settle the H.264 strategy, rerun the corrected sparse harness with `pidin`
  monitoring, then implement thresholded multi-candidate processing and the
  aggregate clip contract.

## Evidence map

- `FFMPEG-PACKAGE.tsv` and `raw/ffmpeg-index-stanza.txt`: official package provenance
- `raw/ffmpeg-simulate.*`, `packages-before.txt`, `packages-after.txt`,
  `packages-added.txt`, and `packages-removed.txt`: transaction safety evidence
- `raw/h264-ffprobe.json` and `logs/job-20261018-102912-fdf2a581.stderr`:
  native H.264 inspection and decode failure
- `raw/mpeg4-ffprobe.json`, `decoded-frames-metadata.txt`, and
  `logs/job-20261018-102933-3a598faf.stderr`: compatible decode evidence
- `raw/four-model-sparse.json`: per-frame model outputs and timings
- `harness/four_model_sparse.py`: exact executed harness, SHA-256
  `3002d8c2c12a9c477b04c85712255da7df329d0cb9a3616fe9e8d3693d2770f0`
- `summary.json`: machine-readable result and limitations
