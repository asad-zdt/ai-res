"""FastAPI application for resource predictions."""

import os
import sys
import threading
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from collector import launcher, monitor
from collector.config_loader import AppSpec
from collector.user_apps import load_all_apps
from config import resolve_path
from errors import UnknownAppError
from model.predict import predict as model_predict
from os_integration import admission
from os_integration.factory import create_enforcement_manager
from os_integration.job_manager import JobUnavailable
from os_integration.linux_cgroup_manager import (
    LinuxCgroupCleanupError,
    LinuxCgroupUnavailable,
)
from os_integration.priority import set_priority
from service.mock_predict import mock_predict
from service.schemas import (
    EnforcementInfo,
    PredictRequest,
    PredictResponse,
    RunAndCompareResponse,
    ResourceMetrics,
)


def _active_predictor() -> str:
    """Select the configured predictor or choose based on model availability."""
    configured = os.getenv("PREDICTOR")
    if configured is not None:
        predictor = configured.strip().lower()
        if predictor not in {"mock", "model"}:
            raise ValueError("PREDICTOR must be 'mock' or 'model'")
        return predictor

    configured_model_path = os.getenv("MODEL_PATH", "model/artifacts/model.pkl")
    path = Path(configured_model_path)
    model_path = path if path.is_absolute() else resolve_path(configured_model_path)
    return "model" if model_path.is_file() else "mock"


app = FastAPI()
_RUN_LOCK = threading.Lock()


def load_apps() -> dict[str, AppSpec]:
    """Load configured workloads and locally selected desktop applications."""
    return load_all_apps()


app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8501"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    """Report the API health and configured predictor."""
    return {"status": "ok", "predictor": _active_predictor()}


@app.post("/predict", response_model=PredictResponse)
def predict(request: PredictRequest) -> PredictResponse:
    """Return a resource prediction using the active predictor."""
    if request.app_name not in load_apps():
        raise HTTPException(
            status_code=404, detail=f"Unknown app: {request.app_name}"
        )

    predictor = _active_predictor()
    try:
        if predictor == "model":
            predicted = model_predict(request.app_name)
        else:
            predicted = mock_predict(request.app_name)
    except UnknownAppError:
        # Model bundle exists but has no profile for this app yet (e.g. it was
        # collected after the last train run). Fall back to the mock predictor
        # so the GUI never shows a hard 503 for a configured app.
        try:
            predicted = mock_predict(request.app_name)
            predictor = "mock"
        except UnknownAppError as error:
            raise HTTPException(
                status_code=503,
                detail=f"No prediction profile available for configured app: {error.app_name}",
            ) from error
    return PredictResponse(
        app_name=request.app_name,
        predicted=predicted,
        source=predictor,
    )


@app.post("/run-and-compare", response_model=RunAndCompareResponse)
def run_and_compare(request: PredictRequest) -> RunAndCompareResponse:
    """Admit, launch, measure, and report one configured workload run."""
    with _RUN_LOCK:
        apps = load_apps()
        spec = apps.get(request.app_name)
        if spec is None:
            raise HTTPException(
                status_code=404,
                detail=f"Unknown app: {request.app_name}",
            )

        predictor = _active_predictor()
        try:
            if predictor == "model":
                predicted = model_predict(request.app_name)
            else:
                predicted = mock_predict(request.app_name)
        except UnknownAppError:
            # Model has no profile for this app yet — fall back to mock.
            try:
                predicted = mock_predict(request.app_name)
                predictor = "mock"
            except UnknownAppError as error:
                raise HTTPException(
                    status_code=503,
                    detail=(
                        "No prediction profile available for configured app: "
                        f"{error.app_name}"
                    ),
                ) from error

        decision = admission.decide(predicted)
        if not decision.admitted:
            raise HTTPException(status_code=409, detail=decision.reason)

        manager = create_enforcement_manager()
        job_handle = None
        launched = None
        actual: dict[str, float] | None = None
        usage: dict[str, float | int | bool] | None = None
        duration_s = 0.0
        cgroup_applied = False
        enforcement_reasons: list[str] = []
        applied_niceness = 0
        if decision.limits is None:
            raise HTTPException(
                status_code=500,
                detail="Admission decision did not include resource limits.",
            )

        start_time = time.monotonic()
        try:
            launched = launcher.launch(spec, suspended=True)
            applied_niceness = set_priority(
                launched.popen.pid,
                decision.niceness,
            )
            if applied_niceness != decision.niceness:
                enforcement_reasons.append(
                    f"Could not apply requested nice/priority level "
                    f"{decision.niceness}; applied level {applied_niceness}."
                )

            if manager.is_available():
                try:
                    job_handle = manager.create(decision.limits)
                except LinuxCgroupCleanupError:
                    raise
                except LinuxCgroupUnavailable as error:
                    enforcement_reasons.append(
                        "Linux cgroups v2 limits were unavailable; the run "
                        f"continues with niceness only: {error}"
                    )
                if job_handle is not None:
                    manager.attach(job_handle, launched.popen.pid)
                    cgroup_applied = True
            else:
                if sys.platform == "linux":
                    enforcement_reasons.append(
                        "Linux cgroups v2 are unavailable; CPU and memory caps "
                        "were not applied."
                    )
                else:
                    enforcement_reasons.append(
                        "Windows Job Objects are unavailable; CPU and memory "
                        "caps were not applied."
                    )

            launcher.resume(launched)
            samples = monitor.monitor_process(
                launched.popen,
                timeout_s=spec.timeout_s,
            )
            actual = monitor.summarize(samples)
            launched.popen.wait()
        except (JobUnavailable, LinuxCgroupUnavailable) as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
        finally:
            duration_s = time.monotonic() - start_time
            try:
                if job_handle is not None:
                    try:
                        usage = manager.usage(job_handle)
                    except (JobUnavailable, LinuxCgroupUnavailable) as error:
                        enforcement_reasons.append(
                            f"Could not read OS enforcement usage: {error}"
                        )
                    finally:
                        manager.cleanup(job_handle)
            finally:
                if launched is not None:
                    launcher.cleanup(launched)

        if actual is None:
            raise HTTPException(
                status_code=500,
                detail="Workload completed without resource measurements.",
            )
        if usage is not None and usage.get("limit_reached"):
            limit_type = (
                "cgroup memory"
                if sys.platform == "linux"
                else "Job Object memory"
            )
            enforcement_reasons.append(
                f"The {limit_type} limit was reached during the run."
            )
        return RunAndCompareResponse(
            app_name=request.app_name,
            predicted=ResourceMetrics(**predicted),
            actual=ResourceMetrics(**actual),
            duration_s=duration_s,
            enforcement=EnforcementInfo(
                admitted=True,
                reason=" ".join(enforcement_reasons) or None,
                niceness=applied_niceness,
                cgroup_applied=cgroup_applied,
            ),
        )
