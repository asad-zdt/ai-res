"""Tests for the run-and-compare API endpoint."""

import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from collector.config_loader import AppSpec
from os_integration.admission import AdmissionDecision
from os_integration.job_manager import Limits
from os_integration.linux_cgroup_manager import LinuxCgroupUnavailable
from service.app import app, run_and_compare
from service.schemas import PredictRequest

client = TestClient(app)
_PREDICTED = {
    "cpu_pct": 20.0,
    "ram_mb": 100.0,
    "disk_mbps": 1.0,
    "net_kbps": 2.0,
}
_ACTUAL = {
    "cpu_pct": 18.0,
    "ram_mb": 90.0,
    "disk_mbps": 0.8,
    "net_kbps": 1.5,
}


def _spec() -> AppSpec:
    """Return a minimal test workload spec."""
    return AppSpec(
        name="cpu_burn",
        category="synthetic_cpu",
        command=("python",),
        cwd=".",
        timeout_s=5.0,
        variants=(("--seconds", "1"), ("--seconds", "2")),
        exe=Path("python"),
        exe_size_mb=1.0,
    )


def _decision(admitted: bool = True) -> AdmissionDecision:
    """Return a predictable admission decision."""
    return AdmissionDecision(
        admitted=admitted,
        reason=None if admitted else "insufficient resources",
        limits=Limits(cpu_cores=0.5, memory_mb=256.0),
        niceness=5,
    )


def _fake_launch(*args, **kwargs):
    """Create a fake launched process for endpoint tests."""
    return SimpleNamespace(
        popen=SimpleNamespace(pid=12345, wait=lambda: 0),
        tmp_dir=Path("temporary"),
    )


