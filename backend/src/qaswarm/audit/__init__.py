"""Audit event construction and hash chaining (SEC-013, FR-054)."""

from qaswarm.audit.chain import (
    GENESIS_HASH,
    ChainBreak,
    append_event,
    canonical_json,
    compute_hash,
    verify_chain,
)

__all__ = [
    "GENESIS_HASH",
    "ChainBreak",
    "append_event",
    "canonical_json",
    "compute_hash",
    "verify_chain",
]
