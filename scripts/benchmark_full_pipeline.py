#!/usr/bin/env python3
"""Run and measure the Simulation Lab's real clip-assessment pipeline.

This is an evidence harness, not a second implementation of the pipeline.  It
constructs the production adapters with timed ONNX sessions, runs one selected
source segment, and emits a single atomic JSON report.  A successful process
exit means both that every configured model executed and that every retained
feces candidate came from an observed video crop classified by the live model.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import resource
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from collections import Counter, defaultdict
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from holy_crap_simlab.clip_assessment import (  # noqa: E402
    DeterministicClipPipeline,
    DeterministicFecesClassifierAdapter,
    StoredVideo,
    VideoProbe,
    probe_video,
)
from holy_crap_simlab.dropping_inference import DroppingOnnxAdapter  # noqa: E402
from holy_crap_simlab.proxy_specimens import ProxySpecimenRepository  # noqa: E402
from holy_crap_simlab.video_inference import (  # noqa: E402
    SparseFfmpegDecoder,
    VideoInferenceResult,
    WholePenVideoInference,
)

MODEL_PATHS = {
    "chicken_detector": REPO_ROOT
    / "models/behaviour-v1/chicken_yolo11n_640.onnx",
    "behavior_classifier": REPO_ROOT
    / "models/behaviour-v1/behaviour7_yolo11n-cls_224.onnx",
    "pen_feces_locator": REPO_ROOT
    / "models/dropping4-pen/dropping4pen_yolo11n_640.onnx",
    "feces_crop_classifier": REPO_ROOT
    / "models/dropping4-laptop/dropping4_yolo11n_320.onnx",
}


class MemoryCeilingExceeded(RuntimeError):
    """Raised once aggregate process-tree resident memory crosses the ceiling."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _percentile(values: Sequence[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    rank = (len(ordered) - 1) * percentile
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (rank - lower)


def distribution(values_s: Sequence[float]) -> dict[str, int | float | None]:
    """Return a stable millisecond latency summary without discarding raw calls."""

    values_ms = [value * 1000.0 for value in values_s]
    if not values_ms:
        return {
            "count": 0,
            "total_ms": 0.0,
            "min_ms": None,
            "mean_ms": None,
            "median_ms": None,
            "p95_ms": None,
            "p99_ms": None,
            "max_ms": None,
        }
    return {
        "count": len(values_ms),
        "total_ms": round(sum(values_ms), 3),
        "min_ms": round(min(values_ms), 3),
        "mean_ms": round(statistics.fmean(values_ms), 3),
        "median_ms": round(statistics.median(values_ms), 3),
        "p95_ms": round(_percentile(values_ms, 0.95) or 0.0, 3),
        "p99_ms": round(_percentile(values_ms, 0.99) or 0.0, 3),
        "max_ms": round(max(values_ms), 3),
    }


class TimingRegistry:
    def __init__(self, clock: Callable[[], float] = time.perf_counter) -> None:
        self.clock = clock
        self.stage_calls: dict[str, list[float]] = defaultdict(list)
        self.model_init_calls: dict[str, list[float]] = defaultdict(list)
        self.model_inference_calls: dict[str, list[float]] = defaultdict(list)
        self.model_inference_records: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._lock = threading.Lock()
        self._local = threading.local()

    @contextmanager
    def stage(self, name: str) -> Iterator[None]:
        started = self.clock()
        try:
            yield
        finally:
            elapsed = self.clock() - started
            with self._lock:
                self.stage_calls[name].append(elapsed)

    def record_model_init(self, name: str, elapsed_s: float) -> None:
        with self._lock:
            self.model_init_calls[name].append(elapsed_s)

    @contextmanager
    def model_call_context(self, **context: Any) -> Iterator[None]:
        previous = getattr(self._local, "model_call_context", None)
        self._local.model_call_context = dict(context)
        try:
            yield
        finally:
            self._local.model_call_context = previous

    def record_model_inference(self, name: str, elapsed_s: float) -> None:
        with self._lock:
            self.model_inference_calls[name].append(elapsed_s)
            call_order = len(self.model_inference_calls[name])
            self.model_inference_records[name].append(
                {
                    "call_order": call_order,
                    "latency_ms": round(elapsed_s * 1000.0, 3),
                    "cold_first_call": call_order == 1,
                    "context": dict(
                        getattr(self._local, "model_call_context", None) or {}
                    ),
                }
            )

    def report(self) -> dict[str, Any]:
        model_names = sorted(
            set(MODEL_PATHS)
            | set(self.model_init_calls)
            | set(self.model_inference_calls)
        )
        return {
            "stages": {
                name: distribution(values)
                for name, values in sorted(self.stage_calls.items())
            },
            "models": {
                name: {
                    "session_initialization": distribution(
                        self.model_init_calls.get(name, [])
                    ),
                    "cold_first_inference_call": distribution(
                        self.model_inference_calls.get(name, [])[:1]
                    ),
                    "steady_state_inference_calls": distribution(
                        self.model_inference_calls.get(name, [])[1:]
                    ),
                    "inference_calls": distribution(
                        self.model_inference_calls.get(name, [])
                    ),
                    "every_inference_call_ms": [
                        round(value * 1000.0, 3)
                        for value in self.model_inference_calls.get(name, [])
                    ],
                    "inference_call_records": list(
                        self.model_inference_records.get(name, [])
                    ),
                }
                for name in model_names
            },
        }


