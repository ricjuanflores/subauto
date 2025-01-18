# src/exceptions/base.py

from typing import Optional


class BaseError(Exception):
    """Base exception class for the application."""
    def __init__(self, message: str, original_error: Optional[Exception] = None):
        self.message = message
        self.original_error = original_error
        super().__init__(self.message)

    def __str__(self) -> str:
        if self.original_error:
            return f"{self.message}: {str(self.original_error)}"
        return self.message