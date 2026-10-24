"""Seed one sample organization and project. Idempotent. Run: ``python -m qaswarm.db.seed``.

Sample data is visibly labelled "(sample org)" and ``is_sample = true``; no repository code is
executed by anything in this slice.
"""

from __future__ import annotations

import logging
import sys

from sqlalchemy import select

from qaswarm.audit.chain import append_event
from qaswarm.db.models import Organization, Project
from qaswarm.db.session import session_scope
from qaswarm.domain.ids import new_id
from qaswarm.telemetry.logging import configure_logging

SAMPLE_ORG_SLUG = "northwind-fintech-sample"
SAMPLE_ORG_NAME = "Northwind Fintech (sample org)"
SAMPLE_PROJECT_NAME = "Payments Platform"

log = logging.getLogger("qaswarm.seed")


def seed() -> tuple[str, str]:
    with session_scope() as session:
        org = session.execute(
            select(Organization).where(Organization.slug == SAMPLE_ORG_SLUG)
        ).scalar_one_or_none()
        if org is None:
            org = Organization(
                id=new_id("organization"),
                name=SAMPLE_ORG_NAME,
                slug=SAMPLE_ORG_SLUG,
                is_sample=True,
            )
            session.add(org)
            session.flush()
            append_event(
                session,
                org_id=org.id,
                actor_type="service",
                actor_id="seed",
                action="organization.created",
                subject_type="organization",
                subject_id=org.id,
                details={"name": org.name, "sample": True},
            )
            log.info("created sample organization", extra={"org_id": org.id})
        project = session.execute(
            select(Project).where(Project.org_id == org.id, Project.name == SAMPLE_PROJECT_NAME)
        ).scalar_one_or_none()
        if project is None:
            project = Project(
                id=new_id("project"),
                org_id=org.id,
                name=SAMPLE_PROJECT_NAME,
                description="Sample data — no repository code executed.",
                is_sample=True,
            )
            session.add(project)
            session.flush()
            append_event(
                session,
                org_id=org.id,
                actor_type="service",
                actor_id="seed",
                action="project.created",
                subject_type="project",
                subject_id=project.id,
                details={"name": project.name, "sample": True},
            )
            log.info("created sample project", extra={"org_id": org.id})
        return org.id, project.id


if __name__ == "__main__":
    configure_logging()
    org_id, project_id = seed()
    sys.stdout.write(f"seeded org={org_id} project={project_id}\n")
