# References

> Autonomous QA Swarm · Documentation v0.1 (Concept) · Status: Proposed — nothing described here is implemented yet.

This document lists the external standards, guidance and tools referred to in the Autonomous QA Swarm documentation set. Referencing a standard does not mean the platform complies with it or has been assessed against it; the standards are used as vocabulary, taxonomies, data formats and design guidance for a platform that has not yet been built. Tools are candidates listed in [Technology options](../05-architecture/05-technology-options.md), not adopted dependencies.

## Note on versions and licences

Versions, licence terms and URLs listed here were recorded at concept stage (October 2026) and **must be re-verified at adoption time**. Open-source projects change licences, rule packs carry their own terms (for example the Semgrep registry rules), hosted services change terms of use, and standards publish new editions. Before any tool is bundled, its current licence must be checked against the project licence decision (DEC-01 in [Risks, limitations and decisions](../12-risks-and-roadmap/01-risks-limitations-and-decisions.md)) and recorded in the platform SBOM. Licences shown below are as understood at concept stage and are indicative only.

## Security standards and guidance

| Reference | Used for | URL |
|---|---|---|
| OWASP Top 10 | Web application risk categories in security reporting | https://owasp.org/www-project-top-ten/ |
| OWASP API Security Top 10 | API risk categories, including object-level authorization (BOLA) | https://owasp.org/www-project-api-security/ |
| OWASP ASVS | Verification requirements that can inform security scenarios | https://owasp.org/www-project-application-security-verification-standard/ |
| OWASP Top 10 for LLM Applications | Threats to the agent layer, such as prompt injection | https://genai.owasp.org/ |
| CWE (MITRE) | Weakness identifiers in findings and fingerprints | https://cwe.mitre.org/ |
| CVE | Identifiers for known vulnerabilities in dependency findings | https://www.cve.org/ |
| CVSS (FIRST) | Base scores mapped to platform severity | https://www.first.org/cvss/ |
| NIST SP 800-218 SSDF | Secure development practices for the platform itself | https://csrc.nist.gov/pubs/sp/800/218/final |
| NIST SP 800-115 | Guidance on planning bounded, authorized security testing | https://csrc.nist.gov/pubs/sp/800/115/final |
| SLSA | Supply-chain integrity levels for platform releases and worker images | https://slsa.dev/ |
| CycloneDX | SBOM format for platform and worker images | https://cyclonedx.org/ |
| SPDX | SBOM and licence identifier format | https://spdx.dev/ |

## Quality, testing and accessibility standards

| Reference | Used for | URL |
|---|---|---|
| ISO/IEC 25010 | Product quality model behind the non-functional requirements | https://www.iso.org/ |
| ISO/IEC/IEEE 29119 | Software testing processes and terminology | https://www.iso.org/ |
| ISTQB Glossary | Standard testing terms used in the glossary | https://glossary.istqb.org/ |
| WCAG 2.2 | Accessibility target (AA) for the Web UI (NFR-012) | https://www.w3.org/TR/WCAG22/ |

ISO standards are listed by catalogue name; search the ISO site for the current edition.

## Interface and data-format specifications

| Reference | Used for | URL |
|---|---|---|
| RFC 9457 Problem Details for HTTP APIs | Error responses (`application/problem+json`) | https://www.rfc-editor.org/rfc/rfc9457 |
| RFC 6585 Additional HTTP Status Codes | HTTP 429 Too Many Requests for rate limiting | https://www.rfc-editor.org/rfc/rfc6585 |
| OpenAPI Specification 3.1 | API contracts and schema-driven API testing | https://spec.openapis.org/oas/v3.1.0 |
| SARIF 2.1.0 (OASIS) | Scanner output normalization and SARIF export | https://docs.oasis-open.org/sarif/sarif/v2.1.0/sarif-v2.1.0.html |
| JUnit XML | Test result import and export; a de facto format without a single normative specification | https://junit.org/ |
| OpenTelemetry | Traces, metrics and logs with correlation IDs (NFR-014) | https://opentelemetry.io/ |

## Tools: platform foundations

