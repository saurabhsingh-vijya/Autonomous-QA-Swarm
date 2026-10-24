# qaswarm_exec — Execution Service host agent

Phase 2 build. Leases `env_prepare` and `check` tasks from the control plane's narrow internal API
(`/internal/v1/exec`, token `AQS_EXEC_TOKEN`), fetches the pinned commit into a disposable
workspace, runs **check engines** through a **process runtime**, uploads evidence and submits a
schema-shaped worker result. It never touches the database and imports nothing from `qaswarm`.

## What runs where

| Piece | Module | Notes |
|---|---|---|
| Worker loop | `host/worker.py` | lease → worker run → heartbeat thread → fetch → engine → evidence → result → destroyed |
| Control-plane client | `host/client.py` | `LeaseLostError` (409) stops work; `ResultRejected` (422, E-EXEC-004) means the attempt was failed server-side |
| Source fetchers | `host/source.py` | `GitSourceFetcher` (one commit over HTTPS, hooks/LFS/submodules off, `git archive`, safe extract) and `FixtureSourceFetcher` (`fixtures/`, dev only) |
| Runtime | `runtime/subprocess_runtime.py` | **not a sandbox**: temp workspace, scrubbed env, wall clock, output cap, process-tree kill. `isolation = "process"`. `DockerRuntime` reports unavailable |
| Check engines | `tools/` | `snapshot_integrity`, `python_syntax`, `secret_scan` (no code execution) and `pytest` (executes repository code; refused unless `AQS_EXEC_ALLOW_UNSANDBOXED_CODE_EXECUTION=true`) |
| Normalisation | `results/` | JUnit XML → the six test statuses; worker result envelope per the LLD schema |

Add an engine: implement `tools.base.CheckEngine` and register it in `tools/registry.py`; the
planner picks it up by id.

## Run

```bash
AQS_EXEC_TOKEN=<same as the API> AQS_EXEC_CONTROL_PLANE_URL=http://127.0.0.1:8000 \
AQS_EXEC_FIXTURES_DIR=./fixtures AQS_EXEC_ALLOW_UNSANDBOXED_CODE_EXECUTION=false \
python -m qaswarm_exec
```

Outcomes per check: `passed`, `failed`, `skipped`, `error` (tool/infrastructure failure, never
the code under test). A task that exceeds its wall clock is reported `timed_out`.
