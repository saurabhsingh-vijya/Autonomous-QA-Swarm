# Safe-Use Policies

> Autonomous QA Swarm · Documentation v0.1 (Concept) · Status: Proposed — nothing described here is implemented yet.

Autonomous QA Swarm is proposed to include security scanning and load generation, capabilities that can harm systems and people if misused. This document sets out the rules of engagement and usage policies the platform is designed to enforce and that operators and users are expected to follow. Where a policy can be enforced technically, the enforcing control is named; where it cannot, the policy relies on human attestation and audit, and that limit is stated. All enforcement mechanisms are **Proposed** or **Planned (MVP)** unless marked **Future**; none is **Implemented / Verified**. These policies complement [Security architecture and threat model](01-security-architecture-and-threat-model.md), in particular TM-25 and TM-26, and the workflows in [Security testing](../09-testing-workflows/02-security-testing.md) and [Performance testing](../09-testing-workflows/03-performance-testing.md).

## Rules of engagement for security testing

### Authorization attestation

No active traffic leaves a sandbox toward a target until that target is registered and its authorization is attested under HA-01 by an Org Admin or Security Reviewer (SEC-016). The attestation is recorded as a `TargetAuthorization` and states who owns the system, who granted permission, the scope, the time window and the permitted test types. An illustrative attestation record:

```yaml
target: payments-api-staging        # sample target, Northwind Fintech (sample org)
environment_class: non-production
owner: Northwind Payments Engineering (sample)
authorized_by: Head of Platform Security (sample)
attested_by_role: Security Reviewer
scope:
  base_urls: ["https://staging.payments.northwind.example"]
  addresses: ["10.20.4.0/28"]
  excluded_paths: ["/admin/*", "/v1/payouts/execute"]
permitted_test_types: [api_negative, authz_checks, dast_passive, dast_active]
window:
  valid_from: 2026-10-24T00:00:00Z
  valid_until: 2026-11-30T23:59:59Z
  allowed_hours_utc: "08:00-18:00"
```

The platform records and audits the attestation but cannot verify legal authority; an attester who lies is responsible for that misuse, and the record makes it attributable.

### Scope and time windows

- Requests are permitted only to the attested base URLs and addresses; the target egress gateway drops everything else.
- Excluded paths are removed from crawler and scanner configuration and also enforced at the gateway.
- Jobs scheduled outside `allowed_hours_utc` or after `valid_until` end `blocked` before any execution.
- DAST (Deep profile) additionally requires HA-02 by a Security Reviewer and, because the plan approval gate defaults on for Deep, HA-05 by a QA Lead. DAST runs are bounded to 60 minutes.
- DAST (Deep profile) is **Future** (Phase 4) for every target type; in the MVP, the only active checks are the Standard profile's API authorization checks, and they run only against ephemeral in-sandbox targets.

### Non-destructive defaults

The platform's default is to observe and prove, never to damage (SEC-018).

- Passive rules run first; active rules run only after passive completes and only if HA-02 covers active testing.
- Rule categories that are inherently destructive (for example, mass deletion, account lockout, persistent stored payload injection into shared data) are disabled by default and cannot be enabled for external targets.
- API negative tests use synthetic accounts created for the job; they do not modify or delete objects they did not create.
- Request rates during security tests are capped per target, separate from performance profiles.

### No exploitation beyond proof of reachability

A finding is confirmed by demonstrating the precondition, not by exploiting it. For the sample finding FND-0193 (IDOR on `GET /v1/accounts/{account_id}/statements`, illustrative), proof means one synthetic user retrieving a statement belonging to a second synthetic user created by the same job, three times in fresh sandboxes. It does not mean enumerating real accounts, downloading data at scale, pivoting to other systems or chaining further vulnerabilities. Payloads that would establish persistence, escalate on the host or exfiltrate data are not included in any profile.

### No social engineering and no third-party targets