class TimedSession:
    def __init__(
        self,
        session: object,
        model_name: str,
        registry: TimingRegistry,
        memory_guard: Callable[[], None],
    ) -> None:
        self._session = session
        self._model_name = model_name
        self._registry = registry
        self._memory_guard = memory_guard

    def get_inputs(self) -> Any:
        return self._session.get_inputs()  # type: ignore[attr-defined]

    def run(self, *args: Any, **kwargs: Any) -> Any:
        self._memory_guard()
        started = self._registry.clock()
        try:
            return self._session.run(*args, **kwargs)  # type: ignore[attr-defined]
        finally:
            self._registry.record_model_inference(
                self._model_name, self._registry.clock() - started
            )
            self._memory_guard()


def _ort_session(path: Path, threads: int) -> object:
    import onnxruntime as ort

    options = ort.SessionOptions()
    options.intra_op_num_threads = threads
    options.inter_op_num_threads = 1
    return ort.InferenceSession(
        str(path), sess_options=options, providers=["CPUExecutionProvider"]
    )


def timed_session_factory(
    *,
    registry: TimingRegistry,
    memory_guard: Callable[[], None],
    threads: int,
    loader: Callable[[Path, int], object] = _ort_session,
) -> Callable[[Path], object]:
    by_path = {path.resolve(): name for name, path in MODEL_PATHS.items()}

    def create(path: Path) -> object:
        resolved = path.resolve()
        name = by_path.get(resolved, resolved.stem)
        started = registry.clock()
        session = loader(path, threads)
        registry.record_model_init(name, registry.clock() - started)
        memory_guard()
        return TimedSession(session, name, registry, memory_guard)

    return create


class InstrumentedDecoder(SparseFfmpegDecoder):
    def __init__(self, registry: TimingRegistry, memory_guard: Callable[[], None]) -> None:
        super().__init__()
        self.registry = registry
        self.memory_guard = memory_guard

    def decode(self, *args: Any, **kwargs: Any) -> Any:
        with self.registry.stage("video_decode_probe_and_frames"):
            result = super().decode(*args, **kwargs)
        self.memory_guard()
        return result


