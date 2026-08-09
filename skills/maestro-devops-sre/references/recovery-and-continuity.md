# Recovery And Continuity

## Purpose

Choose RTO, RPO, degradation, failover, restore, rebuild, rollback or roll-forward, backup isolation, sequencing, and rehearsal.

## Use when

- disaster recovery
- regional failover
- rto rpo
- backup restore
- continuity plan
- 재해 복구
- 리전 페일오버
- 리전 장애 복구
- 백업 복원
- 연속성 계획

## Inputs

- The task goal, affected artifacts, users, owners, constraints, and lifecycle state
- Current dependency and data inventory
- Backup, restore, failover, and recovery-time evidence
- Named incident and business decision owners

## Decision checks

- Define service and data recovery scope, RTO, RPO, allowed degradation, and dependency order.
- Map failure classes to failover, restore, rebuild, rollback, roll-forward, or manual reconciliation.
- Keep recovery credentials, metadata, and backups isolated from the primary failure domain.
- Specify restore order, data validation, traffic reintroduction, communication, and rehearsal cadence.

## Required evidence

- Current dependency and data inventory
- Backup, restore, failover, and recovery-time evidence
- Named incident and business decision owners

## Reject or stop when

- The same failure can destroy production and its only backup or recovery credentials.
- RTO or RPO is claimed without an executed representative recovery.

## Verification

- Perform a bounded restore or failover rehearsal and validate recovered data and service behavior.
- Measure achieved recovery time and data-loss window separately.

## Counterexamples

- Do not equate backup creation with successful restore.
- Do not fail over into a dependency or schema state that cannot serve the workload.
