from __future__ import annotations

import importlib
import sys
import threading
from pathlib import Path

import pytest


EDGE = Path(__file__).resolve().parents[1] / "target" / "qnx" / "edge"


def load_model(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.syspath_prepend(str(EDGE))
    sys.modules.pop("model", None)
    return importlib.import_module("model")


def test_latest_work_pool_evicts_oldest_waiting_item_without_interrupting_running_work(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = load_model(monkeypatch)
    running = threading.Event()
    release = threading.Event()
    finished: list[int] = []

    def work(item: int) -> None:
        if item == 0:
            running.set()
            assert release.wait(timeout=2)
        finished.append(item)

    pool = model.LatestWorkPool(workers=1, pending=2, callback=work)
    try:
        assert pool.submit(0) == "accepted"
        assert running.wait(timeout=2)
        assert pool.submit(1) == "accepted"
        assert pool.submit(2) == "accepted"
        assert pool.submit(3) == "evicted_oldest"
        release.set()
        pool.shutdown(wait=True)
    finally:
        release.set()
        pool.shutdown(wait=True, cancel_pending=True)

    assert finished == [0, 2, 3]


def test_latest_work_pool_keeps_workers_alive_after_item_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = load_model(monkeypatch)
    finished: list[int] = []

    def work(item: int) -> None:
        if item == 1:
            raise RuntimeError("fixture failure")
        finished.append(item)

    pool = model.LatestWorkPool(workers=1, pending=2, callback=work)
    assert pool.submit(1) == "accepted"
    assert pool.submit(2) == "accepted"
    pool.shutdown(wait=True)

    assert finished == [2]


def test_latest_work_pool_reports_callback_failures_without_killing_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = load_model(monkeypatch)
    failures: list[tuple[str, tuple[int, ...]]] = []
    finished: list[int] = []

    def work(item: int) -> None:
        if item == 1:
            raise RuntimeError("fixture failure")
        finished.append(item)

    def failed(exc: Exception, args: tuple[int, ...]) -> None:
        failures.append((type(exc).__name__, args))

    pool = model.LatestWorkPool(
        workers=1, pending=2, callback=work, error_callback=failed
    )
    assert pool.submit(1) == "accepted"
    assert pool.submit(2) == "accepted"
    pool.shutdown(wait=True)

    assert failures == [("RuntimeError", (1,))]
    assert finished == [2]


def test_latest_work_pool_shutdown_can_cancel_waiting_work_and_rejects_new_work(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = load_model(monkeypatch)
    running = threading.Event()
    release = threading.Event()
    finished: list[int] = []

    def work(item: int) -> None:
        running.set()
        assert release.wait(timeout=2)
        finished.append(item)

    pool = model.LatestWorkPool(workers=1, pending=2, callback=work)
    assert pool.submit(0) == "accepted"
    assert running.wait(timeout=2)
    assert pool.submit(1) == "accepted"
    assert pool.submit(2) == "accepted"

    assert pool.shutdown(wait=False, cancel_pending=True) == 2
    assert pool.submit(3) == "dropped"
    release.set()
    assert pool.shutdown(wait=True) == 0

    assert finished == [0]
