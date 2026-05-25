"""Platform-specific exceptions."""


class AuthorizationDenied(RuntimeError):
    """Raised when ReBAC denies an operation."""


class ApprovalRequired(RuntimeError):
    """Raised when a high-risk action must pause for human approval."""


class BudgetExceeded(RuntimeError):
    """Raised when a run exceeds configured cost or loop limits."""

