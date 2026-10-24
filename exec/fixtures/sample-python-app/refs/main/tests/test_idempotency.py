import pytest

from app.idempotency import IdempotencyConflict, IdempotencyStore


def test_same_key_same_payload_replays():
    store = IdempotencyStore()
    first = store.reserve("k-1", {"amount": "10"})
    second = store.reserve("k-1", {"amount": "10"})
    assert first is second


def test_same_key_different_payload_conflicts():
    store = IdempotencyStore()
    store.reserve("k-2", {"amount": "10"})
    with pytest.raises(IdempotencyConflict):
        store.reserve("k-2", {"amount": "20"})
