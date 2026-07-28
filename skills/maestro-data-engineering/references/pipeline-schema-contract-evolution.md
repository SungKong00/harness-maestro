# Pipeline Schema Contract Evolution

## Purpose

Choose directional writer-reader compatibility, field identity, schema preservation, defaults, promotion, rollout, and replay behavior.

## Use when

- pipeline schema evolution
- pipeline data contract
- analytical data contract
- avro schema compatibility
- writer reader schema
- table format evolution
- 파이프라인 스키마 진화
- 파이프라인 데이터 계약
- 분석 데이터 계약
- Avro 스키마 호환성
- writer reader 스키마
- 테이블 포맷 진화
- 스키마 변경 백필

## Inputs

- The task goal, affected artifacts, users, owners, constraints, and lifecycle state
- Versioned schema and table-format rules
- Producer, consumer, stored-data, and replay inventory

## Decision checks

- Identify producer, stored writer schema, current and historical consumers, replay, and compatibility direction.
- Define stable field identity, optionality, defaults, aliases, type promotion, and semantic meaning.
- Separate format-level compatibility from semantic and consumer compatibility.
- Plan producer, storage, consumer, and backfill rollout across mixed versions.

## Required evidence

- Versioned schema and table-format rules
- Producer, consumer, stored-data, and replay inventory

## Reject or stop when

- A field change preserves bytes but changes meaning without a migration decision.
- Historical data cannot be read by the mixed-version rollout.

## Verification

- Run writer-reader compatibility checks in both required directions.
- Read historical and newly written data with old, mixed, and new consumers.

## Counterexamples

- Do not generalize Avro resolution rules to every serialization format.
- Do not use field names as stable identity when the chosen table format requires IDs.
