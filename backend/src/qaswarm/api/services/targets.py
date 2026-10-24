"""Target environments and HA-01 authorizations (FR-050, phase 4).

A target is a registered **non-production** base URL owned by someone who can attest that testing
it is permitted. The control plane validates the URL syntactically and refuses loopback/private
address literals unless controlled local testing is enabled; the Execution Service re-checks the
resolved address at connect time. Credentials never live here.
"""

from __future__ import annotations

import ipaddress
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from qaswarm.api.auth import Principal
from qaswarm.api.errors import Problem
from qaswarm.api.schemas import AuthorizationCreate, AuthorizationOut, TargetCreate, TargetOut
from qaswarm.audit.chain import append_event
from qaswarm.config import Settings
from qaswarm.db.models import Project, TargetAuthorization, TargetEnvironment
from qaswarm.domain.ids import new_id
from qaswarm.intake.hosts import is_public_address

ACTIVITIES: tuple[str, ...] = ("api", "browser", "security", "performance")
MAX_AUTHORIZATION_DAYS = 366
_LOCAL_NAMES = frozenset({"localhost", "localhost.localdomain"})


def _now() -> datetime:
    return datetime.now(UTC)


def validate_base_url(url: str, *, allow_local: bool) -> str:
    parts = urlsplit(url.strip())
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise Problem(
            422, "validation_failed", "base_url must be an absolute http(s) URL with a host."
        )
    if parts.username or parts.password:
        raise Problem(422, "validation_failed", "base_url must not contain credentials.")
    if parts.query or parts.fragment:
        raise Problem(422, "validation_failed", "base_url must not contain a query or fragment.")
    host = parts.hostname.lower()
    literal: str | None = None
    try:
        literal = str(ipaddress.ip_address(host))
    except ValueError:
        literal = None
    if not allow_local and (host in _LOCAL_NAMES or (literal and not is_public_address(literal))):
        raise Problem(
            422,
            "target_host_not_allowed",
            "Loopback, private, link-local and metadata addresses are refused as targets. Set "
            "AQS_ALLOW_LOCAL_TARGETS=true (control plane) and AQS_EXEC_ALLOW_LOCAL_TARGETS=true "
            "(worker) for controlled local testing.",
        )
    normalized = f"{parts.scheme}://{parts.netloc.lower()}{parts.path.rstrip('/')}"
    return normalized


def _active(auth: TargetAuthorization, now: datetime) -> bool:
    return auth.revoked_at is None and auth.valid_from <= now < auth.valid_until


def _auth_out(auth: TargetAuthorization, now: datetime) -> AuthorizationOut:
    return AuthorizationOut(
        id=auth.id,
        target_id=auth.target_id,
        attested_by=auth.attested_by,
        attested_role=auth.attested_role,
        allowed_activities=list(auth.allowed_activities.get("items", [])),
        valid_from=auth.valid_from,
        valid_until=auth.valid_until,
        revoked_at=auth.revoked_at,
        note=auth.note,
        active=_active(auth, now),
        created_at=auth.created_at,
    )


def active_authorization(session: Session, target_id: str) -> TargetAuthorization | None:
    now = _now()
    rows = session.execute(
        select(TargetAuthorization)
        .where(TargetAuthorization.target_id == target_id)
        .order_by(TargetAuthorization.created_at.desc())
    ).scalars()
    for auth in rows:
        if _active(auth, now):
            return auth
    return None


def to_out(session: Session, target: TargetEnvironment) -> TargetOut:
    auth = active_authorization(session, target.id)
    return TargetOut(
        id=target.id,
        org_id=target.org_id,
        project_id=target.project_id,
        name=target.name,
        kind=target.kind,
        environment_type=target.environment_type,
        base_url=target.base_url,
        owner=target.owner,
        allowed_hosts=list(target.network_scope.get("hosts", [])),
        credential_ref_id=target.credential_ref_id,
        active_authorization=_auth_out(auth, _now()) if auth else None,
        created_at=target.created_at,
        updated_at=target.updated_at,
        version=target.version,
    )


def get_target_row(session: Session, principal: Principal, target_id: str) -> TargetEnvironment:
    target = session.execute(
        select(TargetEnvironment).where(
            TargetEnvironment.id == target_id,
            TargetEnvironment.org_id == principal.org_id,
            TargetEnvironment.archived_at.is_(None),
        )
    ).scalar_one_or_none()
    if target is None:
        raise Problem(404, "not_found", "Target environment not found.")
    return target


def create_target(
    session: Session,
    principal: Principal,
    body: TargetCreate,
    settings: Settings,
    correlation_id: str | None,
) -> TargetOut:
    project = session.execute(
        select(Project).where(
            Project.id == body.project_id,
            Project.org_id == principal.org_id,
            Project.archived_at.is_(None),
        )
    ).scalar_one_or_none()
    if project is None:
        raise Problem(404, "not_found", "Project not found.")
    base_url = validate_base_url(body.base_url, allow_local=settings.allow_local_targets)
    hosts = sorted({h.strip().lower() for h in body.allowed_hosts if h.strip()})
    target = TargetEnvironment(
        id=new_id("target_environment"),
        org_id=principal.org_id,
        project_id=project.id,
        name=body.name,
        kind=body.kind,
        environment_type=body.environment_type,
        base_url=base_url,
        owner=body.owner,
        network_scope={"hosts": hosts},
        credential_ref_id=body.credential_ref_id,
        version=1,
    )
    session.add(target)
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise Problem(
            409, "conflict", f"A target named '{body.name}' already exists in this project."
        ) from exc
    append_event(
        session,
        org_id=principal.org_id,
        actor_type="user",
        actor_id=principal.user_id,
        actor_role=principal.role.value,
        action="target.registered",
        subject_type="target_environment",
        subject_id=target.id,
        correlation_id=correlation_id,
        details={
            "project_id": project.id,
            "name": target.name,
            "environment_type": target.environment_type,
            "base_url": target.base_url,
            "allowed_hosts": hosts,
        },
    )
    return to_out(session, target)


