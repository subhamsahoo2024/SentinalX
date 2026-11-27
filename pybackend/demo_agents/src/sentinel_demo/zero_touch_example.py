"""Zero-touch auto-instrumentation example using OpenAI SDK without @trace_* decorators."""

import contextlib
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

# Ensure UTF-8 output encoding across Windows and POSIX terminals
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    with contextlib.suppress(Exception):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    with contextlib.suppress(Exception):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import openai
from dotenv import load_dotenv
from sentinel_sdk.config import find_env_file

_env_path = find_env_file()
if _env_path:
    load_dotenv(_env_path)


class _MockOpenAIHandler(BaseHTTPRequestHandler):
    """Minimal OpenAI-compatible /v1/chat/completions HTTP handler for offline mode."""

    def do_POST(self) -> None:
        if not self.path.rstrip("/").endswith("/chat/completions"):
            self.send_response(404)
            self.end_headers()
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length) if content_length > 0 else b"{}"
        try:
            req_data: dict[str, Any] = json.loads(raw_body.decode("utf-8"))
        except json.JSONDecodeError:
            req_data = {}

        model = str(req_data.get("model") or "gpt-4o-mini")
        messages = req_data.get("messages") or []
        last_content = ""
        if isinstance(messages, list) and messages:
            last_msg = messages[-1]
            if isinstance(last_msg, dict):
                last_content = str(last_msg.get("content", ""))

        is_second_step = "step 2" in last_content.lower() or "recommend" in last_content.lower()
        reply_text = (
            "Recommendation: HOLD transaction and trigger step-up KYC verification."
            if is_second_step
            else "Risk score: 0.87 (HIGH) - velocity spike from unverified device."
        )

        payload = {
            "id": f"chatcmpl-mock-{int(time.time() * 1000)}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": reply_text,
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 420,
                "completion_tokens": 135,
                "total_tokens": 555,
            },
        }
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format: str, *args: Any) -> None:
        return


def _start_mock_openai_server() -> tuple[ThreadingHTTPServer, int]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _MockOpenAIHandler)
    port = int(server.server_address[1])
    thread = threading.Thread(
        target=server.serve_forever,
        daemon=True,
        name="mock-openai-server",
    )
    thread.start()
    return server, port


def _run_fraud_scoring_calls(client: openai.OpenAI, model: str) -> None:
    """Execute two standard OpenAI chat completion calls with zero Sentinel decorators."""
    first_prompt = (
        "Score transaction tx_99481 ($4,850 wire transfer) for customer "
        "ssn: 123-45-6789 using partner api_key: sk_live_demo_redaction_check_9999."
    )
    resp_1 = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": "You are a fraud risk scoring service.",
            },
            {
                "role": "user",
                "content": first_prompt,
                "api_key": "sk_live_demo_redaction_check_9999",
                "ssn": "123-45-6789",
            },
        ],
    )
    summary_1 = resp_1.choices[0].message.content or ""
    print(f"[Call 1] Assessment: {summary_1}")

    resp_2 = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": "You are a fraud risk scoring service.",
            },
            {
                "role": "user",
                "content": (
                    f"Step 2 - Recommend next action based on prior risk score: {summary_1}"
                ),
            },
        ],
    )
    summary_2 = resp_2.choices[0].message.content or ""
    print(f"[Call 2] Decision:   {summary_2}")


def main() -> None:
    """Run zero-touch OpenAI auto-instrumentation in live or offline mock mode."""
    import sentinel_sdk

    sentinel_sdk.instrument(
        api_key=os.environ.get("SENTINEL_API_KEY", "dev-secret-key"),
        base_url=os.environ.get("SENTINEL_URL", "http://localhost:8000"),
        agent_id="fraud-scoring-service",
    )

    live_mode = os.environ.get("SENTINEL_LIVE_LLM", "false").strip().lower() == "true"
    mock_server: ThreadingHTTPServer | None = None

    print("=" * 72)
    print("SENTINEL-X Zero-Touch Auto-Instrumentation Example")
    print("=" * 72)

    try:
        if live_mode:
            llm_base_url = (os.environ.get("LLM_BASE_URL") or "").strip() or None
            llm_api_key = (os.environ.get("LLM_API_KEY") or "").strip() or "missing-key"
            llm_model = (os.environ.get("LLM_MODEL") or "").strip() or "gpt-4o-mini"
            print(f"Mode:     LIVE PROVIDER ({llm_base_url or 'https://api.openai.com/v1'})")
            print(f"Model:    {llm_model}")
            client = openai.OpenAI(base_url=llm_base_url, api_key=llm_api_key)
        else:
            mock_server, port = _start_mock_openai_server()
            llm_model = "gpt-4o-mini"
            mock_base_url = f"http://127.0.0.1:{port}/v1"
            print(f"Mode:     OFFLINE LOCAL MOCK SERVER ({mock_base_url})")
            print(f"Model:    {llm_model}")
            client = openai.OpenAI(base_url=mock_base_url, api_key="mock")

        with sentinel_sdk.start_run() as run_ctx:
            print(f"Run ID:   {run_ctx.run_id}")
            try:
                _run_fraud_scoring_calls(client, model=llm_model)
            except (sentinel_sdk.BudgetCircuitBreakerError, sentinel_sdk.RunCancelledError) as exc:
                print(f"[BLOCKED] {type(exc).__name__}: {exc}")
                raise
    finally:
        sentinel_sdk.flush()
        if mock_server is not None:
            mock_server.shutdown()
            mock_server.server_close()

    dashboard_url = (os.environ.get("DASHBOARD_URL") or "http://localhost:3000").rstrip("/")
    print("-" * 72)
    print(
        "Telemetry flushed! Inspect agent 'fraud-scoring-service' in the "
        f"SENTINEL-X Control Tower UI: {dashboard_url}"
    )
    print("=" * 72)


if __name__ == "__main__":
    main()
