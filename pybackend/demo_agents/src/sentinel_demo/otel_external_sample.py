"""Standalone sample demonstrating zero-SDK OpenTelemetry interoperability with Sentinel-X.

Emits a correlated 3-level agent-LLM-tool trace using standard OpenTelemetry GenAI semantic
conventions directly to Sentinel's OTLP/HTTP trace ingestion endpoint without importing sentinel_sdk.
"""

import os
import time

from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


def emit_external_trace(
    endpoint: str = "http://localhost:8000/v1/traces",
    api_key: str = "dev-secret-key",
) -> tuple[str, str]:
    """Emit a correlated 3-level OpenTelemetry GenAI trace to the Sentinel OTLP endpoint."""
    # 1. Setup Resource and TracerProvider
    resource = Resource.create(
        {
            "service.name": "billing-support-service",
            "team": "customer-ops",
            "deployment.environment": "production",
        }
    )
    provider = TracerProvider(resource=resource)

    # 2. Configure standard OTLPSpanExporter with BatchSpanProcessor
    exporter = OTLPSpanExporter(
        endpoint=endpoint,
        headers={"X-API-Key": api_key},
    )
    processor = BatchSpanProcessor(exporter)
    provider.add_span_processor(processor)

    tracer = provider.get_tracer("sentinel_demo_otel", "1.0.0")

    # 3. Emit correlated 3-level trace:
    #    Level 1 (Parent): triage_billing_dispute (invoke_agent)
    #    Level 2 (Child LLM): chat gpt-4o-mini (chat)
    #    Level 3 (Child Tool): lookup_invoice (execute_tool)
    trace_id_hex = ""
    with tracer.start_as_current_span(
        "triage_billing_dispute",
        attributes={
            "gen_ai.operation.name": "invoke_agent",
            "gen_ai.agent.name": "BillingSupportAgent",
            "gen_ai.agent.id": "agent_billing_otel",
        },
    ) as parent_span:
        ctx = parent_span.get_span_context()
        trace_id_hex = format(ctx.trace_id, "032x")

        with tracer.start_as_current_span(
            "chat gpt-4o-mini",
            attributes={
                "gen_ai.operation.name": "chat",
                "gen_ai.provider.name": "openai",
                "gen_ai.request.model": "gpt-4o-mini",
                "gen_ai.usage.input_tokens": 640,
                "gen_ai.usage.output_tokens": 210,
            },
        ):
            time.sleep(0.05)

            with tracer.start_as_current_span(
                "lookup_invoice",
                attributes={
                    "gen_ai.operation.name": "execute_tool",
                    "gen_ai.tool.name": "lookup_invoice",
                },
            ):
                time.sleep(0.02)

    # 4. Flush the TracerProvider to ensure all spans are transmitted
    provider.force_flush()
    provider.shutdown()

    run_id = f"run_otel_{trace_id_hex[:12]}"
    return trace_id_hex, run_id


def main() -> None:
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT") or "http://localhost:8000/v1/traces"
    api_key = os.getenv("SENTINEL_API_KEY") or "dev-secret-key"

    print("=" * 70)
    print("🌐 Sentinel-X: Zero-SDK OpenTelemetry Trace Ingestion Sample")
    print(f"OTLP Endpoint: {endpoint}")
    print("=" * 70)

    trace_id, run_id = emit_external_trace(endpoint=endpoint, api_key=api_key)

    dashboard_host = os.getenv("DASHBOARD_URL") or "http://localhost:3000"
    dashboard_url = f"{dashboard_host.rstrip('/')}/runs/{run_id}"

    print(f"\nTrace ID:        {trace_id}")
    print(f"Expected Run ID: {run_id}")
    print(f"Control Tower:   {dashboard_url}")
    print("=" * 70)


if __name__ == "__main__":
    main()

