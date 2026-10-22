"""Linux task dispatcher for setup, collection, API, GUI, and tests."""

import argparse
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from config import REPO_ROOT

_TASK_ARGUMENTS = {
    "collect": ["-m", "collector.run_logger", "--runs", "8"],
    "dataset": ["-m", "features.build_dataset"],
    "train": ["-m", "model.train", "--data", "data/processed/dataset.csv"],
    "eval": ["-m", "model.evaluate"],
    "api": [
        "-m",
        "uvicorn",
        "service.app:app",
        "--host",
        "127.0.0.1",
        "--port",
        "8000",
    ],
    "gui": ["-m", "gui.tk_app"],
    "test": ["-m", "pytest", "-q"],
    "e2e": ["scripts/e2e.py"],
}


def _venv_python() -> Path:
    """Return the repository virtual environment's Linux Python executable."""
    return REPO_ROOT / ".venv" / "bin" / "python"


def _run(command: list[str]) -> None:
    """Run one command from the repository root and report its failure."""
    completed = subprocess.run(command, cwd=REPO_ROOT, check=False)
    if completed.returncode:
        raise SystemExit(completed.returncode)


def main() -> None:
    """Run the requested Linux project task."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "task",
        choices=("setup", *_TASK_ARGUMENTS),
    )
    task = parser.parse_args().task

    if sys.platform != "linux":
        parser.error("Linux tasks can only run on Linux.")
    if task == "setup":
        _run([sys.executable, "-m", "venv", str(REPO_ROOT / ".venv")])
        _run(
            [
                str(_venv_python()),
                "-m",
                "pip",
                "install",
                "-r",
                str(REPO_ROOT / "requirements.txt"),
            ]
        )
        return

    python = _venv_python()
    if not python.is_file():
        parser.error("Virtual environment not found; run `python scripts/linux_tasks.py setup`.")
    _run([str(python), *_TASK_ARGUMENTS[task]])


if __name__ == "__main__":
    main()
