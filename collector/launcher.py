"""Launch configured workloads without opening console windows."""

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import psutil

from collector.config_loader import AppSpec

_PROCESS_ERRORS = (
    psutil.NoSuchProcess,
    psutil.AccessDenied,
    psutil.ZombieProcess,
)


@dataclass
class LaunchedApp:
    """A launched application and its per-run temporary directory."""

    popen: subprocess.Popen[bytes]
    tmp_dir: Path


def launch(
    spec: AppSpec,
    variant_index: int = 0,
    suspended: bool = False,
) -> LaunchedApp:
    """Launch one configured app variant, optionally suspended on Windows."""
    tmp_dir = Path(tempfile.mkdtemp(prefix=f"{spec.name}_"))
    try:
        command = spec.command_for_run(tmp_dir, variant_index)
        working_directory = spec.working_directory_for_run(tmp_dir)
        creationflags = 0
        if os.name == "nt":
            creationflags |= subprocess.CREATE_NEW_PROCESS_GROUP
            creationflags |= subprocess.CREATE_NO_WINDOW
            if suspended:
                creationflags |= 0x00000004

        process = subprocess.Popen(
            command,
            cwd=working_directory,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=False,
            creationflags=creationflags,
        )
    except BaseException:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise
    return LaunchedApp(popen=process, tmp_dir=tmp_dir)


def resume(launched: LaunchedApp) -> None:
    """Resume a process that was created in a suspended state."""
    psutil.Process(launched.popen.pid).resume()


def _terminate_process_tree(root: psutil.Process) -> None:
    """Terminate a process tree child-first and kill survivors."""
    try:
        descendants = root.children(recursive=True)
    except _PROCESS_ERRORS:
        descendants = []
    processes = [*reversed(descendants), root]

    for process in processes:
        try:
            process.terminate()
        except _PROCESS_ERRORS:
            continue

    _, survivors = psutil.wait_procs(processes, timeout=3)
    for process in survivors:
        try:
            process.kill()
        except _PROCESS_ERRORS:
            continue
    if survivors:
        psutil.wait_procs(survivors, timeout=3)


def cleanup(launched: LaunchedApp) -> None:
    """Stop any remaining process tree and remove the run's temp directory."""
    try:
        if launched.popen.poll() is None:
            try:
                _terminate_process_tree(psutil.Process(launched.popen.pid))
            except _PROCESS_ERRORS:
                pass
            try:
                launched.popen.wait(timeout=3)
            except subprocess.TimeoutExpired:
                launched.popen.kill()
                launched.popen.wait()
    finally:
        shutil.rmtree(launched.tmp_dir, ignore_errors=True)
