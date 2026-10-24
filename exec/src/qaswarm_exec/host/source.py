"""Source fetchers: bring the pinned commit into a disposable workspace.

``GitSourceFetcher`` fetches exactly one commit over HTTPS with hooks, LFS and submodules
disabled, exports it with ``git archive`` and extracts it with path checks. ``FixtureSourceFetcher``
copies a dev-only fixture directory. Both return the same deterministic snapshot digest so results
are comparable regardless of the source.
"""

from __future__ import annotations

import hashlib
import io
import os
import re
import shutil
import subprocess
import tarfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlsplit

FIXTURE_HOST = "fixtures.local"
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_FIXTURE_PATH = re.compile(r"^[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)?$")
IGNORED_DIRS = {".git", "__pycache__", "node_modules", ".venv", ".mypy_cache", ".pytest_cache"}


class FetchError(Exception):
    def __init__(self, code: str, detail: str, *, retryable: bool = True) -> None:
        self.code = code
        self.detail = detail
        self.retryable = retryable
        super().__init__(detail)


@dataclass(frozen=True)
class FetchedSource:
    commit_sha: str
    snapshot_sha256: str
    file_count: int
    total_bytes: int
    fetcher: str


class SourceFetcher(Protocol):
    name: str

    def fetch(self, source: dict[str, Any], dest: Path) -> FetchedSource: ...


def iter_files(root: Path) -> list[Path]:
    out: list[Path] = []
    for path in sorted(root.rglob("*")):
        if any(part in IGNORED_DIRS for part in path.relative_to(root).parts):
            continue
        if path.is_file() and not path.is_symlink():
            out.append(path)
    return out


def tree_hash(directory: Path) -> str:
    """Deterministic 40-hex hash over relative paths and bytes (fixture 'commit SHA')."""
    h = hashlib.sha1(usedforsecurity=False)
    for path in iter_files(directory):
        rel = path.relative_to(directory).as_posix()
        h.update(rel.encode("utf-8") + b"\0")
        h.update(path.read_bytes() + b"\0")
    return h.hexdigest()


def snapshot_digest(directory: Path) -> tuple[str, int, int]:
    """SHA-256 of a deterministic tarball of ``directory`` (sorted, mtime 0, uid/gid 0)."""
    buf = io.BytesIO()
    count = 0
    total = 0
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.PAX_FORMAT) as tar:
        for path in iter_files(directory):
            data = path.read_bytes()
            info = tarfile.TarInfo(path.relative_to(directory).as_posix())
            info.size = len(data)
            info.mtime = 0
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            info.mode = 0o644
            tar.addfile(info, io.BytesIO(data))
            count += 1
            total += len(data)
    return hashlib.sha256(buf.getvalue()).hexdigest(), count, total


def safe_extract_tar(
    data: bytes, dest: Path, *, max_files: int = 50_000, max_bytes: int = 2_000_000_000
) -> int:
    dest = dest.resolve()
    extracted = 0
    total = 0
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:*") as tar:
        for member in tar.getmembers():
            name = member.name
            if name.startswith(("/", "\\")) or ".." in Path(name).parts:
                raise FetchError("E-EXEC-001", f"unsafe path in archive: {name}", retryable=False)
            target = (dest / name).resolve()
            if not str(target).startswith(str(dest)):
                raise FetchError("E-EXEC-001", f"unsafe path in archive: {name}", retryable=False)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if not member.isfile():
                continue  # symlinks, devices and hard links are dropped
            extracted += 1
            total += member.size
            if extracted > max_files or total > max_bytes:
                raise FetchError("E-EXEC-001", "snapshot exceeds size limits", retryable=False)
            target.parent.mkdir(parents=True, exist_ok=True)
            src = tar.extractfile(member)
            target.write_bytes(src.read() if src else b"")
    return extracted


_GIT_ENV = {
    "GIT_TERMINAL_PROMPT": "0",
    "GIT_ASKPASS": "echo",
    "GIT_LFS_SKIP_SMUDGE": "1",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_CONFIG_GLOBAL": os.devnull,
}
_GIT_FLAGS = [
    "-c",
    "core.hooksPath=" + os.devnull,
    "-c",
    "protocol.allow=never",
    "-c",
    "protocol.https.allow=always",
    "-c",
    "submodule.recurse=false",
    "-c",
    "core.fsmonitor=false",
]


