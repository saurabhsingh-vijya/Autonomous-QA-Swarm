"""Workflow queue against PostgreSQL: no double leasing, retry/backoff, reaper, cancellation."""

from __future__ import annotations

import random
import threading
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine, select, update
from sqlalchemy.orm import Session

from qaswarm.config import Settings
from qaswarm.db.models import Job, Organization, Project, Repository, Task, TaskAttempt
from qaswarm.db.session import session_factory
from qaswarm.domain.enums import ErrorClass, JobState, TaskState
from qaswarm.domain.ids import new_id
from qaswarm.workflow.queue import LeaseLost, TaskQueue, TaskSpec

pytestmark = pytest.mark.integration


@pytest.fixture
def job(clean_db: Engine) -> tuple[str, str]:
    with session_factory()() as session:
        org = session.execute(select(Organization)).scalar_one()
        project = session.execute(select(Project).where(Project.org_id == org.id)).scalar_one()
        repo = Repository(
            id=new_id("repository"),
            org_id=org.id,
            project_id=project.id,
            provider="github",
            url="https://github.com/a/b",
            normalized_url="https://github.com/a/b",
            validation_status="pending_validation",
        )
        session.add(repo)
        session.flush()
        job = Job(
            id=new_id("job"),
            org_id=org.id,
            project_id=project.id,
            repository_id=repo.id,
            display_id="QJ-0001",
            ref="main",
            profiles={},
            profile_hash="x" * 64,
            state=JobState.RUNNING.value,
            created_by="test",
        )
        session.add(job)
        session.commit()
        return org.id, job.id


def _spec(org_id: str, job_id: str, n: int = 0, task_type: str = "unit_test") -> TaskSpec:
    return TaskSpec(org_id, job_id, "functional_and_api_testing", task_type, {"shard": n})


def _queue() -> TaskQueue:
    return TaskQueue(
        Settings(dev_auth=True, lease_ttl_seconds=90, backoff_seconds=[30, 120]),
        rng=random.Random(1),
    )


def test_enqueue_is_idempotent(job: tuple[str, str]) -> None:
    org_id, job_id = job
    q = _queue()
    with session_factory()() as s:
        t1 = q.enqueue(s, _spec(org_id, job_id))
        t2 = q.enqueue(s, _spec(org_id, job_id))
        s.commit()
        assert t1.id == t2.id and t1.state == "pending"
        assert s.execute(select(Task).where(Task.job_id == job_id)).scalars().all().__len__() == 1


