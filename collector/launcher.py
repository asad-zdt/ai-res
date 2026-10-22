"""Launch configured workloads without opening console windows."""

import os
import shutil
import subprocess
import sys
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
    resume_fd: int | None = None


def launch(
    spec: AppSpec,
    variant_index: int = 0,
    suspended: bool = False,
) -> LaunchedApp:
    """Launch a workload, suspended on Windows or gated on Linux when requested."""
    tmp_dir = Path(tempfile.mkdtemp(prefix=f"{spec.name}_"))
    resume_fd: int | None = None
    read_fd: int | None = None
    try:
        command = spec.command_for_run(tmp_dir, variant_index)
        working_directory = spec.working_directory_for_run(tmp_dir)
        creationflags = 0
        pass_fds: tuple[int, ...] = ()
        if os.name == "nt":
            creationflags |= subprocess.CREATE_NEW_PROCESS_GROUP
            creationflags |= subprocess.CREATE_NO_WINDOW
            if suspended:
                creationflags |= 0x00000004
        elif sys.platform == "linux" and suspended:
            read_fd, resume_fd = os.pipe()
            gate_code = (
                "import os, sys; fd = int(sys.argv[1]); "
                "ready = os.read(fd, 1); os.close(fd); "
                "ready or sys.exit(125); "
                "os.execvpe(sys.argv[2], sys.argv[2:], os.environ)"
            )
            command = [sys.executable, "-c", gate_code, str(read_fd), *command]
            pass_fds = (read_fd,)

        try:
            if pass_fds:
                process = subprocess.Popen(
                    command,
                    cwd=working_directory,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    shell=False,
                    creationflags=creationflags,
                    pass_fds=pass_fds,
                )
            else:
                process = subprocess.Popen(
                    command,
                    cwd=working_directory,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    shell=False,
                    creationflags=creationflags,
                )
        finally:
            if read_fd is not None:
                os.close(read_fd)
    except BaseException:
        if resume_fd is not None:
            os.close(resume_fd)
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise
    return LaunchedApp(popen=process, tmp_dir=tmp_dir, resume_fd=resume_fd)


def resume(launched: LaunchedApp) -> None:
    """Resume or release a process held before workload execution."""
    if launched.resume_fd is not None:
        try:
            os.write(launched.resume_fd, b"go")
        finally:
            os.close(launched.resume_fd)
            launched.resume_fd = None
        return
    if os.name != "nt":
        return
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
        if launched.resume_fd is not None:
            os.close(launched.resume_fd)
            launched.resume_fd = None
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
