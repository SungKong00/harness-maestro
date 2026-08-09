# State Recovery And Delivery Semantics

## Purpose

Choose replayable sources, state and offset snapshots, checkpoint or savepoint use, delivery guarantee scope, and sink transaction or idempotence.

## Use when

- pipeline recovery
- checkpoint restore
- checkpoint savepoint
- pipeline delivery semantics
- exactly once pipeline
- 파이프라인 복구
- 체크포인트 복원
- 체크포인트 세이브포인트
- 파이프라인 전달 의미
- exactly once 파이프라인
- 체크포인트 복구

## Inputs

- The task goal, affected artifacts, users, owners, constraints, and lifecycle state
- Versioned engine, source, connector, and sink guarantees
- Failure-injection evidence for state, offsets, duplicates, and external outputs

## Decision checks

- Define failure classes and replay behavior for source, operator state, offsets, timers, and sinks.
- Choose checkpoint, savepoint, restart, and upgrade behavior and their consistency boundary.
- State at-most-once, at-least-once, or exactly-once separately for each stage and external side effect.
- Coordinate source position and output with transactions or idempotence where end-to-end guarantees require it.

## Required evidence

- Versioned engine, source, connector, and sink guarantees
- Failure-injection evidence for state, offsets, duplicates, and external outputs

## Reject or stop when

- Exactly-once is claimed for an external sink without transaction or idempotency support.
- Recovery restores operator state but loses or reorders the corresponding source position.

## Verification

- Kill and restore a representative stateful pipeline and compare output and state invariants.
- Inject sink failure and duplicate replay at the real connector boundary.

## Counterexamples

- Do not interpret exactly-once as physical single execution.
- Do not require transactional sinks when at-least-once plus idempotent materialization is sufficient.