class InstrumentedVideoInference(WholePenVideoInference):
    def __init__(self, *args: Any, registry: TimingRegistry, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.registry = registry
        self.last_result: VideoInferenceResult | None = None

    def analyze(self, *args: Any, **kwargs: Any) -> VideoInferenceResult:
        with self.registry.stage("whole_pen_video_inference"):
            self.last_result = super().analyze(*args, **kwargs)
        return self.last_result

    def _chicken_localizations(self, *args: Any, **kwargs: Any) -> Any:
        with self.registry.stage("chicken_detection"):
            return super()._chicken_localizations(*args, **kwargs)

    def _activity(self, *args: Any, **kwargs: Any) -> Any:
        with self.registry.stage("motion_and_behavior_aggregation"):
            return super()._activity(*args, **kwargs)

    def _dropping_candidates(self, *args: Any, **kwargs: Any) -> Any:
        with self.registry.stage("feces_detection_and_persistence"):
            return super()._dropping_candidates(*args, **kwargs)


class InstrumentedFecesClassifier(DeterministicFecesClassifierAdapter):
    def __init__(self, *args: Any, registry: TimingRegistry, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.registry = registry
        self._local = threading.local()

    def classify(self, *args: Any, **kwargs: Any) -> Any:
        candidates = args[1] if len(args) > 1 else kwargs.get("candidates", [])
        previous = getattr(self._local, "candidate_ids", None)
        self._local.candidate_ids = [candidate.id for candidate in candidates]
        try:
            with self.registry.stage("feces_crop_classification"):
                return super().classify(*args, **kwargs)
        finally:
            self._local.candidate_ids = previous

    def _classify_observed_crop(self, *args: Any, **kwargs: Any) -> Any:
        index = int(args[4] if len(args) > 4 else kwargs["index"])
        candidate_ids = getattr(self._local, "candidate_ids", []) or []
        candidate_id = candidate_ids[index] if index < len(candidate_ids) else None
        with self.registry.model_call_context(
            pipeline_stage="feces_crop_classification",
            candidate_id=candidate_id,
            candidate_index=index,
        ):
            return super()._classify_observed_crop(*args, **kwargs)


def _linux_process_tree_rss_bytes(root_pid: int) -> int | None:
    proc = Path("/proc")
    if not proc.is_dir():
        return None
    parents: dict[int, int] = {}
    rss: dict[int, int] = {}
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            status = (entry / "status").read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        ppid = None
        resident_kib = 0
        for line in status.splitlines():
            if line.startswith("PPid:"):
                ppid = int(line.split()[1])
            elif line.startswith("VmRSS:"):
                resident_kib = int(line.split()[1])
        if ppid is not None:
            pid = int(entry.name)
            parents[pid] = ppid
            rss[pid] = resident_kib * 1024
    selected = {root_pid}
    changed = True
    while changed:
        before = len(selected)
        selected.update(pid for pid, parent in parents.items() if parent in selected)
        changed = len(selected) != before
    return sum(rss.get(pid, 0) for pid in selected)


class MemoryMonitor:
    def __init__(
        self,
        ceiling_bytes: int | None,
        *,
        interval_s: float = 0.05,
        root_pid: int | None = None,
        sampler: Callable[[int], int | None] = _linux_process_tree_rss_bytes,
    ) -> None:
        self.ceiling_bytes = ceiling_bytes
        self.interval_s = interval_s
        self.root_pid = root_pid or os.getpid()
        self.sampler = sampler
        self.max_rss_bytes = 0
        self.sample_count = 0
        self.limit_crossed = False
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def __enter__(self) -> "MemoryMonitor":
        self._sample()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *_args: Any) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=max(0.2, self.interval_s * 4))
        self._sample()

    def _loop(self) -> None:
        while not self._stop.wait(self.interval_s):
            self._sample()

    def _sample(self) -> None:
        value = self.sampler(self.root_pid)
        if value is None:
            # ru_maxrss is KiB on Linux and bytes on macOS.
            raw = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            value = int(raw if sys.platform == "darwin" else raw * 1024)
        self.sample_count += 1
        self.max_rss_bytes = max(self.max_rss_bytes, value)
        if self.ceiling_bytes is not None and value > self.ceiling_bytes:
            self.limit_crossed = True

    def guard(self) -> None:
        if self.limit_crossed:
            ceiling_mib = (self.ceiling_bytes or 0) / (1024 * 1024)
            raise MemoryCeilingExceeded(
                f"process-tree RSS crossed the {ceiling_mib:.1f} MiB ceiling"
            )

    def report(self) -> dict[str, Any]:
        return {
            "measurement": (
                "linux_proc_process_tree_rss"
                if Path("/proc").is_dir()
                else "self_ru_maxrss_fallback"
            ),
            "sample_interval_ms": round(self.interval_s * 1000, 3),
            "sample_count": self.sample_count,
            "max_rss_bytes": self.max_rss_bytes,
            "max_rss_mib": round(self.max_rss_bytes / (1024 * 1024), 3),
            "ceiling_bytes": self.ceiling_bytes,
            "ceiling_mib": (
                round(self.ceiling_bytes / (1024 * 1024), 3)
                if self.ceiling_bytes is not None
                else None
            ),
            "ceiling_crossed": self.limit_crossed,
            "ceiling_semantics": (
                "RSS observation threshold with cooperative fail-stop checks; "
                "not an operating-system-enforced memory limit"
            ),
        }


@dataclass(frozen=True)
class BenchmarkConfig:
    clip: Path
    segment_start: float
    segment_end: float | None
    output: Path
    profile: str
    memory_ceiling_mib: float | None
    memory_sample_ms: float
    threads: int
    external_memory_limit_bytes: int
    external_memory_enforcement: str
    require_every_source_frame: bool


