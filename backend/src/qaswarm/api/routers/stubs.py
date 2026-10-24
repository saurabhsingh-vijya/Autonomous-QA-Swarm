"""501 Not Implemented stubs generated from the contract table. They never return fake data."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends, Request

from qaswarm.api.auth import Principal, get_principal
from qaswarm.api.contract_table import ContractEndpoint, unimplemented
from qaswarm.api.errors import Problem

router = APIRouter(tags=["not implemented yet"])


def _make_handler(endpoint: ContractEndpoint) -> Callable[..., Any]:
    def handler(request: Request, principal: Principal = Depends(get_principal)) -> None:
        raise Problem(
            501,
            "not_implemented",
            f"{endpoint.method} {endpoint.path} ({endpoint.purpose}) is planned for slice "
            f"{endpoint.slice} and is not implemented in this build.",
            planned_slice=endpoint.slice,
        )

    handler.__name__ = f"stub_{endpoint.method.lower()}_" + (
        endpoint.path.strip("/")
        .replace("/", "_")
        .replace("{", "")
        .replace("}", "")
        .replace("-", "_")
    )
    handler.__doc__ = f"Planned for slice {endpoint.slice}: {endpoint.purpose}. Returns 501."
    return handler


for _ep in unimplemented():
    router.add_api_route(
        _ep.path,
        _make_handler(_ep),
        methods=[_ep.method],
        summary=f"[slice {_ep.slice}] {_ep.purpose}",
        responses={501: {"description": "not_implemented (problem+json)"}},
        status_code=501,
    )
