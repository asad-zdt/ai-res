"""Write, read, and remove a temporary file of the requested size."""

import argparse
import tempfile
from pathlib import Path

_CHUNK_SIZE = 1024 * 1024


def run_disk_writer(mb: int, tmp_dir: Path | None = None) -> None:
    """Write and read back the requested MiB, then remove the temporary file."""
    if mb < 1:
        raise ValueError("mb must be at least 1")
    if tmp_dir is not None and not tmp_dir.is_dir():
        raise ValueError(f"temporary directory does not exist: {tmp_dir}")

    chunk = bytes(range(256)) * (_CHUNK_SIZE // 256)
    with tempfile.TemporaryDirectory(
        prefix="disk_writer_", dir=tmp_dir
    ) as temporary_directory:
        file_path = Path(temporary_directory) / "payload.bin"
        with file_path.open("wb") as output:
            for _ in range(mb):
                output.write(chunk)
            output.flush()

        with file_path.open("rb") as source:
            while source.read(_CHUNK_SIZE):
                pass


def main() -> None:
    """Parse arguments and run the disk workload."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mb", type=int, required=True)
    parser.add_argument("--tmp-dir", type=Path)
    args = parser.parse_args()
    run_disk_writer(args.mb, args.tmp_dir)


if __name__ == "__main__":
    main()
