"""Prefixed ULID identifiers (``job_01J…``) and display id helpers."""

from __future__ import annotations

import re

from ulid import ULID

PREFIXES: dict[str, str] = {
    "organization": "org_",
    "user": "usr_",
    "membership": "mbr_",
    "project": "prj_",
    "repository": "rep_",
    "credential_reference": "crd_",
    "target_environment": "tgt_",
    "target_authorization": "tauth_",
    "job": "job_",
    "job_plan": "pln_",
    "task": "tsk_",
    "task_attempt": "att_",
    "agent_output": "aout_",
    "worker_run": "wrk_",
    "source_snapshot": "snp_",
    "finding": "fnd_",
    "evidence_item": "evd_",
    "patch": "pch_",
    "verification_run": "ver_",
    "audit_event": "aud_",
    "outbox_event": "evt_",
}

_ULID_RE = re.compile(r"^[a-z_]+_[0-9A-HJKMNP-TV-Z]{26}$")


def new_id(entity: str) -> str:
    return f"{PREFIXES[entity]}{ULID()}"


def is_id(value: str, entity: str | None = None) -> bool:
    if not _ULID_RE.match(value):
        return False
    return entity is None or value.startswith(PREFIXES[entity])


def display_id(prefix: str, sequence: int) -> str:
    """Human-friendly display id such as ``QJ-1042``."""
    return f"{prefix}-{sequence:04d}"
