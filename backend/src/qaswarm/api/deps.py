"""Request-scoped dependencies."""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Depends
from sqlalchemy.orm import Session

from qaswarm.config import Settings, get_settings
from qaswarm.db.session import session_factory
from qaswarm.evidence import EvidenceStore


def get_db() -> Iterator[Session]:
    session = session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_evidence_store(settings: Settings = Depends(get_settings)) -> EvidenceStore:
    return EvidenceStore(settings.evidence_dir)
