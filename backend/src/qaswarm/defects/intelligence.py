"""Deterministic defect intelligence.

- ``risk_priority``: Severity weight x Confidence factor x Exposure (design 11/02), returned with
  its breakdown so the ordering is explainable. It is a sorting aid, never a gate.
- ``root_cause_hypotheses``: rule-based suggestions derived from the observed status and the
  captured evidence (response body excerpt, headers). Each hypothesis names the evidence it rests
  on and an uncertainty level; none of them changes the DCS or the status.
- ``cross_run_history``: earlier findings with the same fingerprint on the same repository, so a
  recurring defect links to its previous occurrences (design 11/01 "same defect across jobs").
- ``carry_over_status``: suppression semantics from FR-037: a prior ``false_positive`` on the
  same fingerprint within 90 days suppresses the new record (recorded, never silently dropped);
  a prior ``fix_verified`` reappearing becomes ``reopened``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from qaswarm.db.models import Finding, Job

SEVERITY_WEIGHT = {"critical": 10, "high": 7, "medium": 4, "low": 2, "informational": 0}
CONFIDENCE_FACTOR = {"confirmed": 1.0, "probable": 0.6, "candidate": 0.3, "rejected": 0.0}
EXPOSURE = {"external": 1.0, "internal": 0.7, "test_only": 0.4}
SUPPRESSION_DAYS = 90


def risk_priority(severity: str, confidence: str, exposure: str) -> tuple[float, dict[str, Any]]:
    w = SEVERITY_WEIGHT.get(severity, 0)
    c = CONFIDENCE_FACTOR.get(confidence, 0.0)
    e = EXPOSURE.get(exposure, 0.7)
    value = round(w * c * e, 2)
    return value, {
        "formula": "severity_weight * confidence_factor * exposure",
        "severity": severity,
        "severity_weight": w,
        "confidence": confidence,
        "confidence_factor": c,
        "exposure": exposure,
        "exposure_factor": e,
        "value": value,
        "note": "Sorting aid only; a low priority never removes a hard blocker.",
    }


@dataclass
class Hypothesis:
    hypothesis: str
    basis: str
    uncertainty: str  # "low" | "medium" | "high"
    supporting_evidence: list[str] = field(default_factory=list)
    source: str = "deterministic rule"

    def as_dict(self) -> dict[str, Any]:
        return {
            "hypothesis": self.hypothesis,
            "basis": self.basis,
            "uncertainty": self.uncertainty,
            "supporting_evidence": self.supporting_evidence,
            "source": self.source,
            "verified": False,
        }


def root_cause_hypotheses(
    observed: int | None,
    expected: int | None,
    evidence: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Rule-based hypotheses. ``evidence`` items are ``{"id", "content"}`` with the redacted
    http_exchange content. Nothing here is verified; every entry says so."""
    ids = [str(e.get("id")) for e in evidence if e.get("id")]
    bodies = " ".join(
        str(((e.get("content") or {}).get("response") or {}).get("body_excerpt") or "")
        for e in evidence
    ).lower()
    headers: dict[str, str] = {}
    for e in evidence:
        h = ((e.get("content") or {}).get("response") or {}).get("headers") or {}
        headers.update({str(k).lower(): str(v).lower() for k, v in h.items()})
    out: list[Hypothesis] = []
    if observed is None:
        out.append(
            Hypothesis(
                "No HTTP response was captured; the target may be unreachable or timed out.",
                "observed status is absent in the execution metadata",
                "high",
                ids,
            )
        )
        return [h.as_dict() for h in out]
    if observed == 404:
        out.append(
            Hypothesis(
                "The route is not registered at this path, or the contract path differs from the implementation.",
                f"observed 404 where {expected} was expected",
                "medium",
                ids,
            )
        )
        if "not found" in bodies and "text/html" in headers.get("content-type", ""):
            out.append(
                Hypothesis(
                    "The request reached a static or proxy server rather than the API (HTML 'not found' page).",
                    "response content-type is text/html",
                    "medium",
                    ids,
                )
            )
    elif observed in (401, 403):
        out.append(
            Hypothesis(
                "The endpoint requires credentials or a role the check did not send.",
                f"observed {observed}; RaOne sends no credentials with API checks",
                "low",
                ids,
            )
        )
    elif observed == 405:
        out.append(
            Hypothesis(
                "The method is not allowed on this route; the contract may list a different method.",
                "observed 405",
                "low",
                ids,
            )
        )
    elif observed in (400, 422):
        out.append(
            Hypothesis(
                "The request shape (query, headers or body) does not satisfy the endpoint's validation.",
                f"observed {observed}",
                "medium",
                ids,
            )
        )
    elif observed == 429:
        out.append(
            Hypothesis(
                "The target rate-limited the check; the failure may not reproduce at a lower rate.",
                "observed 429",
                "medium",
                ids,
            )
        )
    elif observed >= 500:
        out.append(
            Hypothesis(
                "An unhandled server error or a failing upstream dependency.",
                f"observed {observed}",
                "medium",
                ids,
            )
        )
        if "timeout" in bodies or "timed out" in bodies:
            out.append(
                Hypothesis(
                    "A downstream call timed out inside the server.",
                    "response body mentions a timeout",
                    "medium",
                    ids,
                )
            )
        if observed in (502, 503, 504):
            out.append(
                Hypothesis(
                    "The service behind the gateway was unavailable when the check ran.",
                    f"{observed} is typically emitted by a proxy or gateway",
                    "medium",
                    ids,
                )
            )
    elif 200 <= observed < 400:
        out.append(
            Hypothesis(
                "The endpoint responds, but with a different success or redirect status than the contract states.",
                f"observed {observed}, expected {expected}",
                "medium",
                ids,
            )
        )
    else:
        out.append(
            Hypothesis(
                "The response status differs from the contract for an unclassified reason.",
                f"observed {observed}, expected {expected}",
                "high",
                ids,
            )
        )
    return [h.as_dict() for h in out]


