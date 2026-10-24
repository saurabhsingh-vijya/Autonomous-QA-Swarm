"""HTTP client for the control plane's ``/internal/v1/exec`` API."""

from __future__ import annotations

from typing import Any

import httpx


class ControlPlaneError(Exception):
    def __init__(self, status: int, body: Any) -> None:
        self.status = status
        self.body = body
        code = body.get("error_code") if isinstance(body, dict) else None
        super().__init__(f"control plane returned {status} {code or ''}".strip())


class LeaseLostError(ControlPlaneError):
    """409 lease_lost: stop work and discard the result."""


class ResultRejected(ControlPlaneError):
    """422 worker_result_invalid: the attempt was failed server-side (E-EXEC-004)."""


class ControlPlaneClient:
    def __init__(
        self, http: httpx.Client, token: str, *, base_path: str = "/internal/v1/exec"
    ) -> None:
        self.http = http
        self.base = base_path.rstrip("/")
        self.headers = {"X-Exec-Token": token, "Accept": "application/json"}

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        resp = self.http.post(f"{self.base}{path}", json=payload, headers=self.headers)
        if resp.status_code >= 400:
            try:
                body = resp.json()
            except ValueError:
                body = {"raw": resp.text[:500]}
            code = body.get("error_code") if isinstance(body, dict) else None
            if resp.status_code == 409 and code == "lease_lost":
                raise LeaseLostError(resp.status_code, body)
            if resp.status_code == 422 and code == "worker_result_invalid":
                raise ResultRejected(resp.status_code, body)
            raise ControlPlaneError(resp.status_code, body)
        data: dict[str, Any] = resp.json()
        return data

    def lease(
        self, worker_id: str, task_types: list[str], batch_size: int = 1
    ) -> list[dict[str, Any]]:
        data = self._post(
            "/lease", {"worker_id": worker_id, "task_types": task_types, "batch_size": batch_size}
        )
        tasks: list[dict[str, Any]] = data.get("tasks", [])
        return tasks

    def heartbeat(self, task_id: str, worker_id: str) -> dict[str, Any]:
        return self._post(f"/tasks/{task_id}/heartbeat", {"worker_id": worker_id})

    def create_worker_run(self, task_id: str, payload: dict[str, Any]) -> str:
        data = self._post(f"/tasks/{task_id}/worker-runs", payload)
        return str(data["worker_run_id"])

    def destroy_worker_run(self, worker_run_id: str, payload: dict[str, Any]) -> None:
        self._post(f"/worker-runs/{worker_run_id}/destroyed", payload)

    def upload_evidence(self, task_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._post(f"/tasks/{task_id}/evidence", payload)

    def submit_result(self, task_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._post(f"/tasks/{task_id}/result", payload)

    def submit_failure(self, task_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._post(f"/tasks/{task_id}/fail", payload)
