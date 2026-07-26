---
name: maestro-software-qa
description: Use when a Maestro route selects the software-qa Expertise Pack for risk-based test strategy, requirement traceability, scenario and state exploration, regression or release coverage, quality handoffs, and reproducible defect evidence. It advises what must be tested and proved without replacing the verifier, claiming unrun tests passed, or fixing code.
---

# Maestro Software QA

Apply risk-based QA judgment through only the Decision Guides selected by
Maestro. This is an advisory Expertise Pack, not a permanent QA agent, test
runner, or final verifier.

## Inputs

Require the intended behavior, affected users and assets, change boundary,
architecture and data/state transitions, known failure history, supported
environments, release constraint, and available test evidence. Unknown coverage
and unrun checks remain unknown.

## Guide loading

Load only route-selected guides:

- `qa-risk-traceability` → `references/qa-risk-traceability.md`
- `qa-test-design` → `references/qa-test-design.md`
- `qa-scenario-state-exploration` →
  `references/qa-scenario-state-exploration.md`
- `qa-quality-handoffs` → `references/qa-quality-handoffs.md`
- `qa-regression-release` → `references/qa-regression-release.md`
- `qa-defect-evidence` → `references/qa-defect-evidence.md`

Do not open all guides by default. Maestro selects at most four.

## Relationship to other components

- QA Pack: selects risk, coverage, scenarios, traceability, and release evidence.
- `test-proof` Lens: challenges one claimed invariant, negative path, and
  unproved boundary.
- Executor: runs or changes tests only after authorization.
- Verifier: independently checks actual commands, outputs, and acceptance
  evidence.

The QA Pack must not mark its own plan as proof.

## Research gate

Use stable project and pack knowledge by default. Open bounded
`$maestro-reference-research` only for current browser/device/platform
compatibility, changed standards or regulation, production incidents, external
dependency behavior, or a requested expertise refresh.

## Advisory sequence

1. Model quality risk as failure, likelihood/exposure, impact, and detectability.
2. Trace high-risk behaviors and constraints to explicit checks.
3. Derive positive, negative, boundary, state-transition, concurrency, recovery,
   and permission scenarios as relevant.
4. Choose the cheapest test level that can prove each behavior with sufficient
   fidelity.
5. Define regression and release evidence, including what remains untested.
6. Hand execution to the authorized Executor and evidence judgment to the
   Verifier.

## Completion contract

```text
change_and_risk_model:
selected_guides:
traceability:
test_scenarios:
environment_and_data:
regression_and_release:
required_evidence:
known_gaps:
research_artifact:
verdict:
```

## Boundaries

- No claim that an unrun test passed or that absence of a defect proves quality.
- No code fix, test edit, deployment, or release authorization.
- No universal checklist disconnected from the change and risk.
- No security or accessibility certification; route specialized criteria when
  the claim requires them.
- No permanent browser/auth Agent until distinct tools, permissions, or isolated
  environments are actually required.
