"""Request-scoped dependencies."""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Depends
from sqlalchemy.orm import Session

from qaswarm.config import Settings, get_settings
from qaswarm.db.session import session_factory
from qaswarm.evidence import EvidenceStore


def get_db() -> Iterator[Session]:
    """Request session. Always declare it as ``Depends(get_db, scope="function")``.

    FastAPI >= 0.118 runs the exit code of ``yield`` dependencies *after* the response has been
    sent unless ``scope="function"`` is given. The commit below must happen before the client
    sees the response, otherwise a follow-up request can miss the row it just created
    (observed in phase 6 as 404s right after a 201).
    """
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
