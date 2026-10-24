"""Finding triage lifecycle (FR-037, HA-07, HA-08).

Transitions come from the finding-status table in the data model. Every successful action bumps
the finding version, appends to ``status_history`` and writes a hash-chained audit event. Roles:
false positive needs a QA Lead for functional findings or a Security Reviewer for security
findings; accepting risk needs a QA Lead and an expiry (HA-08; security findings would need a
second approval and are refused here because no security finding can exist yet); duplicate and
reopen need a QA Lead or QA Engineer.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from qaswarm.audit.chain import append_event
from qaswarm.db.models import Approval, Finding
from qaswarm.domain.enums import FindingStatus, Role
from qaswarm.domain.ids import new_id

ACTIONS = ("mark_false_positive", "accept_risk", "mark_duplicate", "reopen", "request_reproduction")

# (action, from-state) -> to-state. Anything missing is an illegal transition (409).
_TRANSITIONS: dict[tuple[str, FindingStatus], FindingStatus] = {}
for _src in (
    FindingStatus.CANDIDATE,
    FindingStatus.TRIAGING,
    FindingStatus.CONFIRMED,
    FindingStatus.REOPENED,
    FindingStatus.FIX_FAILED,
):
    _TRANSITIONS[("mark_false_positive", _src)] = FindingStatus.FALSE_POSITIVE
    _TRANSITIONS[("mark_duplicate", _src)] = FindingStatus.DUPLICATE
    _TRANSITIONS[("accept_risk", _src)] = FindingStatus.ACCEPTED_RISK
for _src in (
    FindingStatus.FALSE_POSITIVE,
    FindingStatus.DUPLICATE,
    FindingStatus.ACCEPTED_RISK,
    FindingStatus.NOT_REPRODUCIBLE,
    FindingStatus.FIX_VERIFIED,
):
    _TRANSITIONS[("reopen", _src)] = FindingStatus.REOPENED


class TriageError(Exception):
    def __init__(self, status: int, code: str, detail: str, **extra: Any) -> None:
        super().__init__(detail)
        self.status, self.code, self.detail, self.extra = status, code, detail, extra


@dataclass(frozen=True)
class Actor:
    user_id: str
    role: Role


def _is_security(finding: Finding) -> bool:
    return finding.category.startswith("security")


def _check_role(action: str, finding: Finding, actor: Actor) -> None:
    if action == "mark_false_positive":
        needed = {Role.SECURITY_REVIEWER} if _is_security(finding) else {Role.QA_LEAD}
        ha = "HA-07"
    elif action == "accept_risk":
        if _is_security(finding):
            raise TriageError(
                501,
                "not_implemented",
                "Accepting risk on a security finding needs two approvals (QA Lead and "
                "Security Reviewer); dual approval is not implemented in this build.",
                planned_slice="2b",
            )
        needed, ha = {Role.QA_LEAD}, "HA-08"
    else:
        needed, ha = {Role.QA_LEAD, Role.QA_ENGINEER}, "triage"
    if actor.role not in needed:
        raise TriageError(
            403,
            "insufficient_role",
            f"Role '{actor.role.value}' may not {action.replace('_', ' ')} this finding ({ha}). "
            f"Allowed: {', '.join(sorted(r.value for r in needed))}.",
            required_roles=sorted(r.value for r in needed),
        )


def apply_triage(
    session: Session,
    finding: Finding,
    *,
    action: str,
    actor: Actor,
    reason: str | None,
    duplicate_of: str | None = None,
    expires_at: datetime | None = None,
    correlation_id: str | None = None,
) -> Finding:
    if action not in ACTIONS:
        raise TriageError(422, "validation_failed", f"Unknown triage action '{action}'.")
    if action == "request_reproduction":
        raise TriageError(
            501,
            "not_implemented",
            "Reproduction runs need a fresh sandbox (FR-035); the execution service arrives in "
            "slice 1c and reproduction in slice 2b.",
            planned_slice="2b",
        )
    _check_role(action, finding, actor)
    if action in ("mark_false_positive", "accept_risk") and not (reason and reason.strip()):
        raise TriageError(
            422, "validation_failed", f"A reason is required to {action.replace('_', ' ')}."
        )
    if action == "accept_risk":
        if expires_at is None:
            raise TriageError(422, "validation_failed", "accept_risk requires expires_at (HA-08).")
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at <= datetime.now(UTC):
            raise TriageError(422, "validation_failed", "expires_at must be in the future.")
    original: Finding | None = None
    if action == "mark_duplicate":
        if not duplicate_of:
            raise TriageError(422, "validation_failed", "mark_duplicate requires duplicate_of.")
        if duplicate_of == finding.id:
            raise TriageError(422, "validation_failed", "A finding cannot duplicate itself.")
        original = session.execute(
            select(Finding).where(Finding.id == duplicate_of, Finding.org_id == finding.org_id)
        ).scalar_one_or_none()
        if original is None:
            raise TriageError(422, "validation_failed", "duplicate_of does not name a finding.")
    current = FindingStatus(finding.status)
    target = _TRANSITIONS.get((action, current))
    if target is None:
        raise TriageError(
            409,
            "invalid_state_transition",
            f"Finding {finding.display_id} is '{current.value}'; '{action}' is not allowed from "
            "that status.",
        )
    now = datetime.now(UTC)
    finding.status = target.value
    if target in (FindingStatus.FALSE_POSITIVE, FindingStatus.DUPLICATE):
        finding.confidence = "rejected"
    elif target == FindingStatus.REOPENED:
        # Confidence is recomputed from the DCS the record already holds.
        finding.confidence = "probable" if finding.dcs >= 50 else "candidate"
    finding.duplicate_of = original.id if original is not None else None
    finding.triage = {
        "action": action,
        "reason": reason,
        "actor_id": actor.user_id,
        "role": actor.role.value,
        "at": now.isoformat(),
        "expires_at": expires_at.isoformat() if expires_at else None,
        "duplicate_of": finding.duplicate_of,
    }
    entries = list((finding.status_history or {}).get("items", []))
    entries.append(
        {
            "from": current.value,
            "to": target.value,
            "action": action,
            "at": now.isoformat(),
            "actor_id": actor.user_id,
            "role": actor.role.value,
            "reason": reason,
        }
    )
    finding.status_history = {"items": entries}
    finding.version += 1
    if action == "accept_risk":
        session.add(
            Approval(
                id=new_id("approval"),
                org_id=finding.org_id,
                ha_id="HA-08",
                subject_type="finding",
                subject_id=finding.id,
                decision="approved",
                approver_id=actor.user_id,
                role_at_decision=actor.role.value,
                reason=reason,
                subject_hash=finding.fingerprint,
                expires_at=expires_at,
            )
        )
    append_event(
        session,
        org_id=finding.org_id,
        actor_type="user",
        actor_id=actor.user_id,
        actor_role=actor.role.value,
        action=f"finding.{action}",
        subject_type="finding",
        subject_id=finding.id,
        job_id=finding.job_id,
        correlation_id=correlation_id,
        details={
            "from": current.value,
            "to": target.value,
            "reason": reason,
            "duplicate_of": finding.duplicate_of,
            "expires_at": expires_at.isoformat() if expires_at else None,
            "fingerprint": finding.fingerprint,
        },
    )
    session.flush()
    return finding
