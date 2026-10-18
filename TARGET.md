# QNX Pi target

## Connection

- SSH host alias: `qnxpi`
- User: `qnxuser`
- Connection test:
  `ssh -o BatchMode=yes -o ConnectTimeout=20 qnxpi 'uname -a; id'`
- Authentication and Railway proxy details stay in the user's SSH
  configuration and are intentionally not tracked here.

For the direct Ethernet link, the dashboard may set `QNX_SSH_HOSTNAME` to the
Pi's current link-local address while leaving `QNX_SSH_ALIAS=qnxpi`. This
preserves the alias's user, identity, and trusted host-key settings. On
2026-10-17, `169.254.55.180` was verified with QNX 8.0.0, Python 3.14.0, and a
running persistent runner. Treat the address as discovered state, not a fixed
deployment value.

## Second setup (Windows laptop with its own Pi)

A second QNX Pi is wired straight to a Windows laptop so both setups can test at the same time. It uses
the alias `qnxpi-win`, never `qnxpi`, so the two never point at each other. On the Windows laptop run
`python scripts/pi_win.py`. It finds the Pi on the cable by its Raspberry Pi network card prefix (the
169.254.x.x address can change after a reboot), rewrites only its own marked block in `~/.ssh/config`
and tests SSH. Repo tools take the alias from `QNX_SSH_ALIAS=qnxpi-win`. Seen on 2026-10-18 at
169.254.237.143. Treat that as discovered state.

## Verified target facts

- OS: QNX 8.0.0
- Machine: RaspberryPi5 (`aarch64le`)
- Home: `/data/home/qnxuser`
- Python: `/system/bin/python3`
- Runner application: `/data/home/qnxuser/qnx-runner-app`
- Runner spool: `/data/home/qnxuser/qnx-runner`
- QNX Screen, the QSTI launcher, and authenticated `vncserv`: running
- Writable build volume: `/data` (17 GiB free during the 2026-10-17 audit)

## Graphical access

The QSTI image exposes its QNX Screen display through the authenticated QNX
VNC server on target TCP port 5900. Keep that service behind SSH. From this
Mac, create a loopback-only tunnel with a dedicated SSH connection:

```sh
ssh -o ControlMaster=no -o ControlPath=none \
  -L 127.0.0.1:5905:127.0.0.1:5900 \
  qnxpi 'while :; do sleep 60; done'
```

Then connect the Mac Screen Sharing client to `vnc://127.0.0.1:5905`. QNX
`vncserv` forwards pointer and keyboard events to Screen, so this is an
interactive session rather than a video-only preview. Do not put the VNC
password in this repository or in the tunnel command. The QSTI initial
credential must be rotated outside source control before field deployment.

The dedicated SSH options are intentional. The `qnxpi` alias normally reuses
a multiplexed control connection, and an `ssh -N` tunnel through that existing
connection did not stay alive in the verified setup. The harmless remote
sleep loop keeps the dedicated forwarding session open. HDMI through a USB
capture dongle remains a fallback for boot and network failures, but it carries
video only; use a USB keyboard/mouse on the Pi or SSH for input.

Verified display facts:

- QNX Screen display 1 renders the QNX Everywhere launcher at 1024 x 600.
- `/system/bin/screenshot` works against display 1 when run with `sudo`;
  unprivileged `qnxuser` received `screen_context_create: Permission denied`.
- `/system/bin/vncserv` listens on target port 5900 with VNC authentication.
- Mac-side `ffmpeg` and `ffplay` are installed for HDMI-capture fallback.

The first screen is only the QSTI welcome launcher. Select **Developer Desktop
→ Start Here** to launch the fuller XFCE environment with its Applications
menu, terminal, file manager, browser, and development utilities.

The Railway/WebSocket/SSH route is functional but visibly laggy. A direct
reachability check from this Mac to the displayed Pi address `192.168.4.248`
timed out on ICMP, TCP 22, and TCP 5900, confirming that the current VNC session
cannot take the local path. For lower latency, put the Mac and Pi on the same
LAN, preferably using wired Ethernet, and tunnel directly to `qnxpi.local`
instead of through Railway. Keep VNC for administration and visual debugging;
the production camera preview needs its own compressed application stream.

## Native package-build status

The Pi already has the native QNX/Alpine package toolchain:

