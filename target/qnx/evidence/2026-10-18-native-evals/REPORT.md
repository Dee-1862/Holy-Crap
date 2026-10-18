# QNX native evaluation report

## Bottom line

This run found one strong, defensible reason to use QNX in the edge design:
fixed-priority scheduling prevented a time-critical loop from being starved by
same-core compute load. The normal round-robin loop had 2.565 seconds of
median wakeup lateness under that contention. The FIFO priority-40 loop had
336 microseconds of median lateness, about 7,600 times lower.

That does not mean the current image meets a 100-microsecond deadline. It
doesn't. The full trial set still had hundreds of microseconds of typical
lateness and occasional multi-millisecond outliers. The HDMI GUI/DRM stack was
active and accounted for roughly 29% aggregate CPU at baseline, including
high-priority interrupt work. The honest demo is that QNX priority and
affinity stop compute starvation; the next engineering step is a headless
profile and a measured deadline that the deployed pipeline can actually meet.

The QNX Pi did not run the full four-model video pipeline. Only the converted
320-pixel feces model is available natively on this target. Full video,
chicken detection, behavior classification, pen-level feces localization, and
crop-by-crop classification still need to be deployed before an end-to-end
QNX/Linux comparison is possible.

## Test target and provenance

- Repository baseline: 7778ee028347acb8793b7fd81d3d92f63ff57d37
- Target: QNX 8.0.0, Raspberry Pi 5, aarch64le
- CPU: four Cortex-A76 cores reported at 1.5 GHz
- RAM: 8,128 MB total; 7,447 MB available at baseline
- Connection: direct Ethernet, with the established qnxpi host identity
- Every measured process had an 8 GiB virtual-memory soft limit. pidin
  confirmed 8388608 kB.
- Source ONNX staged from the pinned commit:
  154407ca791330b8d6fd4ab94e5f683beceaa6ded79d34e24d05b379fe0634f8
- Tested NCNN param:
  064220842481ac84c4736ab11012129ddb7191412b69bbfde8fee261b620b4c3
- Tested NCNN bin:
  6488047efa463cef88932edfa720ec796867f14257fe0eda2f6117b0946ed3c0

The ONNX and NCNN files cannot have the same hash because they are different
formats. The hashes pin both sides of the prior conversion; they do not, by
themselves, recreate its provenance.

## Timing predictability

Each scenario ran five trials of 5,000 absolute CLOCK_MONOTONIC wakeups at a
1 ms period. The control used the default round-robin policy at priority 10.
The QNX profile used FIFO at priority 40. Both were pinned to core 3.

| Scenario | Median late | p95 | p99 | Max | Misses over 100 us |
|---|---:|---:|---:|---:|---:|
| Idle, control | 336 us | 753 us | 1,768 us | 33.6 ms | 99.98% |
| Idle, FIFO 40 | 414 us | 855 us | 861 us | 29.5 ms | 80.13% |
| Load on cores 0-2, control | 633 us | 693 us | 5,966 us | 45.1 ms | 99.98% |
| Load on cores 0-2, FIFO 40 | 725 us | 814 us | 1,536 us | 54.7 ms | 100.00% |
| Same-core load, control | 2.565 s | 4.274 s | 4.426 s | 4.475 s | 100.00% |
| Same-core load, FIFO 40 | 336 us | 908 us | 915 us | 41.8 ms | 100.00% |

The important result is the same-core case. Fixed priority turns seconds of
starvation into sub-millisecond median lateness. It does not improve the idle
median on this image, and it does not eliminate interrupt-driven outliers.
The machine-readable summary stores the control-to-FIFO median ratio as
`round(2564530.037 / 335.658, 3) = 7640.307`.

A separate fixed-priority smoke run returned a 47 us median and zero
100-microsecond misses over 2,000 wakes. The longer suite did not reproduce
that result consistently, so the smoke number is preserved in the raw data
but is not used as the headline.

## Native message passing

Five trials measured 1,000 MsgSend/MsgReceive/MsgReply round trips each. The
request was 57,600 bytes and the reply was 16 bytes.

| Samples | Mean | Median | p95 | p99 | Max |
|---:|---:|---:|---:|---:|---:|
| 5,000 | 95.4 us | 89.7 us | 133.7 us | 185.9 us | 206.3 us |

The earlier Linux number used localhost TCP, not the same IPC primitive. Its
roughly 48-51 us trial means are useful context, but they are not evidence
that either operating system has faster native IPC.

## Native feces inference

The existing NCNN-converted 320 model ran in FP32 with three threads
requested. Each of five trials per scenario measured one first inference and
20 steady calls.

| Scenario | First-call mean | Steady mean | Median | p95 | p99 | Throughput |
|---|---:|---:|---:|---:|---:|---:|
| Idle | 104.7 ms | 102.5 ms | 100.1 ms | 109.4 ms | 150.1 ms | 9.76 calls/s |
| Three bounded CPU workers | 99.9 ms | 103.6 ms | 100.0 ms | 129.2 ms | 144.1 ms | 9.65 calls/s |

