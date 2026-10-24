"""Ref resolvers: ref → immutable commit SHA.

``GitLsRemoteResolver`` runs ``git ls-remote`` against the validated HTTPS URL. That contacts the
Git host but never downloads, checks out or executes repository content. ``FixtureRefResolver``
serves dev-only fixture repositories from a directory (``https://fixtures.local/<name>``), where
each ref is a sub-directory and the commit SHA is a deterministic tree hash.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from urllib.parse import urlsplit

from qaswarm.intake.hosts import HostRejected, resolve_public_host

FIXTURE_HOST = "fixtures.local"
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_REF_RE = re.compile(r"^[A-Za-z0-9._/@-]{1,255}$")


class IntakeError(Exception):
    """Intake failed. ``code`` follows the LLD error catalogue (E-INTAKE-00x)."""

    def __init__(self, code: str, reason: str, detail: str, *, policy: bool = False) -> None:
        self.code = code
        self.reason = reason
        self.detail = detail
        self.policy = policy  # True → job ends ``blocked`` (policy denied) instead of ``failed``
        super().__init__(detail)


@dataclass(frozen=True)
class ResolvedRef:
    commit_sha: str
    default_branch: str | None
    resolver: str


class RefResolver(Protocol):
    name: str

    def resolve(self, url: str, ref: str) -> ResolvedRef: ...


def _check_ref(ref: str) -> None:
    if not _REF_RE.match(ref) or ".." in ref or ref.startswith("-"):
        raise IntakeError("E-INTAKE-002", "invalid_ref", f"Ref '{ref}' is not a valid Git ref.")


class GitLsRemoteResolver:
    name = "git-ls-remote"

    def __init__(self, *, timeout_seconds: int = 60, dns_check: bool = True) -> None:
        self.timeout_seconds = timeout_seconds
        self.dns_check = dns_check

    def _run(self, args: list[str]) -> str:
        env = {
            "PATH": os.environ.get("PATH", ""),
            "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
            "HOME": os.environ.get("HOME", os.environ.get("USERPROFILE", "")),
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_ASKPASS": "echo",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_PROTOCOL_FROM_USER": "0",
        }
        try:
            # ls-remote only lists refs; nothing from the repository is downloaded or run.
            git = shutil.which("git") or "git"
            proc = subprocess.run(  # noqa: S603 - fixed argv, validated https URL, no shell
                [git, "-c", "protocol.allow=never", "-c", "protocol.https.allow=always", *args],
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                env=env,
                check=False,
            )
        except FileNotFoundError as exc:
            raise IntakeError("E-INTAKE-003", "git_unavailable", "git is not installed.") from exc
        except subprocess.TimeoutExpired as exc:
            raise IntakeError(
                "E-INTAKE-003", "timeout", "The Git host did not answer within the time limit."
            ) from exc
        if proc.returncode != 0:
            raise IntakeError(
                "E-INTAKE-003",
                "repository_unreachable",
                "The Git host rejected the request or the repository is not reachable.",
            )
        return proc.stdout

    def resolve(self, url: str, ref: str) -> ResolvedRef:
        _check_ref(ref)
        parts = urlsplit(url)
        if parts.scheme != "https" or not parts.hostname:
            raise IntakeError("E-INTAKE-001", "scheme_not_https", "Only https URLs.", policy=True)
        if self.dns_check:
            try:
                resolve_public_host(parts.hostname)
            except HostRejected as exc:
                raise IntakeError("E-INTAKE-001", exc.reason, exc.message, policy=True) from exc
        if _SHA_RE.match(ref):
            return ResolvedRef(ref, None, self.name)
        out = self._run(
            [
                "ls-remote",
                "--symref",
                url,
                "HEAD",
                ref,
                f"refs/heads/{ref}",
                f"refs/tags/{ref}",
                f"refs/pull/{ref}/head",
            ]
        )
        default_branch: str | None = None
        candidates: dict[str, str] = {}
        for line in out.splitlines():
            if line.startswith("ref: ") and "\tHEAD" in line:
                default_branch = line.split()[1].removeprefix("refs/heads/")
                continue
            if "\t" not in line:
                continue
            found_sha, found_name = line.split("\t", 1)
            candidates[found_name.strip()] = found_sha.strip()
        for name in (f"refs/heads/{ref}", f"refs/tags/{ref}", f"refs/pull/{ref}/head", ref):
            resolved = candidates.get(name)
            if resolved and _SHA_RE.match(resolved):
                return ResolvedRef(resolved, default_branch, self.name)
        raise IntakeError(
            "E-INTAKE-002", "unresolvable_ref", f"Ref '{ref}' does not exist on the remote."
        )


def tree_hash(directory: Path) -> str:
    """Deterministic 40-hex hash over relative paths and file bytes (fixture 'commit SHA')."""
    h = hashlib.sha1(usedforsecurity=False)
    for path in sorted(p for p in directory.rglob("*") if p.is_file()):
        rel = path.relative_to(directory).as_posix()
        h.update(rel.encode("utf-8") + b"\0")
        h.update(path.read_bytes() + b"\0")
    return h.hexdigest()


class FixtureRefResolver:
    name = "fixture"

    def __init__(self, fixtures_dir: str | os.PathLike[str]) -> None:
        self.fixtures_dir = Path(fixtures_dir)

    def resolve(self, url: str, ref: str) -> ResolvedRef:
        _check_ref(ref)
        parts = urlsplit(url)
        name = fixture_name(parts.hostname, parts.path)
        if name is None:
            raise IntakeError("E-INTAKE-001", "not_a_fixture", "Not a fixture URL.", policy=True)
        ref_dir = self.fixtures_dir / name / "refs" / ref
        if not ref_dir.is_dir():
            raise IntakeError(
                "E-INTAKE-002", "unresolvable_ref", f"Fixture '{name}' has no ref '{ref}'."
            )
        refs_dir = self.fixtures_dir / name / "refs"
        default = "main" if (refs_dir / "main").is_dir() else None
        return ResolvedRef(tree_hash(ref_dir), default, self.name)


_FIXTURE_PATH = re.compile(r"^[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)?$")


def fixture_name(hostname: str | None, path: str) -> str | None:
    """``https://fixtures.local/<owner>/<name>`` → ``name`` (owner is ignored); None if invalid."""
    clean = path.strip("/")
    segments = clean.split("/")
    if (
        hostname != FIXTURE_HOST
        or not _FIXTURE_PATH.match(clean)
        or any(seg in {".", ".."} for seg in segments)
    ):
        return None
    return clean.split("/")[-1]


def is_fixture_url(url: str) -> bool:
    return urlsplit(url).hostname == FIXTURE_HOST


def resolver_for(
    url: str, *, dev_fixture_repos: bool, fixtures_dir: str, timeout_seconds: int, dns_check: bool
) -> RefResolver:
    if is_fixture_url(url):
        if not dev_fixture_repos:
            raise IntakeError(
                "E-INTAKE-001",
                "fixtures_disabled",
                "Fixture repositories are disabled (AQS_DEV_FIXTURE_REPOS).",
                policy=True,
            )
        return FixtureRefResolver(fixtures_dir)
    return GitLsRemoteResolver(timeout_seconds=timeout_seconds, dns_check=dns_check)