- `apk-tools` 3.0.6 and `abuild` 3.16.0_p2-r0
- QNX clang/cc 22.1.8, GNU Make 4.4.1, CMake 4.4.2
- Meson 1.10.0, Ninja 1.13.1, Git 2.51.0, pkg-config 2.3.0
- Python 3.14.0, `readelf`, `patch`, and `tar`

`qnxuser` belongs to the `abuild` group and has passwordless `sudo`. After
sourcing `/usr/share/abuild/functions.sh`, the verified target values are:

```text
CBUILD=aarch64-unknown-nto-qnx8.0.0
CHOST=aarch64-unknown-nto-qnx8.0.0
CARCH=aarch64
```

Native packaging is not ready yet. No aports checkout, `~/.abuild` directory,
packager identity, signing key, or local package-output repository was found.
The root IFS is read-only/full; all source, build, and package output must stay
under `/data`. Before the first native port:

1. Place the authoritative `qnx-ports/aports` fork under `/data` and record its
   exact path here.
2. Configure a human-approved packager identity and signing key. Never invent
   the identity or store the private key in this repository.
3. Validate an `apk update` and one dependency fetch; the installed world
   passed `apk add --simulate build-base`, but remote index refresh was not
   changed or tested during the read-only audit.
4. Prove one known package with `abuild -r` and confirm whether the installed
   `abuild-sudo` path is sufficient before adding any custom `SUDO_APK` wrapper.
5. Add the generated local package repositories ahead of remote repositories
   before building a dependency chain.

For ownership checks, query `/usr/...` paths with `apk info -W`; `/system/...`
is a runtime mirror and did not resolve package ownership. Sampled packages on
this Pi expose no `so:` providers, so every built package must be checked with
`readelf -d` and every non-libc runtime dependency recorded explicitly.

## Inference on the Pi (verified 2026-10-18)

- ONNX Runtime 1.24.4 and numpy 2.4.1 are installed from oss.qnx.com packages, offline, with `apk add --no-network`.
  See target/qnx/edge/ortlite/README.md for the package list, the Abseil version trap and the C bridge that
  replaces QNX's broken `python3-onnxruntime` module.
- The edge pipeline runs the detector on the Pi in its own `infer` section at priority 7. The laptop is not needed.
- The Pi boots with its clock at 1970 (no battery, no network time on the direct cable). Set it from the laptop
  before anything that checks TLS certificates.

## Selected camera stack

- Camera: Raspberry Pi Camera Module 3, verified 2026-10-18 as sensor unit 4 (`/dev/sensor/camera4`, the second
  camera port, `/dev/i2c4`), NV12 2304x1296 at 30 fps. Power the Pi off before touching the ribbon.
- Application foundation: QNX AI Camera App
  ([upstream](https://gitlab.com/qnx/projects/ai-camera-app))
- Primary interface: desktop application over reliable, high-bandwidth Wi-Fi
  (working assumption)
- Optional interface: M5Stack StopWatch C152 wall-status client
- Installed Sensor Framework, Screen, OpenCV, TensorFlow Lite, and camera
  configuration state: not yet inventoried on this target
- Current physical network interface and onboard Wi-Fi driver, firmware, and
  association state: not yet inventoried. The working `qnxpi`/Railway path does
  not prove that the intended barn WLAN path is installed or usable.

The upstream AI Camera App describes root-oriented deployment and a graphical
Screen/touch workflow. Do not enable root SSH to follow the sample. Keep the
target's service model non-root, inventory Screen/drm ownership first, and use
the app as a capture/inference reference for a headless service. The project
architecture and bring-up gates are in [docs/BIBLE.md](docs/BIBLE.md).
During discovery, inventory `io-sock`, interfaces, driver/firmware presence,
and association read-only. Do not rebuild the BSP or change `/boot/onboot`.

## Durable jobs

Submit from this Mac with the external helper currently installed at this
machine-local path:

```sh
/Users/lancestreuber/Holy-Crap/qnx-connect/runner/submit-job.py \
  --wait -- COMMAND ARGUMENT...
```

The simulation API uses its checked-in `scripts/qnx_submit_job.py` helper by
default. Unlike the older machine-local helper, it applies the configured SSH
options to every upload, poll, and log request, so `QNX_SSH_HOSTNAME` works for
the entire job instead of only the initial probe.

Check the runner directly with:

```sh
ssh qnxpi /data/home/qnxuser/qnx-runner-app/status-runner.sh
```

The runner executes argv directly without a shell and does not run as root.
