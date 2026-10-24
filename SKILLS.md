# RaOne — skills catalogue

What RaOne can do today, what each agent is allowed to do, and the developer skills needed to work
on the repository. Everything in the "Status" columns reflects the current build, not the roadmap.
The authoritative, machine-readable version of the agent table is `GET /api/v1/system/agents`
(source: `backend/src/qaswarm/agents/registry.py`).

Two principles bound every skill: agents propose, deterministic services dispose, humans approve;
and no evidence, no defect.

## 1. Agent skills

| Agent | Skill | Inputs it works from | Produces | Kind | Status |
|---|---|---|---|---|---|
| AG-01 Orchestrator | Admit a job, build and validate the plan DAG, enqueue tasks with hard/soft dependencies, dispatch leased tasks, reconcile job state, cancel, hold for plan approval (HA-05) | Job inputs and profiles | `JobPlan`, `Task` rows, job state transitions, audit events | Deterministic | Implemented |
| AG-02 Requirements Analysis | Turn requirement texts and API checks into traceable scenarios with stable ids, priorities (P0/P1/P2) and oracles; flag gaps | `inputs.requirements`, `inputs.api_checks` | `requirements_analysis` output (requirements, scenarios, gaps) | Deterministic; optional local LLM (Ollama) may add proposals, which are validated or dropped | Implemented |
| AG-03 Functional Testing | Record every functional/manual scenario; cannot execute anything yet | Scenarios from AG-02 | `TestExecution` rows with status `skipped` and the reason | Deterministic | Implemented (skips honestly; execution engine is slice 1c) |
| AG-04 API Testing | Run HTTP checks with safe methods (GET/HEAD/OPTIONS) against allow-listed local hosts; block everything else with the policy reason | `inputs.api_checks` | `TestExecution` (passed/failed/blocked/timed_out/infrastructure_error), redacted `http_exchange` evidence | Deterministic | Implemented |
| AG-05 Security Testing | — | — | — | Deterministic + LLM | Planned, slice 2a |
| AG-06 Performance Testing | — | — | — | Deterministic + LLM | Planned, slice 3b |
| AG-07 Mutation Testing | — | — | — | Deterministic + LLM | Planned, slice 3c |
| AG-08 Evidence and Defect Analysis | Group failures by fingerprint, score with the Defect Confidence Score (DCS), separate verified facts from inferences | Executions and evidence from AG-03/AG-04 | `Finding` rows (candidate; probable at most without reproduction) | Deterministic | Implemented |
| AG-09 Patch Proposal | — | — | — | LLM-assisted | Planned, slice 3d |
| AG-10 Independent Verification | — | — | — | Deterministic + LLM | Planned, slice 3d |
| AG-11 QA Report | Aggregate persisted records, evaluate quality gates QG-01…QG-08, compute the verdict, write a labelled deterministic narrative | All upstream outputs | `Report` (json/html), gate results | Deterministic | Implemented (QG-05/06/07 report `not_applicable`) |

### What no agent may do

- Execute repository code, fetch or clone repositories (SEC-001).
- Hold credentials or read secrets.
- Change, commit, push or merge a user repository (FR-041).
- Report a test as passed unless deterministic tooling observed it.
- Present a deterministic output as an LLM result, or vice versa (`AgentOutput.adapter` and
  `agent_kind` are stored per output).

### LLM configuration

Default `AQS_LLM_PROVIDER=none`: all agents deterministic. `AQS_LLM_PROVIDER=ollama` enables a local
Ollama adapter (timeouts, rate limit and malformed-output handling built in) used only by AG-02 for
extra scenario proposals. Hosted providers are not supported. See `.env.example`.

## 2. Platform skills (what a user can do in this build)

| Skill | Where | Status |
|---|---|---|
| Register projects and repositories (syntactic URL validation) | Repositories & Projects screen, `/api/v1/projects`, `/api/v1/repositories` | Implemented |
| Create a QA job with requirements and API checks, optionally requiring plan approval | New QA Job screen, `POST /api/v1/jobs` | Implemented |
| Approve or reject a plan (QA Lead) | Job detail, `POST /api/v1/jobs/{id}/plan/approval` | Implemented |
| Follow a job live (state, tasks, attempts, outputs, events) | Live Job Execution screen, SSE `/jobs/{id}/events` | Implemented |
| Cancel a running job | Job detail, `POST /api/v1/jobs/{id}/cancel` | Implemented |
| Inspect executions, evidence, findings with DCS breakdown | Results and defect screens, `/test-executions`, `/evidence`, `/findings` | Implemented |
| Read quality gates, verdict and report (JSON/HTML) | Reports screen, `/quality-gates`, `/report` | Implemented |
| Source intake (SSRF-safe validation, ref pinning, snapshot) | — | Slice 1b |
| Sandboxed execution of repository tests | — | Slice 1c |
| Security, performance, mutation testing; patches; verification; release decision | `501 Not Implemented` with `planned_slice` | Later slices |

## 3. Developer skills and commands

| Need | Command |
|---|---|
| Start PostgreSQL | `make up` (Docker Compose) |
| Migrate / seed | `make migrate`, `make seed` |
| Run API and web dev servers | `make dev-api`, `make dev-web` |
| Lint, type check, tests, build | `make check` (or `make lint`, `make typecheck`, `make test`, `make build`) |
| Backend tests only | `cd backend && uv run python -m pytest -q` (set `AQS_TEST_DATABASE_URL` for integration tests) |
| Format | `make fmt` |

Expected skills for contributors: Python 3.12 with FastAPI, Pydantic v2 and SQLAlchemy 2;
PostgreSQL and Alembic migrations; React 18 with TypeScript, Tailwind and TanStack Query; pytest and
Vitest. Follow `CLAUDE.md` for the rules that apply to every change.
