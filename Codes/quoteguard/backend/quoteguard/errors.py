from __future__ import annotations


class AppError(Exception):
    """A business error with a stable code, a user-facing message and an HTTP status."""

    def __init__(self, code: str, message: str, status: int = 400, details: dict | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.details = details or {}


def not_found(what: str = "Resource") -> AppError:
    # The same answer for "absent" and "in another workspace" so IDs cannot be probed.
    return AppError("NOT_FOUND", f"{what} was not found in this workspace.", 404)


def forbidden(message: str = "Your role does not allow this action.") -> AppError:
    return AppError("FORBIDDEN", message, 403)
