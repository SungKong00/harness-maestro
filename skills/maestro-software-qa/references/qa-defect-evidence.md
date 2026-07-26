# QA defect evidence

## Purpose

Turn an observation into a reproducible, diagnosable quality artifact.

## Required evidence

- concise observed-versus-expected statement;
- exact build, environment, account/role, locale, and relevant configuration;
- minimal deterministic steps and prerequisite data;
- frequency and first known occurrence;
- logs, request IDs, screenshot/video, trace, or failing test as appropriate;
- impact, scope, workaround, and data or privacy sensitivity;
- suspected area labeled as hypothesis, not fact.

## Decision checks

1. Minimize the reproduction without deleting the causal condition.
2. Verify whether the result conflicts with an actual requirement or invariant.
3. Distinguish duplicate symptom from shared root cause.
4. Preserve evidence safely; redact secrets and unnecessary personal data.
5. After a fix, prove the original failure and an adjacent regression boundary.

## Reject

“It does not work” is not reproducible evidence. A screenshot alone rarely
proves state, sequence, network, or build. Severity describes impact; priority
is a product decision and must not be silently substituted.
