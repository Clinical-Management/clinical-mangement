from typing import Any


class DomainError(Exception):
    """Raised by services; turned into an HTTP error response by the handler in main.py."""

    status_code = 400

    def __init__(self, detail: Any):
        super().__init__(detail)
        self.detail = detail


class NotFound(DomainError):
    status_code = 404


class Forbidden(DomainError):
    status_code = 403


class Conflict(DomainError):
    status_code = 409


class Invalid(DomainError):
    status_code = 422
