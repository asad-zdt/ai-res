"""FastAPI application for resource predictions."""

import os
import threading
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from collector import launcher, monitor
from collector.config_loader import load_apps
from config import resolve_path
from errors import UnknownAppError
from model.predict import predict as model_predict
from os_integration import admission
from os_integration.job_manager import JobManager, JobUnavailable
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

        manager = JobManager()
        job_handle = None
        launched = None
        actual: dict[str, float] | None = None
        usage: dict[str, float | int | bool] | None = None
        duration_s = 0.0
        cgroup_applied = False
        enforcement_reasons: list[str] = []
        if decision.limits is None:
            raise HTTPException(
                status_code=500,
                detail="Admission decision did not include resource limits.",
            )

        start_time = time.monotonic()
        try:
            launched = launcher.launch(spec, suspended=True)
            set_priority(launched.popen.pid, decision.niceness)

            if manager.is_available():
                job_handle = manager.create(decision.limits)
                manager.attach(job_handle, launched.popen.pid)
                cgroup_applied = True
            else:
                enforcement_reasons.append(
                    "Windows Job Objects are unavailable; CPU and memory caps were not applied."
                )

            launcher.resume(launched)
            samples = monitor.monitor_process(
                launched.popen,
                timeout_s=spec.timeout_s,
            )
            actual = monitor.summarize(samples)
            launched.popen.wait()
        except JobUnavailable as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
        finally:
            duration_s = time.monotonic() - start_time
            try:
                if job_handle is not None:
                    try:
                        usage = manager.usage(job_handle)
                    except JobUnavailable as error:
                        enforcement_reasons.append(
                            f"Could not read Job Object usage: {error}"
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
            enforcement_reasons.append(
                "The Job Object memory limit was reached during the run."
            )
        return RunAndCompareResponse(
            app_name=request.app_name,
            predicted=ResourceMetrics(**predicted),
            actual=ResourceMetrics(**actual),
            duration_s=duration_s,
            enforcement=EnforcementInfo(
                admitted=True,
                reason=" ".join(enforcement_reasons) or None,
                niceness=decision.niceness,
                cgroup_applied=cgroup_applied,
            ),
        )
