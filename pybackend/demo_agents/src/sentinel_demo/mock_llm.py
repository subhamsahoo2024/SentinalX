import os
import time
from contextvars import ContextVar
from typing import Any

from sentinel_sdk import trace_llm

live_llm_context: ContextVar[bool | None] = ContextVar("live_llm_context", default=None)


def is_live_llm_enabled() -> bool:
    """Check whether live LLM mode is enabled via context variable or environment."""
    ctx_val = live_llm_context.get()
    if ctx_val is not None:
        return ctx_val
    return os.getenv("SENTINEL_LIVE_LLM", "").strip().lower() in ("true", "1", "yes")


@trace_llm(provider="openai", model="gpt-4o")
def mock_llm_completion(
    prompt: str,
    model: str = "gpt-4o",
    provider: str = "openai",
    latency_ms: int = 250,
) -> dict[str, Any]:
    """Execute LLM inference via live OpenAI-compatible API if configured, or fall back to realistic deterministic mock."""
    # 1. Live LLM execution if enabled and API key is present
    if is_live_llm_enabled():
        llm_provider = (
            os.getenv("LLM_PROVIDER")
            or os.getenv("OPENAI_PROVIDER")
            or provider
            or "openai"
        )
        llm_base_url = (
            os.getenv("LLM_BASE_URL")
            or os.getenv("OPENAI_BASE_URL")
            or None
        )
        llm_api_key = (
            os.getenv("LLM_API_KEY")
            or os.getenv("OPENAI_API_KEY")
            or None
        )
        llm_model = (
            os.getenv("LLM_MODEL")
            or os.getenv("OPENAI_MODEL")
            or model
            or "gpt-4o"
        )

        if llm_api_key:
            import openai

            client = openai.OpenAI(base_url=llm_base_url, api_key=llm_api_key)
            response = client.chat.completions.create(
                model=llm_model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=200,
            )
            content = (
                response.choices[0].message.content
                if response.choices and response.choices[0].message
                else ""
            ) or ""
            resp_model = getattr(response, "model", None) or llm_model
            usage = getattr(response, "usage", None)
            prompt_tokens = (
                getattr(usage, "prompt_tokens", None)
                if usage is not None
                else None
            )
            completion_tokens = (
                getattr(usage, "completion_tokens", None)
                if usage is not None
                else None
            )

            usage_dict: dict[str, Any] | None = None
            if prompt_tokens is not None or completion_tokens is not None:
                usage_dict = {
                    "input_tokens": prompt_tokens,
                    "output_tokens": completion_tokens,
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                }

            return {
                "content": content,
                "model": resp_model,
                "provider": llm_provider,
                "usage": usage_dict,
            }

    # 2. Deterministic mock completion fallback
    if latency_ms > 0:
        time.sleep(latency_ms / 1000.0)

    prompt_lower = prompt.lower()
    if "triage" in prompt_lower or "coordinator" in prompt_lower:
        reasoning = (
            "Coordinator Triage Assessment: Ticket analyzed. High latency and connection "
            "timeouts reported. Initiating diagnostic agent to inspect service logs and "
            "cluster connection metrics."
        )
    elif "diagnos" in prompt_lower:
        reasoning = (
            "Diagnostic Assessment: Correlated service logs with database metrics. "
            "Found connection pool exhaustion (98/100 active) and lock contention on "
            "worker node-04. Recommend clearing stale cache and worker restart."
        )
    elif "remediat" in prompt_lower:
        reasoning = (
            "Remediation Assessment: Executed cache eviction across region us-east-1 and "
            "performed graceful restart of worker node-04. Post-remediation health checks "
            "confirm normal pool latency and 0 active deadlocks."
        )
    else:
        reasoning = (
            f"Analysis completed successfully. Processed prompt context: {prompt[:80]}"
        )

    # Calculate deterministic token metrics based on prompt and reasoning length
    input_tokens = max(18, len(prompt.split()) * 3)
    output_tokens = max(24, len(reasoning.split()) * 3)

    return {
        "content": reasoning,
        "model": model,
        "provider": provider,
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "prompt_tokens": input_tokens,
            "completion_tokens": output_tokens,
        },
    }


__all__ = ["is_live_llm_enabled", "live_llm_context", "mock_llm_completion"]