def list_targets(
    session: Session, principal: Principal, *, project_id: str | None
) -> list[TargetOut]:
    stmt = (
        select(TargetEnvironment)
        .where(
            TargetEnvironment.org_id == principal.org_id, TargetEnvironment.archived_at.is_(None)
        )
        .order_by(TargetEnvironment.created_at)
    )
    if project_id:
        stmt = stmt.where(TargetEnvironment.project_id == project_id)
    return [to_out(session, t) for t in session.execute(stmt).scalars()]


def create_authorization(
    session: Session,
    principal: Principal,
    target_id: str,
    body: AuthorizationCreate,
    correlation_id: str | None,
) -> AuthorizationOut:
    target = get_target_row(session, principal, target_id)
    now = _now()
    valid_from = body.valid_from or now
    if body.valid_until <= valid_from:
        raise Problem(422, "validation_failed", "valid_until must be after valid_from.")
    if body.valid_until - valid_from > timedelta(days=MAX_AUTHORIZATION_DAYS):
        raise Problem(
            422,
            "validation_failed",
            f"An attestation may not exceed {MAX_AUTHORIZATION_DAYS} days.",
        )
    activities = sorted({a for a in body.allowed_activities})
    # Design: no two active attestations overlap for the same activity. A new attestation
    # supersedes the active one; the supersession is audited.
    superseded: list[str] = []
    for existing in session.execute(
        select(TargetAuthorization).where(TargetAuthorization.target_id == target.id)
    ).scalars():
        if _active(existing, now) and set(existing.allowed_activities.get("items", [])) & set(
            activities
        ):
            existing.revoked_at = now
            superseded.append(existing.id)
    auth = TargetAuthorization(
        id=new_id("target_authorization"),
        org_id=principal.org_id,
        target_id=target.id,
        attested_by=principal.user_id,
        attested_role=principal.role.value,
        allowed_activities={"items": activities},
        valid_from=valid_from,
        valid_until=body.valid_until,
        note=body.note,
    )
    session.add(auth)
    session.flush()
    append_event(
        session,
        org_id=principal.org_id,
        actor_type="user",
        actor_id=principal.user_id,
        actor_role=principal.role.value,
        action="target.authorized",
        subject_type="target_authorization",
        subject_id=auth.id,
        correlation_id=correlation_id,
        details={
            "approval": "HA-01",
            "target_id": target.id,
            "allowed_activities": activities,
            "valid_from": valid_from.isoformat(),
            "valid_until": body.valid_until.isoformat(),
            "superseded": superseded,
        },
    )
    return _auth_out(auth, now)


def revoke_authorization(
    session: Session,
    principal: Principal,
    target_id: str,
    authorization_id: str,
    correlation_id: str | None,
) -> None:
    target = get_target_row(session, principal, target_id)
    auth = session.execute(
        select(TargetAuthorization).where(
            TargetAuthorization.id == authorization_id,
            TargetAuthorization.target_id == target.id,
        )
    ).scalar_one_or_none()
    if auth is None:
        raise Problem(404, "not_found", "Authorization not found.")
    if auth.revoked_at is None:
        auth.revoked_at = _now()
        append_event(
            session,
            org_id=principal.org_id,
            actor_type="user",
            actor_id=principal.user_id,
            actor_role=principal.role.value,
            action="target.authorization_revoked",
            subject_type="target_authorization",
            subject_id=auth.id,
            correlation_id=correlation_id,
            details={"target_id": target.id},
        )


# ----------------------------------------------------------------- policy evaluation
def evaluate_target_policy(
    session: Session, org_id: str, target_id: str, activities: set[str]
) -> tuple[dict[str, Any] | None, str | None]:
    """Resolve a job's target into a task descriptor, or return the refusal reason.

    Returns ``(descriptor, None)`` when the target exists and an active HA-01 attestation covers
    every requested activity; otherwise ``(None, reason)``. The descriptor carries no secrets.
    """
    target = session.execute(
        select(TargetEnvironment).where(
            TargetEnvironment.id == target_id,
            TargetEnvironment.org_id == org_id,
            TargetEnvironment.archived_at.is_(None),
        )
    ).scalar_one_or_none()
    if target is None:
        return None, "target_not_found"
    auth = active_authorization(session, target.id)
    if auth is None:
        return None, "target_not_authorized"
    allowed = set(auth.allowed_activities.get("items", []))
    missing = sorted(activities - allowed)
    if missing:
        return None, "activities_not_authorized:" + ",".join(missing)
    return {
        "kind": "registered",
        "target_id": target.id,
        "name": target.name,
        "base_url": target.base_url,
        "allowed_hosts": list(target.network_scope.get("hosts", [])),
        "allowed_activities": sorted(allowed),
        "authorization_id": auth.id,
        "authorization_valid_until": auth.valid_until.isoformat(),
    }, None
