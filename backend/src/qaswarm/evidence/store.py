from __future__ import annotations

import hashlib
import os
from pathlib import Path

from sqlalchemy.orm import Session

from qaswarm.db.models import EvidenceItem
from qaswarm.domain.ids import new_id
from qaswarm.telemetry.logging import redact_text

OUTPUT_CAP_BYTES = 50 * 1024 * 1024  # LLD: 50 MiB captured output per task
TRUNCATION_MARKER = b"\n[TRUNCATED by Evidence Store at 50 MiB]\n"

TEXT_MEDIA_PREFIXES = ("text/", "application/json", "application/xml", "application/x-ndjson")


class EvidenceIntegrityError(Exception):
    """Stored bytes no longer hash to their address."""


class EvidenceStore:
    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.root = Path(root)

    @staticmethod
    def storage_key(org_id: str, sha256: str) -> str:
        return f"evidence/{org_id}/{sha256[:2]}/{sha256}"

    def path_for(self, org_id: str, sha256: str) -> Path:
        return self.root / self.storage_key(org_id, sha256)

    def put(self, org_id: str, data: bytes) -> tuple[str, str]:
        """Store ``data`` idempotently; return ``(sha256, storage_key)``. Never overwrites."""
        sha = hashlib.sha256(data).hexdigest()
        key = self.storage_key(org_id, sha)
        path = self.root / key
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(path.name + ".tmp")
            tmp.write_bytes(data)
            os.replace(tmp, path)
        return sha, key

    def get(self, org_id: str, sha256: str) -> bytes:
        path = self.path_for(org_id, sha256)
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != sha256:
            raise EvidenceIntegrityError(sha256)
        return data

    def exists(self, org_id: str, sha256: str) -> bool:
        return self.path_for(org_id, sha256).exists()


def store_evidence(
    session: Session,
    store: EvidenceStore,
    *,
    org_id: str,
    job_id: str,
    kind: str,
    content: bytes | str,
    media_type: str,
    producer: str,
    label: str = "",
    task_id: str | None = None,
    worker_run_id: str | None = None,
    deterministic: bool = True,
    cap_bytes: int = OUTPUT_CAP_BYTES,
) -> EvidenceItem:
    """Redact (text), cap, hash and store one evidence object; return its metadata row."""
    redactions = 0
    if isinstance(content, str):
        redacted = redact_text(content)
        redactions = 0 if redacted == content else 1
        data = redacted.encode("utf-8")
    elif media_type.startswith(TEXT_MEDIA_PREFIXES):
        text = content.decode("utf-8", errors="replace")
        redacted = redact_text(text)
        redactions = 0 if redacted == text else 1
        data = redacted.encode("utf-8")
    else:
        data = content
    original = len(data)
    truncated = original > cap_bytes
    if truncated:
        data = data[:cap_bytes] + TRUNCATION_MARKER
    sha, key = store.put(org_id, data)
    item = EvidenceItem(
        id=new_id("evidence_item"),
        org_id=org_id,
        job_id=job_id,
        task_id=task_id,
        worker_run_id=worker_run_id,
        kind=kind,
        label=label[:200],
        sha256=sha,
        storage_key=key,
        size_bytes=len(data),
        media_type=media_type,
        producer=producer[:120],
        redactions=redactions,
        truncated=truncated,
        original_bytes=original if truncated else None,
        deterministic=deterministic,
    )
    session.add(item)
    session.flush()
    return item
