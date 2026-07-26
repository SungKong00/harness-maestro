# QA risk and traceability

## Purpose

Spend test effort according to plausible harm and make important behaviors
traceable to evidence.

## Risk model

For each changed behavior record:

- failure mode and affected user, data, money, security, or operation;
- likelihood or exposure;
- impact and reversibility;
- detectability before and after release;
- existing control and residual risk.

Rank comparatively; do not pretend subjective scores are measured probability.

## Traceability checks

1. Decompose requirements into observable behavior, constraint, and quality
   condition.
2. Link each high-risk item to one or more tests and an expected evidence type.
3. Include explicit non-goals and unsupported environments.
4. Mark ambiguity, contradiction, and untestable wording before implementation.
5. Trace important architecture constraints and data migrations, not only UI
   acceptance statements.
6. Keep uncovered risks visible with owner and disposition.

## Reject

Test counts and code coverage alone do not establish risk coverage. A
requirement such as “works correctly” or “is fast” is not testable until its
observable condition and boundary are stated.
