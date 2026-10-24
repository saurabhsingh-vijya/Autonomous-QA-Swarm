# Release checklist — Autonomous QA Swarm

Use this before tagging any release. "Verified" means somebody ran it on the release candidate
and recorded the output in the phase report or the release notes. A box that cannot be ticked
blocks the release unless the risk is accepted in writing in the "Accepted risks" table.

Status legend for the current build (Phase 2 engine + Phase 6 hardening, `phase6-hardening`):
✅ done and verified · ⚠️ done, not verified on this machine · ❌ not done (blocking for production).

## 1. Build and test gates

- [x] ✅ `ruff check` and `ruff format --check` clean (backend + exec)
- [x] ✅ `mypy` clean (strict for domain/workflow)
- [x] ✅ Backend unit + integration tests green against PostgreSQL 16 (209 tests on 2026-10-24)
- [x] ✅ Web `tsc`, `eslint` (0 errors), `prettier --check`, `vitest` (25), `vite build`
- [x] ✅ `alembic upgrade head → downgrade base → upgrade head` on an empty database
- [x] ✅ Fresh `uv sync --frozen` and fresh `npm ci` succeed from the lockfiles
- [ ] ⚠️ CI workflow green on GitHub (pins uv 0.13.5; run it after pushing)
- [x] ✅ `pip-audit` reports no known vulnerabilities
- [ ] ⚠️ `npm audit`: remaining items are dev tooling only (vitest/tinypool, esbuild dev server, tailwind 3 → postcss-selector-parser, react-router SSR path). Re-check on each release; upgrade vitest ≥ 5 / tailwind 4 when the web code is ready for them.

## 2. Verified user workflows (run against a live API, not mocks)

- [x] ✅ Project → repository → job → Intake & Pinning → plan → execution → `completed_with_warnings`
- [x] ✅ Checks, test executions, evidence (masked secret scan), worker runs, JSON + HTML report
- [x] ✅ Second run on a fixed ref → compare shows improved checks and tests
- [x] ✅ Idempotent replay (`Idempotent-Replayed: true`), key reuse → 422, duplicate active → 409
- [x] ✅ Cancel with a live worker → `cancelling` → worker reports destroyed → `cancelled`
- [x] ✅ API + embedded worker killed mid-task, restarted: lease reaped (E-QUEUE-001), retry succeeds, orphaned worker run `presumed_dead`, job completes
- [x] ✅ Role boundaries: Viewer cannot create/cancel/read evidence/read audit; unauthenticated → 401; exec API without/with wrong token → 401, unset token → 503
- [x] ✅ UI numbers (Dashboard tiles, job detail summaries, stages) equal the API payloads
- [ ] ❌ A real public GitHub repository end-to-end (needs network from the API and worker hosts; not run in Phase 6)

## 3. Security

- [x] ✅ Control plane never executes repository code (intake uses `git ls-remote` only)
- [x] ✅ Repository URL validation: https only, allow-listed hosts, no credentials, no IP literals, no ports; DNS private-address rejection; git redirects disabled
- [x] ✅ Fixture refs cannot escape the fixtures directory (control plane and worker)
- [x] ✅ Tar extraction rejects absolute paths, `..`, drive letters, symlinks and devices
- [x] ✅ Log and evidence redaction covers header, env, JSON/YAML, URL-credential, JWT, private-key and vendor token shapes
- [x] ✅ Security response headers (nosniff, DENY, no-referrer, CSP, no-store on `/api`)
- [x] ✅ Startup warnings for every unsafe flag, exposed in `/system/capabilities`
- [ ] ❌ Sandbox runtime (gVisor/Docker, non-root, read-only FS, no network during tests) — slice 1c. **Production blocker.** Until then `AQS_EXEC_ALLOW_UNSANDBOXED_CODE_EXECUTION` must stay `false` on any shared host.
- [ ] ❌ Authentication: OIDC + RBAC (slice 3e). **Production blocker.** `AQS_DEV_AUTH` must be `false` on anything reachable by untrusted users, which currently means the API is unusable there.
- [ ] ❌ Rate limiting on `/api/v1` and `/internal/v1/exec`
- [ ] ❌ Database role for the API without `UPDATE`/`DELETE` on `audit_events`
- [ ] ❌ Secrets broker integration (credentials for private repositories)
- [ ] ❌ External penetration test / threat-model review sign-off (SEC-016)

## 4. Configuration for the target environment

- [ ] `AQS_ENVIRONMENT` set (`staging` / `prod`), no `configuration:` warnings at startup other than the OIDC notice
- [ ] `AQS_DATABASE_URL` with a unique password, TLS to PostgreSQL where it crosses a network
- [ ] `AQS_EXEC_TOKEN` ≥ 32 random characters, identical on control plane and worker hosts, rotated with a documented procedure
- [ ] `AQS_DEV_AUTH=false`, `AQS_DEV_FIXTURE_REPOS=false`, `AQS_EMBEDDED_EXEC_WORKER=false`, `AQS_EXEC_ALLOW_UNSANDBOXED_CODE_EXECUTION=false`
- [ ] `AQS_EVIDENCE_DIR` on persistent storage with a retention job (none exists yet)
- [ ] `AQS_CORS_ORIGINS` limited to the UI origin
- [ ] Worker hosts: `git` installed, no route to the database, outbound network restricted to the Git hosts

## 5. Operations

- [ ] Backups of PostgreSQL and the evidence directory tested with a restore
- [ ] `/healthz` and `/readyz` wired to the orchestrator; scheduler and worker processes supervised (systemd/Kubernetes); one scheduler instance at a time is safest (steps use `SKIP LOCKED`, so two are tolerated)
- [ ] Log shipping of the JSON logs; alert on `worker runs presumed dead` and on jobs in `cancelling` for more than two lease TTLs
- [ ] Runbook for stuck jobs: cancel → wait one lease TTL → check `/jobs/{id}/worker-runs`
- [ ] Release notes list the `501` endpoints and the known limitations from the README

## 6. Accepted risks (fill in per release)

| Risk | Owner | Decision | Expiry |
|---|---|---|---|
| Process runtime is not a sandbox | | | |
| Dev header auth only | | | |
| DNS rebinding between intake check and `git ls-remote` | | | |
| Dev-tooling npm advisories (vitest/esbuild/tailwind 3) | | | |
