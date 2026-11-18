import time
from typing import Any

from sentinel_sdk import trace_agent, trace_tool

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
    agent_id="remediation-agent",
    name="Remediation Agent",
    team="it-ops",
    framework="custom",
)
def run_remediation_agent(diagnosis: dict[str, Any]) -> dict[str, Any]:
    """Execute remediation actions recommended by diagnostic agent."""
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
    agent_id="coordinator-agent",
    name="IT Triage Coordinator",
    team="it-ops",
    framework="custom",
)
def run_coordinator_agent(ticket_id: str, description: str) -> dict[str, Any]:
    """Triage incoming IT support ticket and orchestrate diagnostic and remediation agents."""
    # Step 1: Initial Triage Reasoning
    triage_llm = mock_llm_completion(
        prompt=f"Triage IT support ticket {ticket_id}: {description}",
        latency_ms=200,
    )

    incident = {
        "ticket_id": ticket_id,
        "description": description,
        "service": "auth-service",
        "cluster": "primary-postgres-cluster",
        "region": "us-east-1",
    }

    # Step 2: Delegate to Diagnostic Agent
    diagnosis = run_diagnostic_agent(incident=incident)

    # Step 3: Delegate to Remediation Agent
    remediation = run_remediation_agent(diagnosis=diagnosis)

    return {
        "ticket_id": ticket_id,
        "description": description,
        "status": "RESOLVED",
        "triage_assessment": triage_llm["content"],
        "diagnosis": diagnosis,
        "remediation": remediation,
        "resolved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


__all__ = [
    "check_db_metrics",
    "clear_stale_cache",
    "fetch_service_logs",
    "restart_worker_node",
    "run_coordinator_agent",
    "run_diagnostic_agent",
    "run_remediation_agent",
]

