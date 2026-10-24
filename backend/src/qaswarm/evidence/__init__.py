"""qaswarm.evidence: content-addressed, immutable Evidence Store (phase 2).

Objects live on the local filesystem under ``AQS_EVIDENCE_DIR`` using the LLD key layout
``evidence/{org_id}/{sha256[0:2]}/{sha256}``. Text is redacted **before** it is hashed, so an
unredacted secret is never persisted. Signed download URLs and retention jobs arrive later.
"""

from qaswarm.evidence.store import EvidenceStore, store_evidence

__all__ = ["EvidenceStore", "store_evidence"]
