"""AG-01 Orchestrator: admits jobs, builds and persists the plan, enqueues tasks, dispatches
leased tasks to agents, persists their outputs and advances the job state machine.

Everything persists through the existing queue so every task carries attempts, timestamps,
outputs, errors, outbox events and audit events.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from qaswarm.agents.api_testing import HttpChecker
from qaswarm.agents.base import (
    AgentContext,
    AgentFailure,
    AgentResult,
    AgentTaskInput,
    validate_output,
)
from qaswarm.agents.llm import LLMAdapter, build_adapter
from qaswarm.agents.registry import get_agent
from qaswarm.audit.chain import append_event
from qaswarm.config import Settings, get_settings
from qaswarm.db.models import (
    AgentOutput,
    CheckRun,
    EvidenceItem,
    Finding,
    Job,
    JobPlan,
    Organization,
    Report,
    Task,
    TestExecution,
)
from qaswarm.defects.intelligence import carry_over_status, cross_run_history, risk_priority
from qaswarm.domain.enums import TERMINAL_TASK_STATES, ErrorClass, JobState, TaskState
from qaswarm.domain.ids import display_id, new_id
from qaswarm.domain.state_machines import JobEvent, JobStateMachine
from qaswarm.evidence import EvidenceStore
from qaswarm.planning.combined import build_job_plan
from qaswarm.planning.planner import PlanNode
from qaswarm.policy.local import evaluate_api_check
from qaswarm.reporting.basic import build_report
from qaswarm.workflow.jobs import transition_job
from qaswarm.workflow.queue import Lease, LeaseLost, TaskQueue, TaskSpec

log = logging.getLogger("qaswarm.orchestrator")


def _canonical(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)


@dataclass
class Orchestrator:
    settings: Settings
    queue: TaskQueue
    llm: LLMAdapter | None = None
    http: HttpChecker | None = None
    store: EvidenceStore | None = None

    @classmethod
    def from_settings(cls, settings: Settings | None = None, **overrides: Any) -> Orchestrator:
        s = settings or get_settings()
        store = overrides.pop("store", None) or EvidenceStore(s.evidence_dir)
        llm = overrides.pop("llm", None) or build_adapter(
            s.llm_provider,
            base_url=s.llm_base_url,
            model=s.llm_model,
            timeout_seconds=s.llm_timeout_seconds,
            per_minute=s.llm_rate_limit_per_minute,
        )
        http = overrides.pop("http", None) or HttpChecker(
            timeout_seconds=s.api_check_timeout_seconds
        )
        return cls(settings=s, queue=TaskQueue(s), llm=llm, http=http, store=store)

    # ------------------------------------------------------------------ planning
    def plan_job(
        self,
        session: Session,
        job: Job,
        *,
        repository_url: str,
        provider: str,
        correlation_id: str | None = None,
    ) -> bool:
        """``planning`` → plan persisted and tasks enqueued → ``running`` / ``awaiting_approval``.

        Called by the scheduler once Intake & Pinning has finished (with or without a commit; a
        job that could not be pinned but carries inputs runs its agent tasks only). Returns
        False when the plan was rejected (policy denied or invalid).
        """
        inputs = job.inputs or {}
        denied = [
            d.reason
            for c in inputs.get("api_checks", [])
            if not (
                d := evaluate_api_check(
                    str(c.get("method", "GET")),
                    str(c.get("url", "")),
                    self.settings.api_allowed_hosts,
                )
            ).allowed
            and d.rule in ("metadata", "credentials", "scheme")
        ]
        if denied:
            job.held_reason = None
            transition_job(
                session,
                job,
                JobEvent.POLICY_DENIED,
                actor_type="service",
                actor_id="policy",
                correlation_id=correlation_id,
                details={"reasons": denied},
            )
            return False
        result = build_job_plan(
            job,
            repository_url=repository_url,
            provider=provider,
            execution_enabled=bool(self.settings.exec_token),
        )
        if result.problems:
            transition_job(
                session,
                job,
                JobEvent.PLAN_INVALID,
                actor_type="service",
                actor_id="orchestrator",
                correlation_id=correlation_id,
                details={"error_code": "E-PLAN-001", "problems": result.problems},
            )
            return False
        nodes = result.nodes
        phash = result.plan_hash
        plan = JobPlan(
            id=new_id("job_plan"),
            org_id=job.org_id,
            job_id=job.id,
            revision=1,
            dag={"nodes": [n.to_dict() for n in nodes]},
            plan_hash=phash,
            approval_required=job.require_plan_approval,
        )
        session.add(plan)
        existing = list((job.warnings or {}).get("items", []))
        job.warnings = {"items": existing + [w for w in result.warnings if w not in existing]}
        append_event(
            session,
            org_id=job.org_id,
            actor_type="service",
            actor_id="orchestrator",
            action="job.planned",
            subject_type="job",
            subject_id=job.id,
            job_id=job.id,
            correlation_id=correlation_id,
            details={
                "planner": "deterministic",
                "plan_id": plan.id,
                "plan_hash": phash,
                "engines": result.engines,
                "tasks": len(nodes),
                "agents": sorted({n.agent_id for n in nodes if n.agent_id != "EXEC"}),
                "warnings": result.warnings,
            },
        )
        if job.require_plan_approval:
            transition_job(
                session,
                job,
                JobEvent.PLAN_VALID_APPROVAL_REQUIRED,
                actor_type="service",
                actor_id="orchestrator",
                correlation_id=correlation_id,
                details={"approval": "HA-05"},
            )
            job.held_reason = "Waiting for plan approval (HA-05) by a QA Lead."
            return True
        self._start(session, job, nodes, correlation_id)
        return True

    def approve_plan(
        self, session: Session, job: Job, *, approved: bool, correlation_id: str | None
    ) -> None:
        plan = (
            session.execute(
                select(JobPlan).where(JobPlan.job_id == job.id).order_by(JobPlan.revision.desc())
            )
            .scalars()
            .first()
        )
        if plan is None:
            raise ValueError("no plan")
        if not approved:
            transition_job(
                session,
                job,
                JobEvent.APPROVAL_REJECTED,
                actor_type="user",
                actor_id="approver",
                correlation_id=correlation_id,
            )
            job.held_reason = None
            transition_job(
                session,
                job,
                JobEvent.CLEANUP_CONFIRMED_USER,
                actor_type="service",
                actor_id="orchestrator",
                correlation_id=correlation_id,
                details={"reason": "plan rejected"},
            )
            return
        plan.approved_at = datetime.now(UTC)
        job.held_reason = None
        nodes = [
            PlanNode(
                key=str(n["key"]),
                agent_id=str(n["agent_id"]),
                task_type=str(n["task_type"]),
                stage=str(n["stage"]),
                depends_on=tuple(n.get("depends_on", [])),
                soft_depends_on=tuple(n.get("soft_depends_on", [])),
                critical=bool(n.get("critical", False)),
                inputs=dict(n.get("inputs", {})),
            )
            for n in plan.dag["nodes"]
        ]
        transition_job(
            session,
            job,
            JobEvent.APPROVALS_RECORDED,
            actor_type="user",
            actor_id="approver",
            correlation_id=correlation_id,
        )
        self._enqueue(session, job, nodes)

    def _start(
        self, session: Session, job: Job, nodes: list[PlanNode], correlation_id: str | None
    ) -> None:
        transition_job(
            session,
            job,
            JobEvent.PLAN_VALID_NO_APPROVAL,
            actor_type="service",
            actor_id="orchestrator",
            correlation_id=correlation_id,
        )
        job.started_at = datetime.now(UTC)
        self._enqueue(session, job, nodes)

    def _enqueue(self, session: Session, job: Job, nodes: list[PlanNode]) -> None:
        ids: dict[str, str] = {}
        for n in nodes:  # nodes are in dependency order
            inputs = {k: v for k, v in n.inputs.items() if k != "priority"}
            spec = TaskSpec(
                org_id=job.org_id,
                job_id=job.id,
                stage=n.stage,
                task_type=n.task_type,
                inputs={**inputs, "plan_key": n.key, "critical": n.critical},
                agent_id=None if n.agent_id in ("EXEC", None) else n.agent_id,
                depends_on=[ids[d] for d in n.depends_on],
                soft_depends_on=[ids[d] for d in n.soft_depends_on],
                priority=int(n.inputs.get("priority", 0)),
            )
            task = self.queue.enqueue(session, spec)
            ids[n.key] = task.id
        job.started_at = job.started_at or datetime.now(UTC)
        job.current_stage = next(
            (n.stage for n in nodes if n.stage not in ("planning",)), "functional_and_api_testing"
        )

    # ------------------------------------------------------------------ dispatch
    TASK_TYPES = (
        "requirements.analyze",
        "functional.execute",
        "api.check",
        "evidence.correlate",
        "report.build",
    )

    def run_once(self, session: Session, *, worker_id: str | None = None) -> int:
        """Lease up to one task and execute it. Returns the number of tasks processed."""
        wid = worker_id or self.settings.runner_worker_id
        leases = self.queue.lease(session, wid, list(self.TASK_TYPES), batch_size=1)
        session.commit()
        for lease in leases:
            self._execute(session, lease, wid)
        return len(leases)

    def _execute(self, session: Session, lease: Lease, worker_id: str) -> None:
        task = session.get(Task, lease.task_id)
        assert task is not None
        job = session.get(Job, task.job_id)
        assert job is not None
        try:
            self.queue.heartbeat(session, task.id, worker_id)
        except LeaseLost:
            return
        session.commit()
        if job.state == JobState.CANCELLING.value:
            return  # cancel_job_tasks will mark it; nothing to execute
        agent = get_agent(task.task_type)
        started = time.monotonic()
        if agent is None:
            self.queue.fail(
                session,
                task.id,
                worker_id,
                retryable=False,
                error_code="E-POLICY-002",
                error_class=ErrorClass.CONTRACT_ERROR,
            )
            session.commit()
            self.reconcile(session, job)
            return
        upstream = self._upstream(session, job, task)
        agent_input = AgentTaskInput(
            job_id=job.id,
            org_id=job.org_id,
            task_id=task.id,
            task_type=task.task_type,
            stage=task.stage,
            attempt_no=task.attempt_count,
            inputs={k: v for k, v in task.inputs.items() if k not in ("plan_key", "critical")},
            upstream=upstream,
            config={
                "api_allowed_hosts": self.settings.api_allowed_hosts,
                "llm_provider": self.settings.llm_provider,
            },
        )
        ctx = AgentContext(
            llm=self.llm if (self.llm and getattr(self.llm, "is_llm", False)) else None,
            http=self.http,
            cancelled=lambda: self._is_cancelling(session, job.id),
        )
        try:
            result = validate_output(agent, agent.run(agent_input, ctx))
        except AgentFailure as exc:
            log.warning("agent failed", extra={"job_id": job.id, "task_id": task.id})
            self._record_output_failure(
                session,
                job,
                task,
                agent,
                agent_input,
                str(exc),
                int((time.monotonic() - started) * 1000),
            )
            self.queue.fail(
                session,
                task.id,
                worker_id,
                retryable=exc.retryable,
                error_code=exc.error_code,
                error_class=exc.error_class,
            )
            session.commit()
            self.reconcile(session, job)
            return
        except Exception as exc:
            log.exception("agent crashed", extra={"job_id": job.id, "task_id": task.id})
            self._record_output_failure(
                session,
                job,
                task,
                agent,
                agent_input,
                exc.__class__.__name__,
                int((time.monotonic() - started) * 1000),
            )
            self.queue.fail(
                session,
                task.id,
                worker_id,
                retryable=True,
                error_code="E-EXEC-004",
                error_class=ErrorClass.INFRASTRUCTURE_ERROR,
            )
            session.commit()
            self.reconcile(session, job)
            return
        duration = int((time.monotonic() - started) * 1000)
        self._persist(session, job, task, agent, agent_input, result, duration)
        try:
            self.queue.complete(
                session, task.id, worker_id, result_ref=f"agent_output:{task.task_type}"
            )
        except LeaseLost:
            session.rollback()
            return
        session.commit()
        self.reconcile(session, job)

    def _is_cancelling(self, session: Session, job_id: str) -> bool:
        state = session.execute(select(Job.state).where(Job.id == job_id)).scalar_one_or_none()
        return state in (JobState.CANCELLING.value, JobState.CANCELLED.value)

    # ------------------------------------------------------------------ persistence
    def _record_output_failure(
        self,
        session: Session,
        job: Job,
        task: Task,
        agent: Any,
        agent_input: AgentTaskInput,
        message: str,
        duration_ms: int,
    ) -> None:
        session.add(
            AgentOutput(
                id=new_id("agent_output"),
                org_id=job.org_id,
                job_id=job.id,
                task_id=task.id,
                attempt_no=task.attempt_count,
                agent_id=agent.agent_id,
                agent_kind=agent.kind.value,
                adapter="n/a",
                schema_name="error",
                schema_version="1.0",
                validation_status="failed",
                input_sha256=agent_input.sha256(),
                output_sha256=hashlib.sha256(message.encode()).hexdigest(),
                payload={"error": message[:2000]},
                duration_ms=duration_ms,
            )
        )

    def _persist(
        self,
        session: Session,
        job: Job,
        task: Task,
        agent: Any,
        agent_input: AgentTaskInput,
        result: AgentResult,
        duration_ms: int,
    ) -> None:
        evidence_ids: list[str] = []
        for ev in result.evidence:
            evidence_ids.append(self._store_evidence(session, job, task, ev))
        session.add(
            AgentOutput(
                id=new_id("agent_output"),
                org_id=job.org_id,
                job_id=job.id,
                task_id=task.id,
                attempt_no=task.attempt_count,
                agent_id=agent.agent_id,
                agent_kind=result.agent_kind.value,
                adapter=result.adapter,
                model_ref=result.model_ref,
                schema_name=result.schema_name,
                schema_version=result.schema_version,
                validation_status="valid",
                input_sha256=agent_input.sha256(),
                output_sha256=result.sha256(),
                payload=result.payload,
                tokens_in=result.tokens_in,
                tokens_out=result.tokens_out,
                duration_ms=duration_ms,
            )
        )
        if result.warnings:
            w = dict(job.warnings or {})
            items = list(w.get("items", []))
            for msg in result.warnings:
                if msg not in items:
                    items.append(msg)
            job.warnings = {**w, "items": items}
        if task.task_type == "api.check":
            for r in result.payload["results"]:
                idx = r.get("evidence_index")
                session.add(
                    TestExecution(
                        id=new_id("test_execution"),
                        org_id=job.org_id,
                        job_id=job.id,
                        task_id=task.id,
                        scenario_id=r["scenario_id"],
                        node_id=str(r.get("scenario_id") or r["name"])[:500],
                        test_type="api",
                        name=r["name"],
                        status=r["status"],
                        duration_ms=r["duration_ms"],
                        message=r.get("message"),
                        tool=result.payload["tool"],
                        tool_version=result.payload["tool_version"],
                        evidence_id=evidence_ids[idx]
                        if idx is not None and idx < len(evidence_ids)
                        else None,
                        meta={
                            "method": r["method"],
                            "url": r["url"],
                            "expected_status": r["expected_status"],
                            "observed_status": r.get("observed_status"),
                        },
                    )
                )
        elif task.task_type == "functional.execute":
            for r in result.payload["executions"]:
                session.add(
                    TestExecution(
                        id=new_id("test_execution"),
                        org_id=job.org_id,
                        job_id=job.id,
                        task_id=task.id,
                        scenario_id=r["scenario_id"],
                        node_id=str(r.get("scenario_id") or r["name"])[:500],
                        test_type="functional",
                        name=r["name"],
                        status=r["status"],
                        message=r["message"],
                        tool="none",
                        tool_version="0",
                    )
                )
        elif task.task_type == "evidence.correlate":
            org = session.execute(
                select(Organization).where(Organization.id == job.org_id).with_for_update()
            ).scalar_one()
            seq = int((org.settings or {}).get("finding_sequence", 0))
            for f in result.payload["findings"]:
                seq += 1
                history = cross_run_history(session, job, f["fingerprint"])
                status, status_note = carry_over_status(history)
                confidence = "rejected" if status == "false_positive" else f["confidence"]
                priority, breakdown = risk_priority(f["severity"], confidence, "external")
                facts = list(f["facts"])
                if history["recurring"]:
                    seen = history["prior_occurrences"][0]
                    facts.append(
                        f"Seen before: {history['times_seen_before']} earlier job(s) on this "
                        f"repository, most recently {seen['display_id']} in job "
                        f"{seen['job_display_id']} ({seen['status']})."
                    )
                inferred = list(f["inferred"])
                if status_note:
                    inferred.append(status_note)
                now_iso = datetime.now(UTC).isoformat()
                session.add(
                    Finding(
                        id=new_id("finding"),
                        org_id=job.org_id,
                        job_id=job.id,
                        display_id=display_id("FND", seq),
                        category=f["category"],
                        title=f["title"],
                        severity=f["severity"],
                        status=status,
                        confidence=confidence,
                        dcs=f["dcs"],
                        dcs_breakdown=f["dcs_breakdown"],
                        fingerprint=f["fingerprint"],
                        location=f["location"],
                        occurrences=f["occurrences"],
                        facts={"items": facts},
                        inferred={"items": inferred},
                        evidence_ids={"items": f["evidence_refs"]},
                        test_execution_ids={"items": f["execution_refs"]},
                        description=f.get("description", ""),
                        affected_tests={"items": f.get("affected_tests", [])},
                        reproducibility=f.get("reproducibility", {}),
                        root_causes={"items": f.get("root_causes", [])},
                        risk_priority=priority,
                        priority_breakdown=breakdown,
                        history=history,
                        status_history={
                            "items": [
                                {
                                    "from": None,
                                    "to": status,
                                    "action": "created",
                                    "at": now_iso,
                                    "actor_id": "AG-08",
                                    "role": "agent",
                                    "reason": status_note,
                                }
                            ]
                        },
                    )
                )
            org.settings = {**(org.settings or {}), "finding_sequence": seq}
        elif task.task_type == "report.build":
            content = {
                **result.payload,
                "job": {
                    "id": job.id,
                    "display_id": job.display_id,
                    "ref": job.ref,
                    "profiles": job.profiles,
                    "inputs_sha256": hashlib.sha256(_canonical(job.inputs).encode()).hexdigest(),
                },
                "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            }
            session.add(
                Report(
                    id=new_id("report"),
                    org_id=job.org_id,
                    job_id=job.id,
                    kind="main",
                    verdict=result.payload["verdict"],
                    generator=f"{agent.agent_id} deterministic 1.0",
                    digest=hashlib.sha256(_canonical(content).encode()).hexdigest(),
                    content=content,
                )
            )
        session.flush()

    def _store_evidence(self, session: Session, job: Job, task: Task, ev: dict[str, Any]) -> str:
        body = _canonical(ev["content"])
        data = body.encode()
        sha = hashlib.sha256(data).hexdigest()
        existing = session.execute(
            select(EvidenceItem.id).where(
                EvidenceItem.org_id == job.org_id,
                EvidenceItem.job_id == job.id,
                EvidenceItem.sha256 == sha,
            )
        ).scalar_one_or_none()
        if existing:
            return existing
        storage_key: str | None = None
        if self.store is not None:
            _, storage_key = self.store.put(job.org_id, data)
        item = EvidenceItem(
            id=new_id("evidence_item"),
            org_id=job.org_id,
            job_id=job.id,
            task_id=task.id,
            kind=ev["kind"],
            label=str(ev.get("label") or ev["kind"])[:200],
            sha256=sha,
            storage_key=storage_key,
            size_bytes=len(data),
            media_type="application/json",
            producer=ev["producer"],
            content=ev["content"],
            deterministic=True,
        )
        session.add(item)
        session.flush()
        return item.id

    # ------------------------------------------------------------------ upstream data
    def _upstream(self, session: Session, job: Job, task: Task) -> dict[str, Any]:
        outputs = (
            session.execute(
                select(AgentOutput)
                .where(AgentOutput.job_id == job.id, AgentOutput.validation_status == "valid")
                .order_by(AgentOutput.created_at)
            )
            .scalars()
            .all()
        )
        by_schema = {o.schema_name: o.payload for o in outputs}
        up: dict[str, Any] = {}
        if "requirements_analysis" in by_schema:
            up["scenarios"] = by_schema["requirements_analysis"]["scenarios"]
        if task.task_type in ("evidence.correlate", "report.build"):
            execs = (
                session.execute(select(TestExecution).where(TestExecution.job_id == job.id))
                .scalars()
                .all()
            )
            up["executions"] = [
                {
                    "id": e.id,
                    "scenario_id": e.scenario_id,
                    "name": e.name,
                    "status": e.status,
                    "evidence_id": e.evidence_id,
                    "meta": e.meta,
                    "test_type": e.test_type,
                    "node_id": e.node_id,
                    "file": e.file,
                    "message": e.message,
                    "check_run_id": e.check_run_id,
                }
                for e in execs
            ]
            checks = (
                session.execute(
                    select(CheckRun).where(CheckRun.job_id == job.id).order_by(CheckRun.started_at)
                )
                .scalars()
                .all()
            )
            up["check_runs"] = [
                {
                    "id": c.id,
                    "engine": c.engine_id,
                    "name": c.name,
                    "outcome": c.outcome,
                    "duration_ms": c.duration_ms,
                    "failure_message": c.failure_message,
                    "summary": c.summary,
                    "tool": {"name": c.tool_name, "version": c.tool_version},
                    "executes_repository_code": c.executes_repository_code,
                    "log_evidence_id": c.log_evidence_id,
                    "evidence_ids": list((c.evidence or {}).get("items", [])),
                }
                for c in checks
            ]
            if task.task_type == "evidence.correlate":
                ev_ids = [e.evidence_id for e in execs if e.evidence_id]
                items = (
                    session.execute(select(EvidenceItem).where(EvidenceItem.id.in_(ev_ids)))
                    .scalars()
                    .all()
                    if ev_ids
                    else []
                )
                up["evidence"] = [
                    {"id": i.id, "kind": i.kind, "sha256": i.sha256, "content": i.content}
                    for i in items
                ]
        if task.task_type == "report.build":
            up["findings"] = [
                {
                    "id": f.id,
                    "display_id": f.display_id,
                    "category": f.category,
                    "severity": f.severity,
                    "confidence": f.confidence,
                    "dcs": f.dcs,
                    "title": f.title,
                    "status": f.status,
                    "risk_priority": float(f.risk_priority),
                    "recurring": bool((f.history or {}).get("recurring")),
                }
                for f in session.execute(
                    select(Finding)
                    .where(Finding.job_id == job.id)
                    .order_by(Finding.risk_priority.desc(), Finding.dcs.desc())
                ).scalars()
            ]
            up["tasks"] = [
                {
                    "id": t.id,
                    "agent_id": t.agent_id,
                    "task_type": t.task_type,
                    # The report task itself is still running while it composes the report.
                    "state": "succeeded" if t.id == task.id else t.state,
                    "attempts": t.attempt_count,
                    "error_class": t.last_error_class,
                    "error_code": t.last_error_code,
                }
                for t in session.execute(select(Task).where(Task.job_id == job.id)).scalars()
            ]
            up["warnings"] = list((job.warnings or {}).get("items", []))
        return up

    # ------------------------------------------------------------------ job progression
    def reconcile(self, session: Session, job: Job) -> None:
        """Advance the job based on its tasks' states. Idempotent."""
        session.refresh(job)
        if (
            JobStateMachine.is_terminal(JobState(job.state))
            or job.state == JobState.CANCELLING.value
        ):
            return
        tasks = session.execute(select(Task).where(Task.job_id == job.id)).scalars().all()
        if not tasks:
            return
        terminal = {s.value for s in TERMINAL_TASK_STATES}
        failed_critical = [
            t
            for t in tasks
            if t.state
            in (TaskState.FAILED.value, TaskState.INVALID_OUTPUT.value, TaskState.TIMED_OUT.value)
            and t.inputs.get("critical")
        ]
        if failed_critical and job.state in (
            JobState.RUNNING.value,
            JobState.ANALYZING.value,
            JobState.REPORTING.value,
        ):
            transition_job(
                session,
                job,
                JobEvent.CRITICAL_PATH_TASK_FAILED,
                actor_type="service",
                actor_id="orchestrator",
                details={"tasks": [t.id for t in failed_critical]},
            )
            job.current_stage = "cleanup_and_retention"
            build_report(session, job, partial=True)
            for t in tasks:
                if t.state == TaskState.PENDING.value:
                    from qaswarm.domain.state_machines import (
                        TaskEvent,
                    )  # local import to avoid cycle

                    t.state = TaskState.SKIPPED.value
                    append_event(
                        session,
                        org_id=job.org_id,
                        actor_type="service",
                        actor_id="orchestrator",
                        action="task.state_changed",
                        subject_type="task",
                        subject_id=t.id,
                        job_id=job.id,
                        details={
                            "from": "pending",
                            "to": "skipped",
                            "event": TaskEvent.UPSTREAM_FAILED.value,
                        },
                    )
            session.commit()
            return
        by_stage: dict[str, list[Task]] = {}
        for t in tasks:
            by_stage.setdefault(t.stage, []).append(t)
        testing_done = all(
            t.state in terminal
            for s, ts in by_stage.items()
            if s not in ("evidence_correlation_and_triage", "quality_gates_and_reporting")
            for t in ts
        )
        evidence_done = testing_done and all(
            t.state in terminal for t in by_stage.get("evidence_correlation_and_triage", [])
        )
        report_done = evidence_done and all(
            t.state in terminal for t in by_stage.get("quality_gates_and_reporting", [])
        )
        if job.state == JobState.RUNNING.value and testing_done:
            job.current_stage = "evidence_correlation_and_triage"
            transition_job(
                session,
                job,
                JobEvent.TESTING_STAGES_DONE,
                actor_type="service",
                actor_id="orchestrator",
            )
        if job.state == JobState.ANALYZING.value and evidence_done:
            job.current_stage = "quality_gates_and_reporting"
            transition_job(
                session, job, JobEvent.TRIAGE_DONE, actor_type="service", actor_id="orchestrator"
            )
        if job.state == JobState.REPORTING.value and report_done:
            warn_states = {TaskState.SKIPPED.value, TaskState.TIMED_OUT.value}
            warnings = any(
                t.state in warn_states or (t.state == TaskState.FAILED.value) for t in tasks
            )
            skipped_execs = session.execute(
                select(func.count())
                .select_from(TestExecution)
                .where(
                    TestExecution.job_id == job.id,
                    TestExecution.status.in_(
                        ["skipped", "blocked", "timed_out", "infrastructure_error"]
                    ),
                )
            ).scalar_one()
            degraded_checks = session.execute(
                select(func.count())
                .select_from(CheckRun)
                .where(CheckRun.job_id == job.id, CheckRun.outcome.in_(["skipped", "error"]))
            ).scalar_one()
            inconclusive = False
            report = (
                session.execute(select(Report).where(Report.job_id == job.id)).scalars().first()
            )
            if report is not None:
                inconclusive = any(
                    g["result"] == "inconclusive" for g in report.content.get("gates", [])
                )
            job.current_stage = "cleanup_and_retention"
            event = (
                JobEvent.REPORT_STORED_WARNINGS
                if (
                    warnings
                    or skipped_execs
                    or degraded_checks
                    or inconclusive
                    or (job.warnings or {}).get("items")
                )
                else JobEvent.REPORT_STORED_NO_WARNINGS
            )
            transition_job(
                session,
                job,
                event,
                actor_type="service",
                actor_id="orchestrator",
                details={
                    "skipped_or_blocked_executions": int(skipped_execs),
                    "inconclusive_gate": inconclusive,
                },
            )
        session.commit()

    def cancel_cleanup(self, session: Session, job: Job, actor: str) -> int:
        """Cancel every non-terminal task; no workers exist, so cleanup is immediate."""
        return self.queue.cancel_job_tasks(session, job.id, actor=actor)

    # ------------------------------------------------------------------ synchronous driver (tests, CLI)
    def run_job_to_completion(
        self, session: Session, job_id: str, *, max_steps: int = 50, scheduler: Any = None
    ) -> Job:
        """Synchronous driver for tests and the CLI: scheduler tick (intake, planning,
        reaping, state advancement) followed by agent task execution until the job is terminal
        or waits for approval. Execution Service tasks need a worker and are not run here."""
        job = session.get(Job, job_id)
        assert job is not None
        for _ in range(max_steps):
            session.commit()
            if scheduler is not None:
                scheduler.tick()
            session.expire_all()
            session.refresh(job)
            if (
                JobStateMachine.is_terminal(JobState(job.state))
                or job.state == JobState.AWAITING_APPROVAL.value
            ):
                break
            if job.state in (JobState.VALIDATING.value, JobState.QUEUED.value):
                if scheduler is None:
                    break  # nothing can admit the job without a scheduler
                continue
            if self.run_once(session) == 0:
                # Nothing leasable: maybe retries are scheduled in the future; stop to avoid spinning.
                self.reconcile(session, job)
                pending = session.execute(
                    select(func.count())
                    .select_from(Task)
                    .where(
                        Task.job_id == job.id,
                        Task.state.in_(
                            [
                                TaskState.PENDING.value,
                                TaskState.RETRY_SCHEDULED.value,
                                TaskState.LEASED.value,
                                TaskState.RUNNING.value,
                            ]
                        ),
                    )
                ).scalar_one()
                if pending == 0 and scheduler is None:
                    break
                time.sleep(0.05)
        session.commit()
        session.refresh(job)
        return job
