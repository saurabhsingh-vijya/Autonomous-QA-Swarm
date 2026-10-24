"""Repository registration with **syntactic** URL validation only (slice 1a).

Full SSRF defence (DNS pinning, private-address rejection, redirect checks) is slice 1b and is
stated in ``validation_note``. Nothing is fetched here.
"""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from qaswarm.api.auth import Principal
from qaswarm.api.errors import Problem
from qaswarm.api.pagination import encode_cursor
from qaswarm.api.schemas import RepositoryCreate, RepositoryOut
from qaswarm.api.services.projects import get_project_row
from qaswarm.audit.chain import append_event
from qaswarm.config import Settings
from qaswarm.db.models import Repository
from qaswarm.domain.enums import RepositoryProvider, RepositoryValidationStatus
from qaswarm.domain.ids import new_id

VALIDATION_NOTE = (
    "Syntactic validation only (slice 1a): HTTPS scheme, allow-listed host, owner/repo path and no "
    "credentials in the URL were checked. DNS pinning, private-address rejection and reachability "
    "checks arrive in slice 1b. No code was fetched."
)

_OWNER_REPO = re.compile(
    r"^/([A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?)/([A-Za-z0-9._-]+?)(?:\.git)?/?$"
)
_PROVIDER_HOSTS = {RepositoryProvider.GITHUB: "github.com", RepositoryProvider.GITLAB: "gitlab.com"}


@dataclass(frozen=True)
class UrlRejected(Exception):
    reason: str
    code: str
    message: str


def validate_repository_url(url: str, provider: RepositoryProvider, settings: Settings) -> str:
    """Return the normalised URL or raise ``UrlRejected``. Purely syntactic."""
    parts = urlsplit(url.strip())
    if parts.scheme.lower() != "https":
        raise UrlRejected("scheme_not_https", "scheme", "Only https:// URLs are accepted.")
    if parts.username or parts.password or "@" in parts.netloc:
        raise UrlRejected(
            "credentials_in_url",
            "credentials",
            "Credentials in the URL are not accepted; use a credential reference.",
        )
    host = (parts.hostname or "").lower()
    if not host:
        raise UrlRejected("host_not_allow_listed", "host", "The URL has no host.")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise UrlRejected(
            "host_not_allow_listed",
            "host",
            "IP-address hosts are not accepted; use an allow-listed Git host.",
        )
    if parts.port not in (None, 443):
        raise UrlRejected("host_not_allow_listed", "host", "Non-standard ports are not accepted.")
    allowed = {h.lower() for h in settings.git_host_allowlist}
    if settings.dev_fixture_repos:
        allowed.add("fixtures.local")  # dev-only fixture repositories (phase 2)
    if host not in allowed:
        raise UrlRejected(
            "host_not_allow_listed", "host", f"Host '{host}' is not on the Git provider allow-list."
        )
    expected = _PROVIDER_HOSTS.get(provider)
    if expected and host != expected:
        raise UrlRejected(
            "host_not_allow_listed",
            "provider_mismatch",
            f"Provider '{provider.value}' expects host {expected}.",
        )
    if parts.query or parts.fragment:
        raise UrlRejected("path_shape", "path", "Query strings and fragments are not accepted.")
    match = _OWNER_REPO.match(parts.path)
    if not match:
        raise UrlRejected("path_shape", "path", "Path must have the shape owner/repo.")
    owner, repo = match.group(1), match.group(2)
    return f"https://{host}/{owner}/{repo}".lower()


def _reject(reason: str, code: str, message: str) -> Problem:
    return Problem(
        422,
        "repository_url_rejected",
        "The repository URL was rejected: " + message,
        title="Repository URL rejected",
        reason=reason,
        errors=[{"pointer": "/url", "code": code, "message": message}],
    )


def create_repository(
    session: Session,
    principal: Principal,
    body: RepositoryCreate,
    settings: Settings,
    correlation_id: str | None,
) -> RepositoryOut:
    project = get_project_row(session, principal, body.project_id)
    try:
        normalized = validate_repository_url(body.url, body.provider, settings)
    except UrlRejected as exc:
        raise _reject(exc.reason, exc.code, exc.message) from None
    repo = Repository(
        id=new_id("repository"),
        org_id=principal.org_id,
        project_id=project.id,
        provider=body.provider.value,
        url=body.url.strip(),
        normalized_url=normalized,
        default_branch=body.default_branch,
        validation_status=RepositoryValidationStatus.PENDING_VALIDATION.value,
        validation_note=VALIDATION_NOTE,
        language_support="unknown",
        credential_ref_id=body.credential_ref_id,
    )
    session.add(repo)
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise Problem(
            409,
            "repository_exists",
            "This repository URL is already registered in the organization.",
        ) from exc
    append_event(
        session,
        org_id=principal.org_id,
        actor_type="user",
        actor_id=principal.user_id,
        actor_role=principal.role.value,
        action="repository.registered",
        subject_type="repository",
        subject_id=repo.id,
        correlation_id=correlation_id,
        details={"project_id": project.id, "url": normalized, "provider": repo.provider},
    )
    return RepositoryOut.model_validate(repo)


def get_repository_row(session: Session, principal: Principal, repository_id: str) -> Repository:
    repo = session.execute(
        select(Repository).where(
            Repository.id == repository_id,
            Repository.org_id == principal.org_id,
            Repository.archived_at.is_(None),
        )
    ).scalar_one_or_none()
    if repo is None:
        raise Problem(404, "not_found", "Repository not found.")
    return repo


def list_repositories(
    session: Session,
    principal: Principal,
    *,
    project_id: str | None,
    limit: int,
    after: str | None,
) -> tuple[list[RepositoryOut], str | None]:
    stmt = (
        select(Repository)
        .where(Repository.org_id == principal.org_id, Repository.archived_at.is_(None))
        .order_by(Repository.id.desc())
        .limit(limit + 1)
    )
    if project_id:
        stmt = stmt.where(Repository.project_id == project_id)
    if after:
        stmt = stmt.where(Repository.id < after)
    rows = list(session.execute(stmt).scalars())
    next_cursor = encode_cursor(rows[limit - 1].id) if len(rows) > limit else None
    return [RepositoryOut.model_validate(r) for r in rows[:limit]], next_cursor
