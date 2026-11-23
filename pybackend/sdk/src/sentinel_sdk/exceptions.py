class SentinelGovernanceError(Exception):
    """Base exception for Sentinel Human-in-the-Loop governance failures."""


class GovernanceRejectedError(SentinelGovernanceError):
    """Raised when an approval request is explicitly rejected by a human reviewer."""


class GovernanceTimeoutError(SentinelGovernanceError):
    """Raised when an approval request times out waiting for human review."""


class RunCancelledError(SentinelGovernanceError):
    """Raised when run execution is halted by an operator kill-switch or cancellation."""


class BudgetCircuitBreakerError(SentinelGovernanceError):
    """Raised when LLM execution is halted due to a policy budget circuit-breaker trip."""


__all__ = [
    "BudgetCircuitBreakerError",
    "GovernanceRejectedError",
    "GovernanceTimeoutError",
    "RunCancelledError",
    "SentinelGovernanceError",
]
