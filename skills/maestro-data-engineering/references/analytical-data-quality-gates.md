# Analytical Data Quality Gates

## Purpose

Define fitness-for-purpose dimensions, metrics, measurements, thresholds, warn or block severity, quarantine, and quality ownership.

## Use when

- analytical data quality
- data quality gate
- dataset assertion
- dataset quality metric
- 분석 데이터 품질
- 데이터 품질 게이트
- 데이터셋 assertion
- 데이터 품질 메트릭

## Inputs

- The task goal, affected artifacts, users, owners, constraints, and lifecycle state
- Consumer and data-owner requirements
- Measured quality results tied to dataset and pipeline revisions

## Decision checks

- Name the consumer purpose and failure impact before selecting quality dimensions.
- Define metric, population, sampling, expected value or range, threshold, and measurement time.
- Choose warn, block, quarantine, degrade, or annotate behavior with an owner.
- Preserve actual results, severity, affected dataset or columns, and remediation lifecycle.

## Required evidence

- Consumer and data-owner requirements
- Measured quality results tied to dataset and pipeline revisions

## Reject or stop when

- A universal quality score replaces purpose-specific metrics.
- A blocking threshold has no owner, false-positive treatment, or recovery path.

## Verification

- Inject a representative quality failure and observe warn, block, quarantine, and recovery behavior.
- Confirm reported measurements identify exact dataset, columns, run, and rule version.

## Counterexamples

- Do not use application referential integrity as the only analytical quality model.
- Do not block an exploratory dataset on production thresholds without an owner decision.
