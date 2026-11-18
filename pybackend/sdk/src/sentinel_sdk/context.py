import threading
import uuid
from contextvars import ContextVar, Token
from types import TracebackType
from typing import Any, Self

current_trace_id_var: ContextVar[str | None] = ContextVar(
    "sentinel_trace_id", default=None
)
current_span_id_var: ContextVar[str | None] = ContextVar(
    "sentinel_current_span_id", default=None
)
current_run_id_var: ContextVar[str | None] = ContextVar(
    "sentinel_run_id", default=None
)
current_agent_id_var: ContextVar[str | None] = ContextVar(
    "sentinel_agent_id", default=None
)
current_agent_name_var: ContextVar[str | None] = ContextVar(
    "sentinel_agent_name", default=None
)
current_team_var: ContextVar[str] = ContextVar("sentinel_team", default="default")

_counter_lock = threading.Lock()
_attempt_counters: dict[tuple[str, str, str], int] = {}


def get_trace_id() -> str | None:
    return current_trace_id_var.get()


def set_trace_id(val: str | None) -> Token[str | None]:
    return current_trace_id_var.set(val)


def get_current_span_id() -> str | None:
    return current_span_id_var.get()


def set_current_span_id(val: str | None) -> Token[str | None]:
    return current_span_id_var.set(val)


def get_run_id() -> str | None:
    return current_run_id_var.get()


def set_run_id(val: str | None) -> Token[str | None]:
    return current_run_id_var.set(val)


def get_agent_id() -> str | None:
    return current_agent_id_var.get()


def set_agent_id(val: str | None) -> Token[str | None]:
    return current_agent_id_var.set(val)


def get_agent_name() -> str | None:
    return current_agent_name_var.get()


def set_agent_name(val: str | None) -> Token[str | None]:
    return current_agent_name_var.set(val)


def get_team() -> str:
    return current_team_var.get()


def set_team(val: str) -> Token[str]:
    return current_team_var.set(val)


def next_attempt_number(run_id: str, agent_id: str, operation_name: str) -> int:
    """Thread-safe sequential attempt counter per (run_id, agent_id, operation_name)."""
    key = (run_id, agent_id, operation_name)
    with _counter_lock:
        attempt = _attempt_counters.get(key, 0) + 1
        _attempt_counters[key] = attempt
        return attempt


def get_attempt_number(run_id: str, agent_id: str, operation_name: str) -> int:
    """Read current attempt count without incrementing."""
    key = (run_id, agent_id, operation_name)
    with _counter_lock:
        return _attempt_counters.get(key, 0)


def reset_attempt_counters(run_id: str | None = None) -> None:
    """Reset attempt counters for a specific run or for all runs."""
    with _counter_lock:
        if run_id is None:
            _attempt_counters.clear()
        else:
            keys_to_del = [k for k in _attempt_counters if k[0] == run_id]
            for k in keys_to_del:
                del _attempt_counters[k]


class RunContext(str):
    """String subclass representing active run_id, providing attribute and item access."""

    run_id: str
    trace_id: str
    team: str

    def __new__(cls, run_id: str, trace_id: str, team: str) -> Self:
        instance = super().__new__(cls, run_id)
        instance.run_id = run_id
        instance.trace_id = trace_id
        instance.team = team
        return instance

    def __getitem__(self, item: Any) -> Any:
        if isinstance(item, str):
            if hasattr(self, item):
                return getattr(self, item)
            raise KeyError(item)
        return super().__getitem__(item)

    def get(self, item: str, default: Any = None) -> Any:
        return getattr(self, item, default)


class RunContextManager:
    """Context manager for run execution context supporting both sync and async usage."""

    def __init__(
        self,
        run_id: str | None = None,
        trace_id: str | None = None,
        team: str = "default",
    ) -> None:
        self.run_id = (
            run_id if run_id is not None else f"run_{uuid.uuid4().hex[:12]}"
        )
        self.trace_id = (
            trace_id if trace_id is not None else uuid.uuid4().hex
        )
        self.team = team
        self._tokens: list[tuple[ContextVar[Any], Token[Any]]] = []

    def __enter__(self) -> RunContext:
        self._tokens = [
            (current_run_id_var, current_run_id_var.set(self.run_id)),
            (current_trace_id_var, current_trace_id_var.set(self.trace_id)),
            (current_team_var, current_team_var.set(self.team)),
            (current_span_id_var, current_span_id_var.set(None)),
            (current_agent_id_var, current_agent_id_var.set(None)),
            (current_agent_name_var, current_agent_name_var.set(None)),
        ]
        return RunContext(self.run_id, self.trace_id, self.team)

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        for var, token in reversed(self._tokens):
            var.reset(token)
        self._tokens.clear()

    async def __aenter__(self) -> RunContext:
        return self.__enter__()

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.__exit__(exc_type, exc_val, exc_tb)


def start_run(
    run_id: str | None = None,
    trace_id: str | None = None,
    team: str = "default",
) -> RunContextManager:
    """Context manager initializing execution context with run_id and trace_id."""
    return RunContextManager(run_id=run_id, trace_id=trace_id, team=team)


__all__ = [
    "RunContext",
    "RunContextManager",
    "current_agent_id_var",
    "current_agent_name_var",
    "current_run_id_var",
    "current_span_id_var",
    "current_team_var",
    "current_trace_id_var",
    "get_agent_id",
    "get_agent_name",
    "get_attempt_number",
    "get_current_span_id",
    "get_run_id",
    "get_team",
    "get_trace_id",
    "next_attempt_number",
    "reset_attempt_counters",
    "set_agent_id",
    "set_agent_name",
    "set_current_span_id",
    "set_run_id",
    "set_team",
    "set_trace_id",
    "start_run",
]
