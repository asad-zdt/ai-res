"""Generate Python modules and compile them in a temporary directory."""

import argparse
import compileall
import tempfile
from pathlib import Path


def run_compile_job(modules: int, tmp_dir: Path | None = None) -> None:
    """Generate the requested modules, compile them, and clean up afterward."""
    if modules < 1:
        raise ValueError("modules must be at least 1")
    if tmp_dir is not None and not tmp_dir.is_dir():
        raise ValueError(f"temporary directory does not exist: {tmp_dir}")

    with tempfile.TemporaryDirectory(
        prefix="compile_job_", dir=tmp_dir
    ) as temporary_directory:
        source_directory = Path(temporary_directory) / "modules"
        source_directory.mkdir()
        for index in range(modules):
            module_path = source_directory / f"module_{index:05d}.py"
            module_path.write_text(
                f"VALUE = {index}\nRESULT = VALUE * VALUE + 17\n",
                encoding="utf-8",
            )

        if not compileall.compile_dir(
            source_directory,
            quiet=1,
            force=True,
            workers=1,
        ):
            raise RuntimeError(f"compileall failed for {source_directory}")


def main() -> None:
    """Parse arguments and run the compilation workload."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--modules", type=int, required=True)
    parser.add_argument("--tmp-dir", type=Path)
    args = parser.parse_args()
    run_compile_job(args.modules, args.tmp_dir)


if __name__ == "__main__":
    main()
