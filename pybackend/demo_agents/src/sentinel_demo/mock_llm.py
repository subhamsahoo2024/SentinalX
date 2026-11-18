import time

from sentinel_sdk import trace_llm


@trace_llm(provider="openai", model="gpt-4o")
def mock_llm_completion(
    prompt: str,
    model: str = "gpt-4o",
    provider: str = "openai",
    latency_ms: int = 250,
) -> dict:
    """Simulate realistic LLM inference with deterministic outputs and token counts."""
    # Simulate network & inference latency
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
        },
    }


__all__ = ["mock_llm_completion"]

