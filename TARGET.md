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

## Durable jobs

Submit from this Mac with:

```sh
/Users/lancestreuber/Holy-Crap/qnx-connect/runner/submit-job.py \
  --wait -- COMMAND ARGUMENT...
```

Check the runner directly with:

```sh
ssh qnxpi /data/home/qnxuser/qnx-runner-app/status-runner.sh
```

The runner executes argv directly without a shell and does not run as root.
