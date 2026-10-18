# QNX ONNX runtime restoration

## Result

The connected QNX Pi can execute the pinned 320-pixel feces model through the
checked-in `ortlite` bridge. The restore used only signed packages downloaded
from QNX's official repositories. No existing package was upgraded,
downgraded, removed, or replaced.

The model ran on a tensor prepared from the repository's `healthy.jpg`
specimen. Five warm calls averaged 129.199 ms. QNX returned the expected
`[1, 8, 2100]` output, and that output matches the Mac ONNX Runtime reference
within `rtol=1e-4, atol=1e-5`.

The checked-in HTTP service now takes an explicit, validated input side. An
ephemeral loopback-only run with the same pinned model returned verified GET
metadata and one real POST result. The service measured 111.4 ms for the model
and preprocessing path; `curl` measured 115.583 ms end to end.

## Source and target

- Source commit: `7778ee028347acb8793b7fd81d3d92f63ff57d37`
- Target: QNX 8.0.0 on Raspberry Pi 5, aarch64le
- Staging directory:
  `/data/home/qnxuser/hc-ort-restore-20261018-ortlite-7778ee0`
- Model SHA-256:
  `154407ca791330b8d6fd4ab94e5f683beceaa6ded79d34e24d05b379fe0634f8`
- Bridge source SHA-256:
  `0e78489d984567d24cef0edecc371516bd1b65aeead3e83630109c12005390c0`
- Built bridge SHA-256:
  `437d2edb5999297d020d50346d406368bdc792c72fe30117a231d80f5ec65b53`
- Verified HTTP server source SHA-256:
  `ed608cfd9d996b5453f6c83d6ce9ab957f5f179374309d5f7a53046b0159ea8c`

## Package safety gate

The Mac bundle used for the restore contained 107 APKs.
`PACKAGE-BUNDLE.tsv` records every exact package version, official URL, byte
size, and SHA-256. The reproducible 31 MiB APK copies and their duplicate tar
archive are intentionally omitted from repository evidence; they can be
downloaded again from the recorded official URLs and verified against those
hashes. The development-header APK was kept separate in
`HEADER-PACKAGE.tsv`; it was unpacked into the staging directory and was not
installed.

The target received the same 107 runtime APKs. Every target hash matched the
Mac bundle. This command was then run against only those files:

```sh
apk add --simulate --no-network /data/home/qnxuser/hc-ort-restore-20261018-ortlite-7778ee0/bundle/*.apk
```

The simulation exited successfully and proposed 107 installs, with no
upgrade, downgrade, removal, or purge line. Installation ran through the
persistent runner with `sudo apk add --no-network --repositories-file
/dev/null` followed by the 107 exact paths. The inventory grew from 649 to
756 packages. A comparison of all exact pre-install and post-install package
lines found all 649 original entries unchanged and exactly 107 new entries.

Installed runtime checks:

- NumPy imports as version 2.4.1.
- `/usr/lib/libonnxruntime.so.1.24.4` is owned by
  `onnxruntime-1.24.4-r0`.
- `python3-onnxruntime` was intentionally left uninstalled because the
  official package omits its compiled binding. A direct Python import is
  therefore unavailable; `ortlite` calls the installed C library instead.

## Bridge build and inference

The bridge was built natively through the persistent runner:

```sh
/proc/boot/on -L vmem:8589934592 clang -O2 -shared -fPIC hc_ort.c \
  -I /data/home/qnxuser/hc-ort-restore-20261018-ortlite-7778ee0/stage/include-root/usr/include/onnxruntime \
  -l:libonnxruntime.so.1 -o libhcort.so
```

The result is an AArch64 shared object linked to
`libonnxruntime.so.1`. The compiler reported two ignored-return-value
warnings for `AllocatorFree`; it produced the library successfully.

The real-specimen tensor has shape `[1, 3, 320, 320]` and SHA-256
`bb9f9e5d882f6293825ca4a620ca861481da9e364ce0773485750be445e624fc`.
The same tensor and model were used on both machines.

| Result | QNX Pi | Mac reference |
|---|---:|---:|
| Runtime | ONNX Runtime 1.24.4 C API | ONNX Runtime 1.31.0 |
| Session load | 1,018.392 ms | Not recorded |
| Warm calls | 5 | 5 |
| Mean warm call | 129.199 ms | 14.380 ms |
| Output shape | `[1, 8, 2100]` | `[1, 8, 2100]` |
| Output SHA-256 | `7afafa5a...1cde2` | `52796af4...9b8e` |
| Maximum absolute difference | 0.000167847 | reference |
| Mean absolute difference | 0.000004193 | reference |
| `allclose(rtol=1e-4, atol=1e-5)` | true | reference |

