"""Principal resolution.

Dev-only header auth when ``AQS_DEV_AUTH=true`` (``X-Dev-User`` / ``X-Dev-Role``; query parameters
``dev_user`` / ``dev_role`` are accepted for the SSE endpoint because EventSource cannot send
headers). Otherwise every ``/api/v1`` call is 401: OIDC arrives in slice 3e.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from qaswarm.api.deps import get_db
from qaswarm.api.errors import Problem
from qaswarm.config import Settings, get_settings
from qaswarm.db.models import Organization
from qaswarm.domain.enums import Role

WRITE_ROLES: frozenset[Role] = frozenset(
    {Role.ORG_ADMIN, Role.QA_LEAD, Role.QA_ENGINEER, Role.DEVELOPER, Role.CI_SERVICE_ACCOUNT}
)
PROJECT_WRITE_ROLES: frozenset[Role] = frozenset({Role.ORG_ADMIN, Role.QA_LEAD})


@dataclass(frozen=True)
class Principal:
    user_id: str
    role: Role
    org_id: str
    source: str  # "dev" today; "oidc" in slice 3e


def _resolve_role(raw: str | None) -> Role:
    if raw is None:
        return Role.VIEWER
    try:
        return Role(raw)
    except ValueError as exc:
        raise Problem(
            400,
            "bad_request",
            f"Unknown X-Dev-Role. Allowed roles: {', '.join(r.value for r in Role)}.",
        ) from exc


def get_principal(
    request: Request,
    session: Session = Depends(get_db, scope="function"),
    settings: Settings = Depends(get_settings),
) -> Principal:
    if not settings.dev_auth:
        raise Problem(
            401,
            "unauthenticated",
            "No authentication is configured. OIDC bearer authentication arrives in slice 3e; "
            "set AQS_DEV_AUTH=true for local development.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = request.headers.get("x-dev-user")
    role_raw = request.headers.get("x-dev-role")
    # Query-parameter credentials only where EventSource forces them (SSE); everywhere else they
    # would leak into access logs and browser history for no reason.
    if request.url.path.endswith("/events"):
        user = user or request.query_params.get("dev_user")
        role_raw = role_raw or request.query_params.get("dev_role")
    if not user:
        raise Problem(
            401,
            "unauthenticated",
            "Dev auth is enabled: send X-Dev-User and X-Dev-Role headers.",
            headers={"WWW-Authenticate": "X-Dev-User"},
        )
    role = _resolve_role(role_raw)
    org_id = session.execute(
        select(Organization.id).order_by(Organization.created_at).limit(1)
    ).scalar_one_or_none()
    if org_id is None:
        raise Problem(
            503,
            "dependency_unavailable",
            "No organization exists yet. Run the seed command (make seed).",
        )
    return Principal(user_id=user[:200], role=role, org_id=org_id, source="dev")


def require_role(*roles: Role) -> Any:
    allowed = frozenset(roles)

    def _check(principal: Principal = Depends(get_principal)) -> Principal:
        if principal.role not in allowed:
            raise Problem(
                403,
                "insufficient_role",
                f"Role '{principal.role.value}' may not perform this action. "
                f"Allowed: {', '.join(sorted(r.value for r in allowed))}.",
                required_roles=sorted(r.value for r in allowed),
            )
        return principal

    return Depends(_check)
