"""Project-specific exceptions."""


class UnknownAppError(KeyError):
    """Raised when a prediction is requested for an unconfigured application."""

    def __init__(self, app_name: str) -> None:
        """Initialize the error with the requested application name."""
        self.app_name = app_name
        super().__init__(f"Unknown app: {app_name}")
