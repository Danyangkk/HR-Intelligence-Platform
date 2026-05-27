from __future__ import annotations


class FlowTimeoutError(TimeoutError):
    """Raised when the full agent graph exceeds the flow timeout."""


class HarnessNodeExhausted(Exception):
    """Raised when a node exhausts retries (for tests / diagnostics)."""

    def __init__(self, node: str, error_type: str) -> None:
        self.node = node
        self.error_type = error_type
        super().__init__(f"{node} exhausted retries: {error_type}")
