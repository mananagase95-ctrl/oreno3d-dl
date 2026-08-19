__version__ = "0.1.0"


class ItemError(Exception):
    """Recoverable per-item failure; the batch continues."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class FatalError(Exception):
    """Unrecoverable error; the whole run must stop."""
