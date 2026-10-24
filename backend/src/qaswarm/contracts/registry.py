"""Schema registry: name + major version → JSON Schema document (loaded from this package)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import resources
from typing import Any


@dataclass(frozen=True)
class SchemaRef:
    name: str
    version: str
    filename: str


SCHEMAS: dict[str, SchemaRef] = {
    "task_contract/1": SchemaRef("task_contract", "1.0", "task_contract_v1.json"),
    "worker_result/1": SchemaRef("worker_result", "1.0", "worker_result_v1.json"),
}


def list_schemas() -> list[SchemaRef]:
    return list(SCHEMAS.values())


def get_schema(key: str) -> dict[str, Any]:
    ref = SCHEMAS[key]
    text = resources.files("qaswarm.contracts.schemas").joinpath(ref.filename).read_text("utf-8")
    loaded: dict[str, Any] = json.loads(text)
    return loaded
