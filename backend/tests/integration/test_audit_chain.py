from __future__ import annotations

import itertools

import pytest
from sqlalchemy import Engine, select, text

from qaswarm.audit.chain import GENESIS_HASH, append_event, verify_chain
from qaswarm.db.models import AuditEvent, Organization
from qaswarm.db.session import session_factory

pytestmark = pytest.mark.integration


def _org(session) -> str:  # type: ignore[no-untyped-def]
    return session.execute(select(Organization.id)).scalar_one()


def test_chain_links_from_genesis_and_verifies(clean_db: Engine) -> None:
    with session_factory()() as s:
        org_id = _org(s)
        for i in range(5):
            append_event(
                s,
                org_id=org_id,
                actor_type="user",
                actor_id="u",
                action=f"test.{i}",
                subject_type="job",
                subject_id=f"job_{i}",
                details={"i": i},
            )
        s.commit()
        events = (
            s.execute(
                select(AuditEvent).where(AuditEvent.org_id == org_id).order_by(AuditEvent.seq)
            )
            .scalars()
            .all()
        )
        assert events[0].prev_hash == GENESIS_HASH
        for prev, cur in itertools.pairwise(events):
            assert cur.prev_hash == prev.hash
        assert verify_chain(s, org_id) is None
        assert verify_chain(s, org_id, from_seq=events[2].seq) is None


def test_editing_one_stored_row_is_detected(clean_db: Engine) -> None:
    with session_factory()() as s:
        org_id = _org(s)
        ids = [
            append_event(
                s,
                org_id=org_id,
                actor_type="user",
                actor_id="u",
                action="a",
                subject_type="job",
                subject_id="job_x",
                details={"n": i},
            ).seq
            for i in range(4)
        ]
        s.commit()
        s.execute(
            text("UPDATE audit_events SET details = '{\"n\": 99}'::jsonb WHERE seq = :seq"),
            {"seq": ids[2]},
        )
        s.commit()
        s.expire_all()
        broken = verify_chain(s, org_id)
        assert broken is not None and broken.seq == ids[2]
        assert "recomputed" in broken.reason


def test_deleting_a_row_breaks_the_chain(clean_db: Engine) -> None:
    with session_factory()() as s:
        org_id = _org(s)
        seqs = [
            append_event(
                s,
                org_id=org_id,
                actor_type="user",
                actor_id="u",
                action="a",
                subject_type="job",
                subject_id="job_x",
            ).seq
            for _ in range(3)
        ]
        s.commit()
        s.execute(text("DELETE FROM audit_events WHERE seq = :seq"), {"seq": seqs[1]})
        s.commit()
        broken = verify_chain(s, org_id)
        assert broken is not None and broken.seq == seqs[2] and "prev_hash" in broken.reason
