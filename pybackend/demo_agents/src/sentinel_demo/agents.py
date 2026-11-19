import os
import time
from typing import Any

import sentinel_sdk
from sentinel_sdk import gate_tool, trace_agent, trace_tool

from sentinel_demo.mock_llm import mock_llm_completion


# ============================================================================
# Simulated IT Support Tools
# ============================================================================
@trace_tool(tool_name="fetch_service_logs")
def fetch_service_logs(
    service_name: str,
    api_token: str = "sk-secret-demo-999",
) -> dict[str, Any]:
    """Fetch recent log records for a service.

    Accepts api_token deliberately to verify sensitive credential redaction.
    """
    time.sleep(0.12)
    return {
        "service": service_name,
        "token_authenticated": bool(api_token),
        "status": "warning",
        "entries": [
            {
                "timestamp": "2026-11-18T15:00:01Z",
                "level": "INFO",
                "message": f"Service '{service_name}' listening on 0.0.0.0:8080",
            },
            {
                "timestamp": "2026-11-18T15:01:23Z",
                "level": "WARN",
                "message": "High database connection wait duration: 1850ms on pool 'pool-alpha'",
            },
            {
                "timestamp": "2026-11-18T15:02:45Z",
                "level": "ERROR",
                "message": "ConnectionTimeoutError: exhausted worker connections on node 'node-04'",
            },
        ],
    }


@trace_tool(tool_name="check_db_metrics")
def check_db_metrics(cluster: str) -> dict[str, Any]:
    """Check database CPU, connection pool, and lock metrics."""
    time.sleep(0.15)
    return {
        "cluster": cluster,
        "cpu_utilization_pct": 89.2,
        "connection_pool_active": 98,
        "connection_pool_max": 100,
        "active_deadlocks": 3,
        "queries_queued": 142,
        "health_status": "DEGRADED",
    }


@trace_tool(tool_name="clear_stale_cache")
def clear_stale_cache(region: str) -> dict[str, Any]:
    """Evict expired and stale cache keys across Redis cluster."""
    time.sleep(0.1)
    return {
        "region": region,
        "keys_evicted": 1845,
        "memory_reclaimed_mb": 420.8,
        "status": "CACHE_CLEARED",
    }


@trace_tool(tool_name="restart_worker_node")
def restart_worker_node(node_id: str) -> dict[str, Any]:
    """Perform rolling restart and health check on degraded worker node."""
    time.sleep(0.2)
    return {
        "node_id": node_id,
        "action": "graceful_restart",
        "drain_duration_s": 1.8,
        "restart_status": "RESTARTED",
        "health_check": "PASSED",
    }


@gate_tool(
    risk_level="CRITICAL",
    policy_reason="Restarting production database cluster impacts live customer traffic",
)
def restart_production_cluster(
    cluster_name: str,
    force_failover: bool = True,
    auth_token: str = "prod-root-secret-777",
) -> dict[str, Any]:
    """Restart production database cluster with failover (HIGH-RISK HITL ACTION).

    Accepts auth_token deliberately to verify sensitive credential redaction.
    """
    time.sleep(0.3)
    return {
        "cluster_name": cluster_name,
        "force_failover": force_failover,
        "auth_authenticated": bool(auth_token),
        "status": "RESTARTED",
        "failover_duration_s": 2.4,
        "new_primary": f"{cluster_name}-replica-01",
    }


@trace_tool(tool_name="query_flaky_endpoint")
def query_flaky_endpoint(
    endpoint: str = "/api/v1/health",
    retry_mode: str = "immediate",
) -> dict[str, Any]:
    """Query an unstable external endpoint simulating transient failure."""
    time.sleep(0.08)
    return {
        "endpoint": endpoint,
        "retry_mode": retry_mode,
        "http_status": 503,
        "error": "Service Unavailable: Backend connection drained",
    }


@trace_tool(tool_name="fetch_corrupt_config")
def fetch_corrupt_config(env: str = "prod") -> dict[str, Any]:
    """Fetch cluster runtime configuration from config registry."""
    time.sleep(0.1)
    raise ValueError("Malformed JSON schema in upstream config registry")


# ============================================================================
# Instrumented Agents
# ============================================================================
@trace_agent(
    agent_id="diagnostic-agent",
    name="Diagnostic Agent",
    team="it-ops",
    framework="custom",
)
def run_diagnostic_agent(incident: dict[str, Any]) -> dict[str, Any]:
    """Diagnose incident by analyzing logs and database metrics."""
    service_name = incident.get("service", "auth-service")
    cluster_name = incident.get("cluster", "primary-postgres-cluster")

    # Step 1: LLM Reasoning on Incident
    llm_diag = mock_llm_completion(
        prompt=(
            f"Diagnose issue for incident: service={service_name}, "
            f"cluster={cluster_name}, description={incident.get('description', '')}"
        ),
        latency_ms=180,
    )

    # Step 2: Fetch service logs (contains api_token to verify redaction)
    logs = fetch_service_logs(
        service_name=service_name,
        api_token="sk-secret-demo-999",
    )

    # Step 3: Check database metrics
    metrics = check_db_metrics(cluster=cluster_name)

    return {
        "status": "DIAGNOSED",
        "service": service_name,
        "affected_node": "node-04",
        "region": incident.get("region", "us-east-1"),
        "root_cause": (
            "Worker node-04 has thread lock starvation causing pool exhaustion "
            "(98/100 active connections) and elevated query timeouts."
        ),
        "severity": "HIGH",
        "analysis": llm_diag["content"],
        "telemetry_findings": {
            "error_count": len(logs.get("entries", [])),
            "db_health": metrics.get("health_status"),
            "deadlocks": metrics.get("active_deadlocks"),
        },
        "recommended_actions": ["clear_stale_cache", "restart_worker_node"],
    }


