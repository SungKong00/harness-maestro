---
name: maestro-devops-sre
description: Use when a Maestro route selects the devops-sre Expertise Pack for service objectives, telemetry architecture, progressive delivery, recovery and continuity, capacity and overload, or production readiness. It advises operational design without replacing rollback-observability review, QA release evidence, platform execution, incident authority, or final verification.
---

# Maestro DevOps SRE

Apply only the Decision Guides selected by Maestro. This Pack supplies
decision criteria; it is not a permanent specialist, implementation owner,
policy authority, or final verifier.

<!-- MAESTRO:EXPERTISE-AUTHORITY:BEGIN -->
This Pack never grants repository or external write authority. In a read-only
Assignment it returns advisory criteria only. When a validated Maestro plan already
grants mutation authority to the owning Executor, that Executor may apply the
selected Guide criteria while implementing within its Assignment boundaries.
The Pack does not expand those boundaries or authorize another writer.
<!-- MAESTRO:EXPERTISE-AUTHORITY:END -->

## Inputs

Require the task goal, affected surface, current architecture and state,
public or operational contracts, owners, constraints, failure and recovery
expectations, compatibility boundary, and available executable evidence.
Unknown facts and unrun checks remain unknown.

## Guide loading

Load only route-selected guides:

- `service-objectives-and-error-budgets` → `references/service-objectives-and-error-budgets.md`
- `telemetry-architecture` → `references/telemetry-architecture.md`
- `progressive-delivery-and-change-control` → `references/progressive-delivery-and-change-control.md`
- `recovery-and-continuity` → `references/recovery-and-continuity.md`
- `capacity-and-overload` → `references/capacity-and-overload.md`
- `production-readiness-and-ownership` → `references/production-readiness-and-ownership.md`

Do not open all guides by default. Maestro selects at most four.

## Relationship to other components

- Expertise Pack: supplies the selected decision procedure.
- Lens: independently checks cross-task failure and evidence boundaries.
- Executor: may implement only when a validated Maestro Assignment already grants it.
- Verifier: checks actual artifacts, commands, and completion claims.

## Research gate

Reuse stable and versioned criteria by default. Open bounded
`$maestro-reference-research` only when current platform, vendor, standard,
incident, compatibility, regulation, or implementation behavior can change
the decision.

## Advisory sequence

1. Frame the decision, owners, constraints, and explicit non-goals.
2. Load only the selected Guides and gather their required evidence.
3. Compare alternatives by declared behavior, failure, compatibility, and recovery.
4. Stop on missing authority, unsafe ambiguity, or an open irreversible decision.
5. Hand implementation to the authorized Executor and proof to the Verifier.

## Completion contract

```text
decision_scope:
selected_guides:
constraints_and_owners:
alternatives_and_tradeoffs:
required_evidence:
chosen_criteria:
failure_and_recovery:
compatibility:
known_gaps:
research_artifact:
verdict:
```

## Boundaries

- Application-level code architecture or transaction design
- Regression selection and release-quality proof
- Executing deployments, incidents, failovers, or external changes
- Do not claim unrun checks passed or that advisory criteria prove production behavior.
- Do not expand paths, permissions, external authority, or the number of writers.
