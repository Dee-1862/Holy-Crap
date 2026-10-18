from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/benchmark_full_pipeline.py"
SPEC = importlib.util.spec_from_file_location("benchmark_full_pipeline", SCRIPT)
assert SPEC and SPEC.loader
benchmark = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = benchmark
SPEC.loader.exec_module(benchmark)


class _Input:
    name = "images"


class _FakeSession:
    def __init__(self) -> None:
        self.calls = 0

    def get_inputs(self):
        return [_Input()]

    def run(self, _outputs, _inputs):
        self.calls += 1
        return [[self.calls]]


class _Clock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        self.value += 0.001
        return self.value


def test_distribution_reports_every_latency_statistic() -> None:
    result = benchmark.distribution([0.001, 0.002, 0.003, 0.004])

    assert result == {
        "count": 4,
        "total_ms": 10.0,
        "min_ms": 1.0,
        "mean_ms": 2.5,
        "median_ms": 2.5,
        "p95_ms": 3.85,
        "p99_ms": 3.97,
        "max_ms": 4.0,
    }


def test_fake_session_factory_records_init_and_each_inference(tmp_path: Path) -> None:
    model = tmp_path / "fixture.onnx"
    model.write_bytes(b"fixture")
    clock = _Clock()
    registry = benchmark.TimingRegistry(clock=clock)
    guarded = []
    factory = benchmark.timed_session_factory(
        registry=registry,
        memory_guard=lambda: guarded.append(True),
        threads=2,
        loader=lambda path, threads: _FakeSession(),
    )

    session = factory(model)
    assert session.get_inputs()[0].name == "images"
    with registry.model_call_context(candidate_id="feces-001"):
        assert session.run(None, {"images": "first"}) == [[1]]
    with registry.model_call_context(candidate_id="feces-002"):
        assert session.run(None, {"images": "second"}) == [[2]]

    report = registry.report()["models"]["fixture"]
    assert report["session_initialization"]["count"] == 1
    assert report["inference_calls"]["count"] == 2
    assert report["cold_first_inference_call"]["count"] == 1
    assert report["cold_first_inference_call"]["mean_ms"] == 1.0
    assert report["steady_state_inference_calls"]["count"] == 1
    assert report["every_inference_call_ms"] == [1.0, 1.0]
    assert report["inference_call_records"] == [
        {
            "call_order": 1,
            "latency_ms": 1.0,
            "cold_first_call": True,
            "context": {"candidate_id": "feces-001"},
        },
        {
            "call_order": 2,
            "latency_ms": 1.0,
            "cold_first_call": False,
            "context": {"candidate_id": "feces-002"},
        },
    ]
    assert len(guarded) == 5


def _candidate(
    candidate_id: str,
    *,
    location: str = "observed_video",
    appearance: str = "observed_crop",
    inferred: bool = True,
):
    return SimpleNamespace(
        id=candidate_id,
        crop=SimpleNamespace(materialized=True),
        classification=SimpleNamespace(inference_performed=inferred, mode="real"),
        provenance=SimpleNamespace(
            location_source=location, appearance_input=appearance
        ),
    )


def _timing(crop_calls: int, *, behavior_calls: int = 1):
    return {
        "models": {
            "chicken_detector": {"inference_calls": {"count": 3}},
            "behavior_classifier": {"inference_calls": {"count": behavior_calls}},
            "pen_feces_locator": {"inference_calls": {"count": 3}},
            "feces_crop_classifier": {
                "inference_calls": {"count": crop_calls},
                "inference_call_records": [
                    {
                        "call_order": index + 1,
                        "latency_ms": 10.0 + index,
                        "cold_first_call": index == 0,
                        "context": {"candidate_id": f"feces-{index + 1:03d}"},
                    }
                    for index in range(crop_calls)
                ],
            },
        }
    }


def test_classifier_call_mapping_uses_explicit_candidate_context() -> None:
    mapped = benchmark._classifier_calls_by_candidate(_timing(2))

    assert mapped["feces-001"]["latency_ms"] == 10.0
    assert mapped["feces-001"]["cold_first_call"] is True
    assert mapped["feces-002"]["call_order"] == 2


def test_strict_validation_requires_real_observed_crop_per_candidate() -> None:
    assessment = SimpleNamespace(
        summary=SimpleNamespace(
            feces=SimpleNamespace(candidates=[_candidate("feces-001")])
        )
    )

    result = benchmark._strict_checks(assessment, _timing(1))

    assert result["strict_real_pipeline_pass"] is True
    assert result["all_configured_models_executed"] is True
    assert result["overall_pass"] is True


def test_strict_validation_rejects_proxy_fallback_and_skipped_model() -> None:
    assessment = SimpleNamespace(
        summary=SimpleNamespace(
            feces=SimpleNamespace(
                candidates=[
                    _candidate(
                        "feces-001",
                        location="deterministic_overlay",
                        appearance="curated_proxy",
                        inferred=False,
                    )
                ]
            )
        )
    )

    result = benchmark._strict_checks(
        assessment, _timing(0, behavior_calls=0)
    )

    assert result["strict_real_pipeline_pass"] is False
    assert result["overall_pass"] is False
    assert "behavior_classifier" in result["missing_model_executions"]
    assert any("appearance_input" in item for item in result["violations"])
    assert any("call count" in item for item in result["violations"])