def cross_run_history(session: Session, job: Job, fingerprint: str) -> dict[str, Any]:
    """Earlier findings with the same fingerprint on the same repository and organisation."""
    rows = session.execute(
        select(Finding, Job)
        .join(Job, Job.id == Finding.job_id)
        .where(
            Finding.org_id == job.org_id,
            Finding.fingerprint == fingerprint,
            Job.repository_id == job.repository_id,
            Job.id != job.id,
        )
        .order_by(Finding.created_at.desc())
    ).all()
    prior = [
        {
            "finding_id": f.id,
            "display_id": f.display_id,
            "job_id": j.id,
            "job_display_id": j.display_id,
            "job_ref": j.ref,
            "status": f.status,
            "confidence": f.confidence,
            "dcs": f.dcs,
            "seen_at": f.created_at.isoformat(),
        }
        for f, j in rows
    ]
    first = prior[-1] if prior else None
    return {
        "prior_occurrences": prior,
        "times_seen_before": len(prior),
        "first_seen": first,
        "recurring": bool(prior),
        "scope": "same repository, same organisation, exact fingerprint",
    }


def carry_over_status(
    history: dict[str, Any], now: datetime | None = None
) -> tuple[str, str | None]:
    """Status for a new finding given its history, and the reason when it is not ``candidate``."""
    now = now or datetime.now(UTC)
    prior = history.get("prior_occurrences") or []
    if not prior:
        return "candidate", None
    latest = prior[0]
    if latest["status"] == "false_positive":
        seen = datetime.fromisoformat(latest["seen_at"])
        if seen.tzinfo is None:
            seen = seen.replace(tzinfo=UTC)
        if now - seen <= timedelta(days=SUPPRESSION_DAYS):
            return (
                "false_positive",
                f"Suppressed: same fingerprint as {latest['display_id']} marked false positive on "
                f"{seen.date().isoformat()} (suppression lasts {SUPPRESSION_DAYS} days).",
            )
    if latest["status"] == "fix_verified":
        return (
            "reopened",
            f"Reappeared after {latest['display_id']} was marked fix_verified; reopened.",
        )
    return "candidate", None


def suggested_duplicates(
    signature: str, location: str, candidates: list[tuple[str, str, str]]
) -> list[dict[str, Any]]:
    """Near matches (AC-101): token similarity ≥ 0.9 on the signature with the same location.
    ``candidates`` are ``(finding_id, location, signature)``. Suggested only; never merged."""
    tokens = set(signature.replace(":", " ").replace("!=", " ").split())
    out = []
    for fid, loc, sig in candidates:
        if loc != location:
            continue
        other = set(sig.replace(":", " ").replace("!=", " ").split())
        if not tokens or not other:
            continue
        sim = len(tokens & other) / len(tokens | other)
        if sim >= 0.9 and sig != signature:
            out.append({"finding_id": fid, "similarity": round(sim, 3)})
    return out
