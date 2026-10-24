"""Hash-chained audit log.

``hash = SHA-256(prev_hash + canonical JSON of the event body)``. The chain is per organisation
and the first event links to ``GENESIS_HASH`` (64 zeros). ``verify_chain`` recomputes every hash
and reports the first broken link.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from qaswarm.db.models import AuditEvent
from qaswarm.domain.ids import new_id

GENESIS_HASH = "0" * 64


def canonical_json(data: dict[str, Any]) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def event_body(event: AuditEvent) -> dict[str, Any]:
    return {
        "id": event.id,
        "org_id": event.org_id,
        "occurred_at": event.occurred_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "actor_type": event.actor_type,
        "actor_id": event.actor_id,
        "actor_role": event.actor_role,
        "action": event.action,
        "subject_type": event.subject_type,
        "subject_id": event.subject_id,
        "job_id": event.job_id,
        "correlation_id": event.correlation_id,
        "details": event.details,
    }


def compute_hash(prev_hash: str, body: dict[str, Any]) -> str:
    return hashlib.sha256((prev_hash + canonical_json(body)).encode("utf-8")).hexdigest()


def _chain_head(session: Session, org_id: str) -> str:
    stmt = (
        select(AuditEvent.hash)
        .where(AuditEvent.org_id == org_id)
        .order_by(AuditEvent.seq.desc())
        .limit(1)
        .with_for_update()
    )
    head = session.execute(stmt).scalar_one_or_none()
    return head or GENESIS_HASH


def append_event(
    session: Session,
    *,
    org_id: str,
    actor_type: str,
    actor_id: str,
    action: str,
    subject_type: str,
    subject_id: str,
    actor_role: str | None = None,
    job_id: str | None = None,
    correlation_id: str | None = None,
    details: dict[str, Any] | None = None,
    occurred_at: datetime | None = None,
) -> AuditEvent:
    """Append one event to the organisation's chain inside the caller's transaction."""
    session.execute(select(1))  # ensure a transaction is open before locking the chain head
    prev_hash = _chain_head(session, org_id)
    event = AuditEvent(
        id=new_id("audit_event"),
        org_id=org_id,
        occurred_at=occurred_at or datetime.now(UTC),
        actor_type=actor_type,
        actor_id=actor_id,
        actor_role=actor_role,
        action=action,
        subject_type=subject_type,
        subject_id=subject_id,
        job_id=job_id,
        correlation_id=correlation_id,
        details=details or {},
        prev_hash=prev_hash,
        hash="",
    )
    event.hash = compute_hash(prev_hash, event_body(event))
    session.add(event)
    session.flush()
    return event


@dataclass(frozen=True)
class ChainBreak:
    seq: int
    event_id: str
    reason: str


def verify_chain(
    session: Session, org_id: str, *, from_seq: int | None = None, to_seq: int | None = None
) -> ChainBreak | None:
    """Return the first broken link in the range, or ``None`` when the chain verifies.

    When ``from_seq`` is given, the previous event's hash is used as the starting link.
    """
    stmt = select(AuditEvent).where(AuditEvent.org_id == org_id).order_by(AuditEvent.seq)
    if from_seq is not None:
        stmt = stmt.where(AuditEvent.seq >= from_seq)
    if to_seq is not None:
        stmt = stmt.where(AuditEvent.seq <= to_seq)
    events = list(session.execute(stmt).scalars())
    if not events:
        return None

    expected_prev = GENESIS_HASH
    if from_seq is not None:
        prior = session.execute(
            select(AuditEvent.hash)
            .where(AuditEvent.org_id == org_id, AuditEvent.seq < events[0].seq)
            .order_by(AuditEvent.seq.desc())
            .limit(1)
        ).scalar_one_or_none()
        expected_prev = prior or GENESIS_HASH

    for ev in events:
        if ev.prev_hash != expected_prev:
            return ChainBreak(ev.seq, ev.id, "prev_hash does not match previous event hash")
        recomputed = compute_hash(ev.prev_hash, event_body(ev))
        if recomputed != ev.hash:
            return ChainBreak(ev.seq, ev.id, "stored hash does not match recomputed hash")
        expected_prev = ev.hash
    return None
