# Telemetry Architecture

## Purpose

Choose signals, correlation, semantic conventions, collection topology, sampling, cardinality, cost, and telemetry-failure behavior from operational questions.

## Use when

- telemetry architecture
- observability design
- trace sampling
- metric cardinality
- 텔레메트리 아키텍처
- 관측성 설계
- 트레이스 샘플링
- 메트릭 카디널리티

## Inputs

- The task goal, affected artifacts, users, owners, constraints, and lifecycle state
- Current instrumentation and collector capability
- Signal volume, cardinality, sampling, retention, and cost estimates
- Representative failure and correlation queries

## Decision checks

- Start from concrete detection, diagnosis, capacity, and audit questions.
- Map each question to traces, metrics, logs, profiles, or events with stable identity and correlation.
- Choose semantic conventions, collection topology, buffering, sampling, retention, and cardinality limits.
- Define sensitive-data handling, cost ownership, and behavior when the telemetry pipeline degrades.

## Required evidence

- Current instrumentation and collector capability
- Signal volume, cardinality, sampling, retention, and cost estimates
- Representative failure and correlation queries

## Reject or stop when

- Sensitive or unbounded high-cardinality data is emitted without need and protection.
- A success or alert signal can precede the durable effect it claims.

## Verification

- Trace a representative request and failure across the chosen correlation fields.
- Load-test telemetry volume and exercise collector or exporter failure.

## Counterexamples

- Do not collect every signal at full fidelity by default.
- Do not replace a missing domain event with an unrelated infrastructure metric.
