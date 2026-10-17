"""Fast tests for synthetic workload helper functions."""

from pathlib import Path

from collector.workloads.compile_job import run_compile_job
from collector.workloads.cpu_burn import run_cpu_burn
from collector.workloads.disk_writer import run_disk_writer
from collector.workloads.mem_hog import run_mem_hog
from collector.workloads.sort_big import run_sort_big


def test_cpu_burn_runs_with_spawned_worker() -> None:
    """The CPU workload starts and joins its process worker."""
    run_cpu_burn(seconds=0.1, workers=1)


def test_memory_workload_allocates_and_releases_small_block() -> None:
    """The memory workload accepts a small allocation and duration."""
    run_mem_hog(mb=1, seconds=0.01)


def test_disk_workload_cleans_temporary_output(tmp_path: Path) -> None:
    """The disk workload removes its generated file and child directory."""
    run_disk_writer(mb=1, tmp_dir=tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_sort_workload_writes_requested_line_count(tmp_path: Path) -> None:
    """The sorting workload writes all generated lines to its output."""
    output_path = tmp_path / "sorted.txt"

    result_path = run_sort_big(lines=100, output_path=output_path)

    assert result_path == output_path
    assert len(output_path.read_text(encoding="utf-8").splitlines()) == 100


def test_compile_workload_cleans_generated_modules(tmp_path: Path) -> None:
    """The compilation workload removes source and bytecode artifacts."""
    run_compile_job(modules=5, tmp_dir=tmp_path)
    assert list(tmp_path.iterdir()) == []
