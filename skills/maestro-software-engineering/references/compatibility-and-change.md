# Compatibility And Change

## Purpose

Plan source, wire, semantic, and persisted compatibility with staged migration, deprecation, and recovery.

## Use when

- compatibility migration
- breaking change
- schema evolution
- parallel change
- deprecation
- 호환성 마이그레이션
- 브레이킹 체인지
- 스키마 진화
- 병렬 변경
- 지원 중단
- 단계적 마이그레이션

## Inputs

- The task goal, affected artifacts, users, owners, constraints, and lifecycle state
- Consumer and stored-data inventory tied to the current revision
- Before, mixed-version, and after states with executable or source evidence
- Owner-approved compatibility and support commitments

## Decision checks

- Inventory public, generated, persisted, event, operational, and undocumented-but-real consumers.
- Evaluate source, wire, semantic, and stored-data compatibility separately.
- State the versioning and deprecation contract; do not use a version number as compatibility proof.
- Use expand, migrate, and contract phases when consumers cannot move atomically.
- Define support windows, observability, rollback or roll-forward, and removal evidence.

## Required evidence

- Consumer and stored-data inventory tied to the current revision
- Before, mixed-version, and after states with executable or source evidence
- Owner-approved compatibility and support commitments

## Reject or stop when

- A public contract changes without an explicit compatibility decision.
- Removal is scheduled before consumer migration can be observed.
- Rollback would make newly written data unreadable.

## Verification

- Run compatibility checks across old, mixed, and new producer/consumer versions.
- Prove both forward recovery and the smallest safe disable or rollback path.

## Counterexamples

- Do not create a major version for an internal refactor with no public contract change.
- Do not keep dual paths indefinitely without an owner and removal condition.