def _patch_common(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch prediction and registry loading for a configured app."""
    monkeypatch.setenv("PREDICTOR", "mock")
    monkeypatch.setattr("service.app.load_apps", lambda: {"cpu_burn": _spec()})
    monkeypatch.setattr("service.app.mock_predict", lambda app_name: _PREDICTED)
    monkeypatch.setattr("service.app.admission.decide", lambda predicted: _decision())
    monkeypatch.setattr("service.app.launcher.launch", _fake_launch)
    monkeypatch.setattr("service.app.launcher.resume", lambda launched: None)
    monkeypatch.setattr(
        "service.app.monitor.monitor_process",
        lambda popen, timeout_s: [object(), object(), object()],
    )
    monkeypatch.setattr("service.app.monitor.summarize", lambda samples: _ACTUAL)
    monkeypatch.setattr("service.app.launcher.cleanup", lambda launched: None)
    monkeypatch.setattr("service.app.set_priority", lambda pid, level: level)


def test_run_and_compare_success_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """The success path returns prediction, actuals, and enforcement fields."""
    _patch_common(monkeypatch)

    class AvailableJobManager:
        def is_available(self) -> bool:
            return True

        def create(self, limits: Limits) -> object:
            return object()

        def attach(self, handle: object, pid: int) -> None:
            return None

        def usage(self, handle: object) -> dict[str, bool]:
            return {"limit_reached": False}

        def cleanup(self, handle: object) -> None:
            return None

    monkeypatch.setattr(
        "service.app.create_enforcement_manager",
        AvailableJobManager,
    )
    response = client.post("/run-and-compare", json={"app_name": "cpu_burn"})

    assert response.status_code == 200
    body = response.json()
    assert body["predicted"] == _PREDICTED
    assert body["actual"] == _ACTUAL
    assert body["enforcement"] == {
        "admitted": True,
        "reason": None,
        "niceness": 5,
        "cgroup_applied": True,
    }


def test_run_and_compare_unknown_app_returns_404(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Names missing from the configured app registry return 404."""
    _patch_common(monkeypatch)
    monkeypatch.setattr("service.app.load_apps", lambda: {})

    response = client.post("/run-and-compare", json={"app_name": "unknown"})

    assert response.status_code == 404
    assert response.json() == {"detail": "Unknown app: unknown"}


def test_run_and_compare_refused_admission_returns_409(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Admission refusals are returned without launching a process."""
    _patch_common(monkeypatch)
    monkeypatch.setattr(
        "service.app.admission.decide",
        lambda predicted: _decision(admitted=False),
    )
    launch_calls: list[bool] = []
    monkeypatch.setattr(
        "service.app.launcher.launch",
        lambda *args, **kwargs: launch_calls.append(True),
    )

    response = client.post("/run-and-compare", json={"app_name": "cpu_burn"})

    assert response.status_code == 409
    assert response.json() == {"detail": "insufficient resources"}
    assert launch_calls == []


def test_run_and_compare_without_job_objects_continues(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing Job Object capability is reported without blocking a run."""
    _patch_common(monkeypatch)

    class UnavailableJobManager:
        def is_available(self) -> bool:
            return False

    monkeypatch.setattr(
        "service.app.create_enforcement_manager",
        UnavailableJobManager,
    )
    response = client.post("/run-and-compare", json={"app_name": "cpu_burn"})

    assert response.status_code == 200
    enforcement = response.json()["enforcement"]
    assert enforcement["cgroup_applied"] is False
    expected_reason = (
        "Linux cgroups v2 are unavailable"
        if os.name != "nt"
        else "Windows Job Objects are unavailable"
    )
    assert expected_reason in enforcement["reason"]


def test_linux_run_and_compare_falls_back_when_cgroups_are_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A Linux cgroup setup denial continues with nice priority only."""
    _patch_common(monkeypatch)
    monkeypatch.setattr("service.app.sys.platform", "linux")

    class UnavailableCgroupManager:
        def is_available(self) -> bool:
            return True

        def create(self, limits: Limits) -> object:
            raise LinuxCgroupUnavailable("permission denied")

    monkeypatch.setattr(
        "service.app.create_enforcement_manager",
        UnavailableCgroupManager,
    )

    response = client.post("/run-and-compare", json={"app_name": "cpu_burn"})

    assert response.status_code == 200
    enforcement = response.json()["enforcement"]
    assert enforcement["cgroup_applied"] is False
    assert "continues with niceness only: permission denied" in enforcement["reason"]


def test_run_and_compare_cleans_up_on_monitor_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Launched process resources are cleaned even when monitoring fails."""
    _patch_common(monkeypatch)

    class UnavailableJobManager:
        def is_available(self) -> bool:
            return False

    monkeypatch.setattr(
        "service.app.create_enforcement_manager",
        UnavailableJobManager,
    )
    launched = _fake_launch()
    monkeypatch.setattr("service.app.launcher.launch", lambda *args, **kwargs: launched)

    def fail_monitor(*args, **kwargs):
        raise RuntimeError("monitor failed")

    cleanup_calls: list[object] = []
    monkeypatch.setattr("service.app.monitor.monitor_process", fail_monitor)
    monkeypatch.setattr(
        "service.app.launcher.cleanup",
        lambda item: cleanup_calls.append(item),
    )

    with pytest.raises(RuntimeError, match="monitor failed"):
        run_and_compare(PredictRequest(app_name="cpu_burn"))
    assert cleanup_calls == [launched]


def test_run_and_compare_closes_job_on_monitor_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Close the Job Object and launched workload when monitoring raises."""
    _patch_common(monkeypatch)
    launched = _fake_launch()
    monkeypatch.setattr(
        "service.app.launcher.launch",
        lambda *args, **kwargs: launched,
    )

    class AvailableJobManager:
        def __init__(self) -> None:
            self.handle = object()
            self.cleaned: list[object] = []

        def is_available(self) -> bool:
            return True

        def create(self, limits: Limits) -> object:
            return self.handle

        def attach(self, handle: object, pid: int) -> None:
            return None

        def usage(self, handle: object) -> dict[str, bool]:
            return {"limit_reached": False}

        def cleanup(self, handle: object) -> None:
            self.cleaned.append(handle)

    manager = AvailableJobManager()
    monkeypatch.setattr("service.app.create_enforcement_manager", lambda: manager)

    def fail_monitor(*args, **kwargs):
        raise RuntimeError("monitor failed")

    monkeypatch.setattr("service.app.monitor.monitor_process", fail_monitor)
    launched_cleanup: list[object] = []
    monkeypatch.setattr(
        "service.app.launcher.cleanup",
        launched_cleanup.append,
    )

    with pytest.raises(RuntimeError, match="monitor failed"):
        run_and_compare(PredictRequest(app_name="cpu_burn"))

    assert manager.cleaned == [manager.handle]
    assert launched_cleanup == [launched]
