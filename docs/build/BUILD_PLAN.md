# Build plan — Autonomous QA Swarm (phase-wise, for Claude Code)

Each slice is one Claude Code session (roughly 1–3 hours of agent work). Finish and review a slice before starting the next. Each slice ends with a report in `docs/build/phase-<id>-report.md` and must meet its exit check before you move on.

The slices below break roadmap **Phase 1 (Foundations)**, **Phase 2** and **Phase 3** into buildable pieces. Requirement IDs refer to `docs/design/03-requirements/01-functional-requirements.md`.

## Phase 1 — Foundations

| Slice | Goal | Main requirements | Design files to point Claude at | Exit check |
|---|---|---|---|---|
| **1a Boilerplate** | Monorepo, Docker Compose, FastAPI skeleton, DB + migrations, state machines, task queue core, audit chain, API stubs for repositories and jobs, React shell with all 15 screens as routes, CI | FR-005, FR-006, FR-047, FR-054 (partial), NFR-013, NFR-014 (partial) | 02-high-level-design, 03-low-level-design, 04-component-architecture, 05-technology-options, 07-data-model, 08-api-contracts, 02-prd-frd/03-ui-screen-inventory, mockups | `docker compose up` works; `make check` green; illegal state transitions rejected by tests; idempotent `POST /jobs` proven by test |
| **1b Source intake** | SSRF-safe URL validation, DNS pinning, ref → commit SHA resolution (`git ls-remote`, no checkout on control plane), source snapshot tarball + SHA-256, local content-addressed evidence store | FR-001, FR-002, FR-004, FR-032 | 03-low-level-design (intake, evidence key layout), 10-security/01 (TM entries for SSRF), 07-data-model | Malicious URL test suite (private IPs, metadata IP, `file://`, `ext::`, credentials in URL, redirects) rejected 100%; snapshot checksum stable across runs |
| **1c Sandbox execution** | Execution Service: disposable Docker worker per task, non-root, caps dropped, read-only root FS, PIDs/CPU/memory/time/output limits, network off during tests, dependency-fetch phase, strict result schema, guaranteed cleanup + orphan reaper; gVisor when available | FR-011, FR-012, FR-015, SEC-003, SEC-004, SEC-005, NFR-008 | 10-security/03-sandboxed-execution, 03-low-level-design (task contract, worker result), 09-testing-workflows/01 | Escape/egress tests pass (no metadata IP, no RFC1918, no Docker socket, read-only FS); workers destroyed on success, failure, timeout and cancel |
| **1d Results and live job** | Run existing pytest suites end-to-end, normalise to the six test statuses, flaky reruns in fresh workers, SSE live events, basic JSON + HTML report, UI: Live Job Execution, Functional Results, Jobs history wired to real data | FR-010, FR-017, FR-018, FR-044, FR-047 | 09-testing-workflows/01, 11-quality-gates-and-reporting/01, 08-api-contracts (SSE), mockups SCR-04, SCR-06 | A real public Python repo runs end-to-end from the UI; results match a local run; report downloads |

**Phase 1 demo:** paste a GitHub URL → commit pinned → tests run in a sandbox → live progress → results and report.

## Phase 2 — Analysis and security baseline

| Slice | Goal | Main requirements | Design files |
|---|---|---|---|
| **2a Security Quick profile** | Semgrep CE, Bandit, Gitleaks, OSV-Scanner in the sandbox; SARIF/JSON normalised into the finding schema; secret redaction; Security Center UI | FR-022, FR-023, FR-024, SEC-008 | 09-testing-workflows/02-security-testing, 11-quality/01 |
| **2b Evidence engine** | Fingerprinting, dedup, reproduction runs, Defect Confidence Score, triage workflow (false positive, accepted risk) with approvals | FR-033 to FR-037, HA-07, HA-08 | 11-quality/01-evidence-and-defect-analysis, 10-security/02 |
| **2c Model Gateway + first agents** | Provider-agnostic gateway (hosted API or local Ollama), redaction, token budgets, schema validation with one corrective retry; Requirements Analysis Agent and change-impact selection | FR-013, FR-014, FR-053, SEC-014, SEC-015, SEC-021 | 06-agent-design/01 and 02, 03-low-level-design (Model Gateway pipeline) |
| **2d Quality gates + release readiness** | QG-01…QG-08, verdict logic, release decision (HA-10), SARIF/JUnit export, Reports UI | FR-042, FR-043, FR-045, FR-046 | 11-quality/02-quality-gates-and-release-readiness, mockup SCR-14 |

## Phase 3 — MVP 1.0

| Slice | Goal | Main requirements | Design files |
|---|---|---|---|
| **3a API testing** | OpenAPI conformance and negative/property tests (Schemathesis) against an ephemeral target; authorization checks with two test identities | FR-019, FR-020, FR-021 | 09-testing-workflows/01 |
| **3b Performance Smoke/Baseline** | k6 in sandbox, approvals (HA-03), abort rules, baseline comparison, Performance Lab UI | FR-027, FR-029, SEC-017 | 09-testing-workflows/03 |
| **3c Mutation testing** | mutmut / Stryker on changed modules, valid score calculation, survived-mutant analysis | FR-030, FR-031 | 09-testing-workflows/04 |
| **3d Patch proposal + independent verification** | Patch Proposal Agent, deterministic patch validation, human review (HA-06), fresh-sandbox verification, never auto-commit | FR-038 to FR-041 | 09-testing-workflows/05 |
| **3e Integrations + hardening** | GitHub/GitLab webhooks and commit status, CI trigger (GitHub Actions, Jenkins), notifications (Slack/Teams), OIDC login and RBAC | FR-052, SEC-009, SEC-010 | 05-architecture/06-integrations, 10-security/02 |

## How to run each slice

1. Create a branch: `git checkout -b phase-1a-boilerplate` (use the slice ID).
2. Start Claude Code in the repo root (`claude`).
3. Paste the slice prompt, or tell Claude Code: `Read @docs/build/prompts/PHASE_1A_BOILERPLATE.md and execute it.`
4. Let it finish; read `docs/build/phase-<id>-report.md`; run `make check` and `docker compose up` yourself.
5. Merge, then ask for the next slice's prompt.
