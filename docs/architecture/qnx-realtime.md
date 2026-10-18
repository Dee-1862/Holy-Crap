# QNX realtime architecture

## Why QNX matters here

QNX does not improve the vision model's accuracy. Its useful role is to keep
camera capture and pen-health publication predictable when CPU-heavy inference
is overloaded or fails, and to make that behavior measurable. This claim is
valid only after the scheduling and recovery controls below are configured and
tested on the physical Pi.

The target design uses separate processes:

- **Capture** acquires and timestamps frames in a short, bounded loop at a
  higher fixed priority. It does not run model code.
- **Inference** consumes queued frames at a lower priority. A QNX
  `SCHED_SPORADIC` policy can give its thread an execution budget per
  replenishment period, dropping it to a low priority after the budget is
  consumed. Overload should therefore drop or defer inference work rather than
  delay capture.
- **Assessment/publisher** combines activity and feces events into a pen-level
  assessment and publishes health/status events independently of the model
  worker.

QNX schedules the highest-priority ready thread and immediately preempts lower
priorities. `SCHED_SPORADIC` is a per-thread budget mechanism; processor
runmasks may also isolate bounded capture work from bulk inference. These
settings require a native QNX service and target measurements before they can
be shown as active.

> **QNX 8 correction:** QNX OS 8.0 does not support the Adaptive Partitioning
> Scheduler (APS). Do not describe this system as using APS or adaptive CPU
> partitions. Use fixed-priority scheduling, `SCHED_SPORADIC`, processor
> affinity, and process resource limits instead.

## Recovery and fault containment

Capture, inference, and publishing stay in separate address spaces. QNX's
microkernel process model provides memory isolation even for system services
and drivers, so a failed model worker need not take down the capture service.
Apply process limits to the inference worker for address space, heap, threads,
file descriptors, and CPU use where appropriate.

The intended recovery layers are:

1. The High Availability Manager (HAM) monitors process death and missed
   heartbeats, records the condition, and restarts the failed service.
2. The Raspberry Pi 5 BSP hardware watchdog resets the board only when the OS
   can no longer service the watchdog.
3. QNX kernel tracing records scheduler, interrupt, thread, context-switch,
   IPC, and application trace events for an evidence capture after a load or
   fault test.

HAM, the hardware watchdog, and kernel trace capture are future integration
gates. Their presence in QNX documentation is not evidence that they are
enabled in this target image.

## Dashboard proof

Every QNX field must carry one of `proven_on_target`, `configured`,
`os_supported_only`, or `unavailable`. Do not render an OS capability as an
active feature.

The dashboard should expose:

- target identity, execution mode, model/video hashes, and receipt status;
- capture scheduling policy, priority, runmask, frame period, wake-up jitter
  p50/p95/p99/max, and deadline misses;
- capture-to-assessment latency, queue depth, processed frames, and dropped
  frames;
- inference normal/low priority, budget and replenishment period, budget
  exhaustion count, CPU use, memory use, and configured resource limits;
- HAM state, heartbeat age, restart count, last failure reason, recovery time,
  and service uptime;
- hardware-watchdog enabled state, timeout, kick interval, and reset reason,
  but only after it is configured;
- last QNX trace identifier, duration, lost-event indicator, and downloadable
  `.kev` artifact.

The acceptance demonstration is a controlled overload and recovery drill:
load the inference worker, verify capture jitter and deadline misses remain
within the measured target, terminate the inference worker, and show HAM
restart it while capture and pen-level publication remain alive. No numeric
latency guarantee should be stated until this test runs on the deployed image.

## Current evidence boundary

Verified on the physical target:

- QNX 8.0.0 on Raspberry Pi 5 (`aarch64le`) with the persistent runner;
- target-probe receipts that verify the exact model and scenario hashes were
  processed on that target;
- a separate native NCNN experiment using the final 320x320 model: ten
  model-only runs averaged 98.4287 ms (about 10.16 FPS), excluding decode,
  resize, and postprocessing;
- one real feces frame completed in 100.583 ms, with native NCNN output close
  to the ONNX reference (maximum absolute difference 0.0010681, mean absolute
  difference 0.00002026, output shape `1x8x2100`).

The dashboard's general-purpose QNX executor is still a target probe and
reports `inference_performed: false`. That does not erase the separate native
NCNN benchmark, but it must not be presented as though every dashboard run
already performs inference on the target.

Not configured or verified on this target:

- Camera Module 3 capture through QNX Sensor Framework;
- TensorFlow Lite/OpenCV inference and a productionized NCNN executor;
- fixed-priority capture, sporadic inference budgets, or runmasks;
- HAM registration, heartbeat recovery, process limits, or a security policy;
- hardware watchdog activation or kernel trace capture.

The target clock has also returned epoch-era timestamps after boot. Use a
monotonic QNX clock for durations and host UTC for operator-facing event time
until target wall-clock synchronization is proven.

## Official QNX references

- [What is Real Time and Why Do I Need It?](https://qnx.com/developers/docs/8.0/com.qnx.doc.neutrino.sys_arch/topic/what_is_realtime.html)
- [QNX 8 scheduling policies](https://qnx.com/developers/docs/8.0/com.qnx.doc.neutrino.sys_arch/topic/kernel_SchedulingAlgorithms.html)
- [Sporadic scheduling](https://qnx.com/developers/docs/8.0/com.qnx.doc.neutrino.sys_arch/topic/kernel_Sporadic_scheduling.html)
- [Processor affinity and runmasks](https://qnx.com/developers/docs/8.0/com.qnx.doc.neutrino.prog/topic/multicore_processor_affinity.html)
- [APS View: QNX OS 8.0 does not support adaptive partitioning](https://qnx.com/developers/docs/8.0/com.qnx.doc.ide.userguide/topic/APS_view.html)
- [Microkernel architecture](https://qnx.com/developers/docs/8.0/com.qnx.doc.neutrino.sys_arch/topic/intro_MICROKERNELARCH.html)
- [Process resource limits](https://qnx.com/developers/docs/8.0/com.qnx.doc.neutrino.lib_ref/topic/s/setrlimit.html)
- [High Availability Manager](https://qnx.com/developers/docs/8.0/com.qnx.doc.ham/topic/hamover.html)
- [HAM conditions and restart actions](https://qnx.com/developers/docs/8.0/com.qnx.doc.ham/topic/hamapi/ham_condition.html)
- [Raspberry Pi 5 watchdog setup](https://www.qnx.com/developers/docs/BSP8.0/com.qnx.doc.bsp_raspberrypi.bcm2712.rpi5_8.0/topic/driver_commands.html)
- [Kernel event tracing](https://qnx.com/developers/docs/8.0/com.qnx.doc.ide.userguide/topic/kernel_tracing_process.html)
- [`tracelogger`](https://qnx.com/developers/docs/8.0/com.qnx.doc.neutrino.utilities/topic/t/tracelogger.html)
- [QNX AI Camera App](https://gitlab.com/qnx/projects/ai-camera-app/-/tree/main)
- [QSTI Raspberry Pi camera configuration](https://www.qnx.com/developers/docs/qnxeverywhere/com.qnx.doc.target_images/topic/qsti/next-steps.html#camera)
