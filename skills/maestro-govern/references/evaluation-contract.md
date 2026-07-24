# Evaluation contract

Compare the current and candidate workflow on the same stratified, frozen held-out cases. Pin the base revision, model policy, tools, budget, conventions, and adapter versions. Record proposal-case and held-out-case IDs and reject any overlap.

The held-out set must include positive, negative or out-of-scope, and existing regression cases. Keep the candidate proposer from seeing held-out expected answers. Use deterministic oracles first; calibrate any model grader against separately human-reviewed examples.

Measure:

- outcome and verifier result;
- correction and rollback count;
- unique decision-changing evidence;
- duplicate packet rate;
- parent-context tokens and total-system tokens separately;
- wall time and tool calls;
- human correction required.

Use raw artifacts and hide the intended answer from the evaluator. Compare baseline and candidate under equal conditions. A candidate may be promoted only after forward tests, zero critical regressions, explicit cost review, independent verification, and owner approval. Repetition count only opens review.
