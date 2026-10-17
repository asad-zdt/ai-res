"""Run a fixed-duration CPU workload across multiple spawned processes."""

import argparse
import multiprocessing
import time


def _burn_worker(seconds: float) -> None:
    """Consume CPU until the requested duration has elapsed."""
    deadline = time.monotonic() + seconds
    value = 0
    while time.monotonic() < deadline:
        value = (value + 1) % 1_000_003


def run_cpu_burn(seconds: float, workers: int) -> None:
    """Start the requested number of CPU workers for the given duration."""
    if seconds <= 0:
        raise ValueError("seconds must be greater than zero")
    if workers < 1:
        raise ValueError("workers must be at least 1")

    processes = [
        multiprocessing.Process(target=_burn_worker, args=(seconds,))
        for _ in range(workers)
    ]
    for process in processes:
        process.start()
    for process in processes:
        process.join()
        if process.exitcode != 0:
            raise RuntimeError(f"CPU worker exited with status {process.exitcode}")


def main() -> None:
    """Parse arguments and run the CPU workload."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=float, required=True)
    parser.add_argument("--workers", type=int, required=True)
    args = parser.parse_args()
    run_cpu_burn(args.seconds, args.workers)


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