- The platform does not send phishing messages, impersonate users, call people or interact with humans as part of testing.
- Third-party services the application integrates with (payment processors, identity providers, email services, SaaS APIs) are never targets. In-sandbox targets are expected to use stubs or vendor-provided sandboxes; external targets must exclude third-party endpoints in their scope.
- Public internet hosts not owned by the attesting organization cannot be registered as targets; registration of well-known third-party domains is planned to be refused by a deny-list.

## Performance testing safety

Load generation can degrade or take down a system. Performance profiles are therefore bounded and approval-gated (SEC-017).

| Profile | Workload cap | Duration cap | Approval | MVP status |
|---|---|---|---|---|
| Smoke | 5 VUs | 1 min | None for ephemeral target | Planned (MVP) |
| Baseline | 20 VUs | 5 min | HA-03 | Planned (MVP) |
| Load | ≤ 100 VUs or ≤ 200 req/s | 15 min | HA-03 | Future |
| Stress | ramp to ≤ 500 VUs | 20 min | HA-03 + HA-05 | Future |
| Spike | burst to ≤ 300 VUs for ≤ 60 s | 5 min | HA-03 + HA-05 | Future |
| Soak | ≤ 50 VUs | 2 h | HA-03 + HA-05 | Future |

Any profile against an external (non-ephemeral) target requires HA-03 by a QA Lead, even Smoke.

### Automatic abort rules

The load generator supervisor stops the run immediately when any of these conditions is met:

| Condition | Action |
|---|---|
| Error rate > 20% for 60 s | Abort; run marked aborted with reason |
| Target health check fails 3 times consecutively | Abort; target owner notified |
| p95 > 5 × baseline for 2 min | Abort; results kept as partial |
| Generator CPU > 90% | Run marked invalid (generator-bound) |

### Production and coordination

- Production targets are not permitted by default. A production run would require a separately registered target with an explicit, authorized test plan agreed with the system owner, a named contact on call during the window, and the target classified as production in its attestation. Production targets are not supported in the MVP.
- Shared non-production environments should be coordinated with their owners: the attestation names a contact, and the Notification Service is planned to notify that contact when an approved run starts and ends.
- Rate caps apply to the whole job, so parallel tasks cannot add up to more than the approved profile.

## Data handling

- **No real customer data in sandboxes.** Repositories, fixtures and in-sandbox targets must use synthetic test data. Operators must not load production database dumps into ephemeral targets.
- **Synthetic identities.** Target test users are generated per job or supplied as dedicated non-production test identities through the Secrets Broker; they must not be real people's accounts.
- **Secrets.** Real credentials are never placed in repositories under test, task contracts or prompts. Secret-detection findings report location and rule, never the value. Credentials that a scan discovers in a repository should be rotated by the owner, because they must be presumed exposed.
- **Personal data in evidence.** If personal data is found in evidence anyway, the evidence can be deleted early by a QA Lead, and the event is audited.
- **Model providers.** Projects that handle sensitive code should be restricted to local models through the Model Gateway (SEC-021). Details are in [Identity, secrets, audit and data protection](02-identity-secrets-audit-and-data-protection.md).

## Responsible disclosure for third-party issues

Dependency scanning (OSV-Scanner) and SAST can surface vulnerabilities in third-party packages rather than in the user's code. When a scan or reachability analysis suggests a previously unknown vulnerability in an open-source dependency:

1. Do not publish details in public issue trackers, chat channels or reports shared outside the organization.
2. Check whether the issue is already known (OSV, GitHub Security Advisories, vendor advisories).
3. Report privately through the project's documented security policy (for example `SECURITY.md` or a private vulnerability reporting channel).
4. Allow a reasonable disclosure window agreed with the maintainers, commonly 90 days.
5. Record the disclosure reference against the finding; an accepted risk (HA-08) with expiry can track the exposure until a fixed version is available.

