"""Background task execution with queue-only communication to the Tk thread."""

from __future__ import annotations

from dataclasses import dataclass
import queue
import threading
from typing import Any, Callable


@dataclass(frozen=True)
class TaskMessage:
    """A result, phase, failure, or completion event delivered to the UI."""

    kind: str
    payload: Any = None


class TaskRunner:
    """Execute blocking operations without accessing widgets from worker threads."""

    def __init__(self) -> None:
        """Create the message queue and initialize task state."""
        self.messages: queue.Queue[TaskMessage] = queue.Queue()
        self._lock = threading.Lock()
        self._busy = False

    @property
    def busy(self) -> bool:
        """Return whether a background operation is active."""
        with self._lock:
            return self._busy

    def start(
        self, function: Callable[[Callable[[str], None]], Any], result_kind: str
    ) -> bool:
        """Start work and queue its result, phases, errors, and completion."""
        with self._lock:
            if self._busy:
                return False
            self._busy = True

        def work() -> None:
            try:
                result = function(
                    lambda phase: self.messages.put(TaskMessage("phase", phase))
                )
                self.messages.put(TaskMessage(result_kind, result))
            except Exception as error:
                self.messages.put(TaskMessage("error", error))
            finally:
                self.messages.put(TaskMessage("worker_done"))

        threading.Thread(target=work, daemon=True).start()
        return True

    def mark_done(self) -> None:
        """Mark the runner idle after the UI consumes its completion event."""
        with self._lock:
            self._busy = False
