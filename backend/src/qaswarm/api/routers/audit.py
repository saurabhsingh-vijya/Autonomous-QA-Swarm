from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from qaswarm.api.auth import Principal, require_role
from qaswarm.api.deps import get_db
from qaswarm.api.pagination import clamp_limit
from qaswarm.api.schemas import AuditEventOut, Paginated
from qaswarm.api.services import results as svc
from qaswarm.domain.enums import Role

router = APIRouter(prefix="/audit-events", tags=["audit"])

AUDIT_ROLES = (Role.ORG_ADMIN, Role.QA_LEAD, Role.SECURITY_REVIEWER)


@router.get("", response_model=Paginated[AuditEventOut])
def list_audit_events(
    job_id: str | None = None,
    actor_id: str | None = None,
    action: str | None = None,
    limit: int | None = Query(default=None, ge=1, le=200),
    cursor: int | None = Query(default=None, description="Return events with seq below this"),
    session: Session = Depends(get_db),
    principal: Principal = require_role(*AUDIT_ROLES),
) -> Paginated[AuditEventOut]:
    lim = clamp_limit(limit)
    items, next_seq = svc.list_audit_events(
        session, principal, job_id=job_id, actor_id=actor_id, action=action, limit=lim, after=cursor
    )
    return Paginated(items=items, next_cursor=str(next_seq) if next_seq else None, limit=lim)
