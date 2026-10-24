"""Idempotency store (fixture)."""

import hashlib
import json


class IdempotencyConflict(Exception):
    pass


class IdempotencyStore:
    def __init__(self) -> None:
        self._records: dict[str, tuple[str, dict[str, object]]] = {}

    @staticmethod
    def payload_hash(payload: dict[str, object]) -> str:
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()

    def reserve(self, key: str, payload: dict[str, object]) -> dict[str, object]:
        h = self.payload_hash(payload)
        if key in self._records:
            stored_hash, response = self._records[key]
            if stored_hash != h:
                raise IdempotencyConflict(key)
            return response
        response = {"key": key, "replayed": False}
        self._records[key] = (h, response)
        return response