@trace_agent(
    agent_id="looping-diagnostic-agent",
    name="Looping Diagnostic Agent",
    team="it-ops",
    framework="custom",
)
def run_looping_diagnostic_agent(incident: dict[str, Any]) -> dict[str, Any]:
    """Diagnostic agent that repeatedly retries a flaky endpoint without backoff, causing a tool loop."""
    endpoint = incident.get("endpoint", "/api/v1/health")
    retry_mode = incident.get("retry_mode", "immediate")
    responses: list[dict[str, Any]] = []
    # Call 4 times consecutively with identical arguments before aborting
    for _ in range(4):
        res = query_flaky_endpoint(endpoint=endpoint, retry_mode=retry_mode)
        responses.append(res)

    return {
        "status": "ABORTED",
        "service": incident.get("service", "auth-service"),
        "loop_count": len(responses),
        "last_response": responses[-1] if responses else None,
        "reason": "Aborted after 4 consecutive failed probe attempts to flaky endpoint",
    }


@trace_agent(
    agent_id="verbose-analysis-agent",
    name="Verbose Analysis Agent",
    team="it-ops",
    framework="custom",
)
def run_verbose_analysis_agent(incident: dict[str, Any]) -> dict[str, Any]:
    """Agent that performs deep system analysis with exhaustive multi-log context, exceeding token budget."""
    # Build oversized context prompt totaling ~7,500 tokens
    # 24 words * 102 repetitions = 2,448 words -> 2,448 * 3 = 7,344 input tokens.
    chunk = (
        "Detailed system telemetry analysis: inspect thread dump stack traces, "
        "TCP socket connection buffers, worker queue latencies, garbage collection pauses, "
        "and replication sync states across distributed database shards. "
    )
    oversized_prompt = (
        (chunk * 102)
        + f"Incident description: {incident.get('description', '')}"
    )

    llm_res = mock_llm_completion(
        prompt=oversized_prompt,
        latency_ms=150,
    )

    return {
        "status": "ANALYSIS_COMPLETE",
        "service": incident.get("service", "auth-service"),
        "total_tokens_consumed": (
            llm_res["usage"]["input_tokens"] + llm_res["usage"]["output_tokens"]
        ),
        "summary": llm_res["content"],
    }


@trace_agent(
    agent_id="corrupt-schema-diagnostic",
    name="Corrupt Schema Diagnostic Agent",
    team="it-ops",
    framework="custom",
)
def run_corrupt_schema_diagnostic(incident: dict[str, Any]) -> dict[str, Any]:
    """Diagnostic agent that attempts to read corrupt configuration."""
    env = incident.get("env", "prod")
    config = fetch_corrupt_config(env=env)
    return {"status": "SUCCESS", "config": config}


@trace_agent(
    agent_id="remediation-agent",
    name="Remediation Agent",
    team="it-ops",
    framework="custom",
)
def run_remediation_agent(diagnosis: dict[str, Any]) -> dict[str, Any]:
    """Execute remediation actions recommended by diagnostic agent."""
    if not diagnosis or not diagnosis.get("affected_node"):
        raise RuntimeError(
            "Cannot remediate: missing target cluster metadata from upstream diagnostic"
        )

    region = diagnosis.get("region", "us-east-1")
    node_id = diagnosis.get("affected_node", "node-04")

    # Step 1: LLM Remediation Planning
    llm_plan = mock_llm_completion(
        prompt=(
            f"Plan remediation for root cause: {diagnosis.get('root_cause', '')} "
            f"on node {node_id} in {region}."
        ),
        latency_ms=180,
    )

    # Step 2: Clear stale Redis cache keys
    cache_res = clear_stale_cache(region=region)

    # Step 3: Restart degraded worker node
    restart_res = restart_worker_node(node_id=node_id)

    return {
        "status": "RESOLVED",
        "region": region,
        "node_restarted": node_id,
        "actions_taken": [
            f"Evicted {cache_res.get('keys_evicted', 0)} stale cache keys",
            f"Gracefully restarted worker {restart_res.get('node_id', node_id)}",
        ],
        "verification": "Health check PASSED. Database connections stabilized.",
        "plan_summary": llm_plan["content"],
    }