def test_two_concurrent_leasers_never_get_the_same_task(job: tuple[str, str]) -> None:
    org_id, job_id = job
    q = _queue()
    with session_factory()() as s:
        for n in range(20):
            q.enqueue(s, _spec(org_id, job_id, n))
        s.commit()

    results: dict[str, list[str]] = {}
    barrier = threading.Barrier(4)

    def worker(name: str) -> None:
        got: list[str] = []
        barrier.wait()
        for _ in range(10):
            with session_factory()() as s:
                leases = q.lease(s, name, ["unit_test"], batch_size=1)
                s.commit()
            got.extend(lease.task_id for lease in leases)
        results[name] = got

    threads = [threading.Thread(target=worker, args=(f"w{i}",)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    all_ids = [tid for ids in results.values() for tid in ids]
    assert len(all_ids) == 20 and len(set(all_ids)) == 20
    with session_factory()() as s:
        attempts = s.execute(select(TaskAttempt)).scalars().all()
        assert len(attempts) == 20 and {a.attempt_no for a in attempts} == {1}
        assert all(t.state == "leased" for t in s.execute(select(Task)).scalars())


def test_heartbeat_moves_to_running_and_lost_lease_is_rejected(job: tuple[str, str]) -> None:
    org_id, job_id = job
    q = _queue()
    with session_factory()() as s:
        q.enqueue(s, _spec(org_id, job_id))
        lease = q.lease(s, "w1", ["unit_test"])[0]
        s.commit()
    with session_factory()() as s:
        q.heartbeat(s, lease.task_id, "w1")
        s.commit()
        assert s.get(Task, lease.task_id).state == TaskState.RUNNING.value
        with pytest.raises(LeaseLost):
            q.heartbeat(s, lease.task_id, "impostor")
        with pytest.raises(LeaseLost):
            q.complete(s, lease.task_id, "impostor")
    with session_factory()() as s:
        q.complete(s, lease.task_id, "w1", result_ref="evidence/x")
        s.commit()
        assert s.get(Task, lease.task_id).state == TaskState.SUCCEEDED.value


def _expire_lease(session: Session, task_id: str) -> None:
    past = datetime.now(UTC) - timedelta(seconds=1)
    session.execute(update(Task).where(Task.id == task_id).values(lease_expires_at=past))
    session.execute(
        update(TaskAttempt).where(TaskAttempt.task_id == task_id).values(lease_expires_at=past)
    )


def test_expired_lease_is_reaped_and_retry_scheduled_then_third_failure_ends_failed(
    job: tuple[str, str],
) -> None:
    org_id, job_id = job
    q = _queue()
    with session_factory()() as s:
        q.enqueue(s, _spec(org_id, job_id))
        lease = q.lease(s, "w1", ["unit_test"])[0]
        s.commit()
    tid = lease.task_id

    # Attempt 1: lease expires -> failed_retryable -> retry_scheduled with ~30 s backoff.
    with session_factory()() as s:
        _expire_lease(s, tid)
        assert q.reap_expired_leases(s) == [tid]
        s.commit()
        task = s.get(Task, tid)
        assert task.state == TaskState.RETRY_SCHEDULED.value
        assert task.last_error_code == "E-QUEUE-001" and task.attempt_count == 1
        delay = (task.available_at - datetime.now(UTC)).total_seconds()
        assert 20 <= delay <= 37
        attempt = s.execute(select(TaskAttempt).where(TaskAttempt.task_id == tid)).scalar_one()
        assert attempt.outcome == "lease_expired"
        assert q.lease(s, "w2", ["unit_test"]) == []  # not available until backoff elapses
        s.execute(update(Task).where(Task.id == tid).values(available_at=datetime.now(UTC)))
        s.commit()

    # Attempt 2: transient failure -> retry_scheduled with ~120 s backoff.
    with session_factory()() as s:
        lease2 = q.lease(s, "w2", ["unit_test"])[0]
        assert lease2.attempt_no == 2
        q.fail(s, tid, "w2", retryable=True, error_code="E-EXEC-001")
        s.commit()
        task = s.get(Task, tid)
        assert task.state == TaskState.RETRY_SCHEDULED.value
        delay = (task.available_at - datetime.now(UTC)).total_seconds()
        assert 90 <= delay <= 145
        s.execute(update(Task).where(Task.id == tid).values(available_at=datetime.now(UTC)))
        s.commit()

    # Attempt 3: a third transient failure exhausts the budget -> failed / infrastructure_error.
    with session_factory()() as s:
        lease3 = q.lease(s, "w3", ["unit_test"])[0]
        assert lease3.attempt_no == 3
        q.fail(
            s,
            tid,
            "w3",
            retryable=True,
            error_code="E-EXEC-001",
            error_class=ErrorClass.INFRASTRUCTURE_ERROR,
        )
        s.commit()
        task = s.get(Task, tid)
        assert task.state == TaskState.FAILED.value
        assert task.last_error_class == "infrastructure_error"
        assert (
            len(s.execute(select(TaskAttempt).where(TaskAttempt.task_id == tid)).scalars().all())
            == 3
        )


def test_dependencies_gate_leasing_and_cancel_marks_tasks_cancelled(job: tuple[str, str]) -> None:
    org_id, job_id = job
    q = _queue()
    with session_factory()() as s:
        parent = q.enqueue(s, _spec(org_id, job_id, 1, "build"))
        child = q.enqueue(
            s,
            TaskSpec(
                org_id,
                job_id,
                "functional_and_api_testing",
                "unit_test",
                {"shard": 2},
                depends_on=[parent.id],
            ),
        )
        s.commit()
        assert q.lease(s, "w", ["unit_test"]) == []
        lease = q.lease(s, "w", ["build"])[0]
        q.complete(s, lease.task_id, "w")
        s.commit()
        assert q.lease(s, "w", ["unit_test"])[0].task_id == child.id
        s.commit()
        assert q.cancel_job_tasks(s, job_id, actor="user") == 1
        s.commit()
        assert s.get(Task, child.id).state == TaskState.CANCELLED.value
        assert s.get(Task, parent.id).state == TaskState.SUCCEEDED.value
