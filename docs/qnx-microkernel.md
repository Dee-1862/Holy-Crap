# Using the QNX microkernel on the Pi

Written 2026-10-18. Everything marked measured was run on the Windows laptop's QNX Pi (`qnxpi-win`,
QNX 8.0.0, Raspberry Pi 5) over the direct cable.

## What is different from Linux

Linux is a monolithic kernel. Drivers, file systems and the network stack run inside the kernel, so a bad
driver can take the whole machine down, and fixing it usually means a reboot.

QNX Neutrino is a microkernel. The kernel only does scheduling, timers, interrupts and message passing.
Drivers, the file system, the network stack (`io-sock`) and the camera service are ordinary user processes
with their own memory. Processes talk by synchronous message passing: `MsgSend` blocks the sender, the
kernel copies the message straight into the receiver's buffer, the receiver answers with `MsgReply`.
A fault stays inside one process, and that process can be restarted while the rest keeps running.

For a barn box that nobody watches, that is the selling point: a crashing detector or camera driver
should cost seconds of data, not a dead device.

## How the edge pipeline uses it

Code in `target/qnx/edge/`. Seven sections, each its own process with its own memory, started by
`supervisor.py` at its own real time priority with QNX's `on -p` (higher runs first, normal is 10):

| Section | Priority | Job | Threads |
|---|---|---|---|
| `watchlink.py` | 21 | serves the StopWatch the same API as the console, on port 8089, so alerts work without internet | HTTP threads |
| camera: `cam/hccam` (C) or `camera.py` (replay) | 20 | full frames into a shared memory ring, a small grey copy to the spot finder | camera library thread plus a worker thread |
| `spotter.py` | 12 | `stillspot.py`, new things that appeared and stayed still | |
| `uplink.py` | 11 | status for the console Pi page, port 8088 | HTTP threads |
| `cloudlink.py` | 11 | results and farmer actions to the console or Vercel (`/api/edge/ingest`), queued on disk while offline | sender thread |
| `explain.py` | 9 | measures each patch (darker or lighter than the floor, red, green, white shares) and decides alert, normal or dismissed | |
| `model.py` | 8 | cuts a full resolution patch from shared memory and gets the detector's verdict | pool of 3 threads |

Messages go by QNX message passing (`qnxipc.py`: `name_attach`, `name_open`, `MsgSend`, `MsgReceive`,
`MsgReply` through ctypes). Big frames never travel in messages. The camera keeps the newest full frames in
`/dev/shmem/hc-frames` (4 slots, each with a sequence number) and each section cuts out only the part it
needs (`shm.py`). Nothing queues: the camera overwrites the oldest slot, the model holds at most 6 patches
and skips the rest, the spot finder's sends fail at once if a section is down.

Priority inheritance came for free. When the camera (20) sends to the spot finder, the spot finder's
receiving thread runs at 20 for that message. So the model's quick patch cut runs at the sender's priority
and its slow detector work runs in pool threads at its own priority 8.

Python on this image keeps the global interpreter lock, so Python threads only overlap waiting, not
computing. Real parallel work comes from the separate processes on the 4 cores and from the C camera threads.

## Measured on the Pi

- Native message passing between two processes, a 57.6 KB frame and reply: 95 microseconds a round trip.
- Spot finder at 320 by 180: 63 ms a frame on the NESTLER pen clip, 74 to 131 ms on the dense PIO broiler house. The pipeline runs at 2 frames a second.
- SIGKILL on any section: restarted in 20 to 33 ms. Killing the spot finder cost the camera 1 frame, the others nothing.
- New code went live by crashing a section: the supervisor started the updated file, no reboot.
- Full pipeline on the PIO barn clip: 477 full resolution patches checked by the model with none stale or skipped, results reached the console through the cloud link.
- C capture through the QNX camera library: about 29 frames a second at 1280 by 720 (unit 1), 15 (unit 2).

## The camera on this Pi

`libcamapi` and the Camera Module 3 driver (imx708) are installed, but the SDP headers are not, so `cam/hccam.c`
declares the few calls it uses and `cam/probe.c` dumps a live frame description to check the layout.
Python cannot take the camera's callbacks: any C to Python ctypes callback crashes this Python build
(checked with plain `qsort`), so capture is in C.

Since 2026-10-18 the Camera Module 3 is detected as unit 4 (`/dev/sensor/camera4`, the second ribbon port). It sends
NV12 at 2304 by 1296, which `hccam.c` stores as it arrives. The first boot found nothing on either port (I2C err=5)
until the ribbon was reseated, so power the Pi off and reseat the ribbon if the unit is missing.
`autostart.sh` starts live when the camera is found and plays recorded barn footage otherwise.

## Limits, stated plainly

- The detector runs on the Pi with ONNX Runtime from the QNX open source packages, through the C bridge in `ortlite/`, because the packaged Python binding does not load on QNX.
- That detector learned on close-up photos. At pen scale it scores white birds as salmonella at up to 0.83. The explain section's checks (box on the spot, dropping sized, not white, not lighter than the floor, score at least 0.6) dismiss nearly all of it, so the watch stays quiet rather than raising false alarms. The pen scale model (`models/dropping4-pen`) fixes this for finding droppings, see its README.
- The explain measurements describe appearance, they are not a diagnosis. Consistency and foam are not measured and are sent as a neutral 5.
- `stillspot.py` is a candidate filter, not a dropping detector.
- Adaptive partitioning (guaranteed CPU shares) is not in this image (`aps` missing). Priorities are used instead.
- The pipeline starts at boot through `install_autostart.sh` (one line in the network settings file, `/boot/onboot` untouched). To start it by hand:
  `cd ~/hc-edge && nohup python3 supervisor.py --camera live --unit 4 &` (or `--camera replay` without a camera).
- The Pi has no clock battery. `autostart.sh` sets the time with ntpdate once Wi-Fi is up. On the direct cable alone it starts at 1970.
