"""Allocate and touch memory for a fixed duration."""

import argparse
import time


def run_mem_hog(mb: int, seconds: float) -> None:
    """Allocate and touch the requested memory, retaining it for a duration."""
    if mb < 1:
        raise ValueError("mb must be at least 1")
    if seconds <= 0:
        raise ValueError("seconds must be greater than zero")

    allocation = bytearray(mb * 1024 * 1024)
    page_size = 4096
    for offset in range(0, len(allocation), page_size):
        allocation[offset] = 1
    time.sleep(seconds)
    del allocation


def main() -> None:
    """Parse arguments and run the memory workload."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mb", type=int, required=True)
    parser.add_argument("--seconds", type=float, required=True)
    args = parser.parse_args()
    run_mem_hog(args.mb, args.seconds)


if __name__ == "__main__":
    main()
