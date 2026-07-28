# Contracts And Invariants

## Purpose

Define caller obligations, provider guarantees, stable-state invariants, errors, and evidence for public or internal behavior.

## Use when

- behavior contract
- precondition
- postcondition
- invariant
- error contract
- REST API data contract
- API payload contract
- 동작 계약
- 사전 조건
- 사후 조건
- 불변식
- 오류 계약
- 공개 API

## Inputs

- The task goal, affected artifacts, users, owners, constraints, and lifecycle state
- Current implementation, schema, and representative consumer evidence
- Explicit examples for success, invalid input, conflict, and partial failure

## Decision checks

- Separate caller preconditions, provider postconditions, and invariants that must hold after every completed operation.
- Distinguish public, cross-module, persisted, and purely local contracts.
- Define success, rejection, partial-effect, timeout, cancellation, and retry-visible outcomes.
- Use requirement language consistently and tie mandatory claims to observable behavior.
- Bind schemas, examples, and documentation to executable or source evidence rather than treating prose as proof.

## Required evidence

- Current implementation, schema, and representative consumer evidence
- Explicit examples for success, invalid input, conflict, and partial failure

## Reject or stop when

- A mandatory behavior cannot be observed or verified.
- The contract hides ownership or leaves a partial state semantically undefined.

## Verification

- Demonstrate that a plausible wrong implementation would violate a named invariant.
- Compare public documentation and examples against executable behavior or source.

## Counterexamples

- Do not turn an internal helper detail into a permanent public promise.
- Do not use MUST or SHOULD to hide an unresolved product or policy choice.
