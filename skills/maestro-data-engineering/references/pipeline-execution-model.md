# Pipeline Execution Model

## Purpose

Choose bounded or unbounded execution, event-time semantics, windows, triggers, watermarks, lateness, and runner capability.

## Use when

- batch pipeline
- stream processing
- etl
- elt
- data orchestration
- airflow dag
- event time
- watermark
- 배치 파이프라인
- 스트림 처리
- 데이터 오케스트레이션
- Airflow DAG
- 이벤트 시간
- 워터마크

## Inputs

- The task goal, affected artifacts, users, owners, constraints, and lifecycle state
- Source characteristics, lateness distribution, consumer timeliness needs
- Versioned runner and connector capability evidence

## Decision checks

- Classify each input as bounded or unbounded and choose batch, streaming, or a deliberate hybrid.
- Define event time, processing time, windows, triggers, watermarks, allowed lateness, and pane accumulation where applicable.
- State update, correction, and finalization semantics visible to downstream consumers.
- Verify the selected runner and connectors support the required model and guarantees.

## Required evidence

- Source characteristics, lateness distribution, consumer timeliness needs
- Versioned runner and connector capability evidence

## Reject or stop when

- An unbounded aggregation has no window, trigger, or state-retention decision.
- Model-level semantics are assumed supported by a runner without versioned evidence.

## Verification

- Replay representative late and out-of-order data and inspect emitted revisions.
- Compare planned features against the target runner capability matrix.

## Counterexamples

- Do not turn a finite daily file into a continuously running stream without a need.
- Do not use processing time when the business result requires event-time ordering.