def test_memory_monitor_flags_aggregate_process_tree_ceiling() -> None:
    samples = iter([10, 20, 101, 90])
    monitor = benchmark.MemoryMonitor(
        100,
        interval_s=60,
        root_pid=123,
        sampler=lambda _pid: next(samples, 90),
    )

    monitor._sample()
    monitor._sample()
    monitor._sample()

    assert monitor.max_rss_bytes == 101
    assert monitor.limit_crossed is True
    try:
        monitor.guard()
    except benchmark.MemoryCeilingExceeded:
        pass
    else:
        raise AssertionError("memory ceiling must fail closed")


def test_resource_report_separates_observation_from_external_enforcement() -> None:
    monitor = benchmark.MemoryMonitor(100, sampler=lambda _pid: 90)
    monitor._sample()
    config = SimpleNamespace(
        external_memory_limit_bytes=8 * 1024**3,
        external_memory_enforcement="prlimit --as=8589934592",
    )

    report = benchmark._resource_report(monitor, config)

    assert report["observed_rss"]["max_bytes"] == 90
    assert report["internal_monitor"]["enforces_os_memory_limit"] is False
    assert report["external_enforcement"] == {
        "limit_bytes": 8 * 1024**3,
        "limit_mib": 8192.0,
        "description": "prlimit --as=8589934592",
        "reported_by_operator": True,
        "verified_by_harness": False,
    }


def test_git_metadata_marks_dirty_unknown_when_git_status_unavailable(monkeypatch) -> None:
    def fake_run(command, **_kwargs):
        arguments = command[1:]
        if arguments == ["rev-parse", "--is-inside-work-tree"]:
            return SimpleNamespace(returncode=0, stdout="true\n")
        if arguments == ["rev-parse", "HEAD"]:
            return SimpleNamespace(returncode=0, stdout="abc123\n")
        if arguments == ["branch", "--show-current"]:
            return SimpleNamespace(returncode=0, stdout="feature\n")
        if arguments == ["status", "--porcelain"]:
            return SimpleNamespace(returncode=128, stdout="")
        raise AssertionError(arguments)

    monkeypatch.setattr(benchmark.subprocess, "run", fake_run)
    monkeypatch.setattr(benchmark, "_tool_version", lambda _name: None)

    metadata = benchmark._metadata()

    assert metadata["git"] == {
        "git_available": True,
        "commit": "abc123",
        "branch": "feature",
        "dirty": None,
    }


def test_git_metadata_marks_git_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(
        benchmark.subprocess,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(FileNotFoundError()),
    )
    monkeypatch.setattr(benchmark, "_tool_version", lambda _name: None)

    metadata = benchmark._metadata()

    assert metadata["git"]["git_available"] is False
    assert metadata["git"]["dirty"] is None


def test_every_source_frame_strict_mode_rejects_sampling_or_count_mismatch() -> None:
    assessment = SimpleNamespace(
        summary=SimpleNamespace(
            feces=SimpleNamespace(candidates=[_candidate("feces-001")])
        )
    )

    sampled = benchmark._strict_checks(
        assessment,
        _timing(1),
        require_every_source_frame=True,
        sampling_mode="uniform_bounded_sample",
        source_frames_estimated=100,
        decoded_frames=20,
    )
    complete = benchmark._strict_checks(
        assessment,
        _timing(1),
        require_every_source_frame=True,
        sampling_mode="every_source_frame",
        source_frames_estimated=100,
        decoded_frames=100,
    )

    assert sampled["every_source_frame_pass"] is False
    assert sampled["overall_pass"] is False
    assert complete["every_source_frame_pass"] is True
    assert complete["overall_pass"] is True


def test_segment_report_names_requested_sampled_and_skipped_frames() -> None:
    config = SimpleNamespace(segment_start=4.0, segment_end=24.0)
    assessed = SimpleNamespace(
        segment_start_s=4.0,
        segment_end_s=24.0,
        duration_s=60.0,
    )
    video_result = SimpleNamespace(
        source_frames_estimated=100,
        frame_sampling_mode="uniform_bounded_sample",
    )

    report = benchmark._segment_report(config, assessed, video_result, 20)

    assert report["scope"] == "selected_segment"
    assert report["requested_selected_segment"] == {"start_s": 4.0, "end_s": 24.0}
    assert report["source_frames_estimated"] == 100
    assert report["sampled_frames"] == 20
    assert report["source_frames_skipped_estimated"] == 80


def test_cli_requires_explicit_external_memory_enforcement() -> None:
    parser = benchmark._parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["clip.mp4", "--output", "report.json"])

    args = parser.parse_args(
        [
            "clip.mp4",
            "--output",
            "report.json",
            "--external-memory-limit-bytes",
            "8589934592",
            "--external-memory-enforcement",
            "prlimit --as=8589934592",
            "--require-every-source-frame",
        ]
    )
    assert args.external_memory_limit_bytes == 8589934592
    assert args.external_memory_enforcement.startswith("prlimit")
    assert args.require_every_source_frame is True


def test_atomic_json_write_replaces_complete_document(tmp_path: Path) -> None:
    destination = tmp_path / "evidence" / "result.json"
    benchmark.atomic_write_json(destination, {"run": 1})
    benchmark.atomic_write_json(destination, {"run": 2, "complete": True})

    assert json.loads(destination.read_text()) == {"run": 2, "complete": True}
    assert not list(destination.parent.glob(f".{destination.name}.*"))
