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

Code in `target/qnx/edge/`, standard library Python only (the Pi has no numpy or OpenCV).

| Process | Job | Talks to |
|---|---|---|
| `camera.py` | sends grey frames at a fixed rate (replay file for now) | `hc/spotter` by MsgSend |
| `spotter.py` | `stillspot.py`, flags small things that appeared and stayed still | `hc/uplink` by MsgSend |
| `uplink.py` | keeps status and saved spots, serves them on HTTP port 8088 | the dashboard `/edge` page |
| `supervisor.py` | starts the three and restarts any that dies | reports health to `hc/uplink` |

`qnxipc.py` calls `name_attach`, `name_open`, `MsgSend`, `MsgReceive` and `MsgReply` through ctypes.
Off QNX it falls back to a local socket so the same code runs on a laptop.

Because `MsgSend` blocks until the reply, a fast camera can never queue frames ahead of a slow detector,
there is no buffer to overflow. If the receiver is gone the send fails at once and the camera counts a
dropped frame and keeps its pace.

## Measured on the Pi

- Native message passing between two processes, a 57.6 KB frame and reply: 95 microseconds a round trip.
- Spot finder at 320 by 180: 63 ms a frame on the NESTLER pen clip, 80 to 116 ms on the dense PIO broiler house. The pipeline runs at 2 frames a second.
- SIGKILL on the spot finder: restarted in 22 to 26 ms, the camera lost 1 frame, camera and uplink kept their process ids.
- SIGKILL on the uplink: restarted in 23 to 24 ms, saved spots survived, the camera lost nothing.
- New code went live by crashing a process: the supervisor started the updated file, no reboot.

## Limits, stated plainly

- The camera process replays recorded footage. Live Camera Module 3 capture goes through the QNX Sensor Framework (`/dev/sensor/camera1` is present, so are the `camera_example*` programs), which has a C API. That needs a small C capture program that sends frames to `hc/spotter` the same way.
- `stillspot.py` is a candidate filter, not a dropping detector. In the dense PIO broiler house most candidates are birds resting in place. The pen scale model on the laptop still has to check them, and the 24 by 24 grey crops from the 320 wide replay are too small for that. Live capture at full resolution would give proper crops.
- The supervisor is our own Python. QNX also ships a High Availability Manager and hardware watchdog support. We have not tried them.
- Adaptive partitioning (guaranteed CPU shares, so alerts can never be starved by the detector) is a QNX feature, but the `aps` tool is not in this image. Not claimed.
- Nothing starts at boot. `/boot/onboot` is off limits unless asked (AGENTS.md). Start it by hand: `cd ~/hc-edge && nohup python3 supervisor.py --replay ../hc-replay/pio.gray &`.
- The Pi clock has no network time on the direct cable (boot time shows 1970), so spot times are only right relative to each other.