The bounded load reduced mean throughput by about 1%. It had a larger effect
on the p95 tail. The model process reported about 48 MB of data memory.
pidin times increased by about one user CPU-second per wall-clock second in
the longer resource profile. That is the process counter QNX exposed here,
not a claim that all three requested NCNN threads stayed busy.

Temperature reached 60.91 C and the fan moved from 30.2% to 50.2%. This image
did not expose a throttle counter in the paths checked, so the run cannot
claim that throttling did or did not occur.

The earlier Linux model-only test used ONNX Runtime, a 2.4 GHz Linux image,
and synthetic input. It averaged about 36.2 ms at 320 pixels. The QNX result
uses NCNN, a 1.5 GHz image, and the preserved real tensor. Treat this as a
deployment measurement, not a clean OS shootout.

## Fault isolation and recovery

Each of five trials launched a disposable worker, sent SIGKILL only to that
PID, detected its exit, spawned a replacement, waited for readiness, and
waited for the first result. A separate FIFO priority-40 timer stayed on core
3 for the entire recovery.

| Measure | Result |
|---|---:|
| Mean failure detection | 11.5 ms |
| Worst failure detection | 17.0 ms |
| Mean replacement ready | 4.388 s |
| Mean first result | 4.398 s |
| Worst first result | 4.679 s |

All five high-priority timer processes kept the same PID, completed all
16,000 scheduled wakeups, spanned the kill and the replacement's first
result, and continued for at least another 3.66 seconds. Their largest
observed inter-wakeup gaps ranged from 25.1 to 31.4 ms.

This proves process-level isolation for the disposable user-space worker. It
does not test a kernel fault, driver fault, memory corruption, or the actual
four-model pipeline. The 4.4-second recovery is dominated by Python process
startup and is too slow for the final service. A native prestarted worker or
warm standby is the obvious next benchmark.

## Resource and baseline notes

- Baseline top: 24.3% user, 4.4% kernel, 49 processes, 307 threads.
- drm-rpi5 plus its interrupt thread accounted for roughly 24% CPU in the
  captured baseline. The launcher, Screen, and VNC services were also active.
- Feces inference reported about 48 MB of process data memory.
- The Python fault supervisor reported about 4.7-5.1 MB of data memory and an
  8 MB stack mapping.
- No reboot was performed, so boot-time cost was not benchmarked.
- No long-duration uptime or soak test was performed.

## Current QNX runtime gap

The checked-in ortlite README says NumPy, ONNX Runtime, and the C bridge were
installed on a Pi. They are not present on the target connected for this run.

Both python3 and /system/bin/python3 resolve to QNX Python 3.14. Both fail to
import numpy and onnxruntime. The installed package inventory contains no
matching package, and a search under /system, /usr, and the user's data
directory found no libhcort.so, libonnxruntime.so, ortlite.py, or edge
infer.py. The only matching ONNX file already on the target was the older
dropping4-e37 320 model.

This is a target-state discrepancy, not a benchmark result. Do not claim the
current Pi is running the checked-in ONNX edge worker until those artifacts
are deployed and reverified.

## Development experience

The native C and C++ harnesses compiled successfully through the durable
runner. Runner timestamps show roughly 3 seconds for the small jitter
compile, less than one timestamp second for the stress helper, and 8 seconds
for the NCNN harness.

Two setup problems are preserved in the evidence:

1. The existing submit helper's qnxpi SCP route returned Connection closed
   after the Ethernet change. Direct SSH/SCP with the trusted HostKeyAlias
   worked, and the same job JSON protocol was submitted manually.
2. QNX on -L takes the virtual-memory value in bytes, while pidin reports it
   in kilobytes. The first Python attempts passed 8388608, creating an
   accidental 8 MiB cap and failing cleanly with Not enough memory. The
   corrected value was 8589934592; pidin then reported the intended
   8388608 kB limit.

## Commands and raw evidence

Every long-running command went through the persistent runner. Exact argv
arrays, working directories, timeouts, exit codes, and timestamps are in
runner/*-state.json. Per-test argv arrays also appear in the suite manifests.

The main measured command shapes were:

    on -L vmem:8589934592 -C 3 [-p 40f] ./jitter_bench 5000 1000 100 RAW.csv
    on -L vmem:8589934592 -C CPU ./cpu_stress SECONDS
    on -L vmem:8589934592 python3 src/tools/ipc_eval.py RAW.csv 1000 57600
    on -L vmem:8589934592 -R 15 ./ncnn_bench PARAM BIN INPUT 320 21 3 in0 out0 RAW.csv
    on -L vmem:8589934592 -C 0 python3 src/fault_supervisor.py OUTPUT_DIR

Useful entry points:

- summary.json: machine-readable aggregate
- raw/*-suite-manifest.json: scenario metadata and process observations
- raw/*-calls.csv and raw/jitter-*.csv: every measured call
- raw/runtime-inventory.txt: installed-runtime check
- raw/artifact-hashes.txt and raw/harness-hashes.txt: provenance
- runner/: durable-runner job state and logs
- harness/: exact source snapshot copied back from the target
- raw/failed-attempt-vmem-8mb/: preserved unit-error failure
- raw/incomplete-fault-timing-window/ and
  raw/partial-fault-timing-window-12s/: superseded fault-window attempts
