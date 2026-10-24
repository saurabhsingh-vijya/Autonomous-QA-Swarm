from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Query, Request, Response, status
from sqlalchemy.orm import Session

from qaswarm.api.auth import PROJECT_WRITE_ROLES, Principal, get_principal, require_role
from qaswarm.api.deps import get_db
from qaswarm.api.etag import etag_for, parse_if_match
from qaswarm.api.pagination import clamp_limit, decode_cursor
from qaswarm.api.schemas import Paginated, ProjectCreate, ProjectOut, ProjectUpdate
from qaswarm.api.services import projects as svc
from qaswarm.telemetry.logging import correlation_id_var

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=Paginated[ProjectOut])
def list_projects(
    limit: int | None = Query(default=None, ge=1, le=200),
    cursor: str | None = None,
    session: Session = Depends(get_db, scope="function"),
    principal: Principal = Depends(get_principal),
) -> Paginated[ProjectOut]:
    lim = clamp_limit(limit)
    items, next_cursor = svc.list_projects(
        session, principal, limit=lim, after=decode_cursor(cursor)
    )
    return Paginated(items=items, next_cursor=next_cursor, limit=lim)


@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
def create_project(
    body: ProjectCreate,
    response: Response,
    session: Session = Depends(get_db, scope="function"),
    principal: Principal = require_role(*PROJECT_WRITE_ROLES),
) -> ProjectOut:
    out = svc.create_project(session, principal, body, correlation_id_var.get())
    response.headers["Location"] = f"/api/v1/projects/{out.id}"
    response.headers["ETag"] = etag_for(out.id, out.version)
    return out


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(
    project_id: str,
    response: Response,
    session: Session = Depends(get_db, scope="function"),
    principal: Principal = Depends(get_principal),
) -> ProjectOut:
    out = svc.get_project(session, principal, project_id)
    response.headers["ETag"] = etag_for(out.id, out.version)
    return out


@router.patch("/{project_id}", response_model=ProjectOut)
def update_project(
    project_id: str,
    body: ProjectUpdate,
    request: Request,
    response: Response,
    if_match: str | None = Header(default=None, alias="If-Match"),
    session: Session = Depends(get_db, scope="function"),
    principal: Principal = require_role(*PROJECT_WRITE_ROLES),
) -> ProjectOut:
    out = svc.update_project(
        session,
        principal,
        project_id,
        body,
        parse_if_match(if_match, project_id),
        correlation_id_var.get(),
    )
    response.headers["ETag"] = etag_for(out.id, out.version)
    return out


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: str,
    session: Session = Depends(get_db, scope="function"),
    principal: Principal = require_role(*PROJECT_WRITE_ROLES),
) -> Response:
    svc.archive_project(session, principal, project_id, correlation_id_var.get())
    return Response(status_code=status.HTTP_204_NO_CONTENT)
