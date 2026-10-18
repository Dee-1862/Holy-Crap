# Fixes to send upstream (qnx-ports)

Drafts, not posted. Found while running the dropping detector on the QNX Pi (see ../edge/ortlite).

## onnxruntime 1.24.4: Python module missing from python3-onnxruntime

- Package: `python3-onnxruntime 1.24.4-r0`, QNX 8.0.5 extra, aarch64 (build 2) and x86_64 (build 1).
  oss.qnx.com shows `test_passed: false` for both.
- Symptom: `import onnxruntime` fails with
  `ModuleNotFoundError: No module named 'onnxruntime.capi.onnxruntime_pybind11_state'`.
  The package holds only `libonnxruntime.so*` and `libonnxruntime_providers_shared.so` in `capi/`.
- Cause: onnxruntime's `setup.py` (line 364 at v1.24.4) picks files by `platform.system()`. QNX reports `'QNX'`
  (checked on the Pi), so it takes the Windows branch, looks for `onnxruntime_pybind11_state.pyd` and silently
  packages nothing. The build itself compiles the module because the APKBUILD sets `onnxruntime_ENABLE_PYTHON=ON`.
  The APKBUILD's manual symlinks of the two libraries in `package()` work around the same branch.
- Fix: `0002-qnx-package-python-module.patch` treats QNX like Linux in `setup.py`, and
  `APKBUILD.onnxruntime.diff` adds it to `source=` and makes `check()` import the package so this cannot ship again.
  The `sha512sums` line needs regenerating with `abuild checksum`.
- Not yet verified by a rebuild: building onnxruntime needs the full dev toolchain and about an hour or more.

## Abseil version mismatch in the 8.0.3 index

The `8.0.3/extra/aarch64` index lists `abseil-cpp 20230802.1-r0` next to `20250814.1-r0`. protobuf 31.1 and re2
require `>= 20250814.1`, so a resolver that picks the first entry gets an unsatisfiable set.
