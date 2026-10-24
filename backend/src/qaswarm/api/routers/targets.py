from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from qaswarm.api.auth import Principal, get_principal, require_role
from qaswarm.api.deps import get_db
from qaswarm.api.etag import etag_for
from qaswarm.api.schemas import AuthorizationCreate, AuthorizationOut, TargetCreate, TargetOut
from qaswarm.api.services import targets as svc
from qaswarm.config import Settings, get_settings
from qaswarm.domain.enums import Role
from qaswarm.telemetry.logging import correlation_id_var

router = APIRouter(prefix="/targets", tags=["targets"])

# Contract scopes: ``targets:write`` → Org Admin; ``targets:authorize`` → Org Admin, Security
# Reviewer (HA-01, AC-149).
TARGET_WRITE_ROLES = (Role.ORG_ADMIN,)
TARGET_AUTHORIZE_ROLES = (Role.ORG_ADMIN, Role.SECURITY_REVIEWER)


@router.post("", response_model=TargetOut, status_code=status.HTTP_201_CREATED)
def register_target(
    body: TargetCreate,
    response: Response,
    session: Session = Depends(get_db),
    principal: Principal = require_role(*TARGET_WRITE_ROLES),
    settings: Settings = Depends(get_settings),
) -> TargetOut:
    out = svc.create_target(session, principal, body, settings, correlation_id_var.get())
    response.headers["Location"] = f"/api/v1/targets/{out.id}"
    response.headers["ETag"] = etag_for(out.id, out.version)
    return out


@router.get("", response_model=list[TargetOut])
def list_targets(
    project_id: str | None = Query(default=None),
    session: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> list[TargetOut]:
    return svc.list_targets(session, principal, project_id=project_id)


@router.get("/{target_id}", response_model=TargetOut)
def get_target(
    target_id: str,
    response: Response,
    session: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> TargetOut:
    target = svc.get_target_row(session, principal, target_id)
    response.headers["ETag"] = etag_for(target.id, target.version)
    return svc.to_out(session, target)


@router.post(
    "/{target_id}/authorizations",
    response_model=AuthorizationOut,
    status_code=status.HTTP_201_CREATED,
    summary="Record authorization attestation (HA-01)",
)
def record_authorization(
    target_id: str,
    body: AuthorizationCreate,
    session: Session = Depends(get_db),
    principal: Principal = require_role(*TARGET_AUTHORIZE_ROLES),
) -> AuthorizationOut:
    return svc.create_authorization(session, principal, target_id, body, correlation_id_var.get())


@router.delete(
    "/{target_id}/authorizations/{authorization_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke an authorization attestation",
)
def revoke_authorization(
    target_id: str,
    authorization_id: str,
    session: Session = Depends(get_db),
    principal: Principal = require_role(*TARGET_AUTHORIZE_ROLES),
) -> Response:
    svc.revoke_authorization(
        session, principal, target_id, authorization_id, correlation_id_var.get()
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