| Tool | Proposed role | Licence (as recorded) | URL |
|---|---|---|---|
| Python | Backend language (3.12) | PSF License | https://www.python.org/ |
| FastAPI | API framework | MIT | https://fastapi.tiangolo.com/ |
| Pydantic | Schema validation of contracts and outputs | MIT | https://docs.pydantic.dev/ |
| PostgreSQL | Metadata DB and MVP task queue (16+) | PostgreSQL License | https://www.postgresql.org/ |
| Temporal | Future workflow engine option | MIT | https://temporal.io/ |
| Ceph (RGW) | S3-compatible object storage option | LGPL-2.1/LGPL-3.0 (mixed) | https://ceph.io/ |
| SeaweedFS | S3-compatible object storage option | Apache-2.0 | https://github.com/seaweedfs/seaweedfs |
| MinIO | S3-compatible object storage option | AGPL-3.0 | https://min.io/ |
| React | Web UI framework | MIT | https://react.dev/ |
| TypeScript | Web UI language | Apache-2.0 | https://www.typescriptlang.org/ |
| Vite | Web UI build tool | MIT | https://vite.dev/ |
| Keycloak | OIDC identity provider | Apache-2.0 | https://www.keycloak.org/ |
| OpenBao | Secrets Broker backend | MPL-2.0 | https://openbao.org/ |
| HashiCorp Vault | Secrets Broker backend alternative | BUSL-1.1 (not OSI open source) | https://www.vaultproject.io/ |
| Open Policy Agent | Policy Engine (Rego) | Apache-2.0 | https://www.openpolicyagent.org/ |

## Tools: isolation, observability and models

| Tool | Proposed role | Licence (as recorded) | URL |
|---|---|---|---|
| Docker | Container runtime (rootless) | Apache-2.0 (Moby/Engine); Docker Desktop has commercial terms | https://www.docker.com/ |
| Podman | Container runtime (rootless) | Apache-2.0 | https://podman.io/ |
| gVisor | MVP sandbox isolation (`runsc`) | Apache-2.0 | https://gvisor.dev/ |
| Firecracker | Future microVM isolation | Apache-2.0 | https://firecracker-microvm.github.io/ |
| Kata Containers | Future microVM isolation alternative | Apache-2.0 | https://katacontainers.io/ |
| Prometheus | Metrics | Apache-2.0 | https://prometheus.io/ |
| Grafana | Dashboards | AGPL-3.0 | https://grafana.com/ |
| Loki | Log store option | AGPL-3.0 | https://grafana.com/oss/loki/ |
| OpenSearch | Log store option | Apache-2.0 | https://opensearch.org/ |
| Ollama | Local model serving | MIT | https://ollama.com/ |
| vLLM | Local model serving | Apache-2.0 | https://github.com/vllm-project/vllm |

## Tools: testing

| Tool | Proposed role | Licence (as recorded) | URL |
|---|---|---|---|
| pytest | Python test runner | MIT | https://pytest.org/ |
| Hypothesis | Property-based testing for Python | MPL-2.0 | https://hypothesis.works/ |
| Jest | JavaScript test runner | MIT | https://jestjs.io/ |
| Vitest | JavaScript/TypeScript test runner | MIT | https://vitest.dev/ |
| Playwright | UI/E2E testing, screenshots and traces | Apache-2.0 | https://playwright.dev/ |
| JUnit | Java test framework (Phase 4 language support) | EPL-2.0 | https://junit.org/ |
| Schemathesis | OpenAPI schema and property-based API testing | MIT | https://github.com/schemathesis/schemathesis |
| REST Assured | Optional Java API testing | Apache-2.0 | https://rest-assured.io/ |

## Tools: security, performance and mutation

| Tool | Proposed role | Licence (as recorded) | URL |
|---|---|---|---|
| Semgrep CE | SAST | LGPL-2.1 engine; registry rules under Semgrep Rules License | https://semgrep.dev/ |
| Bandit | Python security linter | Apache-2.0 | https://github.com/PyCQA/bandit |
| Gitleaks | Secret detection | MIT | https://github.com/gitleaks/gitleaks |
| OSV-Scanner | Dependency vulnerability scanning | Apache-2.0 | https://github.com/google/osv-scanner |
| Trivy | Container image and IaC/config scanning | Apache-2.0 | https://github.com/aquasecurity/trivy |
| Checkov | IaC/config scanning | Apache-2.0 | https://www.checkov.io/ |
| OWASP ZAP | DAST (Deep profile, Future — Phase 4) | Apache-2.0 | https://www.zaproxy.org/ |
| k6 | Default load generator, run as a separate process | AGPL-3.0 | https://k6.io/ |
| Locust | Alternative load generator | MIT | https://locust.io/ |
| mutmut | Python mutation testing | BSD-3 | https://github.com/boxed/mutmut |
| Stryker | JS/TS, C# and Scala mutation testing | Apache-2.0 | https://stryker-mutator.io/ |
| PIT | Java mutation testing | Apache-2.0 | https://pitest.org/ |

## Related documents

- [Glossary](01-glossary.md)
- [Technology options](../05-architecture/05-technology-options.md)
- [Security architecture and threat model](../10-security-and-threat-model/01-security-architecture-and-threat-model.md)
