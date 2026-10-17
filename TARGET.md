# QNX Pi target

## Connection

- SSH host alias: `qnxpi`
- User: `qnxuser`
- Connection test:
  `ssh -o BatchMode=yes -o ConnectTimeout=20 qnxpi 'uname -a; id'`
- Authentication and Railway proxy details stay in the user's SSH
  configuration and are intentionally not tracked here.

## Verified target facts

- OS: QNX 8.0.0
- Machine: RaspberryPi5 (`aarch64le`)
- Home: `/data/home/qnxuser`
- Python: `/system/bin/python3`
- Runner application: `/data/home/qnxuser/qnx-runner-app`
- Runner spool: `/data/home/qnxuser/qnx-runner`
- Aports tree: not configured or verified

## Selected camera stack

- Camera: Raspberry Pi Camera Module 3
- Application foundation: QNX AI Camera App
  ([upstream](https://gitlab.com/qnx/projects/ai-camera-app))
- Primary interface: desktop application over reliable, high-bandwidth Wi-Fi
  (working assumption)
- Optional interface: M5Stack StopWatch C152 wall-status client
- Installed Sensor Framework, Screen, OpenCV, TensorFlow Lite, and camera
  configuration state: not yet inventoried on this target

The upstream AI Camera App describes root-oriented deployment and a graphical
Screen/touch workflow. Do not enable root SSH to follow the sample. Keep the
target's service model non-root, inventory Screen/drm ownership first, and use
the app as a capture/inference reference for a headless service. The project
architecture and bring-up gates are in [docs/BIBLE.md](docs/BIBLE.md).

## Durable jobs

Submit from this Mac with the external helper currently installed at this
machine-local path:

```sh
/Users/lancestreuber/Holy-Crap/qnx-connect/runner/submit-job.py \
  --wait -- COMMAND ARGUMENT...
```

Check the runner directly with:

```sh
ssh qnxpi /data/home/qnxuser/qnx-runner-app/status-runner.sh
```

The runner executes argv directly without a shell and does not run as root.
