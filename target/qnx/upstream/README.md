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

## Review of extra/onnxruntime (cloned to cloner/qnx-aports), worst first

Measured on a Raspberry Pi 5 running QNX 8.0 with the 8.0.5 packages.

1. **The Python package does not work at all.** `python3-onnxruntime` ships without its compiled module (see above),
   for every QNX user on both architectures. Fix: `0002-qnx-package-python-module.patch`.
2. **Broken packages pass the gate.** `check()` excludes `onnxruntime_test_all` and `onnxruntime_provider_test`,
   the two main suites, and never imports the Python package. oss.qnx.com shows `test_passed: false` for both builds,
   yet the packages are published. Fix: the import line in `APKBUILD.onnxruntime.diff`, and do not publish a build
   whose tests failed.
3. **ONNX operator schemas register twice on every load.** Each process that loads onnxruntime prints 629
   "Schema error ... already registered" messages, 1,259 lines and 187 KB of stderr, about 1 s to load a small model.
   onnxruntime links the system `libonnx.so` (`-Donnx_SOURCE_DIR=/usr/include`), and extra/onnx builds it without
   `-DONNX_DISABLE_STATIC_REGISTRATION=ON`, so the schemas register when libonnx loads and again when onnxruntime
   registers them. Upstream onnxruntime builds onnx with static registration off. Fix either by building onnxruntime
   with its bundled onnx (drop `onnx_SOURCE_DIR` and the onnx dependency) or by turning static registration off in
   extra/onnx, after checking that python3-onnx still registers its schemas on import.
4. **The Arm build is not recognised as Arm everywhere.** QNX reports `aarch64le`, the build compares against
   `aarch64`, so KleidiAI (Arm's optimised kernels) is switched off. Fix: `0003-qnx-aarch64le-is-aarch64.patch`.
   The speed gain is not measured yet. The same patch area forces `x86_64` whenever the processor is `unknown`,
   which would be wrong for an Arm build that reports `unknown`.
5. **Smaller:** `-Werror` is turned off for all of QNX instead of for the warnings that fail, `options="net"` lets
   the build download dependencies, and the test patch leaves a debug `std::cout` in `test_runtime_path.cc`.

Also measured: on the Pi with our 8 section pipeline running, 2 threads (362 ms) beat 4 (562 ms) for a 640 model,
because the other sections share the 4 cores. That is our setting, not the recipe.
