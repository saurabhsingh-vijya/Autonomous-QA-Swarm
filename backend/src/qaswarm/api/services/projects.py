from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from qaswarm.api.auth import Principal
from qaswarm.api.errors import Problem
from qaswarm.api.pagination import encode_cursor
from qaswarm.api.schemas import ProjectCreate, ProjectOut, ProjectUpdate
from qaswarm.audit.chain import append_event
from qaswarm.db.models import Organization, Project, Repository
from qaswarm.domain.ids import new_id


def _org_name(session: Session, org_id: str) -> str:
    return session.execute(select(Organization.name).where(Organization.id == org_id)).scalar_one()


def _to_out(project: Project, repo_count: int, org_name: str = "") -> ProjectOut:
    out = ProjectOut.model_validate(project)
    out.repository_count = repo_count
    out.org_name = org_name
    return out


def _repo_counts(session: Session, project_ids: list[str]) -> dict[str, int]:
    if not project_ids:
        return {}
    rows = session.execute(
        select(Repository.project_id, func.count())
        .where(Repository.project_id.in_(project_ids), Repository.archived_at.is_(None))
        .group_by(Repository.project_id)
    ).all()
    return {pid: int(n) for pid, n in rows}


def list_projects(
    session: Session, principal: Principal, *, limit: int, after: str | None
) -> tuple[list[ProjectOut], str | None]:
    stmt = (
        select(Project)
        .where(Project.org_id == principal.org_id, Project.archived_at.is_(None))
        .order_by(Project.id.desc())
        .limit(limit + 1)
    )
    if after:
        stmt = stmt.where(Project.id < after)
    rows = list(session.execute(stmt).scalars())
    next_cursor = encode_cursor(rows[limit - 1].id) if len(rows) > limit else None
    rows = rows[:limit]
    counts = _repo_counts(session, [p.id for p in rows])
    org_name = _org_name(session, principal.org_id)
    return [_to_out(p, counts.get(p.id, 0), org_name) for p in rows], next_cursor


def get_project_row(session: Session, principal: Principal, project_id: str) -> Project:
    project = session.execute(
        select(Project).where(
            Project.id == project_id,
            Project.org_id == principal.org_id,
            Project.archived_at.is_(None),
        )
    ).scalar_one_or_none()
    if project is None:
        raise Problem(404, "not_found", "Project not found.")
    return project


def get_project(session: Session, principal: Principal, project_id: str) -> ProjectOut:
    project = get_project_row(session, principal, project_id)
    return _to_out(
        project,
        _repo_counts(session, [project.id]).get(project.id, 0),
        _org_name(session, principal.org_id),
    )


def create_project(
    session: Session, principal: Principal, body: ProjectCreate, correlation_id: str | None
) -> ProjectOut:
    project = Project(
        id=new_id("project"),
        org_id=principal.org_id,
        name=body.name,
        description=body.description,
    )
    session.add(project)
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise Problem(
            409, "project_name_taken", f"A project named '{body.name}' already exists."
        ) from exc
    append_event(
        session,
        org_id=principal.org_id,
        actor_type="user",
        actor_id=principal.user_id,
        actor_role=principal.role.value,
        action="project.created",
        subject_type="project",
        subject_id=project.id,
        correlation_id=correlation_id,
        details={"name": project.name},
    )
    return _to_out(project, 0, _org_name(session, principal.org_id))


def update_project(
    session: Session,
    principal: Principal,
    project_id: str,
    body: ProjectUpdate,
    if_match: int | None,
    correlation_id: str | None,
) -> ProjectOut:
    project = get_project_row(session, principal, project_id)
    if if_match is not None and if_match != project.version:
        raise Problem(412, "etag_mismatch", "The project changed since you loaded it.")
    changes = body.model_dump(exclude_unset=True)
    if not changes:
        raise Problem(422, "validation_failed", "No fields to update.")
    before = {k: getattr(project, k) for k in changes}
    for key, value in changes.items():
        setattr(project, key, value)
    project.version += 1
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise Problem(
            409, "project_name_taken", "A project with that name already exists."
        ) from exc
    append_event(
        session,
        org_id=principal.org_id,
        actor_type="user",
        actor_id=principal.user_id,
        actor_role=principal.role.value,
        action="project.updated",
        subject_type="project",
        subject_id=project.id,
        correlation_id=correlation_id,
        details={"before": before, "after": changes},
    )
    return _to_out(
        project,
        _repo_counts(session, [project.id]).get(project.id, 0),
        _org_name(session, principal.org_id),
    )


def archive_project(
    session: Session, principal: Principal, project_id: str, correlation_id: str | None
) -> None:
    project = get_project_row(session, principal, project_id)
    now = datetime.now(UTC)
    project.archived_at = now
    project.version += 1
    for repo in session.execute(
        select(Repository).where(
            Repository.project_id == project.id, Repository.archived_at.is_(None)
        )
    ).scalars():
        repo.archived_at = now
    append_event(
        session,
        org_id=principal.org_id,
        actor_type="user",
        actor_id=principal.user_id,
        actor_role=principal.role.value,
        action="project.archived",
        subject_type="project",
        subject_id=project.id,
        correlation_id=correlation_id,
        details={"name": project.name},
    )
