class SentinelGovernanceError(Exception):
    """Base exception for Sentinel Human-in-the-Loop governance failures."""


class GovernanceRejectedError(SentinelGovernanceError):
    """Raised when an approval request is explicitly rejected by a human reviewer."""


class GovernanceTimeoutError(SentinelGovernanceError):
    """Raised when an approval request times out waiting for human review."""


__all__ = [
    "GovernanceRejectedError",
    "GovernanceTimeoutError",
    "SentinelGovernanceError",
]