def _metadata() -> dict[str, Any]:
    def git(*args: str) -> tuple[bool, str | None]:
        try:
            completed = subprocess.run(
                ["git", *args],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
        except OSError:
            return False, None
        value = completed.stdout.strip()
        return completed.returncode == 0, value or None

    inside_ok, inside_value = git("rev-parse", "--is-inside-work-tree")
    git_available = inside_ok and inside_value == "true"
    commit_ok, commit = git("rev-parse", "HEAD") if git_available else (False, None)
    branch_ok, branch = (
        git("branch", "--show-current") if git_available else (False, None)
    )
    status_ok, status = git("status", "--porcelain") if git_available else (False, None)

    try:
        import onnxruntime

        ort_version = onnxruntime.__version__
    except Exception:
        ort_version = None
    return {
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "git": {
            "git_available": git_available,
            "commit": commit if commit_ok else None,
            "branch": branch if branch_ok else None,
            "dirty": bool(status) if status_ok else None,
        },
        "host": {
            "hostname": platform.node(),
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "logical_cpu_count": os.cpu_count(),
            "load_average": list(os.getloadavg()) if hasattr(os, "getloadavg") else None,
        },
        "runtime": {
            "python": platform.python_version(),
            "python_implementation": platform.python_implementation(),
            "onnxruntime": ort_version,
            "ffmpeg": _tool_version("ffmpeg"),
            "ffprobe": _tool_version("ffprobe"),
        },
    }


def _tool_version(name: str) -> str | None:
    try:
        completed = subprocess.run(
            [name, "-version"], text=True, capture_output=True, timeout=5, check=False
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    return completed.stdout.splitlines()[0] if completed.returncode == 0 else None


def _model_artifacts() -> dict[str, Any]:
    artifacts: dict[str, Any] = {}
    for name, path in MODEL_PATHS.items():
        exists = path.is_file()
        artifacts[name] = {
            "path": str(path.relative_to(REPO_ROOT)),
            "exists": exists,
            "size_bytes": path.stat().st_size if exists else None,
            "sha256": _sha256(path) if exists else None,
        }
    return artifacts


def _build_pipeline(
    registry: TimingRegistry,
    monitor: MemoryMonitor,
    threads: int,
) -> tuple[DeterministicClipPipeline, InstrumentedVideoInference]:
    video_factory = timed_session_factory(
        registry=registry, memory_guard=monitor.guard, threads=threads
    )
    decoder = InstrumentedDecoder(registry, monitor.guard)
    video = InstrumentedVideoInference(
        decoder=decoder,
        model_root=REPO_ROOT / "models",
        session_factory=video_factory,
        registry=registry,
    )

    crop_path = MODEL_PATHS["feces_crop_classifier"]
    crop_factory = timed_session_factory(
        registry=registry, memory_guard=monitor.guard, threads=threads
    )
    crop = DroppingOnnxAdapter(
        model_path=crop_path,
        session_factory=lambda: crop_factory(crop_path),
    )
    proxy = ProxySpecimenRepository()
    pipeline = DeterministicClipPipeline(proxy, crop, video_inference=video)
    pipeline.feces_classifier = InstrumentedFecesClassifier(
        proxy, crop, registry=registry
    )
    return pipeline, video


def _bird_summary(assessment: Any, sampled_frames: int) -> dict[str, Any]:
    by_frame: Counter[int] = Counter()
    for annotation in assessment.video_annotations:
        if annotation.kind == "chicken" and annotation.sample_index is not None:
            by_frame[int(annotation.sample_index)] += 1
    counts = [by_frame[index] for index in range(sampled_frames)]
    values = [float(value) for value in counts]
    return {
        "meaning": (
            "accepted individual-sized bird detections per sampled frame; "
            "these observations are not tracked identities and are NOT a unique chicken count"
        ),
        "frames": sampled_frames,
        "total_frame_observations": sum(counts),
        "per_frame_counts": counts,
        "per_frame_summary": {
            "min": min(counts) if counts else None,
            "mean": round(statistics.fmean(values), 3) if values else None,
            "median": round(statistics.median(values), 3) if values else None,
            "p95": round(_percentile(values, 0.95) or 0.0, 3) if values else None,
            "max": max(counts) if counts else None,
        },
    }


def _candidate_report(
    candidate: Any, classifier_call: dict[str, Any] | None
) -> dict[str, Any]:
    classification = candidate.classification
    provenance = candidate.provenance
    crop = candidate.crop
    score_semantics = (
        "raw model ranking scores in [0,1], not calibrated probabilities"
        if classification.inference_performed
        else "deterministic fallback demo scores, not model output or probabilities"
    )
    return {
        "id": candidate.id,
        "timestamp_s": candidate.timestamp_s,
        "detection_confidence": candidate.detection_confidence,
        "bbox_normalized_xywh": candidate.bbox.model_dump(mode="json"),
        "crop": {
            "materialized": crop.materialized,
            "source_video_sha256": crop.source_video_sha256,
            "input_sha256": classification.input_sha256,
            "target_width": crop.target_width,
            "target_height": crop.target_height,
        },
        "persistence": (
            candidate.lifecycle.model_dump(mode="json")
            if candidate.lifecycle is not None
            else None
        ),
        "provenance": (
            provenance.model_dump(mode="json") if provenance is not None else None
        ),
        "classification": {
            "label": classification.label,
            "product_label": classification.product_label,
            "mode": classification.mode,
            "inference_performed": classification.inference_performed,
            "fallback_reason": classification.fallback_reason,
            "score_semantics": score_semantics,
            "top_score": classification.confidence,
            "class_scores": dict(classification.scores),
            "model": (
                classification.model.model_dump(mode="json")
                if classification.model is not None
                else None
            ),
            "inference_call": classifier_call,
        },
    }


def _strict_checks(
    assessment: Any,
    timing: dict[str, Any],
    *,
    require_every_source_frame: bool = False,
    sampling_mode: str | None = None,
    source_frames_estimated: int | None = None,
    decoded_frames: int | None = None,
) -> dict[str, Any]:
    candidates = assessment.summary.feces.candidates
    violations: list[str] = []
    if not candidates:
        violations.append("no persistent feces candidate was retained")
    for candidate in candidates:
        provenance = candidate.provenance
        if provenance is None or provenance.location_source != "observed_video":
            violations.append(f"{candidate.id}: location_source is not observed_video")
        if provenance is None or provenance.appearance_input != "observed_crop":
            violations.append(f"{candidate.id}: appearance_input is not observed_crop")
        if not candidate.crop.materialized:
            violations.append(f"{candidate.id}: observed crop was not materialized")
        if not candidate.classification.inference_performed:
            violations.append(f"{candidate.id}: close-up inference was not performed")
        if candidate.classification.mode != "real":
            violations.append(f"{candidate.id}: classification mode is not real")

    models = timing["models"]
    crop_calls = models["feces_crop_classifier"]["inference_calls"]["count"]
    if crop_calls != len(candidates):
        violations.append(
            "feces crop classifier call count does not equal retained candidate count "
            f"({crop_calls} != {len(candidates)})"
        )
    call_records = models["feces_crop_classifier"].get(
        "inference_call_records", []
    )
    records_by_candidate: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for call in call_records:
        candidate_id = call.get("context", {}).get("candidate_id")
        if candidate_id is not None:
            records_by_candidate[str(candidate_id)].append(call)
    for candidate in candidates:
        matched_calls = records_by_candidate.get(candidate.id, [])
        if len(matched_calls) != 1:
            violations.append(
                f"{candidate.id}: expected exactly one attributed close-up classifier "
                f"call, found {len(matched_calls)}"
            )

    every_source_frame_pass = True
    if require_every_source_frame:
        if sampling_mode != "every_source_frame":
            violations.append(
                "strict every-source-frame mode requires sampling_mode=every_source_frame "
                f"(got {sampling_mode!r})"
            )
            every_source_frame_pass = False
        if (
            source_frames_estimated is None
            or decoded_frames is None
            or source_frames_estimated != decoded_frames
        ):
            violations.append(
                "strict every-source-frame mode requires estimated source frames to equal "
                f"decoded frames ({source_frames_estimated!r} != {decoded_frames!r})"
            )
            every_source_frame_pass = False
    missing_models = [
        name
        for name in MODEL_PATHS
        if models[name]["inference_calls"]["count"] == 0
    ]
    return {
        "strict_real_pipeline_pass": not violations,
        "all_configured_models_executed": not missing_models,
        "overall_pass": not violations and not missing_models,
        "retained_candidate_count": len(candidates),
        "expected_closeup_classifier_calls": len(candidates),
        "actual_closeup_classifier_calls": crop_calls,
        "attributed_closeup_classifier_calls": sum(
            len(records_by_candidate.get(candidate.id, [])) for candidate in candidates
        ),
        "require_every_source_frame": require_every_source_frame,
        "every_source_frame_pass": every_source_frame_pass,
        "missing_model_executions": missing_models,
        "violations": violations,
    }


def _classifier_calls_by_candidate(
    timing: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    calls = timing["models"]["feces_crop_classifier"].get(
        "inference_call_records", []
    )
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for call in calls:
        candidate_id = call.get("context", {}).get("candidate_id")
        if candidate_id is not None:
            grouped[str(candidate_id)].append(call)
    return {
        candidate_id: records[0]
        for candidate_id, records in grouped.items()
        if len(records) == 1
    }


def _resource_report(
    monitor: MemoryMonitor, config: BenchmarkConfig
) -> dict[str, Any]:
    observed = monitor.report()
    return {
        **observed,
        "observed_rss": {
            "measurement": observed["measurement"],
            "sample_interval_ms": observed["sample_interval_ms"],
            "sample_count": observed["sample_count"],
            "max_bytes": observed["max_rss_bytes"],
            "max_mib": observed["max_rss_mib"],
        },
        "internal_monitor": {
            "enforces_os_memory_limit": False,
            "rss_alert_threshold_bytes": observed["ceiling_bytes"],
            "rss_alert_threshold_mib": observed["ceiling_mib"],
            "threshold_crossed": observed["ceiling_crossed"],
            "behavior": (
                "periodic observation plus cooperative fail-stop guards; this is not "
                "an operating-system memory limit"
            ),
        },
        "external_enforcement": {
            "limit_bytes": config.external_memory_limit_bytes,
            "limit_mib": round(
                config.external_memory_limit_bytes / (1024 * 1024), 3
            ),
            "description": config.external_memory_enforcement,
            "reported_by_operator": True,
            "verified_by_harness": False,
        },
    }


def _segment_report(
    config: BenchmarkConfig,
    assessed_video: Any,
    video_result: VideoInferenceResult | None,
    sampled_frames: int,
) -> dict[str, Any]:
    source_frames_estimated = (
        video_result.source_frames_estimated if video_result is not None else None
    )
    return {
        "scope": "selected_segment",
        "requested_selected_segment": {
            "start_s": config.segment_start,
            "end_s": config.segment_end,
        },
        # Retained for schema compatibility with earlier evidence files.
        "requested_start_s": config.segment_start,
        "requested_end_s": config.segment_end,
        "actual_start_s": assessed_video.segment_start_s,
        "actual_end_s": assessed_video.segment_end_s,
        "video_seconds": (
            assessed_video.segment_end_s - assessed_video.segment_start_s
            if assessed_video.segment_end_s is not None
            else assessed_video.duration_s
        ),
        "source_frames_estimated": source_frames_estimated,
        "sampled_frames": sampled_frames,
        # Retained for schema compatibility; these are decoded sampled frames,
        # not a claim that every source frame was decoded.
        "decoded_sampled_frames": sampled_frames,
        "source_frames_skipped_estimated": (
            max(0, source_frames_estimated - sampled_frames)
            if source_frames_estimated is not None
            else None
        ),
        "sampling_mode": (
            video_result.frame_sampling_mode if video_result is not None else None
        ),
    }


def run_benchmark(
    config: BenchmarkConfig,
    *,
    registry: TimingRegistry | None = None,
    monitor: MemoryMonitor | None = None,
    pipeline_builder: Callable[
        [TimingRegistry, MemoryMonitor, int], tuple[Any, Any]
    ] = _build_pipeline,
    probe_fn: Callable[[Path], VideoProbe] = probe_video,
) -> dict[str, Any]:
    clip = config.clip.resolve()
    if not clip.is_file():
        raise FileNotFoundError(f"clip does not exist: {clip}")
    media_type = _media_type(clip)
    if media_type is None:
        raise ValueError(
            "unsupported clip extension; expected mp4, m4v, mov, webm, mkv, or avi"
        )
    registry = registry or TimingRegistry()
    ceiling = (
        int(config.memory_ceiling_mib * 1024 * 1024)
        if config.memory_ceiling_mib is not None
        else None
    )
    monitor = monitor or MemoryMonitor(
        ceiling, interval_s=config.memory_sample_ms / 1000.0
    )
    metadata = _metadata()
    model_artifacts = _model_artifacts()
    clip_sha = _sha256(clip)
    probe = probe_fn(clip)
    pipeline, video_inference = pipeline_builder(registry, monitor, config.threads)
    progress_events: list[dict[str, Any]] = []

    def progress(percent: int, stage: str, message: str) -> None:
        monitor.guard()
        progress_events.append(
            {
                "elapsed_ms": round((registry.clock() - pipeline_started) * 1000, 3),
                "percent": percent,
                "stage": stage,
                "message": message,
            }
        )

    started_cpu = time.process_time()
    started_children = resource.getrusage(resource.RUSAGE_CHILDREN)
    started_child_cpu = started_children.ru_utime + started_children.ru_stime
    with monitor:
        pipeline_started = registry.clock()
        with registry.stage("aggregate_clip_assessment"):
            assessment = pipeline.assess(
                stored=StoredVideo(clip, clip_sha, clip.stat().st_size),
                filename=clip.name,
                media_type=media_type,
                source="upload",
                probe=probe,
                profile=config.profile,
                segment_start_s=config.segment_start,
                segment_end_s=config.segment_end,
                progress=progress,
            )
        total_wall_s = registry.clock() - pipeline_started
        monitor.guard()
    timing = registry.report()
    ended_children = resource.getrusage(resource.RUSAGE_CHILDREN)
    ended_child_cpu = ended_children.ru_utime + ended_children.ru_stime
    python_cpu_s = time.process_time() - started_cpu
    child_cpu_s = max(0.0, ended_child_cpu - started_child_cpu)
    process_tree_cpu_s = python_cpu_s + child_cpu_s
    video_result = getattr(video_inference, "last_result", None)
    sampled_frames = int(
        video_result.frames_sampled
        if video_result is not None
        else assessment.summary.activity.sampled_frames
    )
    segment_report = _segment_report(
        config, assessment.video, video_result, sampled_frames
    )
    segment_duration = segment_report["video_seconds"]
    candidates = assessment.summary.feces.candidates
    source_frames_estimated = segment_report["source_frames_estimated"]
    classifier_calls = _classifier_calls_by_candidate(timing)
    result = {
        "schema_version": 1,
        "status": "completed",
        **metadata,
        "benchmark_contract": {
            "scope": "selected_segment_benchmark",
            "pipeline": "production Simulation Lab adapters",
            "bird_count_semantics": "per-frame observations, not unique tracked birds",
            "feces_count_semantics": "persistent stationary candidates retained across sampled frames",
            "score_semantics": (
                "model scores are raw/normalized ranking scores and are not calibrated probabilities"
            ),
            "stage_timing_semantics": (
                "stage wall clocks are nested and must not be summed; per-model call timings "
                "are contained within their owning stages"
            ),
            "strict_pass_requires": (
                "every retained feces candidate has observed_video location, observed_crop input, "
                "materialized crop, real mode, and inference_performed=true; close-up inference "
                "call count must equal retained candidates"
            ),
        },
        "clip": {
            "path": str(clip),
            "size_bytes": clip.stat().st_size,
            "sha256": clip_sha,
            "duration_s": probe.duration_s,
            "width": probe.width,
            "height": probe.height,
            "fps": probe.fps,
            "metadata_source": probe.source,
        },
        "models": model_artifacts,
        "execution_modules": [
            module.model_dump(mode="json") for module in assessment.modules
        ],
        "segment": segment_report,
        "timing": {
            **timing,
            "total_wall_ms": round(total_wall_s * 1000, 3),
            "python_process_cpu_ms": round(python_cpu_s * 1000, 3),
            "completed_child_process_cpu_ms": round(child_cpu_s * 1000, 3),
            "process_tree_cpu_ms": round(process_tree_cpu_s * 1000, 3),
            "average_process_tree_logical_core_utilization_percent": (
                round(process_tree_cpu_s / total_wall_s * 100, 3)
                if total_wall_s > 0
                else None
            ),
            "video_seconds_per_wall_second": (
                round(segment_duration / total_wall_s, 6)
                if segment_duration is not None and total_wall_s > 0
                else None
            ),
        },
        "resources": _resource_report(monitor, config),
        "progress_events": progress_events,
        "observations": {
            "video_inference_modes": {
                "activity": (
                    video_result.activity_mode if video_result is not None else "fallback"
                ),
                "feces_detector": (
                    video_result.detector_mode if video_result is not None else "fallback"
                ),
            },
            "birds": _bird_summary(assessment, sampled_frames),
            "activity": assessment.summary.activity.model_dump(mode="json"),
            "feces": {
                "persistent_candidate_count": len(candidates),
                "class_distribution": dict(
                    assessment.summary.feces.class_distribution
                ),
                "actual_classification_count": sum(
                    candidate.classification.inference_performed
                    for candidate in candidates
                ),
                "fallback_classification_count": sum(
                    not candidate.classification.inference_performed
                    for candidate in candidates
                ),
                "candidates": [
                    _candidate_report(item, classifier_calls.get(item.id))
                    for item in candidates
                ],
            },
            "pen_aggregate": (
                assessment.summary.pen_assessment.model_dump(mode="json")
                if assessment.summary.pen_assessment is not None
                else None
            ),
        },
    }
    result["validation"] = _strict_checks(
        assessment,
        timing,
        require_every_source_frame=config.require_every_source_frame,
        sampling_mode=(
            video_result.frame_sampling_mode if video_result is not None else None
        ),
        source_frames_estimated=source_frames_estimated,
        decoded_frames=sampled_frames,
    )
    return result


def _media_type(path: Path) -> str | None:
    return {
        ".mp4": "video/mp4",
        ".m4v": "video/mp4",
        ".mov": "video/quicktime",
        ".webm": "video/webm",
        ".mkv": "video/x-matroska",
        ".avi": "video/x-msvideo",
    }.get(path.suffix.lower())


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("clip", type=Path, help="local video file to assess")
    parser.add_argument("--segment-start", type=float, default=0.0)
    parser.add_argument("--segment-end", type=float)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--profile", choices=("healthy", "mixed", "concerning"), default="mixed"
    )
    parser.add_argument(
        "--memory-ceiling-mib",
        type=float,
        default=8192.0,
        help=(
            "aggregate process-tree RSS alert/cooperative fail-stop threshold; "
            "not an OS-enforced limit (default: 8192 MiB)"
        ),
    )
    parser.add_argument(
        "--external-memory-limit-bytes",
        type=int,
        required=True,
        help="memory limit in bytes enforced outside this harness",
    )
    parser.add_argument(
        "--external-memory-enforcement",
        required=True,
        help=(
            "operator-supplied description of the external enforcement mechanism, "
            "for example 'prlimit --as=8589934592 on benchmark process tree'"
        ),
    )
    parser.add_argument("--memory-sample-ms", type=float, default=50.0)
    parser.add_argument("--threads", type=int, default=3)
    parser.add_argument(
        "--require-every-source-frame",
        action="store_true",
        help=(
            "fail validation unless the pipeline reports every_source_frame and the "
            "estimated source-frame count equals decoded frames"
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    config = BenchmarkConfig(
        clip=args.clip,
        segment_start=args.segment_start,
        segment_end=args.segment_end,
        output=args.output,
        profile=args.profile,
        memory_ceiling_mib=args.memory_ceiling_mib,
        memory_sample_ms=args.memory_sample_ms,
        threads=args.threads,
        external_memory_limit_bytes=args.external_memory_limit_bytes,
        external_memory_enforcement=args.external_memory_enforcement,
        require_every_source_frame=args.require_every_source_frame,
    )
    if config.memory_ceiling_mib is not None and config.memory_ceiling_mib <= 0:
        raise SystemExit("--memory-ceiling-mib must be positive")
    if config.memory_sample_ms <= 0:
        raise SystemExit("--memory-sample-ms must be positive")
    if config.threads <= 0:
        raise SystemExit("--threads must be positive")
    if config.external_memory_limit_bytes <= 0:
        raise SystemExit("--external-memory-limit-bytes must be positive")
    if not config.external_memory_enforcement.strip():
        raise SystemExit("--external-memory-enforcement must not be blank")
    registry = TimingRegistry()
    ceiling = (
        int(config.memory_ceiling_mib * 1024 * 1024)
        if config.memory_ceiling_mib is not None
        else None
    )
    monitor = MemoryMonitor(
        ceiling, interval_s=config.memory_sample_ms / 1000.0
    )
    try:
        result = run_benchmark(config, registry=registry, monitor=monitor)
    except BaseException as exc:
        result = {
            "schema_version": 1,
            "status": "failed",
            **_metadata(),
            "error": {"type": type(exc).__name__, "message": str(exc)},
            "partial_timing": registry.report(),
            "resources": _resource_report(monitor, config),
        }
        atomic_write_json(config.output, result)
        print(json.dumps(result, indent=2), file=sys.stderr)
        return 2
    atomic_write_json(config.output, result)
    print(json.dumps(result["validation"], indent=2))
    return 0 if result["validation"]["overall_pass"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