Different output hashes are expected because the runtimes and hardware do
not produce bit-identical floating-point values. The explicit tolerance check
is the parity result. The Mac timing is context only, not an operating-system
comparison: it uses different hardware and ONNX Runtime 1.31.0.

The QNX smoke process was launched with `on -L vmem:8589934592`. A separate
Python probe reported the soft address-space limit as exactly 8,589,934,592
bytes.

## Configured HTTP inference smoke

`target/qnx/edge/infer.py` now reads `HC_MODEL_SIDE` eagerly. The default stays
640. Accepted values are 32 through 4096 and must be divisible by 32; a bad
value fails before the model or HTTP listener starts. Twenty-three focused
tests cover the default, the pinned 320 side, input tensor shape and dtype,
metadata, boundary values, and invalid configuration. The combined edge test
selection passed 39 tests. A target-side launch with `HC_MODEL_SIDE=641`
failed with the expected validation error.

The ephemeral QNX service was submitted as runner job
`job-20261018-102446-dbc22f46` with:

```text
HC_MODEL=.../dropping4_yolo11n_320.onnx
HC_MODEL_SIDE=320
HC_THREADS=2
HC_INFER_PORT=18771
/proc/boot/on -L vmem:8589934592 /system/bin/python3 infer.py
```

GET `http://127.0.0.1:18771/` returned HTTP 200 with model
`dropping4_yolo11n_320.onnx`, target `pi`, side 320, and all four classes in
3.499 ms. One POST of the real 180x135 RGB specimen returned HTTP 200 with a
`cocci` box at score 0.874, 111.4 ms service time, and 115.583 ms total loopback
time. The raw request payload SHA-256 is
`c49fb5494c1136d0a1c01f6ea1cae60c3da9c01b71e8f311488140213d9540aa`.

`pidin` reported 65 MiB of process data after the request and a soft virtual-
memory limit of 8,388,608 KiB. The service bound only to 127.0.0.1. It was
stopped with SIGTERM after the assertions; the runner therefore recorded the
controlled shutdown as exit -15, not an inference failure. A final probe got
connection refused, the service PID no longer existed, and the persistent
runner remained healthy with no running jobs. No autostart or persistent
service was enabled.

## Limits and friction

- This proves one feces model call, not the full four-model video pipeline or
  the clip-worker contract.
- `infer.py` and `ortlite` are staged and the 320 HTTP path is verified, but no
  persistent service was enabled.
- ONNX Runtime emits the already-documented duplicate schema-registration
  messages during startup. They did not prevent inference.
- The first runner install submission passed a literal `*.apk` argument and
  failed before changing package state because the runner intentionally does
  not invoke a shell. The successful submission passed all 107 paths as
  separate argv entries.
- `ldd` printed the full bridge dependency graph, then exited 1 with
  `Could not clean up dynamic TLS memory`. Actual model inference completed
  successfully, so this is recorded as an inspection-tool failure rather than
  a loader failure.
- No boot, tunnel, camera, driver, repository, or autostart configuration was
  changed.

## Evidence map

- `PACKAGE-BUNDLE.tsv`: exact runtime bundle, official URLs, and hashes
- `HEADER-PACKAGE.tsv`: unpacked development-header package provenance
- `raw/exact-bundle-simulate.stdout`: clean no-network transaction plan
- `raw/install-runner-output-2.txt`: completed persistent-runner install
- `raw/target-installed-before.txt` and `target-installed-after.txt`: exact
  package inventories
- `raw/build-runner-output.txt`: bridge build job and warnings
- `smoke/mac-smoke.json` and `smoke/qnx-smoke.json`: timings and output hashes
- `smoke/parity.json`: numerical output comparison
- `raw/input-side-tests.txt`: focused input-side validation tests
- `raw/http-smoke/`: GET/POST bodies, headers, timings, process limits, memory,
  runner state, and shutdown proof
- `logs/http-smoke/`: service stdout and stderr from the persistent runner
- `raw/final-target-runtime-validation.txt`: ownership, dependencies, and
  target hashes
