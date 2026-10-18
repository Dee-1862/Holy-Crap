"""Create an isolated disposable Linux edge benchmark stage.

The source tree is copied, never edited.  Compatibility changes are applied
only to the disposable copy and are recorded with pre/post hashes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text()
    if text.count(old) != 1:
        raise RuntimeError(f"expected exactly one patch anchor in {path}: {old!r}")
    path.write_text(text.replace(old, new))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", type=Path, required=True)
    parser.add_argument("--edge-source", type=Path, required=True)
    parser.add_argument("--model-source", type=Path, required=True)
    parser.add_argument("--clip-source", type=Path, required=True)
    parser.add_argument("--assets", type=Path, required=True)
    parser.add_argument("--fps", type=float, default=5.0)
    args = parser.parse_args()

    stage = args.stage.resolve()
    if stage.exists():
        raise RuntimeError(f"refusing to reuse existing stage: {stage}")
    if not stage.name.startswith("hc-edge-fault-bench-"):
        raise RuntimeError("stage basename must start with hc-edge-fault-bench-")
    stage.mkdir(parents=True)
    edge = stage / "edge"
    shutil.copytree(args.edge_source.resolve(), edge, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copy2(args.model_source.resolve(), edge / "dropping4_yolo11n_640.onnx")
    shutil.copy2(args.clip_source.resolve(), stage / "source.mp4")
    for name in ("run_edge_fault_bench.py", "stress_worker.py", "summarize_edge_fault_bench.py"):
        shutil.copy2(args.assets.resolve() / name, stage / name)

    modified = [
        edge / "qnxipc.py",
        edge / "shm.py",
        edge / "watchlink.py",
        edge / "ortlite" / "ortlite.py",
    ]
    before = {str(path.relative_to(stage)): sha256(path) for path in modified}

    shutil.copy2(args.assets.resolve() / "qnxipc_linux.py", edge / "qnxipc.py")
    replace_once(
        edge / "shm.py",
        'PATH = "/dev/shmem/hc-frames"\n',
        'PATH = os.environ.get("HC_SHM_PATH", "/dev/shmem/hc-frames")\n',
    )
    replace_once(edge / "watchlink.py", "import json\n", "import json\nimport os\n")
    replace_once(
        edge / "watchlink.py",
        'ThreadingHTTPServer(("0.0.0.0", 8089), Http)',
        'ThreadingHTTPServer(("127.0.0.1", int(os.environ.get("HC_WATCH_PORT", "8089"))), Http)',
    )
    shutil.copy2(args.assets.resolve() / "ortlite_linux.py", edge / "ortlite" / "ortlite.py")
    after = {str(path.relative_to(stage)): sha256(path) for path in modified}

    ffmpeg = [
        "ffmpeg",
        "-nostdin",
        "-v",
        "error",
        "-i",
        str(stage / "source.mp4"),
        "-an",
        "-vf",
        f"fps={args.fps}",
        "-c:v",
        "rawvideo",
        "-pix_fmt",
        "argb",
        str(stage / "replay-argb.mov"),
    ]
    subprocess.run(ffmpeg, check=True)
    manifest = {
        "sourceHashesBeforeCompatibilityPatch": before,
        "stageHashesAfterCompatibilityPatch": after,
        "clipSourceSha256": sha256(stage / "source.mp4"),
        "replayArgbMovSha256": sha256(stage / "replay-argb.mov"),
        "modelSha256": sha256(edge / "dropping4_yolo11n_640.onnx"),
        "ffmpegArgv": ffmpeg,
        "compatibilityOnly": True,
        "claimBoundary": "Linux TCP/application-supervisor control; not QNX",
    }
    (stage / "compatibility-manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
