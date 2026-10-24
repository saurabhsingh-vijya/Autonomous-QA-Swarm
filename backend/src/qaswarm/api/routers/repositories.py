from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from qaswarm.api.auth import PROJECT_WRITE_ROLES, Principal, get_principal, require_role
from qaswarm.api.deps import get_db
from qaswarm.api.etag import etag_for
from qaswarm.api.pagination import clamp_limit, decode_cursor
from qaswarm.api.schemas import Paginated, RepositoryCreate, RepositoryOut
from qaswarm.api.services import repositories as svc
from qaswarm.config import Settings, get_settings
from qaswarm.telemetry.logging import correlation_id_var

router = APIRouter(prefix="/repositories", tags=["repositories"])


@router.get("", response_model=Paginated[RepositoryOut])
def list_repositories(
    project_id: str | None = None,
    limit: int | None = Query(default=None, ge=1, le=200),
    cursor: str | None = None,
    session: Session = Depends(get_db, scope="function"),
    principal: Principal = Depends(get_principal),
) -> Paginated[RepositoryOut]:
    lim = clamp_limit(limit)
    items, next_cursor = svc.list_repositories(
        session, principal, project_id=project_id, limit=lim, after=decode_cursor(cursor)
    )
    return Paginated(items=items, next_cursor=next_cursor, limit=lim)


@router.post(
    "",
    response_model=RepositoryOut,
    status_code=status.HTTP_201_CREATED,
    responses={422: {"description": "repository_url_rejected (problem+json)"}},
)
def create_repository(
    body: RepositoryCreate,
    response: Response,
    session: Session = Depends(get_db, scope="function"),
    principal: Principal = require_role(*PROJECT_WRITE_ROLES),
    settings: Settings = Depends(get_settings),
) -> RepositoryOut:
    out = svc.create_repository(session, principal, body, settings, correlation_id_var.get())
    response.headers["Location"] = f"/api/v1/repositories/{out.id}"
    response.headers["ETag"] = etag_for(out.id, out.version)
    return out


@router.get("/{repository_id}", response_model=RepositoryOut)
def get_repository(
    repository_id: str,
    response: Response,
    session: Session = Depends(get_db, scope="function"),
    principal: Principal = Depends(get_principal),
) -> RepositoryOut:
    out = RepositoryOut.model_validate(svc.get_repository_row(session, principal, repository_id))
    response.headers["ETag"] = etag_for(out.id, out.version)
    return out
