# CLAUDE.md — Autonomous QA Swarm

Standing instructions for Claude Code in this repository. Read this file at the start of every session and follow it for every phase.

## What this project is

Autonomous QA Swarm is an open-source, self-hostable QA platform. Specialized AI agents, coordinated by a deterministic workflow engine, plan and run tests against a **pinned commit** of a repository inside **disposable sandboxes**, correlate evidence, propose fixes for human review and independently verify them.

Two principles override everything else:

1. **Agents propose, deterministic services dispose, humans approve.** Agents never execute code, never hold credentials, never change a repository. They emit typed proposals; the Policy Engine validates them; the Execution Service runs them in sandboxes.
2. **No evidence, no defect.** Nothing is reported as a confirmed defect without reproducible evidence captured by deterministic tooling.

## Source of truth

The design lives in `docs/design/` (Markdown, Mermaid diagrams) and `docs/design/mockups/` (UI concept PNGs). When code and design disagree, follow the design or stop and ask; do not silently invent a different design.

Use these names exactly as the design defines them: agent IDs `AG-01`…`AG-11`, job states, task states, test statuses, finding and patch statuses, verdicts, quality gates `QG-01`…`QG-08`, human approvals `HA-01`…`HA-12`, requirement IDs `FR-xxx`, `NFR-xxx`, `SEC-xxx`, `AC-xxx`, API paths under `/api/v1`, and the `qaswarm` / `qaswarm_exec` module names.

Key reference files:

| Topic | File |
|---|---|
| Layers, architecture decisions, deployment | `docs/design/05-architecture/02-high-level-design.md` |
| State machines, task contract, worker result schema, error codes | `docs/design/05-architecture/03-low-level-design.md` |
| Module structure (`qaswarm.*`, `qaswarm_exec.*`) | `docs/design/05-architecture/04-component-architecture.md` |
| Technology choices | `docs/design/05-architecture/05-technology-options.md` |
| Entities and integrity rules | `docs/design/07-data-model/01-data-model-and-erd.md` |
| API contracts, errors, idempotency, SSE | `docs/design/08-api-specifications/01-api-contracts.md` |
| Requirements and acceptance criteria | `docs/design/03-requirements/01-functional-requirements.md`, `02-non-functional-requirements.md` |
| Sandbox rules | `docs/design/10-security-and-threat-model/03-sandboxed-execution.md` |
| Phases and exit criteria | `docs/design/12-risks-and-roadmap/02-roadmap.md` and `docs/build/BUILD_PLAN.md` |

Read only the files relevant to the current task; do not load the whole design set at once.

## Stack (do not change without asking)

- Backend: Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.x, Alembic, PostgreSQL 16, `uv` for dependency management.
- Frontend: React 18 + TypeScript + Vite, Tailwind CSS, React Router, TanStack Query, Lucide icons.
- Tests: pytest (+ Hypothesis), Vitest + React Testing Library; Playwright later.
- Quality: ruff, mypy (strict for `qaswarm` domain/workflow code), eslint, prettier, pre-commit.
- Local run: Docker Compose. CI: GitHub Actions (a Jenkinsfile may be added later on request).

## Non-negotiable rules

- **The control plane never executes repository code** (SEC-001). No `git clone` + run, no `pip install` of target repos, no `subprocess` on repository content outside the sandbox execution service.
- **No secrets in code, logs, prompts, test fixtures or the database.** Secrets come from environment variables or the secrets broker; logs go through redaction.
- **No automatic commit, push or merge of user repositories** (FR-041). Patches are proposals only.
- **Never claim something works unless you ran it.** Report test, lint and build results exactly as they came out, including failures and anything you could not run.
- **Stay inside the current phase's scope.** If you see work that belongs to a later phase, note it in the phase report under "Deferred", do not build it.
- **Mark stubs honestly.** Anything not yet implemented returns `501 Not Implemented` with a problem+json body or is labelled "Not implemented in this phase" in the UI. Never return fabricated results.
- Demo or sample data in the UI must be visibly labelled: "Sample data — no repository code executed".

## Working method for every phase

1. Read the phase prompt and the listed design files.
2. Write a short plan to `docs/build/phase-<id>-plan.md` (files to create, decisions, risks). Then continue without waiting unless something is genuinely ambiguous or destructive.
3. Implement in small, reviewable steps. Commit after each coherent step on the phase branch with a clear message. Do not push unless asked.
4. Run all checks (`make check` once it exists): lint, type check, unit and integration tests, frontend build. Fix what you broke.
5. Write `docs/build/phase-<id>-report.md`: what was built, requirement IDs covered (fully or partially), commands to run, actual check results, known gaps, deferred items, and next-step suggestions.
6. Stop and summarise. Do not start the next phase on your own.

## Conventions

- IDs: ULIDs with prefixes (`org_`, `prj_`, `rep_`, `job_`, `tsk_`, `att_`, `aud_`, `evd_`, `fnd_`, `pch_`, `ver_`). Display IDs like `QJ-1042` are separate, human-friendly sequences.
- Times: UTC in storage and API (ISO 8601 with `Z`).
- API errors: RFC 9457 `application/problem+json` with an `error_code` field.
- Logging: structured JSON with `correlation_id`, `job_id`, `task_id` where relevant.
- Every state change goes through the state-machine module (illegal transitions raise) and writes an audit event.
