# QNX native evaluation harness

These tests are intentionally separate from the edge service. They measure
QNX scheduling, native message passing, model inference, resource use, and
process-level fault isolation without killing or changing a production
process.

The durable runner expects a disposable layout like this:

    EVAL_ROOT/
      src/run_native_suite.py
      src/fault_supervisor.py
      src/fault_worker.py
      src/qnxipc.py
      src/tools/ipc_eval.py
      jitter_bench
      cpu_stress
      ncnn_bench
      model/model.ncnn.param
      model/model.ncnn.bin
      input.raw
      raw/
      logs/

Compile the three native programs on the QNX target. Run each suite through
the persistent runner, not an SSH-owned process:

    python3 src/run_native_suite.py jitter
    python3 src/run_native_suite.py ipc
    python3 src/run_native_suite.py ncnn
    python3 src/run_native_suite.py resource
    python3 src/run_native_suite.py fault

The orchestrator applies an 8 GiB virtual-memory soft limit to every measured
process, pins the timing profiles to explicit CPUs, and records the requested
policy, observed policy, runmask, memory, temperature, raw timings, and exact
argv. The fault suite sends SIGKILL only to the disposable child it spawned.

See ../evidence/2026-10-18-native-evals/ for a complete run, including the
exact staged source snapshot and runner job records.
