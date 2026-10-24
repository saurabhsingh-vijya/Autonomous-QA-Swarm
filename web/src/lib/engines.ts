/** What each engine-centred screen shows, and what it honestly does not. */
export const ENGINE_SCREENS = {
  security: {
    engines: ["secret_scan", "security_checks"],
    findingPrefix: "security",
    subtitle:
      "Security results persisted for one job: the secret-detection engine on the pinned snapshot and the read-only hygiene checks against an authorised target, plus the findings the Evidence Analysis Agent derived from them.",
    limits: [
      "secret_scan runs on every job with a security profile; values are stored masked.",
      "security_checks (headers, cookie flags, redirects, verbose errors) runs only against a registered target with an HA-01 authorisation or the dev-only local fixture target, and is informational, not an assessment.",
      "SAST, dependency and IaC scanners (slice 2a) and DAST (Deep profile, Phase 4 future) are not built; nothing is shown for them.",
    ],
  },
  performance: {
    engines: ["performance_probe"],
    findingPrefix: null,
    subtitle:
      "Performance results persisted for one job: the bounded closed-loop probe (p50/p95/p99, throughput, error rate) against an authorised target.",
    limits: [
      "performance_probe runs only with a performance profile and a registered target (HA-01) or the local fixture target; Baseline against a registered target needs HA-03, which is not built, so it is recorded as a warning.",
      "Load generation with k6, performance runs as an entity and GET /jobs/{id}/performance-runs arrive in slice 3b.",
    ],
  },
} as const;

export type EngineKind = keyof typeof ENGINE_SCREENS;
