"""Shared exceptions."""


class ToolExecutionError(RuntimeError):
    """Raised when a tool cannot complete execution."""


class SafetyError(RuntimeError):
    """Raised when a request is blocked by safety policy."""
