"""Enumerations exactly as the LLD and data model define them."""

from __future__ import annotations

from enum import StrEnum


class JobState(StrEnum):
    CREATED = "created"
    VALIDATING = "validating"
    QUEUED = "queued"
    PLANNING = "planning"
    AWAITING_APPROVAL = "awaiting_approval"
    RUNNING = "running"
    ANALYZING = "analyzing"
    REPORTING = "reporting"
    CANCELLING = "cancelling"
    COMPLETED = "completed"
    COMPLETED_WITH_WARNINGS = "completed_with_warnings"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"
    BLOCKED = "blocked"


TERMINAL_JOB_STATES: frozenset[JobState] = frozenset(
    {
        JobState.COMPLETED,
        JobState.COMPLETED_WITH_WARNINGS,
        JobState.FAILED,
        JobState.CANCELLED,
        JobState.TIMED_OUT,
        JobState.BLOCKED,
    }
)


class TaskState(StrEnum):
    PENDING = "pending"
    LEASED = "leased"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED_RETRYABLE = "failed_retryable"
    RETRY_SCHEDULED = "retry_scheduled"
    FAILED = "failed"
    INVALID_OUTPUT = "invalid_output"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"


TERMINAL_TASK_STATES: frozenset[TaskState] = frozenset(
    {
        TaskState.SUCCEEDED,
        TaskState.FAILED,
        TaskState.INVALID_OUTPUT,
        TaskState.TIMED_OUT,
        TaskState.CANCELLED,
        TaskState.SKIPPED,
    }
)


class TaskAttemptOutcome(StrEnum):
    LEASED = "leased"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    LEASE_EXPIRED = "lease_expired"
    CANCELLED = "cancelled"


class ErrorClass(StrEnum):
    INFRASTRUCTURE_ERROR = "infrastructure_error"
    POLICY_DENIED = "policy_denied"
    CONTRACT_ERROR = "contract_error"
    TOOL_ERROR = "tool_error"


class RetryClass(StrEnum):
    TRANSIENT = "transient"
    CORRECTIVE = "corrective"


class TestExecutionStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    BLOCKED = "blocked"
    TIMED_OUT = "timed_out"
    INFRASTRUCTURE_ERROR = "infrastructure_error"


class CheckOutcome(StrEnum):
    """Outcome of one check run (a task executed by a check engine).

    ``error`` means the tool or the infrastructure failed; it never describes the code under
    test. Individual tests inside a check use :class:`TestExecutionStatus`.
    """

    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"


class EvidenceKind(StrEnum):
    LOG = "log"
    JUNIT_XML = "junit_xml"
    SCANNER_REPORT = "scanner_report"
    ENVIRONMENT_MANIFEST = "environment_manifest"
    SOURCE_INVENTORY = "source_inventory"
    STACK_TRACE = "stack_trace"


class WorkerRunOutcome(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"


class FindingStatus(StrEnum):
    CANDIDATE = "candidate"
    TRIAGING = "triaging"
    REPRODUCING = "reproducing"
    CONFIRMED = "confirmed"
    NOT_REPRODUCIBLE = "not_reproducible"
    FALSE_POSITIVE = "false_positive"
    DUPLICATE = "duplicate"
    ACCEPTED_RISK = "accepted_risk"
    FIX_PROPOSED = "fix_proposed"
    FIX_VERIFIED = "fix_verified"
    FIX_FAILED = "fix_failed"
    REOPENED = "reopened"


class PatchStatus(StrEnum):
    PROPOSED = "proposed"
    AWAITING_REVIEW = "awaiting_review"
    APPROVED_FOR_VERIFICATION = "approved_for_verification"
    VERIFICATION_RUNNING = "verification_running"
    VERIFIED = "verified"
    VERIFICATION_FAILED = "verification_failed"
    REJECTED = "rejected"


class GateResult(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    ADVISORY_FAILED = "advisory_failed"
    INCONCLUSIVE = "inconclusive"
    NOT_APPLICABLE = "not_applicable"
    PENDING = "pending"


class Verdict(StrEnum):
    READY = "READY"
    READY_WITH_RISKS = "READY_WITH_RISKS"
    NOT_READY = "NOT_READY"
    INCONCLUSIVE = "INCONCLUSIVE"


class Role(StrEnum):
    ORG_ADMIN = "Org Admin"
    QA_LEAD = "QA Lead"
    QA_ENGINEER = "QA Engineer"
    DEVELOPER = "Developer"
    SECURITY_REVIEWER = "Security Reviewer"
    VIEWER = "Viewer"
    CI_SERVICE_ACCOUNT = "CI Service Account"


class Severity(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFORMATIONAL = "informational"


class Confidence(StrEnum):
    CONFIRMED = "confirmed"
    PROBABLE = "probable"
    CANDIDATE = "candidate"
    REJECTED = "rejected"


class SecuritySourceClass(StrEnum):
    SCANNER_ALERT = "scanner_alert"
    PROBABLE_VULNERABILITY = "probable_vulnerability"
    CONFIRMED_VULNERABILITY = "confirmed_vulnerability"
    FALSE_POSITIVE = "false_positive"


class RepositoryProvider(StrEnum):
    GITHUB = "github"
    GITLAB = "gitlab"
    OTHER = "other"


class RepositoryValidationStatus(StrEnum):
    PENDING_VALIDATION = "pending_validation"
    VALIDATING = "validating"
    VALID = "valid"
    VALIDATION_FAILED = "validation_failed"


class FunctionalProfile(StrEnum):
    NONE = "none"
    STANDARD = "standard"


class SecurityProfile(StrEnum):
    NONE = "none"
    QUICK = "quick"
    STANDARD = "standard"
    DEEP = "deep"


class PerformanceProfile(StrEnum):
    NONE = "none"
    SMOKE = "smoke"
    BASELINE = "baseline"
    LOAD = "load"
    STRESS = "stress"
    SPIKE = "spike"
    SOAK = "soak"


PIPELINE_STAGES: tuple[str, ...] = (
    "intake_and_pinning",
    "planning",
    "environment_preparation",
    "baseline_run",
    "functional_and_api_testing",
    "security_testing",
    "performance_testing",
    "mutation_testing",
    "evidence_correlation_and_triage",
    "patch_proposal",
    "independent_verification",
    "quality_gates_and_reporting",
    "cleanup_and_retention",
)
