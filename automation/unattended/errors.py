"""Typed failures. Every failure is fail-closed: the caller never advances state on one."""


class UnattendedError(Exception):
    """Base class; ``code`` is a stable machine-readable token."""

    code = "error"

    def __init__(self, message: str, **detail):
        super().__init__(message)
        self.detail = detail

    def as_dict(self) -> dict:
        return {"code": self.code, "message": str(self), **self.detail}


class PolicyError(UnattendedError):
    code = "policy-invalid"


class TransportError(UnattendedError):
    """A GitHub call failed for a reason the tool cannot classify further."""

    code = "transport-unknown"


class PermissionDenied(TransportError):
    code = "permission-denied"


class Outage(TransportError):
    code = "outage"


class NotFound(TransportError):
    code = "not-found"


class StaleRevision(UnattendedError):
    code = "stale-revision"


class Conflict(UnattendedError):
    code = "conflict"


class Refused(UnattendedError):
    """An operation the state machine refuses (precondition not met)."""

    code = "refused"


class BudgetExhausted(Refused):
    code = "budget-exhausted"


class ReceiptInvalid(Refused):
    code = "receipt-invalid"
