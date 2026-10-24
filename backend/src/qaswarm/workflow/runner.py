"""Background runner: leases tasks, dispatches to agents, reaps expired leases.

Runs in-process with the API when ``AQS_RUNNER_ENABLED=true`` (default) and can also run as a
separate process: ``python -m qaswarm.workflow.runner``.
"""

from __future__ import annotations

import logging
import threading
import time

from qaswarm.config import Settings, get_settings
from qaswarm.db.session import session_factory
from qaswarm.workflow.orchestrator import Orchestrator

log = logging.getLogger("qaswarm.runner")


class Runner:
    def __init__(
        self, settings: Settings | None = None, orchestrator: Orchestrator | None = None
    ) -> None:
        self.settings = settings or get_settings()
        self.orchestrator = orchestrator or Orchestrator.from_settings(self.settings)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.last_error: str | None = None
        self.processed = 0

    def tick(self) -> int:
        factory = session_factory()
        with factory() as session:
            reaped = self.orchestrator.queue.reap_expired_leases(session)
            session.commit()
            if reaped:
                log.info("reaped expired leases", extra={"task_id": ",".join(reaped)})
        with factory() as session:
            n = self.orchestrator.run_once(session)
            self.processed += n
            return n

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                n = self.tick()
                self.last_error = None
            except Exception as exc:
                log.exception("runner tick failed")
                self.last_error = exc.__class__.__name__
                n = 0
            if n == 0:
                self._stop.wait(self.settings.runner_poll_seconds)

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._loop, name="raone-runner", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout)
            self._thread = None

    @property
    def alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()


def main() -> None:
    from qaswarm.telemetry.logging import configure_logging

    configure_logging()
    runner = Runner()
    log.info("runner started")
    try:
        while True:
            if runner.tick() == 0:
                time.sleep(runner.settings.runner_poll_seconds)
    except KeyboardInterrupt:
        log.info("runner stopped")


if __name__ == "__main__":
    main()
