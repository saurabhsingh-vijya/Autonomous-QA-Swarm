# Implementation decisions

The spec in `docs/spec/` (v0.1, concept) contradicts itself in a few places. This
file records which reading the code follows. When the spec and this file disagree,
the code follows this file.

## Behaviour choices for spec conflicts

| # | Topic | Code behaviour | Spec sources reconciled |
|---|---|---|---|
| 1 | Mutation when mapped baseline tests fail | Mutation task ends `blocked`; MutationRun `inconclusive`, no score | AC-090, UC-07, AG-07, mutation workflow |
| 2 | Advisory gate inconclusive | Only *blocking* inconclusive gates make the verdict `INCONCLUSIVE`; an inconclusive advisory gate gives at most `READY_WITH_RISKS` | QG doc verdict step 4 vs mutation doc |
| 3 | Token budget exhausted | Remaining LLM tasks end `skipped` (reason `budget_exhausted`); deterministic tasks continue; job `completed_with_warnings` | AC-158, E-MODEL-002 vs tech/obs docs |
| 4 | Job cancelled during verification | Patch `verification_failed` (reason `cancelled before completion`); re-verify allowed without new HA-06 if diff unchanged | FS-15, orchestration vs patch doc |
| 5 | DAST without HA-02 | Job waits in `awaiting_approval`; rejection ends `cancelled` | security workflow vs safe-use table |
| 6 | Job timeout while awaiting approval | Job ends `timed_out` | LLD vs perf doc |
| 7 | Worker result fails schema validation | Attempt `failed_retryable` (error class `infrastructure_error`), max 2 retries, then `failed` with `E-EXEC-004` | LLD vs sandbox doc |
| 8 | Worker OOM | Always `infrastructure_error`, never a product defect | FS-04 vs sandbox table |
| 9 | Corrective retry for invalid LLM output | Done once inside the Model Gateway call; the task state machine has no separate corrective branch | LLD lines 72 vs 314 |
| 10 | Approving a superseded plan | `409`; stale `If-Match` is `412` | AC-026 vs UC-03 |
| 11 | HA-09 / HA-10 separation of duties | Enforced: the QA Lead who overrides a gate cannot record HA-10 for that job | identity doc vs UJ-06 |
| 16 | Fork-triggered jobs | Always require HA-05 plan approval | integrations doc |
| 17 | Early evidence deletion | Allowed for a QA Lead (personal data), audited; otherwise retention only | safe-use vs AC-095 |
| 18 | Evidence key layout | `evidence/{org_id}/{sha256[0:2]}/{sha256}` | LLD vs evidence doc |
| 20 | Patch size limit | ≤ 10 files, ≤ 300 changed lines | patch doc vs SCR-12 |
| 21 | Spike / Soak caps | Spike burst ≤ 300 VUs for ≤ 60 s, 5 min cap; Soak ≤ 50 VUs, 2 h | AC-082 vs key questions |

## Environment-driven deviations (honest limits of this build)

| Spec | This build | Why |
|---|---|---|
| gVisor rootless containers, network off (SEC-003/004) | Plain subprocess workers with time, output and process-tree limits. `WorkerRun.isolation = "none-dev"`. The execution service **refuses to start** unless `AQS_UNSAFE_LOCAL_EXEC=1` is set. Network isolation is **not** enforced. | Windows dev machine, no Docker/gVisor. Run only trusted fixture repos. |
| PostgreSQL + `FOR UPDATE SKIP LOCKED`, RLS | SQLite by default (Postgres URL supported). Leasing uses a conditional `UPDATE … WHERE state IN (…)` compare-and-set. `org_id` is enforced in the service layer. | Zero-setup local run. |
| OPA/Rego policy engine | Python deny-by-default evaluator with the same 8-step order and audited decisions. | No OPA binary available. |
| OpenBao/Vault Secrets Broker | Local secrets broker (env/encrypted file) behind the same interface; agents never get values. | No secrets backend installed. |
| Keycloak OIDC | Dev auth: bearer tokens mapped to seeded users/roles (`X-Dev-User` fallback). OIDC verifier is a pluggable interface. | No IdP installed. |
| Semgrep, Gitleaks, OSV-Scanner, Trivy, Checkov, k6, mutmut, Stryker | Bandit is used when installed. A built-in pattern secret scanner, built-in Python AST mutation engine and built-in async HTTP load generator are used. Missing external tools end their task `skipped` with reason `tool not installed`. | Binaries not installed; downloading them needs owner approval. mutmut does not run natively on Windows. |
| LLM providers | Model Gateway defaults to an `offline` provider, which triggers the documented LLM-outage fallbacks (template plan, raw scanner alerts, report without narrative). An Anthropic adapter is used only if `ANTHROPIC_API_KEY` is set. | No provider configured. |
| Python 3.12 | Python 3.11 | Installed runtime. |
| PDF report | Generated only if WeasyPrint is importable; otherwise the PDF format returns `503` with a reason. | Optional dependency. |
| Private repos / GitHub App | Public HTTPS repos and a dev-only `local` fixture provider (off unless `AQS_ALLOW_LOCAL_REPOS=1`). | No app credentials. |
