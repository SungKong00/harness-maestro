# State Concurrency And Idempotency

## Purpose

Choose coordination, isolation, and idempotency from state invariants, competing operations, and retry semantics.

## Use when

- transaction design
- concurrency control design
- transaction isolation design
- webhook idempotency
- exactly once webhook
- idempotency
- duplicate request
- race condition control
- 트랜잭션 설계
- 동시성 제어 설계
- 트랜잭션 격리 설계
- 멱등성
- 중복 요청
- 경쟁 상태 제어

## Inputs

- The task goal, affected artifacts, users, owners, constraints, and lifecycle state
- A competing-operation map and concrete failing interleaving
- Storage or coordination semantics for the selected mechanism
- Evidence for duplicate, retry, partial-commit, and recovery behavior

## Decision checks

- Name the invariant, state owner, and every operation class that can read or write the decision state.
- Identify the anomaly or interleaving that must be forbidden before selecting isolation, locking, or optimistic control.
- Define the meaning of retry after timeout or unknown commit outcome.
- Use a stable idempotency key and persist its decision atomically with the protected mutation when deduplication is required.
- Specify key scope, semantic-equivalence rules, retention, conflict behavior, and recovery.

## Required evidence

- A competing-operation map and concrete failing interleaving
- Storage or coordination semantics for the selected mechanism
- Evidence for duplicate, retry, partial-commit, and recovery behavior

## Reject or stop when

- Only the primary writer is coordinated while another mutation path remains unclassified.
- Idempotency is claimed without a stable key or durable decision.
- The selected isolation behavior is assumed from a generic database label.

## Verification

- Exercise two competing operations and a retry after an ambiguous outcome.
- Confirm the invariant from durable state, not only response status or mock calls.

## Counterexamples

- Do not add distributed locking to a single-owner in-memory calculation.
- Do not equate an idempotent HTTP method with an implementation that cannot duplicate external effects.
