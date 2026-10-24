"""Every endpoint in the API contract with the slice that implements it.

The 501 stubs are generated from this table so that nothing in the contract is missed and the
OpenAPI document shows the whole surface. Implemented endpoints are listed too, so the table
doubles as a coverage checklist (tests assert that every row is either implemented or stubbed).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ContractEndpoint:
    method: str
    path: str
    purpose: str
    slice: str
    implemented: bool = False


CONTRACT: tuple[ContractEndpoint, ...] = (
    ContractEndpoint("POST", "/projects", "Create project", "1a", True),
    ContractEndpoint("GET", "/projects", "List projects", "1a", True),
    ContractEndpoint("POST", "/repositories", "Register repository", "1a", True),
    ContractEndpoint("GET", "/repositories/{repository_id}", "Repository details", "1a", True),
    ContractEndpoint(
        "POST",
        "/repositories/{repository_id}/validate",
        "Re-validate reachability and resolve default branch",
        "1b",
    ),
    ContractEndpoint("POST", "/targets", "Register target environment", "2b"),
    ContractEndpoint(
        "POST",
        "/targets/{target_id}/authorizations",
        "Record authorization attestation (HA-01)",
        "2b",
    ),
    ContractEndpoint("POST", "/jobs", "Create QA job", "1a", True),
    ContractEndpoint("GET", "/jobs", "List jobs", "1a", True),
    ContractEndpoint("GET", "/jobs/{job_id}", "Job details", "1a", True),
    ContractEndpoint("POST", "/jobs/{job_id}/cancel", "Request cancellation", "1a", True),
    ContractEndpoint("GET", "/jobs/{job_id}/events", "Server-Sent Events stream", "1a", True),
    ContractEndpoint("GET", "/jobs/{job_id}/plan", "Job plan (DAG)", "3", True),
    ContractEndpoint(
        "POST", "/jobs/{job_id}/plan/approval", "Approve/reject plan (HA-05)", "3", True
    ),
    ContractEndpoint("GET", "/jobs/{job_id}/tasks", "Tasks with attempts and status", "3", True),
    ContractEndpoint("GET", "/jobs/{job_id}/test-executions", "Test results", "3", True),
    ContractEndpoint("GET", "/jobs/{job_id}/findings", "Findings", "3", True),
    ContractEndpoint(
        "GET", "/findings/{finding_id}", "Finding with evidence references", "3", True
    ),
    ContractEndpoint("POST", "/findings/{finding_id}/triage", "Change finding status", "5", True),
    ContractEndpoint("GET", "/findings/{finding_id}/evidence", "Evidence items", "3", True),
    ContractEndpoint("GET", "/jobs/{job_id}/performance-runs", "Performance runs", "3b"),
    ContractEndpoint("GET", "/jobs/{job_id}/mutation-runs", "Mutation runs", "3c"),
    ContractEndpoint("GET", "/jobs/{job_id}/patches", "Patch proposals", "3d"),
    ContractEndpoint("POST", "/patches/{patch_id}/review", "Approve/reject patch (HA-06)", "3d"),
    ContractEndpoint(
        "POST", "/patches/{patch_id}/verifications", "Start independent verification", "3d"
    ),
    ContractEndpoint("GET", "/verifications/{verification_id}", "Verification result", "3d"),
    ContractEndpoint("GET", "/jobs/{job_id}/quality-gates", "Quality gate results", "3", True),
    ContractEndpoint("GET", "/jobs/{job_id}/report", "Report", "3", True),
    ContractEndpoint(
        "POST", "/jobs/{job_id}/release-decision", "Record release decision (HA-10)", "2d"
    ),
    ContractEndpoint("GET", "/audit-events", "Audit trail", "1d", True),
)

# Endpoints added beyond the v0.1 contract table in phase 2 (recorded as a deviation for review).
ADDITIONAL: tuple[ContractEndpoint, ...] = (
    ContractEndpoint("GET", "/jobs/{job_id}/checks", "Check runs with outcomes", "2", True),
    ContractEndpoint("GET", "/jobs/{job_id}/evidence", "Evidence items of a job", "2", True),
    ContractEndpoint("GET", "/jobs/{job_id}/worker-runs", "Worker runs of a job", "2", True),
    ContractEndpoint("GET", "/jobs/{job_id}/compare", "Compare two runs", "2", True),
    ContractEndpoint("GET", "/evidence/{evidence_id}", "Evidence metadata", "2", True),
    ContractEndpoint("GET", "/evidence/{evidence_id}/content", "Evidence inline text", "2", True),
    ContractEndpoint("GET", "/evidence/{evidence_id}/download", "Evidence bytes", "2", True),
    ContractEndpoint("GET", "/system/capabilities", "Build capabilities", "2", True),
)


def unimplemented() -> list[ContractEndpoint]:
    return [e for e in CONTRACT if not e.implemented]
