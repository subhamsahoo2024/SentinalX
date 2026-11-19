import atexit
import logging
import queue
import threading
import time

import httpx

from sentinel_sdk.config import load_sdk_env
from sentinel_sdk.schema import CanonicalEventV1, TelemetryBatchRequest

logger = logging.getLogger(__name__)


class SentinelExporter:
    """Thread-safe batching telemetry exporter for Sentinel control tower."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        batch_size: int = 25,
        flush_interval: float = 0.25,
    ) -> None:
        if base_url is None or api_key is None:
            env_url, env_key = load_sdk_env()
            if base_url is None:
                base_url = env_url
            if api_key is None:
                api_key = env_key

        if "localhost" in base_url:
            base_url = base_url.replace("localhost", "127.0.0.1")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.batch_size = batch_size
        self.flush_interval = flush_interval

        self._queue: queue.Queue[CanonicalEventV1] = queue.Queue()
        self._batch: list[CanonicalEventV1] = []
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._flush_trigger = threading.Event()
        self._client: httpx.Client = httpx.Client(timeout=10.0)

        self._thread = threading.Thread(
            target=self._worker_loop,
            daemon=True,
            name="sentinel-exporter",
        )
        self._thread.start()

    def enqueue(self, event: CanonicalEventV1) -> None:
        """Enqueue a telemetry event for background transmission."""
        self._queue.put(event)

    def _send_batch(self, batch: list[CanonicalEventV1]) -> None:
        """Send a batch of events via HTTP POST to the telemetry endpoint."""
        if not batch:
            return
        payload = TelemetryBatchRequest(events=batch).model_dump(mode="json")
        url = f"{self.base_url}/api/telemetry/events"
        headers = {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json",
        }
        try:
            resp = self._client.post(url, json=payload, headers=headers)
            if resp.status_code >= 400:
                logger.warning(
                    "Sentinel telemetry export failed with status %d: %s",
                    resp.status_code,
                    resp.text,
                )
        except (httpx.HTTPError, OSError, RuntimeError) as exc:
            logger.warning(
                "Sentinel telemetry export connection error: %s", exc
            )

    def _worker_loop(self) -> None:
        """Daemon worker loop draining queue every 0.25s or when 25 events accumulate."""
        last_flush = time.monotonic()

        while not self._stop_event.is_set():
            time_since_flush = time.monotonic() - last_flush
            remaining_time = max(0.01, self.flush_interval - time_since_flush)

            try:
                event = self._queue.get(timeout=min(0.05, remaining_time))
                with self._lock:
                    self._batch.append(event)
                    while len(self._batch) < self.batch_size:
                        try:
                            self._batch.append(self._queue.get_nowait())
                        except queue.Empty:
                            break
            except queue.Empty:
                pass

            now = time.monotonic()
            with self._lock:
                should_flush = (
                    len(self._batch) >= self.batch_size
                    or (self._batch and (now - last_flush) >= self.flush_interval)
                    or (self._batch and self._flush_trigger.is_set())
                )

                if should_flush and self._batch:
                    self._send_batch(self._batch)
                    for _ in range(len(self._batch)):
                        self._queue.task_done()
                    self._batch.clear()
                    last_flush = time.monotonic()
                    self._flush_trigger.clear()

        # Drain any remaining events on shutdown
        with self._lock:
            while not self._queue.empty():
                try:
                    self._batch.append(self._queue.get_nowait())
                except queue.Empty:
                    break
            if self._batch:
                for i in range(0, len(self._batch), self.batch_size):
                    chunk = self._batch[i : i + self.batch_size]
                    self._send_batch(chunk)
                    for _ in range(len(chunk)):
                        self._queue.task_done()
                self._batch.clear()

    def flush(self, timeout: float = 5.0) -> None:
        """Synchronously flush all queued events with a timeout."""
        with self._lock:
            # Drain any items still in queue into batch
            while not self._queue.empty():
                try:
                    self._batch.append(self._queue.get_nowait())
                except queue.Empty:
                    break

            # Send all accumulated batch events
            if self._batch:
                for i in range(0, len(self._batch), self.batch_size):
                    chunk = self._batch[i : i + self.batch_size]
                    self._send_batch(chunk)
                    for _ in range(len(chunk)):
                        self._queue.task_done()
                self._batch.clear()
                self._flush_trigger.clear()

    def shutdown(self, timeout: float = 5.0) -> None:
        """Flush remaining events, stop the background worker, and close HTTP client."""
        self.flush(timeout=timeout)
        self._stop_event.set()
        if self._thread.is_alive():
            self._thread.join(timeout=timeout)
        try:
            self._client.close()
        except (httpx.HTTPError, OSError, RuntimeError) as exc:
            logger.debug("Error closing HTTP client: %s", exc)


_exporter_instance: SentinelExporter | None = None
_exporter_lock = threading.Lock()


def get_exporter() -> SentinelExporter:
    """Return the singleton SentinelExporter instance."""
    global _exporter_instance
    if _exporter_instance is None:
        with _exporter_lock:
            if _exporter_instance is None:
                _exporter_instance = SentinelExporter()
    return _exporter_instance


def configure_sentinel(
    base_url: str | None = None,
    api_key: str | None = None,
    batch_size: int = 25,
    flush_interval: float = 0.25,
) -> SentinelExporter:
    """Configure or reconfigure the singleton SentinelExporter."""
    global _exporter_instance
    with _exporter_lock:
        if _exporter_instance is not None:
            _exporter_instance.shutdown(timeout=2.0)
        _exporter_instance = SentinelExporter(
            base_url=base_url,
            api_key=api_key,
            batch_size=batch_size,
            flush_interval=flush_interval,
        )
    return _exporter_instance


def flush(timeout: float = 5.0) -> None:
    """Synchronously flush the singleton exporter."""
    if _exporter_instance is not None:
        _exporter_instance.flush(timeout=timeout)


def _atexit_flush() -> None:
    if _exporter_instance is not None:
        _exporter_instance.flush(timeout=5.0)


atexit.register(_atexit_flush)


__all__ = [
    "SentinelExporter",
    "configure_sentinel",
    "flush",
    "get_exporter",
]
