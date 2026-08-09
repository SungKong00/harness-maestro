# Failure Semantics And Recovery

## Purpose

Define timeout, cancellation, retry, degradation, compensation, and recovery behavior without amplifying failures.

## Use when

- failure semantics
- timeout design
- retry policy
- backoff jitter
- cancellation propagation
- 실패 의미
- 타임아웃 설계
- 재시도 정책
- 재시도
- 응답이 끊긴
- 백오프 지터
- 취소 전파

## Inputs

- The task goal, affected artifacts, users, owners, constraints, and lifecycle state
- Dependency latency, failure, and side-effect semantics
- Retry budget, deadline, recovery owner, and observable failure signal

## Decision checks

- Classify failures as permanent, retryable, ambiguous, partial, or overload before choosing a response.
- Set end-to-end deadlines and propagate remaining time and cancellation through dependency calls.
- Place bounded retries at one accountable layer and use backoff with jitter where synchronized retry is harmful.
- Define whether partial effects are rolled back, compensated, reconciled, or exposed for manual recovery.
- Keep success signals behind the durable effect they claim.

## Required evidence

- Dependency latency, failure, and side-effect semantics
- Retry budget, deadline, recovery owner, and observable failure signal

## Reject or stop when

- A timeout is treated as proof that no effect occurred.
- Multiple layers retry independently without a shared budget.
- Recovery depends on sensitive diagnostics that are not protected.

## Verification

- Inject timeout, overload, cancellation, and partial-effect cases at the real boundary.
- Verify that work stops after cancellation and recovery restores the declared invariant.

## Counterexamples

- Do not retry validation or authorization failures.
- Do not add backoff to an operation whose duplicate side effects remain undefined.