Vulnerabilities found in Autonomous QA Swarm itself are planned to be reported through the project's own `SECURITY.md`, with a private reporting channel and a coordinated disclosure process.

## AI usage policy

- **Human review gates.** Agent output is a proposal. Generated tests require review before promotion (FR-016); patches require HA-06; release decisions require HA-10. No LLM output can satisfy an approval.
- **No autonomous code changes.** The platform never commits, pushes or merges (FR-041). Pull request export is **Future** under HA-12 and still requires a code owner.
- **Evidence before claims.** No finding is reported as Confirmed without reproducible deterministic evidence; LLM judgement alone can never lift a finding to Confirmed.
- **Model provider selection.** Org Admins choose providers from an allow-list; per-project restriction to local models is available; provider and model identifier are recorded per call.
- **Budgets.** Per-job token and compute budgets are enforced (NFR-015) so that a misbehaving agent cannot run up unbounded cost.
- **Transparency.** Reports label AI-generated narrative, generated tests and patch rationale as such, separately from deterministic results.

## Acceptable use and prohibited uses

Autonomous QA Swarm is proposed as open-source software under Apache-2.0 (DEC-01 still open). The licence does not restrict use, but the project is proposed to publish an acceptable-use statement and to design the software so that the following uses are hard rather than easy.

| Acceptable | Prohibited |
|---|---|
| Testing repositories you own or are authorized to test | Scanning or load-testing systems without the owner's permission |
| Active security checks against registered non-production targets within scope | Using DAST or load profiles as an attack or denial-of-service tool |
| Performance testing within approved profiles | Disabling safety limits, abort rules or approval gates to exceed caps |
| Using synthetic data and test identities | Processing real customer personal data in sandboxes |
| Proposing fixes for human review | Deploying agent patches without human review |
| Private disclosure of third-party vulnerabilities | Publishing or weaponizing discovered vulnerabilities |
| Self-hosting with local models for sensitive code | Using the platform to exfiltrate code from repositories you are not authorized to access |

Forks can remove safeguards; the project cannot prevent that. Official releases are planned to ship with the safeguards enabled by default and to document that disabling them transfers responsibility to the operator.

## Policy enforcement summary

| Policy | Enforced by | Failure behavior |
|---|---|---|
| Target must be authorized (HA-01) | Policy Engine, Target Environment Manager | Job ends `blocked`; no traffic sent |
| Active checks need HA-02 | Policy Engine | Active tasks `skipped`; passive only, noted in report |
| Scope and excluded paths | Target egress gateway, scanner config | Out-of-scope requests dropped and audited |
| Time window | Policy Engine at validation, scheduling and task start | Job `blocked` if the window is closed at validation; running target tasks `cancelled` at window end and the job finishes `completed_with_warnings` |
| Performance caps and approvals (HA-03, HA-05) | Policy Engine, load generator supervisor | Plan rejected or job awaits approval |
| Abort rules | Load generator supervisor | Run aborted; partial results kept and flagged |
| Network off during execution | Execution Service, host firewall | Connections fail inside sandbox |
| Allow-list changes need HA-04 | Settings API, Policy Engine | Request refused with `403` |
| No credentials to agents or prompts | Secrets Broker scoping, Model Gateway redaction | Prompt refused if a known secret is detected |
| Generated tests reviewed before promotion | Workflow Engine | Unreviewed tests not run in CI |
| No automatic commit, push or merge | No such task type exists for any agent | Proposal rejected by schema |
| Overrides need reason (HA-07, HA-08, HA-09) | API validation, audit | Request rejected with `422` |
| Synthetic data only | Operator policy, secret detection | Not technically enforceable; findings raised if detected |
| Responsible disclosure | Operator policy | Not technically enforceable; relies on people |

Where the final column says a policy is not technically enforceable, the platform is limited to detection and audit. Those gaps are recorded as residual risk in [Risks, limitations and decisions](../12-risks-and-roadmap/01-risks-limitations-and-decisions.md).
