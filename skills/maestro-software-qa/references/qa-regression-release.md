# QA regression and release

## Purpose

Choose proportionate regression scope and define a truthful release evidence
packet.

## Regression selection

1. Map changed files and contracts to callers, consumers, data, and deployment
   surfaces.
2. Include the direct change, adjacent invariant, historic failure area, and
   critical smoke path.
3. Expand for shared libraries, schema changes, feature flags, security
   boundaries, and irreversible operations.
4. Reduce redundant low-signal tests; do not use “run everything” as the only
   strategy.
5. Define rollback or forward-fix validation for material releases.

## Release evidence

Record revision, environment, commands, timestamps, result counts, artifact
links, known failures, excluded scope, waivers, and decision owner. A release
recommendation states confidence and residual risk, not “bug free.”

## Stop conditions

Block the recommendation when a critical behavior has no oracle, the evidence
does not match the candidate build, a migration lacks recovery evidence, or a
failed high-risk check is waived without an owner and rationale.
