"""Table-driven tests for every LLD transition plus Hypothesis property tests."""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from qaswarm.domain.enums import TERMINAL_JOB_STATES, TERMINAL_TASK_STATES, JobState, TaskState
from qaswarm.domain.state_machines import (
    IllegalTransition,
    JobEvent,
    JobStateMachine,
    TaskEvent,
    TaskStateMachine,
)

J, JE = JobState, JobEvent
T, TE = TaskState, TaskEvent

JOB_MAIN_PATH = [
    (J.CREATED, JE.JOB_ADMITTED, J.VALIDATING),
    (J.VALIDATING, JE.VALIDATION_PASSED, J.QUEUED),
    (J.VALIDATING, JE.POLICY_DENIED, J.BLOCKED),
    (J.VALIDATING, JE.INTAKE_ERROR, J.FAILED),
    (J.QUEUED, JE.PLANNER_LEASED, J.PLANNING),
    (J.PLANNING, JE.PLAN_VALID_APPROVAL_REQUIRED, J.AWAITING_APPROVAL),
    (J.PLANNING, JE.PLAN_VALID_NO_APPROVAL, J.RUNNING),
    (J.PLANNING, JE.PLAN_INVALID, J.FAILED),
    (J.AWAITING_APPROVAL, JE.APPROVALS_RECORDED, J.RUNNING),
    (J.AWAITING_APPROVAL, JE.APPROVAL_REJECTED, J.CANCELLING),
    (J.RUNNING, JE.TESTING_STAGES_DONE, J.ANALYZING),
    (J.ANALYZING, JE.TRIAGE_DONE, J.REPORTING),
    (J.REPORTING, JE.REPORT_STORED_NO_WARNINGS, J.COMPLETED),
    (J.REPORTING, JE.REPORT_STORED_WARNINGS, J.COMPLETED_WITH_WARNINGS),
]
JOB_FAILURE_PATH = [
    (J.RUNNING, JE.CRITICAL_PATH_TASK_FAILED, J.FAILED),
    (J.ANALYZING, JE.CRITICAL_PATH_TASK_FAILED, J.FAILED),
    (J.REPORTING, JE.CRITICAL_PATH_TASK_FAILED, J.FAILED),
    (J.CANCELLING, JE.CLEANUP_CONFIRMED_USER, J.CANCELLED),
    (J.CANCELLING, JE.CLEANUP_CONFIRMED_TIMEOUT, J.TIMED_OUT),
]
JOB_CANCEL_ROWS = [
    (s, ev, J.CANCELLING)
    for s in J
    if s not in TERMINAL_JOB_STATES and s is not J.CANCELLING
    for ev in (JE.CANCEL_REQUESTED, JE.DEADLINE_PASSED)
]

TASK_ROWS = [
    (T.PENDING, TE.LEASED, T.LEASED),
    (T.PENDING, TE.UPSTREAM_FAILED, T.SKIPPED),
    (T.LEASED, TE.FIRST_HEARTBEAT, T.RUNNING),
    (T.LEASED, TE.LEASE_EXPIRED, T.FAILED_RETRYABLE),
    (T.RUNNING, TE.LEASE_EXPIRED, T.FAILED_RETRYABLE),
    (T.RUNNING, TE.VALID_RESULT, T.SUCCEEDED),
    (T.RUNNING, TE.TRANSIENT_ERROR, T.FAILED_RETRYABLE),
    (T.RUNNING, TE.INVALID_OUTPUT_FIRST, T.FAILED_RETRYABLE),
    (T.RUNNING, TE.INVALID_OUTPUT_SECOND, T.INVALID_OUTPUT),
    (T.RUNNING, TE.TASK_TIMEOUT, T.TIMED_OUT),
    (T.RUNNING, TE.NON_RETRYABLE_ERROR, T.FAILED),
    (T.FAILED_RETRYABLE, TE.BUDGET_REMAINS, T.RETRY_SCHEDULED),
    (T.FAILED_RETRYABLE, TE.BUDGET_EXHAUSTED, T.FAILED),
    (T.RETRY_SCHEDULED, TE.LEASED, T.LEASED),
    (T.PENDING, TE.JOB_CANCELLING, T.CANCELLED),
    (T.LEASED, TE.JOB_CANCELLING, T.CANCELLED),
    (T.RUNNING, TE.JOB_CANCELLING, T.CANCELLED),
    (T.RETRY_SCHEDULED, TE.JOB_CANCELLING, T.CANCELLED),
]


@pytest.mark.parametrize(
    ("src", "event", "dst"), JOB_MAIN_PATH + JOB_FAILURE_PATH + JOB_CANCEL_ROWS
)
def test_job_allowed_transition(src: JobState, event: JobEvent, dst: JobState) -> None:
    assert JobStateMachine.transition(src, event) is dst


