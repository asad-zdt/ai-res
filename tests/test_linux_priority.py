"""Tests for Linux nice-level priority handling."""

import pytest

from os_integration.priority import set_priority


def test_linux_priority_applies_nice_level_to_process_tree(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    applied: list[tuple[int, int]] = []

    class FakeProcess:
        def __init__(self, pid: int) -> None:
            self.pid = pid

        def children(self, recursive: bool = True) -> list["FakeProcess"]:
            assert recursive
            return [FakeProcess(12346)]

        def nice(self, value: int) -> None:
            applied.append((self.pid, value))

    monkeypatch.setattr("os_integration.priority.sys.platform", "linux")
    monkeypatch.setattr("os_integration.priority.os.getpid", lambda: 99999)
    monkeypatch.setattr("os_integration.priority.psutil.Process", FakeProcess)

    result = set_priority(12345, 5)

    assert result == 5
    assert applied == [(12346, 5), (12345, 5)]
