"""Job and task state machines built from the LLD transition tables.

``transition(current, event)`` returns the new state or raises ``IllegalTransition``.
Terminal states have no outgoing transitions.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import Generic, TypeVar

from qaswarm.domain.enums import (
    TERMINAL_JOB_STATES,
    TERMINAL_TASK_STATES,
    JobState,
    TaskState,
)


class IllegalTransition(Exception):
    def __init__(self, machine: str, state: StrEnum, event: StrEnum) -> None:
        self.machine = machine
        self.state = state
        self.event = event
        super().__init__(f"{machine}: no transition from '{state}' on event '{event}'")


class JobEvent(StrEnum):
    JOB_ADMITTED = "job_admitted"
    VALIDATION_PASSED = "validation_passed"
    POLICY_DENIED = "policy_denied"
    INTAKE_ERROR = "intake_error"
    PLANNER_LEASED = "planner_leased"
    PLAN_VALID_APPROVAL_REQUIRED = "plan_valid_approval_required"
    PLAN_VALID_NO_APPROVAL = "plan_valid_no_approval"
    PLAN_INVALID = "plan_invalid"
    APPROVALS_RECORDED = "approvals_recorded"
    APPROVAL_REJECTED = "approval_rejected"
    TESTING_STAGES_DONE = "testing_stages_done"
    TRIAGE_DONE = "triage_done"
    REPORT_STORED_NO_WARNINGS = "report_stored_no_warnings"
    REPORT_STORED_WARNINGS = "report_stored_warnings"
    CRITICAL_PATH_TASK_FAILED = "critical_path_task_failed"
    CANCEL_REQUESTED = "cancel_requested"
    DEADLINE_PASSED = "deadline_passed"
    CLEANUP_CONFIRMED_USER = "cleanup_confirmed_user"
    CLEANUP_CONFIRMED_TIMEOUT = "cleanup_confirmed_timeout"


class TaskEvent(StrEnum):
    LEASED = "leased"
    UPSTREAM_FAILED = "upstream_failed"
    FIRST_HEARTBEAT = "first_heartbeat"
    LEASE_EXPIRED = "lease_expired"
    VALID_RESULT = "valid_result"
    TRANSIENT_ERROR = "transient_error"
    INVALID_OUTPUT_FIRST = "invalid_output_first"
    INVALID_OUTPUT_SECOND = "invalid_output_second"
    TASK_TIMEOUT = "task_timeout"
    NON_RETRYABLE_ERROR = "non_retryable_error"
    BUDGET_REMAINS = "budget_remains"
    BUDGET_EXHAUSTED = "budget_exhausted"
    JOB_CANCELLING = "job_cancelling"


S = TypeVar("S", bound=StrEnum)
E = TypeVar("E", bound=StrEnum)


class StateMachine(Generic[S, E]):
    name: str
    states: frozenset[S]
    terminal: frozenset[S]
    table: Mapping[tuple[S, E], S]

    def __init__(
        self,
        name: str,
        states: frozenset[S],
        terminal: frozenset[S],
        table: Mapping[tuple[S, E], S],
    ) -> None:
        self.name = name
        self.states = states
        self.terminal = terminal
        self.table = dict(table)
        for (src, _), dst in self.table.items():
            if src in terminal:
                raise ValueError(f"{name}: terminal state {src} must have no outgoing transitions")
            if dst not in states or src not in states:
                raise ValueError(f"{name}: unknown state in transition {src} -> {dst}")

    def is_terminal(self, state: S) -> bool:
        return state in self.terminal

    def can(self, state: S, event: E) -> bool:
        return (state, event) in self.table

    def transition(self, state: S, event: E) -> S:
        try:
            return self.table[(state, event)]
        except KeyError as exc:
            raise IllegalTransition(self.name, state, event) from exc

    def events_from(self, state: S) -> list[E]:
        return [ev for (src, ev) in self.table if src == state]


_ACTIVE_JOB_STATES: tuple[JobState, ...] = (
    JobState.QUEUED,
    JobState.PLANNING,
    JobState.AWAITING_APPROVAL,
    JobState.RUNNING,
    JobState.ANALYZING,
    JobState.REPORTING,
)
_NON_TERMINAL_JOB_STATES: tuple[JobState, ...] = tuple(
    s for s in JobState if s not in TERMINAL_JOB_STATES
)


def _job_table() -> dict[tuple[JobState, JobEvent], JobState]:
    t: dict[tuple[JobState, JobEvent], JobState] = {
        # Main path
        (JobState.CREATED, JobEvent.JOB_ADMITTED): JobState.VALIDATING,
        (JobState.VALIDATING, JobEvent.VALIDATION_PASSED): JobState.QUEUED,
        (JobState.VALIDATING, JobEvent.POLICY_DENIED): JobState.BLOCKED,
        (JobState.VALIDATING, JobEvent.INTAKE_ERROR): JobState.FAILED,
        (JobState.QUEUED, JobEvent.PLANNER_LEASED): JobState.PLANNING,
        (JobState.PLANNING, JobEvent.PLAN_VALID_APPROVAL_REQUIRED): JobState.AWAITING_APPROVAL,
        (JobState.PLANNING, JobEvent.PLAN_VALID_NO_APPROVAL): JobState.RUNNING,
        (JobState.PLANNING, JobEvent.PLAN_INVALID): JobState.FAILED,
        (JobState.AWAITING_APPROVAL, JobEvent.APPROVALS_RECORDED): JobState.RUNNING,
        (JobState.AWAITING_APPROVAL, JobEvent.APPROVAL_REJECTED): JobState.CANCELLING,
        (JobState.RUNNING, JobEvent.TESTING_STAGES_DONE): JobState.ANALYZING,
        (JobState.ANALYZING, JobEvent.TRIAGE_DONE): JobState.REPORTING,
        (JobState.REPORTING, JobEvent.REPORT_STORED_NO_WARNINGS): JobState.COMPLETED,
        (JobState.REPORTING, JobEvent.REPORT_STORED_WARNINGS): JobState.COMPLETED_WITH_WARNINGS,
        # Failure, cancellation, timeout
        (JobState.RUNNING, JobEvent.CRITICAL_PATH_TASK_FAILED): JobState.FAILED,
        (JobState.ANALYZING, JobEvent.CRITICAL_PATH_TASK_FAILED): JobState.FAILED,
        (JobState.REPORTING, JobEvent.CRITICAL_PATH_TASK_FAILED): JobState.FAILED,
        (JobState.CANCELLING, JobEvent.CLEANUP_CONFIRMED_USER): JobState.CANCELLED,
        (JobState.CANCELLING, JobEvent.CLEANUP_CONFIRMED_TIMEOUT): JobState.TIMED_OUT,
    }
    for s in _NON_TERMINAL_JOB_STATES:
        if s is JobState.CANCELLING:
            continue
        t[(s, JobEvent.CANCEL_REQUESTED)] = JobState.CANCELLING
        t[(s, JobEvent.DEADLINE_PASSED)] = JobState.CANCELLING
    return t


def _task_table() -> dict[tuple[TaskState, TaskEvent], TaskState]:
    t: dict[tuple[TaskState, TaskEvent], TaskState] = {
        (TaskState.PENDING, TaskEvent.LEASED): TaskState.LEASED,
        (TaskState.PENDING, TaskEvent.UPSTREAM_FAILED): TaskState.SKIPPED,
        (TaskState.LEASED, TaskEvent.FIRST_HEARTBEAT): TaskState.RUNNING,
        (TaskState.LEASED, TaskEvent.LEASE_EXPIRED): TaskState.FAILED_RETRYABLE,
        (TaskState.RUNNING, TaskEvent.LEASE_EXPIRED): TaskState.FAILED_RETRYABLE,
        (TaskState.RUNNING, TaskEvent.VALID_RESULT): TaskState.SUCCEEDED,
        (TaskState.RUNNING, TaskEvent.TRANSIENT_ERROR): TaskState.FAILED_RETRYABLE,
        (TaskState.RUNNING, TaskEvent.INVALID_OUTPUT_FIRST): TaskState.FAILED_RETRYABLE,
        (TaskState.RUNNING, TaskEvent.INVALID_OUTPUT_SECOND): TaskState.INVALID_OUTPUT,
        (TaskState.RUNNING, TaskEvent.TASK_TIMEOUT): TaskState.TIMED_OUT,
        (TaskState.RUNNING, TaskEvent.NON_RETRYABLE_ERROR): TaskState.FAILED,
        (TaskState.FAILED_RETRYABLE, TaskEvent.BUDGET_REMAINS): TaskState.RETRY_SCHEDULED,
        (TaskState.FAILED_RETRYABLE, TaskEvent.BUDGET_EXHAUSTED): TaskState.FAILED,
        (TaskState.RETRY_SCHEDULED, TaskEvent.LEASED): TaskState.LEASED,
    }
    for s in (TaskState.PENDING, TaskState.LEASED, TaskState.RUNNING, TaskState.RETRY_SCHEDULED):
        t[(s, TaskEvent.JOB_CANCELLING)] = TaskState.CANCELLED
    return t


JobStateMachine: StateMachine[JobState, JobEvent] = StateMachine(
    "JobStateMachine", frozenset(JobState), TERMINAL_JOB_STATES, _job_table()
)
TaskStateMachine: StateMachine[TaskState, TaskEvent] = StateMachine(
    "TaskStateMachine", frozenset(TaskState), TERMINAL_TASK_STATES, _task_table()
)

__all__ = [
    "_ACTIVE_JOB_STATES",
    "IllegalTransition",
    "JobEvent",
    "JobStateMachine",
    "StateMachine",
    "TaskEvent",
    "TaskStateMachine",
]
