"""Domain errors, translated to HTTP responses at the edge."""


class DomainError(Exception):
    """A rule of the domain was violated. Carries a message safe to show a user."""

    status_code = 400

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class NotFound(DomainError):
    status_code = 404


class Conflict(DomainError):
    status_code = 409


class ValidationError(DomainError):
    status_code = 422
