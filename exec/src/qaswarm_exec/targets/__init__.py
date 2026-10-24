"""Target Environment Manager (phase 4).

Turns the ``target`` descriptor of a task into a :class:`ResolvedTarget` for the engines and
owns the lifecycle of the worker-started local fixture target. Descriptors are produced by the
control plane's planner and contain no secrets::

    {"kind": "local_fixture", "name": "sample-target-app"}
    {"kind": "registered", "target_id": "tgt_…", "base_url": "https://staging.example.test",
     "allowed_hosts": ["staging.example.test"], "allowed_activities": ["api", "security"]}
"""

from __future__ import annotations

from pathlib import Path
from types import TracebackType
from typing import Any

from qaswarm_exec.targets.local_app import LocalTargetApp, LocalTargetError
from qaswarm_exec.targets.policy import (
    ResolvedTarget,
    TargetBlocked,
    TargetPolicy,
    hosts_for,
)

__all__ = [
    "LocalTargetError",
    "ResolvedTarget",
    "TargetBlocked",
    "TargetPolicy",
    "TargetSession",
    "hosts_for",
]


class TargetSession:
    """Context manager yielding the resolved target; starts/stops the local fixture app."""

    def __init__(
        self,
        descriptor: dict[str, Any] | None,
        *,
        fixtures_dir: str | None,
        allow_local: bool,
        out_dir: Path,
        max_redirects: int = 5,
    ) -> None:
        self.descriptor = descriptor or {}
        self.fixtures_dir = fixtures_dir
        self.allow_local = allow_local
        self.out_dir = out_dir
        self.max_redirects = max_redirects
        self._app: LocalTargetApp | None = None

    def __enter__(self) -> ResolvedTarget:
        kind = str(self.descriptor.get("kind", ""))
        if kind == "local_fixture":
            if not self.fixtures_dir:
                raise TargetBlocked(
                    "local_fixture", "fixtures_disabled", "fixture targets are disabled"
                )
            name = str(self.descriptor.get("name", "sample-target-app"))
            self._app = LocalTargetApp(self.fixtures_dir, name, self.out_dir / f"{name}.log")
            app = self._app.__enter__()
            policy = TargetPolicy(
                allowed_hosts=hosts_for(app.base_url),
                allow_local=True,
                local_fixture=True,
                max_redirects=self.max_redirects,
            )
            return ResolvedTarget(
                kind="local_fixture",
                base_url=app.base_url,
                policy=policy,
                name=name,
                allowed_activities=frozenset({"api", "browser", "security", "performance"}),
            )
        if kind == "registered":
            base_url = str(self.descriptor.get("base_url", ""))
            extra = [str(h) for h in self.descriptor.get("allowed_hosts", [])]
            policy = TargetPolicy(
                allowed_hosts=hosts_for(base_url, extra),
                allow_local=self.allow_local,
                local_fixture=False,
                max_redirects=self.max_redirects,
            )
            policy.check_url(base_url)  # scheme, authority, address class — refused early
            return ResolvedTarget(
                kind="registered",
                base_url=base_url,
                policy=policy,
                name=str(self.descriptor.get("name", "")),
                target_id=self.descriptor.get("target_id"),
                allowed_activities=frozenset(
                    str(a) for a in self.descriptor.get("allowed_activities", [])
                ),
            )
        raise TargetBlocked("", "no_target", "the task has no target descriptor")

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._app is not None:
            self._app.__exit__(exc_type, exc, tb)
            self._app = None