@pytest.mark.parametrize(("src", "event", "dst"), TASK_ROWS)
def test_task_allowed_transition(src: TaskState, event: TaskEvent, dst: TaskState) -> None:
    assert TaskStateMachine.transition(src, event) is dst


def test_job_table_is_exactly_the_lld_table() -> None:
    expected = {(s, e): d for s, e, d in JOB_MAIN_PATH + JOB_FAILURE_PATH + JOB_CANCEL_ROWS}
    assert dict(JobStateMachine.table) == expected


def test_task_table_is_exactly_the_lld_table() -> None:
    assert dict(TaskStateMachine.table) == {(s, e): d for s, e, d in TASK_ROWS}


@pytest.mark.parametrize("state", sorted(TERMINAL_JOB_STATES))
def test_terminal_job_states_have_no_outgoing_transitions(state: JobState) -> None:
    assert JobStateMachine.is_terminal(state)
    assert JobStateMachine.events_from(state) == []
    for event in JobEvent:
        with pytest.raises(IllegalTransition):
            JobStateMachine.transition(state, event)


@pytest.mark.parametrize("state", sorted(TERMINAL_TASK_STATES))
def test_terminal_task_states_have_no_outgoing_transitions(state: TaskState) -> None:
    assert TaskStateMachine.is_terminal(state)
    for event in TaskEvent:
        with pytest.raises(IllegalTransition):
            TaskStateMachine.transition(state, event)


@pytest.mark.parametrize(
    ("src", "event"),
    [
        (J.CREATED, JE.VALIDATION_PASSED),
        (J.QUEUED, JE.TESTING_STAGES_DONE),
        (J.RUNNING, JE.REPORT_STORED_NO_WARNINGS),
        (J.CANCELLING, JE.CANCEL_REQUESTED),
        (J.COMPLETED, JE.CANCEL_REQUESTED),
    ],
)
def test_job_illegal_transitions_raise(src: JobState, event: JobEvent) -> None:
    with pytest.raises(IllegalTransition) as exc:
        JobStateMachine.transition(src, event)
    assert exc.value.state is src and exc.value.event is event


@pytest.mark.parametrize(
    ("src", "event"),
    [
        (T.PENDING, TE.VALID_RESULT),
        (T.LEASED, TE.VALID_RESULT),
        (T.SUCCEEDED, TE.LEASED),
        (T.FAILED, TE.BUDGET_REMAINS),
        (T.RETRY_SCHEDULED, TE.FIRST_HEARTBEAT),
    ],
)
def test_task_illegal_transitions_raise(src: TaskState, event: TaskEvent) -> None:
    with pytest.raises(IllegalTransition):
        TaskStateMachine.transition(src, event)


def _walk(machine, start, events):  # type: ignore[no-untyped-def]
    state = start
    for ev in events:
        if machine.is_terminal(state):
            with pytest.raises(IllegalTransition):
                machine.transition(state, ev)
            continue
        if machine.can(state, ev):
            state = machine.transition(state, ev)
        else:
            with pytest.raises(IllegalTransition):
                machine.transition(state, ev)
        assert state in machine.states
    return state


@settings(max_examples=200, deadline=None)
@given(st.lists(st.sampled_from(list(JobEvent)), max_size=40))
def test_job_random_event_sequences_stay_in_defined_states(events: list[JobEvent]) -> None:
    state = _walk(JobStateMachine, JobState.CREATED, events)
    assert state in set(JobState)


@settings(max_examples=200, deadline=None)
@given(
    st.sampled_from(sorted(TERMINAL_JOB_STATES)),
    st.lists(st.sampled_from(list(JobEvent)), max_size=20),
)
def test_job_terminal_state_is_never_left(start: JobState, events: list[JobEvent]) -> None:
    assert _walk(JobStateMachine, start, events) is start


@settings(max_examples=200, deadline=None)
@given(st.lists(st.sampled_from(list(TaskEvent)), max_size=40))
def test_task_random_event_sequences_stay_in_defined_states(events: list[TaskEvent]) -> None:
    assert _walk(TaskStateMachine, TaskState.PENDING, events) in set(TaskState)


@settings(max_examples=200, deadline=None)
@given(
    st.sampled_from(sorted(TERMINAL_TASK_STATES)),
    st.lists(st.sampled_from(list(TaskEvent)), max_size=20),
)
def test_task_terminal_state_is_never_left(start: TaskState, events: list[TaskEvent]) -> None:
    assert _walk(TaskStateMachine, start, events) is start
