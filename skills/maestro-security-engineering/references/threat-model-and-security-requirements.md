# Threat Model And Security Requirements

## Purpose

Turn assets, trust boundaries, attackers, and abuse paths into scoped security requirements and residual-risk decisions.

## Use when

- threat model
- trust boundary
- abuse case
- security requirement
- security architecture
- 위협 모델
- 신뢰 경계
- 오용 사례
- 보안 요구사항
- 보안 아키텍처

## Inputs

- The task goal, affected artifacts, users, owners, constraints, and lifecycle state
- Current data-flow and trust-boundary evidence
- Asset classification, threat assumptions, and named risk owner

## Decision checks

- Inventory protected assets, actors, entry points, data flows, trust boundaries, and privileged operations.
- State attacker capabilities, misuse assumptions, and the impact of compromise or denial.
- Trace each material threat to prevention, detection, response, and residual-risk ownership.
- Revisit the model when architecture, identity, data classification, or external dependencies change.

## Required evidence

- Current data-flow and trust-boundary evidence
- Asset classification, threat assumptions, and named risk owner

## Reject or stop when

- A severe threat has no treatment or explicit owner acceptance.
- The model omits an entry point or privileged fallback path.

## Verification

- Trace every material requirement back to a threat and affected asset.
- Verify implemented enforcement at the real trust boundary.

## Counterexamples

- Do not require one threat-modeling notation for every project.
- Do not convert an unverified brainstorming list into a security certification.
