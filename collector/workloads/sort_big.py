"""Generate random text lines, sort them in memory, and write the result."""

import argparse
import random
import string
import tempfile
from pathlib import Path


def run_sort_big(lines: int, output_path: Path | None = None) -> Path:
    """Generate and sort random lines, writing them to a temporary result file."""
    if lines < 1:
        raise ValueError("lines must be at least 1")

    rng = random.Random()
    alphabet = string.ascii_letters + string.digits
    generated_lines = [
        "".join(rng.choices(alphabet, k=32)) for _ in range(lines)
    ]
    generated_lines.sort()

    if output_path is None:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            prefix="sort_big_",
            suffix=".txt",
            delete=False,
        ) as output:
            result_path = Path(output.name)
    else:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        result_path = output_path

    with result_path.open("w", encoding="utf-8", newline="\n") as output:
        output.write("\n".join(generated_lines))
        output.write("\n")
    return result_path


def main() -> None:
    """Parse arguments and run the sorting workload."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lines", type=int, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    print(run_sort_big(args.lines, args.output))


if __name__ == "__main__":
    main()
