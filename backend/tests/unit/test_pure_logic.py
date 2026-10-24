from __future__ import annotations

import random

import pytest

from qaswarm.api.pagination import decode_cursor, encode_cursor
from qaswarm.api.services.repositories import UrlRejected, validate_repository_url
from qaswarm.audit.chain import GENESIS_HASH, canonical_json, compute_hash
from qaswarm.config import Settings
from qaswarm.domain.enums import RepositoryProvider
from qaswarm.telemetry.logging import redact_text, redact_value
from qaswarm.workflow.queue import TaskQueue, TaskSpec

SETTINGS = Settings(dev_auth=True, git_host_allowlist=["github.com", "gitlab.com"])


@pytest.mark.parametrize(
    ("url", "provider"),
    [
        ("https://github.com/northwind/payments-api", RepositoryProvider.GITHUB),
        ("https://github.com/northwind/payments-api.git", RepositoryProvider.GITHUB),
        ("https://GitHub.com/Northwind/Payments-API/", RepositoryProvider.GITHUB),
        ("https://gitlab.com/group/repo", RepositoryProvider.GITLAB),
    ],
)
def test_url_accepted_and_normalised(url: str, provider: RepositoryProvider) -> None:
    out = validate_repository_url(url, provider, SETTINGS)
    assert out.startswith("https://") and out == out.lower() and not out.endswith(".git")


@pytest.mark.parametrize(
    ("url", "reason"),
    [
        ("http://github.com/a/b", "scheme_not_https"),
        ("ssh://git@github.com/a/b", "scheme_not_https"),
        ("file:///etc/passwd", "scheme_not_https"),
        ("https://user:token@github.com/a/b", "credentials_in_url"),
        ("https://10.0.4.12/internal/repo.git", "host_not_allow_listed"),
        ("https://169.254.169.254/latest/meta-data", "host_not_allow_listed"),
        ("https://evil.example.com/a/b", "host_not_allow_listed"),
        ("https://github.com:8443/a/b", "host_not_allow_listed"),
        ("https://github.com/onlyowner", "path_shape"),
        ("https://github.com/a/b/c", "path_shape"),
        ("https://github.com/a/b?x=1", "path_shape"),
    ],
)
def test_url_rejected_syntactically(url: str, reason: str) -> None:
    with pytest.raises(UrlRejected) as exc:
        validate_repository_url(url, RepositoryProvider.GITHUB, SETTINGS)
    assert exc.value.reason == reason


def test_provider_host_mismatch() -> None:
    with pytest.raises(UrlRejected) as exc:
        validate_repository_url("https://github.com/a/b", RepositoryProvider.GITLAB, SETTINGS)
    assert exc.value.code == "provider_mismatch"


def test_hash_chain_is_deterministic_and_order_sensitive() -> None:
    body = {"b": 1, "a": {"y": [1, 2], "x": "é"}}
    assert canonical_json(body) == '{"a":{"x":"é","y":[1,2]},"b":1}'
    h1 = compute_hash(GENESIS_HASH, body)
    assert h1 == compute_hash(GENESIS_HASH, {"a": {"y": [1, 2], "x": "é"}, "b": 1})
    assert h1 != compute_hash(h1, body)
    assert len(h1) == 64


def test_redaction_masks_tokens_passwords_and_authorization() -> None:
    text = (
        "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0."
        "sflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c "
        "password=hunter2 token: ghp_abcdefghijklmnopqrstuvwxyz0123 https://u:pw@github.com/a/b"
    )
    out = redact_text(text)
    assert (
        "hunter2" not in out
        and "ghp_abc" not in out
        and "eyJhbGci" not in out
        and ":pw@" not in out
    )
    assert redact_value({"Authorization": "x", "nested": {"password": "y", "ok": "fine"}}) == {
        "Authorization": "[REDACTED]",
        "nested": {"password": "[REDACTED]", "ok": "fine"},
    }


def test_cursor_round_trip() -> None:
    assert decode_cursor(encode_cursor("job_01ABC")) == "job_01ABC"
    assert decode_cursor(None) is None


def test_task_idempotency_key_is_stable_and_input_sensitive() -> None:
    a = TaskSpec("org_x", "job_x", "planning", "plan", {"k": 1, "j": 2})
    b = TaskSpec("org_x", "job_x", "planning", "plan", {"j": 2, "k": 1})
    c = TaskSpec("org_x", "job_x", "planning", "plan", {"k": 2})
    assert a.idempotency_key() == b.idempotency_key() != c.idempotency_key()


def test_backoff_uses_30_then_120_seconds_with_20_percent_jitter() -> None:
    q = TaskQueue(SETTINGS, rng=random.Random(7))
    for attempt, base in ((1, 30), (2, 120), (3, 120)):
        for _ in range(200):
            v = q.backoff_seconds(attempt)
            assert base * 0.8 <= v <= base * 1.2
