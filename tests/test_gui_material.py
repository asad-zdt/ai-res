"""Focused tests for reusable desktop theme and background-task helpers."""

from __future__ import annotations

import queue
from pathlib import Path

from gui.task_runner import TaskMessage, TaskRunner
from gui.theme import manager, tokens
from gui.dashboard_data import gauge_color


def test_gauge_color_uses_relative_semantic_thresholds() -> None:
    assert gauge_color(20.0, 100.0, tokens.LIGHT) == tokens.LIGHT["success"]
    assert gauge_color(60.0, 100.0, tokens.LIGHT) == tokens.LIGHT["warning"]
    assert gauge_color(90.0, 100.0, tokens.LIGHT) == tokens.LIGHT["error"]


def test_theme_preference_round_trip_uses_local_file(
    tmp_path: Path, monkeypatch
) -> None:
    preference_path = tmp_path / "preferences.json"
    monkeypatch.setattr(manager, "_PREFERENCES_PATH", preference_path)

    assert manager.load_theme_preference() == "light"
    manager.save_theme_preference("dark")

    assert manager.load_theme_preference() == "dark"


def test_task_runner_queues_phases_results_and_completion() -> None:
    runner = TaskRunner()

    started = runner.start(
        lambda phase: (phase("Working"), "done")[1],
        "result",
    )

    assert started
    messages: list[TaskMessage] = []
    while len(messages) < 3:
        messages.append(runner.messages.get(timeout=2))
    assert [(message.kind, message.payload) for message in messages] == [
        ("phase", "Working"),
        ("result", "done"),
        ("worker_done", None),
    ]
    assert runner.busy
    runner.mark_done()
    assert not runner.busy


def test_task_runner_rejects_overlapping_work() -> None:
    runner = TaskRunner()
    gate = queue.Queue()

    assert runner.start(lambda _phase: gate.get(timeout=2), "result")
    assert not runner.start(lambda _phase: None, "ignored")
    gate.put("finished")
    assert runner.messages.get(timeout=2).kind == "result"
    assert runner.messages.get(timeout=2).kind == "worker_done"
    runner.mark_done()
