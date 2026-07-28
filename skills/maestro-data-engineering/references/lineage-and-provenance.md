# Lineage And Provenance

## Purpose

Design stable dataset, job, and run identity plus input-output derivation, runtime and design lineage, versions, and transformation evidence.

## Use when

- data lineage
- data provenance
- openlineage
- dataset identity
- 데이터 리니지
- 데이터 프로비넌스
- OpenLineage
- 데이터셋 식별

## Inputs

- The task goal, affected artifacts, users, owners, constraints, and lifecycle state
- Current orchestration, storage, and catalog identities
- Representative lineage events across retries, branches, and version changes

## Decision checks

- Define stable namespaces and identities for datasets, jobs, runs, code, schema, and owners.
- Capture input use, output generation, derivation, attribution, and relevant transformations.
- Separate runtime run events from design-time job and dataset metadata.
- Choose required granularity and retention from debugging, impact, audit, and cost needs.

## Required evidence

- Current orchestration, storage, and catalog identities
- Representative lineage events across retries, branches, and version changes

## Reject or stop when

- Identity collisions merge unrelated datasets or runs.
- Declared lineage omits a material input, output, or transformation boundary.

## Verification

- Trace one output back to exact inputs, code or job version, schema, and run.
- Verify retry and backfill events remain distinguishable without duplicating identities.

## Counterexamples

- Do not collect column lineage when dataset-level impact analysis is sufficient.
- Do not treat logs without stable dataset and run identity as interoperable lineage.
