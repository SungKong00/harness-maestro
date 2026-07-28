# Backfill And Historical Correction

## Purpose

Plan interval or partition scope, reprocessing mode, deterministic output, concurrency, ordering, dry run, self-check, and publication for historical correction.

## Use when

- data backfill
- backfill
- historical correction
- data reprocessing
- partition rerun
- 데이터 백필
- 백필
- 과거 데이터 정정
- 데이터 재처리
- 파티션 재실행
- 파티션 백필

## Inputs

- The task goal, affected artifacts, users, owners, constraints, and lifecycle state
- Affected partitions and downstream dependency graph
- Representative dry-run diff, resource estimate, and reconciliation rule

## Decision checks

- Bind the correction to explicit intervals, partitions, input versions, code, schema, and target datasets.
- Define reprocess eligibility, ordering, concurrency, throttling, isolation, and interaction with live pipelines.
- Require deterministic or intentionally versioned output and idempotent replacement behavior.
- Provide dry run, self-check, reconciliation, staged publication, abort, and cleanup.

## Required evidence

- Affected partitions and downstream dependency graph
- Representative dry-run diff, resource estimate, and reconciliation rule

## Reject or stop when

- The job reads wall-clock latest data instead of the intended historical interval.
- Backfill can overwrite live output without isolation, reconciliation, or abort ownership.

## Verification

- Run a bounded partition twice and compare deterministic or versioned results.
- Validate downstream impact and publish only after reconciliation passes.

## Counterexamples

- Do not use backfill to hide an unresolved schema or semantic migration.
- Do not treat crash recovery from a checkpoint as intentional historical correction.
