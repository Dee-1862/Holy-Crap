# Inference on the QNX Pi

The dropping detector runs on the Pi in the `infer` section (`../infer.py`), through ONNX Runtime from QNX's open
source packages. Nothing goes to the laptop.

## What is installed and why this folder exists

- `onnxruntime 1.24.4` and `python3-numpy 2.4.1` for QNX 8.0.x aarch64, from https://oss.qnx.com
  (repo `https://repo.oss.qnx.com/8.0.5/extra/aarch64`, numpy and abseil from `8.0.3/extra`). 106 packages with
  dependencies, about 28 MB, installed offline with `sudo apk add --no-network ./*.apk` because the Pi has no internet.
- Abseil must be `20250814.1` or newer. The 8.0.3 index also lists `20230802.1`, which protobuf 31 and re2 reject.
- QNX's `python3-onnxruntime` package is missing its compiled `onnxruntime_pybind11_state` module, so
  `import onnxruntime` fails. `libonnxruntime.so` itself works, so `hc_ort.c` wraps the few C API calls we need
  and `ortlite.py` calls it with ctypes, with the same `run(x)` idea as `onnxruntime.InferenceSession`.
- The headers come from `onnxruntime-dev`, unpacked by hand into `~/ort-include` (installing the package pulls in
  dev packages that do not exist for 8.0.5).

## Build on the Pi

```sh
cd ~/hc-edge/ortlite
clang -O2 -shared -fPIC hc_ort.c -I$HOME/ort-include -l:libonnxruntime.so.1 -o libhcort.so
```

## Measured on the Pi 5, 4 threads

| model | input | time |
|---|---|---|
| dropping4_yolo11n_320.onnx | 320 | 168 ms |
| dropping4_yolo11n_640.onnx | 640 | 618 ms |
| dropping4pen_yolo11n_640.onnx | 640 | 608 ms |

The same 128 pixel patch gave cocci 0.494 on the Pi and 0.486 on the laptop, with the same box. The small gap is the
numpy resize in `infer.py` against OpenCV's on the laptop.

## Things to know

- ONNX Runtime prints its operator registry twice on load ("Schema error ... already registered"). It is harmless,
  `infer.py` hides it.
- The Pi has no clock battery and no network time on the direct cable, so it boots in 1970. Set it before anything
  that checks certificates: `sudo date -u -s @$(date -u +%s)` run from the laptop over ssh.
