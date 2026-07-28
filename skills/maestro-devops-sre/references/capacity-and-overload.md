# Capacity And Overload

## Purpose

Model limiting resources, demand, headroom, lead time, scaling, admission, queueing, quotas, load shedding, degradation, and bounded retry.

## Use when

- capacity planning
- autoscaling headroom
- autoscaling
- backpressure
- overload control
- load shedding
- admission control
- 용량 계획
- 오토스케일링 헤드룸
- 오토스케일링
- 백프레셔
- 과부하 제어
- 로드 셰딩
- 어드미션 제어

## Inputs

- The task goal, affected artifacts, users, owners, constraints, and lifecycle state
- Representative load and resource measurements
- Provisioning lead time, scaling limits, dependency quotas, and failure assumptions

## Decision checks

- Segment workload classes and map them to limiting resources and dependency costs.
- Forecast normal, growth, event, and failure demand across provisioning lead time.
- Derive headroom from availability and degradation goals; validate the resource-to-capacity model.
- Choose scaling, concurrency, queue, quota, admission, shedding, degradation, and retry behavior before saturation.

## Required evidence

- Representative load and resource measurements
- Provisioning lead time, scaling limits, dependency quotas, and failure assumptions

## Reject or stop when

- A queue can grow without a bound, expiry, or overload signal.
- Retries increase offered load after the system crosses its sustainable capacity.

## Verification

- Load-test representative request-cost classes through saturation and recovery.
- Verify graceful degradation and priority behavior under constrained dependencies.

## Counterexamples

- Do not use average request rate as the only capacity model when request cost varies.
- Do not optimize a microbenchmark while the limiting production resource is unknown.
