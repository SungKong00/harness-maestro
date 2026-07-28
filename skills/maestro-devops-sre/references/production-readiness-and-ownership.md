# Production Readiness And Ownership

## Purpose

Assemble service objectives, telemetry, delivery, recovery, capacity, dependencies, runbooks, ownership, toil, and lifecycle into a risk-scaled readiness handoff.

## Use when

- production readiness design
- production readiness review
- operational readiness design
- production launch checklist
- runbook ownership
- 프로덕션 준비 설계
- 프로덕션 준비 검토
- 운영 준비 설계
- 프로덕션 출시 체크리스트
- 런북 소유권

## Inputs

- The task goal, affected artifacts, users, owners, constraints, and lifecycle state
- Revision-bound readiness artifacts and owners
- Representative runbook, dashboard, alert, rollback, restore, and scaling evidence

## Decision checks

- Collect rather than re-decide the selected SLO, telemetry, rollout, recovery, and capacity contracts.
- Expose dependency, version-skew, access, break-glass, support, and escalation assumptions.
- Name operator, service, incident, data, security, and decision owners plus troubleshooting entry points.
- Record manual toil, maintenance, decommission, open gaps, waivers, and review conditions.

## Required evidence

- Revision-bound readiness artifacts and owners
- Representative runbook, dashboard, alert, rollback, restore, and scaling evidence

## Reject or stop when

- A critical gap has neither remediation nor an explicit owner decision.
- Readiness is declared from a document with no executed operational evidence.

## Verification

- Walk through one detection-to-recovery scenario with the named owner and artifacts.
- Verify every dependency and waiver has a lifecycle and escalation path.

## Counterexamples

- Do not turn readiness review into duplicate QA release approval.
- Do not require enterprise process for a non-production disposable experiment.
