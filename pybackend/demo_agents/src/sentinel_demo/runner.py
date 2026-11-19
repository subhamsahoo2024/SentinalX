import argparse
import os
import sys

from dotenv import load_dotenv

import sentinel_sdk
from sentinel_sdk import (
    GovernanceRejectedError,
    GovernanceTimeoutError,
    start_run,
)
from sentinel_sdk.config import find_env_file
from sentinel_demo.agents import run_coordinator_agent

# Ensure .env configuration is loaded
_env_path = find_env_file()
if _env_path:
    load_dotenv(_env_path)


def main() -> None:
    """CLI entrypoint for running reproducible Sentinel demo scenarios."""
    parser = argparse.ArgumentParser(
        description="Sentinel Multi-Agent IT Support Triage Demo",
    )
    parser.add_argument(
        "--scenario",
        type=str,
        default="normal",
        choices=["normal", "hitl", "loop", "budget", "cascade", "stall"],
        help="Demo scenario to execute: normal, hitl, loop, budget, cascade, stall (default: normal)",
    )
    parser.add_argument(
        "--ticket-id",
        type=str,
        default="INC-8492",
        help="Simulated IT support ticket ID (default: INC-8492)",
    )
    parser.add_argument(
        "--description",
        type=str,
        default=(
            "Authentication service experiencing connection timeouts and elevated "
            "pool latency on primary database cluster."
        ),
        help="Incident description",
    )
    parser.add_argument(
        "--team",
        type=str,
        default="it-ops",
        help="Team attribution for Sentinel telemetry (default: it-ops)",
    )
    parser.add_argument(
        "--dashboard-host",
        type=str,
        default=os.getenv("DASHBOARD_URL") or "http://localhost:3000",
        help="Frontend dashboard host URL (default: http://localhost:3000)",
    )

    args = parser.parse_args()

    print("=" * 70)
    print("🚀 SENTINEL-X: Reproducible Multi-Agent IT Support Triage Demo")
    print(f"Scenario:     {args.scenario.upper()}")
    print(f"Ticket ID:    {args.ticket_id}")
    print(f"Team:         {args.team}")
    print("=" * 70)

    run_id: str | None = None
    trace_id: str | None = None

    try:
        with start_run(team=args.team) as run_ctx:
            run_id = run_ctx.run_id
            trace_id = run_ctx.trace_id

            print(f"\n[1/3] Initializing Run: {run_id}")
            print(f"      Trace ID:        {trace_id}")
            sys.stdout.flush()
            print("\n[2/3] Orchestrating Multi-Agent Workflow...")
            if args.scenario == "hitl":
                print("      • Coordinator Agent          -> Triage assessment & delegation")
                print("      • Diagnostic Agent           -> Log analysis & DB health inspection")
                print("      • Critical Remediation Agent -> Production cluster restart [HITL GATE]\n")
            elif args.scenario == "loop":
                print("      • Coordinator Agent        -> Triage assessment & delegation")
                print("      • Looping Diagnostic Agent -> Flaky endpoint probe (4 consecutive retries) [LOOP DETECTED]\n")
            elif args.scenario == "budget":
                print("      • Coordinator Agent        -> Triage assessment & delegation")
                print("      • Verbose Analysis Agent   -> Exhaustive context inference (~7,500 tokens) [BUDGET EXCEEDED]\n")
            elif args.scenario == "cascade":
                print("      • Coordinator Agent        -> Triage assessment & delegation")
                print("      • Corrupt Diagnostic Agent -> Upstream schema fetch failure (root cause)")
                print("      • Remediation Agent        -> Downstream execution crash [CASCADE FAILURE]\n")
            elif args.scenario == "stall":
                print("      • Coordinator Agent        -> Initial RUNNING span emitted and flushed")
                print("      • Watchdog Monitor         -> 30s silence window [RUN STALLED WATCHDOG]")
                print(f"      • Live Dashboard URL       -> {args.dashboard_host.rstrip('/')}/runs/{run_id}\n")
            else:
                print("      • Coordinator Agent -> Triage assessment & delegation")
                print("      • Diagnostic Agent  -> Log analysis & DB health inspection")
                print("      • Remediation Agent -> Cache eviction & worker node restart\n")

            try:
                result = run_coordinator_agent(
                    ticket_id=args.ticket_id,
                    description=args.description,
                    scenario=args.scenario,
                )
                print("[3/3] Workflow Completed Successfully!")
                print(f"      Incident Status: {result.get('status', 'UNKNOWN')}")
                print(f"      Root Cause:      {result.get('diagnosis', {}).get('root_cause', 'N/A')}")
                print(f"      Actions Taken:   {', '.join(result.get('remediation', {}).get('actions_taken', []))}")
            except GovernanceRejectedError as exc:
                print("[3/3] Workflow Terminated by Human-in-the-Loop Governance Gate:")
                print("      Status:  REJECTED")
                print(f"      Reason:  {exc}")
                print("      High-risk operation was halted. Production cluster state preserved.")
            except GovernanceTimeoutError as exc:
                print("[3/3] Workflow Timed Out Waiting for Human Approval:")
                print("      Status:  TIMED_OUT")
                print(f"      Reason:  {exc}")
                print("      High-risk operation was aborted.")
            except RuntimeError as exc:
                if args.scenario == "cascade":
                    print("[3/3] Workflow Terminated by Cascading Failure Chain:")
                    print("      Status:           FAILED")
                    print("      Root Cause Tool:  fetch_corrupt_config (ValueError: Malformed JSON schema)")
                    print(f"      Downstream Error: {exc}")
                else:
                    raise
    finally:
        # Synchronously flush all trailing telemetry events before exiting
        print("\n⏳ Flushing telemetry buffer to Sentinel Control Tower...")
        sentinel_sdk.flush()
        print("✓ Telemetry flushed.")

    if run_id:
        dashboard_url = f"{args.dashboard_host.rstrip('/')}/runs/{run_id}"
        print("\n" + "=" * 70)
        print("📊 Run Lineage & Telemetry Available:")
        print(f"   Run ID:        {run_id}")
        print(f"   Trace ID:      {trace_id}")
        print(f"   Dashboard URL: {dashboard_url}")
        print("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(130)
