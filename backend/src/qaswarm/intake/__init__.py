"""qaswarm.intake: Source Intake Service (phase 2, minimal slice 1b).

The control plane only resolves a ref to a commit SHA (``git ls-remote``) after DNS resolution and
private-address rejection (SEC-002). It never clones, checks out or executes anything (SEC-001).
Fetching the pinned commit happens in the Execution Service.
"""

from qaswarm.intake.resolvers import (
    FixtureRefResolver,
    GitLsRemoteResolver,
    IntakeError,
    RefResolver,
    ResolvedRef,
    resolver_for,
)
from qaswarm.intake.service import run_intake

__all__ = [
    "FixtureRefResolver",
    "GitLsRemoteResolver",
    "IntakeError",
    "RefResolver",
    "ResolvedRef",
    "resolver_for",
    "run_intake",
]
