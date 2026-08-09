# Progressive Delivery And Change Control

## Purpose

Choose rollout mechanism, step size, readiness, promotion, stop, rollback, and irreversible-change controls from change risk.

## Use when

- progressive delivery
- canary deployment
- blue green deployment
- rollout strategy
- 점진적 배포
- 카나리 배포
- 블루그린 배포
- 롤아웃 전략

## Inputs

- The task goal, affected artifacts, users, owners, constraints, and lifecycle state
- Version and state compatibility matrix
- Executed readiness and rollback behavior for the target platform
- Promotion and stop metrics tied to user-visible risk

## Decision checks

- Classify blast radius, reversibility, state compatibility, dependency skew, and delayed failure modes.
- Choose rolling, canary, blue-green, feature control, or another mechanism from the actual boundary.
- Define step population, duration, readiness, health, business guardrails, promotion, and automatic or manual stop criteria.
- Name the last rollback-safe point and the roll-forward plan after irreversible state change.

## Required evidence

- Version and state compatibility matrix
- Executed readiness and rollback behavior for the target platform
- Promotion and stop metrics tied to user-visible risk

## Reject or stop when

- The rollout can expose incompatible versions or unreadable data.
- A canary has no representative traffic, duration, success criterion, or stop owner.

## Verification

- Rehearse a stopped rollout and rollback or roll-forward from a representative step.
- Confirm readiness prevents traffic before dependencies and migrations are safe.

## Counterexamples

- Do not call a single all-users deployment a canary.
- Do not use rollback when irreversible data changes require forward recovery.