@trace_agent(
    agent_id="critical-remediation-agent",
    name="Critical Remediation Agent",
    team="it-ops",
    framework="custom",
)
def run_critical_remediation_agent(diagnosis: dict[str, Any]) -> dict[str, Any]:
    """Execute high-risk critical remediation requiring human approval gate."""
    cluster_name = diagnosis.get("cluster", "primary-postgres-cluster")

    # Step 1: LLM Reasoning on Critical Remediation
    llm_plan = mock_llm_completion(
        prompt=(
            f"Evaluate critical failover and cluster restart for {cluster_name}. "
            f"Root cause: {diagnosis.get('root_cause', '')}"
        ),
        latency_ms=200,
    )

    # Step 2: Invoke gated high-risk tool
    restart_res = restart_production_cluster(
        cluster_name=cluster_name,
        force_failover=True,
        auth_token="prod-root-secret-777",
    )

    return {
        "status": "RESOLVED",
        "cluster": cluster_name,
        "actions_taken": [
            (
                f"Executed production restart on {cluster_name} "
                f"(failover: {restart_res.get('force_failover')})"
            ),
            f"Promoted {restart_res.get('new_primary')} to new primary cluster node",
        ],
        "details": restart_res,
        "plan_summary": llm_plan["content"],
    }


@trace_agent(
    agent_id="coordinator-agent",
    name="IT Triage Coordinator",
    team="it-ops",
    framework="custom",
)
def run_coordinator_agent(
    ticket_id: str,
    description: str,
    scenario: str = "normal",
    stall_duration_sec: float = 30.0,
    exit_on_stall: bool = True,
) -> dict[str, Any]:
    """Triage incoming IT support ticket and orchestrate diagnostic and remediation agents."""
    # Scenario: stall
    if scenario == "stall":
        # Initial RUNNING span has already been emitted upon entering @trace_agent.
        # Synchronously flush to backend so Run is RUNNING in database.
        sentinel_sdk.flush()
        import sys
        sys.stdout.flush()
        if stall_duration_sec > 0:
            time.sleep(stall_duration_sec)
        if exit_on_stall:
            sys.stdout.flush()
            os._exit(0)
        return {"status": "STALLED"}

    # Step 1: Initial Triage Reasoning
    triage_llm = mock_llm_completion(
        prompt=f"Triage IT support ticket {ticket_id}: {description} (scenario={scenario})",
        latency_ms=200,
    )

    incident = {
        "ticket_id": ticket_id,
        "description": description,
        "service": "auth-service",
        "cluster": "primary-postgres-cluster",
        "region": "us-east-1",
    }

    # Scenario: loop
    if scenario == "loop":
        diagnosis = run_looping_diagnostic_agent(incident=incident)
        return {
            "ticket_id": ticket_id,
            "description": description,
            "scenario": scenario,
            "status": "ABORTED",
            "triage_assessment": triage_llm["content"],
            "diagnosis": diagnosis,
            "resolved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

    # Scenario: budget
    if scenario == "budget":
        diagnosis = run_verbose_analysis_agent(incident=incident)
        remediation = run_remediation_agent(
            diagnosis={
                "status": "DIAGNOSED",
                "affected_node": "node-04",
                "region": "us-east-1",
                "root_cause": "Excessive token volume analyzed.",
            }
        )
        return {
            "ticket_id": ticket_id,
            "description": description,
            "scenario": scenario,
            "status": "RESOLVED",
            "triage_assessment": triage_llm["content"],
            "diagnosis": diagnosis,
            "remediation": remediation,
            "resolved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

    # Scenario: cascade
    if scenario == "cascade":
        corrupt_payload: dict[str, Any] = {}
        try:
            run_corrupt_schema_diagnostic(incident=incident)
        except ValueError:
            corrupt_payload = {}

        # Pass empty/corrupt payload to remediation agent, which fails with RuntimeError
        remediation = run_remediation_agent(diagnosis=corrupt_payload)
        return {
            "ticket_id": ticket_id,
            "description": description,
            "scenario": scenario,
            "status": "RESOLVED",
            "diagnosis": {},
            "remediation": remediation,
        }

    # Step 2: Delegate to Diagnostic Agent (normal / hitl)
    diagnosis = run_diagnostic_agent(incident=incident)

    # Step 3: Delegate to Remediation Agent based on scenario
    if scenario == "hitl":
        remediation = run_critical_remediation_agent(diagnosis=diagnosis)
    else:
        remediation = run_remediation_agent(diagnosis=diagnosis)

    return {
        "ticket_id": ticket_id,
        "description": description,
        "scenario": scenario,
        "status": "RESOLVED",
        "triage_assessment": triage_llm["content"],
        "diagnosis": diagnosis,
        "remediation": remediation,
        "resolved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


__all__ = [
    "check_db_metrics",
    "clear_stale_cache",
    "fetch_corrupt_config",
    "fetch_service_logs",
    "query_flaky_endpoint",
    "restart_production_cluster",
    "restart_worker_node",
    "run_coordinator_agent",
    "run_corrupt_schema_diagnostic",
    "run_critical_remediation_agent",
    "run_diagnostic_agent",
    "run_looping_diagnostic_agent",
    "run_remediation_agent",
    "run_verbose_analysis_agent",
]