class GitSourceFetcher:
    name = "git"

    def __init__(self, *, timeout_seconds: int = 300) -> None:
        self.timeout_seconds = timeout_seconds

    def _git(self, args: list[str], cwd: Path) -> subprocess.CompletedProcess[bytes]:
        env = {
            "PATH": os.environ.get("PATH", ""),
            "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
            "HOME": str(cwd),
            "USERPROFILE": str(cwd),
            **_GIT_ENV,
        }
        try:
            # Fixed argv, validated https URL, no shell; hooks/LFS/submodules disabled above.
            git = shutil.which("git") or "git"
            return subprocess.run(  # noqa: S603
                [git, *_GIT_FLAGS, *args],
                cwd=cwd,
                capture_output=True,
                timeout=self.timeout_seconds,
                env=env,
                check=False,
            )
        except FileNotFoundError as exc:
            raise FetchError("E-EXEC-001", "git is not installed on the worker host") from exc
        except subprocess.TimeoutExpired as exc:
            raise FetchError("E-EXEC-003", "git fetch timed out") from exc

    def fetch(self, source: dict[str, Any], dest: Path) -> FetchedSource:
        url = str(source.get("repository_url", ""))
        sha = str(source.get("commit_sha", ""))
        ref = str(source.get("ref", ""))
        parts = urlsplit(url)
        if parts.scheme != "https" or not parts.hostname:
            raise FetchError("E-EXEC-003", "repository URL must be https", retryable=False)
        if not _SHA_RE.match(sha):
            raise FetchError("E-EXEC-003", "no pinned commit SHA for this job", retryable=False)
        work = dest.parent / "git-fetch"
        work.mkdir(parents=True, exist_ok=True)
        if self._git(["init", "-q", "repo"], work).returncode != 0:
            raise FetchError("E-EXEC-001", "git init failed")
        repo = work / "repo"
        self._git(["remote", "add", "origin", url], repo)
        fetched = self._git(["fetch", "-q", "--depth", "1", "--no-tags", "origin", sha], repo)
        if fetched.returncode != 0 and ref:
            fetched = self._git(["fetch", "-q", "--depth", "200", "--no-tags", "origin", ref], repo)
        if fetched.returncode != 0:
            raise FetchError(
                "E-EXEC-003",
                "could not fetch the pinned commit: "
                + fetched.stderr.decode(errors="replace")[-300:].strip(),
            )
        if self._git(["cat-file", "-e", f"{sha}^{{commit}}"], repo).returncode != 0:
            raise FetchError(
                "E-EXEC-003", "pinned commit is not reachable from the ref", retryable=False
            )
        archive = self._git(["archive", "--format=tar", sha], repo)
        if archive.returncode != 0:
            raise FetchError("E-EXEC-001", "git archive failed")
        dest.mkdir(parents=True, exist_ok=True)
        count = safe_extract_tar(archive.stdout, dest)
        shutil.rmtree(work, ignore_errors=True)
        digest, n, total = snapshot_digest(dest)
        return FetchedSource(sha, digest, max(count, n), total, self.name)


class FixtureSourceFetcher:
    name = "fixture"

    def __init__(self, fixtures_dir: str | os.PathLike[str]) -> None:
        self.fixtures_dir = Path(fixtures_dir)

    def fetch(self, source: dict[str, Any], dest: Path) -> FetchedSource:
        url = str(source.get("repository_url", ""))
        ref = str(source.get("ref", ""))
        sha = str(source.get("commit_sha", ""))
        parts = urlsplit(url)
        clean = parts.path.strip("/")
        if (
            parts.hostname != FIXTURE_HOST
            or not _FIXTURE_PATH.match(clean)
            or any(seg in {".", ".."} for seg in clean.split("/"))
        ):
            raise FetchError("E-EXEC-003", "not a fixture URL", retryable=False)
        name = clean.split("/")[-1]  # https://fixtures.local/<owner>/<name>; owner is ignored
        if not re.fullmatch(r"[A-Za-z0-9._/@-]{1,255}", ref) or ".." in ref:
            raise FetchError("E-EXEC-003", "invalid ref", retryable=False)
        src = self.fixtures_dir / name / "refs" / ref
        if not src.is_dir():
            raise FetchError("E-EXEC-003", f"fixture ref '{ref}' not found", retryable=False)
        actual = tree_hash(src)
        if sha and actual != sha:
            raise FetchError(
                "E-EXEC-003", "fixture content changed since the ref was pinned", retryable=False
            )
        shutil.copytree(src, dest, dirs_exist_ok=True, ignore=shutil.ignore_patterns(*IGNORED_DIRS))
        digest, n, total = snapshot_digest(dest)
        return FetchedSource(actual, digest, n, total, self.name)


def fetcher_for(source: dict[str, Any], fixtures_dir: str | None) -> SourceFetcher:
    url = str(source.get("repository_url", ""))
    if urlsplit(url).hostname == FIXTURE_HOST:
        if not fixtures_dir:
            raise FetchError("E-EXEC-003", "fixture repositories are disabled", retryable=False)
        return FixtureSourceFetcher(fixtures_dir)
    return GitSourceFetcher()
