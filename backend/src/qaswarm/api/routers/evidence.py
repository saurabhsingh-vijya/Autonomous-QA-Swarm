from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from qaswarm.api.auth import Principal, require_role
from qaswarm.api.deps import get_db, get_evidence_store
from qaswarm.api.schemas import EvidenceContentOut, EvidenceItemOut
from qaswarm.api.services import results as svc
from qaswarm.config import Settings, get_settings
from qaswarm.domain.enums import Role
from qaswarm.evidence import EvidenceStore

router = APIRouter(prefix="/evidence", tags=["evidence"])

# Contract: ``evidence:read`` is held by every role except Viewer and CI Service Account.
EVIDENCE_ROLES = (
    Role.ORG_ADMIN,
    Role.QA_LEAD,
    Role.QA_ENGINEER,
    Role.DEVELOPER,
    Role.SECURITY_REVIEWER,
)


@router.get("/{evidence_id}", response_model=EvidenceItemOut)
def get_evidence(
    evidence_id: str,
    session: Session = Depends(get_db),
    principal: Principal = require_role(*EVIDENCE_ROLES),
) -> EvidenceItemOut:
    return EvidenceItemOut.model_validate(svc.get_evidence(session, principal, evidence_id))


@router.get("/{evidence_id}/content", response_model=EvidenceContentOut)
def get_evidence_content(
    evidence_id: str,
    session: Session = Depends(get_db),
    principal: Principal = require_role(*EVIDENCE_ROLES),
    store: EvidenceStore = Depends(get_evidence_store),
    settings: Settings = Depends(get_settings),
) -> EvidenceContentOut:
    """Inline text content (up to ``AQS_EVIDENCE_INLINE_MAX_BYTES``); use ``/download`` for bytes."""
    _, _, out = svc.evidence_content(
        session, store, principal, evidence_id, settings.evidence_inline_max_bytes
    )
    return out


@router.get("/{evidence_id}/download", response_class=Response)
def download_evidence(
    evidence_id: str,
    session: Session = Depends(get_db),
    principal: Principal = require_role(*EVIDENCE_ROLES),
    store: EvidenceStore = Depends(get_evidence_store),
    settings: Settings = Depends(get_settings),
) -> Response:
    item, data, _ = svc.evidence_content(
        session, store, principal, evidence_id, settings.evidence_inline_max_bytes
    )
    return Response(
        content=data,
        media_type=item.media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{item.id}"',
            "X-Content-SHA256": item.sha256,
            "Cache-Control": "private, no-store",
        },
    )
